"""A demo reset keeps the LLM ledger (round 6 PR B1, review of PR #108).

Without this, resetting would renew the paid allowance of the same real day, renew a
trial run, and erase the recorded cost. These tests commit, like test_demo_reset.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.db.models import LlmCallLog, LlmTrialUsage, Staff
from app.db.session import SessionLocal, engine
from app.domain.enums import ExplanationStatus, LlmCallStatus, LlmRefusal, LlmWorkType
from app.integrations.llm import LlmAttempt, LlmRequest, fake
from app.seed import reset as reset_module
from app.seed.reset import reset_demo
from app.services import explanation_service, llm_gateway, llm_service
from tests.integration.test_rank_explanation import _requested_case

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
        _requested_case(db)  # commits
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
        _requested_case(db)  # commits
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

    def broken(db: Session, **kwargs: object) -> None:
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


# --------------------------------------------------------------------------- #
# Concurrent gateway writes (review of PR #108, second round)
# --------------------------------------------------------------------------- #
def _summary(attempt: int, summary_id: int = 50) -> llm_gateway.Subject:
    return llm_gateway.case_summary(
        summary_id=summary_id, case_id=1, prompt_version="v", attempt=attempt, input_hash="h"
    )


def _wait_for_lock_waiter(timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    with engine.connect() as connection:
        while time.monotonic() < deadline:
            if connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                    " AND wait_event_type = 'Lock'"
                )
            ):
                return
            connection.rollback()
            time.sleep(0.02)
    pytest.fail("nothing is waiting for a lock")


def _in_thread(work: Callable[[], object], errors: list[BaseException]) -> threading.Thread:
    def run() -> None:
        try:
            work()
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_a_write_in_progress_is_in_the_copy(spent, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reservation made but not yet committed when the reset starts: the reset waits for
    it and keeps it."""
    monkeypatch.setattr(settings, "llm_daily_call_cap", 10)
    errors: list[BaseException] = []
    db = SessionLocal()
    try:
        ticket = llm_gateway.start(db, _request(), _summary(1))
        assert isinstance(ticket, llm_gateway.Ticket)
        reset = _in_thread(reset_demo, errors)
        _wait_for_lock_waiter()
        db.commit()  # the reset can go on
        reset.join(60)
    finally:
        db.close()
    assert not reset.is_alive() and not errors

    with SessionLocal() as db:
        assert llm_gateway.demo_used(db) == 3
        logs = _logs(db)
        assert len(logs) == 4 and logs[-1].status == LlmCallStatus.IN_FLIGHT


