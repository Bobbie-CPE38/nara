"""Upgrade has no backfill and SQL enforces a single outcome per offer attempt."""

import io

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import OfferOutcomeNotification
from app.seed.reset import ALEMBIC_INI
from tests.integration.test_offer_outcome_notifications import cancelled

REVISION = "b4e7a9c2d6f0"


def test_upgrade_preserves_offers_and_does_not_backfill_history(production_seeded):
    db = production_seeded
    _, _, row, _ = cancelled(db)
    offer_id = row.id
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1
    assert script.get_revision("c5f8b0d3e7a1").down_revision == REVISION
    revision = script.get_revision(REVISION)
    assert revision.down_revision == "f6b2d8a4c0e1"
    with Operations.context(MigrationContext.configure(db.connection())):
        revision.module.downgrade()
        revision.module.upgrade()
    assert db.scalar(select(func.count()).select_from(OfferOutcomeNotification)) == 0
    assert (
        db.scalar(text("SELECT id FROM candidate_outreach WHERE id=:id"), {"id": offer_id})
        == offer_id
    )


@pytest.mark.parametrize(
    "change", ["delivery_attempts=-1", "delivery_attempts=4", "delivery_status='BOGUS'"]
)
def test_invalid_delivery_values_are_rejected(production_seeded, change):
    db = production_seeded
    _, _, _, out = cancelled(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(f"UPDATE offer_outcome_notification SET {change} WHERE id=:id"), {"id": out.id}
        )


def test_unique_offer_is_enforced_in_sql(production_seeded):
    db = production_seeded
    _, _, _, out = cancelled(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text("""
            INSERT INTO offer_outcome_notification
                (outreach_id, case_id, staff_id, audit_id, reason, message, created_at)
            SELECT outreach_id, case_id, staff_id, audit_id, reason, message, created_at
            FROM offer_outcome_notification WHERE id=:id
        """),
            {"id": out.id},
        )


def test_offline_upgrade_and_downgrade():
    output = io.StringIO()
    command.upgrade(Config(str(ALEMBIC_INI), output_buffer=output), "head", sql=True)
    assert "CREATE TABLE offer_outcome_notification" in output.getvalue()
    output = io.StringIO()
    command.downgrade(
        Config(str(ALEMBIC_INI), output_buffer=output), f"{REVISION}:f6b2d8a4c0e1", sql=True
    )
    assert "DROP TABLE offer_outcome_notification" in output.getvalue()
