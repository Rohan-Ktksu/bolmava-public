"""Order fulfillment and pre-dispatch cancellation. Separate from simulated payments: nothing here records money."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth import Member, member
from app.catalog import change_stock
from app.db import get_db
from app.errors import AppError
from app.models import FulfillmentEvent, Order, PaymentRequest
from app.payments import OPEN, lock_order
from app.schemas import CancelIn, FulfillmentEventOut, FulfillmentIn, OrderOut
from app.trade import BUYERS, SELLERS

router = APIRouter(prefix="/api/v1", tags=["fulfillment"])

# action -> (side allowed: roles, required current status, resulting status)
ACTIONS = {
    "dispatch": ({"seller": SELLERS}, "pending", "dispatched"),
    "deliver": ({"seller": SELLERS, "buyer": BUYERS}, "dispatched", "delivered"),
    "accept": ({"buyer": BUYERS}, "delivered", "accepted"),
}


def _party_order(db: Session, m: Member, order_id) -> tuple[Order, str]:
    order = lock_order(db, order_id, or_(Order.buyer_org_id == m.org.id, Order.seller_org_id == m.org.id))
    return order, "seller" if order.seller_org_id == m.org.id else "buyer"


def _event(db: Session, order: Order, m: Member, status: str, note) -> None:
    db.add(FulfillmentEvent(order_id=order.id, status=status, actor_user_id=m.user.id, note=note))
    for org_id in (order.buyer_org_id, order.seller_org_id):
        audit(db, org_id, m.user.id, f"order.{status}", "order", order.id, {"note": note})


@router.post("/orgs/{org_id}/orders/{order_id}/fulfillment", response_model=OrderOut)
def fulfil(order_id: uuid.UUID, body: FulfillmentIn, m: Member = Depends(member), db: Session = Depends(get_db)):
    order, side = _party_order(db, m, order_id)
    allowed, required, result = ACTIONS[body.action]
    m.require(allowed.get(side, ()))
    if order.fulfillment_status == result and order.status != "cancelled":
        return order  # repeated request: already applied
    if order.status != "confirmed" or order.fulfillment_status != required:
        status = "cancelled" if order.status == "cancelled" else order.fulfillment_status
        raise AppError(409, "invalid_transition", f"This order is {status}.", {"status": status})
    order.fulfillment_status = result
    if result == "accepted":
        order.status = "completed"
    _event(db, order, m, result, body.note)
    db.commit()
    return order


@router.post("/orgs/{org_id}/orders/{order_id}/cancel", response_model=OrderOut)
def cancel(order_id: uuid.UUID, body: CancelIn, m: Member = Depends(member), db: Session = Depends(get_db)):
    order, side = _party_order(db, m, order_id)
    m.require(BUYERS if side == "buyer" else ("admin",))
    if order.status == "cancelled":
        return order  # repeated request: stock was restored once already
    if order.status != "confirmed" or order.fulfillment_status != "pending":
        raise AppError(409, "invalid_transition", "Only an order that has not been dispatched can be cancelled.",
                       {"status": order.fulfillment_status if order.status == "confirmed" else order.status})
    # Order row is locked; the stock row is locked last. The unique key restores stock at most once.
    change_stock(db, order.seller_org_id, order.product_id, order.quantity, "order_cancel", body.reason, m.user.id,
                 f"order-cancel:{order.id}", order_id=order.id)
    db.execute(update(PaymentRequest).where(PaymentRequest.order_id == order.id, PaymentRequest.status.in_(OPEN)).values(status="cancelled"))
    order.status = "cancelled"
    _event(db, order, m, "cancelled", body.reason)
    db.commit()
    return order


@router.get("/orgs/{org_id}/orders/{order_id}/fulfillment-events", response_model=list[FulfillmentEventOut])
def events(order_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    party = or_(Order.buyer_org_id == m.org.id, Order.seller_org_id == m.org.id)
    if db.scalar(select(Order.id).where(Order.id == order_id, party)) is None:
        raise AppError(404, "not_found", "Not found.")
    return db.scalars(select(FulfillmentEvent).where(FulfillmentEvent.order_id == order_id).order_by(FulfillmentEvent.created_at)).all()
