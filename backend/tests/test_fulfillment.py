from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import StockMovement
from tests.conftest import login
from tests.test_payments import ADVANCE, approve, code, order, payments, record, request
from tests.test_trade import DISTRIBUTOR, RETAILER, SELLER, race, stock


def act(client, h, o, action, org):
    return client.post(f"/api/v1/orgs/{org}/orders/{o['id']}/fulfillment", headers=h, json={"action": action})


def cancel(client, h, o, org=DISTRIBUTOR):
    return client.post(f"/api/v1/orgs/{org}/orders/{o['id']}/cancel", headers=h, json={"reason": "Changed plan"})


def cancel_movements(o):
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.order_id == o["id"], StockMovement.reason == "order_cancel"))


def test_dispatch_deliver_accept(client):
    buyer, seller, o = order(client)
    assert o["fulfillment_status"] == "pending"
    assert act(client, buyer, o, "dispatch", DISTRIBUTOR).status_code == 403  # buyer cannot dispatch
    assert code(act(client, buyer, o, "accept", DISTRIBUTOR)) == "invalid_transition"  # not delivered yet
    r = act(client, seller, o, "dispatch", SELLER)
    assert r.status_code == 200 and r.json()["fulfillment_status"] == "dispatched"
    assert act(client, seller, o, "dispatch", SELLER).status_code == 200  # repeat is harmless
    assert code(cancel(client, buyer, o)) == "invalid_transition"  # too late to cancel
    assert act(client, seller, o, "accept", SELLER).status_code == 403  # seller cannot accept for the buyer
    assert act(client, buyer, o, "deliver", DISTRIBUTOR).json()["fulfillment_status"] == "delivered"
    done = act(client, buyer, o, "accept", DISTRIBUTOR).json()
    assert (done["fulfillment_status"], done["status"]) == ("accepted", "completed")
    assert code(act(client, seller, o, "dispatch", SELLER)) == "invalid_transition"
    events = client.get(f"/api/v1/orgs/{SELLER}/orders/{o['id']}/fulfillment-events", headers=seller).json()
    assert [e["status"] for e in events] == ["dispatched", "delivered", "accepted"]
    assert payments(client, buyer, o)["received_paise"] == 0  # delivery never records money


def test_wrong_parties_refused(client):
    buyer, seller, o = order(client)
    viewer = login(client, "meena.viewer@example.test")
    assert act(client, viewer, o, "deliver", DISTRIBUTOR).status_code == 403
    assert cancel(client, viewer, o).status_code == 403
    assert cancel(client, seller, o, org=SELLER).status_code == 403  # catalog manager may not cancel
    outsider = login(client, "kiran.retail@example.test")
    assert act(client, outsider, o, "deliver", RETAILER).status_code == 404
    assert cancel(client, outsider, o, org=RETAILER).status_code == 404
    assert client.get(f"/api/v1/orgs/{RETAILER}/orders/{o['id']}/fulfillment-events", headers=outsider).status_code == 404


def test_cancel_restores_stock_once_and_keeps_receipts(client):
    buyer, seller, o = order(client)
    finance = login(client, "farah.finance@example.test")
    req = request(client, buyer, o).json()
    approve(client, finance, req)
    record(client, finance, req)
    open_req = request(client, buyer, o, amount=1000, purpose="balance").json()
    assert stock(client, seller) == 490

    seller_admin = login(client, "ravi.seller@example.test")
    r = cancel(client, seller_admin, o, org=SELLER)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert cancel(client, buyer, o).status_code == 200  # repeat: no second restore
    assert stock(client, seller) == 500 and cancel_movements(o) == 1

    v = payments(client, buyer, o)
    assert (v["received_paise"], v["outstanding_paise"], v["refund_due_paise"]) == (ADVANCE, 0, ADVANCE)
    assert {x["id"]: x["status"] for x in v["requests"]}[open_req["id"]] == "cancelled"
    assert code(act(client, seller, o, "dispatch", SELLER)) == "invalid_transition"
    assert code(request(client, buyer, o, amount=1)) == "invalid_transition"


def test_concurrent_cancellations_restore_stock_once(client):
    buyer, seller, o = order(client)
    admin = login(client, "lakshmi.admin@example.test")
    results = race(lambda c: cancel(c, buyer, o), lambda c: cancel(c, admin, o))
    assert [r.status_code for r in results] == [200, 200]
    assert stock(client, seller) == 500 and cancel_movements(o) == 1


def test_cancel_and_dispatch_race_has_one_outcome(client):
    buyer, seller, o = order(client)
    cancelled, dispatched = race(lambda c: cancel(c, buyer, o), lambda c: act(c, seller, o, "dispatch", SELLER))
    statuses = sorted([cancelled.status_code, dispatched.status_code])
    assert statuses == [200, 409], (cancelled.text, dispatched.text)
    if cancelled.status_code == 200:
        assert stock(client, seller) == 500 and cancel_movements(o) == 1
    else:
        assert stock(client, seller) == 490 and cancel_movements(o) == 0
