from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import update

from app.conversation import rupees
from app.db import SessionLocal
from app.models import Order, PaymentEvent
from app.seed import _id
from tests.conftest import login
from tests.test_cases import open_case
from tests.test_conversation import chat
from tests.test_fulfillment import cancel
from tests.test_payments import approve, approve_reversal, ask_reversal, order, record, request
from tests.test_trade import DISTRIBUTOR, RETAILER, SELLER, confirm, quote, rfq, setup

IST = ZoneInfo("Asia/Kolkata")


def at(y, m, d, hh=10, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def set_time(model, row_id, when):
    with SessionLocal() as db:
        db.execute(update(model).where(model.id == row_id).values(created_at=when))
        db.commit()


def fixtures(client):
    """A: Godavari buys from Sri Lakshmi (advance recorded 30 Sep 23:30 IST). B: same pair, cancelled.
    C: Godavari sells to Vizag (full receipt, then reversed). Open case and a pending request on A."""
    buyer, seller, a = order(client)
    finance = login(client, "farah.finance@example.test")
    adv = request(client, buyer, a).json()
    approve(client, finance, adv)
    a_receipt = record(client, finance, adv).json()
    b = confirm(client, buyer, quote(client, seller, rfq(client, buyer)["id"]), key="b").json()
    assert cancel(client, buyer, b).status_code == 200

    retailer, godavari_admin = login(client, "kiran.retail@example.test"), login(client, "lakshmi.admin@example.test")
    c_rfq = rfq(client, retailer, org=RETAILER, product=_id("product:GD-6A-1W-10"), quantity=5)
    draft = client.post(f"/api/v1/orgs/{DISTRIBUTOR}/rfqs/{c_rfq['id']}/quotes", headers=godavari_admin,
                        json={"unit_price_paise": 52000, "valid_until": (datetime.now(UTC) + timedelta(days=3)).isoformat()}).json()
    sent = client.post(f"/api/v1/orgs/{DISTRIBUTOR}/quotes/{draft['id']}/send", headers=godavari_admin).json()
    c = confirm(client, retailer, sent, key="c", org=RETAILER).json()
    full = request(client, retailer, c, amount=c["total_paise"], purpose="balance", org=RETAILER).json()
    approve(client, finance, full)
    c_receipt = record(client, finance, full).json()
    asked = ask_reversal(client, finance, c_receipt, reason="Bounced (simulated)").json()
    c_reversal = {"id": approve_reversal(client, login(client, "arjun.finance@example.test"), asked).json()["reversal_event_id"]}

    open_case(client, buyer, a)
    assert request(client, buyer, a, amount=1000, purpose="balance").status_code == 201

    set_time(Order, a["id"], at(2026, 9, 15))
    set_time(Order, b["id"], at(2026, 9, 16))
    set_time(Order, c["id"], at(2026, 10, 5))
    set_time(PaymentEvent, a_receipt["id"], at(2026, 9, 30, 23, 30))  # 18:00 UTC: still September in India
    set_time(PaymentEvent, c_receipt["id"], at(2026, 10, 5, 15))
    set_time(PaymentEvent, c_reversal["id"], at(2026, 10, 6, 9))
    return a, b, c


def report(client, h, org, frm=None, to=None):
    params = {k: v for k, v in (("from", frm), ("to", to)) if v}
    r = client.get(f"/api/v1/orgs/{org}/reports/summary", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def totals(block):
    return {k: block[k] for k in ("orders", "order_value_paise", "cancelled_orders", "received_paise", "outstanding_paise",
                                  "refund_due_paise", "awaiting_approval_paise", "approved_unrecorded_paise")}


def test_reports_reconcile_with_saved_records(client):
    a, b, c = fixtures(client)
    A, C = a["total_paise"], c["total_paise"]
    godavari = login(client, "lakshmi.admin@example.test")

    sept = report(client, godavari, DISTRIBUTOR, "2026-09-01", "2026-09-30")
    assert sept["period_start_utc"].startswith("2026-08-31T18:30:00") and sept["period_end_utc"].startswith("2026-09-30T18:30:00")
    assert totals(sept["purchases"]) == dict(orders=1, order_value_paise=A, cancelled_orders=1, received_paise=100000,
                                             outstanding_paise=A - 100000, refund_due_paise=0, awaiting_approval_paise=1000,
                                             approved_unrecorded_paise=0)
    assert totals(sept["sales"]) == dict(orders=0, order_value_paise=0, cancelled_orders=0, received_paise=0,
                                         outstanding_paise=C, refund_due_paise=0, awaiting_approval_paise=0, approved_unrecorded_paise=0)
    assert sept["open_cases"] == 1 and sept["simulated"] is True

    octo = report(client, godavari, DISTRIBUTOR, "2026-10-01", "2026-10-31")
    assert (octo["sales"]["orders"], octo["sales"]["order_value_paise"], octo["sales"]["received_paise"]) == (1, C, 0)
    assert (octo["purchases"]["orders"], octo["purchases"]["received_paise"]) == (0, 0)  # 30 Sep 23:30 IST stays in September

    aug = report(client, godavari, DISTRIBUTOR, "2026-08-01", "2026-08-31")
    assert (aug["purchases"]["orders"], aug["purchases"]["received_paise"], aug["sales"]["order_value_paise"]) == (0, 0, 0)
    assert aug["purchases"]["outstanding_paise"] == A - 100000  # balances are as of now, not per period

    seller = report(client, login(client, "ravi.seller@example.test"), SELLER, "2026-09-01", "2026-09-30")
    assert (seller["sales"]["orders"], seller["sales"]["cancelled_orders"], seller["sales"]["received_paise"]) == (1, 1, 100000)
    assert seller["purchases"]["orders"] == 0 and seller["open_cases"] == 1

    vizag = report(client, login(client, "kiran.retail@example.test"), RETAILER, "2026-10-01", "2026-10-31")
    assert (vizag["purchases"]["orders"], vizag["purchases"]["received_paise"], vizag["purchases"]["outstanding_paise"]) == (1, 0, C)
    assert vizag["open_cases"] == 0

    week_ago = datetime.now(UTC) - timedelta(days=7)
    expected = {o["id"] for o, when in ((a, at(2026, 9, 15)), (c, at(2026, 10, 5))) if when < week_ago}
    assert {d["order_id"] for d in sept["delayed_orders"]} == expected and sept["delayed_orders_count"] == len(expected)
    assert report(client, godavari, DISTRIBUTOR, "2026-09-01", "2026-09-30")["delayed_orders"][0]["side"] == "purchases"


def test_report_access_and_validation(client):
    buyer, _ = setup(client)
    outsider = login(client, "kiran.retail@example.test")
    assert client.get(f"/api/v1/orgs/{DISTRIBUTOR}/reports/summary", headers=outsider).status_code == 404
    url = f"/api/v1/orgs/{DISTRIBUTOR}/reports/summary"
    assert client.get(url, headers=buyer, params={"from": "2026-10-02", "to": "2026-10-01"}).status_code == 400
    assert client.get(url, headers=buyer, params={"from": "2025-01-01", "to": "2026-10-01"}).status_code == 400
    assert client.get(url, headers=buyer, params={"limit": 101}).status_code == 400
    assert client.get(url, headers=login(client, "meena.viewer@example.test")).status_code == 200  # all members may read


def test_assistant_report_uses_the_same_numbers(client):
    fixtures(client)
    godavari = login(client, "lakshmi.admin@example.test")
    r = report(client, godavari, DISTRIBUTOR)  # default: current Asia/Kolkata month, same as the assistant
    reply = chat(client, godavari)("show me the sales report")["reply"]
    s, p = r["sales"], r["purchases"]
    assert f"Sales: {s['orders']} orders worth {rupees(s['order_value_paise'])}" in reply
    assert f"Still to receive {rupees(s['outstanding_paise'])}" in reply
    assert f"Still to pay {rupees(p['outstanding_paise'])}" in reply
    assert f"Open complaints: {r['open_cases']}" in reply and "simulated" in reply
    assert "possible suppliers" in reply
