"""Migration K preserves history and refuses duplicate legacy LINE ownership."""

import importlib.util
import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

BACKEND = Path(__file__).resolve().parents[2]


def migration():
    spec = importlib.util.spec_from_file_location(
        "line_account_migration", next((BACKEND / "alembic/versions").glob("*d7f0b3c5e9a2*"))
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_single_head_follows_line_delivery():
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert len(script.get_heads()) == 1
    assert script.get_revision("d7f0b3c5e9a2").down_revision == "c6e9a2b4d8f1"


def test_upgrade_retains_contacts_and_allows_multiple_nulls(production_seeded):
    db = production_seeded
    module = migration()
    with Operations.context(MigrationContext.configure(db.connection())):
        module.downgrade()
        db.execute(
            text(
                "INSERT INTO contacts (staff_id, line_uid, is_active) VALUES "
                "(201, 'U201', true), (202, NULL, true), (203, NULL, false)"
            )
        )
        module.upgrade()
    assert db.execute(text("SELECT line_uid FROM contacts ORDER BY staff_id")).scalars().all() == [
        "U201",
        None,
        None,
    ]
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text("INSERT INTO contacts (staff_id, line_uid, is_active) VALUES (202, 'U201', false)")
        )
    assert db.scalar(text("SELECT count(*) FROM line_account_link_code")) == 0


def test_upgrade_refuses_duplicate_legacy_uid_without_silently_reassigning(production_seeded):
    db = production_seeded
    with (
        pytest.raises(DBAPIError, match="Duplicate LINE bindings"),
        db.begin_nested(),
        Operations.context(MigrationContext.configure(db.connection())),
    ):
        module = migration()
        module.downgrade()
        db.execute(
            text(
                "INSERT INTO contacts (staff_id, line_uid, is_active) VALUES "
                "(201, 'Udup', true), (202, 'Udup', false)"
            )
        )
        module.upgrade()
    assert db.scalar(text("SELECT count(*) FROM contacts")) == 0


def test_offline_guard_precedes_the_unique_constraint_and_code_table():
    script = io.StringIO()
    command.upgrade(Config(str(BACKEND / "alembic.ini"), output_buffer=script), "head", sql=True)
    sql = script.getvalue()
    guard = "RAISE EXCEPTION 'Duplicate LINE bindings exist"
    unique = "ALTER TABLE contacts ADD CONSTRAINT uq_contacts_line_uid"
    table = "CREATE TABLE line_account_link_code"
    assert sql.index(guard) < sql.index(unique) < sql.index(table)
