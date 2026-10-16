"""Check-ins of everyone on a shift that has already started (docs/workflow.md, 6.24).

Call last, on the frozen demo clock, after the other loaders. Each ASSIGNED roster
row whose shift is running gets an on-time ATTENDANCE row and its audit row, written
by the same function as a real check-in. At reset the clock is D 21:00 and the
earliest seeded shift starts at D 23:00, so this writes nothing today.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import RosterAssignment, Shift
from app.domain.enums import ActorName, CheckInSource, RosterStatus
from app.services import actor_service, attendance_service


def seed(db: Session) -> None:
    """Write the check-ins, leaving the commit to the caller."""
    now = clock.now()
    rows = db.execute(
        select(RosterAssignment, Shift)
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .where(RosterAssignment.status == RosterStatus.ASSIGNED)
        .order_by(RosterAssignment.id)
    ).all()
    actor_id: int | None = None
    for roster, shift in rows:
        if not shift.start_at <= now < attendance_service.effective_end_at(roster, shift):
            continue
        if actor_id is None:
            actor_id = actor_service.component_id(db, ActorName.SYSTEM)
        attendance_service.record(
            db,
            roster=roster,
            shift=shift,
            check_in_at=attendance_service.required_arrival_at(roster, shift),
            source=CheckInSource.SIMULATED,
            actor_id=actor_id,
        )
