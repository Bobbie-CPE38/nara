"""H2 upgrade leaves old snapshots unsent and constrains the durable outbox."""

import io

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import Attendance, StructuredHandover
from app.seed.reset import ALEMBIC_INI
from tests.integration.test_handover import created

REVISION = "f6b2d8a4c0e1"


def test_upgrade_preserves_existing_snapshot_without_sending_it(production_seeded):
    db = production_seeded
    _, _, row = created(db)
    db.flush()
    row_id, content = row.id, row.content
    attendance_ids = list(db.scalars(select(Attendance.id).order_by(Attendance.id)))
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1
    assert script.get_revision("b4e7a9c2d6f0").down_revision == REVISION
    revision = script.get_revision(REVISION)
    assert revision.down_revision == "e8c4b2a6f0d9"
    with Operations.context(MigrationContext.configure(db.connection())):
        revision.module.downgrade()
        revision.module.upgrade()
    db.expire_all()
    row = db.get(StructuredHandover, row_id)
    assert row.content == content and row.delivery_status is None
    assert row.delivery_attempts == 0 and row.delivery_payload is None
    assert list(db.scalars(select(Attendance.id).order_by(Attendance.id))) == attendance_ids


@pytest.mark.parametrize(
    "assignment", ["delivery_status = 'BOGUS'", "delivery_attempts = -1", "delivery_attempts = 4"]
)
def test_outbox_checks_in_sql(production_seeded, assignment):
    db = production_seeded
    _, _, row = created(db)
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(f"UPDATE structured_handover SET {assignment} WHERE id=:id"), {"id": row.id}
        )


def test_offline_upgrade_is_available():
    output = io.StringIO()
    command.upgrade(Config(str(ALEMBIC_INI), output_buffer=output), "head", sql=True)
    sql = output.getvalue()
    assert "ck_structured_handover_delivery_status" in sql
    assert "ix_structured_handover_delivery_due" in sql
