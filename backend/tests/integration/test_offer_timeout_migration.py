"""Offer expiry migration upgrades existing history without replacing it."""

import io
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.models import OutreachPolicy
from app.domain.enums import OutreachStatus
from app.seed.reset import ALEMBIC_INI
from tests.integration.case_rows import offer, short_case
from tests.integration.conftest import DEMO_NOW

REVISION = "a4b8c2d6e9f1"


def migration():
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION).module


def test_upgrade_backfills_initial_duration_and_sent_timestamps(seeded):
    db = seeded
    case, items = short_case(db)
    sent = offer(db, case, items[201])
    accepted = offer(db, case, items[202], OutreachStatus.ACCEPTED)
    historical = offer(db, case, items[203], OutreachStatus.REJECTED)
    historical.sent_at = None
    db.flush()
    connection = db.connection()
    with Operations.context(MigrationContext.configure(connection)):
        migration().downgrade()
        migration().upgrade()
    rows = dict(connection.execute(text("SELECT id, expires_at FROM candidate_outreach")).all())
    assert rows[sent.id] == rows[accepted.id] == DEMO_NOW + timedelta(seconds=300)
    assert rows[historical.id] is None
    assert (
        connection.scalar(text("SELECT offer_timeout_seconds FROM outreach_policy WHERE id = 1"))
        == 300
    )
    column = next(
        c
        for c in inspect(connection).get_columns("outreach_policy")
        if c["name"] == "offer_timeout_seconds"
    )
    assert column["nullable"] is False and column["default"] is None


def test_upgrade_refuses_sent_rows_without_a_timestamp_before_changing_schema(seeded):
    db = seeded
    case, items = short_case(db)
    row = offer(db, case, items[201])
    connection = db.connection()
    with Operations.context(MigrationContext.configure(connection)):
        migration().downgrade()
        connection.execute(
            text("UPDATE candidate_outreach SET sent_at = NULL WHERE id = :id"), {"id": row.id}
        )
        with (
            pytest.raises(DBAPIError, match="repair SENT offers missing sent_at"),
            connection.begin_nested(),
        ):
            migration().upgrade()
    assert "expires_at" not in {
        c["name"] for c in inspect(connection).get_columns("candidate_outreach")
    }


def test_offline_upgrade_contains_guard_and_backfill():
    output = io.StringIO()
    command.upgrade(Config(str(ALEMBIC_INI), output_buffer=output), "head", sql=True)
    sql = output.getvalue()
    assert sql.index("repair SENT offers missing sent_at") < sql.index("ADD COLUMN expires_at")
    assert "INTERVAL '300 seconds'" in sql
    assert len(ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads()) == 1


@pytest.mark.parametrize("seconds", [0, -1])
def test_timeout_must_be_positive(seeded, seconds):
    seeded.get(OutreachPolicy, 1).offer_timeout_seconds = seconds
    with pytest.raises(IntegrityError, match="offer_timeout_positive"):
        seeded.flush()


def test_sent_offer_requires_an_expiry(seeded):
    case, items = short_case(seeded)
    row = offer(seeded, case, items[201])
    row.expires_at = None
    with pytest.raises(IntegrityError, match="sent_has_expiry"):
        seeded.flush()
