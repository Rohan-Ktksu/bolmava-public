import hashlib
import hmac
import time
import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.models import Membership, Organization, StaffGrant, User

TOKEN_TTL_SECONDS = 12 * 3600
bearer = HTTPBearer(auto_error=False)


def _sign(payload: str) -> str:
    return hmac.new(settings.local_auth_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_local_token(user_id: uuid.UUID) -> tuple[str, int]:
    expires = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{user_id}.{expires}"
    return f"{payload}.{_sign(payload)}", expires


def _unauthenticated() -> AppError:
    return AppError(401, "unauthenticated", "Sign in again.")


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None:
        raise _unauthenticated()
    try:
        user_id, expires, sig = creds.credentials.split(".")
        ok = hmac.compare_digest(sig, _sign(f"{user_id}.{expires}")) and int(expires) > time.time()
        user = db.get(User, uuid.UUID(user_id)) if ok else None
    except (ValueError, TypeError):  # TypeError: compare_digest rejects non-ASCII signatures
        user = None
    if user is None or not user.is_fictional:
        raise _unauthenticated()
    return user


class Member:
    """The caller's membership in the organization named by the {org_id} path parameter."""

    def __init__(self, membership: Membership, org: Organization, user: User):
        self.role, self.org, self.user = membership.role, org, user

    def require(self, roles: tuple[str, ...], capability: str | None = None) -> None:
        if self.role not in roles:
            raise AppError(403, "forbidden", "Your role cannot do this.")
        if capability and not getattr(self.org, capability):
            raise AppError(403, "forbidden", f"This organization is not set up to {capability.removeprefix('can_')}.")


def member(org_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Member:
    row = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.org_id)
        .where(Membership.org_id == org_id, Membership.user_id == user.id)
    ).first()
    if row is None:
        raise AppError(404, "not_found", "Not found.")
    return Member(row[0], row[1], user)


def staff_roles(db: Session, user_id) -> list[str]:
    return db.scalars(
        select(StaffGrant.role).where(StaffGrant.user_id == user_id, StaffGrant.revoked_at.is_(None)).order_by(StaffGrant.role)
    ).all()


def staff(role: str):
    """Dependency: the caller must hold an active platform staff grant for `role`. Organization roles never count."""
    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if role not in staff_roles(db, user.id):
            raise AppError(403, "forbidden", f"This needs the platform {role} role.")
        return user
    return dependency
