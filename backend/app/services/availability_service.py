"""
Can a staff member take a shift at all? (docs/workflow.md, section 8)

One rule set for the steps that pick or confirm a replacement: the Solver drops
candidates that break it, and Safety re-checks the accepted candidate, because
the situation can change while the offer waits for an answer. A staff member is
unavailable for a shift when they:
  1. are not ACTIVE,
  2. already have a roster row on that shift in COMMITTED_ROSTER_STATUSES,
  3. have STAFF_UNAVAILABILITY overlapping the shift (no end_at = from start_at on).

Rules:
  * Read-only. Nothing here adds, flushes or commits.
  * Clashes with other shifts (rest time, double booking) are left to the real
    hard rules after the skeleton.
  * PENDING_APPROVAL counts as committed. Nothing writes it in the skeleton; a
    later step that writes it for the accepted candidate before Safety must
    exclude that row, or rule 2 blocks the candidate on their own assignment.
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import RosterAssignment, Shift, Staff, StaffUnavailability
from app.domain.enums import COMMITTED_ROSTER_STATUSES, StaffStatus


class CandidateNotAvailableError(ValueError):
    """The staff member cannot take the shift. The subclass names the rule."""


class StaffNotActiveError(CandidateNotAvailableError):
    """Rule 1: the staff member is not ACTIVE."""


class StaffAlreadyOnShiftError(CandidateNotAvailableError):
    """Rule 2: the staff member is already rostered on the shift."""


class StaffUnavailableError(CandidateNotAvailableError):
    """Rule 3: STAFF_UNAVAILABILITY overlaps the shift."""


def unavailable_staff(
    db: Session, shift: Shift, staff_ids: list[int]
) -> dict[int, type[CandidateNotAvailableError]]:
    """Map each staff ID that cannot take the shift to the first rule it breaks.

    Staff IDs that are absent from the result are available.
    """
    active = set(
        db.scalars(
            select(Staff.id).where(Staff.id.in_(staff_ids), Staff.status == StaffStatus.ACTIVE)
        )
    )
    on_shift = set(
        db.scalars(
            select(RosterAssignment.staff_id).where(
                RosterAssignment.staff_id.in_(staff_ids),
                RosterAssignment.shift_id == shift.id,
                RosterAssignment.status.in_(list(COMMITTED_ROSTER_STATUSES)),
            )
        )
    )
    on_leave = set(
        db.scalars(
            select(StaffUnavailability.staff_id).where(
                StaffUnavailability.staff_id.in_(staff_ids),
                StaffUnavailability.start_at < shift.end_at,
                or_(
                    StaffUnavailability.end_at.is_(None),
                    StaffUnavailability.end_at > shift.start_at,
                ),
            )
        )
    )

    blocked: dict[int, type[CandidateNotAvailableError]] = {}
    for staff_id in staff_ids:
        if staff_id not in active:
            blocked[staff_id] = StaffNotActiveError
        elif staff_id in on_shift:
            blocked[staff_id] = StaffAlreadyOnShiftError
        elif staff_id in on_leave:
            blocked[staff_id] = StaffUnavailableError
    return blocked


def assert_available(db: Session, shift: Shift, staff_id: int) -> None:
    """Raise the error of the first rule the staff member breaks for the shift."""
    error = unavailable_staff(db, shift, [staff_id]).get(staff_id)
    if error is not None:
        raise error(f"Staff {staff_id} cannot take shift {shift.id}")
