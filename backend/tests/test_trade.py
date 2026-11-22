import threading
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.db import SessionLocal
from app.main import app
from app.models import Quote, StockMovement
from app.seed import _id
from tests.conftest import login

SELLER = _id("org:sri-lakshmi")
DISTRIBUTOR = _id("org:godavari")
RETAILER = _id("org:vizag-home")
SWITCH = _id("product:SL-6A-1W-10")  # moq 5, stock 500, ₹450 per box


def soon(hours=72):
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def rfq(client, buyer, org=DISTRIBUTOR, product=SWITCH, quantity=10):
    r = client.post(f"/api/v1/orgs/{org}/rfqs", headers=buyer | {"Idempotency-Key": str(uuid.uuid4())},
                    json={"product_id": str(product), "quantity": quantity, "delivery_city": "Guntur"})
    assert r.status_code == 201, r.text
    return r.json()


def quote(client, seller, rfq_id, send=True, **terms):
    body = {"unit_price_paise": 45000, "discount_paise": 1000, "freight_paise": 5000, "advance_paise": 100000,
            "valid_until": soon()} | terms
    r = client.post(f"/api/v1/orgs/{SELLER}/rfqs/{rfq_id}/quotes", headers=seller, json=body)
    assert r.status_code == 201, r.text
    if send:
        r = client.post(f"/api/v1/orgs/{SELLER}/quotes/{r.json()['id']}/send", headers=seller)
        assert r.status_code == 200, r.text
    return r.json()


def confirm(client, buyer, q, key="k1", org=DISTRIBUTOR, **override):
    body = {"quote_id": q["id"], "quote_version": q["version"], "total_paise": q["total_paise"]} | override
    return client.post(f"/api/v1/orgs/{org}/orders", headers=buyer | {"Idempotency-Key": key}, json=body)


def stock(client, seller, product=SWITCH):
    return client.get(f"/api/v1/orgs/{SELLER}/products/{product}", headers=seller).json()["available_qty"]


def reason(r):
    assert r.status_code == 409, r.text
    return r.json()["error"]["details"]["reason"]


def setup(client):
    return login(client, "suresh.buyer@example.test"), login(client, "anitha.catalog@example.test")


def test_trade_happens_exactly_once(client):
    buyer, seller = setup(client)
    q = quote(client, seller, rfq(client, buyer)["id"])
    # 10 × 450.00 − 10.00 discount = 4,490.00; + 50.00 freight; 18% simulated tax on 4,540.00 = 817.20
    assert (q["subtotal_paise"], q["tax_paise"], q["total_paise"], q["status"]) == (449000, 81720, 535720, "sent")

    first = confirm(client, buyer, q)
    assert first.status_code == 201, first.text
    order = first.json()
    assert (order["total_paise"], order["quantity"], order["simulated"]) == (535720, 10, True)
    assert order["product_snapshot"]["sku"] == "SL-6A-1W-10"
    replay = confirm(client, buyer, q)
    assert replay.status_code == 200 and replay.json()["id"] == order["id"]
    assert stock(client, seller) == 490

    assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/quotes/{q['id']}", headers=buyer).json()["status"] == "accepted"
    assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/rfqs/{q['rfq_id']}", headers=buyer).json()["status"] == "closed"
    assert [o["id"] for o in client.get(f"/api/v1/orgs/{SELLER}/orders", headers=seller).json()] == [order["id"]]
    with SessionLocal() as db:
        movement = db.scalar(select(StockMovement).where(StockMovement.order_id == order["id"]))
    assert (movement.delta, movement.reason) == (-10, "order")


