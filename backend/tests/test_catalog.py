import threading

from fastapi.testclient import TestClient

from app import catalog
from app.main import app
from app.seed import _id
from tests.conftest import login

SELLER = _id("org:sri-lakshmi")
DISTRIBUTOR = _id("org:godavari")
RETAILER = _id("org:vizag-home")
SWITCH = _id("product:SL-6A-1W-10")

NEW_PRODUCT = {
    "sku": "SL-NEW", "name": "20A one-way switch", "brand": "Kanaka (Fictional)", "model": "K20", "rating_amps": 20,
    "voltage_v": 240, "ways": 1, "unit": "piece", "pack_size": 1, "moq": 10, "price_paise": 12000,
    "lead_time_days": 4, "delivery_cities": ["Guntur"],
}


def products_url(org=SELLER):
    return f"/api/v1/orgs/{org}/products"


def test_catalog_manager_creates_and_edits(client):
    h = login(client, "anitha.catalog@example.test")
    r = client.post(products_url(), headers=h, json=NEW_PRODUCT)
    assert r.status_code == 201, r.text
    p = r.json()
    assert (p["available_qty"], p["version"], p["category"]) == (0, 1, "electrical_switch")

    r = client.patch(f"{products_url()}/{p['id']}", headers=h, json={"version": 1, "price_paise": 11500})
    assert r.status_code == 200
    assert (r.json()["price_paise"], r.json()["version"], r.json()["name"]) == (11500, 2, NEW_PRODUCT["name"])

    stale = client.patch(f"{products_url()}/{p['id']}", headers=h, json={"version": 1, "price_paise": 1})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"


def test_patch_revalidates_merged_product(client):
    h = login(client, "anitha.catalog@example.test")
    r = client.patch(f"{products_url()}/{SWITCH}", headers=h, json={"version": 2, "unit": "piece"})
    assert r.status_code == 400  # box of 10 cannot become a piece without pack_size 1


