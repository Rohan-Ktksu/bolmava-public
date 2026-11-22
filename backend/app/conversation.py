"""Deterministic assistant: keyword and number matching only, no model or API key. Every value comes from the database."""
import copy
import re
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app import events
from app.auth import Member, member
from app.catalog import discoverable, search
from app.db import get_db
from app.errors import AppError
from app import reports
from app.audit import audit
from app.models import Case, Conversation, Handoff, Message, Order, Organization, PendingAction, Product, Quote, Rfq
from app.schemas import (
    AssistantReply, ConversationDetail, ConversationOut, HandoffIn, HandoffOut, MessageIn, MessageOut, OrderIn, PendingResult, RfqIn, RfqOut,
)
from app.trade import confirm_order, create_rfq, db_clock

router = APIRouter(prefix="/api/v1", tags=["assistant"])
IST = ZoneInfo("Asia/Kolkata")
PENDING_MINUTES = 10

# shortcut: English and Telugu keyword lists need review by native Telugu-speaking sellers (P01).
INTENTS = [
    ("cancel", re.compile(r"\b(cancel|stop)\b|రద్దు|ఆపు")),
    ("report", re.compile(r"\b(report|sales|summary|how much)\b|రిపోర్ట్|అమ్మకాలు|లెక్క")),
    ("confirm_order", re.compile(r"\b(order|buy)\b|ఆర్డర్|కొనాలి")),
    ("show_quote", re.compile(r"\b(show|status|my quotes?)\b|చూపించు|స్థితి")),
    ("request_quote", re.compile(r"\b(quote|quotation|rfq|price)\b|కొటేషన్|కోటేషన్|కోట్(?![\u0C00-\u0C7F])|ధర")),  # కోట్: "quote" in te-IN speech
    ("find_product", re.compile(r"\b(find|search|need|want|looking)\b|వెతుకు|కావాలి")),
]
HUMAN = re.compile(r"\b(human|person|agent|support)\b|మనిషి|సహాయకుడు")
# Spoken Telugu (browser speech) writes ఆమ్, ఆంప్స్ or ఆంపియర్ for amp and టు for టూ; the forms seen in testing are accepted.
AMPS = re.compile(r"(\d+)\s*(?:amperes?|amps?|a|ఆంపియర్లు|ఆంపియర్|ఆంప్స్|ఆంప్|ఆమ్)(?![a-z])")
WAYS = re.compile(r"\b(one|1|two|2)[\s-]*way\b|(వన్|టూ|టు)[\s-]*వే")
NUMBER = re.compile(r"\d+")  # \d also matches Telugu digits, and int() reads them
# Telugu number words read as digits ("ఆరు ఆంప్" is 6A). ఒక alone is left out: it also means "a".
TE_NUMBERS = {"ఒకటి": 1, "రెండు": 2, "మూడు": 3, "నాలుగు": 4, "ఐదు": 5, "ఆరు": 6, "ఏడు": 7, "ఎనిమిది": 8,
              "తొమ్మిది": 9, "పది": 10, "పదహారు": 16, "ఇరవై": 20, "ముప్పై": 30, "యాభై": 50, "వంద": 100}
TE_NUMBER = re.compile(r"(?<!\S)(" + "|".join(TE_NUMBERS) + r")(?=[\s,.!?]|$)")
# Speech also writes six as ఆర్ or ఆరే; read them as 6 only before an amp word, so ఆర్డర్ and others are untouched.
TE_SIX_BEFORE_AMP = re.compile(r"(?<!\S)(?:ఆర్|ఆరే)(?=\s*(?:ఆంప|ఆమ్|amp))")


def te_digits(text: str) -> str:
    return TE_NUMBER.sub(lambda m: str(TE_NUMBERS[m.group(1)]), TE_SIX_BEFORE_AMP.sub("6", text))

