"""Schema of the round 1 Solver: CANDIDATE_ITEM_TARGET, the snapshot link on
CANDIDATE_ITEMS, the source weight on SOFT_CONSTRAINT_POLICY and their migration."""

from types import ModuleType

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import CandidateItem, CandidateItemTarget
from app.domain.enums import SelectionType, TargetType
from app.seed.reset import ALEMBIC_INI
from tests.integration.case_rows import make_case, make_plan

REVISION = "f3a7c1d9e5b2"
ROLE_CHECK = "ck_candidate_item_target_role_id_matches_target_type"
SKILL_CHECK = "ck_candidate_item_target_skill_id_matches_target_type"


def _columns(connection: Connection, table: str) -> dict[str, dict[str, object]]:
    return {column["name"]: dict(column) for column in inspect(connection).get_columns(table)}


def _checks(connection: Connection, table: str) -> set[str | None]:
    return {check["name"] for check in inspect(connection).get_check_constraints(table)}


def _migration() -> ModuleType:
    revision = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION)
    assert revision is not None
    return revision.module


def _item(db: Session) -> CandidateItem:
    return make_plan(db, make_case(db), (201,))[201]


def _target(item: CandidateItem, target_type: TargetType, **ids: int) -> CandidateItemTarget:
    return CandidateItemTarget(
        candidate_item_id=item.id,
        target_type=target_type,
        selection_type=SelectionType.PRIMARY,
        **ids,
    )


def test_target_table_columns(db: Session) -> None:
    columns = _columns(db.connection(), "candidate_item_target")

    assert set(columns) == {
        "id",
        "candidate_item_id",
        "target_type",
        "role_id",
        "skill_id",
        "selection_type",
    }
    assert {name for name, column in columns.items() if not column["nullable"]} == {
        "id",
        "candidate_item_id",
        "target_type",
        "selection_type",
    }


def test_checks_exist_under_their_names(db: Session) -> None:
    """Alembic does not compare CHECK constraints, so they are asserted by name here."""
    checks = _checks(db.connection(), "candidate_item_target")

    assert {ROLE_CHECK, SKILL_CHECK} <= checks
    assert len(ROLE_CHECK) <= 63 and len(SKILL_CHECK) <= 63


@pytest.mark.parametrize(
    ("target_type", "ids"),
    [
        (TargetType.ROLE, {}),
        (TargetType.HEADCOUNT, {"role_id": 1}),
        (TargetType.SKILL, {}),
        (TargetType.ROLE, {"skill_id": 1}),
        (TargetType.SKILL, {"role_id": 1}),
    ],
)
def test_database_rejects_ids_that_do_not_match_the_type(
    seeded: Session, target_type: TargetType, ids: dict[str, int]
) -> None:
    item = _item(seeded)
    seeded.add(_target(item, target_type, **ids))

    with pytest.raises(IntegrityError):
        seeded.flush()


def test_database_accepts_one_valid_row_of_each_type(seeded: Session) -> None:
    item = _item(seeded)
    seeded.add_all(
        [
            _target(item, TargetType.HEADCOUNT),
            _target(item, TargetType.ROLE, role_id=1),
            _target(item, TargetType.SKILL, skill_id=1),
        ]
    )

    seeded.flush()


def test_new_columns(db: Session) -> None:
    connection = db.connection()
    weight = _columns(connection, "soft_constraint_policy")["candidate_source_weight"]
    link = _columns(connection, "candidate_items")["working_time_snapshot_id"]

    assert weight["nullable"] is False
    assert weight["default"] is None
    assert link["nullable"] is True


def test_migration_can_be_reversed_and_backfills_the_weight(seeded: Session) -> None:
    connection = seeded.connection()
    migration = _migration()

    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        assert "candidate_item_target" not in inspect(connection).get_table_names()
        assert "working_time_snapshot_id" not in _columns(connection, "candidate_items")
        assert "candidate_source_weight" not in _columns(connection, "soft_constraint_policy")
        migration.upgrade()

    assert "candidate_item_target" in inspect(connection).get_table_names()
    assert "working_time_snapshot_id" in _columns(connection, "candidate_items")
    assert (
        connection.execute(
            text("SELECT candidate_source_weight FROM soft_constraint_policy WHERE id = 1")
        ).scalar_one()
        == 200
    )
