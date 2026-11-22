"""Order complaints. Parties see party-visible updates; only the assigned support person sees internal notes.
Nothing here creates, approves, records, or reverses money."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth import Member, member, staff
from app.db import get_db
from app.errors import AppError
from app.models import ROLES, Case, CaseEvidence, CaseUpdate, Order, User
from app.schemas import (
    CaseDetail, CaseIn, CaseOut, CaseQueueItem, CaseUpdateOut, EvidenceIn, EvidenceOut, ResolveIn, StaffUpdateIn, UpdateIn,
)
from app.trade import BUYERS, db_clock

router = APIRouter(prefix="/api/v1", tags=["cases"])
support = staff("support")
NOT_FOUND = AppError(404, "not_found", "Not found.")
CONTRIBUTORS = tuple(r for r in ROLES if r != "viewer")


def _invalid(case: Case) -> AppError:
    return AppError(409, "invalid_transition", f"This case is {case.status}.", {"status": case.status})


def _party_case(db: Session, org_id, case_id, lock=False) -> Case:
    stmt = select(Case).where(Case.id == case_id, or_(Case.buyer_org_id == org_id, Case.seller_org_id == org_id))
    case = db.scalar(stmt.with_for_update() if lock else stmt)
    if case is None:
        raise NOT_FOUND
    return case


def _assigned_case(db: Session, user: User, case_id, lock=False) -> Case:
    stmt = select(Case).where(Case.id == case_id, Case.assigned_to == user.id)
    case = db.scalar(stmt.with_for_update() if lock else stmt)
    if case is None:  # unassigned staff learn nothing about the case
        raise NOT_FOUND
    return case


def _detail(db: Session, case: Case, internal: bool) -> CaseDetail:
    updates = select(CaseUpdate).where(CaseUpdate.case_id == case.id).order_by(CaseUpdate.created_at, CaseUpdate.id)
    if not internal:
        updates = updates.where(CaseUpdate.visibility == "parties")
    evidence = select(CaseEvidence).where(CaseEvidence.case_id == case.id).order_by(CaseEvidence.created_at)
    return CaseDetail(**CaseOut.model_validate(case).model_dump(), updates=db.scalars(updates).all(), evidence=db.scalars(evidence).all())


def _touch(db: Session, case: Case, actor: User, action: str, data: dict) -> None:
    case.updated_at = db_clock(db)
    for org_id in (case.buyer_org_id, case.seller_org_id):
        audit(db, org_id, actor.id, f"case.{action}", "case", case.id, data)


@router.post("/orgs/{org_id}/orders/{order_id}/cases", response_model=CaseOut, status_code=201)
def open_case(order_id: uuid.UUID, body: CaseIn, m: Member = Depends(member), db: Session = Depends(get_db)):
    m.require(BUYERS, "can_buy")
    order = db.scalar(select(Order).where(Order.id == order_id, Order.buyer_org_id == m.org.id))
    if order is None:
        raise NOT_FOUND
    case = Case(order_id=order.id, buyer_org_id=order.buyer_org_id, seller_org_id=order.seller_org_id, opened_by=m.user.id, **body.model_dump())
    db.add(case)
    db.flush()
    _touch(db, case, m.user, "opened", body.model_dump())
    db.commit()
    return case


@router.get("/orgs/{org_id}/cases", response_model=list[CaseOut])
def list_cases(m: Member = Depends(member), db: Session = Depends(get_db)):
    party = or_(Case.buyer_org_id == m.org.id, Case.seller_org_id == m.org.id)
    return db.scalars(select(Case).where(party).order_by(Case.created_at.desc(), Case.id)).all()


@router.get("/orgs/{org_id}/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    return _detail(db, _party_case(db, m.org.id, case_id), internal=False)


@router.post("/orgs/{org_id}/cases/{case_id}/updates", response_model=CaseUpdateOut, status_code=201)
def party_update(case_id: uuid.UUID, body: UpdateIn, m: Member = Depends(member), db: Session = Depends(get_db)):
    m.require(CONTRIBUTORS)
    case = _party_case(db, m.org.id, case_id, lock=True)
    if case.status == "closed":
        raise _invalid(case)
    update = CaseUpdate(case_id=case.id, author_id=m.user.id, visibility="parties", body=body.body)
    db.add(update)
    _touch(db, case, m.user, "updated", {"visibility": "parties"})
    db.commit()
    return update


@router.post("/orgs/{org_id}/cases/{case_id}/evidence", response_model=EvidenceOut, status_code=201)
def add_evidence(case_id: uuid.UUID, body: EvidenceIn, m: Member = Depends(member), db: Session = Depends(get_db)):
    """Metadata only (SPEC O5): no file is stored and no download URL exists."""
    m.require(CONTRIBUTORS)
    case = _party_case(db, m.org.id, case_id, lock=True)
    if case.status == "closed":
        raise _invalid(case)
    evidence = CaseEvidence(case_id=case.id, added_by=m.user.id, **body.model_dump())
    db.add(evidence)
    _touch(db, case, m.user, "evidence_added", {"filename": body.filename, "sha256": body.sha256})
    db.commit()
    return evidence


def _buyer_transition(db: Session, m: Member, case_id, action: str) -> Case:
    m.require(BUYERS, "can_buy")
    case = _party_case(db, m.org.id, case_id, lock=True)
    if case.buyer_org_id != m.org.id:
        raise AppError(403, "forbidden", "Only the buyer can do this.")
    if case.status != "resolved":
        raise _invalid(case)
    if action == "reopen":
        case.status, case.reopen_count = ("assigned" if case.assigned_to else "open"), case.reopen_count + 1
    else:
        case.status = "closed"
    _touch(db, case, m.user, action, {})
    db.commit()
    return case


@router.post("/orgs/{org_id}/cases/{case_id}/reopen", response_model=CaseOut)
def reopen(case_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    return _buyer_transition(db, m, case_id, "reopen")


@router.post("/orgs/{org_id}/cases/{case_id}/close", response_model=CaseOut)
def close(case_id: uuid.UUID, m: Member = Depends(member), db: Session = Depends(get_db)):
    return _buyer_transition(db, m, case_id, "closed")


@router.get("/staff/cases", tags=["staff"])
def staff_cases(scope: str = Query("unassigned", pattern="^(unassigned|mine)$"), user: User = Depends(support), db: Session = Depends(get_db)):
    if scope == "unassigned":
        rows = db.scalars(select(Case).where(Case.status == "open", Case.assigned_to.is_(None)).order_by(Case.created_at).limit(100)).all()
        return [CaseQueueItem.model_validate(c) for c in rows]
    rows = db.scalars(select(Case).where(Case.assigned_to == user.id).order_by(Case.updated_at.desc()).limit(100)).all()
    return [CaseOut.model_validate(c) for c in rows]


@router.post("/staff/cases/{case_id}/take", response_model=CaseDetail, tags=["staff"])
def take_case(case_id: uuid.UUID, user: User = Depends(support), db: Session = Depends(get_db)):
    case = db.scalar(select(Case).where(Case.id == case_id).with_for_update())
    if case is None:
        raise NOT_FOUND
    if case.assigned_to != user.id:
        if case.assigned_to is not None or case.status != "open":
            raise AppError(409, "invalid_transition", "This case is not available to take.", {"status": "unavailable"})
        case.assigned_to, case.status = user.id, "assigned"
        _touch(db, case, user, "assigned", {})
        db.commit()
    return _detail(db, case, internal=True)


@router.get("/staff/cases/{case_id}", response_model=CaseDetail, tags=["staff"])
def staff_case(case_id: uuid.UUID, user: User = Depends(support), db: Session = Depends(get_db)):
    return _detail(db, _assigned_case(db, user, case_id), internal=True)


@router.post("/staff/cases/{case_id}/updates", response_model=CaseUpdateOut, status_code=201, tags=["staff"])
def staff_update(case_id: uuid.UUID, body: StaffUpdateIn, user: User = Depends(support), db: Session = Depends(get_db)):
    case = _assigned_case(db, user, case_id, lock=True)
    if case.status == "closed":
        raise _invalid(case)
    update = CaseUpdate(case_id=case.id, author_id=user.id, **body.model_dump())
    db.add(update)
    _touch(db, case, user, "updated", {"visibility": body.visibility})
    db.commit()
    return update


@router.post("/staff/cases/{case_id}/investigate", response_model=CaseOut, tags=["staff"])
def investigate(case_id: uuid.UUID, user: User = Depends(support), db: Session = Depends(get_db)):
    case = _assigned_case(db, user, case_id, lock=True)
    if case.status != "assigned":
        raise _invalid(case)
    case.status = "investigating"
    _touch(db, case, user, "investigating", {})
    db.commit()
    return case


@router.post("/staff/cases/{case_id}/resolve", response_model=CaseOut, tags=["staff"])
def resolve(case_id: uuid.UUID, body: ResolveIn, user: User = Depends(support), db: Session = Depends(get_db)):
    case = _assigned_case(db, user, case_id, lock=True)
    if case.status not in ("assigned", "investigating"):
        raise _invalid(case)
    case.status, case.resolution = "resolved", body.resolution
    _touch(db, case, user, "resolved", {"resolution": body.resolution})
    db.commit()
    return case