def test_trade_records_carry_display_names_for_both_parties(client):
    buyer, seller = setup(client)
    created = rfq(client, buyer)
    names = ("Godavari Electricals Distributors (Fictional)", "Sri Lakshmi Switchgear (Fictional)")
    for org, headers in ((DISTRIBUTOR, buyer), (SELLER, seller)):
        listed = client.get(f"/api/v1/orgs/{org}/rfqs", headers=headers).json()[0]
        assert (listed["buyer_org_name"], listed["seller_org_name"]) == names
        assert listed["product_unit"] == "box" and listed["product_name"]
    assert (created["buyer_org_name"], created["seller_org_name"]) == names
    order = confirm(client, buyer, quote(client, seller, created["id"])).json()
    assert (order["buyer_org_name"], order["seller_org_name"]) == names
    assert client.get(f"/api/v1/orgs/{SELLER}/orders/{order['id']}", headers=seller).json()["seller_org_name"] == names[1]


def test_confirmation_rejections(client):
    buyer, seller = setup(client)

    q = quote(client, seller, rfq(client, buyer)["id"])
    assert reason(confirm(client, buyer, q, total_paise=q["total_paise"] - 1)) == "total_mismatch"
    with SessionLocal() as db:
        db.execute(update(Quote).where(Quote.id == q["id"]).values(valid_until=datetime.now(UTC) - timedelta(seconds=1)))
        db.commit()
    assert reason(confirm(client, buyer, q)) == "expired"
    assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/quotes/{q['id']}", headers=buyer).json()["status"] == "expired"

    r = rfq(client, buyer)["id"]
    v1 = quote(client, seller, r)
    v2 = quote(client, seller, r, unit_price_paise=44000)
    assert v2["version"] == 2
    assert reason(confirm(client, buyer, v1, key="k2")) == "superseded"
    assert reason(confirm(client, buyer, v2, key="k3", quote_version=1)) == "superseded"
    assert confirm(client, buyer, v2, key="k4").status_code == 201
    assert reason(confirm(client, buyer, v2, key="k5")) == "already_accepted"
    reused = confirm(client, buyer, v1, key="k4")
    assert reused.status_code == 409 and reused.json()["error"]["code"] == "idempotency_key_reused"
    missing = client.post(f"/api/v1/orgs/{DISTRIBUTOR}/orders", headers=buyer, json={"quote_id": v2["id"], "quote_version": 2, "total_paise": 1})
    assert missing.json()["error"]["code"] == "idempotency_key_required"


def test_insufficient_stock_commits_nothing(client):
    buyer, seller = setup(client)
    q = quote(client, seller, rfq(client, buyer, quantity=501)["id"])
    r = confirm(client, buyer, q)
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"
    assert stock(client, seller) == 500
    assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/quotes/{q['id']}", headers=buyer).json()["status"] == "sent"
    assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/orders", headers=buyer).json() == []


def test_only_buyer_purchasers_can_confirm(client):
    buyer, seller = setup(client)
    q = quote(client, seller, rfq(client, buyer)["id"])
    assert confirm(client, login(client, "meena.viewer@example.test"), q).status_code == 403
    assert confirm(client, seller, q, org=SELLER).status_code == 403  # catalog manager of a selling-only org
    assert confirm(client, login(client, "ravi.seller@example.test"), q, org=SELLER).status_code == 403  # admin, cannot buy
    outsider = login(client, "kiran.retail@example.test")
    assert confirm(client, outsider, q, org=RETAILER).status_code == 404
    assert stock(client, seller) == 500


def test_other_orgs_cannot_read_trade_records(client):
    buyer, seller = setup(client)
    q = quote(client, seller, rfq(client, buyer)["id"])
    order = confirm(client, buyer, q).json()
    outsider = login(client, "kiran.retail@example.test")
    for path in (f"rfqs/{q['rfq_id']}", f"quotes/{q['id']}", f"orders/{order['id']}"):
        assert client.get(f"/api/v1/orgs/{RETAILER}/{path}", headers=outsider).status_code == 404, path
        assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/{path}", headers=outsider).status_code == 404, path
    assert client.get(f"/api/v1/orgs/{RETAILER}/rfqs", headers=outsider).json() == []
    assert client.get(f"/api/v1/orgs/{RETAILER}/orders", headers=outsider).json() == []


