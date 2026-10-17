"""LLM gateway (round 6 PR B1): quota, call log and the one path to the provider.

Offline: the fake adapter runs, or llm_service.generate_explanation is replaced. The tests
marked "committed" use real sessions and delete their own rows, since a second connection
cannot see the rolled-back `db` fixture.
"""

import ast
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.db.models import LlmCallLog, LlmDailyUsage, LlmTrialUsage
from app.db.session import SessionLocal, engine
from app.domain.enums import LlmCallStatus, LlmQuotaScope, LlmRefusal, LlmWorkType
from app.integrations.llm import LlmAttempt, LlmRequest, fake
from app.services import llm_gateway as gateway
from app.services import llm_service

APP = Path(__file__).resolve().parents[2] / "app"
PAYLOAD = {
    "candidates": [
        {
            "rank": 1,
            "first_wave": True,
            "terms": [{"name": "OVERTIME", "value": 2, "weight": 2, "points": 4}],
        }
    ]
}
# A day no other test writes, far from the real date of a run
OLD_DAY_AT = datetime(2001, 1, 1, 12, 0, tzinfo=UTC)
TEST_RUN_PREFIX = "b1-test-"
DETACHED = datetime(2026, 10, 1, tzinfo=UTC)


def _request(prompt: str = "Explain.", max_output_tokens: int = 100) -> LlmRequest:
    return LlmRequest(
        system="system",
        prompt=prompt,
        payload=PAYLOAD,
        max_output_tokens=max_output_tokens,
        timeout_seconds=1,
    )


def _summary(attempt: int = 1, summary_id: int = 1) -> gateway.Subject:
    return gateway.case_summary(
        summary_id=summary_id, case_id=1, prompt_version="v", attempt=attempt, input_hash="h"
    )


def _trial(run: str, attempt: int = 1, key: str = "case-1/fake") -> gateway.Subject:
    return gateway.model_trial(
        trial_run_id=run, trial_case_key=key, prompt_version="v", attempt=attempt, input_hash="h"
    )


def _daily(db: Session) -> list[LlmDailyUsage]:
    return list(db.scalars(select(LlmDailyUsage).execution_options(populate_existing=True)))


def _logs(db: Session) -> list[LlmCallLog]:
    db.expire_all()
    return list(db.scalars(select(LlmCallLog).order_by(LlmCallLog.id)))


class Spy:
    def __init__(self) -> None:
        self.requests: list[LlmRequest] = []

    def __call__(self, request: LlmRequest) -> LlmAttempt:
        self.requests.append(request)
        return fake.generate(request)


@pytest.fixture
def llm_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_enabled", True)


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Spy:
    installed = Spy()
    monkeypatch.setattr(llm_service, "generate_explanation", installed)
    return installed


@pytest.fixture
def cap(monkeypatch: pytest.MonkeyPatch) -> Callable[[int], None]:
    def set_cap(value: int) -> None:
        monkeypatch.setattr(settings, "llm_daily_call_cap", value)

    return set_cap


# --------------------------------------------------------------------------- #
# One attempt
# --------------------------------------------------------------------------- #
def test_an_attempt_is_counted_and_logged_before_the_call(db: Session, llm_on, spy) -> None:
    ticket = gateway.start(db, _request(), _summary())
    assert isinstance(ticket, gateway.Ticket)
    (log,) = _logs(db)
    assert log.status == LlmCallStatus.IN_FLIGHT and log.work_type == LlmWorkType.CASE_SUMMARY
    assert [row.used for row in _daily(db)] == [1]
    assert spy.requests == []
    db.commit()

    result = gateway.send(db, ticket)

    assert result.status == LlmCallStatus.SUCCEEDED and len(spy.requests) == 1
    (log,) = _logs(db)
    assert log.status == LlmCallStatus.SUCCEEDED and log.finished_at is not None
    assert log.input_tokens and log.estimated_cost_usd == 0
    assert (log.subject_id, log.case_id, log.plan_id, log.explanation_id) == (1, 1, None, None)


def test_send_refuses_an_open_transaction_and_a_second_send(db: Session, llm_on, spy) -> None:
    ticket = gateway.start(db, _request(), _summary())
    assert isinstance(ticket, gateway.Ticket)

    with pytest.raises(RuntimeError, match="commit or roll back"):
        gateway.send(db, ticket)
    db.commit()
    gateway.send(db, ticket)
    with pytest.raises(RuntimeError, match="already sent"):
        gateway.send(db, ticket)

    assert len(spy.requests) == 1


