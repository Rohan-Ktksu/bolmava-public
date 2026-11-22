import uuid

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth import Member, member
from app.catalog import change_stock, discoverable, lock_idempotency_key
from app.db import get_db
from app.errors import AppError
from app.models import Order, Product, Quote, Rfq
from app.schemas import OrderIn, OrderOut, QuoteIn, QuoteOut, RfqDetail, RfqIn, RfqOut

router = APIRouter(prefix="/api/v1", tags=["trade"])
BUYERS = ("admin", "purchaser")
SELLERS = ("admin", "catalog_manager")
SIMULATED_TAX_BP = 1800
NOT_FOUND = AppError(404, "not_found", "Not found.")
# Product fields a quote's agreement is bound to; changing any of them needs a new quote version.
PRODUCT_TERMS = ("sku", "name", "name_te", "brand", "model", "rating_amps", "voltage_v", "ways", "unit", "pack_size")
# Lock order for every trade write: RFQ row, then quote row, then product stock row. Never the reverse.


def product_terms(product: Product) -> dict:
    return {k: getattr(product, k) for k in PRODUCT_TERMS}


def db_clock(db: Session):
    """Current database time. now() is frozen at transaction start, so it is stale after waiting for a lock."""
    return db.scalar(select(func.clock_timestamp()))


def tax_paise(taxable: int, bp: int) -> int:
    """Integer half-up rounding to whole paise."""
    return (taxable * bp + 5000) // 10000


def _invalid(message: str) -> AppError:
    return AppError(400, "validation_error", message)


def create_rfq(db: Session, m: Member, body: RfqIn, key: str) -> tuple[Rfq, bool]:
    """Shared by the form endpoint and the assistant's pending action. Returns (rfq, replayed). Caller commits."""
    m.require(BUYERS, "can_buy")
    lock_idempotency_key(db, m.org.id, key)
    prior = db.scalar(select(Rfq).where(Rfq.buyer_org_id == m.org.id, Rfq.idempotency_key == key))
    if prior:
        if {k: getattr(prior, k) for k in RfqIn.model_fields} != body.model_dump():
            raise AppError(409, "idempotency_key_reused", "This Idempotency-Key was already used for a different request.")
        return prior, True
    product = db.scalar(discoverable().where(Product.id == body.product_id))
    if product is None:
        raise NOT_FOUND
    if product.org_id == m.org.id:
        raise _invalid("You cannot request a quote from your own organization.")
    if body.quantity < product.moq:
        raise _invalid(f"Minimum order for this product is {product.moq} {product.unit}.")
    rfq = Rfq(buyer_org_id=m.org.id, seller_org_id=product.org_id, created_by=m.user.id, idempotency_key=key, **body.model_dump())
    db.add(rfq)
    db.flush()
    for org_id in (rfq.buyer_org_id, rfq.seller_org_id):
        audit(db, org_id, m.user.id, "rfq.created", "rfq", rfq.id, body.model_dump(mode="json"))
    return rfq, False


def _rfq(db: Session, org_id, rfq_id, *, as_seller=False, lock=False) -> Rfq:
    party = Rfq.seller_org_id == org_id if as_seller else or_(Rfq.buyer_org_id == org_id, Rfq.seller_org_id == org_id)
    stmt = select(Rfq).where(Rfq.id == rfq_id, party)
    rfq = db.scalar(stmt.with_for_update() if lock else stmt)
    if rfq is None:
        raise NOT_FOUND
    return rfq


def _visible_quote(db: Session, org_id, quote_id) -> Quote:
    """Both parties see sent and later quotes; drafts are private to the seller."""
    quote = db.scalar(
        select(Quote).join(Quote.rfq).where(
            Quote.id == quote_id,
            or_(Rfq.seller_org_id == org_id, (Rfq.buyer_org_id == org_id) & (Quote.status != "draft")),
        )
    )
    if quote is None:
        raise NOT_FOUND
    return quote


@router.post("/orgs/{org_id}/rfqs", response_model=RfqOut, status_code=201)
def post_rfq(
    body: RfqIn,
    response: Response,
    idempotency_key: str | None = Header(None, min_length=1, max_length=80),
    m: Member = Depends(member),
    db: Session = Depends(get_db),
):
    if not idempotency_key:
        raise AppError(400, "idempotency_key_required", "Send an Idempotency-Key header.")
    rfq, replayed = create_rfq(db, m, body, idempotency_key)
    if replayed:
        response.status_code = 200
    db.commit()
    return rfq


