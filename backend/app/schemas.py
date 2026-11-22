import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = lambda n: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=n)]  # noqa: E731


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LocalUser(Out):
    email: str
    display_name: str
    preferred_language: str


class LocalSessionIn(BaseModel):
    email: Text(254)


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class OrgIn(BaseModel):
    name: Text(160)
    city: Text(80)
    state: Text(80)
    can_sell: bool
    can_buy: bool

    @model_validator(mode="after")
    def capability(self):
        if not (self.can_sell or self.can_buy):
            raise ValueError("an organization must be able to sell, buy, or both")
        return self


class OrgOut(Out):
    id: uuid.UUID
    name: str
    city: str
    state: str
    can_sell: bool
    can_buy: bool
    verification_status: str
    is_fictional: bool
    created_at: datetime


class MembershipOut(BaseModel):
    role: str
    organization: OrgOut


class MeOut(Out):
    id: uuid.UUID
    email: str
    display_name: str
    preferred_language: str
    memberships: list[MembershipOut]
    staff_roles: list[str]


class ProductIn(BaseModel):
    sku: Text(64)
    name: Text(200)
    name_te: Text(200) | None = None
    brand: Text(80)
    model: Text(80)
    rating_amps: int = Field(gt=0, le=1000)
    voltage_v: int = Field(gt=0, le=1000)
    ways: Literal[1, 2]
    unit: Literal["piece", "box"]
    pack_size: int = Field(ge=1, le=100_000)
    moq: int = Field(ge=1, le=1_000_000)
    price_paise: int = Field(gt=0, le=10**12)
    lead_time_days: int = Field(ge=0, le=365)
    delivery_cities: list[Text(80)] = Field(default_factory=list, max_length=50)
    status: Literal["active", "inactive"] = "active"

    @model_validator(mode="after")
    def piece_is_single(self):
        if self.unit == "piece" and self.pack_size != 1:
            raise ValueError("pack_size must be 1 when unit is piece")
        return self


class ProductPatch(BaseModel):
    version: int = Field(ge=1)
    sku: str | None = None
    name: str | None = None
    name_te: str | None = None
    brand: str | None = None
    model: str | None = None
    rating_amps: int | None = None
    voltage_v: int | None = None
    ways: int | None = None
    unit: str | None = None
    pack_size: int | None = None
    moq: int | None = None
    price_paise: int | None = None
    lead_time_days: int | None = None
    delivery_cities: list[str] | None = None
    status: str | None = None


class ProductOut(Out, ProductIn):
    id: uuid.UUID
    org_id: uuid.UUID
    category: str
    available_qty: int
    version: int
    created_at: datetime
    updated_at: datetime


class StockIn(BaseModel):
    delta: int = Field(ge=-1_000_000, le=1_000_000)
    reason: Literal["restock", "correction", "damage"]
    note: Text(200) | None = None

    @model_validator(mode="after")
    def nonzero(self):
        if self.delta == 0:
            raise ValueError("delta must not be zero")
        return self


class StockOut(Out):
    id: uuid.UUID
    product_id: uuid.UUID
    delta: int
    reason: str
    note: str | None
    resulting_qty: int
    created_at: datetime


class StockHistoryItem(Out):
    id: uuid.UUID
    delta: int
    reason: str
    note: str | None
    resulting_qty: int
    created_at: datetime
    order_id: uuid.UUID | None
    actor_name: str | None = None


class StockHistory(BaseModel):
    items: list[StockHistoryItem]
    next_before: uuid.UUID | None


class SellerOut(Out):
    id: uuid.UUID
    name: str
    city: str
    verification_status: str


class CatalogProduct(Out, ProductIn):
    id: uuid.UUID
    category: str
    available_qty: int
    seller: SellerOut


class CatalogPage(BaseModel):
    items: list[CatalogProduct]
    applied_filters: dict
    limit: int
    offset: int


class RfqIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=1_000_000)
    delivery_city: Text(80)
    needed_by: date | None = None
    note: Text(500) | None = None


class QuoteIn(BaseModel):
    unit_price_paise: int = Field(gt=0, le=10**12)
    discount_paise: int = Field(0, ge=0, le=10**15)
    freight_paise: int = Field(0, ge=0, le=10**12)
    advance_paise: int = Field(0, ge=0, le=10**16)
    valid_until: AwareDatetime


