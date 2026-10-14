"""Roster rows of ended shifts become COMPLETED (round 3 PR R, workflow.md section 3.8).

Called by job_service.run_due_work() every tick. COMPLETED counts like ASSIGNED
everywhere (COMMITTED_ROSTER_STATUSES, COVERING_ROSTER_STATUSES), so the change
moves no gap, fatigue check or score. No audit row: no AuditAction names this
change, and the roster row keeps it in updated_at.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import RosterAssignment, Shift
from app.domain.enums import RosterStatus


def complete_ended_shifts(db: Session) -> list[int]:
    """Set ASSIGNED rows whose shift ended (end_at <= backend clock) to COMPLETED; commit.

    Rows another transaction holds (a leave report cancelling the row) are
    skipped and picked up on a later tick, so this never waits on a lock and
    never takes rows out of the shift → roster order of event intake.
    Returns the completed row IDs in ID order.
    """
    now = clock.now()
    rows = list(
        db.scalars(
            select(RosterAssignment)
            .join(Shift, Shift.id == RosterAssignment.shift_id)
            .where(RosterAssignment.status == RosterStatus.ASSIGNED, Shift.end_at <= now)
            .order_by(RosterAssignment.id)
            .with_for_update(of=RosterAssignment, skip_locked=True)
        )
    )
    for row in rows:
        row.status = RosterStatus.COMPLETED
    db.commit()
    return [row.id for row in rows]
