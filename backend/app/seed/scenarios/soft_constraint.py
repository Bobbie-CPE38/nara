"""Equal Hard Rule results, different first waves (round 1 contract, sections 8.3 and 9.1).

Call after base_data.seed() and golden_case.seed(). Tests only (Q16).
201 already worked three day shifts this week (Monday to Wednesday), 24 hours.
202 and 203 only have their Golden Case shift. When 105 then reports leave for
shift 1, all three pass the Hard Rules, but with the seeded weights the first
wave is 202 + 203 instead of 201 + 202.

ignore_workload() switches the workload weight off. The first wave is then
201 + 202, while rank still lists 202 before 201: plan_penalty picks the group,
ranking_key orders it.

The demo day must be Thursday or later, so that Monday to Wednesday lie in the
same week before it. The tests freeze the clock on a Friday.
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    RosterAssignment,
    Shift,
    SoftConstraintPolicy,
    StaffingRequirement,
    StaffingRequirementRole,
)
from app.domain.constraints.context import week_start
from app.domain.enums import AssignmentType, RosterStatus, ShiftType
from app.seed import sync_sequences

BUSY_STAFF_ID = 201
# Monday, Tuesday, Wednesday
WORKED_SHIFT_IDS = (3, 4, 5)


def seed(db: Session) -> None:
    """Add the rows on top of the Golden Case; flush but never commit."""
    now = clock.now()
    if now.weekday() < 3:
        raise ValueError("The soft constraint scenario needs a demo day of Thursday or later")
    monday = week_start(now)
    for day, shift_id in enumerate(WORKED_SHIFT_IDS):
        start_at = monday + timedelta(days=day, hours=7)
        db.add(
            Shift(
                id=shift_id,
                ward_id=1,
                patient_count=2,
                start_at=start_at,
                end_at=start_at + timedelta(hours=8),
                shift_type=ShiftType.DAY,
                is_active=True,
            )
        )
    db.flush()
    for shift_id in WORKED_SHIFT_IDS:
        db.add(
            StaffingRequirement(
                id=shift_id, shift_id=shift_id, required_staff=1, minimum_staff=1, created_at=now
            )
        )
    db.flush()
    for shift_id in WORKED_SHIFT_IDS:
        db.add_all(
            [
                StaffingRequirementRole(
                    staffing_requirement_id=shift_id, role_id=1, required_count=1
                ),
                RosterAssignment(
                    staff_id=BUSY_STAFF_ID,
                    shift_id=shift_id,
                    status=RosterStatus.ASSIGNED,
                    assignment_type=AssignmentType.REGULAR,
                    candidate_source=None,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
    sync_sequences(db, [Shift.__tablename__, StaffingRequirement.__tablename__])


def ignore_workload(db: Session) -> None:
    """Set workload_imbalance_weight of the demo soft policy to 0; flush only."""
    policy = db.get(SoftConstraintPolicy, 1)
    if policy is None:
        raise LookupError("Soft constraint policy id=1 is missing; load the demo seed")
    policy.workload_imbalance_weight = Decimal(0)
    db.flush()
