from sqlalchemy import func, update

from app.db import SessionLocal
from app.models import Message, PendingAction, StaffGrant
from app.seed import _id
from tests.conftest import login
from tests.test_conversation import chat, press_confirm
from tests.test_payments import code, order, payments
from tests.test_trade import DISTRIBUTOR, RETAILER, SELLER, confirm, quote, race, rfq, setup

SHA = "a" * 64


def open_case(client, h, o, org=DISTRIBUTOR):
    return client.post(f"/api/v1/orgs/{org}/orders/{o['id']}/cases", headers=h,
                       json={"category": "damaged", "description": "3 switches arrived cracked", "urgency": "high"})


def staff(client, email):
    return login(client, email)


def test_complaint_lifecycle_and_privacy(client):
    buyer, seller, o = order(client)
    case = open_case(client, buyer, o)
    assert case.status_code == 201, case.text
    case = case.json()
    cid = case["id"]
    viewer = login(client, "meena.viewer@example.test")
    outsider = login(client, "kiran.retail@example.test")
    sanjay, vani, farah = (staff(client, e) for e in ("sanjay.support@example.test", "vani.support@example.test", "farah.finance@example.test"))

    assert open_case(client, seller, o, org=SELLER).status_code == 403  # seller cannot open the buyer's complaint
    assert client.get(f"/api/v1/orgs/{SELLER}/cases/{cid}", headers=seller).status_code == 200
    assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/cases/{cid}", headers=viewer).status_code == 200
    assert client.post(f"/api/v1/orgs/{DISTRIBUTOR}/cases/{cid}/updates", headers=viewer, json={"body": "x"}).status_code == 403
    assert client.get(f"/api/v1/orgs/{RETAILER}/cases/{cid}", headers=outsider).status_code == 404
    assert client.get("/api/v1/staff/cases", headers=farah).status_code == 403  # finance has no case access

    queue = client.get("/api/v1/staff/cases", headers=vani).json()
    assert queue == [{"id": cid, "category": "damaged", "urgency": "high", "status": "open", "created_at": queue[0]["created_at"]}]
    taken = client.post(f"/api/v1/staff/cases/{cid}/take", headers=sanjay)
    assert taken.status_code == 200 and taken.json()["status"] == "assigned"
    assert client.post(f"/api/v1/staff/cases/{cid}/take", headers=vani).status_code == 409
    assert client.get(f"/api/v1/staff/cases/{cid}", headers=vani).status_code == 404
    assert client.post(f"/api/v1/staff/cases/{cid}/updates", headers=vani, json={"body": "x"}).status_code == 404

    internal = client.post(f"/api/v1/staff/cases/{cid}/updates", headers=sanjay, json={"body": "Seller has a history of packing issues", "visibility": "internal"})
    visible = client.post(f"/api/v1/staff/cases/{cid}/updates", headers=sanjay, json={"body": "We are checking with the seller."})
    assert internal.status_code == visible.status_code == 201
    client.post(f"/api/v1/orgs/{SELLER}/cases/{cid}/updates", headers=seller, json={"body": "Photos please"})
    for h, org in ((buyer, DISTRIBUTOR), (seller, SELLER)):
        bodies = [u["body"] for u in client.get(f"/api/v1/orgs/{org}/cases/{cid}", headers=h).json()["updates"]]
        assert bodies == ["We are checking with the seller.", "Photos please"]
    assert len(client.get(f"/api/v1/staff/cases/{cid}", headers=sanjay).json()["updates"]) == 3

    assert client.post(f"/api/v1/staff/cases/{cid}/investigate", headers=sanjay).json()["status"] == "investigating"
    assert code(client.post(f"/api/v1/orgs/{DISTRIBUTOR}/cases/{cid}/close", headers=buyer)) == "invalid_transition"
    resolved = client.post(f"/api/v1/staff/cases/{cid}/resolve", headers=sanjay, json={"resolution": "Seller will replace 3 units."})
    assert resolved.json()["status"] == "resolved"
    assert client.post(f"/api/v1/orgs/{SELLER}/cases/{cid}/reopen", headers=login(client, "ravi.seller@example.test")).status_code == 403
    reopened = client.post(f"/api/v1/orgs/{DISTRIBUTOR}/cases/{cid}/reopen", headers=buyer).json()
    assert (reopened["status"], reopened["reopen_count"]) == ("assigned", 1)
    client.post(f"/api/v1/staff/cases/{cid}/resolve", headers=sanjay, json={"resolution": "Replacement delivered."})
    assert client.post(f"/api/v1/orgs/{DISTRIBUTOR}/cases/{cid}/close", headers=buyer).json()["status"] == "closed"
    assert code(client.post(f"/api/v1/orgs/{DISTRIBUTOR}/cases/{cid}/updates", headers=buyer, json={"body": "x"})) == "invalid_transition"
    assert payments(client, buyer, o)["received_paise"] == 0 and payments(client, buyer, o)["events"] == []