def test_drafts_are_private_to_seller(client):
    buyer, seller = setup(client)
    r = rfq(client, buyer)["id"]
    draft = quote(client, seller, r, send=False)
    assert draft["status"] == "draft"
    assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/quotes/{draft['id']}", headers=buyer).status_code == 404
    assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/rfqs/{r}", headers=buyer).json()["quotes"] == []
    assert len(client.get(f"/api/v1/orgs/{SELLER}/rfqs/{r}", headers=seller).json()["quotes"]) == 1
    assert confirm(client, buyer, draft).status_code == 404


def test_quote_rules(client):
    buyer, seller = setup(client)
    r = rfq(client, buyer)["id"]
    url = f"/api/v1/orgs/{SELLER}/rfqs/{r}/quotes"
    base = {"unit_price_paise": 45000, "valid_until": soon()}
    assert client.post(url, headers=seller, json=base | {"discount_paise": 450000}).status_code == 400
    assert client.post(url, headers=seller, json=base | {"advance_paise": 10**9}).status_code == 400
    assert client.post(url, headers=seller, json=base | {"valid_until": soon(-1)}).status_code == 400
    assert client.post(url, headers=seller, json=base | {"valid_until": "2030-01-01T00:00:00"}).status_code == 400  # no timezone
    assert client.post(url, headers=buyer, json=base).status_code == 404  # not a member of the seller org
    assert client.post(f"/api/v1/orgs/{DISTRIBUTOR}/rfqs/{r}/quotes", headers=buyer, json=base).status_code == 403
    assert client.post(f"/api/v1/orgs/{DISTRIBUTOR}/rfqs/{r}/quotes", headers=login(client, "lakshmi.admin@example.test"), json=base).status_code == 404  # buyer side cannot quote its own RFQ

    v1 = quote(client, seller, r, send=False)
    quote(client, seller, r, send=False)
    stale = client.post(f"/api/v1/orgs/{SELLER}/quotes/{v1['id']}/send", headers=seller)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "quote_not_sendable"


def test_reject_reopens_rfq_for_a_new_version(client):
    buyer, seller = setup(client)
    q = quote(client, seller, rfq(client, buyer)["id"])
    r = client.post(f"/api/v1/orgs/{DISTRIBUTOR}/quotes/{q['id']}/reject", headers=buyer)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/rfqs/{q['rfq_id']}", headers=buyer).json()["status"] == "open"
    assert reason(confirm(client, buyer, q)) == "not_sent"
    assert quote(client, seller, q["rfq_id"], unit_price_paise=43000)["version"] == 2


def test_rfq_rules(client):
    buyer, _ = setup(client)
    buyer = buyer | {"Idempotency-Key": "rules"}
    url = f"/api/v1/orgs/{DISTRIBUTOR}/rfqs"
    body = {"product_id": str(SWITCH), "quantity": 4, "delivery_city": "Guntur"}
    assert client.post(url, headers=buyer, json=body).status_code == 400  # below MOQ 5
    own = body | {"product_id": str(_id("product:GD-6A-1W-10")), "quantity": 5}
    assert client.post(url, headers=buyer, json=own).status_code == 400
    key = {"Idempotency-Key": "rules"}
    assert client.post(url, headers=login(client, "meena.viewer@example.test") | key, json=body | {"quantity": 5}).status_code == 403
    seller_admin = login(client, "ravi.seller@example.test")
    assert client.post(f"/api/v1/orgs/{SELLER}/rfqs", headers=seller_admin | key, json=body | {"quantity": 5}).status_code == 403


RFQ_BODY = {"product_id": str(SWITCH), "quantity": 10, "delivery_city": "Guntur", "note": "retry check"}


def post_rfq(client, headers, key, body=RFQ_BODY, org=DISTRIBUTOR):
    return client.post(f"/api/v1/orgs/{org}/rfqs", headers=headers | {"Idempotency-Key": key}, json=body)


def rfq_count(client, headers, org=DISTRIBUTOR):
    return len(client.get(f"/api/v1/orgs/{org}/rfqs", headers=headers).json())


