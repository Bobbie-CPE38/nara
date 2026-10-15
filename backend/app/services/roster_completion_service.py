"""Ended roster intervals become COMPLETED (workflow.md sections 3.8 and 6.20).

Called by job_service.run_due_work() every tick. COMPLETED counts like ASSIGNED
everywhere (COMMITTED_ROSTER_STATUSES, COVERING_ROSTER_STATUSES), so the change
moves no gap, fatigue check or score. No audit row: no AuditAction names this
change, and the roster row keeps it in updated_at.

A row with a queued staff event (STAFF_UNAVAILABLE or ASSIGNMENT_CANCELLED still
RECEIVED) is not completed: closing the window needs it ASSIGNED
(merge_window_service._assigned_roster), or the accepted report would be
ignored as NO_ASSIGNED_ROSTER. The row is completed on the first tick after
its events are processed or ignored, also when an active case keeps the window
waiting past the end of the shift.
"""

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import RosterAssignment, Shift, StaffingEvent
from app.domain.enums import STAFF_EVENT_TYPES, EventStatus, RosterStatus
from app.services import roster_time_service


def complete_ended_shifts(db: Session) -> list[int]:
    """Complete ASSIGNED rows at their effective end (actual end, else shift end); commit.

    Rows of a person with a queued staff event on the shift are left as they are.

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
            .where(
                RosterAssignment.status == RosterStatus.ASSIGNED,
                roster_time_service.end_at() <= now,
                ~exists().where(
                    StaffingEvent.shift_id == RosterAssignment.shift_id,
                    StaffingEvent.staff_id == RosterAssignment.staff_id,
                    StaffingEvent.event_type.in_(list(STAFF_EVENT_TYPES)),
                    StaffingEvent.status == EventStatus.RECEIVED,
                ),
            )
            .order_by(RosterAssignment.id)
            .with_for_update(of=RosterAssignment, skip_locked=True)
        )
    )
    for row in rows:
        row.status = RosterStatus.COMPLETED
    db.commit()
    return [row.id for row in rows]