def test_evidence_is_metadata_only_and_scoped(client):
    buyer, seller, o = order(client)
    cid = open_case(client, buyer, o).json()["id"]
    url = f"/api/v1/orgs/{DISTRIBUTOR}/cases/{cid}/evidence"
    good = {"filename": "box.jpg", "content_type": "image/jpeg", "size_bytes": 2048, "sha256": SHA}
    r = client.post(url, headers=buyer, json=good)
    assert r.status_code == 201 and not any("url" in k for k in r.json())
    assert client.post(url, headers=buyer, json=good | {"sha256": "nothex"}).status_code == 400
    assert client.post(url, headers=buyer, json=good | {"size_bytes": 21 * 1024 * 1024}).status_code == 400
    outsider = login(client, "kiran.retail@example.test")
    assert client.post(f"/api/v1/orgs/{RETAILER}/cases/{cid}/evidence", headers=outsider, json=good).status_code == 404
    assert [e["filename"] for e in client.get(f"/api/v1/orgs/{SELLER}/cases/{cid}", headers=seller).json()["evidence"]] == ["box.jpg"]


def pending_order(client):
    buyer, seller = setup(client)
    quote(client, seller, rfq(client, buyer)["id"])
    say = chat(client, buyer)
    say("order")
    return buyer, seller, say, say("1")["pending_action"]


def messages(client, h, say_conv):
    return client.get(f"/api/v1/orgs/{DISTRIBUTOR}/conversations/{say_conv}/messages", headers=h).json()


def test_handoff_pauses_automation_until_released(client):
    buyer, seller, say, stale = pending_order(client)
    asked = say("I want to talk to a person")
    assert "support" in asked["reply"] or "సపోర్ట్" in asked["reply"]
    r = press_confirm(client, buyer, stale)
    assert r.status_code == 409 and code(r) == "conversation_paused"
    paused = say("order")
    assert paused["pending_action"] is None and ("handling" in paused["reply"] or "చూస్తున్నారు" in paused["reply"])

    sanjay, vani = staff(client, "sanjay.support@example.test"), staff(client, "vani.support@example.test")
    assert client.get("/api/v1/staff/handoffs", headers=staff(client, "farah.finance@example.test")).status_code == 403
    (item,) = client.get("/api/v1/staff/handoffs", headers=vani).json()
    assert set(item) == {"id", "urgency", "status", "created_at", "your_case_id"} and item["your_case_id"] is None  # nothing revealing before take
    hid = item["id"]
    assert client.get(f"/api/v1/staff/handoffs/{hid}", headers=vani).status_code == 404
    summary = client.post(f"/api/v1/staff/handoffs/{hid}/take", headers=sanjay).json()
    assert summary["cancelled_actions"] == ["confirm_order"]
    assert summary["organization_name"].startswith("Godavari") and summary["language"] == "te"
    assert summary["recent_messages"][-2]["text"] == "order"  # then the stored paused reply
    assert client.post(f"/api/v1/staff/handoffs/{hid}/messages", headers=vani, json={"text": "hi"}).status_code == 404
    assert client.post(f"/api/v1/staff/handoffs/{hid}/release", headers=vani).status_code == 404

    sent = client.post(f"/api/v1/staff/handoffs/{hid}/messages", headers=sanjay, json={"text": "Hello, I can help with your order."})
    assert sent.status_code == 201
    conv = summary["conversation_id"]
    assert [m["role"] for m in messages(client, buyer, conv)][-1] == "agent"
    assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/conversations/{conv}/messages", headers=login(client, "lakshmi.admin@example.test")).status_code == 404

    assert client.post(f"/api/v1/staff/handoffs/{hid}/release", headers=sanjay).json()["status"] == "released"
    assert code(client.post(f"/api/v1/staff/handoffs/{hid}/messages", headers=sanjay, json={"text": "late"})) == "invalid_transition"
    say("order")
    fresh = say("1")["pending_action"]
    assert fresh is not None and press_confirm(client, buyer, fresh).status_code == 200
    assert code(press_confirm(client, buyer, stale)) == "pending_action_not_active"  # the pre-handoff proposal stays dead


