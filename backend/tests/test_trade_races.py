"""R02 regressions: agreed product terms, expiry after lock waits, and RFQ-then-quote lock order."""
import threading
import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app import trade
from app.db import SessionLocal
from app.main import app
from app.models import PendingAction, Quote, Rfq
from tests.test_conversation import chat, press_confirm
from tests.test_trade import DISTRIBUTOR, SELLER, SWITCH, confirm, quote, race, reason, rfq, setup, stock

PRODUCT = f"/api/v1/orgs/{SELLER}/products/{SWITCH}"


def edit_product(client, seller, **changes):
    version = client.get(PRODUCT, headers=seller).json()["version"]
    r = client.patch(PRODUCT, headers=seller, json={"version": version} | changes)
    assert r.status_code == 200, r.text


def orders(client, buyer):
    return client.get(f"/api/v1/orgs/{DISTRIBUTOR}/orders", headers=buyer).json()


def test_assistant_order_refuses_terms_changed_after_readback(client):
    buyer, seller = setup(client)
    quote(client, seller, rfq(client, buyer)["id"])
    say = chat(client, buyer)
    say("order")
    readback = say("1")
    assert "6A one-way modular switch, box of 10 10 బాక్సులు" in readback["reply"]  # suresh reads Telugu
    edit_product(client, seller, unit="piece", pack_size=1, rating_amps=16)
    r = press_confirm(client, buyer, readback["pending_action"])
    assert reason(r) == "product_changed"
    assert orders(client, buyer) == [] and stock(client, seller) == 500


def test_order_uses_the_quoted_terms_and_ignores_non_material_edits(client):
    buyer, seller = setup(client)
    q = quote(client, seller, rfq(client, buyer)["id"])
    assert (q["product_snapshot"]["unit"], q["product_snapshot"]["pack_size"], q["product_snapshot"]["rating_amps"]) == ("box", 10, 6)
    edit_product(client, seller, price_paise=99999, delivery_cities=["Guntur"], lead_time_days=9)  # not part of the agreement
    r = confirm(client, buyer, q)
    assert r.status_code == 201, r.text
    assert r.json()["product_snapshot"] == q["product_snapshot"]
    assert r.json()["unit_price_paise"] == 45000


def test_material_change_blocks_send_and_confirm_until_requoted(client):
    buyer, seller = setup(client)
    request = rfq(client, buyer)["id"]
    sent = quote(client, seller, request)
    draft = quote(client, seller, request, send=False)
    edit_product(client, seller, name="6A one-way switch, new design")
    assert reason(confirm(client, buyer, sent)) == "product_changed"
    stale = client.post(f"/api/v1/orgs/{SELLER}/quotes/{draft['id']}/send", headers=seller)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "quote_not_sendable"
    fresh = quote(client, seller, request)
    assert fresh["product_snapshot"]["name"] == "6A one-way switch, new design"
    assert confirm(client, buyer, fresh, key="k2").status_code == 201


def hold_lock_past(deadline, lock_stmt, start_request):
    """Hold a row lock until after `deadline` while `start_request` runs in another thread; return its response."""
    started, results = threading.Event(), []
    original = trade.lock_idempotency_key

    def signal(*args):
        original(*args)
        started.set()

    trade.lock_idempotency_key = signal
    try:
        def worker():
            with TestClient(app, raise_server_exceptions=False) as c:
                results.append(start_request(c))

        with SessionLocal() as blocker:
            blocker.scalar(lock_stmt.with_for_update())
            thread = threading.Thread(target=worker)
            thread.start()
            assert started.wait(5)
            time.sleep(max(0, (deadline - datetime.now(UTC)).total_seconds()) + 0.3)
            blocker.rollback()
        thread.join(timeout=10)
        assert not thread.is_alive()
    finally:
        trade.lock_idempotency_key = original
    return results[0]


