from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth import Member, current_user, issue_local_token, member, staff_roles
from app.catalog import lock_idempotency_key
from app.db import get_db
from app.errors import AppError
from app.models import Membership, Organization, User
from app.schemas import LocalSessionIn, LocalUser, MeOut, OrgIn, OrgOut, TokenOut

local_router = APIRouter(prefix="/api/v1/auth/local", tags=["local auth (non-production)"])
router = APIRouter(prefix="/api/v1", tags=["identity"])


@local_router.get("/users", response_model=list[LocalUser])
def local_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).where(User.is_fictional).order_by(User.email)).all()


@local_router.post("/session", response_model=TokenOut)
def local_session(body: LocalSessionIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower(), User.is_fictional))
    if user is None:
        raise AppError(401, "unauthenticated", "No fictional demo user has this email.")
    token, expires = issue_local_token(user.id)
    return TokenOut(access_token=token, expires_at=datetime.fromtimestamp(expires, UTC))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Membership.role, Organization)
        .join(Organization, Organization.id == Membership.org_id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.name)
    ).all()
    memberships = [{"role": role, "organization": OrgOut.model_validate(org)} for role, org in rows]
    return MeOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        preferred_language=user.preferred_language,
        memberships=memberships,
        staff_roles=staff_roles(db, user.id),
    )


@router.post("/orgs", response_model=OrgOut, status_code=201)
def create_org(
    body: OrgIn,
    response: Response,
    idempotency_key: str | None = Header(None, min_length=1, max_length=80),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Optional Idempotency-Key: the same person retrying with the same key gets the same organization back (200)."""
    if idempotency_key:
        lock_idempotency_key(db, user.id, idempotency_key)  # concurrent retries wait for the first to commit
        prior = db.scalar(select(Organization).where(Organization.created_by == user.id, Organization.idempotency_key == idempotency_key))
        if prior:
            if {k: getattr(prior, k) for k in OrgIn.model_fields} != body.model_dump():
                raise AppError(409, "idempotency_key_reused", "This Idempotency-Key was already used for a different request.")
            response.status_code = 200
            return prior
    org = Organization(created_by=user.id, idempotency_key=idempotency_key, **body.model_dump())
    db.add(org)
    db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role="admin"))
    audit(db, org.id, user.id, "org.created", "organization", org.id, body.model_dump())
    db.commit()
    return org


@router.get("/orgs/{org_id}", response_model=OrgOut)
def get_org(m: Member = Depends(member)):
    return m.org