def test_duplicate_sku_conflicts(client):
    h = login(client, "anitha.catalog@example.test")
    r = client.post(products_url(), headers=h, json=NEW_PRODUCT | {"sku": "SL-6A-1W-10"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_invalid_product_rejected(client):
    r = client.post(products_url(), headers=login(client, "ravi.seller@example.test"),
                    json=NEW_PRODUCT | {"price_paise": 0, "ways": 3})
    assert r.status_code == 400
    assert len(r.json()["error"]["details"]) == 2


def test_roles_and_capabilities_enforced(client):
    for email in ("suresh.buyer@example.test", "meena.viewer@example.test"):
        r = client.post(products_url(DISTRIBUTOR), headers=login(client, email), json=NEW_PRODUCT)
        assert r.status_code == 403, email
    retailer = client.post(products_url(RETAILER), headers=login(client, "kiran.retail@example.test"), json=NEW_PRODUCT)
    assert retailer.status_code == 403  # admin, but the org cannot sell


def test_other_org_cannot_read_private_catalog(client):
    h = login(client, "suresh.buyer@example.test")
    assert client.get(products_url(), headers=h).status_code == 404
    assert client.get(f"{products_url()}/{SWITCH}", headers=h).status_code == 404
    # own org route, other org's product id
    assert client.get(f"{products_url(DISTRIBUTOR)}/{SWITCH}", headers=h).status_code == 404
    r = client.patch(f"{products_url(DISTRIBUTOR)}/{SWITCH}", headers=login(client, "lakshmi.admin@example.test"),
                     json={"version": 2, "price_paise": 1})
    assert r.status_code == 404


def adjust(client, h, key, delta, reason="damage", product=SWITCH):
    return client.post(f"{products_url()}/{product}/stock-adjustments", headers=h | {"Idempotency-Key": key},
                       json={"delta": delta, "reason": reason})


def test_stock_adjustment_is_idempotent(client):
    h = login(client, "anitha.catalog@example.test")
    first = adjust(client, h, "k1", 50, "restock")
    assert first.status_code == 201 and first.json()["resulting_qty"] == 550
    again = adjust(client, h, "k1", 50, "restock")
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    assert client.get(f"{products_url()}/{SWITCH}", headers=h).json()["available_qty"] == 550
    reused = adjust(client, h, "k1", 7, "restock")
    assert reused.status_code == 409 and reused.json()["error"]["code"] == "idempotency_key_reused"


def test_stock_cannot_go_negative_or_skip_key(client):
    h = login(client, "anitha.catalog@example.test")
    r = adjust(client, h, "k2", -501)
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"
    r = client.post(f"{products_url()}/{SWITCH}/stock-adjustments", headers=h, json={"delta": 1, "reason": "restock"})
    assert r.json()["error"]["code"] == "idempotency_key_required"
    assert client.get(f"{products_url()}/{SWITCH}", headers=h).json()["available_qty"] == 500


def test_concurrent_decrements_never_oversell(client):
    h = login(client, "anitha.catalog@example.test")
    barrier, results = threading.Barrier(12), []

    def worker(i):
        c = TestClient(app)
        barrier.wait()
        results.append(adjust(c, h, f"c{i}", -60).status_code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201] * 8 + [409] * 4  # 500 // 60 = 8
    assert client.get(f"{products_url()}/{SWITCH}", headers=h).json()["available_qty"] == 20


def test_discovery_filters(client):
    h = login(client, "suresh.buyer@example.test")
    url = "/api/v1/catalog/products"
    everything = client.get(url, headers=h).json()["items"]
    assert len(everything) == 5
    prices = [p["price_paise"] for p in everything]
    assert prices == sorted(prices)

    r = client.get(url, headers=h, params={"rating_amps": 6, "ways": 1, "quantity": 100, "city": "guntur"}).json()
    assert [p["sku"] for p in r["items"]] == ["SL-BELL-1", "SL-6A-1W-10"]  # by price_paise
    assert r["applied_filters"] == {"rating_amps": 6, "ways": 1, "city": "guntur", "quantity": 100}
    assert r["items"][1]["seller"]["name"] == "Sri Lakshmi Switchgear (Fictional)"

    assert [p["sku"] for p in client.get(url, headers=h, params={"q": "బెల్"}).json()["items"]] == ["SL-BELL-1"]
    assert client.get(url, headers=h, params={"q": "%"}).json()["items"] == []
    assert client.get(url, headers=h, params={"city": "Chennai"}).json()["items"] == []
    assert len(client.get(url, headers=h, params={"max_price_paise": 50000}).json()["items"]) == 2
    assert client.get(url, headers=h, params={"limit": 0}).status_code == 400
    assert client.get(url).status_code == 401


def test_inactive_products_hidden_from_discovery(client):
    seller = login(client, "ravi.seller@example.test")
    client.patch(f"{products_url()}/{SWITCH}", headers=seller, json={"version": 2, "status": "inactive"})
    buyer = login(client, "suresh.buyer@example.test")
    assert client.get(f"/api/v1/catalog/products/{SWITCH}", headers=buyer).status_code == 404
    assert len(client.get("/api/v1/catalog/products", headers=buyer).json()["items"]) == 4
    assert client.get(f"/api/v1/catalog/products/{_id('product:SL-BELL-1')}", headers=buyer).status_code == 200


def test_audit_trail_written(client):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import AuditEvent

    h = login(client, "anitha.catalog@example.test")
    adjust(client, h, "k3", 5, "restock")
    with SessionLocal() as db:
        actions = db.scalars(select(AuditEvent.action).where(AuditEvent.org_id == SELLER)).all()
    assert actions == ["stock.adjusted"]


def test_concurrent_same_key_retry_on_last_stock_replays(client, monkeypatch):
    h = login(client, "anitha.catalog@example.test")
    product = client.post(products_url(), headers=h, json=NEW_PRODUCT).json()["id"]
    assert adjust(client, h, "stock-1", 1, "restock", product).json()["resulting_qty"] == 1
    start, past_lookup, results = threading.Barrier(2), threading.Barrier(2), []
    real_replay = catalog._replay

    def replay_then_wait(db, org_id, key, *rest):
        # Hold each request after its replay lookup until both have looked (or 2 s pass, if the
        # same-key lock correctly keeps the second request out), forcing the stale-lookup race.
        prior = real_replay(db, org_id, key, *rest)
        if prior is None and key == "same-key":
            try:
                past_lookup.wait(timeout=2)
            except threading.BrokenBarrierError:
                pass
        return prior

    monkeypatch.setattr(catalog, "_replay", replay_then_wait)

    def worker():
        c = TestClient(app)
        start.wait()
        results.append(adjust(c, h, "same-key", -1, product=product))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r.status_code for r in results) == [200, 201]
    assert results[0].json()["id"] == results[1].json()["id"]
    assert client.get(f"{products_url()}/{product}", headers=h).json()["available_qty"] == 0
    # a different key on empty stock is a genuine shortage
    assert adjust(client, h, "other-key", -1, product=product).json()["error"]["code"] == "insufficient_stock"


def history(client, h, product=SWITCH, org=SELLER, **params):
    return client.get(f"{products_url(org)}/{product}/stock-movements", headers=h, params=params)


def test_stock_history_pages_newest_first_without_shifting(client):
    h = login(client, "anitha.catalog@example.test")
    for i in range(5):
        assert adjust(client, h, f"hist-{i}", i + 1, "restock").status_code == 201
    first = history(client, h, limit=2).json()
    assert [m["delta"] for m in first["items"]] == [5, 4]
    assert first["items"][0]["actor_name"] == "Anitha (Fictional)"
    assert first["items"][0]["resulting_qty"] - first["items"][1]["resulting_qty"] == 5
    # A movement made after the first page was read must not push rows into the next page.
    assert adjust(client, h, "hist-late", 9, "restock").status_code == 201
    second = history(client, h, limit=2, before=first["next_before"]).json()
    assert [m["delta"] for m in second["items"]] == [3, 2]
    rest = history(client, h, limit=100, before=second["next_before"]).json()
    assert rest["next_before"] is None and rest["items"][0]["delta"] == 1
    assert rest["items"][-1]["actor_name"] is None  # seed stock has no person


def test_stock_history_access_and_cursor_rules(client):
    viewer = login(client, "meena.viewer@example.test")
    seller = login(client, "anitha.catalog@example.test")
    godavari_product = _id("product:GD-6A-1W-10")
    assert history(client, viewer, product=godavari_product, org=DISTRIBUTOR).status_code == 200  # members may read
    assert history(client, viewer, product=SWITCH, org=DISTRIBUTOR).status_code == 404  # not Godavari's product
    assert history(client, viewer, product=SWITCH, org=SELLER).status_code in (403, 404)  # not a member
    other = history(client, viewer, product=godavari_product, org=DISTRIBUTOR).json()["items"][0]["id"]
    r = history(client, seller, before=other)
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_error"


def test_order_movements_show_the_order_not_the_buyer(client):
    from tests.test_trade import confirm, quote, rfq, setup
    buyer, seller = setup(client)
    order = confirm(client, buyer, quote(client, seller, rfq(client, buyer)["id"])).json()
    latest = history(client, seller).json()["items"][0]
    assert (latest["reason"], latest["order_id"], latest["actor_name"], latest["delta"]) == ("order", order["id"], None, -10)