def test_quote_expiring_while_waiting_for_lock_is_refused(client):
    buyer, seller = setup(client)
    deadline = datetime.now(UTC) + timedelta(seconds=2)
    q = quote(client, seller, rfq(client, buyer)["id"], valid_until=deadline.isoformat())
    r = hold_lock_past(deadline, select(Quote).where(Quote.id == q["id"]), lambda c: confirm(c, buyer, q, key="late"))
    assert reason(r) == "expired"
    assert orders(client, buyer) == [] and stock(client, seller) == 500


def test_pending_action_expiring_while_waiting_for_lock_is_refused(client):
    buyer, seller = setup(client)
    q = quote(client, seller, rfq(client, buyer)["id"])
    say = chat(client, buyer)
    say("order")
    action = say("1")["pending_action"]
    deadline = datetime.now(UTC) + timedelta(seconds=2)
    with SessionLocal() as db:
        db.execute(update(PendingAction).where(PendingAction.id == action["id"]).values(expires_at=deadline))
        db.commit()
    r = hold_lock_past(deadline, select(Rfq).where(Rfq.id == q["rfq_id"]), lambda c: press_confirm(c, buyer, action))
    assert r.status_code == 409 and r.json()["error"]["details"] == {"status": "expired"}, r.text
    assert orders(client, buyer) == [] and stock(client, seller) == 500
    with SessionLocal() as db:
        assert db.get(PendingAction, action["id"]).status == "expired"


def test_sending_a_revision_while_old_version_is_confirmed_does_not_deadlock(client, monkeypatch):
    buyer, seller = setup(client)
    request = rfq(client, buyer)["id"]
    old = quote(client, seller, request)
    draft = quote(client, seller, request, send=False, unit_price_paise=44000)
    send_holds_rfq, confirm_waiting = threading.Event(), threading.Event()
    original_rfq, original_lock = trade._rfq, trade.lock_idempotency_key

    def rfq_then_wait(*args, **kwargs):
        row = original_rfq(*args, **kwargs)
        if kwargs.get("as_seller") and kwargs.get("lock"):  # send holds the RFQ lock while confirm starts
            send_holds_rfq.set()
            assert confirm_waiting.wait(5)
            time.sleep(0.3)
        return row

    def lock_then_signal(*args):
        original_lock(*args)
        confirm_waiting.set()

    monkeypatch.setattr(trade, "_rfq", rfq_then_wait)
    monkeypatch.setattr(trade, "lock_idempotency_key", lock_then_signal)
    results = {}

    def send_new():
        with TestClient(app, raise_server_exceptions=False) as c:
            results["send"] = c.post(f"/api/v1/orgs/{SELLER}/quotes/{draft['id']}/send", headers=seller)

    def buy_old():
        assert send_holds_rfq.wait(5)
        with TestClient(app, raise_server_exceptions=False) as c:
            results["confirm"] = confirm(c, buyer, old, key="send-race")

    threads = [threading.Thread(target=send_new), threading.Thread(target=buy_old)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    assert not any(t.is_alive() for t in threads)
    assert results["send"].status_code == 200, results["send"].text
    assert reason(results["confirm"]) == "superseded"
    assert orders(client, buyer) == [] and stock(client, seller) == 500


def test_reject_and_confirm_race_has_one_consistent_outcome(client):
    buyer, seller = setup(client)
    admin = TestClient(app)
    q = quote(client, seller, rfq(client, buyer)["id"])
    rejected, confirmed = race(
        lambda c: c.post(f"/api/v1/orgs/{DISTRIBUTOR}/quotes/{q['id']}/reject", headers=buyer),
        lambda c: confirm(c, buyer, q, key="reject-race"),
    )
    assert sorted([rejected.status_code, confirmed.status_code]) in ([200, 409], [201, 409]), (rejected.text, confirmed.text)
    final = admin.get(f"/api/v1/orgs/{DISTRIBUTOR}/quotes/{q['id']}", headers=buyer).json()["status"]
    if confirmed.status_code == 201:
        assert final == "accepted" and stock(client, seller) == 490 and len(orders(client, buyer)) == 1
    else:
        assert final == "rejected" and reason(confirmed) == "not_sent" and stock(client, seller) == 500
