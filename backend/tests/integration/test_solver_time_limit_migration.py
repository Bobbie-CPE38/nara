"""PR B adds soft_constraint_policy.solver_time_limit_seconds."""

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.models import SoftConstraintPolicy
from app.seed.reset import ALEMBIC_INI

REVISION = "c9e4a7b2d5f8"
WEIGHTS = (
    "candidate_count_weight, consecutive_shift_weight, workload_imbalance_weight, "
    "projected_overtime_weight, roster_change_weight, candidate_source_weight"
)


def migration():
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION).module


def test_upgrade_backfills_five_seconds_and_keeps_weights(seeded):
    connection = seeded.connection()
    query = text(f"SELECT {WEIGHTS} FROM soft_constraint_policy WHERE id = 1")
    before = tuple(connection.execute(query).one())
    with Operations.context(MigrationContext.configure(connection)):
        migration().downgrade()
        assert "solver_time_limit_seconds" not in {
            row["name"] for row in inspect(connection).get_columns("soft_constraint_policy")
        }
        migration().upgrade()
    columns = inspect(connection).get_columns("soft_constraint_policy")
    assert not {row["name"]: row for row in columns}["solver_time_limit_seconds"]["nullable"]
    assert (
        connection.scalar(
            text("SELECT solver_time_limit_seconds FROM soft_constraint_policy WHERE id = 1")
        )
        == 5
    )
    assert tuple(connection.execute(query).one()) == before


@pytest.mark.parametrize("seconds", [0, -1])
def test_solver_time_limit_is_positive(seeded, seconds):
    seeded.get(SoftConstraintPolicy, 1).solver_time_limit_seconds = seconds
    with pytest.raises(IntegrityError, match="solver_time_limit_positive"):
        seeded.flush()


def test_single_migration_head_and_parent():
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1
    assert script.get_revision(REVISION).down_revision == "b7d2f8a1c6e4"
