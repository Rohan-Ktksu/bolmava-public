import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    MetaData,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase, Mapped, column_property, mapped_column, relationship

ROLES = ("admin", "catalog_manager", "purchaser", "viewer")
FULFILLMENT = ("pending", "dispatched", "delivered", "accepted")


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    type_annotation_map = {datetime: DateTime(timezone=True)}


def _org_name(org_id):
    """Read-only name for display. A select-list subquery, so FOR UPDATE on the parent row locks no other table."""
    return column_property(select(Organization.name).where(Organization.id == org_id).scalar_subquery())


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254))
    display_name: Mapped[str] = mapped_column(String(120))
    preferred_language: Mapped[str] = mapped_column(String(2), default="te")
    is_fictional: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("uq_users_email_lower", func.lower(email), unique=True),
        CheckConstraint(_in("preferred_language", ("te", "en")), name="language"),
    )


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160))
    city: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(80))
    can_sell: Mapped[bool]
    can_buy: Mapped[bool]
    verification_status: Mapped[str] = mapped_column(String(32), default="simulated_unverified")
    is_fictional: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Who registered it and their Idempotency-Key, so a retried registration returns the same organization (F05).
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(80))

    __table_args__ = (
        UniqueConstraint("created_by", "idempotency_key"),
        CheckConstraint("can_sell OR can_buy", name="capability"),
        CheckConstraint(
            _in("verification_status", ("simulated_unverified", "simulated_verified")),
            name="verification_status",
        ),
    )


class Membership(Base):
    __tablename__ = "memberships"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint("org_id", "user_id"),
        CheckConstraint(_in("role", ROLES), name="role"),
    )


class Product(Base):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    sku: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    name_te: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40), default="electrical_switch")
    brand: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    rating_amps: Mapped[int] = mapped_column(SmallInteger)
    voltage_v: Mapped[int] = mapped_column(SmallInteger)
    ways: Mapped[int] = mapped_column(SmallInteger)
    unit: Mapped[str] = mapped_column(String(16))
    pack_size: Mapped[int]
    moq: Mapped[int]
    price_paise: Mapped[int] = mapped_column(BigInteger)
    available_qty: Mapped[int] = mapped_column(default=0)
    lead_time_days: Mapped[int] = mapped_column(SmallInteger)
    delivery_cities: Mapped[list[str]] = mapped_column(ARRAY(String(80)), default=list)
    status: Mapped[str] = mapped_column(String(16), default="active")
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    seller: Mapped[Organization] = relationship(lazy="raise")

    __table_args__ = (
        UniqueConstraint("org_id", "sku"),
        Index("ix_products_discovery", "status", "price_paise"),
        CheckConstraint("category = 'electrical_switch'", name="category"),
        CheckConstraint("rating_amps > 0", name="rating_amps"),
        CheckConstraint("voltage_v > 0", name="voltage_v"),
        CheckConstraint("ways IN (1, 2)", name="ways"),
        CheckConstraint(_in("unit", ("piece", "box")), name="unit"),
        CheckConstraint("pack_size >= 1 AND (unit <> 'piece' OR pack_size = 1)", name="pack_size"),
        CheckConstraint("moq >= 1", name="moq"),
        CheckConstraint("price_paise > 0 AND price_paise <= 1000000000000", name="price_paise"),
        CheckConstraint("available_qty >= 0", name="available_qty"),
        CheckConstraint("lead_time_days >= 0", name="lead_time_days"),
        CheckConstraint(_in("status", ("active", "inactive")), name="status"),
        CheckConstraint("version >= 1", name="version"),
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    delta: Mapped[int]
    reason: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(200))
    resulting_qty: Mapped[int]
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(80))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint("org_id", "idempotency_key"),
        CheckConstraint("delta <> 0", name="delta"),
        CheckConstraint("resulting_qty >= 0", name="resulting_qty"),
        CheckConstraint(
            _in("reason", ("restock", "correction", "damage", "order", "order_cancel")), name="reason"
        ),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID]
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Rfq(Base):
    __tablename__ = "rfqs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    buyer_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    seller_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    delivery_city: Mapped[str] = mapped_column(String(80))
    needed_by: Mapped[date | None]
    note: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Null only for RFQs created before migration 0008.
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    product: Mapped[Product] = relationship(lazy="raise")
    buyer_org_name = _org_name(buyer_org_id)
    seller_org_name = _org_name(seller_org_id)
    product_name = column_property(select(Product.name).where(Product.id == product_id).scalar_subquery())
    product_name_te = column_property(select(Product.name_te).where(Product.id == product_id).scalar_subquery())
    product_unit = column_property(select(Product.unit).where(Product.id == product_id).scalar_subquery())

    __table_args__ = (
        CheckConstraint("buyer_org_id <> seller_org_id", name="distinct_orgs"),
        UniqueConstraint("buyer_org_id", "idempotency_key"),
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint(_in("status", ("open", "quoted", "closed", "cancelled")), name="status"),
    )


