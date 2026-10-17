"""Round 6 PR B1 migration: every work type in llm_call_log, and the two quota counters."""

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text

from app.core import clock
from app.db.models import LlmCallLog, RankExplanation
from app.domain.enums import ExplanationStatus, LlmCallStatus, LlmWorkType
from app.seed.reset import ALEMBIC_INI
from tests.integration.case_rows import short_case

REVISION = "d2a6f9c1e4b7"


def test_the_migration_is_the_single_head_after_reserve_notifications():
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert script.get_heads() == [REVISION]
    assert script.get_revision(REVISION).down_revision == "c5f8b0d3e7a1"


def test_round_trip_keeps_explanation_attempts_and_drops_other_types(production_seeded):
    db = production_seeded
    case, items = short_case(db)
    plan_id = next(iter(items.values())).plan_id
    explanation = RankExplanation(
        case_id=case.id, plan_id=plan_id, prompt_version="v", status=ExplanationStatus.PENDING
    )
    db.add(explanation)
    db.flush()
    common = {
        "provider": "fake",
        "prompt_version": "v",
        "attempt": 1,
        "status": LlmCallStatus.SUCCEEDED,
        "started_at": clock.now(),
    }
    db.add_all(
        [
            LlmCallLog(
                work_type=LlmWorkType.RANK_EXPLANATION,
                explanation_id=explanation.id,
                case_id=case.id,
                plan_id=plan_id,
                **common,
            ),
            LlmCallLog(work_type=LlmWorkType.CASE_SUMMARY, subject_id=1, case_id=case.id, **common),
            LlmCallLog(
                work_type=LlmWorkType.MODEL_TRIAL, trial_run_id="r", trial_case_key="k", **common
            ),
            LlmCallLog(work_type=LlmWorkType.RANK_EXPLANATION, detached_at=clock.now(), **common),
        ]
    )
    db.flush()
    revision = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION)

    with Operations.context(MigrationContext.configure(db.connection())):
        revision.module.downgrade()
        inspector = inspect(db.connection())
        assert not {"llm_daily_usage", "llm_trial_usage"} & set(inspector.get_table_names())
        columns = {c["name"]: c for c in inspector.get_columns("llm_call_log")}
        assert "work_type" not in columns and columns["plan_id"]["nullable"] is False
        assert db.execute(text("SELECT count(*) FROM llm_call_log")).scalar_one() == 1
        revision.module.upgrade()

    db.expire_all()
    (log,) = db.scalars(select(LlmCallLog))
    assert log.work_type == LlmWorkType.RANK_EXPLANATION and log.explanation_id == explanation.id
    inspector = inspect(db.connection())
    assert {"llm_daily_usage", "llm_trial_usage"} <= set(inspector.get_table_names())
    default = {c["name"]: c for c in inspector.get_columns("llm_call_log")}["work_type"]["default"]
    assert default is None  # new rows must name their type
    checks = {c["name"] for c in inspector.get_check_constraints("llm_call_log")}
    assert "ck_llm_call_log_work_type_subject" in checks
    indexes = {i["name"] for i in inspector.get_indexes("llm_call_log")}
    assert {"uq_llm_call_log_case_summary_attempt", "uq_llm_call_log_model_trial_attempt"} <= (
        indexes
    )
