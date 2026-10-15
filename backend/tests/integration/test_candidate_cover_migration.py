"""Schema of the round 4 cover window: the three columns on CANDIDATE_ITEMS and their migration."""

from datetime import timedelta
from types import ModuleType

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import CandidateItem
from app.seed.reset import ALEMBIC_INI
from tests.integration.case_rows import make_case, make_plan
from tests.integration.conftest import DEMO_NOW

REVISION = "a9c3e7f1b5d2"
SOURCE_FK = "fk_candidate_items_source_assignment_id_roster_assignment"
BOTH_OR_NEITHER = "ck_candidate_items_cover_both_or_neither"
IN_ORDER = "ck_candidate_items_cover_in_order"
NEW_COLUMNS = {"cover_start_at", "cover_end_at", "source_assignment_id"}


def _columns(connection: Connection) -> dict[str, dict[str, object]]:
    return {c["name"]: dict(c) for c in inspect(connection).get_columns("candidate_items")}


def _migration() -> ModuleType:
    revision = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION)
    assert revision is not None
    return revision.module


def _item(db: Session) -> CandidateItem:
    return make_plan(db, make_case(db), (201,))[201]


def test_new_columns_are_nullable(db: Session) -> None:
    columns = _columns(db.connection())

    assert set(columns) >= NEW_COLUMNS
    assert all(columns[name]["nullable"] is True for name in NEW_COLUMNS)
    assert columns["cover_start_at"]["type"].timezone is True
    assert columns["cover_end_at"]["type"].timezone is True
    assert columns["source_assignment_id"]["type"].__class__.__name__ == "BIGINT"


def test_source_foreign_key_and_checks_exist_under_their_names(db: Session) -> None:
    """Alembic does not compare CHECK constraints, so they are asserted by name here."""
    inspector = inspect(db.connection())
    foreign_keys = {fk["name"]: fk for fk in inspector.get_foreign_keys("candidate_items")}
    checks = {c["name"] for c in inspector.get_check_constraints("candidate_items")}

    assert foreign_keys[SOURCE_FK]["referred_table"] == "roster_assignment"
    assert foreign_keys[SOURCE_FK]["constrained_columns"] == ["source_assignment_id"]
    assert {BOTH_OR_NEITHER, IN_ORDER} <= checks
    assert len(BOTH_OR_NEITHER) <= 63 and len(IN_ORDER) <= 63


def test_new_item_has_no_cover(seeded: Session) -> None:
    item = _item(seeded)
    seeded.refresh(item)

    assert item.cover_start_at is None
    assert item.cover_end_at is None
    assert item.source_assignment_id is None


def test_database_accepts_a_valid_window(seeded: Session) -> None:
    item = _item(seeded)
    item.cover_start_at = DEMO_NOW
    item.cover_end_at = DEMO_NOW + timedelta(hours=6)

    seeded.flush()


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (DEMO_NOW, None),
        (None, DEMO_NOW),
        (DEMO_NOW, DEMO_NOW),
        (DEMO_NOW + timedelta(hours=1), DEMO_NOW),
    ],
    ids=["only_start", "only_end", "start_equals_end", "start_after_end"],
)
def test_database_rejects_a_bad_window(seeded: Session, start, end) -> None:
    item = _item(seeded)
    item.cover_start_at = start
    item.cover_end_at = end

    with pytest.raises(IntegrityError):
        seeded.flush()


def test_database_rejects_an_unknown_source_assignment(seeded: Session) -> None:
    item = _item(seeded)
    item.source_assignment_id = 999_999_999

    with pytest.raises(IntegrityError, match=SOURCE_FK):
        seeded.flush()


def test_migration_can_be_reversed(seeded: Session) -> None:
    connection = seeded.connection()
    migration = _migration()

    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        inspector = inspect(connection)
        assert not NEW_COLUMNS & set(_columns(connection))
        assert SOURCE_FK not in {fk["name"] for fk in inspector.get_foreign_keys("candidate_items")}
        assert not {BOTH_OR_NEITHER, IN_ORDER} & {
            c["name"] for c in inspector.get_check_constraints("candidate_items")
        }
        migration.upgrade()

    inspector = inspect(connection)
    assert set(_columns(connection)) >= NEW_COLUMNS
    assert SOURCE_FK in {fk["name"] for fk in inspector.get_foreign_keys("candidate_items")}
    assert {BOTH_OR_NEITHER, IN_ORDER} <= {
        c["name"] for c in inspector.get_check_constraints("candidate_items")
    }


def test_single_migration_head_and_parent() -> None:
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))

    assert len(script.get_heads()) == 1
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == "e1a4c7f2b9d6"
