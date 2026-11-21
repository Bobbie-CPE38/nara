"""The cross-ward test-run scenario (round 6 PR EV5a, docs/workflow.md 6.35.3).

Call after load() on the same frozen demo clock. Like multi_ward, this creates
neither events nor cases: the test run reports the leave of 105 afterwards.

multi_ward alone never gives a cross-ward candidate: Medicine is exactly at its
target, so everyone there is skipped. This scenario changes two facts:

- 201, 202 and 203, the free ICU nurses, worked an ICU day shift that ended four
  hours before the night shift, so each fails INSUFFICIENT_REST on it.
- Malee (303), a Medicine RN with the ICU skill, joins both Medicine shifts, so
  Medicine has one person above its target and one of them may move.

The plan for the night shift then has only FLOAT_POOL and CROSS_WARD candidates,
and every one of them has a source assignment in Medicine: both wards must approve.
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    Actor,
    RosterAssignment,
    Shift,
    Staff,
    StaffingRequirement,
    StaffingRequirementRole,
    StaffSkill,
)
from app.domain.enums import ActorType, AssignmentType, RosterStatus, ShiftType, StaffStatus
from app.seed import staff_subject, sync_sequences
from app.seed.scenarios.multi_ward import MEDICINE_WARD, MIRRORED_SHIFTS

ICU_WARD = 1
NIGHT_SHIFT = 1
# Free above 3 (multi_ward's note); 31 is the day shift before the night shift
TIRED_DAY_SHIFT = 31
TIRED_NURSES = (201, 202, 203)
# The day shift ends this long before the night shift starts: under the 11 hours of rest
REST_BEFORE_NIGHT = timedelta(hours=4)
DAY_SHIFT_LENGTH = timedelta(hours=8)
EXTRA_MEDICINE_RN = 303


def seed(db: Session) -> None:
    """Add the tired ICU day shift and the extra Medicine RN, leaving commit to the caller."""
    now = clock.now()
    night = db.get(Shift, NIGHT_SHIFT)
    assert night is not None, "call load() first"
    day_end = night.start_at - REST_BEFORE_NIGHT
    db.add(
        Shift(
            id=TIRED_DAY_SHIFT,
            ward_id=ICU_WARD,
            patient_count=2,
            start_at=day_end - DAY_SHIFT_LENGTH,
            end_at=day_end,
            shift_type=ShiftType.DAY,
            is_active=True,
            merge_window_seconds=0,
        )
    )
    db.flush()
    db.add(
        StaffingRequirement(
            id=TIRED_DAY_SHIFT,
            shift_id=TIRED_DAY_SHIFT,
            required_staff=len(TIRED_NURSES),
            minimum_staff=len(TIRED_NURSES),
            created_at=now,
        )
    )
    db.flush()
    db.add(
        StaffingRequirementRole(
            staffing_requirement_id=TIRED_DAY_SHIFT, role_id=1, required_count=len(TIRED_NURSES)
        )
    )
    # Over before the clock reaches D 21:00, as the job's shift completion would leave them
    db.add_all(
        RosterAssignment(
            staff_id=staff_id,
            shift_id=TIRED_DAY_SHIFT,
            status=RosterStatus.COMPLETED,
            assignment_type=AssignmentType.REGULAR,
            candidate_source=None,
            created_at=now,
            updated_at=now,
        )
        for staff_id in TIRED_NURSES
    )

    db.add(
        Staff(
            id=EXTRA_MEDICINE_RN,
            first_name="Malee",
            last_name="Demo",
            email=f"{EXTRA_MEDICINE_RN}@demo.local",
            password_hash="!",
            role_id=1,
            home_ward_id=MEDICINE_WARD,
            status=StaffStatus.ACTIVE,
            auth_subject=staff_subject(db, EXTRA_MEDICINE_RN),
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()
    db.add(
        Actor(name=str(EXTRA_MEDICINE_RN), actor_type=ActorType.USER, staff_id=EXTRA_MEDICINE_RN)
    )
    # ICU (1) and BLS (2), like Niran
    db.add_all(StaffSkill(staff_id=EXTRA_MEDICINE_RN, skill_id=skill_id) for skill_id in (1, 2))
    db.add_all(
        RosterAssignment(
            staff_id=EXTRA_MEDICINE_RN,
            shift_id=shift_id,
            status=RosterStatus.ASSIGNED,
            assignment_type=AssignmentType.REGULAR,
            candidate_source=None,
            created_at=now,
            updated_at=now,
        )
        for shift_id in MIRRORED_SHIFTS
    )
    sync_sequences(
        db,
        [Staff.__tablename__, Shift.__tablename__, StaffingRequirement.__tablename__],
    )
