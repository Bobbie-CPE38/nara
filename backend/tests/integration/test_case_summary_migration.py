"""Single migration chain, existing data untouched, summary usage retained on downgrade."""

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select

from app.core.config import settings
from app.db.models import CaseSummary, LlmCallLog, LlmDailyUsage
from app.seed.reset import ALEMBIC_INI
from app.services import case_summary_service
from tests.integration.case_rows import short_case

REVISION = "f9a1c3e5b7d2"


def test_one_head_after_e1():
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert script.get_heads() == [REVISION]
    assert script.get_revision(REVISION).down_revision == "e7c3a5d9b1f4"


def test_downgrade_keeps_cost_and_quota_then_upgrade_starts_with_no_summaries(
    production_seeded, monkeypatch
):
    db = production_seeded
    monkeypatch.setattr(settings, "llm_enabled", True)
    case, _ = short_case(db)
    db.commit()
    case_summary_service.request(db, case.id)
    case_summary_service.run_pending(db)
    log = db.scalars(select(LlmCallLog)).one()
    log_id, cost = log.id, log.estimated_cost_usd
    used = db.scalars(select(LlmDailyUsage.used)).one()
    revision = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION)
    with Operations.context(MigrationContext.configure(db.connection())):
        revision.module.downgrade()
        assert "case_summary" not in inspect(db.connection()).get_table_names()
        db.expire_all()
        held = db.get(LlmCallLog, log_id)
        assert held.subject_id is None and held.case_id is None and held.detached_at is not None
        assert held.estimated_cost_usd == cost
        assert db.scalars(select(LlmDailyUsage.used)).one() == used
        revision.module.upgrade()
    assert db.scalars(select(CaseSummary)).all() == []
