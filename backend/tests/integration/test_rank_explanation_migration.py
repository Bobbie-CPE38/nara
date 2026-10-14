"""Migration X creates the LLM explanation tables and bounds them with constraints."""

import importlib.util
import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.core import clock
from app.db.models import LlmCallLog, RankExplanation
from app.domain.enums import ExplanationStatus, LlmCallStatus
from tests.integration.case_rows import short_case

BACKEND = Path(__file__).resolve().parents[2]


def migration():
    spec = importlib.util.spec_from_file_location(
        "rank_explanation_migration", next((BACKEND / "alembic/versions").glob("*e1a4c7f2b9d6*"))
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_single_head_follows_line_account_linking():
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert script.get_heads() == ["e1a4c7f2b9d6"]
    assert script.get_revision("e1a4c7f2b9d6").down_revision == "d7f0b3c5e9a2"


def test_downgrade_then_upgrade_round_trip(production_seeded):
    db = production_seeded
    module = migration()
    with Operations.context(MigrationContext.configure(db.connection())):
        module.downgrade()
        tables = set(inspect(db.connection()).get_table_names())
        assert not {"rank_explanation", "llm_call_log"} & tables
        module.upgrade()
    inspector = inspect(db.connection())
    assert {"rank_explanation", "llm_call_log"} <= set(inspector.get_table_names())
    assert "ix_llm_call_log_plan_id" in {i["name"] for i in inspector.get_indexes("llm_call_log")}
    pending = next(
        i
        for i in inspector.get_indexes("rank_explanation")
        if i["name"] == "ix_rank_explanation_pending"
    )
    assert pending["column_names"] == ["id"]


def test_offline_sql_creates_both_tables():
    script = io.StringIO()
    command.upgrade(Config(str(BACKEND / "alembic.ini"), output_buffer=script), "head", sql=True)
    sql = script.getvalue()
    assert "CREATE TABLE rank_explanation" in sql
    assert "CREATE TABLE llm_call_log" in sql
    assert "WHERE status = 'PENDING'" in sql


def _explanation(case_id: int, plan_id: int, version: str) -> RankExplanation:
    return RankExplanation(
        case_id=case_id,
        plan_id=plan_id,
        prompt_version=version,
        status=ExplanationStatus.PENDING,
    )


def test_one_explanation_per_plan_and_prompt_version(production_seeded):
    db = production_seeded
    case, items = short_case(db)
    plan_id = next(iter(items.values())).plan_id
    db.add(_explanation(case.id, plan_id, "v1"))
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(_explanation(case.id, plan_id, "v1"))
        db.flush()
    db.add(_explanation(case.id, plan_id, "v2"))
    db.flush()
    row = db.query(RankExplanation).filter_by(prompt_version="v1").one()
    assert row.attempts == 0 and row.created_at is not None


def test_one_log_row_per_attempt(production_seeded):
    db = production_seeded
    case, items = short_case(db)
    plan_id = next(iter(items.values())).plan_id
    explanation = _explanation(case.id, plan_id, "v1")
    db.add(explanation)
    db.flush()

    def log(attempt: int) -> LlmCallLog:
        return LlmCallLog(
            explanation_id=explanation.id,
            case_id=case.id,
            plan_id=plan_id,
            provider="fake",
            prompt_version="v1",
            attempt=attempt,
            status=LlmCallStatus.IN_FLIGHT,
            started_at=clock.now(),
        )

    db.add(log(1))
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(log(1))
        db.flush()
    db.add(log(2))
    db.flush()
    assert db.scalar(text("SELECT count(*) FROM llm_call_log")) == 2
