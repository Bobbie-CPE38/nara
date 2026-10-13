"""Threshold scenario: a shift with more people than its workload needs.

Call after base_data.seed() and golden_case.seed(). Adds shift 3 and its rows;
nothing of the Golden Case is copied or changed. Used by tests in round 1
(docs/round1/round1-contract-draft.md, section 9.1).

Shift 3 has 2 patients and 3 nurses (101, 102, 103). With a ratio of 2 it needs
1 nurse, and its fixed floor minimum_staff is 3. What that makes possible:

  * One nurse leaves: 2 are left, below the floor, but 2 patients per 2 nurses
    is within the ratio and the one required RN is there. No event passes the
    threshold, so no case opens (Q32).
  * The patient count goes to 8 and then to 6 in one window: the first event
    passes (8 > 2 * 3), the second one makes 3 nurses enough again, and the
    window ends without a case.
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

SHIFT_ID = 3
REQUIREMENT_ID = 3
MERGE_WINDOW_SECONDS = 600
STAFF_IDS = (101, 102, 103)
RN_ROLE_ID = 1


def seed(db: Session) -> None:
    """Add the over-staffed evening shift, leaving the commit to the caller."""
    now = clock.now()
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    db.add(
        Shift(
            id=SHIFT_ID,
            ward_id=1,
            patient_count=2,
            start_at=day + timedelta(days=3, hours=15),
            end_at=day + timedelta(days=3, hours=23),
            shift_type=ShiftType.EVENING,
            is_active=True,
            merge_window_seconds=MERGE_WINDOW_SECONDS,
        )
    )
    db.flush()
    db.add(
        StaffingRequirement(
            id=REQUIREMENT_ID,
            shift_id=SHIFT_ID,
            required_staff=1,
            minimum_staff=3,
            created_at=now,
        )
    )
    db.flush()
    db.add(
        StaffingRequirementRole(
            staffing_requirement_id=REQUIREMENT_ID, role_id=RN_ROLE_ID, required_count=1
        )
    )
    db.add_all(
        RosterAssignment(
            staff_id=staff_id,
            shift_id=SHIFT_ID,
            status=RosterStatus.ASSIGNED,
            assignment_type=AssignmentType.REGULAR,
            candidate_source=None,
            created_at=now,
            updated_at=now,
        )
        for staff_id in STAFF_IDS
    )
    sync_sequences(db, [Shift.__tablename__, StaffingRequirement.__tablename__])