TEXT = {
    "en": {
        "help": "I can find products, request a quote, show your quotes, or place an order. Try: 'find 6A switch'.",
        "cancelled": "Cancelled. What would you like to do?",
        "found": "I found {n}:\n{lines}\nTo ask a seller for a price, say 'quote'.",
        "found_line": "{i}. {name}, {seller}: {price} per {unit}, {qty} in stock, minimum {moq}",
        "none_found": "No matching products are listed right now.",
        "search_first": "First tell me what to find, for example 'find 6A switch'.",
        "ask_product": "Which product number from the list? (1 to {n})",
        "ask_quantity": "How many {unit}? The minimum is {moq}.",
        "ask_city": "Which city should it be delivered to?",
        "not_number": "Please say a number.",
        "gone": "That product is no longer available. Please search again.",
        "readback_rfq": "Please check: ask {seller} for a quote for {qty} {unit} of {name}, delivered to {city}. Press Confirm to send the request.",
        "no_quotes": "You have no open quotes right now.",
        "quotes": "Your open quotes:\n{lines}",
        "quote_line": "{i}. {name}: {qty} {unit}, total {total} (simulated), valid until {until}",
        "ask_quote": "Which quote number do you want to order? (1 to {n})",
        "readback_order": "Please check: order {qty} {unit} of {name} from {seller}. Total {total}, including {tax} simulated tax. Advance {advance}. This is a simulated order; no money moves. Press Confirm to place it.",
        "handoff": "I have asked a person from support to help. They will reply here; I will not take any action until they hand back.",
        "paused": "A person from support is handling this conversation and will reply here.",
        "report": ("Report for {start} to {end}. Money is simulated; only recorded receipts count as received.\n"
                   "Sales: {s_orders} orders worth {s_value}, {s_cancel} cancelled. Received {s_recv}. Still to receive {s_out}.\n"
                   "Purchases: {p_orders} orders worth {p_value}, {p_cancel} cancelled. Paid {p_recv}. Still to pay {p_out}.\n"
                   "Waiting for approval: {pending}. Open complaints: {cases}. Delayed orders: {delayed}.\n"
                   "Search results are only possible suppliers; requests and quotes are not sales."),
        "units": {"box": "boxes", "piece": "pieces"},
        "unit": {"box": "box", "piece": "piece"},
    },
    "te": {
        "help": "నేను ఉత్పత్తులు వెతకగలను, కొటేషన్ అడగగలను, మీ కొటేషన్లు చూపించగలను, ఆర్డర్ చేయగలను. ఉదాహరణ: '6A స్విచ్ కావాలి'.",
        "cancelled": "రద్దు చేశాను. ఇంకేం చేయాలి?",
        "found": "{n} దొరికాయి:\n{lines}\nధర అడగాలంటే 'కొటేషన్' అని చెప్పండి.",
        "found_line": "{i}. {name}, {seller}: ఒక్కో {unit}కి {price}, స్టాక్ {qty}, కనీసం {moq}",
        "none_found": "సరిపోయే ఉత్పత్తులు ఇప్పుడు లేవు.",
        "search_first": "ముందు ఏం వెతకాలో చెప్పండి, ఉదాహరణ: '6A స్విచ్ కావాలి'.",
        "ask_product": "జాబితాలో ఏ నంబర్ ఉత్పత్తి? (1 నుండి {n})",
        "ask_quantity": "ఎన్ని {unit}? కనీసం {moq}.",
        "ask_city": "ఏ ఊరికి డెలివరీ చేయాలి?",
        "not_number": "దయచేసి ఒక నంబర్ చెప్పండి.",
        "gone": "ఆ ఉత్పత్తి ఇప్పుడు అందుబాటులో లేదు. మళ్లీ వెతకండి.",
        "readback_rfq": "సరిచూడండి: {seller} నుండి {name} {qty} {unit}కి కొటేషన్ అడుగుతున్నాం, డెలివరీ {city}కి. పంపడానికి Confirm నొక్కండి.",
        "no_quotes": "ఇప్పుడు మీకు తెరిచి ఉన్న కొటేషన్లు లేవు.",
        "quotes": "మీ కొటేషన్లు:\n{lines}",
        "quote_line": "{i}. {name}: {qty} {unit}, మొత్తం {total} (నమూనా), {until} వరకు చెల్లుతుంది",
        "ask_quote": "ఏ నంబర్ కొటేషన్‌కి ఆర్డర్ చేయాలి? (1 నుండి {n})",
        "readback_order": "సరిచూడండి: {seller} నుండి {name} {qty} {unit} ఆర్డర్. మొత్తం {total}, ఇందులో నమూనా పన్ను {tax}. అడ్వాన్స్ {advance}. ఇది నమూనా ఆర్డర్ మాత్రమే, ఏ డబ్బూ బదిలీ కాదు. ఆర్డర్ చేయడానికి Confirm నొక్కండి.",
        "handoff": "సపోర్ట్ నుండి ఒక వ్యక్తిని సహాయానికి అడిగాను. వారు ఇక్కడే జవాబిస్తారు; వారు తిరిగి అప్పగించే వరకు నేను ఏ పనీ చేయను.",
        "paused": "సపోర్ట్ నుండి ఒక వ్యక్తి ఈ సంభాషణను చూస్తున్నారు, ఇక్కడే జవాబిస్తారు.",
        "report": ("{start} నుండి {end} వరకు రిపోర్ట్. ఇది నమూనా డబ్బు; నమోదైన రసీదులే అందినట్లు లెక్క.\n"
                   "అమ్మకాలు: {s_orders} ఆర్డర్లు, విలువ {s_value}, రద్దు {s_cancel}. అందింది {s_recv}. ఇంకా రావాల్సింది {s_out}.\n"
                   "కొనుగోళ్లు: {p_orders} ఆర్డర్లు, విలువ {p_value}, రద్దు {p_cancel}. చెల్లించింది {p_recv}. ఇంకా చెల్లించాల్సింది {p_out}.\n"
                   "ఆమోదం కోసం వేచి ఉంది: {pending}. పరిష్కారం కాని ఫిర్యాదులు: {cases}. ఆలస్యమైన ఆర్డర్లు: {delayed}.\n"
                   "శోధన ఫలితాలు కేవలం సంభావ్య సరఫరాదారుల వివరాలను మాత్రమే చూపిస్తాయి; అభ్యర్థనలు, కొటేషన్లు అమ్మకాలు కావు."),
        "units": {"box": "బాక్సులు", "piece": "ముక్కలు"},
        "unit": {"box": "బాక్సు", "piece": "ముక్క"},
    },
}


