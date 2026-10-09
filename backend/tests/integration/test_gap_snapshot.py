"""The workload snapshot on STAFFING_GAP: its columns, its CHECK and its migration."""

from datetime import timedelta
from decimal import Decimal
from types import ModuleType

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Integer, Numeric, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import StaffingCase, StaffingEvent, StaffingGap, StaffingRequirement
from app.domain.enums import CaseStatus, EventStatus, EventType
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT = 1
LEAVING_STAFF_ID = 105
SNAPSHOT_REVISION = "c4d7e19a52f3"
CHECK_NAME = "ck_staffing_gap_patients_per_nurse_valid"
SNAPSHOT_COLUMNS = {"patient_count", "patients_per_nurse"}


def _case_and_requirement(db: Session) -> tuple[int, int]:
    """IDs of a new case on the night shift and of that shift's requirement."""
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
        occurred_at=DEMO_NOW,
        staff_id=LEAVING_STAFF_ID,
        status=EventStatus.PROCESSED,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        event_id=event.id,
        shift_id=NIGHT_SHIFT,
        status=CaseStatus.ASSESSING,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(case)
    db.flush()
    requirement_id = db.scalar(
        select(StaffingRequirement.id).where(StaffingRequirement.shift_id == NIGHT_SHIFT)
    )
    assert requirement_id is not None
    return case.id, requirement_id


def _gap(db: Session, *, patients_per_nurse: Decimal | None) -> StaffingGap:
    case_id, requirement_id = _case_and_requirement(db)
    return StaffingGap(
        case_id=case_id,
        staffing_requirement_id=requirement_id,
        headcount_gap=1,
        patient_count=10,
        patients_per_nurse=patients_per_nurse,
        computed_at=DEMO_NOW,
    )


def _columns(connection: Connection) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns("staffing_gap")}


def _snapshot_migration() -> ModuleType:
    revision = ScriptDirectory.from_config(Config("alembic.ini")).get_revision(SNAPSHOT_REVISION)
    assert revision is not None
    return revision.module


# --------------------------------------------------------------------------- #
# What the migration built
# --------------------------------------------------------------------------- #
def test_snapshot_columns_are_typed_and_not_null(db: Session) -> None:
    columns = {
        column["name"]: column for column in inspect(db.connection()).get_columns("staffing_gap")
    }

    assert isinstance(columns["patient_count"]["type"], Integer)
    assert columns["patient_count"]["nullable"] is False
    assert isinstance(columns["patients_per_nurse"]["type"], Numeric)
    assert columns["patients_per_nurse"]["nullable"] is False
    # Unbounded numeric, like the policy column it is copied from: 2.5 must fit
    assert columns["patients_per_nurse"]["type"].precision is None


def test_ratio_check_exists_under_its_short_name(db: Session) -> None:
    """Alembic does not compare CHECK constraints, so it is asserted by name here."""
    checks = {
        check["name"] for check in inspect(db.connection()).get_check_constraints("staffing_gap")
    }

    assert CHECK_NAME in checks


@pytest.mark.parametrize("ratio", ["0", "-1", "NaN", "Infinity", "-Infinity"])
def test_database_rejects_an_invalid_snapshot_ratio(seeded: Session, ratio: str) -> None:
    seeded.add(_gap(seeded, patients_per_nurse=Decimal(ratio)))

    with pytest.raises(IntegrityError, match=CHECK_NAME):
        seeded.flush()


def test_database_rejects_a_missing_snapshot_ratio(seeded: Session) -> None:
    seeded.add(_gap(seeded, patients_per_nurse=None))

    with pytest.raises(IntegrityError, match="patients_per_nurse"):
        seeded.flush()


def test_fractional_ratio_survives_a_database_round_trip(seeded: Session) -> None:
    gap = _gap(seeded, patients_per_nurse=Decimal("2.5"))
    seeded.add(gap)
    seeded.flush()
    seeded.expire_all()

    assert gap.patient_count == 10
    assert gap.patients_per_nurse == Decimal("2.5")


# --------------------------------------------------------------------------- #
# The migration itself. DDL is transactional in PostgreSQL, so the fixture's
# rollback puts the schema back.
# --------------------------------------------------------------------------- #
def test_snapshot_migration_can_be_reversed_on_an_empty_table(db: Session) -> None:
    connection = db.connection()
    migration = _snapshot_migration()

    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        assert _columns(connection).isdisjoint(SNAPSHOT_COLUMNS)
        assert CHECK_NAME not in {
            check["name"] for check in inspect(connection).get_check_constraints("staffing_gap")
        }
        migration.upgrade()

    assert _columns(connection) >= SNAPSHOT_COLUMNS
    assert CHECK_NAME in {
        check["name"] for check in inspect(connection).get_check_constraints("staffing_gap")
    }


def test_snapshot_migration_stops_when_gap_rows_exist(seeded: Session) -> None:
    """No backfill: today's values would pass for a snapshot of the past."""
    case_id, requirement_id = _case_and_requirement(seeded)
    connection = seeded.connection()
    migration = _snapshot_migration()

    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        connection.execute(
            text(
                "INSERT INTO staffing_gap "
                "(case_id, staffing_requirement_id, headcount_gap, computed_at) "
                "VALUES (:case_id, :requirement_id, 1, :computed_at)"
            ),
            {"case_id": case_id, "requirement_id": requirement_id, "computed_at": DEMO_NOW},
        )
        with pytest.raises(RuntimeError, match="make reset"):
            migration.upgrade()

    # It stopped before changing anything
    assert _columns(connection).isdisjoint(SNAPSHOT_COLUMNS)
