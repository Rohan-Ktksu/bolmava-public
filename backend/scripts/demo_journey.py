"""Fictional backend journey against a running local API (no paid services, simulated money only).

    python scripts/demo_journey.py                 # full story, prints each step, exits 1 on any failure
    python scripts/demo_journey.py --report-only   # print the saved-record reports (after restart/restore)

Set BOLMAVA_API (default http://localhost:8000). The API must run in local fictional-user mode with seed data.
Each run creates new records (one RFQ, quote, order of 10 boxes, payment, complaint, conversation).
"""
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = os.environ.get("BOLMAVA_API", "http://localhost:8000")
SWITCH_SKU = "SL-6A-1W-10"


def call(method, path, token=None, body=None, headers=None, expect=(200, 201)):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(API + path, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(req) as r:
            status, payload = r.status, json.loads(r.read() or b"null")
    except HTTPError as e:
        status, payload = e.code, json.loads(e.read() or b"null")
    if status not in expect:
        sys.exit(f"FAILED {method} {path}: {status} {payload}")
    return payload


def login(email):
    return call("POST", "/api/v1/auth/local/session", body={"email": email})["access_token"]


def org_of(token, name_start):
    me = call("GET", "/api/v1/me", token)
    return next(m["organization"]["id"] for m in me["memberships"] if m["organization"]["name"].startswith(name_start))


def step(text):
    print(f"- {text}")


def reports(token, org, label):
    r = call("GET", f"/api/v1/orgs/{org}/reports/summary", token)
    s, p = r["sales"], r["purchases"]
    print(f"{label}: sales orders={s['orders']} value={s['order_value_paise']} received={s['received_paise']} "
          f"outstanding={s['outstanding_paise']} | purchases orders={p['orders']} value={p['order_value_paise']} "
          f"paid={p['received_paise']} outstanding={p['outstanding_paise']} | open_cases={r['open_cases']} (simulated)")
    return r


def report_only():
    seller, buyer = login("ravi.seller@example.test"), login("lakshmi.admin@example.test")
    reports(seller, org_of(seller, "Sri Lakshmi"), "Sri Lakshmi")
    reports(buyer, org_of(buyer, "Godavari"), "Godavari")


def journey():
    seller, catalog, buyer = login("ravi.seller@example.test"), login("anitha.catalog@example.test"), login("lakshmi.admin@example.test")
    finance, support = login("farah.finance@example.test"), login("sanjay.support@example.test")
    seller_org, buyer_org = org_of(seller, "Sri Lakshmi"), org_of(buyer, "Godavari")

    product = next(p for p in call("GET", f"/api/v1/orgs/{seller_org}/products", catalog) if p["sku"] == SWITCH_SKU)
    call("POST", f"/api/v1/orgs/{seller_org}/products/{product['id']}/stock-adjustments", catalog,
         {"delta": 10, "reason": "restock", "note": "demo restock"}, {"Idempotency-Key": str(uuid.uuid4())})
    step(f"Seller catalog: {product['name']} restocked by 10")

    say_conv = call("POST", f"/api/v1/orgs/{buyer_org}/conversations", buyer)["id"]

    def say(text):
        reply = call("POST", f"/api/v1/orgs/{buyer_org}/conversations/{say_conv}/messages", buyer, {"text": text})
        print(f"    buyer: {text}\n    assistant: {reply['reply'].splitlines()[0]}")
        return reply

    say("find 6A one-way switch 100")
    say("quote")
    say("2")
    say("10")
    proposal = say("Guntur")["pending_action"]
    rfq = call("POST", f"/api/v1/orgs/{buyer_org}/pending-actions/{proposal['id']}/confirm", buyer)["rfq"]
    step(f"Buyer RFQ {rfq['id']} for {rfq['quantity']} boxes created through the assistant and an explicit Confirm")

    valid = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    draft = call("POST", f"/api/v1/orgs/{seller_org}/rfqs/{rfq['id']}/quotes", catalog,
                 {"unit_price_paise": 45000, "discount_paise": 1000, "freight_paise": 5000, "advance_paise": 100000, "valid_until": valid})
    quote = call("POST", f"/api/v1/orgs/{seller_org}/quotes/{draft['id']}/send", catalog)
    step(f"Seller sent quote v{quote['version']}: total {quote['total_paise']} paise (simulated tax {quote['tax_paise']})")

    say("order")
    proposal = say("1")["pending_action"]
    order = call("POST", f"/api/v1/orgs/{buyer_org}/pending-actions/{proposal['id']}/confirm", buyer)["order"]
    step(f"Buyer confirmed order {order['id']} (simulated) for the exact quoted terms")

    req = call("POST", f"/api/v1/orgs/{buyer_org}/orders/{order['id']}/payment-requests", buyer,
               {"purpose": "advance", "amount_paise": order["advance_paise"], "quote_version": order["quote_version"]})
    call("POST", f"/api/v1/staff/payment-requests/{req['id']}/approve", buyer,
         {"order_id": order["id"], "purpose": "advance", "amount_paise": req["amount_paise"], "quote_version": req["quote_version"]}, expect=(403,))
    call("POST", f"/api/v1/staff/payment-requests/{req['id']}/approve", finance,
         {"order_id": order["id"], "purpose": "advance", "amount_paise": req["amount_paise"], "quote_version": req["quote_version"]})
    call("POST", f"/api/v1/staff/payment-requests/{req['id']}/record", finance)
    balance = call("GET", f"/api/v1/orgs/{buyer_org}/orders/{order['id']}/payments", buyer)
    step(f"Simulated advance requested by buyer, approved by a different finance user, recorded once: "
         f"received {balance['received_paise']}, outstanding {balance['outstanding_paise']}")

    for who, org, action in ((catalog, seller_org, "dispatch"), (catalog, seller_org, "deliver"), (buyer, buyer_org, "accept")):
        status = call("POST", f"/api/v1/orgs/{org}/orders/{order['id']}/fulfillment", who, {"action": action})["fulfillment_status"]
        step(f"Fulfillment: {action} -> {status}")

    case = call("POST", f"/api/v1/orgs/{buyer_org}/orders/{order['id']}/cases", buyer,
                {"category": "quality", "description": "Two switches feel loose (fictional)", "urgency": "normal"})
    say("I want to talk to a person")
    handoff = next(h for h in call("GET", "/api/v1/staff/handoffs", support) if h["status"] == "queued")
    call("POST", f"/api/v1/staff/handoffs/{handoff['id']}/take", support)
    call("POST", f"/api/v1/staff/handoffs/{handoff['id']}/messages", support, {"text": "I am looking into the quality issue."})
    call("POST", f"/api/v1/staff/cases/{case['id']}/take", support)
    call("POST", f"/api/v1/staff/cases/{case['id']}/updates", support, {"body": "Seller will send two replacements."})
    call("POST", f"/api/v1/staff/cases/{case['id']}/resolve", support, {"resolution": "Two replacements agreed (fictional)."})
    call("POST", f"/api/v1/staff/handoffs/{handoff['id']}/release", support)
    visible = call("GET", f"/api/v1/orgs/{buyer_org}/cases/{case['id']}", buyer)["updates"]
    step(f"Complaint {case['id']} handled by support; buyer sees: {visible[-1]['body']!r}; assistant released")

    say("report")
    reports(seller, seller_org, "Sri Lakshmi")
    reports(buyer, buyer_org, "Godavari")
    print("Journey complete (fictional data, simulated money).")


if __name__ == "__main__":
    report_only() if "--report-only" in sys.argv else journey()
