"""PR L never delivers historical rows when upgrading an existing database."""

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text

from tests.integration.case_rows import offer, short_case

BACKEND = Path(__file__).resolve().parents[2]


def test_history_gets_no_delivery_intent(production_seeded):
    db = production_seeded
    case, items = short_case(db)
    row = offer(db, case, items[201])
    row_id = row.id
    db.flush()
    spec = importlib.util.spec_from_file_location(
        "line_migration", next((BACKEND / "alembic/versions").glob("*c6e9a2b4d8f1*"))
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(db.connection())):
        module.downgrade()
        module.upgrade()
    assert db.execute(
        text("SELECT delivery_status, delivery_attempts FROM candidate_outreach WHERE id=:id"),
        {"id": row_id},
    ).one() == (None, 0)
    # The in-place migration CHECK permits the team's terminal no-contact state.
    db.execute(
        text("UPDATE candidate_outreach SET delivery_status='NO_CONTACT' WHERE id=:id"),
        {"id": row_id},
    )
    assert db.execute(
        text("SELECT delivery_status, delivery_attempts FROM candidate_outreach WHERE id=:id"),
        {"id": row_id},
    ).one() == ("NO_CONTACT", 0)


def test_single_head_and_expected_parent():
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert len(script.get_heads()) == 1
    assert script.get_revision("c6e9a2b4d8f1").down_revision == "b7d3e5a1c9f2"
