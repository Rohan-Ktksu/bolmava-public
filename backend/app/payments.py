"""Simulated payments: maker-checker approval, one-time recording, full reversals. No provider; no real money."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth import Member, member, staff
from app.db import get_db
from app.errors import AppError
from app.models import Order, PaymentEvent, PaymentRequest, PaymentReversal, User
from app.schemas import (
    ApprovalIn, DecisionNote, PaymentEventOut, PaymentRequestIn, PaymentRequestOut, PaymentReversalOut, PaymentsView,
    ReversalApprovalIn, ReversalIn,
)
from app.trade import BUYERS, db_clock

router = APIRouter(prefix="/api/v1", tags=["simulated payments"])
APPROVAL_HOURS = 24
OPEN = ("pending_approval", "approved")
NOT_FOUND = AppError(404, "not_found", "Not found.")
finance = staff("finance")


def lock_order(db: Session, order_id, *party) -> Order:
    """Lock order: order row first, then payment request, then (cancellation) product stock."""
    order = db.scalar(select(Order).where(Order.id == order_id, *party).with_for_update().execution_options(populate_existing=True))
    if order is None:
        raise NOT_FOUND
    return order


def _locked_request(db: Session, request_id) -> tuple[Order, PaymentRequest]:
    order_id = db.scalar(select(PaymentRequest.order_id).where(PaymentRequest.id == request_id))
    if order_id is None:
        raise NOT_FOUND
    order = lock_order(db, order_id)
    req = db.scalar(select(PaymentRequest).where(PaymentRequest.id == request_id).with_for_update().execution_options(populate_existing=True))
    return order, req


def view(db: Session, order: Order) -> PaymentsView:
    """Balance computed only from saved receipt/reversal events; approvals and requests never count as received."""
    requests = db.scalars(select(PaymentRequest).where(PaymentRequest.order_id == order.id).order_by(PaymentRequest.created_at)).all()
    events = db.scalars(select(PaymentEvent).where(PaymentEvent.order_id == order.id).order_by(PaymentEvent.created_at)).all()
    received = sum(e.amount_paise if e.kind == "receipt" else -e.amount_paise for e in events)
    due = 0 if order.status == "cancelled" else order.total_paise
    return PaymentsView(
        order_id=order.id, order_status=order.status, total_paise=order.total_paise, advance_paise=order.advance_paise,
        received_paise=received, outstanding_paise=max(due - received, 0), refund_due_paise=max(received - due, 0),
        requests=requests, events=events,
    )


def _advance_received(v: PaymentsView) -> int:
    purpose = {r.id: r.purpose for r in v.requests}
    receipt_purpose = {e.id: purpose[e.request_id] for e in v.events if e.kind == "receipt"}
    return sum(
        (e.amount_paise if e.kind == "receipt" else -e.amount_paise)
        for e in v.events
        if receipt_purpose.get(e.id if e.kind == "receipt" else e.reverses_event_id) == "advance"
    )


def _check_amount(v: PaymentsView, purpose: str, amount: int) -> None:
    if amount > v.outstanding_paise:
        raise AppError(409, "exceeds_outstanding", "This is more than the remaining amount.", {"outstanding_paise": v.outstanding_paise})
    if purpose == "advance" and amount > v.advance_paise - _advance_received(v):
        raise AppError(409, "exceeds_outstanding", "This is more than the agreed advance still due.",
                       {"advance_remaining_paise": v.advance_paise - _advance_received(v)})


def _audit(db: Session, order: Order, actor: User, action: str, entity: str, entity_id, data: dict) -> None:
    for org_id in (order.buyer_org_id, order.seller_org_id):
        audit(db, org_id, actor.id, action, entity, entity_id, data | {"simulated": True})


@router.post("/orgs/{org_id}/orders/{order_id}/payment-requests", response_model=PaymentRequestOut, status_code=201)
def request_payment(order_id: uuid.UUID, body: PaymentRequestIn, response: Response, m: Member = Depends(member), db: Session = Depends(get_db)):
    m.require(BUYERS, "can_buy")
    order = lock_order(db, order_id, Order.buyer_org_id == m.org.id)
    if order.status == "cancelled":
        raise AppError(409, "invalid_transition", "This order is cancelled.", {"status": order.status})
    if body.quote_version != order.quote_version:
        raise AppError(409, "terms_mismatch", "This request does not match the order's agreed terms version.")
    open_req = db.scalar(select(PaymentRequest).where(PaymentRequest.order_id == order.id, PaymentRequest.status.in_(OPEN))
                         .with_for_update())
    if open_req and open_req.status == "approved" and db_clock(db) >= open_req.approval_expires_at:
        open_req.status = "expired"  # a lapsed approval frees the open slot; its decision fields stay as history
        db.flush()
        open_req = None
    if open_req:
        if (open_req.purpose, open_req.amount_paise, open_req.requested_by) == (body.purpose, body.amount_paise, m.user.id):
            response.status_code = 200  # a retry of the same request
            return open_req
        raise AppError(409, "open_request_exists", "This order already has an open payment request.", {"request_id": str(open_req.id)})
    _check_amount(view(db, order), body.purpose, body.amount_paise)
    req = PaymentRequest(order_id=order.id, requested_by=m.user.id, **body.model_dump())
    db.add(req)
    db.flush()
    _audit(db, order, m.user, "payment.requested", "payment_request", req.id, body.model_dump())
    db.commit()
    return req


@router.get("/orgs/{org_id}/orders/{order_id}/payments", response_model=PaymentsView)
def order_payments(order_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where(Order.id == order_id, or_(Order.buyer_org_id == m.org.id, Order.seller_org_id == m.org.id)))
    if order is None:
        raise NOT_FOUND
    return view(db, order)


@router.get("/staff/orders/{order_id}/payments", response_model=PaymentsView, tags=["staff"])
def staff_order_payments(order_id: uuid.UUID, _: User = Depends(finance), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise NOT_FOUND
    return view(db, order)


@router.get("/staff/payment-requests", response_model=list[PaymentRequestOut], tags=["staff"])
def finance_queue(
    status: str = Query("pending_approval", pattern="^(pending_approval|approved|rejected|recorded|expired|cancelled)$"),
    limit: int = Query(50, ge=1, le=100),
    _: User = Depends(finance),
    db: Session = Depends(get_db),
):
    now = db_clock(db)
    match status:  # approvals past their deadline are listed as expired even before the expiry is saved
        case "approved":
            where = and_(PaymentRequest.status == "approved", PaymentRequest.approval_expires_at > now)
        case "expired":
            where = or_(PaymentRequest.status == "expired",
                        and_(PaymentRequest.status == "approved", PaymentRequest.approval_expires_at <= now))
        case _:
            where = PaymentRequest.status == status
    stmt = select(PaymentRequest).where(where).order_by(PaymentRequest.created_at, PaymentRequest.id)
    return db.scalars(stmt.limit(limit)).all()


def _decide(db: Session, request_id, user: User) -> tuple[Order, PaymentRequest]:
    order, req = _locked_request(db, request_id)
    if req.requested_by == user.id:
        raise AppError(403, "self_approval", "A different person must decide on this request.")
    if req.status != "pending_approval":
        raise AppError(409, "invalid_transition", f"This request is {req.status}.", {"status": req.status})
    return order, req


@router.post("/staff/payment-requests/{request_id}/approve", response_model=PaymentRequestOut, tags=["staff"])
def approve(request_id: uuid.UUID, body: ApprovalIn, user: User = Depends(finance), db: Session = Depends(get_db)):
    order, req = _decide(db, request_id, user)
    if (body.order_id, body.purpose, body.amount_paise, body.quote_version) != (req.order_id, req.purpose, req.amount_paise, req.quote_version):
        raise AppError(409, "terms_mismatch", "The approval does not match the request's order, purpose, amount, or terms version.")
    now = db_clock(db)
    req.status, req.decided_by, req.decided_at, req.decision_note = "approved", user.id, now, body.note
    req.approval_expires_at = now + timedelta(hours=APPROVAL_HOURS)
    _audit(db, order, user, "payment.approved", "payment_request", req.id, {"amount_paise": req.amount_paise})
    db.commit()
    return req


@router.post("/staff/payment-requests/{request_id}/reject", response_model=PaymentRequestOut, tags=["staff"])
def reject(request_id: uuid.UUID, body: DecisionNote, user: User = Depends(finance), db: Session = Depends(get_db)):
    order, req = _decide(db, request_id, user)
    req.status, req.decided_by, req.decided_at, req.decision_note = "rejected", user.id, db_clock(db), body.note
    _audit(db, order, user, "payment.rejected", "payment_request", req.id, {"note": body.note})
    db.commit()
    return req


@router.post("/staff/payment-requests/{request_id}/record", response_model=PaymentEventOut, status_code=201, tags=["staff"])
def record(request_id: uuid.UUID, response: Response, user: User = Depends(finance), db: Session = Depends(get_db)):
    order, req = _locked_request(db, request_id)
    if req.status == "recorded":  # replay: the one receipt for this request
        response.status_code = 200
        return db.scalar(select(PaymentEvent).where(PaymentEvent.request_id == req.id))
    if req.status != "approved":
        raise AppError(409, "invalid_transition", f"This request is {req.status}.", {"status": req.status})
    if db_clock(db) >= req.approval_expires_at:
        req.status = "expired"
        db.commit()
        raise AppError(409, "approval_expired", "The approval has expired. Ask for a new approval.")
    if order.status == "cancelled":
        raise AppError(409, "invalid_transition", "This order is cancelled.", {"status": order.status})
    _check_amount(view(db, order), req.purpose, req.amount_paise)
    event = PaymentEvent(order_id=order.id, kind="receipt", amount_paise=req.amount_paise, request_id=req.id, recorded_by=user.id)
    db.add(event)
    req.status = "recorded"
    db.flush()
    _audit(db, order, user, "payment.recorded", "payment_event", event.id, {"amount_paise": event.amount_paise})
    db.commit()
    return event


def _lapse(db: Session, rev: PaymentReversal) -> bool:
    """Save a pending reversal request whose deadline has passed (database clock) as expired."""
    if rev.status == "pending_approval" and db_clock(db) >= rev.expires_at:
        rev.status = "expired"
        db.flush()
    return rev.status == "expired"


@router.post("/staff/payment-events/{event_id}/reverse", response_model=PaymentReversalOut, status_code=201, tags=["staff"])
def request_reversal(event_id: uuid.UUID, body: ReversalIn, response: Response, user: User = Depends(finance), db: Session = Depends(get_db)):
    """Asks for a full reversal of one receipt. Nothing changes in the ledger until a different finance person approves."""
    order_id = db.scalar(select(PaymentEvent.order_id).where(PaymentEvent.id == event_id))
    if order_id is None:
        raise NOT_FOUND
    order = lock_order(db, order_id)
    receipt = db.get(PaymentEvent, event_id)
    if receipt.kind != "receipt":
        raise AppError(409, "invalid_transition", "Only a receipt can be reversed.", {"status": receipt.kind})
    if db.scalar(select(PaymentEvent.id).where(PaymentEvent.reverses_event_id == receipt.id)):
        raise AppError(409, "invalid_transition", "This receipt is already reversed.", {"status": "reversed"})
    pending = db.scalar(select(PaymentReversal).where(
        PaymentReversal.receipt_event_id == receipt.id, PaymentReversal.status == "pending_approval").with_for_update())
    if pending and not _lapse(db, pending):
        if (pending.requested_by, pending.reason) == (user.id, body.reason):
            response.status_code = 200  # a retry of the same request
            return pending
        raise AppError(409, "open_request_exists", "This receipt already has a pending reversal request.", {"request_id": str(pending.id)})
    rev = PaymentReversal(receipt_event_id=receipt.id, order_id=order.id, amount_paise=receipt.amount_paise, reason=body.reason,
                          requested_by=user.id, expires_at=db_clock(db) + timedelta(hours=APPROVAL_HOURS))
    db.add(rev)
    db.flush()
    _audit(db, order, user, "payment.reversal_requested", "payment_reversal", rev.id,
           {"receipt_event_id": str(receipt.id), "amount_paise": rev.amount_paise, "reason": body.reason})
    db.commit()
    return rev


@router.get("/staff/payment-reversals", response_model=list[PaymentReversalOut], tags=["staff"])
def reversal_queue(
    status: str = Query("pending_approval", pattern="^(pending_approval|executed|rejected|expired)$"),
    limit: int = Query(50, ge=1, le=100),
    _: User = Depends(finance),
    db: Session = Depends(get_db),
):
    now = db_clock(db)
    match status:
        case "pending_approval":
            where = and_(PaymentReversal.status == status, PaymentReversal.expires_at > now)
        case "expired":
            where = or_(PaymentReversal.status == status,
                        and_(PaymentReversal.status == "pending_approval", PaymentReversal.expires_at <= now))
        case _:
            where = PaymentReversal.status == status
    stmt = select(PaymentReversal).where(where).order_by(PaymentReversal.created_at, PaymentReversal.id)
    return db.scalars(stmt.limit(limit)).all()


def _locked_reversal(db: Session, reversal_id, user: User) -> tuple[Order, PaymentReversal]:
    order_id = db.scalar(select(PaymentReversal.order_id).where(PaymentReversal.id == reversal_id))
    if order_id is None:
        raise NOT_FOUND
    order = lock_order(db, order_id)
    rev = db.scalar(select(PaymentReversal).where(PaymentReversal.id == reversal_id).with_for_update().execution_options(populate_existing=True))
    if rev.requested_by == user.id:  # holds for every role combination, including the receipt's own approver or recorder
        raise AppError(403, "self_approval", "A different person must decide on this reversal.")
    return order, rev


@router.post("/staff/payment-reversals/{reversal_id}/approve", response_model=PaymentReversalOut, tags=["staff"])
def approve_reversal(reversal_id: uuid.UUID, body: ReversalApprovalIn, user: User = Depends(finance), db: Session = Depends(get_db)):
    order, rev = _locked_reversal(db, reversal_id, user)
    if rev.status == "executed":  # replay
        return rev
    if (body.order_id, body.receipt_event_id, body.amount_paise, body.reason) != (rev.order_id, rev.receipt_event_id, rev.amount_paise, rev.reason):
        raise AppError(409, "terms_mismatch", "The approval does not match the reversal's order, receipt, amount, or reason.")
    if _lapse(db, rev):
        db.commit()
        raise AppError(409, "approval_expired", "This reversal request has expired. Ask for a new one.")
    if rev.status != "pending_approval":
        raise AppError(409, "invalid_transition", f"This reversal request is {rev.status}.", {"status": rev.status})
    event = PaymentEvent(order_id=order.id, kind="reversal", amount_paise=rev.amount_paise,
                         reverses_event_id=rev.receipt_event_id, reason=rev.reason, recorded_by=user.id)
    db.add(event)
    db.flush()
    rev.status, rev.decided_by, rev.decided_at, rev.decision_note, rev.reversal_event_id = "executed", user.id, db_clock(db), body.note, event.id
    _audit(db, order, user, "payment.reversed", "payment_event", event.id,
           {"reversal_request_id": str(rev.id), "requested_by": str(rev.requested_by), "amount_paise": event.amount_paise, "reason": rev.reason})
    db.commit()
    return rev


@router.post("/staff/payment-reversals/{reversal_id}/reject", response_model=PaymentReversalOut, tags=["staff"])
def reject_reversal(reversal_id: uuid.UUID, body: DecisionNote, user: User = Depends(finance), db: Session = Depends(get_db)):
    order, rev = _locked_reversal(db, reversal_id, user)
    if _lapse(db, rev):
        db.commit()
    if rev.status != "pending_approval":
        raise AppError(409, "invalid_transition", f"This reversal request is {rev.status}.", {"status": rev.status})
    rev.status, rev.decided_by, rev.decided_at, rev.decision_note = "rejected", user.id, db_clock(db), body.note
    _audit(db, order, user, "payment.reversal_rejected", "payment_reversal", rev.id, {"note": body.note})
    db.commit()
    return rev
