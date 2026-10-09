"""
Actor lookups for the audit trail (docs/workflow.md, section 6.3).

Every AUDIT_LOG row needs an `actor_id`. These helpers turn "who did it" into
that ID: a system/component name, or the staff member behind a request.

Rules:
  * Read-only. Nothing here adds, flushes or commits.
  * A missing actor raises ActorNotFoundError: the seed data is incomplete, so
    the caller must not continue (the orchestrator turns it into FAILED, D11).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Actor
from app.domain.enums import ActorName, ActorType


class ActorNotFoundError(LookupError):
    """No ACTORS row matches. base_data / golden_case seed one per name and per staff."""


def component_id(db: Session, name: ActorName) -> int:
    """Return ACTORS.id of a non-user actor (the system or a component)."""
    # A plain string could match a user actor, whose name is str(staff.id)
    if not isinstance(name, ActorName):
        raise TypeError(f"name must be an ActorName, got {name!r}")

    actor_id = db.scalar(
        select(Actor.id).where(Actor.name == name.value, Actor.actor_type != ActorType.USER)
    )
    if actor_id is None:
        raise ActorNotFoundError(f"No actor named {name.value!r}")
    return actor_id


def user_id(db: Session, staff_id: int) -> int:
    """Return ACTORS.id of the user actor that belongs to a staff member."""
    actor_id = db.scalar(select(Actor.id).where(Actor.staff_id == staff_id))
    if actor_id is None:
        raise ActorNotFoundError(f"No actor for staff {staff_id}")
    return actor_id
