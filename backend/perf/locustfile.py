"""Level 3 benchmark: catalog search, RFQ creation and retry, quote retrieval, order confirmation and concurrent stock.

Run only against a local API backed by a disposable database (see docs/CI.md). Fictional seed users only.
"""
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from locust import HttpUser, between, events, task

LOCAL = {"localhost", "127.0.0.1", "::1"}
BUYER, SELLER = "suresh.buyer@example.test", "anitha.catalog@example.test"
SWITCH_SKU = "SL-6A-1W-10"  # fictional seed product: MOQ 5 boxes


@events.init.add_listener
def refuse_remote(environment, **_):
    host = urlparse(environment.host or "").hostname
    if host not in LOCAL:
        raise SystemExit(f"perf: refusing to load-test {environment.host!r}; only a local disposable API is allowed")


def sign_in(user: HttpUser, email: str) -> tuple[dict, str]:
    token = user.client.post("/api/v1/auth/local/session", json={"email": email}, name="sign in").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = user.client.get("/api/v1/me", headers=headers, name="me").json()
    return headers, me["memberships"][0]["organization"]["id"]


class Trader(HttpUser):
    """A buyer searching and requesting quotes, with the seller answering so that orders can be confirmed."""

    weight = 4
    wait_time = between(0.2, 1.0)

    def on_start(self):
        self.buyer, self.buyer_org = sign_in(self, BUYER)
        self.seller, self.seller_org = sign_in(self, SELLER)
        items = self.client.get("/api/v1/catalog/products", params={"q": "6A"}, headers=self.buyer, name="catalog search").json()["items"]
        self.product = next(p for p in items if p["sku"] == SWITCH_SKU)
        self.quotes: list[str] = []

    def _rfq(self, name: str) -> dict | None:
        key = str(uuid.uuid4())
        body = {"product_id": self.product["id"], "quantity": 5, "delivery_city": "Guntur", "note": "perf (fictional)"}
        url = f"/api/v1/orgs/{self.buyer_org}/rfqs"
        r = self.client.post(url, json=body, headers=self.buyer | {"Idempotency-Key": key}, name=name)
        # The retry after a lost response must replay (200), not create a second RFQ (201). Builds without RFQ keys report failures here.
        with self.client.post(url, json=body, headers=self.buyer | {"Idempotency-Key": key}, name="rfq retry (same key)", catch_response=True) as retry:
            if retry.status_code != 200:
                retry.failure(f"expected 200 replay, got {retry.status_code}")
        return r.json() if r.ok else None

    @task(6)
    def catalog_search(self):
        self.client.get("/api/v1/catalog/products", params={"q": "switch", "city": "Guntur", "quantity": 10}, headers=self.buyer, name="catalog search")

    @task(2)
    def rfq_create_and_retry(self):
        self._rfq("rfq create")

    @task(3)
    def quote_retrieval(self):
        if self.quotes:
            self.client.get(f"/api/v1/orgs/{self.buyer_org}/quotes/{self.quotes[-1]}", headers=self.buyer, name="quote retrieval")

    @task(1)
    def order_confirmation(self):
        rfq = self._rfq("rfq create")
        if not rfq:
            return
        valid = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        draft = self.client.post(f"/api/v1/orgs/{self.seller_org}/rfqs/{rfq['id']}/quotes", headers=self.seller,
                                 json={"unit_price_paise": self.product["price_paise"], "valid_until": valid}, name="quote draft (seller)")
        if not draft.ok:
            return
        sent = self.client.post(f"/api/v1/orgs/{self.seller_org}/quotes/{draft.json()['id']}/send", headers=self.seller, name="quote send (seller)")
        if not sent.ok:
            return
        q = sent.json()
        self.quotes = self.quotes[-20:] + [q["id"]]
        body = {"quote_id": q["id"], "quote_version": q["version"], "total_paise": q["total_paise"]}
        key = {"Idempotency-Key": str(uuid.uuid4())}
        self.client.post(f"/api/v1/orgs/{self.buyer_org}/orders", json=body, headers=self.buyer | key, name="order confirmation")
        self.client.post(f"/api/v1/orgs/{self.buyer_org}/orders", json=body, headers=self.buyer | key, name="order retry (same key)")


class StockKeeper(HttpUser):
    """Concurrent restocks of the same product row, competing with order confirmations for its stock lock."""

    weight = 1
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.seller, self.seller_org = sign_in(self, SELLER)
        products = self.client.get(f"/api/v1/orgs/{self.seller_org}/products", headers=self.seller, name="seller products").json()
        self.product = next(p for p in products if p["sku"] == SWITCH_SKU)

    @task
    def concurrent_stock(self):
        self.client.post(f"/api/v1/orgs/{self.seller_org}/products/{self.product['id']}/stock-adjustments",
                         headers=self.seller | {"Idempotency-Key": str(uuid.uuid4())},
                         json={"delta": 5, "reason": "restock", "note": "perf (fictional)"}, name="stock adjustment (concurrent)")