def test_a_reservation_arriving_during_the_reset_is_kept(
    spent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reviewer's case: a gateway call commits after the ledger was copied. It must wait
    for the reset and then count in the rebuilt tables, not be overwritten by the copy."""
    monkeypatch.setattr(settings, "llm_daily_call_cap", 10)
    errors: list[BaseException] = []
    arrived: list[threading.Thread] = []
    results: list[object] = []
    real_hold = reset_module._hold_llm_ledger

    def hold_then_let_a_call_arrive(connection):
        held = real_hold(connection)  # copied and locked

        def call() -> None:
            with SessionLocal() as other:
                results.append(llm_gateway.call(other, _request(), _summary(1)))

        arrived.append(_in_thread(call, errors))
        _wait_for_lock_waiter()
        return held

    monkeypatch.setattr(reset_module, "_hold_llm_ledger", hold_then_let_a_call_arrive)
    reset_demo()
    arrived[0].join(60)
    assert not arrived[0].is_alive() and not errors

    assert isinstance(results[0], LlmAttempt)
    with SessionLocal() as db:
        assert llm_gateway.demo_used(db) == 3  # 2 before the reset, 1 after
        logs = _logs(db)
        assert len(logs) == 4 and logs[-1].status == LlmCallStatus.SUCCEEDED
        assert logs[-1].detached_at is None and logs[-1].subject_id == 50


def test_a_completion_arriving_during_the_reset_lands_on_the_kept_row(
    spent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An attempt already sent whose result is saved while the reset runs: the row has its
    old id after the reset, so the update is not lost."""
    monkeypatch.setattr(settings, "llm_daily_call_cap", 10)
    with SessionLocal() as db:
        ticket = llm_gateway.start(db, _request(), _summary(1))
        assert isinstance(ticket, llm_gateway.Ticket)
        db.commit()
    errors: list[BaseException] = []
    arrived: list[threading.Thread] = []
    real_hold = reset_module._hold_llm_ledger

    def hold_then_let_the_result_arrive(connection):
        held = real_hold(connection)

        def finish() -> None:
            with SessionLocal() as other:
                llm_gateway.send(other, ticket)

        arrived.append(_in_thread(finish, errors))
        _wait_for_lock_waiter()
        return held

    monkeypatch.setattr(reset_module, "_hold_llm_ledger", hold_then_let_the_result_arrive)
    reset_demo()
    arrived[0].join(60)
    assert not arrived[0].is_alive() and not errors

    with SessionLocal() as db:
        logs = _logs(db)
        assert len(logs) == 4
        assert logs[-1].id == ticket.log_id and logs[-1].status == LlmCallStatus.SUCCEEDED
        assert logs[-1].finished_at is not None and logs[-1].estimated_cost_usd is not None


def test_a_result_saved_after_the_reset_lands_on_the_kept_row(
    spent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The provider is still answering while the whole reset runs (no lock is held then)."""
    monkeypatch.setattr(settings, "llm_daily_call_cap", 10)
    answering, release = threading.Event(), threading.Event()

    def slow(request: LlmRequest) -> LlmAttempt:
        answering.set()
        assert release.wait(30)
        return _priced(request)

    monkeypatch.setattr(llm_service, "generate_explanation", slow)
    errors: list[BaseException] = []

    def call() -> None:
        with SessionLocal() as db:
            llm_gateway.call(db, _request(), _summary(1))

    caller = _in_thread(call, errors)
    assert answering.wait(30)
    reset_demo()
    release.set()
    caller.join(60)
    assert not caller.is_alive() and not errors

    with SessionLocal() as db:
        last = _logs(db)[-1]
        assert last.status == LlmCallStatus.SUCCEEDED and last.estimated_cost_usd is not None
        assert last.detached_at is not None  # its subject was deleted by the reset


def test_a_deadlock_with_a_writer_starts_the_reset_over(
    spent, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts: list[int] = []
    real = reset_module._reset_demo

    def deadlocked_once():
        attempts.append(1)
        if len(attempts) == 1:
            raise OperationalError("reset", {}, psycopg.errors.DeadlockDetected("deadlock"))
        return real()

    monkeypatch.setattr(reset_module, "_reset_demo", deadlocked_once)
    reset_demo()

    assert len(attempts) == 2
    with SessionLocal() as db:
        assert len(_logs(db)) == 3 and llm_gateway.demo_quota_left(db) == 0


def test_another_database_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[int] = []

    def broken():
        attempts.append(1)
        raise OperationalError("reset", {}, psycopg.errors.QueryCanceled("slow"))

    monkeypatch.setattr(reset_module, "_reset_demo", broken)
    with pytest.raises(OperationalError):
        reset_demo()
    assert attempts == [1]


# --------------------------------------------------------------------------- #
# A log from before PR B1
# --------------------------------------------------------------------------- #
PREVIOUS_HEAD = "c5f8b0d3e7a1"


def test_reset_from_the_previous_migration_head_keeps_the_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(llm_service, "generate_explanation", _priced)
    reset_demo()
    with SessionLocal() as db:
        _requested_case(db)  # commits
        assert explanation_service.run_pending(db) == 1
        (before,) = _logs(db)
        cost, started_at = before.estimated_cost_usd, before.started_at
        assert cost is not None and cost > 0
    command.downgrade(Config(str(reset_module.ALEMBIC_INI)), PREVIOUS_HEAD)
    with engine.connect() as connection:
        tables = {row[0] for row in connection.execute(text("SELECT tablename FROM pg_tables"))}
        columns = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = 'llm_call_log'"
                )
            )
        }
    assert "work_type" not in columns and "llm_daily_usage" not in tables

    reset_demo()

    with SessionLocal() as db:
        (log,) = _logs(db)
        assert log.work_type == LlmWorkType.RANK_EXPLANATION
        assert log.id == before.id and log.estimated_cost_usd == cost
        assert log.started_at == started_at and log.detached_at is not None
        assert (log.explanation_id, log.case_id, log.plan_id, log.subject_id) == (None,) * 4
        assert _spend(db) == llm_gateway.Spend(known_usd=cost, unknown_calls=0)
        # The counters did not exist, so nothing was counted for the legacy attempt
        assert llm_gateway.demo_used(db) == 0
        assert db.scalar(select(func.count()).select_from(LlmTrialUsage)) == 0
        assert db.scalar(text("SELECT version_num FROM alembic_version")) != PREVIOUS_HEAD
