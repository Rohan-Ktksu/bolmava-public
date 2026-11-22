import uuid

from sqlalchemy.orm import Session

from app.models import AuditEvent


def audit(db: Session, org_id, actor_id, action: str, entity_type: str, entity_id: uuid.UUID, data: dict) -> None:
    db.add(AuditEvent(org_id=org_id, actor_user_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id, data=data))
