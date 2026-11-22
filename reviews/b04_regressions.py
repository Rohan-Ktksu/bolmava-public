"""Independent B04 review checks. Run from backend with the guarded disposable PostgreSQL test setup.

    python -m pytest ../reviews/b04_regressions.py -q --tb=short

These assert required behavior and intentionally fail on reviewed head 7a5210d.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.db import SessionLocal
from app.models import Message, PaymentRequest, StaffGrant
from app.seed import _id
from tests.conftest import login
from tests.test_payments import approve, order, payments, record, request
from tests.test_trade import DISTRIBUTOR

pytest_plugins = ["tests.conftest"]


def test_reversal_requires_a_distinct_authorized_approval(client):
    buyer, _, o = order(client)
    finance = login(client, "farah.finance@example.test")
    req = request(client, buyer, o).json()
    assert approve(client, finance, req).status_code == 200
    receipt = record(client, finance, req).json()
    with SessionLocal() as db:
        db.add(StaffGrant(user_id=_id("user:suresh.buyer@example.test"), role="finance"))
        db.commit()
    response = client.post(f"/api/v1/staff/payment-events/{receipt['id']}/reverse", headers=buyer,
                           json={"reason": "Requester changes their own recorded payment"})
    balance = payments(client, buyer, o)
    assert balance["received_paise"] == receipt["amount_paise"], (
        f"Unapproved reversal changed the ledger: HTTP {response.status_code}, received={balance['received_paise']}"
    )


def test_expired_approval_does_not_block_a_replacement_request(client):
    buyer, _, o = order(client)
    req = request(client, buyer, o).json()
    assert approve(client, login(client, "farah.finance@example.test"), req).status_code == 200
    with SessionLocal() as db:
        db.execute(update(PaymentRequest).where(PaymentRequest.id == req["id"]).values(
            approval_expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        db.commit()
    assert payments(client, buyer, o)["requests"][0]["status"] == "expired"
    replacement = request(client, buyer, o)
    assert replacement.status_code == 201 and replacement.json()["id"] != req["id"], replacement.text


def test_released_agent_cannot_read_a_later_agents_live_messages(client):
    buyer = login(client, "suresh.buyer@example.test")
    sanjay = login(client, "sanjay.support@example.test")
    vani = login(client, "vani.support@example.test")
    base = f"/api/v1/orgs/{DISTRIBUTOR}/conversations"
    conv = client.post(base, headers=buyer).json()["id"]
    first = client.post(f"{base}/{conv}/handoff", headers=buyer, json={}).json()["id"]
    assert client.post(f"/api/v1/staff/handoffs/{first}/take", headers=sanjay).status_code == 200
    assert client.post(f"/api/v1/staff/handoffs/{first}/release", headers=sanjay).status_code == 200
    second = client.post(f"{base}/{conv}/handoff", headers=buyer, json={}).json()["id"]
    assert client.post(f"/api/v1/staff/handoffs/{second}/take", headers=vani).status_code == 200
    private = "Private message for the newly assigned agent"
    assert client.post(f"{base}/{conv}/messages", headers=buyer, json={"text": private}).status_code == 200
    old_view = client.get(f"/api/v1/staff/handoffs/{first}", headers=sanjay)
    assert old_view.status_code in (403, 404) or private not in old_view.text, old_view.text


def test_owner_can_retrieve_agent_messages_after_500_messages(client):
    buyer = login(client, "suresh.buyer@example.test")
    base = f"/api/v1/orgs/{DISTRIBUTOR}/conversations"
    conv = client.post(base, headers=buyer).json()["id"]
    with SessionLocal() as db:
        db.add_all(Message(conversation_id=conv, role="user", text=f"Earlier message {i}") for i in range(500))
        db.commit()
    handoff = client.post(f"{base}/{conv}/handoff", headers=buyer, json={}).json()["id"]
    support = login(client, "sanjay.support@example.test")
    assert client.post(f"/api/v1/staff/handoffs/{handoff}/take", headers=support).status_code == 200
    message = "Your assigned support person's latest reply"
    assert client.post(f"/api/v1/staff/handoffs/{handoff}/messages", headers=support,
                       json={"text": message}).status_code == 201
    history = client.get(f"{base}/{conv}/messages", headers=buyer)
    assert history.status_code == 200
    assert any(m["text"] == message for m in history.json()), "Newest agent reply is inaccessible; no history cursor exists"
