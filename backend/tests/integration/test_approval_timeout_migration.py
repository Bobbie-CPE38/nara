"""PR T upgrade retains history, links attempts and refuses ambiguous legacy offers."""

from datetime import timedelta

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core import clock
from app.db.models import ApprovalPolicy
from app.domain.enums import OutreachStatus
from app.seed.reset import ALEMBIC_INI
from app.services import approval_timeout_service
from tests.integration.case_rows import approval, offer, safety, short_case
from tests.integration.conftest import DEMO_NOW

REVISION = "b7d2f8a1c6e4"


def migration():
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION).module


def test_upgrade_backfills_all_history_and_job_only_expires_actionable_request(production_seeded):
    db = production_seeded
    case, items = short_case(db)
    pending = approval(db, case, items[201])
    decided = approval(db, case, items[202], approved=False)
    orphan = approval(db, case, items[203])
    db.execute(
        text("UPDATE candidate_outreach SET status = 'CANCELLED' WHERE id = :id"),
        {"id": orphan.outreach_id},
    )
    validation = safety(db, case, items[201], passed=True)
    expected = {
        pending.id: pending.outreach_id,
        decided.id: decided.outreach_id,
        orphan.id: orphan.outreach_id,
    }
    connection = db.connection()
    with Operations.context(MigrationContext.configure(connection)):
        migration().downgrade()
        migration().upgrade()
    rows = connection.execute(
        text("SELECT id, outreach_id, expires_at, is_timed_out FROM approval_request ORDER BY id")
    ).all()
    assert len(rows) == 3
    for row in rows:
        assert row.outreach_id == expected[row.id]
        assert row.expires_at == DEMO_NOW + timedelta(seconds=900)
        assert not row.is_timed_out
    assert (
        connection.scalar(
            text("SELECT outreach_id FROM safety_validation WHERE id = :id"), {"id": validation.id}
        )
        == pending.outreach_id
    )
    columns = {row["name"]: row for row in inspect(connection).get_columns("approval_request")}
    assert not columns["outreach_id"]["nullable"] and not columns["expires_at"]["nullable"]
    assert (
        connection.scalar(text("SELECT approval_timeout_seconds FROM approval_policy WHERE id = 1"))
        == 900
    )
    db.commit()
    clock.advance(timedelta(seconds=900))
    assert approval_timeout_service.expire_due_approvals(db).approval_ids == [pending.id]


@pytest.mark.parametrize("duplicate", [False, True])
def test_missing_or_duplicate_offer_aborts_before_ddl(seeded, duplicate):
    case, items = short_case(seeded)
    request = approval(seeded, case, items[201])
    connection = seeded.connection()
    with Operations.context(MigrationContext.configure(connection)):
        migration().downgrade()
        if duplicate:
            offer(seeded, case, items[201], OutreachStatus.CANCELLED)
        else:
            connection.execute(
                text("DELETE FROM candidate_outreach WHERE id = :id"), {"id": request.outreach_id}
            )
        with pytest.raises(DBAPIError, match="exactly one offer"), connection.begin_nested():
            migration().upgrade()
    assert "expires_at" not in {
        row["name"] for row in inspect(connection).get_columns("approval_request")
    }
    assert "approval_timeout_seconds" not in {
        row["name"] for row in inspect(connection).get_columns("approval_policy")
    }


@pytest.mark.parametrize("seconds", [0, -1])
def test_approval_timeout_policy_is_positive(seeded, seconds):
    seeded.get(ApprovalPolicy, 1).approval_timeout_seconds = seconds
    with pytest.raises(IntegrityError, match="approval_timeout_positive"):
        seeded.flush()


def test_single_migration_head_and_parent():
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1
    assert script.get_revision(REVISION).down_revision == "a4b8c2d6e9f1"