@router.get("/orgs/{org_id}/rfqs", response_model=list[RfqOut])
def list_rfqs(m: Member = Depends(member), db: Session = Depends(get_db)):
    party = or_(Rfq.buyer_org_id == m.org.id, Rfq.seller_org_id == m.org.id)
    return db.scalars(select(Rfq).where(party).order_by(Rfq.created_at.desc(), Rfq.id)).all()


@router.get("/orgs/{org_id}/rfqs/{rfq_id}", response_model=RfqDetail)
def get_rfq(rfq_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    rfq = _rfq(db, m.org.id, rfq_id)
    quotes = select(Quote).where(Quote.rfq_id == rfq.id).order_by(Quote.version)
    if rfq.seller_org_id != m.org.id:
        quotes = quotes.where(Quote.status != "draft")
    return RfqDetail(**RfqOut.model_validate(rfq).model_dump(), quotes=db.scalars(quotes).all())


@router.post("/orgs/{org_id}/rfqs/{rfq_id}/quotes", response_model=QuoteOut, status_code=201)
def create_quote(rfq_id: uuid.UUID, body: QuoteIn, m: Member = Depends(member), db: Session = Depends(get_db)):
    m.require(SELLERS, "can_sell")
    rfq = _rfq(db, m.org.id, rfq_id, as_seller=True, lock=True)  # lock serializes version numbering
    if rfq.status not in ("open", "quoted"):
        raise AppError(409, "conflict", f"This RFQ is {rfq.status}.")
    if body.valid_until <= db_clock(db):
        raise _invalid("valid_until must be in the future.")
    subtotal = rfq.quantity * body.unit_price_paise - body.discount_paise
    if subtotal <= 0:
        raise _invalid("The discount must be less than the quantity times the unit price.")
    tax = tax_paise(subtotal + body.freight_paise, SIMULATED_TAX_BP)
    total = subtotal + body.freight_paise + tax
    if body.advance_paise > total:
        raise _invalid("The advance cannot be more than the total.")
    version = (db.scalar(select(func.max(Quote.version)).where(Quote.rfq_id == rfq.id)) or 0) + 1
    quote = Quote(
        rfq_id=rfq.id, version=version, product_id=rfq.product_id, quantity=rfq.quantity, tax_bp=SIMULATED_TAX_BP,
        product_snapshot=product_terms(db.get(Product, rfq.product_id)),
        subtotal_paise=subtotal, tax_paise=tax, total_paise=total, created_by=m.user.id, **body.model_dump(),
    )
    db.add(quote)
    db.flush()
    audit(db, m.org.id, m.user.id, "quote.drafted", "quote", quote.id, {"version": version, "total_paise": total})
    db.commit()
    return quote


@router.post("/orgs/{org_id}/quotes/{quote_id}/send", response_model=QuoteOut)
def send_quote(quote_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    m.require(SELLERS, "can_sell")
    quote = _visible_quote(db, m.org.id, quote_id)
    rfq = _rfq(db, m.org.id, quote.rfq_id, as_seller=True, lock=True)
    db.refresh(quote)
    latest = db.scalar(select(func.max(Quote.version)).where(Quote.rfq_id == rfq.id))
    if quote.status != "draft" or quote.version != latest or rfq.status not in ("open", "quoted"):
        raise AppError(409, "quote_not_sendable", "Only the newest draft of an open RFQ can be sent.")
    if quote.valid_until <= db_clock(db):
        raise AppError(409, "quote_not_sendable", "This draft has already expired. Create a new version.")
    if product_terms(db.get(Product, quote.product_id)) != quote.product_snapshot:
        raise AppError(409, "quote_not_sendable", "The product details changed after this draft. Create a new version.")
    db.execute(update(Quote).where(Quote.rfq_id == rfq.id, Quote.status == "sent").values(status="superseded"))
    quote.status, quote.sent_at, rfq.status = "sent", func.now(), "quoted"
    for org_id in (rfq.buyer_org_id, rfq.seller_org_id):
        audit(db, org_id, m.user.id, "quote.sent", "quote", quote.id, {"version": quote.version, "total_paise": quote.total_paise})
    db.commit()
    db.refresh(quote)
    return quote


@router.get("/orgs/{org_id}/quotes/{quote_id}", response_model=QuoteOut)
def get_quote(quote_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    return _visible_quote(db, m.org.id, quote_id)


@router.post("/orgs/{org_id}/quotes/{quote_id}/reject", response_model=QuoteOut)
def reject_quote(quote_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    m.require(BUYERS, "can_buy")
    quote = _visible_quote(db, m.org.id, quote_id)
    rfq = _rfq(db, m.org.id, quote.rfq_id, lock=True)
    if rfq.buyer_org_id != m.org.id:
        raise NOT_FOUND
    db.refresh(quote)
    if quote.status != "sent":
        raise AppError(409, "conflict", f"This quote is {quote.status} and cannot be rejected.")
    quote.status, rfq.status = "rejected", "open"
    for org_id in (rfq.buyer_org_id, rfq.seller_org_id):
        audit(db, org_id, m.user.id, "quote.rejected", "quote", quote.id, {"version": quote.version})
    db.commit()
    return quote


def confirm_order(db: Session, m: Member, body: OrderIn, key: str) -> tuple[Order, bool]:
    """Turn the exact sent quote version into a simulated order once. Returns (order, replayed). Caller commits."""
    m.require(BUYERS, "can_buy")
    lock_idempotency_key(db, m.org.id, key)
    prior = db.scalar(select(Order).where(Order.buyer_org_id == m.org.id, Order.idempotency_key == key))
    if prior:
        if (prior.quote_id, prior.quote_version) != (body.quote_id, body.quote_version):
            raise AppError(409, "idempotency_key_reused", "This Idempotency-Key was already used for a different request.")
        return prior, True
    rfq_id = db.scalar(
        select(Quote.rfq_id).join(Quote.rfq)
        .where(Quote.id == body.quote_id, Rfq.buyer_org_id == m.org.id, Quote.status != "draft")
    )
    if rfq_id is None:
        raise NOT_FOUND
    rfq = _rfq(db, m.org.id, rfq_id, lock=True)  # serializes with send/reject and other confirmations
    quote = db.scalar(select(Quote).where(Quote.id == body.quote_id).with_for_update().execution_options(populate_existing=True))
    product = db.get(Product, quote.product_id)
    reason = (
        "already_accepted" if quote.status == "accepted"
        else "superseded" if quote.status == "superseded" or quote.version != body.quote_version
        else "not_sent" if quote.status != "sent"
        else "expired" if db_clock(db) >= quote.valid_until
        else "total_mismatch" if body.total_paise != quote.total_paise
        else "product_changed" if product_terms(product) != quote.product_snapshot
        else None
    )
    if reason:
        raise AppError(409, "quote_not_confirmable", f"This quote cannot be confirmed ({reason}).", {"reason": reason})
    money = {k: getattr(quote, k) for k in ("quantity", "unit_price_paise", "discount_paise", "freight_paise", "tax_bp", "subtotal_paise", "tax_paise", "total_paise", "advance_paise")}
    order = Order(
        quote_id=quote.id, quote_version=quote.version, buyer_org_id=rfq.buyer_org_id, seller_org_id=rfq.seller_org_id,
        product_id=product.id, product_snapshot=quote.product_snapshot, confirmed_by=m.user.id, idempotency_key=key, **money,
    )
    db.add(order)
    db.flush()
    change_stock(db, rfq.seller_org_id, product.id, -quote.quantity, "order", None, m.user.id, f"order:{quote.id}", order_id=order.id)
    if db_clock(db) >= quote.valid_until:  # the stock row lock can also wait; recheck before the caller commits
        raise AppError(409, "quote_not_confirmable", "This quote cannot be confirmed (expired).", {"reason": "expired"})
    quote.status, rfq.status = "accepted", "closed"
    for org_id in (rfq.buyer_org_id, rfq.seller_org_id):
        audit(db, org_id, m.user.id, "order.confirmed", "order", order.id, {"quote_id": str(quote.id), "version": quote.version, "total_paise": quote.total_paise})
    return order, False


@router.post("/orgs/{org_id}/orders", response_model=OrderOut, status_code=201)
def post_order(
    body: OrderIn,
    response: Response,
    idempotency_key: str | None = Header(None, min_length=1, max_length=80),
    m: Member = Depends(member),
    db: Session = Depends(get_db),
):
    if not idempotency_key:
        raise AppError(400, "idempotency_key_required", "Send an Idempotency-Key header.")
    order, replayed = confirm_order(db, m, body, idempotency_key)
    if replayed:
        response.status_code = 200
    db.commit()
    return order


@router.get("/orgs/{org_id}/orders", response_model=list[OrderOut])
def list_orders(m: Member = Depends(member), db: Session = Depends(get_db)):
    party = or_(Order.buyer_org_id == m.org.id, Order.seller_org_id == m.org.id)
    return db.scalars(select(Order).where(party).order_by(Order.created_at.desc(), Order.id)).all()


@router.get("/orgs/{org_id}/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    party = or_(Order.buyer_org_id == m.org.id, Order.seller_org_id == m.org.id)
    order = db.scalar(select(Order).where(Order.id == order_id, party))
    if order is None:
        raise NOT_FOUND
    return order