def rupees(paise: int) -> str:
    """Indian digit grouping, e.g. 10000000 paise -> ₹1,00,000.00."""
    whole, frac = divmod(paise, 100)
    digits = str(whole)
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return f"₹{','.join(groups + [tail])}.{frac:02d}"


def _number(text: str) -> int | None:
    match = NUMBER.search(WAYS.sub("", AMPS.sub("", text)))  # "6A two-way" holds no quantity
    return int(match.group()) if match else None


def _open_quotes(db: Session, org_id) -> list[tuple[Quote, Organization]]:
    """Product names and units come from the quote's bound snapshot, the terms an order will use."""
    return db.execute(
        select(Quote, Organization)
        .join(Rfq, Rfq.id == Quote.rfq_id)
        .join(Organization, Organization.id == Rfq.seller_org_id)
        .where(Rfq.buyer_org_id == org_id, Quote.status == "sent", Quote.valid_until > func.now())
        .order_by(Quote.sent_at.desc())
        .limit(5)
    ).all()


def _quote_lines(T, rows) -> str:
    return "\n".join(
        T["quote_line"].format(i=i, name=q.product_snapshot["name"], qty=q.quantity, unit=T["units"][q.product_snapshot["unit"]],
                               total=rupees(q.total_paise), until=q.valid_until.astimezone(IST).strftime("%d %b %Y %I:%M %p"))
        for i, (q, _) in enumerate(rows, 1)
    )


