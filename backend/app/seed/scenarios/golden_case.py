"""The initial, pre-leave ICU roster from docs/workflow.md section 10.2.

Call after base_data.seed() on a fresh database with the demo clock frozen at
D 21:00 +07:00. This creates neither events nor cases nor candidate plans.
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    Actor,
    Role,
    RosterAssignment,
    Shift,
    Skill,
    Staff,
    StaffingRequirement,
    StaffingRequirementRole,
    StaffingRequirementSkill,
    StaffSkill,
    Ward,
)
from app.domain.enums import ActorType, AssignmentType, RosterStatus, ShiftType, StaffStatus
from app.seed import sync_sequences

# (staff ID, first name, role ID, skill IDs). Last names are absent from the contract.
STAFF_DATA = (
    (101, "Pimchanok", 1, (1, 2)),
    (102, "Thanaphon", 1, (1,)),
    (103, "Wanna", 1, (2,)),
    (104, "Kitti", 1, (2,)),
    (105, "Sudarat", 1, (2,)),
    (201, "Arunee", 1, (1, 2)),
    (202, "Phanu", 1, (2,)),
    (203, "Chonthicha", 1, (1,)),
    (900, "Malai", 2, ()),
)


def seed(db: Session) -> None:
    """Load the documented roster, leaving commit and clock setup to the caller."""
    now = clock.now()
    if not clock.is_frozen() or (now.hour, now.minute, now.second, now.microsecond) != (
        21,
        0,
        0,
        0,
    ):
        raise ValueError("Freeze the demo clock at D 21:00 +07:00 before seeding")
    day = now.replace(hour=0)
    db.add_all(
        [
            Ward(id=1, name="ICU", is_active=True, created_at=now, updated_at=now),
            Role(id=1, name="RN"),
            Role(id=2, name="HEAD_NURSE"),
            Skill(id=1, name="ICU"),
            Skill(id=2, name="BLS"),
        ]
    )
    db.flush()
    for staff_id, first_name, role_id, _ in STAFF_DATA:
        db.add(
            Staff(
                id=staff_id,
                first_name=first_name,
                last_name="Demo",
                email=f"{staff_id}@demo.local",
                password_hash="!",
                role_id=role_id,
                home_ward_id=1,
                status=StaffStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    for staff_id, _, _, skill_ids in STAFF_DATA:
        db.add(Actor(name=str(staff_id), actor_type=ActorType.USER, staff_id=staff_id))
        db.add_all(StaffSkill(staff_id=staff_id, skill_id=skill_id) for skill_id in skill_ids)
    db.add_all(
        [
            Shift(
                id=1,
                ward_id=1,
                patient_count=10,
                start_at=day + timedelta(hours=23),
                end_at=day + timedelta(days=1, hours=7),
                shift_type=ShiftType.NIGHT,
                is_active=True,
            ),
            Shift(
                id=2,
                ward_id=1,
                patient_count=2,
                start_at=day + timedelta(days=2, hours=7),
                end_at=day + timedelta(days=2, hours=15),
                shift_type=ShiftType.DAY,
                is_active=True,
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            StaffingRequirement(
                id=1, shift_id=1, required_staff=5, minimum_staff=4, created_at=now
            ),
            StaffingRequirement(
                id=2, shift_id=2, required_staff=1, minimum_staff=1, created_at=now
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            StaffingRequirementRole(staffing_requirement_id=1, role_id=1, required_count=5),
            StaffingRequirementRole(staffing_requirement_id=2, role_id=1, required_count=1),
            StaffingRequirementSkill(staffing_requirement_id=1, skill_id=1, required_count=2),
        ]
    )
    for shift_id, staff_ids in ((1, (101, 102, 103, 104, 105)), (2, (202, 203))):
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
            for staff_id in staff_ids
        )
    sync_sequences(
        db,
        [
            Ward.__tablename__,
            Role.__tablename__,
            Skill.__tablename__,
            Staff.__tablename__,
            Shift.__tablename__,
            StaffingRequirement.__tablename__,
        ],
    )
