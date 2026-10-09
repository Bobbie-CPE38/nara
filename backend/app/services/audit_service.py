"""
Audit trail writer (docs/workflow.md, section 6.3 and decision D4).

Rules:
  * `log()` never commits. It shares the caller's session, so the work and its
    audit row succeed or fail together when the orchestrator commits the round.
  * `action` and `entity_type` must be enum members, never typed text.
  * `payload` must not contain individual patient data, free-text leave reasons
    or `password_hash`.
  * `payload` values must be JSON-serializable: send datetimes as `.isoformat()`.
  * `created_at` comes from the model default, `clock.now()` (D10).
"""

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog
from app.domain.enums import AuditAction, EntityType


def log(
    db: Session,
    *,
    case_id: int | None,
    actor_id: int,
    action: AuditAction,
    entity_type: EntityType,
    entity_id: int | None,
    payload: dict[str, Any],
) -> None:
    """Add one AUDIT_LOG row to the caller's transaction; flush but never commit."""
    # StrEnumText would otherwise accept a plain "CASE_OPENED" string
    if not isinstance(action, AuditAction):
        raise TypeError(f"action must be an AuditAction, got {action!r}")
    if not isinstance(entity_type, EntityType):
        raise TypeError(f"entity_type must be an EntityType, got {entity_type!r}")

    db.add(
        AuditLog(
            case_id=case_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
    )
    # Surface FK errors here, inside the caller's round, and make the row
    # visible to later queries (SessionLocal has autoflush=False)
    db.flush()
