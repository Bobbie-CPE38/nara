"""
Unplanned leave of a staff member on an assigned shift (docs/workflow.md, section 3).

Writes the STAFF_UNAVAILABILITY row and cancels the roster row. The caller
(event_service) owns the audit rows and the transaction.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RosterAssignment, Shift, StaffUnavailability
from app.domain.enums import AvailabilityReason, RosterStatus


class NoAssignedRosterError(LookupError):
    """The staff member has no ASSIGNED roster row in the shift.

    Also what a repeated leave report finds: the first one already cancelled the row.
    """


def lock_assigned_roster(db: Session, *, staff_id: int, shift_id: int) -> RosterAssignment:
    """Return the staff member's one ASSIGNED roster row in the shift, locked.

    The row lock makes two leave reports for the same person and shift run one
    after the other. PostgreSQL re-checks the status once the first commits, so
    the second finds no ASSIGNED row and raises NoAssignedRosterError.
    """
    rows = db.scalars(
        select(RosterAssignment)
        .where(
            RosterAssignment.staff_id == staff_id,
            RosterAssignment.shift_id == shift_id,
            RosterAssignment.status == RosterStatus.ASSIGNED,
        )
        .with_for_update(key_share=True)
    ).all()
    if not rows:
        raise NoAssignedRosterError(
            f"Staff {staff_id} has no assigned roster row in shift {shift_id}"
        )
    if len(rows) > 1:
        raise RuntimeError(
            f"Staff {staff_id} has {len(rows)} assigned roster rows in shift {shift_id}"
        )
    return rows[0]


def record_unplanned_leave(
    db: Session, *, roster: RosterAssignment, shift: Shift, end_at: datetime | None
) -> StaffUnavailability:
    """Create the unavailability period and cancel the roster row. Flush, never commit.

    `end_at` is the return time the staff member gave. Without one the period
    ends with the shift.
    """
    unavailability = StaffUnavailability(
        staff_id=roster.staff_id,
        start_at=shift.start_at,
        end_at=end_at if end_at is not None else shift.end_at,
        # It overlaps an assigned shift, so it is unplanned by definition
        reason=AvailabilityReason.UNPLANNED_LEAVE,
    )
    db.add(unavailability)
    roster.status = RosterStatus.CANCELLED
    db.flush()
    return unavailability