def test_release_ends_the_former_assignees_access(client):
    buyer = login(client, "suresh.buyer@example.test")
    sanjay, vani = staff(client, "sanjay.support@example.test"), staff(client, "vani.support@example.test")
    base = f"/api/v1/orgs/{DISTRIBUTOR}/conversations"
    conv = client.post(base, headers=buyer).json()["id"]
    first = client.post(f"{base}/{conv}/handoff", headers=buyer, json={}).json()["id"]
    assert client.post(f"/api/v1/staff/handoffs/{first}/take", headers=sanjay).status_code == 200
    assert client.post(f"/api/v1/staff/handoffs/{first}/take", headers=sanjay).status_code == 200  # repeat while assigned
    assert client.get(f"/api/v1/staff/handoffs/{first}", headers=sanjay).status_code == 200
    assert client.post(f"/api/v1/staff/handoffs/{first}/release", headers=sanjay).status_code == 200

    # Released: no summary through GET or a repeated take, even before anyone else takes over.
    assert client.get(f"/api/v1/staff/handoffs/{first}", headers=sanjay).status_code == 404
    r = client.post(f"/api/v1/staff/handoffs/{first}/take", headers=sanjay)
    assert r.status_code == 409 and code(r) == "invalid_transition" and "recent_messages" not in r.text
    assert client.post(f"/api/v1/staff/handoffs/{first}/release", headers=sanjay).json()["status"] == "released"  # no transcript
    (mine,) = client.get("/api/v1/staff/handoffs?scope=mine", headers=sanjay).json()
    assert mine["id"] == first and "recent_messages" not in mine

    second = client.post(f"{base}/{conv}/handoff", headers=buyer, json={}).json()["id"]
    assert client.post(f"/api/v1/staff/handoffs/{second}/take", headers=vani).status_code == 200
    private = "Private message for the newly assigned agent"
    client.post(f"{base}/{conv}/messages", headers=buyer, json={"text": private})
    for r in (client.get(f"/api/v1/staff/handoffs/{first}", headers=sanjay),
              client.post(f"/api/v1/staff/handoffs/{first}/take", headers=sanjay),
              client.get(f"/api/v1/staff/handoffs/{second}", headers=sanjay),
              client.post(f"/api/v1/staff/handoffs/{second}/take", headers=sanjay)):
        assert r.status_code in (404, 409) and private not in r.text
    current = client.get(f"/api/v1/staff/handoffs/{second}", headers=vani)
    assert current.status_code == 200 and current.json()["recent_messages"][-2]["text"] == private  # then the stored paused reply
    assert messages(client, buyer, conv)[-2]["text"] == private  # the owner keeps their messages

    with SessionLocal() as db:  # a revoked support grant loses even the current view
        db.execute(update(StaffGrant).where(StaffGrant.user_id == _id("user:vani.support@example.test")).values(revoked_at=func.now()))
        db.commit()
    assert client.get(f"/api/v1/staff/handoffs/{second}", headers=vani).status_code == 403