class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rfq_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rfqs.id"))
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default="draft")
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    unit_price_paise: Mapped[int] = mapped_column(BigInteger)
    discount_paise: Mapped[int] = mapped_column(BigInteger)
    freight_paise: Mapped[int] = mapped_column(BigInteger)
    tax_bp: Mapped[int] = mapped_column(SmallInteger)
    subtotal_paise: Mapped[int] = mapped_column(BigInteger)
    tax_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    advance_paise: Mapped[int] = mapped_column(BigInteger)
    valid_until: Mapped[datetime]
    product_snapshot: Mapped[dict] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    rfq: Mapped[Rfq] = relationship(lazy="raise")

    __table_args__ = (
        UniqueConstraint("rfq_id", "version"),
        Index("uq_quotes_one_sent_per_rfq", "rfq_id", unique=True, postgresql_where=text("status = 'sent'")),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(
            _in("status", ("draft", "sent", "accepted", "rejected", "expired", "superseded")), name="status"
        ),
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint("unit_price_paise > 0", name="unit_price"),
        CheckConstraint("discount_paise >= 0 AND freight_paise >= 0 AND tax_paise >= 0", name="non_negative"),
        CheckConstraint("tax_bp BETWEEN 0 AND 10000", name="tax_bp"),
        CheckConstraint("subtotal_paise = quantity * unit_price_paise - discount_paise AND subtotal_paise > 0", name="subtotal"),
        CheckConstraint("total_paise = subtotal_paise + freight_paise + tax_paise", name="total"),
        CheckConstraint("advance_paise BETWEEN 0 AND total_paise", name="advance"),
    )


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    quote_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quotes.id"), unique=True)
    quote_version: Mapped[int]
    buyer_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    seller_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    product_snapshot: Mapped[dict] = mapped_column(JSONB)
    quantity: Mapped[int]
    unit_price_paise: Mapped[int] = mapped_column(BigInteger)
    discount_paise: Mapped[int] = mapped_column(BigInteger)
    freight_paise: Mapped[int] = mapped_column(BigInteger)
    tax_bp: Mapped[int] = mapped_column(SmallInteger)
    subtotal_paise: Mapped[int] = mapped_column(BigInteger)
    tax_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    advance_paise: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="confirmed")
    fulfillment_status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    confirmed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    buyer_org_name = _org_name(buyer_org_id)
    seller_org_name = _org_name(seller_org_id)

    __table_args__ = (
        UniqueConstraint("buyer_org_id", "idempotency_key"),
        CheckConstraint(_in("status", ("confirmed", "cancelled", "completed")), name="status"),
        CheckConstraint(_in("fulfillment_status", FULFILLMENT), name="fulfillment_status"),
        CheckConstraint("total_paise = subtotal_paise + freight_paise + tax_paise", name="total"),
    )


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(16), default="web")
    language: Mapped[str] = mapped_column(String(2))
    state: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_conversations_owner", "org_id", "user_id"),
        CheckConstraint("channel = 'web'", name="channel"),
        CheckConstraint(_in("language", ("te", "en")), name="language"),
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(String(2000))
    idempotency_key: Mapped[str | None] = mapped_column(String(80))  # user messages only; retries of one send
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint(_in("role", ("user", "assistant", "agent")), name="role"),
        UniqueConstraint("conversation_id", "idempotency_key"),
    )


class PendingAction(Base):
    __tablename__ = "pending_actions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB)
    expires_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(16), default="pending")
    result_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint(_in("action", ("create_rfq", "confirm_order")), name="action"),
        CheckConstraint(_in("status", ("pending", "confirmed", "expired", "cancelled")), name="status"),
    )


class StaffGrant(Base):
    __tablename__ = "staff_grants"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    revoked_at: Mapped[datetime | None]

    __table_args__ = (
        Index("uq_staff_grants_active", "user_id", "role", unique=True, postgresql_where=text("revoked_at IS NULL")),
        CheckConstraint(_in("role", ("finance", "support")), name="role"),
    )


