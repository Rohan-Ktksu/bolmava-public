"""Independent review regressions; run separately against the disposable review database."""
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest

pytest_plugins = ["tests.conftest"]


def test_order_keeps_product_terms_shown_at_confirmation(client):
    from tests.conftest import login
    from tests.test_conversation import chat, press_confirm
    from tests.test_trade import DISTRIBUTOR, SELLER, SWITCH, quote, rfq, setup

    buyer, seller = setup(client)
    quote(client, seller, rfq(client, buyer)["id"])
    say = chat(client, buyer)
    say("order")
    readback = say("1")
    assert "10" in readback["reply"] and ("boxes" in readback["reply"] or "బాక్సులు" in readback["reply"])
    before = client.get(f"/api/v1/orgs/{SELLER}/products/{SWITCH}", headers=seller).json()
    changed = client.patch(
        f"/api/v1/orgs/{SELLER}/products/{SWITCH}", headers=seller,
        json={"version": before["version"], "unit": "piece", "pack_size": 1, "rating_amps": 16},
    )
    assert changed.status_code == 200
    result = press_confirm(client, buyer, readback["pending_action"])
    # A safe implementation either refuses the changed terms or preserves the exact shown agreement.
    if result.status_code == 200:
        snapshot = result.json()["order"]["product_snapshot"]
        assert (snapshot["unit"], snapshot["pack_size"], snapshot["rating_amps"]) == ("box", 10, 6), result.text
    else:
        assert result.status_code in (400, 409)


def test_quote_must_still_be_unexpired_after_waiting_for_its_lock(client, monkeypatch):
    from sqlalchemy import select
    from app import trade
    from app.db import SessionLocal
    from app.models import Quote
    from tests.test_trade import confirm, quote, rfq, setup
    from fastapi.testclient import TestClient
    from app.main import app

    buyer, seller = setup(client)
    deadline = datetime.now(UTC) + timedelta(seconds=3)
    q = quote(client, seller, rfq(client, buyer)["id"], valid_until=deadline.isoformat())
    started = threading.Event()
    original_lock = trade.lock_idempotency_key

    def lock_then_signal(*args):
        original_lock(*args)
        started.set()

    monkeypatch.setattr(trade, "lock_idempotency_key", lock_then_signal)
    results = []
    def worker():
        with TestClient(app, raise_server_exceptions=False) as other:
            results.append(confirm(other, buyer, q, key="expiry-lock"))

    with SessionLocal() as blocker:
        blocker.scalar(select(Quote).where(Quote.id == q["id"]).with_for_update())
        thread = threading.Thread(target=worker)
        thread.start()
        assert started.wait(5)
        time.sleep(max(0, (deadline - datetime.now(UTC)).total_seconds()) + 0.3)
        blocker.rollback()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert results[0].status_code == 409, f"Confirmed after deadline: {results[0].status_code} {results[0].text}"
    assert results[0].json()["error"]["details"]["reason"] == "expired"


def test_revised_quote_and_confirmation_do_not_deadlock(client, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import event
    from app import trade
    from app.db import engine
    from app.main import app
    from tests.test_trade import SELLER, confirm, quote, rfq, setup

    buyer, seller = setup(client)
    request = rfq(client, buyer)
    sent = quote(client, seller, request["id"])
    draft = quote(client, seller, request["id"], send=False, unit_price_paise=44000)
    rfq_locked, quote_locked = threading.Event(), threading.Event()
    original_rfq = trade._rfq

    def rfq_then_wait(*args, **kwargs):
        row = original_rfq(*args, **kwargs)
        if kwargs.get("as_seller") and kwargs.get("lock"):
            rfq_locked.set()
            # The old code can take the opposite quote lock here. A consistent lock
            # order correctly blocks it, so release this gate after a bounded wait.
            quote_locked.wait(timeout=2)
        return row

    def detect_quote_lock(conn, cursor, statement, parameters, context, many):
        if "FOR UPDATE OF quotes" in statement:
            quote_locked.set()

    monkeypatch.setattr(trade, "_rfq", rfq_then_wait)
    results = {}
    def send_new():
        with TestClient(app, raise_server_exceptions=False) as other:
            results["send"] = other.post(f"/api/v1/orgs/{SELLER}/quotes/{draft['id']}/send", headers=seller)
    def buy_old():
        assert rfq_locked.wait(5)
        with TestClient(app, raise_server_exceptions=False) as other:
            results["confirm"] = confirm(other, buyer, sent, key="send-race")

    event.listen(engine, "after_cursor_execute", detect_quote_lock)
    try:
        threads = [threading.Thread(target=send_new), threading.Thread(target=buy_old)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        assert not any(thread.is_alive() for thread in threads)
    finally:
        event.remove(engine, "after_cursor_execute", detect_quote_lock)
    assert set(results) == {"send", "confirm"}
    statuses = {key: value.status_code for key, value in results.items()}
    assert all(status < 500 for status in statuses.values()), f"Lock-order race produced server error: {statuses}"
