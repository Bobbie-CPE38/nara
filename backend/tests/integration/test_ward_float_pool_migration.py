"""Schema of WARD.is_float_pool (round 4 PR C1, docs/workflow.md section 6.19)."""

from types import ModuleType

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, func, inspect, select
from sqlalchemy.orm import Session

from app.db.models import Ward
from app.seed.reset import ALEMBIC_INI
from tests.integration.conftest import DEMO_NOW

REVISION = "c4e8a2f6d1b3"


def _columns(connection: Connection) -> dict[str, dict[str, object]]:
    return {c["name"]: dict(c) for c in inspect(connection).get_columns("ward")}


def _migration() -> ModuleType:
    revision = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION)
    assert revision is not None
    return revision.module


def test_column_is_a_required_boolean(db: Session) -> None:
    column = _columns(db.connection())["is_float_pool"]

    assert column["nullable"] is False
    assert column["type"].__class__.__name__ == "BOOLEAN"


def test_ward_without_the_field_is_not_float_pool(db: Session) -> None:
    ward_id = (db.scalar(select(func.max(Ward.id))) or 0) + 1
    db.add(Ward(id=ward_id, name="Plain", is_active=True, created_at=DEMO_NOW, updated_at=DEMO_NOW))
    db.flush()
    db.expire_all()

    ward = db.get(Ward, ward_id)
    assert ward is not None
    assert ward.is_float_pool is False


def test_migration_can_be_reversed(db: Session) -> None:
    connection = db.connection()
    migration = _migration()

    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        assert "is_float_pool" not in _columns(connection)
        migration.upgrade()

    column = _columns(connection)["is_float_pool"]
    assert column["nullable"] is False


def test_single_migration_head_and_parent() -> None:
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))

    assert len(script.get_heads()) == 1
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == "b8d4f1a6c2e9"
