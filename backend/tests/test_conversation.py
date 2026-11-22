from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.db import SessionLocal
from app.models import PendingAction
from tests.conftest import login
from tests.test_trade import DISTRIBUTOR, SELLER, SWITCH, quote, stock


def chat(client, h, org=DISTRIBUTOR):
    conv = client.post(f"/api/v1/orgs/{org}/conversations", headers=h).json()["id"]

    def say(text):
        r = client.post(f"/api/v1/orgs/{org}/conversations/{conv}/messages", headers=h, json={"text": text})
        assert r.status_code == 200, r.text
        return r.json()

    return say


def press_confirm(client, h, action, org=DISTRIBUTOR):
    return client.post(f"/api/v1/orgs/{org}/pending-actions/{action['id']}/confirm", headers=h)


def test_find_quote_and_order_through_conversation(client):
    buyer = login(client, "lakshmi.admin@example.test")
    seller = login(client, "anitha.catalog@example.test")
    say = chat(client, buyer)

    found = say("I need 6A one-way switch, 100")
    assert "2. 6A one-way modular switch, box of 10, Sri Lakshmi Switchgear (Fictional): ₹450.00 per box, 500 in stock, minimum 5" in found["reply"]
    assert "resale" not in found["reply"]  # the buyer's own organization's listing is excluded
    assert found["pending_action"] is None

    assert "Which product number" in say("get a quote")["reply"]
    assert "How many boxes? The minimum is 5." in say("2")["reply"]
    assert "minimum is 5" in say("3")["reply"]  # below MOQ: asks again
    assert say("10")["reply"] == "Which city should it be delivered to?"
    proposal = say("Guntur")
    assert "10 boxes of 6A one-way modular switch, box of 10, delivered to Guntur" in proposal["reply"]
    rfq = press_confirm(client, buyer, proposal["pending_action"])
    assert rfq.status_code == 200, rfq.text
    rfq = rfq.json()["rfq"]
    assert (rfq["product_id"], rfq["quantity"], rfq["status"]) == (str(SWITCH), 10, "open")

    sent = quote(client, seller, rfq["id"])
    listing = say("order")
    assert "total ₹5,357.20 (simulated)" in listing["reply"]
    readback = say("1")
    assert "Total ₹5,357.20, including ₹817.20 simulated tax. Advance ₹1,000.00." in readback["reply"]
    assert readback["pending_action"]["payload"] == {"quote_id": sent["id"], "quote_version": 1, "total_paise": 535720}

    first = press_confirm(client, buyer, readback["pending_action"])
    assert first.status_code == 200, first.text
    again = press_confirm(client, buyer, readback["pending_action"])
    assert again.json()["order"]["id"] == first.json()["order"]["id"]
    assert stock(client, seller) == 490
    assert "no open quotes" in say("show my quotes")["reply"]


