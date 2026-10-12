"""Schema of the round 1 Hard Rules: the consecutive-shift limit on
HARD_CONSTRAINT_POLICY, the overtime CHECK on ATTENDANCE and their migration."""

from datetime import timedelta
from types import ModuleType

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Integer, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Attendance
from app.seed.reset import ALEMBIC_INI
from app.services.policy_service import get_hard_constraint_policy
from tests.integration.conftest import DEMO_NOW

REVISION = "e1f5a8b3c6d2"
LIMIT_CHECK = "ck_hard_constraint_policy_consecutive_shifts_non_negative"
OVERTIME_CHECK = "ck_attendance_overtime_within_work"


def _checks(connection: Connection, table: str) -> set[str | None]:
    return {check["name"] for check in inspect(connection).get_check_constraints(table)}


def _limit_column(connection: Connection) -> dict[str, object] | None:
    return next(
        (
            dict(column)
            for column in inspect(connection).get_columns("hard_constraint_policy")
            if column["name"] == "maximum_consecutive_shifts"
        ),
        None,
    )


def _attendance(*, work_minutes: int | None, overtime_minutes: int | None) -> Attendance:
    return Attendance(
        staff_id=201,
        check_in_at=DEMO_NOW,
        check_out_at=DEMO_NOW + timedelta(hours=8),
        work_minutes=work_minutes,
        overtime_minutes=overtime_minutes,
        synced_at=DEMO_NOW,
    )


def _migration() -> ModuleType:
    revision = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION)
    assert revision is not None
    return revision.module


# --------------------------------------------------------------------------- #
# What the migration built
# --------------------------------------------------------------------------- #
def test_limit_column_is_a_required_integer_without_a_default(db: Session) -> None:
    column = _limit_column(db.connection())

    assert column is not None
    assert isinstance(column["type"], Integer)
    assert column["nullable"] is False
    # New policy versions must supply their own limit
    assert column["default"] is None


def test_checks_exist_under_their_names(db: Session) -> None:
    """Alembic does not compare CHECK constraints, so they are asserted by name here."""
    connection = db.connection()

    assert LIMIT_CHECK in _checks(connection, "hard_constraint_policy")
    assert OVERTIME_CHECK in _checks(connection, "attendance")
    # PostgreSQL cuts identifiers at 63 characters
    assert len(LIMIT_CHECK) <= 63


@pytest.mark.parametrize("limit", [-1, None])
def test_database_rejects_an_invalid_consecutive_shift_limit(
    seeded: Session, limit: int | None
) -> None:
    with pytest.raises(IntegrityError), seeded.begin_nested():
        seeded.execute(
            text(
                "UPDATE hard_constraint_policy SET maximum_consecutive_shifts = :limit WHERE id=1"
            ),
            {"limit": limit},
        )


def test_database_accepts_a_limit_of_zero(seeded: Session) -> None:
    policy = get_hard_constraint_policy(seeded)
    policy.maximum_consecutive_shifts = 0
    seeded.flush()
    seeded.expire_all()

    assert get_hard_constraint_policy(seeded).maximum_consecutive_shifts == 0


@pytest.mark.parametrize(
    ("work_minutes", "overtime_minutes"),
    [(480, 481), (480, -1), (0, 1)],
)
def test_database_rejects_overtime_outside_the_work_minutes(
    seeded: Session, work_minutes: int, overtime_minutes: int
) -> None:
    seeded.add(_attendance(work_minutes=work_minutes, overtime_minutes=overtime_minutes))

    with pytest.raises(IntegrityError, match=OVERTIME_CHECK):
        seeded.flush()


@pytest.mark.parametrize(
    ("work_minutes", "overtime_minutes"),
    [
        (480, 0),
        (480, 480),
        # NULL = not summarised yet, so the CHECK has nothing to compare
        (480, None),
        (None, None),
        (None, 30),
    ],
)
def test_database_accepts_overtime_within_work_or_not_summarised(
    seeded: Session, work_minutes: int | None, overtime_minutes: int | None
) -> None:
    row = _attendance(work_minutes=work_minutes, overtime_minutes=overtime_minutes)
    seeded.add(row)
    seeded.flush()

    assert row.id is not None


# --------------------------------------------------------------------------- #
# The migration itself. DDL is transactional in PostgreSQL, so the fixture's
# rollback puts the schema back.
# --------------------------------------------------------------------------- #
def test_migration_backfills_the_existing_policy_and_can_be_reversed(seeded: Session) -> None:
    connection = seeded.connection()
    migration = _migration()

    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        assert _limit_column(connection) is None
        assert LIMIT_CHECK not in _checks(connection, "hard_constraint_policy")
        assert OVERTIME_CHECK not in _checks(connection, "attendance")
        migration.upgrade()

    assert LIMIT_CHECK in _checks(connection, "hard_constraint_policy")
    assert OVERTIME_CHECK in _checks(connection, "attendance")
    # The column was dropped and added again, so this 7 is the backfill, not the seed
    assert (
        connection.execute(
            text("SELECT maximum_consecutive_shifts FROM hard_constraint_policy WHERE id=1")
        ).scalar_one()
        == 7
    )
    column = _limit_column(connection)
    assert column is not None
    assert column["nullable"] is False
    assert column["default"] is None
    seeded.expire_all()
    assert get_hard_constraint_policy(seeded).maximum_consecutive_shifts == 7
