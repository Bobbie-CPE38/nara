"""The migration that adds the merge window columns (docs/workflow.md, section 3.2)."""

import io
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Shift
from app.domain.enums import CaseStatus
from app.seed.reset import ALEMBIC_INI
from tests.integration.case_rows import make_case

REVISION = "f2a6b9c4d7e1"
PARENT_REVISION = "d91a6c8e203f"
# table -> columns the upgrade adds
ADDED = {
    "shift": {"merge_window_seconds"},
    "staffing_events": {"processed_at", "case_id"},
    "audit_log": {"event_id"},
}


def _migration() -> ModuleType:
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION)
    assert script is not None
    return script.module


def _columns(connection: Connection, table: str) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns(table)}


def _is_upgraded(connection: Connection) -> bool:
    added = all(columns <= _columns(connection, table) for table, columns in ADDED.items())
    return added and "event_id" not in _columns(connection, "staffing_cases")


def _is_downgraded(connection: Connection) -> bool:
    removed = all(not (columns & _columns(connection, table)) for table, columns in ADDED.items())
    return removed and "event_id" in _columns(connection, "staffing_cases")


def test_migration_follows_the_outreach_policy_migration() -> None:
    migration = _migration()

    assert migration.down_revision == PARENT_REVISION
    # One head, whichever it is: a later migration must not have to edit this test
    assert len(ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads()) == 1


def test_downgrade_and_upgrade_round_trip_on_an_empty_database(db: Session) -> None:
    connection = db.connection()
    migration = _migration()
    assert _is_upgraded(connection)

    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        assert _is_downgraded(connection)
        migration.upgrade()

    assert _is_upgraded(connection)
    foreign_keys = {
        (table, key["name"])
        for table in ("staffing_events", "audit_log", "staffing_cases")
        for key in inspect(connection).get_foreign_keys(table)
    }
    assert ("staffing_events", "fk_staffing_events_case_id_staffing_cases") in foreign_keys
    assert ("audit_log", "fk_audit_log_event_id_staffing_events") in foreign_keys
    assert ("staffing_cases", "fk_staffing_cases_event_id_staffing_events") not in foreign_keys


def test_upgrade_stops_when_shifts_exist(seeded: Session) -> None:
    """No backfill (Q34): the window length of an existing shift is not known."""
    connection = seeded.connection()
    migration = _migration()

    with Operations.context(MigrationContext.configure(connection)):
        # The seed has shifts but no case, so going down is allowed
        migration.downgrade()
        # The savepoint keeps the outer test transaction usable after the refusal
        with (
            pytest.raises(DBAPIError, match="does not fill merge_window_seconds"),
            connection.begin_nested(),
        ):
            migration.upgrade()

    # It stopped before changing anything
    assert _is_downgraded(connection)


def test_downgrade_stops_when_cases_exist(seeded: Session) -> None:
    """staffing_cases.event_id is NOT NULL and this downgrade does not fill it."""
    make_case(seeded, CaseStatus.OPEN)
    connection = seeded.connection()
    migration = _migration()

    with (
        Operations.context(MigrationContext.configure(connection)),
        pytest.raises(DBAPIError, match="event_id is not filled"),
        connection.begin_nested(),
    ):
        migration.downgrade()

    assert _is_upgraded(connection)


def test_sql_only_upgrade_carries_the_guard_before_the_schema_change() -> None:
    """`alembic upgrade head --sql` has no query result to inspect in Python."""
    script = io.StringIO()

    command.upgrade(Config(str(ALEMBIC_INI), output_buffer=script), "head", sql=True)

    sql = script.getvalue()
    migration = _migration()
    guard = migration.REFUSE_EXISTING_ROWS.strip()
    assert "make reset" in guard
    assert guard != migration.REFUSE_EXISTING_ROWS_ON_DOWNGRADE.strip()
    assert sql.index(guard) < sql.index("ALTER TABLE shift ADD COLUMN merge_window_seconds")
    assert sql.index(guard) < sql.index("ALTER TABLE staffing_cases DROP COLUMN event_id")
    assert "ck_shift_merge_window_seconds_non_negative" in sql


def test_merge_window_cannot_be_negative(seeded: Session) -> None:
    shift = seeded.get(Shift, 1)
    assert shift is not None
    shift.merge_window_seconds = -1

    with pytest.raises(IntegrityError, match="ck_shift_merge_window_seconds_non_negative"):
        seeded.flush()


def test_merge_window_has_no_database_default(seeded: Session) -> None:
    """The column is NOT NULL without a default: a row written without the model must say so."""
    with pytest.raises(IntegrityError, match="merge_window_seconds"), seeded.begin_nested():
        seeded.execute(
            text(
                "INSERT INTO shift (ward_id, patient_count, start_at, end_at, shift_type, "
                "is_active) VALUES (1, 0, now(), now(), 'DAY', true)"
            )
        )