def test_a_raising_provider_is_logged_by_type_only(
    db: Session, llm_on, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    def boom(request: LlmRequest) -> LlmAttempt:
        raise RuntimeError("SECRET-do-not-log")

    monkeypatch.setattr(llm_service, "generate_explanation", boom)

    result = gateway.call(db, _request(), _summary())

    assert isinstance(result, LlmAttempt) and result.status == LlmCallStatus.SERVICE_ERROR
    (log,) = _logs(db)
    assert log.error_type == "RuntimeError" and log.estimated_cost_usd is None
    assert "SECRET-do-not-log" not in caplog.text


def test_the_output_cap_bounds_every_request(
    db: Session, llm_on, spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_max_output_tokens", 50)

    gateway.call(db, _request(max_output_tokens=4000), _summary(1))
    gateway.call(db, _request(max_output_tokens=20), _summary(2))

    assert [r.max_output_tokens for r in spy.requests] == [50, 20]


# --------------------------------------------------------------------------- #
# Refusals: nothing sent, nothing logged, no quota used
# --------------------------------------------------------------------------- #
def _assert_nothing_spent(db: Session, spy: Spy) -> None:
    assert spy.requests == [] and _logs(db) == [] and _daily(db) == []


def test_demo_work_is_refused_while_llm_is_off(db: Session, spy) -> None:
    assert settings.llm_enabled is False
    assert gateway.call(db, _request(), _summary()) == LlmRefusal.DISABLED
    _assert_nothing_spent(db, spy)


def test_bedrock_without_a_model_is_refused(
    db: Session, llm_on, spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(settings, "llm_model_id", None)
    monkeypatch.setattr(settings, "aws_region", "ap-southeast-1")

    assert gateway.call(db, _request(), _summary()) == LlmRefusal.NOT_CONFIGURED
    _assert_nothing_spent(db, spy)


def test_a_payload_over_the_input_cap_is_not_sent(
    db: Session, llm_on, spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_max_input_tokens", 100)
    # "system" is 6 bytes: 6 + 294 = 300 bytes = 100 tokens, the cap itself
    at_cap = _request(prompt="x" * 294)
    assert gateway.estimate_input_tokens(at_cap) == 100
    over = _request(prompt="x" * 295)

    assert gateway.call(db, over, _summary(1)) == LlmRefusal.INPUT_TOO_LARGE
    _assert_nothing_spent(db, spy)
    assert isinstance(gateway.call(db, at_cap, _summary(2)), LlmAttempt)


def test_thai_text_counts_one_token_per_character() -> None:
    request = LlmRequest(
        system="", prompt="อันดับ", payload={}, max_output_tokens=1, timeout_seconds=1
    )
    assert gateway.estimate_input_tokens(request) == len("อันดับ")


def test_the_daily_cap_stops_calls(db: Session, llm_on, spy, cap) -> None:
    cap(2)

    results = [gateway.call(db, _request(), _summary(n)) for n in (1, 2, 3)]

    assert [isinstance(r, LlmAttempt) for r in results] == [True, True, False]
    assert results[2] == LlmRefusal.QUOTA_EXHAUSTED
    assert len(spy.requests) == 2 and len(_logs(db)) == 2
    assert [row.used for row in _daily(db)] == [2]
    assert gateway.demo_quota_left(db) == 0


def test_a_zero_cap_allows_nothing(db: Session, llm_on, spy, cap) -> None:
    cap(0)
    assert gateway.call(db, _request(), _summary()) == LlmRefusal.QUOTA_EXHAUSTED
    _assert_nothing_spent(db, spy)


def test_a_lowered_cap_applies_to_the_running_day(db: Session, llm_on, spy, cap) -> None:
    cap(5)
    gateway.call(db, _request(), _summary(1))
    gateway.call(db, _request(), _summary(2))
    cap(1)

    assert gateway.call(db, _request(), _summary(3)) == LlmRefusal.QUOTA_EXHAUSTED
    assert [row.used for row in _daily(db)] == [2]


def test_the_day_turns_at_midnight_in_bangkok(db: Session, cap) -> None:
    cap(1)
    before = datetime(2001, 1, 1, 16, 59, 59, tzinfo=UTC)  # 23:59:59 in Bangkok
    after = datetime(2001, 1, 1, 17, 0, 0, tzinfo=UTC)  # 00:00:00 the next day

    assert gateway._reserve_demo(db, at=before)
    assert not gateway._reserve_demo(db, at=before)
    assert gateway._reserve_demo(db, at=after)

    rows = {row.usage_date.isoformat(): row.used for row in _daily(db)}
    assert rows == {"2001-01-01": 1, "2001-01-02": 1}
    assert gateway.demo_used(db, at=before) == 1 and gateway.demo_quota_left(db, at=after) == 0


def test_moving_the_demo_clock_does_not_renew_the_day(db: Session, llm_on, spy, cap) -> None:
    cap(1)
    clock.set_time(datetime.now(UTC))
    try:
        assert isinstance(gateway.call(db, _request(), _summary(1)), LlmAttempt)
        clock.advance(timedelta(days=2))
        assert gateway.call(db, _request(), _summary(2)) == LlmRefusal.QUOTA_EXHAUSTED
    finally:
        clock.reset()


# --------------------------------------------------------------------------- #
# Model trial scope
# --------------------------------------------------------------------------- #
def test_the_scope_follows_the_work_type() -> None:
    assert gateway.scope_of(LlmWorkType.MODEL_TRIAL) == LlmQuotaScope.TRIAL
    assert gateway.scope_of(LlmWorkType.RANK_EXPLANATION) == LlmQuotaScope.DEMO
    assert gateway.scope_of(LlmWorkType.CASE_SUMMARY) == LlmQuotaScope.DEMO


def test_a_trial_runs_without_llm_enabled_and_leaves_the_daily_count(db: Session, spy) -> None:
    gateway.create_trial_run(db, "run-a", cap=2)

    results = [gateway.call(db, _request(), _trial("run-a", attempt=n)) for n in (1, 2, 3)]

    assert results[2] == LlmRefusal.QUOTA_EXHAUSTED and len(spy.requests) == 2
    assert _daily(db) == []
    logs = _logs(db)
    assert [log.work_type for log in logs] == [LlmWorkType.MODEL_TRIAL] * 2
    assert all(log.case_id is None and log.plan_id is None for log in logs)
    assert db.get(LlmTrialUsage, "run-a").used == 2


def test_an_unknown_trial_run_has_no_allowance(db: Session, spy) -> None:
    assert gateway.call(db, _request(), _trial("never-created")) == LlmRefusal.QUOTA_EXHAUSTED
    assert spy.requests == [] and _logs(db) == []


def test_the_trial_cap_is_fixed_when_the_run_is_created(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert settings.llm_trial_call_cap == 180
    first = gateway.create_trial_run(db, "run-b", cap=10)
    again = gateway.create_trial_run(db, "run-b", cap=100)
    default = gateway.create_trial_run(db, "run-c")

    assert (first.cap, again.cap, default.cap) == (10, 10, 180)
    with pytest.raises(ValueError):
        gateway.create_trial_run(db, "run-d", cap=181)
    # Raising the setting later does not raise a run that exists
    monkeypatch.setattr(settings, "llm_trial_call_cap", 500)
    assert gateway.create_trial_run(db, "run-b", cap=400).cap == 10


# --------------------------------------------------------------------------- #
# Log shape
# --------------------------------------------------------------------------- #
def _raw_log(db: Session, **columns: Any) -> None:
    values = {
        "provider": "fake",
        "prompt_version": "v",
        "attempt": 1,
        "status": "IN_FLIGHT",
        "started_at": clock.now(),
        "created_at": clock.now(),
        **columns,
    }
    names = ", ".join(values)
    params = ", ".join(f":{name}" for name in values)
    db.execute(text(f"INSERT INTO llm_call_log ({names}) VALUES ({params})"), values)


@pytest.mark.parametrize(
    "columns",
    [
        {"work_type": "CASE_SUMMARY", "case_id": 1},  # no subject_id
        {"work_type": "CASE_SUMMARY", "subject_id": 1, "case_id": 1, "plan_id": 1},
        {"work_type": "MODEL_TRIAL", "trial_run_id": "r"},  # no case key
        {"work_type": "MODEL_TRIAL", "trial_run_id": "r", "trial_case_key": "k", "case_id": 1},
        {"work_type": "RANK_EXPLANATION", "case_id": 1, "plan_id": 1},  # no explanation
        {"work_type": "SOMETHING_ELSE", "trial_run_id": "r", "trial_case_key": "k"},
        # Detached by a demo reset: no references, and never a trial
        {"work_type": "CASE_SUMMARY", "subject_id": 1, "case_id": 1, "detached_at": DETACHED},
        {"work_type": "RANK_EXPLANATION", "plan_id": 1, "detached_at": DETACHED},
        {
            "work_type": "MODEL_TRIAL",
            "trial_run_id": "r",
            "trial_case_key": "k",
            "detached_at": DETACHED,
        },
        {"work_type": "MODEL_TRIAL", "detached_at": DETACHED},
    ],
)
def test_the_check_rejects_a_mixed_or_incomplete_row(db: Session, columns) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_llm_call_log_work_type_subject"),
        db.begin_nested(),
    ):
        _raw_log(db, **columns)


@pytest.mark.parametrize("work_type", ["RANK_EXPLANATION", "CASE_SUMMARY"])
def test_a_detached_row_keeps_only_its_type_and_cost(db: Session, work_type: str) -> None:
    _raw_log(db, work_type=work_type, detached_at=DETACHED, estimated_cost_usd=Decimal(1))
    _raw_log(db, work_type=work_type, detached_at=DETACHED)  # no unique on NULL references
    assert db.scalar(text("SELECT count(*) FROM llm_call_log")) == 2


def test_one_log_row_per_attempt_of_each_type(db: Session) -> None:
    summary = {"work_type": "CASE_SUMMARY", "subject_id": 7, "case_id": 1}
    trial = {"work_type": "MODEL_TRIAL", "trial_run_id": "r", "trial_case_key": "k"}
    for columns in (summary, trial):
        _raw_log(db, **columns)
        with pytest.raises(IntegrityError, match="uq_llm_call_log_"), db.begin_nested():
            _raw_log(db, **columns)
        _raw_log(db, **columns, attempt=2)
    _raw_log(db, **{**trial, "trial_case_key": "k2"})
    assert db.scalar(text("SELECT count(*) FROM llm_call_log")) == 5


def test_spend_adds_up_every_work_type(db: Session) -> None:
    now = clock.now()
    for columns, cost in (
        ({"work_type": "CASE_SUMMARY", "subject_id": 1, "case_id": 1}, Decimal("0.25")),
        ({"work_type": "MODEL_TRIAL", "trial_run_id": "r", "trial_case_key": "k"}, Decimal("1")),
        ({"work_type": "MODEL_TRIAL", "trial_run_id": "r", "trial_case_key": "j"}, None),
    ):
        _raw_log(db, **columns, estimated_cost_usd=cost, started_at=now)
    _raw_log(
        db,
        work_type="CASE_SUMMARY",
        subject_id=2,
        case_id=1,
        estimated_cost_usd=Decimal(5),
        started_at=now - timedelta(days=40),
    )

    total = gateway.spend(db, start_at=now - timedelta(days=1), end_at=now + timedelta(days=1))

    assert total == gateway.Spend(known_usd=Decimal("1.25"), unknown_calls=1)


# --------------------------------------------------------------------------- #
# Only the gateway reaches the provider
# --------------------------------------------------------------------------- #
def test_only_the_gateway_calls_the_provider_in_app_code() -> None:
    """Static check: generate_explanation and the adapters' generate are called in exactly
    one place, llm_gateway.send() and llm_service.generate_explanation() respectively."""
    callers: dict[str, set[str]] = {}
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                name = node.func.attr
                if name in {"generate_explanation", "generate", "converse"}:
                    callers.setdefault(name, set()).add(path.relative_to(APP).as_posix())
    assert callers == {
        "generate_explanation": {"services/llm_gateway.py"},
        "generate": {"services/llm_service.py"},
        "converse": {"integrations/llm/bedrock.py"},
    }


# --------------------------------------------------------------------------- #
# Committed: two connections
# --------------------------------------------------------------------------- #
@pytest.fixture
def committed() -> Iterator[str]:
    """A unique trial run id; afterwards every row the test committed is deleted."""
    run = f"{TEST_RUN_PREFIX}{uuid.uuid4().hex}"
    try:
        yield run
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM llm_call_log WHERE trial_run_id LIKE :p"),
                {"p": f"{TEST_RUN_PREFIX}%"},
            )
            connection.execute(
                text("DELETE FROM llm_trial_usage WHERE trial_run_id LIKE :p"),
                {"p": f"{TEST_RUN_PREFIX}%"},
            )
            connection.execute(text("DELETE FROM llm_daily_usage WHERE usage_date < '2002-01-01'"))


def _wait_until_blocked(timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    with engine.connect() as connection:
        while time.monotonic() < deadline:
            waiting = connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                    " AND wait_event_type = 'Lock'"
                )
            ).scalar_one()
            if waiting:
                return
            connection.rollback()
            time.sleep(0.02)
    raise AssertionError("the second reservation never waited for the first")


def _race(first: Callable[[Session], bool], second: Callable[[Session], bool]) -> list[bool]:
    """`first` reserves and holds its transaction; `second` runs meanwhile in a thread."""
    results: list[bool] = []
    errors: list[BaseException] = []

    def other() -> None:
        try:
            with SessionLocal() as session:
                results.append(second(session))
                session.commit()
        except BaseException as error:
            errors.append(error)

    with SessionLocal() as holder:
        results.append(first(holder))
        thread = threading.Thread(target=other)
        thread.start()
        _wait_until_blocked()
        holder.commit()
    thread.join(10)
    assert not thread.is_alive() and not errors
    return results


@pytest.mark.parametrize("already_used", [0, 1])
def test_two_workers_cannot_pass_the_daily_cap(committed, cap, already_used) -> None:
    """One unit left (a fresh day, or a day with one used): exactly one worker gets it."""
    cap(already_used + 1)
    if already_used:
        with SessionLocal() as session:
            assert gateway._reserve_demo(session, at=OLD_DAY_AT)
            session.commit()

    def reserve(session: Session) -> bool:
        return gateway._reserve_demo(session, at=OLD_DAY_AT)

    assert sorted(_race(reserve, reserve)) == [False, True]
    engine.dispose()  # a restart keeps the count: it lives in the database
    with SessionLocal() as session:
        assert gateway.demo_used(session, at=OLD_DAY_AT) == already_used + 1


def test_two_workers_cannot_pass_the_trial_cap(committed) -> None:
    with SessionLocal() as session:
        gateway.create_trial_run(session, committed, cap=1)
        session.commit()

    def reserve(session: Session) -> bool:
        return gateway._reserve_trial(session, committed)

    assert sorted(_race(reserve, reserve)) == [False, True]


def test_the_trial_count_survives_midnight_and_new_sessions(committed, spy) -> None:
    clock.set_time(datetime(2026, 10, 20, 23, 58, tzinfo=clock.APP_TIMEZONE))
    try:
        with SessionLocal() as session:
            gateway.create_trial_run(session, committed, cap=3)
            session.commit()
            assert isinstance(gateway.call(session, _request(), _trial(committed, 1)), LlmAttempt)
            assert isinstance(gateway.call(session, _request(), _trial(committed, 2)), LlmAttempt)
        clock.advance(timedelta(minutes=5))  # the next day in Bangkok
        engine.dispose()
        with SessionLocal() as session:
            gateway.create_trial_run(session, committed, cap=180)  # cannot renew or raise
            session.commit()
            assert isinstance(gateway.call(session, _request(), _trial(committed, 3)), LlmAttempt)
            refused = gateway.call(session, _request(), _trial(committed, 4))
            usage = session.get(LlmTrialUsage, committed)
            assert refused == LlmRefusal.QUOTA_EXHAUSTED
            assert usage is not None and (usage.cap, usage.used) == (3, 3)
    finally:
        clock.reset()
    assert len(spy.requests) == 3


def test_no_lock_is_held_while_the_provider_answers(
    committed, cap, monkeypatch: pytest.MonkeyPatch
) -> None:
    """During the call, another connection sees the committed IN_FLIGHT row and its quota,
    and can reserve quota at once (lock_timeout would fail it otherwise)."""
    cap(10)
    seen: list[tuple[str, int]] = []

    def provider(request: LlmRequest) -> LlmAttempt:
        with engine.connect() as other:
            other.execute(text("SET lock_timeout = '500ms'"))
            status = other.execute(
                text("SELECT status FROM llm_call_log WHERE trial_run_id = :run"),
                {"run": committed},
            ).scalar_one()
            used = other.execute(
                text("SELECT used FROM llm_trial_usage WHERE trial_run_id = :run"),
                {"run": committed},
            ).scalar_one()
            seen.append((status, used))
            with Session(bind=other) as session:
                assert gateway._reserve_demo(session, at=OLD_DAY_AT)
                session.execute(
                    text("UPDATE llm_trial_usage SET used = used WHERE trial_run_id = :run"),
                    {"run": committed},
                )
                session.commit()
        return fake.generate(request)

    monkeypatch.setattr(llm_service, "generate_explanation", provider)
    with SessionLocal() as session:
        gateway.create_trial_run(session, committed, cap=5)
        session.commit()
        result = gateway.call(session, _request(), _trial(committed))

    assert isinstance(result, LlmAttempt) and seen == [("IN_FLIGHT", 1)]
    with SessionLocal() as session:
        (log,) = session.scalars(select(LlmCallLog).where(LlmCallLog.trial_run_id == committed))
        assert log.status == LlmCallStatus.SUCCEEDED
