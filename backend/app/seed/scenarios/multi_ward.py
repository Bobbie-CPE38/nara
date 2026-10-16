"""The second ward, the Float Pool and the Supervisor (round 4 PR W4, docs/workflow.md 6.19, 6.21).

Call after golden_case.seed() on the same frozen demo clock. This creates neither
events nor cases nor candidate plans.

The Golden Case must plan exactly as with one ward (round 4 status, R4-Q38). Since
PR C1, every free person of another active ward joins the pool of an ICU shift, and
a person who fails a Hard Rule is listed in the plan's `skipped`. So everyone added
here holds a Medicine duty at the same times as ICU shifts 1 and 2. Since PR C2 that
makes them movable, so they reach the pool, but Medicine is exactly at its target:
each is skipped (SOURCE_WARD_MINIMUM_VIOLATION, or ROLE_MISMATCH for the head nurse
and the supervisor) and none is ever a candidate. The Float Pool ward has no shifts
of its own (6.19): its nurse works Medicine's shifts.
"""

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
    Ward,
)
from app.domain.enums import ActorType, AssignmentType, RosterStatus, StaffStatus
from app.seed import sync_sequences

MEDICINE_WARD = 2
FLOAT_POOL_WARD = 3
# SUPERVISOR is role 3, seeded by golden_case since round 4 PR S
SUPERVISOR_ROLE_ID = 3

# (staff ID, first name, role ID, home ward ID, skill IDs). RN = 1, HEAD_NURSE = 2
STAFF_DATA = (
    (301, "Niran", 1, MEDICINE_WARD, (1, 2)),
    (302, "Kanya", 1, MEDICINE_WARD, (2,)),
    (401, "Somchai", 1, FLOAT_POOL_WARD, (1, 2)),
    (902, "Ratana", 2, MEDICINE_WARD, ()),
    (950, "Prasert", SUPERVISOR_ROLE_ID, MEDICINE_WARD, ()),
)

# Medicine shift ID to the ICU shift whose times it copies. Only the times are
# copied, not the patient count. High IDs leave 3 and up to the scenarios and
# tests that add ICU shifts with explicit IDs
MIRRORED_SHIFTS = {21: 1, 22: 2}
# Every Medicine shift: 10 patients at 2 per nurse need the 5 people on duty
MEDICINE_PATIENT_COUNT = 10
MEDICINE_REQUIRED_STAFF = 5


def seed(db: Session) -> None:
    """Load the wards, people and Medicine roster, leaving commit to the caller."""
    now = clock.now()
    db.add_all(
        [
            Ward(id=MEDICINE_WARD, name="Medicine", is_active=True, created_at=now, updated_at=now),
            Ward(
                id=FLOAT_POOL_WARD,
                name="Float Pool",
                is_active=True,
                is_float_pool=True,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db.flush()
    for staff_id, first_name, role_id, ward_id, _ in STAFF_DATA:
        db.add(
            Staff(
                id=staff_id,
                first_name=first_name,
                last_name="Demo",
                email=f"{staff_id}@demo.local",
                password_hash="!",
                role_id=role_id,
                home_ward_id=ward_id,
                status=StaffStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    for staff_id, _, _, _, skill_ids in STAFF_DATA:
        db.add(Actor(name=str(staff_id), actor_type=ActorType.USER, staff_id=staff_id))
        db.add_all(StaffSkill(staff_id=staff_id, skill_id=skill_id) for skill_id in skill_ids)

    for shift_id, icu_shift_id in MIRRORED_SHIFTS.items():
        icu = db.get(Shift, icu_shift_id)
        assert icu is not None, "call golden_case.seed() first"
        db.add(
            Shift(
                id=shift_id,
                ward_id=MEDICINE_WARD,
                patient_count=MEDICINE_PATIENT_COUNT,
                start_at=icu.start_at,
                end_at=icu.end_at,
                shift_type=icu.shift_type,
                is_active=True,
                merge_window_seconds=0,
            )
        )
    db.flush()
    for shift_id in MIRRORED_SHIFTS:
        db.add(
            StaffingRequirement(
                id=shift_id,
                shift_id=shift_id,
                required_staff=MEDICINE_REQUIRED_STAFF,
                minimum_staff=4,
                created_at=now,
            )
        )
        db.flush()
        db.add(
            StaffingRequirementRole(staffing_requirement_id=shift_id, role_id=1, required_count=3)
        )
        db.add_all(
            RosterAssignment(
                staff_id=staff_id,
                shift_id=shift_id,
                status=RosterStatus.ASSIGNED,
                assignment_type=AssignmentType.REGULAR,
                candidate_source=None,
                created_at=now,
                updated_at=now,
            )
            for staff_id, *_ in STAFF_DATA
        )
    sync_sequences(
        db,
        [
            Ward.__tablename__,
            Staff.__tablename__,
            Shift.__tablename__,
            StaffingRequirement.__tablename__,
        ],
    )
