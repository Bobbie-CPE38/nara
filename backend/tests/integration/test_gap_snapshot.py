"""The headcount target stored on STAFFING_GAP: its column and its migrations."""

import io
from datetime import timedelta
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Integer, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db.models import StaffingCase, StaffingEvent, StaffingGap, StaffingRequirement
from app.domain.enums import CaseStatus, EventStatus, EventType
from app.seed.reset import ALEMBIC_INI
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT = 1
LEAVING_STAFF_ID = 105
WORKLOAD_REVISION = "c4d7e19a52f3"
TARGET_REVISION = "d5e8f20b63a4"
CHECK_NAME = "ck_staffing_gap_patients_per_nurse_valid"
WORKLOAD_COLUMNS = {"patient_count", "patients_per_nurse"}
TARGET_COLUMN = "effective_minimum"


def _case_and_requirement(db: Session) -> tuple[int, int]:
    """IDs of a new case on the night shift and of that shift's requirement."""
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
        occurred_at=DEMO_NOW,
        staff_id=LEAVING_STAFF_ID,
        status=EventStatus.PROCESSED,
        processed_at=DEMO_NOW,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        shift_id=NIGHT_SHIFT,
        status=CaseStatus.ASSESSING,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(case)
    db.flush()
    event.case_id = case.id
    db.flush()
    requirement_id = db.scalar(
        select(StaffingRequirement.id).where(StaffingRequirement.shift_id == NIGHT_SHIFT)
    )
    assert requirement_id is not None
    return case.id, requirement_id


def _gap(db: Session, *, effective_minimum: int | None) -> StaffingGap:
    case_id, requirement_id = _case_and_requirement(db)
    return StaffingGap(
        case_id=case_id,
        staffing_requirement_id=requirement_id,
        headcount_gap=1,
        effective_minimum=effective_minimum,
        computed_at=DEMO_NOW,
    )


def _columns(connection: Connection) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns("staffing_gap")}


def _checks(connection: Connection) -> set[str | None]:
    return {check["name"] for check in inspect(connection).get_check_constraints("staffing_gap")}


def _migration(revision_id: str) -> ModuleType:
    revision = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(revision_id)
    assert revision is not None
    return revision.module


# --------------------------------------------------------------------------- #
# What the migrations built
# --------------------------------------------------------------------------- #
def test_target_column_is_an_integer_and_not_null(db: Session) -> None:
    columns = {
        column["name"]: column for column in inspect(db.connection()).get_columns("staffing_gap")
    }

    assert isinstance(columns[TARGET_COLUMN]["type"], Integer)
    assert columns[TARGET_COLUMN]["nullable"] is False


def test_workload_snapshot_and_its_check_are_gone(db: Session) -> None:
    connection = db.connection()

    assert _columns(connection).isdisjoint(WORKLOAD_COLUMNS)
    assert CHECK_NAME not in _checks(connection)


def test_database_rejects_a_missing_target(seeded: Session) -> None:
    seeded.add(_gap(seeded, effective_minimum=None))

    with pytest.raises(IntegrityError, match=TARGET_COLUMN):
        seeded.flush()


def test_target_survives_a_database_round_trip(seeded: Session) -> None:
    gap = _gap(seeded, effective_minimum=5)
    seeded.add(gap)
    seeded.flush()
    seeded.expire_all()

    assert gap.effective_minimum == 5


# --------------------------------------------------------------------------- #
# The migrations themselves. DDL is transactional in PostgreSQL, so the fixture's
# rollback puts the schema back.
# --------------------------------------------------------------------------- #
def test_target_migration_can_be_reversed_on_an_empty_table(db: Session) -> None:
    connection = db.connection()
    migration = _migration(TARGET_REVISION)

    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        assert TARGET_COLUMN not in _columns(connection)
        assert _columns(connection) >= WORKLOAD_COLUMNS
        assert CHECK_NAME in _checks(connection)
        migration.upgrade()

    assert TARGET_COLUMN in _columns(connection)
    assert _columns(connection).isdisjoint(WORKLOAD_COLUMNS)
    assert CHECK_NAME not in _checks(connection)


