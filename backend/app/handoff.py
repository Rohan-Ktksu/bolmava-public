"""Support staff side of human handoff. A support person sees one conversation only after taking its handoff."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.cases import support
from app.db import get_db
from app.errors import AppError
from app.models import Case, Conversation, Handoff, Message, Order, Organization, User
from app.schemas import CaseOut, HandoffOut, HandoffQueueItem, HandoffSummary, MessageIn, MessageOut
from app.trade import db_clock

router = APIRouter(prefix="/api/v1/staff", tags=["staff"])
NOT_FOUND = AppError(404, "not_found", "Not found.")


def _locked(db: Session, handoff_id, user: User | None = None) -> Handoff:
    """Lock order: conversation, then handoff. With `user`, only that person's assigned handoff is found."""
    conversation_id = db.scalar(select(Handoff.conversation_id).where(Handoff.id == handoff_id))
    if conversation_id is None:
        raise NOT_FOUND
    db.scalar(select(Conversation.id).where(Conversation.id == conversation_id).with_for_update())
    stmt = select(Handoff).where(Handoff.id == handoff_id)
    if user:
        stmt = stmt.where(Handoff.assigned_to == user.id)
    handoff = db.scalar(stmt.with_for_update().execution_options(populate_existing=True))
    if handoff is None:
        raise NOT_FOUND
    return handoff


def _invalid(handoff: Handoff) -> AppError:
    return AppError(409, "invalid_transition", f"This handoff is {handoff.status}.", {"status": handoff.status})


@router.get("/handoffs")
def queue(scope: str = Query("unassigned", pattern="^(unassigned|mine)$"), user: User = Depends(support), db: Session = Depends(get_db)):
    if scope == "unassigned":
        rows = db.scalars(select(Handoff).where(Handoff.status == "queued").order_by(Handoff.created_at).limit(100)).all()
        # Which waiting chats are about complaints this person holds; nobody else learns the link.
        held = set(db.scalars(select(Case.id).where(Case.id.in_([h.case_id for h in rows if h.case_id]), Case.assigned_to == user.id)))
        return [HandoffQueueItem.model_validate(h).model_copy(update={"your_case_id": h.case_id if h.case_id in held else None}) for h in rows]
    rows = db.scalars(select(Handoff).where(Handoff.assigned_to == user.id).order_by(Handoff.created_at.desc()).limit(100)).all()
    return [HandoffOut.model_validate(h) for h in rows]


@router.post("/handoffs/{handoff_id}/take", response_model=HandoffSummary)
def take(handoff_id: uuid.UUID, user: User = Depends(support), db: Session = Depends(get_db)):
    handoff = _locked(db, handoff_id)
    if (handoff.status, handoff.assigned_to) != ("assigned", user.id):  # else a harmless repeat by the current assignee
        if handoff.status != "queued":  # includes the caller's own released handoff: release ends transcript access
            raise AppError(409, "invalid_transition", "This handoff is not available to take.", {"status": "unavailable"})
        handoff.status, handoff.assigned_to, handoff.assigned_at = "assigned", user.id, db_clock(db)
        audit(db, handoff.org_id, user.id, "conversation.handoff_taken", "handoff", handoff.id, {})
    result = summary(db, handoff)  # built while the locks still block release; commit only afterwards
    db.commit()
    return result


@router.get("/handoffs/{handoff_id}", response_model=HandoffSummary)
def get_handoff(handoff_id: uuid.UUID, user: User = Depends(support), db: Session = Depends(get_db)):
    # Same locks as release, held until the summary is built, so a release cannot land between check and read.
    handoff = _locked(db, handoff_id, user)
    if handoff.status != "assigned":
        raise NOT_FOUND
    result = summary(db, handoff)
    db.rollback()  # read-only: end the transaction and its locks
    return result


def summary(db: Session, handoff: Handoff) -> HandoffSummary:
    """Only this conversation's recent messages and its linked case/order: nothing from other conversations.
    Callers hold the conversation → handoff locks (`_locked`) for a handoff assigned to the requester, and keep
    them until this returns, so release cannot commit while the transcript and case are read."""
    if handoff.status != "assigned":
        raise NOT_FOUND
    conv = db.get(Conversation, handoff.conversation_id)
    requester = db.get(User, handoff.requested_by)
    messages = db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.id.desc()).limit(10)).all()
    case = db.get(Case, handoff.case_id) if handoff.case_id else None
    return HandoffSummary(
        **HandoffOut.model_validate(handoff).model_dump(),
        requester_name=requester.display_name, language=conv.language,
        organization_name=db.get(Organization, handoff.org_id).name,
        recent_messages=[MessageOut.model_validate(x) for x in reversed(messages)],
        case=CaseOut.model_validate(case) if case else None,
        order_status=db.get(Order, case.order_id).status if case else None,
        cancelled_actions=handoff.cancelled_actions,
    )


@router.post("/handoffs/{handoff_id}/messages", response_model=MessageOut, status_code=201)
def agent_message(handoff_id: uuid.UUID, body: MessageIn, user: User = Depends(support), db: Session = Depends(get_db)):
    handoff = _locked(db, handoff_id, user)
    if handoff.status != "assigned":
        raise _invalid(handoff)
    message = Message(conversation_id=handoff.conversation_id, role="agent", text=body.text)
    db.add(message)
    db.commit()
    return message


@router.post("/handoffs/{handoff_id}/release", response_model=HandoffOut)
def release(handoff_id: uuid.UUID, user: User = Depends(support), db: Session = Depends(get_db)):
    handoff = _locked(db, handoff_id, user)
    if handoff.status == "released":
        return handoff
    if handoff.status != "assigned":
        raise _invalid(handoff)
    handoff.status, handoff.released_at = "released", db_clock(db)
    audit(db, handoff.org_id, user.id, "conversation.handoff_released", "handoff", handoff.id, {})
    db.commit()
    return handoff