def test_rfq_retry_after_lost_response_returns_the_original(client):
    buyer, seller = setup(client)
    first = post_rfq(client, buyer, "form-1")
    assert first.status_code == 201, first.text
    # The client never saw `first` and sends the same intent again.
    again = post_rfq(client, buyer, "form-1")
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    assert rfq_count(client, buyer) == 1 and rfq_count(client, seller, SELLER) == 1


def test_rfq_key_reused_for_a_different_request_is_refused(client):
    buyer, _ = setup(client)
    assert post_rfq(client, buyer, "form-2").status_code == 201
    for change in ({"quantity": 11}, {"delivery_city": "Tenali"}, {"note": None}, {"needed_by": "2026-12-01"}):
        r = post_rfq(client, buyer, "form-2", RFQ_BODY | change)
        assert r.status_code == 409 and r.json()["error"]["code"] == "idempotency_key_reused", change
    assert rfq_count(client, buyer) == 1


def test_rfq_requires_an_idempotency_key(client):
    buyer, _ = setup(client)
    r = client.post(f"/api/v1/orgs/{DISTRIBUTOR}/rfqs", headers=buyer, json=RFQ_BODY)
    assert r.status_code == 400 and r.json()["error"]["code"] == "idempotency_key_required"
    assert rfq_count(client, buyer) == 0


def test_concurrent_rfq_retries_create_one_request(client):
    buyer, _ = setup(client)
    results = race(*[lambda c: post_rfq(c, buyer, "form-3")] * 4)
    assert sorted(r.status_code for r in results) == [200, 200, 200, 201]
    assert len({r.json()["id"] for r in results}) == 1
    assert rfq_count(client, buyer) == 1


def test_rfq_keys_are_scoped_to_the_buyer_organization(client):
    buyer, _ = setup(client)
    retailer = login(client, "kiran.retail@example.test")
    mine = post_rfq(client, buyer, "shared-key").json()
    theirs = post_rfq(client, retailer, "shared-key", org=RETAILER)
    # Same key in another organization is a separate request and reveals nothing about the first.
    assert theirs.status_code == 201 and theirs.json()["id"] != mine["id"]
    assert client.get(f"/api/v1/orgs/{RETAILER}/rfqs/{mine['id']}", headers=retailer).status_code == 404
    # A refused caller cannot use the key to read or replay another organization's request.
    assert post_rfq(client, retailer, "shared-key", org=DISTRIBUTOR).status_code in (403, 404)
    assert post_rfq(client, login(client, "meena.viewer@example.test"), "shared-key").status_code == 403


def race(*calls):
    barrier, results = threading.Barrier(len(calls)), [None] * len(calls)

    def run(i, call):
        c = TestClient(app)
        barrier.wait()
        results[i] = call(c)

    threads = [threading.Thread(target=run, args=(i, call)) for i, call in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_concurrent_orders_for_last_stock(client):
    buyer, seller = setup(client)
    retailer = login(client, "kiran.retail@example.test")
    product = _id("product:SL-16A-1W-10")  # stock 200, moq 5
    q1 = quote(client, seller, rfq(client, buyer, product=product, quantity=150)["id"])
    q2 = quote(client, seller, rfq(client, retailer, org=RETAILER, product=product, quantity=150)["id"])
    results = race(lambda c: confirm(c, buyer, q1), lambda c: confirm(c, retailer, q2, org=RETAILER))
    assert sorted(r.status_code for r in results) == [201, 409]
    assert stock(client, seller, product) == 50


def test_concurrent_confirmations_of_one_quote(client):
    buyer, seller = setup(client)
    admin = login(client, "lakshmi.admin@example.test")
    q = quote(client, seller, rfq(client, buyer)["id"])
    results = race(lambda c: confirm(c, buyer, q, key="a"), lambda c: confirm(c, admin, q, key="b"))
    assert sorted(r.status_code for r in results) == [201, 409]
    assert stock(client, seller) == 490
