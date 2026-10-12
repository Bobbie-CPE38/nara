"""201 accepts, then fails Safety (round 1 contract, section 9.1; case ข of workflow.md 7.3).

Call after base_data.seed() and golden_case.seed(). Tests only (Q16).
seed() adds an extra shift inside the night shift with nobody on it, so 201 still
passes the Solver and gets an offer of wave 1 together with 202.
take_clashing_shift() is the event in the middle: while the offer waits, 201 is
rostered on the extra shift. When 201 then accepts, Safety fails with SHIFT_CONFLICT
and 202, who accepts next, goes on to approval.
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    RosterAssignment,
    Shift,
    StaffingRequirement,
    StaffingRequirementRole,
)
from app.domain.enums import AssignmentType, RosterStatus, ShiftType
from app.seed import sync_sequences

NIGHT_SHIFT_ID = 1
CLASH_SHIFT_ID = 3
CLASHING_STAFF_ID = 201


def seed(db: Session) -> None:
    """Add the extra shift on top of the Golden Case; flush but never commit."""
    night = db.get(Shift, NIGHT_SHIFT_ID)
    if night is None:
        raise LookupError("Load the Golden Case before this scenario")
    # Starts an hour into the night shift and lasts four hours, so the only rule 201
    # breaks is SHIFT_CONFLICT (an eight-hour shift on the same day would also break
    # DAILY_HOURS_EXCEEDED)
    db.add(
        Shift(
            id=CLASH_SHIFT_ID,
            ward_id=night.ward_id,
            patient_count=2,
            start_at=night.start_at + timedelta(hours=1),
            end_at=night.start_at + timedelta(hours=5),
            shift_type=ShiftType.NIGHT,
            is_active=True,
        )
    )
    db.flush()
    db.add(
        StaffingRequirement(
            id=3, shift_id=CLASH_SHIFT_ID, required_staff=1, minimum_staff=1, created_at=clock.now()
        )
    )
    db.flush()
    db.add(StaffingRequirementRole(staffing_requirement_id=3, role_id=1, required_count=1))
    sync_sequences(db, [Shift.__tablename__, StaffingRequirement.__tablename__])


def take_clashing_shift(db: Session, staff_id: int = CLASHING_STAFF_ID) -> None:
    """The event in the middle: the candidate is rostered on the clashing shift."""
    now = clock.now()
    db.add(
        RosterAssignment(
            staff_id=staff_id,
            shift_id=CLASH_SHIFT_ID,
            status=RosterStatus.ASSIGNED,
            assignment_type=AssignmentType.REGULAR,
            candidate_source=None,
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()
