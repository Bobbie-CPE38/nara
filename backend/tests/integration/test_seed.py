"""Seed the real PostgreSQL schema and verify the demo's staffing preconditions."""

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.base import Base
from app.db.models import (
    Actor,
    ApprovalPolicy,
    HardConstraintPolicy,
    Role,
    RosterAssignment,
    Shift,
    SoftConstraintPolicy,
    Staff,
    StaffingCase,
    StaffingEvent,
    StaffingRequirement,
    StaffSkill,
)
from app.domain.enums import ActorName, ActorType, RosterStatus, StaffStatus
from app.seed import base_data, load
from app.seed.scenarios import golden_case

DEMO_TIME = datetime(2026, 10, 9, 21, tzinfo=clock.APP_TIMEZONE)


@pytest.fixture(autouse=True)
def demo_clock() -> Iterator[None]:
    clock.set_time(DEMO_TIME)
    yield
    clock.reset()


@pytest.fixture
def seeded(db: Session) -> Session:
    # Until the first migration lands, create tables inside the test transaction.
    Base.metadata.create_all(db.connection())
    load(db)
    db.expire_all()
    return db


def test_seed_has_all_actor_identities_and_policies(seeded: Session) -> None:
    actors = seeded.scalars(select(Actor)).all()
    assert len(actors) == 15
    components = {actor.name for actor in actors if actor.staff_id is None}
    assert components == {name.value for name in ActorName}
    assert next(actor for actor in actors if actor.name == "system").actor_type is ActorType.SYSTEM
    for staff in seeded.scalars(select(Staff)):
        actor = next(actor for actor in actors if actor.staff_id == staff.id)
        assert actor.name == str(staff.id)
        assert actor.actor_type is ActorType.USER
        assert staff.status is StaffStatus.ACTIVE
        assert staff.password_hash == "!"
        assert staff.created_at == DEMO_TIME
    for model in (HardConstraintPolicy, SoftConstraintPolicy, ApprovalPolicy):
        assert seeded.scalar(select(func.count()).select_from(model)) == 1
    approval = seeded.get(ApprovalPolicy, 1)
    assert approval is not None
    assert approval.ratio == 2
    assert approval.incoming_count == 10
    hard = seeded.get(HardConstraintPolicy, 1)
    assert hard is not None
    assert (hard.minimum_rest_hours, hard.maximum_daily_hours, hard.maximum_weekly_hours) == (
        11,
        12,
        52,
    )


def test_roster_supports_the_gap_and_no_gap_demo_paths(seeded: Session) -> None:
    requirement = seeded.get(StaffingRequirement, 1)
    assert requirement is not None
    shift_one = seeded.scalars(select(RosterAssignment).where(RosterAssignment.shift_id == 1)).all()
    assert {row.staff_id for row in shift_one} == {101, 102, 103, 104, 105}
    icu_staff = set(seeded.scalars(select(StaffSkill.staff_id).where(StaffSkill.skill_id == 1)))
    assert {row.staff_id for row in shift_one} & icu_staff == {101, 102}
    assert requirement.required_staff == len(shift_one) == 5
    next(row for row in shift_one if row.staff_id == 105).status = RosterStatus.CANCELLED
    assert (
        requirement.required_staff - sum(row.status == RosterStatus.ASSIGNED for row in shift_one)
        == 1
    )

    shift_two = seeded.scalars(select(RosterAssignment).where(RosterAssignment.shift_id == 2)).all()
    assert {row.staff_id for row in shift_two} == {202, 203}
    next(row for row in shift_two if row.staff_id == 203).status = RosterStatus.CANCELLED
    assert sum(row.status == RosterStatus.ASSIGNED for row in shift_two) == 1
    assert seeded.scalar(select(func.count()).select_from(StaffingEvent)) == 0
    assert seeded.scalar(select(func.count()).select_from(StaffingCase)) == 0


def test_shift_times_and_generated_ids_after_seed(seeded: Session) -> None:
    night = seeded.get(Shift, 1)
    day = seeded.get(Shift, 2)
    assert night is not None and day is not None
    assert night.start_at == DEMO_TIME + timedelta(hours=2)
    assert night.end_at == DEMO_TIME + timedelta(hours=10)
    assert day.start_at == DEMO_TIME + timedelta(days=1, hours=10)
    assert day.end_at - day.start_at == timedelta(hours=8)
    # Explicit seed IDs must not collide with subsequent generated IDs.
    role = Role(name="NEW_ROLE")
    seeded.add(role)
    seeded.flush()
    assert role.id > 2
    staff = Staff(
        first_name="New",
        last_name="Demo",
        email="new@demo.local",
        password_hash="!",
        role_id=1,
        home_ward_id=1,
        status=StaffStatus.ACTIVE,
    )
    seeded.add(staff)
    seeded.flush()
    assert staff.id > 900


def test_seed_loaders_leave_transaction_control_to_caller(db: Session) -> None:
    Base.metadata.create_all(db.connection())
    transaction = db.begin_nested()
    base_data.seed(db)
    golden_case.seed(db)
    transaction.rollback()
    assert db.scalar(select(func.count()).select_from(Staff)) == 0
    assert db.scalar(select(func.count()).select_from(Actor)) == 0
    assert db.scalar(select(func.count()).select_from(HardConstraintPolicy)) == 0


def test_golden_case_requires_demo_clock(db: Session) -> None:
    clock.reset()
    with pytest.raises(ValueError, match="21:00"):
        golden_case.seed(db)


def test_seed_command_refuses_existing_data_without_modifying_it(seeded: Session) -> None:
    with pytest.raises(ValueError, match="already contains data"):
        load(seeded)
    assert seeded.scalar(select(func.count()).select_from(Staff)) == 9
    assert seeded.scalar(select(func.count()).select_from(Actor)) == 15
