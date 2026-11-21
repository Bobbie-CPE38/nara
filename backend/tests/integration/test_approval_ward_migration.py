"""PR S: schema invariants, safe policy backfill and a single migration chain."""

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.models import ApprovalPolicy, ApprovalRequest
from app.seed.reset import ALEMBIC_INI
from tests.integration.case_rows import approval, short_case

REVISION = "f2a7c9d4e6b8"


def migration():
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION).module


@pytest.mark.parametrize("delay", [0, -1, 900, 901])
def test_supervisor_delay_is_positive_and_less_than_timeout(seeded, delay):
    with pytest.raises(IntegrityError, match="supervisor_delay_valid"), seeded.begin_nested():
        seeded.get(ApprovalPolicy, 1).supervisor_after_seconds = delay
        seeded.flush()


def test_upgrade_backfills_existing_policies_and_preserves_pending_requests(seeded):
    case, items = short_case(seeded, 105)
    request = approval(seeded, case, items[201])
    connection = seeded.connection()
    with Operations.context(MigrationContext.configure(connection)):
        migration().downgrade()
        assert "approval_ward_decision" not in inspect(connection).get_table_names()
        connection.execute(text("UPDATE approval_policy SET approval_timeout_seconds = 60"))
        migration().upgrade()
    assert (
        connection.execute(
            text("SELECT supervisor_after_seconds FROM approval_policy")
        ).scalar_one()
        == 59
    )
    assert seeded.get(ApprovalRequest, request.id).is_pending
    assert "approval_ward_decision" in inspect(connection).get_table_names()


def test_impossible_policy_aborts_upgrade_before_adding_column(seeded):
    connection = seeded.connection()
    with Operations.context(MigrationContext.configure(connection)):
        migration().downgrade()
        connection.execute(text("UPDATE approval_policy SET approval_timeout_seconds = 1"))
        with (
            pytest.raises(DBAPIError, match="requires approval_timeout_seconds > 1"),
            connection.begin_nested(),
        ):
            migration().upgrade()
    assert "supervisor_after_seconds" not in {
        row["name"] for row in inspect(connection).get_columns("approval_policy")
    }


def test_single_head_and_parent():
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1
    assert script.get_revision(REVISION).down_revision == "c6e2b9f4a1d7"


@pytest.mark.parametrize("timeout, delay", [(60, 30), (600, 599)])
def test_new_policy_accepts_explicit_delay_below_short_timeout(seeded, timeout, delay):
    policy = ApprovalPolicy(
        id=2,
        ratio=2,
        incoming_count=10,
        version="short-timeout",
        approval_timeout_seconds=timeout,
        supervisor_after_seconds=delay,
        supervisor_ratio=5,
        supervisor_incoming_count=10,
    )
    seeded.add(policy)
    seeded.flush()
    assert seeded.get(ApprovalPolicy, 2).supervisor_after_seconds == delay


def test_new_policy_requires_explicit_supervisor_delay(seeded):
    with pytest.raises(IntegrityError, match="supervisor_after_seconds"), seeded.begin_nested():
        seeded.add(
            ApprovalPolicy(
                id=2,
                ratio=2,
                incoming_count=10,
                version="missing-delay",
                approval_timeout_seconds=60,
            )
        )
        seeded.flush()
