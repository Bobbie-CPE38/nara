"""A demo reset keeps the LLM ledger (round 6 PR B1, review of PR #108).

Without this, resetting would renew the paid allowance of the same real day, renew a
trial run, and erase the recorded cost. These tests commit, like test_demo_reset.
"""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.db.models import LlmCallLog, LlmTrialUsage, Staff
from app.db.session import SessionLocal
from app.domain.enums import ExplanationStatus, LlmCallStatus, LlmRefusal, LlmWorkType
from app.integrations.llm import LlmAttempt, LlmRequest, fake
from app.seed import reset as reset_module
from app.seed.reset import reset_demo
from app.services import explanation_service, llm_gateway, llm_service
from tests.integration.test_rank_explanation import _planned_case

pytestmark = pytest.mark.usefixtures("restore_empty_database")

TRIAL_RUN = "reset-test-run"


def _priced(request: LlmRequest) -> LlmAttempt:
    """The fake answer with a price, so the attempt has a cost to keep."""
    return replace(
        fake.generate(request),
        input_tokens=1_000,
        output_tokens=100,
        input_rate=Decimal("0.41"),
        output_rate=Decimal("3.39"),
    )


def _request() -> LlmRequest:
    return LlmRequest(
        system="s",
        prompt="p",
        payload={"candidates": [{"rank": 1}]},
        max_output_tokens=10,
        timeout_seconds=1,
    )


def _spend(db: Session) -> llm_gateway.Spend:
    now = clock.now()
    return llm_gateway.spend(db, start_at=now - timedelta(days=400), end_at=now + timedelta(400))


def _logs(db: Session) -> list[LlmCallLog]:
    return list(db.scalars(select(LlmCallLog).order_by(LlmCallLog.id)))


@pytest.fixture
def spent(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """After a reset: one ranking explanation, one case summary and one trial attempt.
    The daily cap equals what was used, so the day is exhausted."""
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_daily_call_cap", 2)
    monkeypatch.setattr(llm_service, "generate_explanation", _priced)
    reset_demo()
    with SessionLocal() as db:
        _planned_case(db)
        db.commit()
        assert explanation_service.run_pending(db) == 1
        summary = llm_gateway.case_summary(
            summary_id=1, case_id=1, prompt_version="v", attempt=1, input_hash="h"
        )
        assert isinstance(llm_gateway.call(db, _request(), summary), LlmAttempt)
        llm_gateway.create_trial_run(db, TRIAL_RUN, cap=3)
        db.commit()
        trial = llm_gateway.model_trial(
            trial_run_id=TRIAL_RUN,
            trial_case_key="case-1/fake",
            prompt_version="v",
            attempt=1,
            input_hash="h",
        )
        assert isinstance(llm_gateway.call(db, _request(), trial), LlmAttempt)
        assert llm_gateway.demo_quota_left(db) == 0
        logs = _logs(db)
        assert [log.work_type for log in logs] == [
            LlmWorkType.RANK_EXPLANATION,
            LlmWorkType.CASE_SUMMARY,
            LlmWorkType.MODEL_TRIAL,
        ]
        return {
            "ids": [log.id for log in logs],
            "costs": [log.estimated_cost_usd for log in logs],
            "spend": _spend(db),
        }


def test_a_reset_keeps_the_exhausted_day(spent) -> None:
    reset_demo()

    with SessionLocal() as db:
        assert llm_gateway.demo_quota_left(db) == 0
        summary = llm_gateway.case_summary(
            summary_id=2, case_id=1, prompt_version="v", attempt=1, input_hash="h"
        )
        assert llm_gateway.call(db, _request(), summary) == LlmRefusal.QUOTA_EXHAUSTED


def test_a_reset_keeps_the_trial_usage_and_its_cap(spent) -> None:
    reset_demo()

    with SessionLocal() as db:
        again = llm_gateway.create_trial_run(db, TRIAL_RUN, cap=180)
        assert (again.cap, again.used) == (3, 1)
        db.commit()
        usage = db.get(LlmTrialUsage, TRIAL_RUN)
        assert usage is not None and (usage.cap, usage.used) == (3, 1)


def test_a_reset_keeps_the_call_history_and_its_spend(spent) -> None:
    reset_demo()
    reset_demo()  # twice: detached_at keeps the first reset

    with SessionLocal() as db:
        logs = _logs(db)
        assert [log.id for log in logs] == spent["ids"]
        assert [log.estimated_cost_usd for log in logs] == spent["costs"]
        assert all(cost and cost > 0 for cost in spent["costs"])
        assert _spend(db) == spent["spend"]
        ranked, summary, trial = logs
        # The demo rows they referred to are gone; the ids restart after a reset
        for log in (ranked, summary):
            assert log.detached_at is not None
            assert (log.explanation_id, log.case_id, log.plan_id, log.subject_id) == (
                None,
                None,
                None,
                None,
            )
        assert ranked.detached_at == summary.detached_at
        assert trial.detached_at is None
        assert (trial.trial_run_id, trial.trial_case_key) == (TRIAL_RUN, "case-1/fake")


def test_new_attempts_after_a_reset_follow_the_kept_ids(
    spent, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset_demo()
    monkeypatch.setattr(settings, "llm_daily_call_cap", 10)

    with SessionLocal() as db:
        _planned_case(db)
        db.commit()
        assert explanation_service.run_pending(db) == 1
        logs = _logs(db)
        assert len(logs) == 4 and logs[-1].id > max(spent["ids"])
        assert logs[-1].explanation_id is not None and logs[-1].detached_at is None
        assert logs[-1].status == LlmCallStatus.SUCCEEDED


def test_a_failed_reset_changes_nothing(spent, monkeypatch: pytest.MonkeyPatch) -> None:
    with SessionLocal() as db:
        staff_before = db.scalar(select(func.count()).select_from(Staff))
        rows_before = db.scalar(
            select(func.count()).select_from(explanation_service.RankExplanation)
        )

    def broken(db: Session) -> None:
        raise RuntimeError("seed failed")

    monkeypatch.setattr(reset_module, "load", broken)
    with pytest.raises(RuntimeError, match="seed failed"):
        reset_demo()

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Staff)) == staff_before
        (row,) = db.scalars(select(explanation_service.RankExplanation))
        assert rows_before == 1 and row.status == ExplanationStatus.READY
        assert [log.detached_at for log in _logs(db)] == [None, None, None]
        assert llm_gateway.demo_quota_left(db) == 0