class QuoteOut(Out):
    id: uuid.UUID
    rfq_id: uuid.UUID
    version: int
    status: str
    product_id: uuid.UUID
    quantity: int
    unit_price_paise: int
    discount_paise: int
    freight_paise: int
    tax_bp: int
    subtotal_paise: int
    tax_paise: int
    total_paise: int
    advance_paise: int
    valid_until: datetime
    product_snapshot: dict
    sent_at: datetime | None
    created_at: datetime
    simulated: bool = True

    @model_validator(mode="after")
    def report_expiry(self):
        if self.status == "sent" and self.valid_until <= datetime.now(UTC):
            self.status = "expired"
        return self


class RfqOut(Out):
    id: uuid.UUID
    buyer_org_id: uuid.UUID
    seller_org_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    delivery_city: str
    needed_by: date | None
    note: str | None
    status: str
    created_at: datetime
    buyer_org_name: str
    seller_org_name: str
    product_name: str
    product_name_te: str | None
    product_unit: str


class RfqDetail(RfqOut):
    quotes: list[QuoteOut]


class OrderIn(BaseModel):
    quote_id: uuid.UUID
    quote_version: int = Field(ge=1)
    total_paise: int = Field(gt=0)


class OrderOut(Out):
    id: uuid.UUID
    quote_id: uuid.UUID
    quote_version: int
    buyer_org_id: uuid.UUID
    seller_org_id: uuid.UUID
    product_id: uuid.UUID
    product_snapshot: dict
    quantity: int
    unit_price_paise: int
    discount_paise: int
    freight_paise: int
    tax_bp: int
    subtotal_paise: int
    tax_paise: int
    total_paise: int
    advance_paise: int
    status: str
    fulfillment_status: str
    confirmed_by: uuid.UUID
    created_at: datetime
    buyer_org_name: str
    seller_org_name: str
    simulated: bool = True


class ConversationOut(Out):
    id: uuid.UUID
    language: str
    created_at: datetime
    # From the conversation's latest handoff (any status), filled in the owner's list (F06): the complaint it was
    # about and queued|assigned|released, so a complaint can lead back to its support chat even after hand-back.
    support_case_id: uuid.UUID | None = None
    support_status: str | None = None


class MessageIn(BaseModel):
    text: Text(1000)


class PendingOut(Out):
    id: uuid.UUID
    action: str
    payload: dict
    expires_at: datetime


class AssistantReply(BaseModel):
    reply: str
    pending_action: PendingOut | None


class PendingResult(BaseModel):
    action: str
    rfq: RfqOut | None = None
    order: OrderOut | None = None


class PaymentRequestIn(BaseModel):
    purpose: Literal["advance", "balance"]
    amount_paise: int = Field(gt=0, le=10**16)
    quote_version: int = Field(ge=1)


class ApprovalIn(PaymentRequestIn):
    order_id: uuid.UUID
    note: Text(500) | None = None


class DecisionNote(BaseModel):
    note: Text(500)


class ReversalIn(BaseModel):
    reason: Text(500)


class PaymentRequestOut(Out):
    id: uuid.UUID
    order_id: uuid.UUID
    purpose: str
    amount_paise: int
    currency: str
    quote_version: int
    status: str
    requested_by: uuid.UUID
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    approval_expires_at: datetime | None
    created_at: datetime
    simulated: bool = True

    @model_validator(mode="after")
    def report_expiry(self):
        if self.status == "approved" and self.approval_expires_at <= datetime.now(UTC):
            self.status = "expired"
        return self


class PaymentEventOut(Out):
    id: uuid.UUID
    order_id: uuid.UUID
    kind: str
    amount_paise: int
    request_id: uuid.UUID | None
    reverses_event_id: uuid.UUID | None
    reason: str | None
    recorded_by: uuid.UUID
    created_at: datetime
    simulated: bool = True


class ReversalApprovalIn(BaseModel):
    order_id: uuid.UUID
    receipt_event_id: uuid.UUID
    amount_paise: int
    reason: Text(500)
    note: Text(500) | None = None


class PaymentReversalOut(Out):
    id: uuid.UUID
    receipt_event_id: uuid.UUID
    order_id: uuid.UUID
    amount_paise: int
    currency: str
    reason: str
    status: str
    requested_by: uuid.UUID
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    expires_at: datetime
    reversal_event_id: uuid.UUID | None
    created_at: datetime
    simulated: bool = True

    @model_validator(mode="after")
    def report_expiry(self):
        if self.status == "pending_approval" and self.expires_at <= datetime.now(UTC):
            self.status = "expired"
        return self