def respond(db: Session, m: Member, conv: Conversation, raw: str) -> tuple[str, dict | None]:
    """Returns the reply and, when details are complete, a pending action to create. Updates conv.state."""
    T, text = TEXT[conv.language], te_digits(raw.lower())
    state = copy.deepcopy(conv.state or {})
    intent = next((name for name, rx in INTENTS if rx.search(text)), None)
    if intent == "cancel":
        conv.state = {}
        return T["cancelled"], None
    if intent:
        state.update(intent=intent, step=None, draft={})
    elif not state.get("intent"):
        return T["help"], None
    reply, action = _step(db, m, state, raw, text, T)
    conv.state = state
    return reply, action


def report_text(T, r) -> str:
    s, p = r.sales, r.purchases
    return T["report"].format(
        start=r.from_date.strftime("%d %b %Y"), end=r.to_date.strftime("%d %b %Y"),
        s_orders=s.orders, s_value=rupees(s.order_value_paise), s_cancel=s.cancelled_orders,
        s_recv=rupees(s.received_paise), s_out=rupees(s.outstanding_paise),
        p_orders=p.orders, p_value=rupees(p.order_value_paise), p_cancel=p.cancelled_orders,
        p_recv=rupees(p.received_paise), p_out=rupees(p.outstanding_paise),
        pending=rupees(s.awaiting_approval_paise + p.awaiting_approval_paise), cases=r.open_cases, delayed=r.delayed_orders_count,
    )


def _step(db, m, state, raw, text, T):
    intent, step = state["intent"], state.get("step")

    if intent == "report":
        state["intent"] = None
        return report_text(T, reports.summary(db, m.org.id, *reports.current_month(db_clock(db)))), None

    if intent == "find_product":
        amps, ways = AMPS.search(text), WAYS.search(text)
        products = [p for p in search(
            db, rating_amps=int(amps.group(1)) if amps else None,
            ways=(1 if (ways.group(1) or ways.group(2)) in ("one", "1", "వన్") else 2) if ways else None,
            quantity=_number(text), limit=10,
        ) if p.org_id != m.org.id][:3]
        state.update(intent=None, results=[str(p.id) for p in products])
        if not products:
            return T["none_found"], None
        lines = "\n".join(
            T["found_line"].format(i=i, name=p.name, seller=p.seller.name, price=rupees(p.price_paise),
                                   unit=T["unit"][p.unit], qty=p.available_qty, moq=p.moq)
            for i, p in enumerate(products, 1)
        )
        return T["found"].format(n=len(products), lines=lines), None

    if intent == "request_quote":
        results = state.get("results", [])
        if step is None:
            if not results:
                state["intent"] = None
                return T["search_first"], None
            state["step"] = "product"
            return T["ask_product"].format(n=len(results)), None
        if step in ("product", "quantity"):
            n = _number(text)
            if n is None:
                return T["not_number"], None
            if step == "product":
                if not 1 <= n <= len(results):
                    return T["ask_product"].format(n=len(results)), None
                state["draft"]["product_id"] = results[n - 1]
        product = db.scalar(discoverable().where(Product.id == uuid.UUID(state["draft"]["product_id"])))
        if product is None:
            state["intent"] = None
            return T["gone"], None
        unit = T["units"][product.unit]
        if step == "product" or (step == "quantity" and n < product.moq):
            state["step"] = "quantity"
            return T["ask_quantity"].format(unit=unit, moq=product.moq), None
        if step == "quantity":
            state["draft"]["quantity"], state["step"] = n, "city"
            return T["ask_city"], None
        city = raw.strip()[:80]
        payload = state["draft"] | {"delivery_city": city}
        state["intent"] = None
        return T["readback_rfq"].format(seller=product.seller.name, qty=payload["quantity"], unit=unit,
                                        name=product.name, city=city), ("create_rfq", payload)

    rows = _open_quotes(db, m.org.id)
    if not rows:
        state["intent"] = None
        return T["no_quotes"], None
    if intent == "show_quote":
        state["intent"] = None
        return T["quotes"].format(lines=_quote_lines(T, rows)), None

    # confirm_order
    if step is None:
        state.update(step="quote", quotes=[str(q.id) for q, _ in rows])
        return T["quotes"].format(lines=_quote_lines(T, rows)) + "\n" + T["ask_quote"].format(n=len(rows)), None
    n, shown = _number(text), state.get("quotes", [])
    if n is None or not 1 <= n <= len(shown):
        return T["ask_quote"].format(n=len(shown)), None
    match = next(((q, s) for q, s in rows if str(q.id) == shown[n - 1]), None)
    state["intent"] = None
    if match is None:  # expired or replaced since it was listed
        return T["no_quotes"], None
    q, seller = match
    terms = q.product_snapshot
    payload = {"quote_id": str(q.id), "quote_version": q.version, "total_paise": q.total_paise}
    return T["readback_order"].format(qty=q.quantity, unit=T["units"][terms["unit"]], name=terms["name"], seller=seller.name,
                                      total=rupees(q.total_paise), tax=rupees(q.tax_paise),
                                      advance=rupees(q.advance_paise)), ("confirm_order", payload)


