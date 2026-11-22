import uuid

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import ValidationError
from sqlalchemy import and_, func, select, text, tuple_, update
from sqlalchemy.orm import Session, contains_eager

from app.audit import audit
from app.auth import Member, current_user, member
from app.db import get_db
from app.errors import AppError
from app.models import Membership, Organization, Product, StockMovement, User
from app.schemas import CatalogPage, CatalogProduct, ProductIn, ProductOut, ProductPatch, StockHistory, StockHistoryItem, StockIn, StockOut

router = APIRouter(prefix="/api/v1", tags=["catalog"])
CATALOG_EDITORS = ("admin", "catalog_manager")
NOT_FOUND = AppError(404, "not_found", "Not found.")


def _own_product(db: Session, org_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    product = db.scalar(select(Product).where(Product.id == product_id, Product.org_id == org_id))
    if product is None:
        raise NOT_FOUND
    return product


@router.get("/orgs/{org_id}/products", response_model=list[ProductOut], tags=["seller"])
def list_products(m: Member = Depends(member), db: Session = Depends(get_db)):
    return db.scalars(select(Product).where(Product.org_id == m.org.id).order_by(Product.name, Product.id)).all()


@router.post("/orgs/{org_id}/products", response_model=ProductOut, status_code=201, tags=["seller"])
def create_product(body: ProductIn, m: Member = Depends(member), db: Session = Depends(get_db)):
    m.require(CATALOG_EDITORS, "can_sell")
    product = Product(org_id=m.org.id, **body.model_dump())
    db.add(product)
    db.flush()
    audit(db, m.org.id, m.user.id, "product.created", "product", product.id, body.model_dump())
    db.commit()
    return product


@router.get("/orgs/{org_id}/products/{product_id}", response_model=ProductOut, tags=["seller"])
def get_product(product_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    return _own_product(db, m.org.id, product_id)


@router.patch("/orgs/{org_id}/products/{product_id}", response_model=ProductOut, tags=["seller"])
def patch_product(product_id: uuid.UUID, body: ProductPatch, m: Member = Depends(member), db: Session = Depends(get_db)):
    m.require(CATALOG_EDITORS, "can_sell")
    product = _own_product(db, m.org.id, product_id)
    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    current = ProductIn.model_validate(product, from_attributes=True).model_dump()
    try:
        merged = ProductIn.model_validate({**current, **changes}).model_dump()
    except ValidationError as e:
        raise AppError(400, "validation_error", "Some fields are missing or invalid.", [{"loc": err["loc"], "msg": err["msg"]} for err in e.errors()])
    updated = db.scalar(
        update(Product)
        .where(Product.id == product.id, Product.org_id == m.org.id, Product.version == body.version)
        .values(**merged, version=Product.version + 1, updated_at=func.now())
        .returning(Product)
        .execution_options(populate_existing=True)
    )
    if updated is None:
        raise AppError(409, "version_conflict", "This product was changed by someone else. Reload and try again.")
    audit(db, m.org.id, m.user.id, "product.updated", "product", product.id, {k: merged[k] for k in changes})
    db.commit()
    return updated


def _replay(db: Session, org_id, key: str, product_id, body: StockIn, response: Response) -> StockMovement | None:
    prior = db.scalar(select(StockMovement).where(StockMovement.org_id == org_id, StockMovement.idempotency_key == key))
    if prior is None:
        return None
    if (prior.product_id, prior.delta, prior.reason, prior.note) != (product_id, body.delta, body.reason, body.note):
        raise AppError(409, "idempotency_key_reused", "This Idempotency-Key was already used for a different request.")
    response.status_code = 200
    return prior


def change_stock(db: Session, org_id, product_id, delta: int, reason: str, note, actor_id, key: str, order_id=None) -> StockMovement:
    """Apply a stock change atomically; never lets available_qty go below zero. Caller commits."""
    _own_product(db, org_id, product_id)
    qty = db.scalar(
        update(Product)
        .where(Product.id == product_id, Product.org_id == org_id, Product.available_qty + delta >= 0)
        .values(available_qty=Product.available_qty + delta, version=Product.version + 1, updated_at=func.now())
        .returning(Product.available_qty)
    )
    if qty is None:
        raise AppError(409, "insufficient_stock", "Not enough stock for this change.")
    movement = StockMovement(
        org_id=org_id, product_id=product_id, delta=delta, reason=reason, note=note,
        resulting_qty=qty, actor_user_id=actor_id, idempotency_key=key, order_id=order_id,
    )
    db.add(movement)
    db.flush()
    return movement


def lock_idempotency_key(db: Session, org_id, key: str) -> None:
    """Make concurrent requests with the same organization/key wait until the first one commits or rolls back."""
    db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"{org_id}:{key}", 0))))


