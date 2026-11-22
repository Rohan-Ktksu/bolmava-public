from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.db import SessionLocal
from app.models import AuditEvent, PaymentEvent, PaymentRequest, PaymentReversal, StaffGrant
from app.seed import _id
from tests.conftest import login
from tests.test_trade import DISTRIBUTOR, RETAILER, SELLER, confirm, quote, race, rfq, setup

TOTAL, ADVANCE = 535720, 100000


def order(client):
    buyer, seller = setup(client)
    o = confirm(client, buyer, quote(client, seller, rfq(client, buyer)["id"]))
    assert o.status_code == 201, o.text
    return buyer, seller, o.json()


def request(client, h, o, amount=ADVANCE, purpose="advance", org=DISTRIBUTOR, version=1):
    return client.post(f"/api/v1/orgs/{org}/orders/{o['id']}/payment-requests", headers=h,
                       json={"purpose": purpose, "amount_paise": amount, "quote_version": version})


def approve(client, h, req, **override):
    body = {"order_id": req["order_id"], "purpose": req["purpose"], "amount_paise": req["amount_paise"],
            "quote_version": req["quote_version"]} | override
    return client.post(f"/api/v1/staff/payment-requests/{req['id']}/approve", headers=h, json=body)


def record(client, h, req):
    return client.post(f"/api/v1/staff/payment-requests/{req['id']}/record", headers=h)


def payments(client, h, o, org=DISTRIBUTOR):
    return client.get(f"/api/v1/orgs/{org}/orders/{o['id']}/payments", headers=h).json()


def code(r):
    return r.json()["error"]["code"]


def counts():
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(PaymentEvent)), db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action.like("payment.%")))


def test_advance_requested_approved_recorded_once(client):
    buyer, seller, o = order(client)
    finance = login(client, "farah.finance@example.test")
    assert client.get("/api/v1/me", headers=finance).json()["staff_roles"] == ["finance"]

    req = request(client, buyer, o)
    assert req.status_code == 201, req.text
    req = req.json()
    assert (req["status"], req["simulated"]) == ("pending_approval", True)
    assert request(client, buyer, o).status_code == 200  # retry returns the same open request
    assert payments(client, buyer, o)["received_paise"] == 0

    approved = approve(client, finance, req, note="Advance per quote v1")
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert payments(client, buyer, o)["received_paise"] == 0  # approval is not a receipt

    receipt = record(client, finance, req)
    assert receipt.status_code == 201 and receipt.json()["amount_paise"] == ADVANCE
    again = record(client, finance, req)
    assert again.status_code == 200 and again.json()["id"] == receipt.json()["id"]

    for h, org in ((buyer, DISTRIBUTOR), (seller, SELLER)):
        v = payments(client, h, o, org)
        assert (v["received_paise"], v["outstanding_paise"], v["refund_due_paise"]) == (ADVANCE, TOTAL - ADVANCE, 0)
        assert [r["status"] for r in v["requests"]] == ["recorded"]
    assert counts() == (1, 6)  # requested, approved, recorded × buyer and seller audit


def test_maker_checker_and_permissions(client):
    buyer, seller, o = order(client)
    req = request(client, buyer, o).json()
    with SessionLocal() as db:  # the requester also holds a finance grant: still may not decide
        db.add(StaffGrant(user_id=_id("user:suresh.buyer@example.test"), role="finance"))
        db.commit()
    r = approve(client, buyer, req)
    assert r.status_code == 403 and code(r) == "self_approval"
    r = client.post(f"/api/v1/staff/payment-requests/{req['id']}/reject", headers=buyer, json={"note": "x"})
    assert code(r) == "self_approval"

    for email in ("lakshmi.admin@example.test", "sanjay.support@example.test", "ravi.seller@example.test"):
        h = login(client, email)
        assert approve(client, h, req).status_code == 403, email
        assert client.get(f"/api/v1/staff/orders/{o['id']}/payments", headers=h).status_code == 403, email
    outsider = login(client, "kiran.retail@example.test")
    assert client.get(f"/api/v1/orgs/{RETAILER}/orders/{o['id']}/payments", headers=outsider).status_code == 404
    assert request(client, outsider, o, org=RETAILER).status_code == 404
    assert request(client, login(client, "meena.viewer@example.test"), o).status_code == 403
    assert request(client, seller, o, org=SELLER).status_code == 403  # selling-only org cannot request
    assert counts() == (0, 2)