def test_message_history_reaches_every_message(client):
    buyer = login(client, "suresh.buyer@example.test")
    base = f"/api/v1/orgs/{DISTRIBUTOR}/conversations"
    conv = client.post(base, headers=buyer).json()["id"]
    with SessionLocal() as db:
        db.add_all(Message(conversation_id=conv, role="user", text=f"Earlier message {i}") for i in range(520))
        db.commit()
    url = f"{base}/{conv}/messages"

    # Scroll back from the newest page until a short page: every message once, oldest first, no gaps.
    page = client.get(url, headers=buyer).json()
    assert len(page) == 100 and page[-1]["text"] == "Earlier message 519"
    seen = page
    while len(page) == 100:
        page = client.get(f"{url}?before={seen[0]['id']}", headers=buyer).json()
        seen = page + seen
    assert [m["text"] for m in seen] == [f"Earlier message {i}" for i in range(520)]
    ids = [m["id"] for m in seen]
    assert ids == sorted(set(ids))

    # Poll forward from the last id: a later agent reply arrives, then nothing new.
    handoff = client.post(f"{base}/{conv}/handoff", headers=buyer, json={}).json()["id"]
    sanjay = staff(client, "sanjay.support@example.test")
    client.post(f"/api/v1/staff/handoffs/{handoff}/take", headers=sanjay)
    client.post(f"/api/v1/staff/handoffs/{handoff}/messages", headers=sanjay, json={"text": "Agent reply"})
    new = client.get(f"{url}?after={ids[-1]}", headers=buyer).json()
    assert [m["role"] for m in new] == ["assistant", "agent"] and new[-1]["text"] == "Agent reply"
    assert client.get(f"{url}?after={new[-1]['id']}", headers=buyer).json() == []
    assert [m["text"] for m in client.get(f"{url}?after={ids[0]}&limit=2", headers=buyer).json()] == ["Earlier message 1", "Earlier message 2"]

    assert client.get(f"{url}?before=5&after=1", headers=buyer).status_code == 400
    for bad in ("limit=0", "limit=501", "before=0"):
        assert client.get(f"{url}?{bad}", headers=buyer).status_code in (400, 422), bad
    assert client.get(url, headers=login(client, "lakshmi.admin@example.test")).status_code == 404  # colleague, not owner
    assert client.get(url, headers=sanjay).status_code in (403, 404)


def test_forms_still_work_while_assistant_is_paused(client):
    buyer, seller = setup(client)
    q = quote(client, seller, rfq(client, buyer)["id"])
    say = chat(client, buyer)
    say("agent please")
    assert confirm(client, buyer, q).status_code == 201  # a person using the form is not the paused assistant


def test_handoff_request_rules(client):
    buyer, seller, o = order(client)
    conv = client.post(f"/api/v1/orgs/{DISTRIBUTOR}/conversations", headers=buyer).json()["id"]
    url = f"/api/v1/orgs/{DISTRIBUTOR}/conversations/{conv}/handoff"
    other_case = open_case(client, buyer, o).json()["id"]
    first = client.post(url, headers=buyer, json={"urgency": "high", "case_id": other_case})
    assert first.status_code == 201 and first.json()["case_id"] == other_case
    assert client.post(url, headers=buyer, json={}).json()["id"] == first.json()["id"]  # one active handoff
    assert client.post(url, headers=login(client, "lakshmi.admin@example.test"), json={}).status_code == 404

    retailer = login(client, "kiran.retail@example.test")
    rconv = client.post(f"/api/v1/orgs/{RETAILER}/conversations", headers=retailer).json()["id"]
    r = client.post(f"/api/v1/orgs/{RETAILER}/conversations/{rconv}/handoff", headers=retailer, json={"case_id": other_case})
    assert r.status_code == 404  # cannot attach another organization's case


def test_confirm_and_handoff_race_is_consistent(client):
    buyer, seller, say, action = pending_order(client)
    confirmed, handed = race(
        lambda c: press_confirm(c, buyer, action),
        lambda c: c.post(f"/api/v1/orgs/{DISTRIBUTOR}/conversations/{action_conv(action)}/handoff", headers=buyer, json={}),
    )
    assert handed.status_code == 201 and confirmed.status_code in (200, 409), confirmed.text
    orders = client.get(f"/api/v1/orgs/{DISTRIBUTOR}/orders", headers=buyer).json()
    if confirmed.status_code == 200:
        assert len(orders) == 1  # confirmed first; the handoff found nothing left to cancel
    else:
        assert orders == [] and code(confirmed) in ("conversation_paused", "pending_action_not_active")


def action_conv(action):
    from app.db import SessionLocal
    from app.models import PendingAction
    with SessionLocal() as db:
        return db.get(PendingAction, action["id"]).conversation_id