class PaymentsView(BaseModel):
    order_id: uuid.UUID
    order_status: str
    total_paise: int
    advance_paise: int
    received_paise: int
    outstanding_paise: int
    refund_due_paise: int
    requests: list[PaymentRequestOut]
    events: list[PaymentEventOut]
    simulated: bool = True


class FulfillmentIn(BaseModel):
    action: Literal["dispatch", "deliver", "accept"]
    note: Text(500) | None = None


class CancelIn(BaseModel):
    reason: Text(500)


class FulfillmentEventOut(Out):
    id: uuid.UUID
    order_id: uuid.UUID
    status: str
    actor_user_id: uuid.UUID
    note: str | None
    created_at: datetime


class CaseIn(BaseModel):
    category: Literal["damaged", "wrong_product", "missing_quantity", "delay", "quality", "payment", "other"]
    description: Text(2000)
    urgency: Literal["low", "normal", "high"] = "normal"


class CaseOut(Out):
    id: uuid.UUID
    order_id: uuid.UUID
    buyer_org_id: uuid.UUID
    seller_org_id: uuid.UUID
    category: str
    description: str
    urgency: str
    status: str
    assigned_to: uuid.UUID | None
    resolution: str | None
    reopen_count: int
    opened_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CaseQueueItem(Out):
    """What any support staff may see before taking a case."""
    id: uuid.UUID
    category: str
    urgency: str
    status: str
    created_at: datetime


class UpdateIn(BaseModel):
    body: Text(2000)


class StaffUpdateIn(UpdateIn):
    visibility: Literal["parties", "internal"] = "parties"


class ResolveIn(BaseModel):
    resolution: Text(2000)


class CaseUpdateOut(Out):
    id: uuid.UUID
    author_id: uuid.UUID
    visibility: str
    body: str
    created_at: datetime


class EvidenceIn(BaseModel):
    filename: Text(200)
    content_type: Text(100)
    size_bytes: int = Field(gt=0, le=20 * 1024 * 1024)
    sha256: Annotated[str, StringConstraints(pattern="^[0-9a-f]{64}$")]
    description: Text(500) | None = None


class EvidenceOut(Out):
    id: uuid.UUID
    added_by: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    description: str | None
    created_at: datetime


class CaseDetail(CaseOut):
    updates: list[CaseUpdateOut]
    evidence: list[EvidenceOut]


class HandoffIn(BaseModel):
    urgency: Literal["low", "normal", "high"] = "normal"
    case_id: uuid.UUID | None = None


class HandoffOut(Out):
    id: uuid.UUID
    conversation_id: uuid.UUID
    case_id: uuid.UUID | None
    urgency: str
    status: str
    assigned_to: uuid.UUID | None
    created_at: datetime
    assigned_at: datetime | None
    released_at: datetime | None



class ConversationDetail(ConversationOut):
    handoff: HandoffOut | None  # the active (queued|assigned) one; null after release
    pending_action: PendingOut | None

class HandoffQueueItem(Out):
    id: uuid.UUID
    urgency: str
    status: str
    created_at: datetime
    # F06: set only for the support person who holds the linked complaint; null for everyone else.
    your_case_id: uuid.UUID | None = None


class MessageOut(Out):
    id: int
    role: str
    text: str
    created_at: datetime


class HandoffSummary(HandoffOut):
    requester_name: str
    language: str
    organization_name: str
    recent_messages: list[MessageOut]
    case: CaseOut | None
    order_status: str | None
    cancelled_actions: list[str]


class TradeTotals(BaseModel):
    orders: int
    order_value_paise: int
    cancelled_orders: int
    received_paise: int
    outstanding_paise: int
    refund_due_paise: int
    awaiting_approval_paise: int
    approved_unrecorded_paise: int


class DelayedOrder(BaseModel):
    order_id: uuid.UUID
    side: Literal["sales", "purchases"]
    fulfillment_status: str
    created_at: datetime


class ReportOut(BaseModel):
    org_id: uuid.UUID
    from_date: date
    to_date: date
    period_start_utc: datetime
    period_end_utc: datetime
    sales: TradeTotals
    purchases: TradeTotals
    open_cases: int
    delayed_orders_count: int
    delayed_orders: list[DelayedOrder]
    simulated: bool = True
