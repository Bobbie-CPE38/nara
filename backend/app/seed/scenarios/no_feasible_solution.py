"""Nobody can take the night shift (round 1 contract, section 9.1; case จ of workflow.md 7.3).

Call after base_data.seed() and golden_case.seed(). Tests only (Q16).
When 105 then reports leave for shift 1, the Solver finds no candidate:
  * 201 is on planned leave over the shift          -> UNAVAILABLE
  * 202 works the evening shift that ends at 23:00  -> INSUFFICIENT_REST
  * 203 no longer works here                        -> STAFF_NOT_ACTIVE
The staff on the shift and the head nurse were never candidates.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    RosterAssignment,
    Shift,
    Staff,
    StaffingRequirement,
    StaffingRequirementRole,
    StaffUnavailability,
)
from app.domain.enums import (
    AssignmentType,
    AvailabilityReason,
    RosterStatus,
    ShiftType,
    StaffStatus,
)
from app.seed import sync_sequences

NIGHT_SHIFT_ID = 1
EVENING_SHIFT_ID = 3


def seed(db: Session) -> None:
    """Add the rows on top of the Golden Case; flush but never commit."""
    night = db.get(Shift, NIGHT_SHIFT_ID)
    if night is None:
        raise LookupError("Load the Golden Case before this scenario")
    now = clock.now()
    db.add(
        Shift(
            id=EVENING_SHIFT_ID,
            ward_id=night.ward_id,
            patient_count=2,
            start_at=night.start_at - timedelta(hours=8),
            end_at=night.start_at,
            shift_type=ShiftType.EVENING,
            is_active=True,
        )
    )
    db.flush()
    db.add(
        StaffingRequirement(
            id=3, shift_id=EVENING_SHIFT_ID, required_staff=1, minimum_staff=1, created_at=now
        )
    )
    db.flush()
    db.add_all(
        [
            StaffingRequirementRole(staffing_requirement_id=3, role_id=1, required_count=1),
            RosterAssignment(
                staff_id=202,
                shift_id=EVENING_SHIFT_ID,
                status=RosterStatus.ASSIGNED,
                assignment_type=AssignmentType.REGULAR,
                candidate_source=None,
                created_at=now,
                updated_at=now,
            ),
            StaffUnavailability(
                staff_id=201,
                start_at=night.start_at - timedelta(days=1),
                end_at=night.end_at + timedelta(days=1),
                reason=AvailabilityReason.PLANNED_LEAVE,
            ),
        ]
    )
    leaver = db.get(Staff, 203)
    if leaver is None:
        raise LookupError("Load the Golden Case before this scenario")
    leaver.status = StaffStatus.INACTIVE
    # Deactivating someone cancels their future assignments (coverage.py)
    for row in db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == 203, RosterAssignment.status == RosterStatus.ASSIGNED
        )
    ):
        row.status = RosterStatus.CANCELLED
    sync_sequences(db, [Shift.__tablename__, StaffingRequirement.__tablename__])
