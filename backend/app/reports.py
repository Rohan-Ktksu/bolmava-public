"""Reports computed only from saved records. Period boundaries: whole Asia/Kolkata days, end exclusive in UTC."""
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.auth import Member, member
from app.db import get_db
from app.errors import AppError
from app.models import Case, Order, PaymentEvent, PaymentRequest
from app.schemas import DelayedOrder, ReportOut, TradeTotals
from app.trade import db_clock

router = APIRouter(prefix="/api/v1", tags=["reports"])
IST = ZoneInfo("Asia/Kolkata")
DELAY_DAYS = 7  # SPEC O6
SIGNED = case((PaymentEvent.kind == "receipt", PaymentEvent.amount_paise), else_=-PaymentEvent.amount_paise)


def current_month(now: datetime) -> tuple[date, date]:
    today = now.astimezone(IST).date()
    return today.replace(day=1), today


def _totals(db: Session, side_col, org_id, start, end, now) -> TradeTotals:
    mine = side_col == org_id
    in_period = (Order.created_at >= start) & (Order.created_at < end)
    counts = db.execute(
        select(
            func.count().filter(Order.status != "cancelled", in_period),
            func.coalesce(func.sum(Order.total_paise).filter(Order.status != "cancelled", in_period), 0),
            func.count().filter(Order.status == "cancelled", in_period),
        ).where(mine)
    ).one()
    received = db.scalar(
        select(func.coalesce(func.sum(SIGNED), 0)).join(Order, Order.id == PaymentEvent.order_id)
        .where(mine, PaymentEvent.created_at >= start, PaymentEvent.created_at < end)
    )
    per_order = (
        select(
            case((Order.status == "cancelled", 0), else_=Order.total_paise).label("due"),
            func.coalesce(select(func.sum(SIGNED)).where(PaymentEvent.order_id == Order.id).scalar_subquery(), 0).label("got"),
        ).where(mine).subquery()
    )
    outstanding, refund = db.execute(select(
        func.coalesce(func.sum(func.greatest(per_order.c.due - per_order.c.got, 0)), 0),
        func.coalesce(func.sum(func.greatest(per_order.c.got - per_order.c.due, 0)), 0),
    )).one()
    pending, approved = db.execute(
        select(
            func.coalesce(func.sum(PaymentRequest.amount_paise).filter(PaymentRequest.status == "pending_approval"), 0),
            func.coalesce(func.sum(PaymentRequest.amount_paise).filter(PaymentRequest.status == "approved", PaymentRequest.approval_expires_at > now), 0),
        ).join(Order, Order.id == PaymentRequest.order_id).where(mine)
    ).one()
    return TradeTotals(
        orders=counts[0], order_value_paise=counts[1], cancelled_orders=counts[2], received_paise=received,
        outstanding_paise=outstanding, refund_due_paise=refund, awaiting_approval_paise=pending, approved_unrecorded_paise=approved,
    )


def summary(db: Session, org_id, from_date: date, to_date: date, limit: int = 20) -> ReportOut:
    """Shared by the report endpoint and the assistant."""
    if to_date < from_date or (to_date - from_date).days > 365:
        raise AppError(400, "validation_error", "Use a period of 1 to 366 days with from on or before to.")
    start = datetime.combine(from_date, time.min, IST).astimezone(UTC)
    end = datetime.combine(to_date + timedelta(days=1), time.min, IST).astimezone(UTC)
    now = db_clock(db)
    party = or_(Order.buyer_org_id == org_id, Order.seller_org_id == org_id)
    delayed = (
        select(Order).where(party, Order.status == "confirmed", Order.fulfillment_status.in_(("pending", "dispatched")),
                            Order.created_at < now - timedelta(days=DELAY_DAYS))
    )
    delayed_rows = db.scalars(delayed.order_by(Order.created_at, Order.id).limit(limit)).all()
    return ReportOut(
        org_id=org_id, from_date=from_date, to_date=to_date, period_start_utc=start, period_end_utc=end,
        sales=_totals(db, Order.seller_org_id, org_id, start, end, now),
        purchases=_totals(db, Order.buyer_org_id, org_id, start, end, now),
        open_cases=db.scalar(select(func.count()).select_from(Case).where(
            or_(Case.buyer_org_id == org_id, Case.seller_org_id == org_id), Case.status.not_in(("resolved", "closed")))),
        delayed_orders_count=db.scalar(select(func.count()).select_from(delayed.subquery())),
        delayed_orders=[
            DelayedOrder(order_id=o.id, side="sales" if o.seller_org_id == org_id else "purchases",
                         fulfillment_status=o.fulfillment_status, created_at=o.created_at)
            for o in delayed_rows
        ],
    )


@router.get("/orgs/{org_id}/reports/summary", response_model=ReportOut)
def report(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    limit: int = Query(20, ge=1, le=100),
    m: Member = Depends(member),
    db: Session = Depends(get_db),
):
    default_from, default_to = current_month(db_clock(db))
    return summary(db, m.org.id, from_date or default_from, to_date or default_to, limit)