@router.post("/orgs/{org_id}/products/{product_id}/stock-adjustments", response_model=StockOut, status_code=201, tags=["seller"])
def adjust_stock(
    product_id: uuid.UUID,
    body: StockIn,
    response: Response,
    idempotency_key: str | None = Header(None, min_length=1, max_length=80),
    m: Member = Depends(member),
    db: Session = Depends(get_db),
):
    m.require(CATALOG_EDITORS, "can_sell")
    if not idempotency_key:
        raise AppError(400, "idempotency_key_required", "Send an Idempotency-Key header.")
    lock_idempotency_key(db, m.org.id, idempotency_key)
    if prior := _replay(db, m.org.id, idempotency_key, product_id, body, response):
        return prior
    movement = change_stock(db, m.org.id, product_id, body.delta, body.reason, body.note, m.user.id, idempotency_key)
    audit(db, m.org.id, m.user.id, "stock.adjusted", "product", product_id, body.model_dump() | {"resulting_qty": movement.resulting_qty})
    db.commit()
    return movement


@router.get("/orgs/{org_id}/products/{product_id}/stock-movements", response_model=StockHistory, tags=["seller"])
def stock_history(
    product_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    before: uuid.UUID | None = None,
    m: Member = Depends(member),
    db: Session = Depends(get_db),
):
    product = _own_product(db, m.org.id, product_id)
    # A name only for people in this organization; order movements were made by the buyer, so they show the order instead.
    stmt = (
        select(StockMovement, User.display_name.label("member_name"))
        .outerjoin(Membership, and_(Membership.user_id == StockMovement.actor_user_id, Membership.org_id == m.org.id))
        .outerjoin(User, User.id == Membership.user_id)
        .where(StockMovement.product_id == product.id, StockMovement.org_id == m.org.id)
    )
    if before is not None:
        anchor = db.scalar(select(StockMovement).where(StockMovement.id == before, StockMovement.product_id == product.id))
        if anchor is None:
            raise AppError(400, "validation_error", "before must be a movement of this product.")
        stmt = stmt.where(tuple_(StockMovement.created_at, StockMovement.id) < tuple_(anchor.created_at, anchor.id))
    rows = db.execute(stmt.order_by(StockMovement.created_at.desc(), StockMovement.id.desc()).limit(limit + 1)).all()
    items = [StockHistoryItem.model_validate(mv).model_copy(update={"actor_name": name}) for mv, name in rows[:limit]]
    return StockHistory(items=items, next_before=items[-1].id if len(rows) > limit else None)


def discoverable():
    return (
        select(Product)
        .join(Product.seller)
        .options(contains_eager(Product.seller))
        .where(Product.status == "active", Organization.can_sell)
    )


def search(db: Session, q=None, rating_amps=None, ways=None, city=None, quantity=None, max_price_paise=None, limit=20, offset=0):
    stmt = discoverable()
    if q:
        stmt = stmt.where(
            Product.name.icontains(q, autoescape=True) | Product.name_te.icontains(q, autoescape=True)
            | Product.brand.icontains(q, autoescape=True) | Product.model.icontains(q, autoescape=True)
        )
    if rating_amps:
        stmt = stmt.where(Product.rating_amps == rating_amps)
    if ways:
        stmt = stmt.where(Product.ways == ways)
    if city:
        stmt = stmt.where(text("EXISTS (SELECT 1 FROM unnest(products.delivery_cities) c WHERE lower(c) = lower(:city))").bindparams(city=city))
    if quantity:
        stmt = stmt.where(Product.available_qty >= quantity, Product.moq <= quantity)
    if max_price_paise:
        stmt = stmt.where(Product.price_paise <= max_price_paise)
    return db.scalars(stmt.order_by(Product.price_paise, Product.id).limit(limit).offset(offset)).all()


@router.get("/catalog/products", response_model=CatalogPage, tags=["discovery"])
def discover(
    q: str | None = Query(None, min_length=1, max_length=100),
    rating_amps: int | None = Query(None, gt=0),
    ways: int | None = Query(None, ge=1, le=2),
    city: str | None = Query(None, min_length=1, max_length=80),
    quantity: int | None = Query(None, ge=1),
    max_price_paise: int | None = Query(None, gt=0),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _=Depends(current_user),
    db: Session = Depends(get_db),
):
    filters = {"q": q, "rating_amps": rating_amps, "ways": ways, "city": city, "quantity": quantity, "max_price_paise": max_price_paise}
    items = search(db, **filters, limit=limit, offset=offset)
    return CatalogPage(
        items=[CatalogProduct.model_validate(p) for p in items],
        applied_filters={k: v for k, v in filters.items() if v is not None},
        limit=limit,
        offset=offset,
    )


@router.get("/catalog/products/{product_id}", response_model=CatalogProduct, tags=["discovery"])
def discover_one(product_id: uuid.UUID, _=Depends(current_user), db: Session = Depends(get_db)):
    product = db.scalar(discoverable().where(Product.id == product_id))
    if product is None:
        raise NOT_FOUND
    return product