def test_tampered_approval_and_rejection(client):
    buyer, _, o = order(client)
    finance = login(client, "farah.finance@example.test")
    req = request(client, buyer, o).json()
    for override in ({"amount_paise": ADVANCE + 1}, {"purpose": "balance"}, {"quote_version": 2}, {"order_id": str(_id("x"))}):
        r = approve(client, finance, req, **override)
        assert r.status_code == 409 and code(r) == "terms_mismatch", override
    rejected = client.post(f"/api/v1/staff/payment-requests/{req['id']}/reject", headers=finance, json={"note": "Wrong amount"})
    assert rejected.json()["status"] == "rejected"
    assert code(approve(client, finance, req)) == "invalid_transition"
    assert code(record(client, finance, req)) == "invalid_transition"
    assert request(client, buyer, o).status_code == 201  # a rejected request no longer blocks a new one
    assert counts()[0] == 0


def test_expired_approval_cannot_be_recorded(client):
    buyer, _, o = order(client)
    finance = login(client, "farah.finance@example.test")
    req = request(client, buyer, o).json()
    approve(client, finance, req)
    with SessionLocal() as db:
        db.execute(update(PaymentRequest).where(PaymentRequest.id == req["id"]).values(approval_expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        db.commit()
    r = record(client, finance, req)
    assert r.status_code == 409 and code(r) == "approval_expired"
    assert payments(client, buyer, o)["requests"][0]["status"] == "expired"
    assert counts()[0] == 0


def test_amount_limits(client):
    buyer, _, o = order(client)
    r = request(client, buyer, o, amount=ADVANCE + 1)
    assert code(r) == "exceeds_outstanding" and r.json()["error"]["details"] == {"advance_remaining_paise": ADVANCE}
    assert code(request(client, buyer, o, amount=TOTAL + 1, purpose="balance")) == "exceeds_outstanding"
    assert code(request(client, buyer, o, version=2)) == "terms_mismatch"
    first = request(client, buyer, o, amount=50000).json()
    r = request(client, buyer, o, amount=60000)
    assert code(r) == "open_request_exists" and r.json()["error"]["details"]["request_id"] == first["id"]


def test_concurrent_recording_creates_one_receipt(client):
    buyer, _, o = order(client)
    finance = login(client, "farah.finance@example.test")
    req = request(client, buyer, o).json()
    approve(client, finance, req)
    results = race(lambda c: record(c, finance, req), lambda c: record(c, finance, req))
    assert sorted(r.status_code for r in results) == [200, 201]
    assert results[0].json()["id"] == results[1].json()["id"]
    assert payments(client, buyer, o)["received_paise"] == ADVANCE
    assert counts()[0] == 1


REASON = "Entered against the wrong order"


def recorded_receipt(client, amount=TOTAL, purpose="balance"):
    buyer, _, o = order(client)
    finance = login(client, "farah.finance@example.test")
    req = request(client, buyer, o, amount=amount, purpose=purpose).json()
    approve(client, finance, req)
    return buyer, o, record(client, finance, req).json()


def ask_reversal(client, h, receipt, reason=REASON):
    return client.post(f"/api/v1/staff/payment-events/{receipt['id']}/reverse", headers=h, json={"reason": reason})


def approve_reversal(client, h, rev, **override):
    body = {"order_id": rev["order_id"], "receipt_event_id": rev["receipt_event_id"], "amount_paise": rev["amount_paise"],
            "reason": rev["reason"]} | override
    return client.post(f"/api/v1/staff/payment-reversals/{rev['id']}/approve", headers=h, json=body)


def expire_reversal(rev):
    with SessionLocal() as db:
        db.execute(update(PaymentReversal).where(PaymentReversal.id == rev["id"]).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        db.commit()


def test_reversal_needs_a_distinct_approver_and_restores_balance(client):
    buyer, o, receipt = recorded_receipt(client)
    farah, arjun = login(client, "farah.finance@example.test"), login(client, "arjun.finance@example.test")
    assert payments(client, buyer, o)["outstanding_paise"] == 0
    assert code(request(client, buyer, o, amount=1, purpose="balance")) == "exceeds_outstanding"
    assert ask_reversal(client, buyer, receipt).status_code == 403  # not finance

    # Farah approved and recorded the receipt and now asks for its reversal: nothing moves yet.
    rev = ask_reversal(client, farah, receipt)
    assert rev.status_code == 201, rev.text
    rev = rev.json()
    assert (rev["status"], rev["amount_paise"], rev["receipt_event_id"], rev["reversal_event_id"]) == ("pending_approval", TOTAL, receipt["id"], None)
    assert payments(client, buyer, o)["received_paise"] == TOTAL and counts()[0] == 1
    assert ask_reversal(client, farah, receipt).json()["id"] == rev["id"]  # retry
    r = ask_reversal(client, arjun, receipt, reason="Another reason")
    assert code(r) == "open_request_exists" and r.json()["error"]["details"]["request_id"] == rev["id"]

    r = approve_reversal(client, farah, rev)
    assert r.status_code == 403 and code(r) == "self_approval"
    for override in ({"amount_paise": TOTAL - 1}, {"reason": "different"}, {"order_id": str(_id("x"))}, {"receipt_event_id": str(_id("y"))}):
        r = approve_reversal(client, arjun, rev, **override)
        assert r.status_code == 409 and code(r) == "terms_mismatch", override
    assert payments(client, buyer, o)["received_paise"] == TOTAL and counts()[0] == 1

    done = approve_reversal(client, arjun, rev, note="Checked the bank statement (simulated)")
    assert done.status_code == 200 and done.json()["status"] == "executed", done.text
    assert approve_reversal(client, arjun, rev).json()["reversal_event_id"] == done.json()["reversal_event_id"]  # replay
    v = payments(client, buyer, o)
    assert (v["received_paise"], v["outstanding_paise"], [e["kind"] for e in v["events"]]) == (0, TOTAL, ["receipt", "reversal"])
    reversal = v["events"][1]
    assert (reversal["id"], reversal["reverses_event_id"], reversal["recorded_by"], reversal["reason"]) == (
        done.json()["reversal_event_id"], receipt["id"], str(_id("user:arjun.finance@example.test")), REASON)

    r = ask_reversal(client, farah, receipt)
    assert code(r) == "invalid_transition" and r.json()["error"]["details"]["status"] == "reversed"
    assert code(ask_reversal(client, farah, reversal)) == "invalid_transition"  # a reversal cannot be reversed
    with SessionLocal() as db:
        actions = db.scalars(select(AuditEvent.action).where(AuditEvent.action.like("payment.revers%"))).all()
    assert sorted(actions) == ["payment.reversal_requested"] * 2 + ["payment.reversed"] * 2  # buyer and seller org each


def test_reversal_rejection_expiry_and_queue(client):
    buyer, o, receipt = recorded_receipt(client)
    farah, arjun = login(client, "farah.finance@example.test"), login(client, "arjun.finance@example.test")
    rev = ask_reversal(client, farah, receipt).json()
    assert [r["id"] for r in client.get("/api/v1/staff/payment-reversals", headers=arjun).json()] == [rev["id"]]
    assert client.get("/api/v1/staff/payment-reversals", headers=buyer).status_code == 403
    assert client.get("/api/v1/staff/payment-reversals", headers=login(client, "sanjay.support@example.test")).status_code == 403

    r = client.post(f"/api/v1/staff/payment-reversals/{rev['id']}/reject", headers=farah, json={"note": "x"})
    assert code(r) == "self_approval"
    r = client.post(f"/api/v1/staff/payment-reversals/{rev['id']}/reject", headers=arjun, json={"note": "Receipt is correct"})
    assert r.json()["status"] == "rejected"
    assert code(approve_reversal(client, arjun, rev)) == "invalid_transition"

    # A new request may follow a rejection; one that lapses cannot be approved and frees the slot.
    second = ask_reversal(client, arjun, receipt).json()
    assert second["id"] != rev["id"]
    expire_reversal(second)
    assert client.get("/api/v1/staff/payment-reversals", headers=farah).json() == []
    assert [r["id"] for r in client.get("/api/v1/staff/payment-reversals?status=expired", headers=farah).json()] == [second["id"]]
    r = approve_reversal(client, farah, second)
    assert r.status_code == 409 and code(r) == "approval_expired"
    with SessionLocal() as db:
        assert db.get(PaymentReversal, second["id"]).status == "expired"  # saved, not only reported
    third = ask_reversal(client, arjun, receipt)
    assert third.status_code == 201 and third.json()["id"] not in (rev["id"], second["id"])
    assert payments(client, buyer, o)["received_paise"] == TOTAL and counts()[0] == 1


def test_concurrent_reversal_requests_and_approvals_reverse_once(client):
    buyer, o, receipt = recorded_receipt(client)
    farah, arjun = login(client, "farah.finance@example.test"), login(client, "arjun.finance@example.test")
    asked = race(lambda c: ask_reversal(c, farah, receipt), lambda c: ask_reversal(c, arjun, receipt, reason="Duplicate entry"))
    assert sorted(r.status_code for r in asked) == [201, 409]
    rev = next(r.json() for r in asked if r.status_code == 201)
    approver = arjun if rev["requested_by"] == str(_id("user:farah.finance@example.test")) else farah
    results = race(lambda c: approve_reversal(c, approver, rev), lambda c: approve_reversal(c, approver, rev))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json()["reversal_event_id"] == results[1].json()["reversal_event_id"]
    assert payments(client, buyer, o)["received_paise"] == 0 and counts()[0] == 2


def test_expired_approval_frees_the_slot_for_a_replacement(client):
    buyer, _, o = order(client)
    finance = login(client, "farah.finance@example.test")
    req = request(client, buyer, o).json()
    approve(client, finance, req)
    with SessionLocal() as db:
        db.execute(update(PaymentRequest).where(PaymentRequest.id == req["id"]).values(approval_expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        db.commit()
    assert client.get("/api/v1/staff/payment-requests?status=approved", headers=finance).json() == []
    assert [r["id"] for r in client.get("/api/v1/staff/payment-requests?status=expired", headers=finance).json()] == [req["id"]]

    # Two concurrent replacements: one new open request, the other is its retry (same terms) or a conflict.
    same = race(lambda c: request(c, buyer, o, amount=80000), lambda c: request(c, buyer, o, amount=80000))
    assert sorted(r.status_code for r in same) == [200, 201] and same[0].json()["id"] == same[1].json()["id"] != req["id"]
    with SessionLocal() as db:
        old = db.get(PaymentRequest, req["id"])
        assert (old.status, old.decided_by) == ("expired", _id("user:farah.finance@example.test"))  # history kept
    assert code(record(client, finance, req)) == "invalid_transition"
    assert code(request(client, buyer, o, amount=70000)) == "open_request_exists"
    assert counts()[0] == 0


def test_concurrent_different_replacements_leave_one_open_request(client):
    buyer, _, o = order(client)
    req = request(client, buyer, o).json()
    approve(client, login(client, "farah.finance@example.test"), req)
    with SessionLocal() as db:
        db.execute(update(PaymentRequest).where(PaymentRequest.id == req["id"]).values(approval_expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        db.commit()
    results = race(lambda c: request(c, buyer, o, amount=80000), lambda c: request(c, buyer, o, amount=90000))
    assert sorted(r.status_code for r in results) == [201, 409]
    with SessionLocal() as db:
        statuses = sorted(db.scalars(select(PaymentRequest.status).where(PaymentRequest.order_id == o["id"])).all())
    assert statuses == ["expired", "pending_approval"] and counts()[0] == 0


def test_finance_queue_lists_pending(client):
    buyer, _, o = order(client)
    req = request(client, buyer, o).json()
    queue = client.get("/api/v1/staff/payment-requests", headers=login(client, "farah.finance@example.test")).json()
    assert [r["id"] for r in queue] == [req["id"]]
    assert client.get("/api/v1/staff/payment-requests", headers=buyer).status_code == 403