def _own_conversation(db: Session, m: Member, conversation_id) -> Conversation:
    conv = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.org_id == m.org.id, Conversation.user_id == m.user.id)
        .with_for_update()
    )
    if conv is None:
        raise AppError(404, "not_found", "Not found.")
    return conv


@router.post("/orgs/{org_id}/conversations", response_model=ConversationOut, status_code=201)
def start_conversation(m: Member = Depends(member), db: Session = Depends(get_db)):
    conv = Conversation(org_id=m.org.id, user_id=m.user.id, language=m.user.preferred_language, state={})
    db.add(conv)
    db.commit()
    return conv



@router.get("/orgs/{org_id}/conversations", response_model=list[ConversationOut])
def list_conversations(m: Member = Depends(member), db: Session = Depends(get_db)):
    """The caller's own conversations only, newest first, each with its latest handoff's complaint and status."""
    convs = db.scalars(
        select(Conversation).where(Conversation.org_id == m.org.id, Conversation.user_id == m.user.id)
        .order_by(Conversation.created_at.desc(), Conversation.id).limit(20)
    ).all()
    latest = {}  # oldest first, so the newest handoff of each conversation wins
    for h in db.scalars(select(Handoff).where(Handoff.conversation_id.in_([c.id for c in convs])).order_by(Handoff.created_at, Handoff.id)):
        latest[h.conversation_id] = h
    return [
        ConversationOut(id=c.id, language=c.language, created_at=c.created_at,
                        support_case_id=latest[c.id].case_id if c.id in latest else None,
                        support_status=latest[c.id].status if c.id in latest else None)
        for c in convs
    ]