def test_old_expired_and_foreign_pending_actions_are_refused(client):
    buyer = login(client, "lakshmi.admin@example.test")
    say = chat(client, buyer)
    say("find 6A switch")
    say("quote")
    say("1")
    say("100")
    old = say("Guntur")["pending_action"]

    say("help")  # any later message withdraws the earlier proposal
    r = press_confirm(client, buyer, old)
    assert r.status_code == 409 and r.json()["error"]["details"] == {"status": "cancelled"}

    say("quote")
    say("1")
    say("100")
    fresh = say("Guntur")["pending_action"]
    other_user = login(client, "suresh.buyer@example.test")
    assert press_confirm(client, other_user, fresh).status_code == 404
    with SessionLocal() as db:
        db.execute(update(PendingAction).where(PendingAction.id == fresh["id"]).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        db.commit()
    r = press_confirm(client, buyer, fresh)
    assert r.status_code == 409 and r.json()["error"]["details"] == {"status": "expired"}
    assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/rfqs", headers=buyer).json() == []


def test_confirmation_rechecks_permissions(client):
    viewer = login(client, "meena.viewer@example.test")
    say = chat(client, viewer)
    say("find 6A switch")
    say("quote")
    say("1")
    say("100")
    action = say("Guntur")["pending_action"]
    assert press_confirm(client, viewer, action).status_code == 403


def test_conversations_are_private(client):
    buyer = login(client, "lakshmi.admin@example.test")
    conv = client.post(f"/api/v1/orgs/{DISTRIBUTOR}/conversations", headers=buyer).json()["id"]
    colleague = login(client, "suresh.buyer@example.test")
    r = client.post(f"/api/v1/orgs/{DISTRIBUTOR}/conversations/{conv}/messages", headers=colleague, json={"text": "show"})
    assert r.status_code == 404


def test_telugu_and_cancel(client):
    buyer = login(client, "suresh.buyer@example.test")  # preferred language te
    say = chat(client, buyer)
    assert "దొరికాయి" in say("6A స్విచ్ కావాలి")["reply"]
    assert "జాబితాలో" in say("కొటేషన్")["reply"]
    assert "రద్దు" in say("రద్దు")["reply"]
    assert "ఉదాహరణ" in say("1")["reply"]  # no active intent after cancel: help, not a quantity


def test_spoken_telugu_numbers_and_variants(client):
    # Words Chrome's te-IN speech recognition produced in the owner's test on 22 November 2026.
    from app.conversation import te_digits
    assert te_digits("ఆరు ఆమ్ స్విచ్ కావాలి") == "6 ఆమ్ స్విచ్ కావాలి"
    assert te_digits("ఒక స్విచ్") == "ఒక స్విచ్"  # "a switch", not a number
    assert te_digits("ఆర్ ఆంపియర్ స్విచ్") == "6 ఆంపియర్ స్విచ్" and te_digits("ఆరే ఆంపియర్") == "6 ఆంపియర్"
    assert te_digits("ఆర్డర్ ఆర్ చూపించు") == "ఆర్డర్ ఆర్ చూపించు"  # not before an amp word
    from app.conversation import INTENTS
    quote = dict(INTENTS)["request_quote"]
    assert quote.search("కోట్") and quote.search("కోటేషన్") and not quote.search("పది కోట్లు")  # not "ten crores"
    say = chat(client, login(client, "suresh.buyer@example.test"))
    for spoken in ("ఆరు ఆమ్ స్విచ్ కావాలి", "ఆరు ఆంపియర్ స్విచ్ కావాలి", "find 6 ampere switch"):
        six = say(spoken)["reply"]
        assert "6A" in six and "16A" not in six, spoken
    two = say("టు వే స్విచ్ వెతుకు")["reply"]
    assert "two-way" in two and "one-way" not in two
    assert "జాబితాలో" in say("కోట్")["reply"]  # English "quote" as Telugu speech writes it
    say("ఒకటి")  # the first listed product
    say("వంద")
    action = say("గుంటూరు")["pending_action"]
    assert action["payload"]["quantity"] == 100 and action["payload"]["delivery_city"] == "గుంటూరు"


def test_assistant_never_invents_quotes(client):
    say = chat(client, login(client, "lakshmi.admin@example.test"))
    assert say("order")["reply"] == "You have no open quotes right now."
    assert say("quote")["reply"].startswith("First tell me what to find")
    seller_chat = chat(client, login(client, "ravi.seller@example.test"), org=SELLER)
    assert "Sri Lakshmi" not in seller_chat("find 6A switch")["reply"]  # a seller is not shown its own listings


def test_retried_message_is_stored_once_and_replays_its_reply(client):
    # F01d: a lost response is retried with the same key; nothing is stored twice and the proposal is not withdrawn.
    buyer = login(client, "lakshmi.admin@example.test")
    base = f"/api/v1/orgs/{DISTRIBUTOR}/conversations"
    conv = client.post(base, headers=buyer).json()["id"]
    url = f"{base}/{conv}/messages"

    def send(text, key):
        return client.post(url, headers={**buyer, "Idempotency-Key": key}, json={"text": text})

    for text, key in (("find 6A switch", "k1"), ("quote", "k2"), ("1", "k3"), ("100", "k4")):
        assert send(text, key).status_code == 200
    first = send("Guntur", "k5").json()
    again = send("Guntur", "k5")
    assert again.status_code == 200 and again.json() == first and first["pending_action"] is not None
    texts = [m["text"] for m in client.get(url, headers=buyer).json()]
    assert texts.count("Guntur") == 1 and len(texts) == 10
    assert press_confirm(client, buyer, first["pending_action"]).status_code == 200  # the replay did not withdraw it

    assert send("Vijayawada", "k5").status_code == 409  # same key, different text
    assert send("help", "k6").status_code == 200
    stale = send("Guntur", "k5").json()  # an old retry after newer messages: same reply, no live proposal offered
    assert stale["reply"] == first["reply"] and stale["pending_action"] is None
    assert len(client.get(url, headers=buyer).json()) == 12
    other = login(client, "suresh.buyer@example.test")
    assert client.post(url, headers={**other, "Idempotency-Key": "k5"}, json={"text": "Guntur"}).status_code == 404


def test_owner_stream_signals_changes_without_content(client, monkeypatch):
    # F01d live updates: the owner's stream wakes on a committed change and carries no message text.
    import threading
    import time

    from app import events

    monkeypatch.setattr(events, "STREAM_SECONDS", 3)
    buyer = login(client, "lakshmi.admin@example.test")
    base = f"/api/v1/orgs/{DISTRIBUTOR}/conversations"
    conv = client.post(base, headers=buyer).json()["id"]
    assert client.get(f"{base}/{conv}/events", headers=login(client, "suresh.buyer@example.test")).status_code == 404

    secret = "private words for the stream test"

    def later():
        time.sleep(0.5)
        client.post(f"{base}/{conv}/messages", headers=buyer, json={"text": secret})

    with client.stream("GET", f"{base}/{conv}/events", headers=buyer) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        lines = r.iter_lines()
        assert next(lines) == "event: ready"
        writer = threading.Thread(target=later)
        writer.start()
        started = time.monotonic()
        seen = []
        for line in lines:
            seen.append(line)
            if line == "event: changed":
                break
        writer.join()
    assert "event: changed" in seen and time.monotonic() - started < 2.5  # pushed, not waiting for a keepalive
    assert secret not in "\n".join(seen)