class PaymentRequest(Base):
    __tablename__ = "payment_requests"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(16))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    quote_version: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default="pending_approval")
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None]
    decision_note: Mapped[str | None] = mapped_column(String(500))
    approval_expires_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("uq_payment_requests_one_open", "order_id", unique=True,
              postgresql_where=text("status IN ('pending_approval', 'approved')")),
        CheckConstraint(_in("purpose", ("advance", "balance")), name="purpose"),
        CheckConstraint("currency = 'INR'", name="currency"),
        CheckConstraint("amount_paise > 0", name="amount"),
        CheckConstraint(
            _in("status", ("pending_approval", "approved", "rejected", "recorded", "expired", "cancelled")), name="status"
        ),
        CheckConstraint("decided_by <> requested_by", name="maker_checker"),
    )


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payment_requests.id"), unique=True)
    reverses_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payment_events.id"), unique=True)
    reason: Mapped[str | None] = mapped_column(String(500))
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="amount"),
        CheckConstraint(
            "(kind = 'receipt' AND request_id IS NOT NULL AND reverses_event_id IS NULL)"
            " OR (kind = 'reversal' AND reverses_event_id IS NOT NULL AND request_id IS NULL)",
            name="kind",
        ),
    )


class PaymentReversal(Base):
    """A requested full reversal of one receipt; a distinct finance person's approval inserts the reversal event."""
    __tablename__ = "payment_reversals"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    receipt_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_events.id"), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="pending_approval")
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None]
    decision_note: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime]
    reversal_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payment_events.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("uq_payment_reversals_one_pending", "receipt_event_id", unique=True,
              postgresql_where=text("status = 'pending_approval'")),
        CheckConstraint("currency = 'INR'", name="currency"),
        CheckConstraint("amount_paise > 0", name="amount"),
        CheckConstraint(_in("status", ("pending_approval", "executed", "rejected", "expired")), name="status"),
        CheckConstraint("decided_by <> requested_by", name="maker_checker"),
        CheckConstraint("(status = 'executed') = (reversal_event_id IS NOT NULL)", name="executed_event"),
    )


class FulfillmentEvent(Base):
    __tablename__ = "fulfillment_events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (CheckConstraint(_in("status", FULFILLMENT[1:] + ("cancelled",)), name="status"),)


CASE_CATEGORIES = ("damaged", "wrong_product", "missing_quantity", "delay", "quality", "payment", "other")
URGENCY = ("low", "normal", "high")


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    buyer_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    seller_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    category: Mapped[str] = mapped_column(String(24))
    description: Mapped[str] = mapped_column(String(2000))
    urgency: Mapped[str] = mapped_column(String(8), default="normal")
    status: Mapped[str] = mapped_column(String(16), default="open")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolution: Mapped[str | None] = mapped_column(String(2000))
    reopen_count: Mapped[int] = mapped_column(default=0)
    opened_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint(_in("category", CASE_CATEGORIES), name="category"),
        CheckConstraint(_in("urgency", URGENCY), name="urgency"),
        CheckConstraint(_in("status", ("open", "assigned", "investigating", "resolved", "closed")), name="status"),
        CheckConstraint("status IN ('open', 'resolved', 'closed') OR assigned_to IS NOT NULL", name="assignee"),
        CheckConstraint("status NOT IN ('resolved', 'closed') OR resolution IS NOT NULL", name="resolution"),
    )


class CaseUpdate(Base):
    __tablename__ = "case_updates"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    visibility: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (CheckConstraint(_in("visibility", ("parties", "internal")), name="visibility"),)


class CaseEvidence(Base):
    __tablename__ = "case_evidence"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    added_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint("size_bytes > 0 AND size_bytes <= 20971520", name="size"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
    )


class Handoff(Base):
    __tablename__ = "handoffs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"))
    urgency: Mapped[str] = mapped_column(String(8), default="normal")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    cancelled_actions: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    assigned_at: Mapped[datetime | None]
    released_at: Mapped[datetime | None]

    __table_args__ = (
        Index("uq_handoffs_one_active", "conversation_id", unique=True, postgresql_where=text("status IN ('queued', 'assigned')")),
        CheckConstraint(_in("urgency", URGENCY), name="urgency"),
        CheckConstraint(_in("status", ("queued", "assigned", "released")), name="status"),
        CheckConstraint("status = 'queued' OR assigned_to IS NOT NULL", name="assignee"),
    )