@router.get("/orgs/{org_id}/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    conv = _own_conversation(db, m, conversation_id)
    pending = db.scalar(select(PendingAction).where(
        PendingAction.conversation_id == conv.id, PendingAction.status == "pending", PendingAction.expires_at > func.now()
    ))
    return ConversationDetail(id=conv.id, language=conv.language, created_at=conv.created_at,
                              handoff=active_handoff(db, conv.id), pending_action=pending)


@router.get("/orgs/{org_id}/conversations/{conversation_id}/events", response_class=StreamingResponse)
def conversation_events(conversation_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    """Owner-only change signals; the content itself is read through the message and status routes."""
    conv_id = str(_own_conversation(db, m, conversation_id).id)
    db.rollback()  # release the row lock and the pooled connection before the long-lived stream starts
    db.close()
    return StreamingResponse(events.stream(conv_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

def active_handoff(db: Session, conversation_id) -> Handoff | None:
    return db.scalar(select(Handoff).where(Handoff.conversation_id == conversation_id, Handoff.status.in_(("queued", "assigned"))))


def _cancel_pending(db: Session, conversation_id) -> list[str]:
    return list(db.scalars(
        update(PendingAction).where(PendingAction.conversation_id == conversation_id, PendingAction.status == "pending")
        .values(status="cancelled").returning(PendingAction.action)
    ))


def request_handoff(db: Session, m: Member, conv: Conversation, body: HandoffIn) -> tuple[Handoff, bool]:
    """Caller holds the conversation lock. Returns (handoff, created). Pending AI proposals are withdrawn."""
    if existing := active_handoff(db, conv.id):
        return existing, False
    if body.case_id and db.scalar(select(Case.id).where(
        Case.id == body.case_id, or_(Case.buyer_org_id == m.org.id, Case.seller_org_id == m.org.id)
    )) is None:
        raise AppError(404, "not_found", "Not found.")
    handoff = Handoff(conversation_id=conv.id, org_id=m.org.id, requested_by=m.user.id,
                      cancelled_actions=_cancel_pending(db, conv.id), **body.model_dump())
    db.add(handoff)
    db.add(Message(conversation_id=conv.id, role="assistant", text=TEXT[conv.language]["handoff"]))
    db.flush()
    audit(db, m.org.id, m.user.id, "conversation.handoff_requested", "handoff", handoff.id, {"urgency": body.urgency})
    return handoff, True


@router.post("/orgs/{org_id}/conversations/{conversation_id}/handoff", response_model=HandoffOut, status_code=201)
def post_handoff(conversation_id: uuid.UUID, body: HandoffIn, response: Response, m: Member = Depends(member), db: Session = Depends(get_db)):
    conv = _own_conversation(db, m, conversation_id)
    handoff, created = request_handoff(db, m, conv, body)
    if not created:
        response.status_code = 200
    db.commit()
    return handoff


@router.get("/orgs/{org_id}/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=500),
    before: int | None = Query(None, ge=1),
    after: int | None = Query(None, ge=0),
    m: Member = Depends(member),
    db: Session = Depends(get_db),
):
    """Oldest first. No cursor: the newest page; `before`: scroll back; `after`: poll for newer. A short page ends that direction."""
    if before is not None and after is not None:
        raise AppError(400, "validation_error", "Use either before or after, not both.")
    conv = _own_conversation(db, m, conversation_id)
    stmt = select(Message).where(Message.conversation_id == conv.id)
    if after is not None:
        return db.scalars(stmt.where(Message.id > after).order_by(Message.id).limit(limit)).all()
    if before is not None:
        stmt = stmt.where(Message.id < before)
    return list(reversed(db.scalars(stmt.order_by(Message.id.desc()).limit(limit)).all()))


@router.post("/orgs/{org_id}/conversations/{conversation_id}/messages", response_model=AssistantReply)
def post_message(
    conversation_id: uuid.UUID,
    body: MessageIn,
    idempotency_key: str | None = Header(None, min_length=1, max_length=80),
    m: Member = Depends(member),
    db: Session = Depends(get_db),
):
    conv = _own_conversation(db, m, conversation_id)  # the lock serializes retries of the same key
    if idempotency_key and (sent := db.scalar(select(Message).where(
        Message.conversation_id == conv.id, Message.role == "user", Message.idempotency_key == idempotency_key
    ))):
        return _replay(db, conv, sent, body.text)
    user_message = Message(conversation_id=conv.id, role="user", text=body.text, idempotency_key=idempotency_key)
    db.add(user_message)
    db.flush()  # its id orders it before the reply, which a replay looks up
    if HUMAN.search(body.text.lower()) and not active_handoff(db, conv.id):
        request_handoff(db, m, conv, HandoffIn())
        db.commit()
        return AssistantReply(reply=TEXT[conv.language]["handoff"], pending_action=None)
    if active_handoff(db, conv.id):  # a person owns the conversation: store the message, propose nothing
        reply = TEXT[conv.language]["paused"]
        db.add(Message(conversation_id=conv.id, role="assistant", text=reply))
        db.commit()
        return AssistantReply(reply=reply, pending_action=None)
    reply, action = respond(db, m, conv, body.text)
    # Only the newest proposal can be confirmed; a new message withdraws older ones.
    _cancel_pending(db, conv.id)
    pending = None
    if action:
        pending = PendingAction(conversation_id=conv.id, org_id=m.org.id, actor_user_id=m.user.id, action=action[0],
                                payload=action[1], expires_at=func.now() + timedelta(minutes=PENDING_MINUTES))
        db.add(pending)
    db.add(Message(conversation_id=conv.id, role="assistant", text=reply))
    db.commit()
    return AssistantReply(reply=reply, pending_action=pending)


def _replay(db: Session, conv: Conversation, sent: Message, text: str) -> AssistantReply:
    """A retried send: the stored reply, and the live proposal only if this is still the newest user message."""
    if sent.text != text:
        raise AppError(409, "idempotency_key_reused", "This Idempotency-Key was already used for a different message.")
    reply = db.scalar(select(Message.text).where(
        Message.conversation_id == conv.id, Message.role == "assistant", Message.id > sent.id
    ).order_by(Message.id).limit(1))
    newest = db.scalar(select(func.max(Message.id)).where(Message.conversation_id == conv.id, Message.role == "user"))
    pending = db.scalar(select(PendingAction).where(
        PendingAction.conversation_id == conv.id, PendingAction.status == "pending", PendingAction.expires_at > func.now()
    )) if newest == sent.id else None
    return AssistantReply(reply=reply or "", pending_action=pending)


@router.post("/orgs/{org_id}/pending-actions/{action_id}/confirm", response_model=PendingResult)
def confirm_pending(action_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    owned = (PendingAction.id == action_id, PendingAction.org_id == m.org.id, PendingAction.actor_user_id == m.user.id)
    conversation_id = db.scalar(select(PendingAction.conversation_id).where(*owned))
    if conversation_id is None:
        raise AppError(404, "not_found", "Not found.")
    # Lock order: conversation, then pending action (same as messages and handoff requests).
    db.scalar(select(Conversation.id).where(Conversation.id == conversation_id).with_for_update())
    pa = db.scalar(select(PendingAction).where(*owned).with_for_update().execution_options(populate_existing=True))
    if active_handoff(db, conversation_id):
        raise AppError(409, "conversation_paused", "A person is handling this conversation; the assistant cannot act now.")
    if pa.status == "confirmed":  # repeated press: same result, nothing new
        if pa.action == "create_rfq":
            return PendingResult(action=pa.action, rfq=db.get(Rfq, pa.result_id))
        return PendingResult(action=pa.action, order=db.get(Order, pa.result_id))
    if pa.status == "pending" and db_clock(db) >= pa.expires_at:
        return _expire(db, pa)
    if pa.status != "pending":
        raise AppError(409, "pending_action_not_active", f"This request is {pa.status}. Please ask again.", {"status": pa.status})
    if pa.action == "create_rfq":
        rfq, _ = create_rfq(db, m, RfqIn(**pa.payload), key=f"pending:{pa.id}")
        result = PendingResult(action=pa.action, rfq=RfqOut.model_validate(rfq))
        pa.result_id = rfq.id
    else:
        order, _ = confirm_order(db, m, OrderIn(**pa.payload), key=f"pending:{pa.id}")
        result, pa.result_id = PendingResult(action=pa.action, order=order), order.id
    if db_clock(db) >= pa.expires_at:  # the business call may have waited for locks past the deadline
        db.rollback()
        return _expire(db, db.get(PendingAction, action_id))
    pa.status = "confirmed"
    db.commit()
    return result


def _expire(db: Session, pa: PendingAction):
    pa.status = "expired"
    db.commit()
    raise AppError(409, "pending_action_not_active", "This request is expired. Please ask again.", {"status": "expired"})