def test_owner_reloads_conversation_status_and_pending_proposal(client):
    # F01d: after signing in again the owner can find the conversation, its live proposal and the paused state.
    buyer, seller, say, pending = pending_order(client)
    base = f"/api/v1/orgs/{DISTRIBUTOR}/conversations"
    conv = client.get(base, headers=buyer).json()[0]
    assert set(conv) == {"id", "language", "created_at", "support_case_id", "support_status"}  # no message content
    detail = client.get(f"{base}/{conv['id']}", headers=buyer).json()
    assert detail["handoff"] is None and detail["pending_action"] == pending

    colleague = login(client, "lakshmi.admin@example.test")
    assert conv["id"] not in [c["id"] for c in client.get(base, headers=colleague).json()]
    assert client.get(f"{base}/{conv['id']}", headers=colleague).status_code == 404
    assert client.get(f"/api/v1/orgs/{RETAILER}/conversations/{conv['id']}", headers=login(client, "kiran.retail@example.test")).status_code == 404

    with SessionLocal() as db:  # an expired proposal is not offered, even before anyone presses confirm
        db.execute(update(PendingAction).where(PendingAction.id == pending["id"]).values(expires_at=func.now()))
        db.commit()
    assert client.get(f"{base}/{conv['id']}", headers=buyer).json()["pending_action"] is None

    fresh = say("order")
    assert fresh["pending_action"] is None
    proposal = say("1")["pending_action"]
    assert client.get(f"{base}/{conv['id']}", headers=buyer).json()["pending_action"]["id"] == proposal["id"]
    say("help")  # a newer message withdraws it
    assert client.get(f"{base}/{conv['id']}", headers=buyer).json()["pending_action"] is None

    say("order")
    say("1")
    handoff = client.post(f"{base}/{conv['id']}/handoff", headers=buyer, json={}).json()
    paused = client.get(f"{base}/{conv['id']}", headers=buyer).json()
    assert paused["handoff"]["id"] == handoff["id"] and paused["handoff"]["status"] == "queued"
    assert paused["pending_action"] is None  # requesting a person withdrew the proposal
    sanjay = staff(client, "sanjay.support@example.test")
    client.post(f"/api/v1/staff/handoffs/{handoff['id']}/take", headers=sanjay)
    assert client.get(f"{base}/{conv['id']}", headers=buyer).json()["handoff"]["status"] == "assigned"
    client.post(f"/api/v1/staff/handoffs/{handoff['id']}/release", headers=sanjay)
    assert client.get(f"{base}/{conv['id']}", headers=buyer).json()["handoff"] is None


def test_conversation_list_keeps_the_complaint_and_support_status_after_hand_back(client):
    # F06: a complaint can lead the buyer back to its support chat while support handles it and after hand-back.
    buyer, _, o = order(client)
    case = open_case(client, buyer, o).json()
    base = f"/api/v1/orgs/{DISTRIBUTOR}/conversations"
    conv = client.post(base, headers=buyer).json()["id"]
    plain = client.post(base, headers=buyer).json()["id"]
    handoff = client.post(f"{base}/{conv}/handoff", headers=buyer, json={"case_id": case["id"]}).json()
    rows = {c["id"]: c for c in client.get(base, headers=buyer).json()}
    assert (rows[conv]["support_case_id"], rows[conv]["support_status"]) == (case["id"], "queued")
    assert (rows[plain]["support_case_id"], rows[plain]["support_status"]) == (None, None)
    support = staff(client, "sanjay.support@example.test")
    assert client.post(f"/api/v1/staff/handoffs/{handoff['id']}/take", headers=support).status_code == 200
    assert client.post(f"/api/v1/staff/handoffs/{handoff['id']}/release", headers=support).status_code == 200
    after = {c["id"]: c for c in client.get(base, headers=buyer).json()}
    assert (after[conv]["support_case_id"], after[conv]["support_status"]) == (case["id"], "released")


def test_waiting_chat_is_marked_for_its_complaint_handler_and_anyone_can_take_it(client):
    # F06 (owner's choice): a chat about a held complaint waits in the shared queue, marked only for its handler.
    buyer, _, o = order(client)
    held = open_case(client, buyer, o).json()
    sanjay, vani = staff(client, "sanjay.support@example.test"), staff(client, "vani.support@example.test")
    client.post(f"/api/v1/staff/cases/{held['id']}/take", headers=sanjay)
    base = f"/api/v1/orgs/{DISTRIBUTOR}/conversations"
    handoff = client.post(f"{base}/{client.post(base, headers=buyer).json()['id']}/handoff", headers=buyer, json={"case_id": held["id"]}).json()
    assert handoff["status"] == "queued"  # not routed to one person, so it cannot get stuck if they are away

    def item(h):
        return next(x for x in client.get("/api/v1/staff/handoffs?scope=unassigned", headers=h).json() if x["id"] == handoff["id"])
    assert item(sanjay)["your_case_id"] == held["id"]
    assert item(vani)["your_case_id"] is None  # others do not learn which complaint it is about
    assert client.post(f"/api/v1/staff/handoffs/{handoff['id']}/take", headers=vani).status_code == 200  # anyone can still take it
