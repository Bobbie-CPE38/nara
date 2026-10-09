"""Real policy storage, shared selection and workload calculation."""

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import RosterAssignment, Shift, Staff, StaffSkill
from app.domain.enums import RosterStatus
from app.domain.staffing.coverage import RosterMember
from app.domain.staffing.gap_calculator import calculate_gap
from app.seed import load
from app.services.policy_service import get_hard_constraint_policy


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    clock.set_time(datetime(2026, 10, 9, 21, tzinfo=clock.APP_TIMEZONE))
    try:
        yield
    finally:
        clock.reset()


def test_seeded_policy_drives_golden_case(db: Session) -> None:
    load(db)
    shift = db.get(Shift, 1)
    assert shift is not None
    roster = [
        RosterMember(
            staff_id=staff.id,
            shift_id=assignment.shift_id,
            status=RosterStatus.CANCELLED if staff.id == 105 else assignment.status,
            role_id=staff.role_id,
            skill_ids=frozenset(
                db.scalars(select(StaffSkill.skill_id).where(StaffSkill.staff_id == staff.id))
            ),
        )
        for assignment, staff in db.execute(
            select(RosterAssignment, Staff).join(Staff, Staff.id == RosterAssignment.staff_id)
        )
    ]
    with patch.object(db, "commit", side_effect=AssertionError("committed")):
        policy = get_hard_constraint_policy(db)
    assert policy.id == 1
    assert policy.maximum_patients_per_nurse == Decimal("2")
    result = calculate_gap(
        shift_id=shift.id,
        patient_count=shift.patient_count,
        patients_per_nurse=policy.maximum_patients_per_nurse,
        required_roles={1: 5},
        required_skills={1: 2},
        roster=roster,
    )
    assert result.minimum_required_staff == 5
    assert result.headcount_gap == result.role_gaps[1].gap_count == 1
    assert result.skill_gaps[1].gap_count == 0
    assert result.has_gap


def test_policy_ratio_is_read_from_database_without_fallback(db: Session) -> None:
    load(db)
    policy = get_hard_constraint_policy(db)
    policy.maximum_patients_per_nurse = Decimal("2.5")
    db.flush()
    db.expire_all()
    result = calculate_gap(
        shift_id=1,
        patient_count=10,
        patients_per_nurse=get_hard_constraint_policy(db).maximum_patients_per_nurse,
        required_roles={},
        required_skills={},
        roster=[],
    )
    assert result.minimum_required_staff == 4


def test_missing_demo_policy_fails_explicitly(db: Session) -> None:
    with pytest.raises(LookupError, match="id=1 is missing"):
        get_hard_constraint_policy(db)


@pytest.mark.parametrize("ratio", ["0", "-1", "NaN", "Infinity", "-Infinity", None])
def test_database_rejects_invalid_policy_ratios(db: Session, ratio: str | None) -> None:
    load(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(
                "UPDATE hard_constraint_policy SET maximum_patients_per_nurse = :ratio WHERE id=1"
            ),
            {"ratio": Decimal(ratio) if ratio is not None else None},
        )


def test_ratio_migration_backfills_existing_policy_and_can_be_reversed(db: Session) -> None:
    load(db)
    connection = db.connection()
    revision = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("a73d9e2c4b10")
    assert revision is not None
    migration = revision.module
    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        assert "maximum_patients_per_nurse" not in {
            column["name"] for column in inspect(connection).get_columns("hard_constraint_policy")
        }
        migration.upgrade()
    assert connection.execute(
        text("SELECT maximum_patients_per_nurse FROM hard_constraint_policy WHERE id=1")
    ).scalar_one() == Decimal("2")
    column = next(
        column
        for column in inspect(connection).get_columns("hard_constraint_policy")
        if column["name"] == "maximum_patients_per_nurse"
    )
    assert not column["nullable"]
    assert column["default"] is None
    db.expire_all()
    assert get_hard_constraint_policy(db).version == "demo-stub-v1"
