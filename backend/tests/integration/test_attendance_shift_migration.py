"""PR N1: attendance.shift_id, its partial unique index and a single migration chain."""

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import Attendance, Shift, Staff
from app.seed.reset import ALEMBIC_INI
from tests.integration.conftest import DEMO_NOW

REVISION = "a4d8e1b7c3f5"


def migration():
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION).module


def _attendance(staff_id: int, shift_id: int | None = None) -> Attendance:
    return Attendance(
        staff_id=staff_id, shift_id=shift_id, check_in_at=DEMO_NOW, synced_at=DEMO_NOW
    )


def test_round_trip_keeps_shiftless_attendance(seeded):
    staff_id = seeded.scalars(select(Staff.id)).first()
    row = _attendance(staff_id)
    seeded.add(row)
    seeded.flush()
    row_id = row.id
    connection = seeded.connection()
    with Operations.context(MigrationContext.configure(connection)):
        migration().downgrade()
        columns = {c["name"] for c in inspect(connection).get_columns("attendance")}
        assert "shift_id" not in columns
        migration().upgrade()
    assert (
        connection.execute(
            text("SELECT shift_id FROM attendance WHERE id = :id"), {"id": row_id}
        ).scalar_one()
        is None
    )


def test_rows_without_shift_are_not_unique(seeded):
    staff_id = seeded.scalars(select(Staff.id)).first()
    seeded.add_all([_attendance(staff_id), _attendance(staff_id)])
    seeded.flush()


def test_duplicate_staff_shift_is_rejected(seeded):
    staff_id = seeded.scalars(select(Staff.id)).first()
    shift_id = seeded.scalars(select(Shift.id)).first()
    seeded.add(_attendance(staff_id, shift_id))
    seeded.flush()
    with pytest.raises(IntegrityError, match="uq_attendance_staff_shift"), seeded.begin_nested():
        seeded.add(_attendance(staff_id, shift_id))
        seeded.flush()


def test_single_head_and_parent():
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1
    assert script.get_revision(REVISION).down_revision == "f2a7c9d4e6b8"
