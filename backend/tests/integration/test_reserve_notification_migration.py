"""Promotion migration preserves old final UUIDs and marks actual waiting reserves."""

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import select, text

from app.db.models import CandidateOutreach, OfferOutcomeNotification
from app.domain.enums import OutreachStatus
from app.seed.reset import ALEMBIC_INI
from tests.integration import test_line_messaging as line_tests
from tests.integration.case_rows import offer
from tests.integration.test_offer_outcome_notifications import cancelled

real_line = line_tests.real_line


def test_reserve_upgrade_and_downgrade_preserve_final_history(production_seeded, real_line):
    db = production_seeded
    case, items, row, final = cancelled(db)
    reserve = offer(db, case, items[202], OutreachStatus.ACCEPTED)
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1
    # Round 6 PR B1 follows this revision
    assert script.get_revision("d2a6f9c1e4b7").down_revision == "c5f8b0d3e7a1"
    revision = script.get_revision("c5f8b0d3e7a1")
    assert revision.down_revision == "b4e7a9c2d6f0"
    before = final.message, final.delivery_retry_key, final.delivery_status
    assert final.delivery_retry_key is not None
    with Operations.context(MigrationContext.configure(db.connection())):
        revision.module.downgrade()
        revision.module.upgrade()
    db.expire_all()
    assert db.get(CandidateOutreach, reserve.id).accepted_as_reserve is True
    final = db.scalars(select(OfferOutcomeNotification)).one()
    assert final.kind == "FINAL"
    assert (final.message, final.delivery_retry_key, final.delivery_status) == before
    assert db.get(CandidateOutreach, row.id).accepted_as_reserve is False
    checks = db.execute(
        text(
            "SELECT count(*) FROM pg_constraint WHERE conname='ck_offer_outcome_notification_kind'"
        )
    ).scalar_one()
    assert checks == 1