def test_workload_migration_can_still_be_reversed_below_the_target_migration(
    db: Session,
) -> None:
    connection = db.connection()
    target = _migration(TARGET_REVISION)
    workload = _migration(WORKLOAD_REVISION)

    with Operations.context(MigrationContext.configure(connection)):
        target.downgrade()
        workload.downgrade()
        assert _columns(connection).isdisjoint(WORKLOAD_COLUMNS | {TARGET_COLUMN})
        assert CHECK_NAME not in _checks(connection)
        workload.upgrade()
        target.upgrade()

    assert TARGET_COLUMN in _columns(connection)


def test_target_migration_stops_when_gap_rows_exist(seeded: Session) -> None:
    """No backfill: the target of an old row cannot be rebuilt from today's requirement."""
    case_id, requirement_id = _case_and_requirement(seeded)
    connection = seeded.connection()
    migration = _migration(TARGET_REVISION)

    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        connection.execute(
            text(
                "INSERT INTO staffing_gap (case_id, staffing_requirement_id, headcount_gap, "
                "patient_count, patients_per_nurse, computed_at) "
                "VALUES (:case_id, :requirement_id, 1, 10, 2, :computed_at)"
            ),
            {"case_id": case_id, "requirement_id": requirement_id, "computed_at": DEMO_NOW},
        )
        # The savepoint keeps the outer test transaction usable after the refusal
        with (
            pytest.raises(DBAPIError, match="effective_minimum cannot be known"),
            connection.begin_nested(),
        ):
            migration.upgrade()

    # It stopped before changing anything
    assert TARGET_COLUMN not in _columns(connection)
    assert _columns(connection) >= WORKLOAD_COLUMNS


def test_target_downgrade_stops_when_gap_rows_exist(seeded: Session) -> None:
    """The old NOT NULL snapshot columns cannot be filled for existing rows either."""
    seeded.add(_gap(seeded, effective_minimum=5))
    seeded.flush()
    connection = seeded.connection()
    migration = _migration(TARGET_REVISION)

    with (
        Operations.context(MigrationContext.configure(connection)),
        pytest.raises(DBAPIError, match="patients_per_nurse cannot be known"),
        connection.begin_nested(),
    ):
        migration.downgrade()

    assert TARGET_COLUMN in _columns(connection)


def test_sql_only_upgrade_carries_each_guard_before_its_schema_change() -> None:
    """Regression: `alembic upgrade head --sql` has no query result to inspect.

    The guard used to read one in Python, which crashed SQL-only mode. The
    generated script must hold the same statement the online upgrade runs (the
    tests above show that statement refuses), ahead of the first schema change
    of its own revision.
    """
    script = io.StringIO()

    command.upgrade(Config(str(ALEMBIC_INI), output_buffer=script), "head", sql=True)

    sql = script.getvalue()
    workload_guard = _migration(WORKLOAD_REVISION).REFUSE_EXISTING_ROWS.strip()
    target_guard = _migration(TARGET_REVISION).REFUSE_EXISTING_ROWS.strip()
    add_patient_count = "ALTER TABLE staffing_gap ADD COLUMN patient_count"
    drop_patient_count = "ALTER TABLE staffing_gap DROP COLUMN patient_count"
    add_target = "ALTER TABLE staffing_gap ADD COLUMN effective_minimum"

    assert "make reset" in workload_guard and "make reset" in target_guard
    assert workload_guard != target_guard
    assert sql.index(workload_guard) < sql.index(add_patient_count)
    assert sql.index(add_patient_count) < sql.index(target_guard)
    assert sql.index(target_guard) < sql.index(drop_patient_count) < sql.index(add_target)
    assert CHECK_NAME in sql
