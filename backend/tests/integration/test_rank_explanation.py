"""LLM ranking explanation (round 3 PR X): a user asks (round 6 PR E1), the Job sweep
generates. The request side has its own tests in test_explanation_request.py.

Everything is offline: the gateway or the adapter functions are replaced, and the fake
adapter is the only one that really runs.
"""

import hashlib
import json
import logging
import threading
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core import clock
from app.core.config import settings
from app.db.models import (
    AuditLog,
    LlmCallLog,
    LlmDailyUsage,
    RankExplanation,
    Staff,
    StaffingCase,
)
from app.db.session import SessionLocal
from app.domain.enums import (
    AuditAction,
    CaseStatus,
    ExplanationStatus,
    LlmCallStatus,
    LlmWorkType,
)
from app.integrations.llm import LlmAttempt, LlmRequest, bedrock, fake
from app.main import app
from app.seed import load
from app.services import explanation_service as service
from app.services import llm_service
from app.workflow.handlers import optimize
from tests.integration.case_rows import leave, make_case, record_gap

SECRET_MESSAGE = "SECRET-SDK-MESSAGE-do-not-leak"


def _failure(status: LlmCallStatus) -> LlmAttempt:
    return LlmAttempt(
        status=status,
        text=None,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        duration_ms=None,
        error_type="Boom",
        provider="fake",
        model_id=None,
        region=None,
        input_rate=None,
        output_rate=None,
    )


class Gateway:
    """Replaces generate_explanation: plays a script of statuses, then succeeds."""

    def __init__(self, *statuses: LlmCallStatus) -> None:
        self.script = list(statuses)
        self.requests: list[LlmRequest] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    def __call__(self, request: LlmRequest) -> LlmAttempt:
        self.requests.append(request)
        status = self.script.pop(0) if self.script else LlmCallStatus.SUCCEEDED
        if status == LlmCallStatus.SUCCEEDED:
            return fake.generate(request)
        return _failure(status)


@pytest.fixture
def llm_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "fake")
    monkeypatch.setattr(settings, "llm_max_retries", 1)


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Gateway]:
    def install(*statuses: LlmCallStatus) -> Gateway:
        spy = Gateway(*statuses)
        monkeypatch.setattr(llm_service, "generate_explanation", spy)
        return spy

    return install


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _planned_case(db: Session) -> StaffingCase:
    leave(db, 105)
    case = make_case(db, CaseStatus.OPTIMIZING)
    record_gap(db, case)
    optimize.handle(db, case)
    return case


def _requested_case(db: Session) -> StaffingCase:
    """A planned case whose explanation a user asked for: one requested PENDING row."""
    case = _planned_case(db)
    service.request(db, case.id)
    return case


def _rows(db: Session) -> list[RankExplanation]:
    db.expire_all()
    return list(db.scalars(select(RankExplanation).order_by(RankExplanation.id)))


def _logs(db: Session) -> list[LlmCallLog]:
    db.expire_all()
    return list(db.scalars(select(LlmCallLog).order_by(LlmCallLog.attempt)))


def _explanation(client: TestClient, case: StaffingCase) -> dict[str, Any] | None:
    response = client.get(f"/cases/{case.id}")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    explanation: dict[str, Any] | None = body["explanation"]
    return explanation


# 1
def test_disabled_writes_no_row_and_never_calls(seeded: Session, gateway) -> None:
    spy = gateway()
    assert settings.llm_enabled is False

    _planned_case(seeded)

    assert _rows(seeded) == []
    assert service.run_pending(seeded) == 0
    assert spy.calls == 0


# 2 (round 6 PR E1)
def test_a_new_plan_gets_no_row_and_no_call_until_a_user_asks(
    seeded: Session, llm_on, gateway
) -> None:
    spy = gateway()

    case = _planned_case(seeded)
    seeded.commit()  # an idle sweep rolls the session back

    assert _rows(seeded) == []
    assert service.run_pending(seeded) == 0
    assert spy.calls == 0

    service.request(seeded, case.id)

    (row,) = _rows(seeded)
    assert (row.status, row.prompt_version) == (ExplanationStatus.PENDING, service.PROMPT_VERSION)
    assert row.case_id == case.id and row.input_payload is None and row.attempts == 0
    assert spy.calls == 0


# 3
def test_sweep_makes_the_sentence_and_logs_the_call(seeded: Session, llm_on) -> None:
    _requested_case(seeded)

    assert service.run_pending(seeded) == 1

    (row,) = _rows(seeded)
    assert row.status == ExplanationStatus.READY
    assert row.text and row.text.startswith("[fake] ")
    assert row.provider == "fake" and row.ready_at is not None and row.claim is None
    assert row.input_payload is not None
    canonical = json.dumps(
        row.input_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    assert row.input_hash == hashlib.sha256(canonical.encode()).hexdigest()
    (log,) = _logs(seeded)
    assert log.status == LlmCallStatus.SUCCEEDED and log.attempt == 1
    assert log.input_tokens and log.output_tokens and log.total_tokens
    assert log.estimated_cost_usd == 0 and log.finished_at is not None
    assert log.input_hash == row.input_hash


# 4
def test_payload_has_no_personal_data(seeded: Session, llm_on) -> None:
    _requested_case(seeded)
    service.run_pending(seeded)
    (row,) = _rows(seeded)
    assert row.input_payload is not None

    def keys(value: Any) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {k for v in value.values() for k in keys(v)}
        if isinstance(value, list):
            return {k for v in value for k in keys(v)}
        return set()

    forbidden = {"staff_id", "first_name", "last_name", "name_th", "email", "source", "line_uid"}
    assert not (keys(row.input_payload) & forbidden)
    blob = json.dumps(row.input_payload, ensure_ascii=False)
    for staff in seeded.scalars(select(Staff)):
        assert staff.first_name not in blob and staff.last_name not in blob
    # The only mention is the tie-break NAME in ranking_key.order, never a key or an ID
    assert blob.count("staff_id") == 1
    assert row.input_payload["ranking_key"]["order"][-1] == "staff_id"
    assert row.input_payload["candidates"][0]["ranking_key"].keys() == {
        "candidate_source",
        "hours_this_week",
        "projected_consecutive_shifts",
        "overtime_hours",
    }
    assert row.text is not None
    for staff in seeded.scalars(select(Staff)):
        assert staff.first_name not in row.text


# 5
def test_payload_separates_plan_penalty_from_ranking_key(
    seeded: Session, llm_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _planned_case(seeded)
    plan = seeded.scalars(
        select(service.CandidatePlan).where(service.CandidatePlan.case_id == case.id)
    ).one()

    payload = service.build_payload(plan)

    assert set(payload) == {
        "targets",
        "plan_penalty",
        "ranking_key",
        "candidate_count",
        "candidates",
    }
    assert payload["plan_penalty"]["value"] == float(plan.objective_score) or (
        payload["plan_penalty"]["value"] == plan.objective_score
    )
    assert payload["ranking_key"]["order"][0] == "candidate_source"
    assert payload["candidate_count"] == len(plan.input_snapshot["candidates"]) == 3
    entries = plan.input_snapshot["candidates"]
    assert [c["rank"] for c in payload["candidates"]] == [1, 2, 3]
    assert [c["first_wave"] for c in payload["candidates"]] == [e["first_wave"] for e in entries]
    # the snapshot order is the CandidateItem.rank order (checked against the items)
    from app.db.models import CandidateItem

    items = seeded.scalars(
        select(CandidateItem).where(CandidateItem.plan_id == plan.id).order_by(CandidateItem.rank)
    ).all()
    assert [i.staff_id for i in items] == [e["staff_id"] for e in entries]

    # cap at 10, full count kept
    padded = [dict(entries[0]) for _ in range(12)]
    monkeypatch.setitem(plan.input_snapshot, "candidates", padded)
    capped = service.build_payload(plan)
    assert len(capped["candidates"]) == service.MAX_EXPLAINED_CANDIDATES == 10
    assert capped["candidate_count"] == 12
    assert [c["rank"] for c in capped["candidates"]] == list(range(1, 11))


# 5b (round 4 PR T4)
def test_a_partial_plan_says_coverage_comes_first_without_new_keys(seeded: Session, llm_on) -> None:
    case = _planned_case(seeded)
    plan = seeded.scalars(
        select(service.CandidatePlan).where(service.CandidatePlan.case_id == case.id)
    ).one()
    normal = service.build_payload(plan)

    plan.input_snapshot = {**plan.input_snapshot, "partial_plan": True}
    partial = service.build_payload(plan)

    assert set(partial) == set(normal)
    assert normal["plan_penalty"]["meaning"] == "selects which group becomes the first wave"
    assert partial["plan_penalty"]["meaning"] == (
        "breaks ties only: no group could cover every target, so the first wave is the group "
        "that leaves the fewest uncovered person-minutes (headcount first, then role, then "
        "skill); points choose only among groups that cover the same"
    )
    assert {**partial, "plan_penalty": normal["plan_penalty"]} == normal
    plan.input_snapshot = {**plan.input_snapshot, "partial_plan": False}
    assert service.build_payload(plan) == normal


def test_the_prompt_version_is_v2_and_the_prompt_defers_to_the_meaning(
    seeded: Session, llm_on
) -> None:
    _requested_case(seeded)

    (row,) = _rows(seeded)

    assert service.PROMPT_VERSION == "rank-explanation-v2"
    assert row.prompt_version == "rank-explanation-v2"
    assert "plan_penalty.meaning says what chose the first wave." in service.SYSTEM_PROMPT
    assert "selects which group of candidates" not in service.SYSTEM_PROMPT


# 6
def test_polling_never_calls_the_llm(client: TestClient, seeded: Session, llm_on, gateway) -> None:
    case = _requested_case(seeded)
    spy = gateway()

    for _ in range(5):
        assert _explanation(client, case) == {
            "status": "PENDING",
            "text": None,
            "provider": None,
            "model_id": None,
            "can_request": False,
            "request_blocked_reason": "PENDING",
        }

    assert spy.calls == 0


# 7
def test_a_second_sweep_after_ready_makes_no_call(seeded: Session, llm_on, gateway) -> None:
    _requested_case(seeded)
    spy = gateway()

    assert service.run_pending(seeded) == 1
    assert service.run_pending(seeded) == 0

    assert spy.calls == 1
    assert len(_logs(seeded)) == 1


# 8
def test_a_timeout_is_retried_once_then_gives_up(seeded: Session, llm_on, gateway) -> None:
    _requested_case(seeded)
    spy = gateway(LlmCallStatus.TIMEOUT)
    service.run_pending(seeded)
    assert spy.calls == 2
    assert [(log.attempt, log.status) for log in _logs(seeded)] == [
        (1, LlmCallStatus.TIMEOUT),
        (2, LlmCallStatus.SUCCEEDED),
    ]
    assert _rows(seeded)[0].status == ExplanationStatus.READY


def test_two_timeouts_end_failed_without_a_third_call(seeded: Session, llm_on, gateway) -> None:
    _requested_case(seeded)
    spy = gateway(LlmCallStatus.TIMEOUT, LlmCallStatus.THROTTLED)

    service.run_pending(seeded)
    service.run_pending(seeded)

    assert spy.calls == 2
    (row,) = _rows(seeded)
    assert row.status == ExplanationStatus.FAILED and row.attempts == 2
    assert row.failure_reason == "THROTTLED"
    assert len(_logs(seeded)) == 2


# 9
@pytest.mark.parametrize(
    "status",
    [LlmCallStatus.CONFIG_ERROR, LlmCallStatus.TRUNCATED, LlmCallStatus.INVALID_OUTPUT],
)
def test_permanent_errors_are_not_retried(seeded: Session, llm_on, gateway, status) -> None:
    _requested_case(seeded)
    spy = gateway(status)

    service.run_pending(seeded)

    assert spy.calls == 1
    (log,) = _logs(seeded)
    assert log.status == status
    (row,) = _rows(seeded)
    assert row.status == ExplanationStatus.FAILED and row.failure_reason == status.value
    assert row.text is None


# 10
def test_llm_failure_does_not_touch_the_case(seeded: Session, llm_on, gateway) -> None:
    case = _requested_case(seeded)
    before = case.status
    gateway(LlmCallStatus.CONFIG_ERROR)

    service.run_pending(seeded)

    assert _rows(seeded)[0].status == ExplanationStatus.FAILED
    seeded.refresh(case)
    assert case.status == before
    failed = seeded.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.case_id == case.id, AuditLog.action == AuditAction.WORKFLOW_FAILED)
    )
    assert failed == 0


# 11
def test_bedrock_failure_never_falls_back_to_fake(
    client: TestClient, seeded: Session, llm_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(settings, "llm_model_id", "some-model")
    monkeypatch.setattr(settings, "aws_region", "us-east-1")
    fake_calls: list[LlmRequest] = []
    bedrock_calls: list[LlmRequest] = []

    def failing(request: LlmRequest) -> LlmAttempt:
        bedrock_calls.append(request)
        return _failure(LlmCallStatus.CONFIG_ERROR)

    def forbidden(request: LlmRequest) -> LlmAttempt:
        fake_calls.append(request)
        return fake.generate(request)

    monkeypatch.setattr(bedrock, "generate", failing)
    monkeypatch.setattr(fake, "generate", forbidden)
    case = _requested_case(seeded)

    service.run_pending(seeded)

    assert len(bedrock_calls) == 1 and fake_calls == []
    assert _explanation(client, case) == {
        "status": "UNAVAILABLE",
        "text": None,
        "provider": None,
        "model_id": None,
        # A configuration error can be repaired outside the row: the user may ask again
        "can_request": True,
        "request_blocked_reason": None,
    }


# 12
def test_a_crash_cannot_exceed_the_attempts_of_the_request(
    seeded: Session, llm_on, gateway
) -> None:
    _requested_case(seeded)
    spy = gateway()
    (row,) = _rows(seeded)
    row.attempts = 2
    row.claim = service.uuid.uuid4()
    row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    seeded.add(
        LlmCallLog(
            work_type=LlmWorkType.RANK_EXPLANATION,
            explanation_id=row.id,
            case_id=row.case_id,
            plan_id=row.plan_id,
            provider="fake",
            prompt_version=row.prompt_version,
            attempt=2,
            status=LlmCallStatus.IN_FLIGHT,
            started_at=clock.now(),
        )
    )
    seeded.flush()

    service.run_pending(seeded)

    assert spy.calls == 0
    (row,) = _rows(seeded)
    assert row.status == ExplanationStatus.FAILED
    assert row.failure_reason == "ATTEMPTS_EXHAUSTED" and row.claim is None
    # Leftover IN_FLIGHT rows are kept: they mean "usage unknown"
    assert [log.status for log in _logs(seeded)] == [LlmCallStatus.IN_FLIGHT]


def test_a_live_lease_blocks_the_sweep(seeded: Session, llm_on, gateway) -> None:
    _requested_case(seeded)
    spy = gateway()
    (row,) = _rows(seeded)
    row.claim = service.uuid.uuid4()
    row.lease_until = datetime.now(UTC) + timedelta(seconds=30)
    seeded.flush()

    assert service.run_pending(seeded) == 0
    assert spy.calls == 0


# 13
def test_a_plan_without_weights_is_skipped_without_a_call(seeded: Session, llm_on, gateway) -> None:
    case = _requested_case(seeded)
    spy = gateway()
    plan = seeded.scalars(
        select(service.CandidatePlan).where(service.CandidatePlan.case_id == case.id)
    ).one()
    snapshot = dict(plan.input_snapshot)
    del snapshot["weights"]
    plan.input_snapshot = snapshot
    seeded.flush()

    service.run_pending(seeded)

    assert spy.calls == 0
    (row,) = _rows(seeded)
    assert row.status == ExplanationStatus.SKIPPED and row.failure_reason == "INVALID_INPUT"
    assert _logs(seeded) == []


def test_a_score_mismatch_is_skipped_without_a_call(seeded: Session, llm_on, gateway) -> None:
    case = _requested_case(seeded)
    spy = gateway()
    plan = seeded.scalars(
        select(service.CandidatePlan).where(service.CandidatePlan.case_id == case.id)
    ).one()
    snapshot = json.loads(json.dumps(plan.input_snapshot))
    snapshot["candidates"][0]["penalty_exact"] = "1/1"
    plan.input_snapshot = snapshot
    seeded.flush()

    service.run_pending(seeded)

    assert spy.calls == 0
    assert _rows(seeded)[0].status == ExplanationStatus.SKIPPED


# 14
def test_misconfigured_bedrock_makes_no_call_and_logs_no_values(
    seeded: Session, llm_on, gateway, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    spy = gateway()
    _requested_case(seeded)
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(settings, "llm_model_id", None)
    monkeypatch.setattr(settings, "aws_region", "region-value-xyz")

    with caplog.at_level(logging.ERROR):
        assert service.run_pending(seeded) == 0

    assert spy.calls == 0
    assert _rows(seeded)[0].status == ExplanationStatus.PENDING
    assert "misconfigured" in caplog.text and "region-value-xyz" not in caplog.text


# 15
def test_two_concurrent_sweeps_make_one_call(
    frozen_clock, restore_empty_database, llm_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, release = threading.Event(), threading.Event()
    calls: list[LlmRequest] = []
    errors: list[BaseException] = []

    def slow(request: LlmRequest) -> LlmAttempt:
        calls.append(request)
        started.set()
        assert release.wait(5)
        return fake.generate(request)

    monkeypatch.setattr(llm_service, "generate_explanation", slow)
    with SessionLocal() as db:
        load(db)
        _requested_case(db)
        db.commit()

    def sweep() -> None:
        try:
            with SessionLocal() as other:
                service.run_pending(other)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=sweep)
    thread.start()
    try:
        assert started.wait(5)
        # The first sweep is inside the call: no lock is held, but the row is leased
        with SessionLocal() as db:
            assert service.run_pending(db) == 0
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and not errors
    assert len(calls) == 1
    with SessionLocal() as db:
        (row,) = _rows(db)
        assert row.status == ExplanationStatus.READY and row.attempts == 1
        assert len(_logs(db)) == 1


def test_the_lease_follows_real_time_not_the_demo_clock(
    frozen_clock, restore_empty_database, llm_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Advancing the Demo Clock past the lease mid-call must not allow a second call."""
    started, release = threading.Event(), threading.Event()
    calls: list[LlmRequest] = []
    errors: list[BaseException] = []

    def slow(request: LlmRequest) -> LlmAttempt:
        calls.append(request)
        started.set()
        assert release.wait(5)
        return fake.generate(request)

    monkeypatch.setattr(llm_service, "generate_explanation", slow)
    with SessionLocal() as db:
        load(db)
        _requested_case(db)
        db.commit()

    def sweep() -> None:
        try:
            with SessionLocal() as other:
                service.run_pending(other)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=sweep)
    thread.start()
    try:
        assert started.wait(5)
        clock.advance(service.lease_duration() * 3)
        with SessionLocal() as db:
            assert service.run_pending(db) == 0
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and not errors
    assert len(calls) == 1
    with SessionLocal() as db:
        (row,) = _rows(db)
        assert row.status == ExplanationStatus.READY and row.attempts == 1
        assert [log.status for log in _logs(db)] == [LlmCallStatus.SUCCEEDED]


# 16
def test_logs_hold_no_message_prompt_or_text(
    seeded: Session, llm_on, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(settings, "llm_model_id", "some-model")
    monkeypatch.setattr(settings, "aws_region", "us-east-1")

    def broken_client() -> Any:
        raise RuntimeError(SECRET_MESSAGE)

    monkeypatch.setattr(bedrock, "_client", broken_client)
    _requested_case(seeded)

    with caplog.at_level(logging.DEBUG):
        service.run_pending(seeded)
        service.run_pending(seeded)

    (row,) = _rows(seeded)
    assert row.status == ExplanationStatus.FAILED
    assert SECRET_MESSAGE not in caplog.text
    assert "Explain this ranking" not in caplog.text and "candidates" not in caplog.text
    for log in _logs(seeded):
        assert SECRET_MESSAGE not in (log.error_type or "")


def test_a_raising_gateway_is_logged_by_type_only(
    seeded: Session, llm_on, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    def boom(request: LlmRequest) -> LlmAttempt:
        raise RuntimeError(SECRET_MESSAGE)

    monkeypatch.setattr(llm_service, "generate_explanation", boom)
    _requested_case(seeded)

    with caplog.at_level(logging.DEBUG):
        service.run_pending(seeded)

    assert SECRET_MESSAGE not in caplog.text and "RuntimeError" in caplog.text
    assert [log.error_type for log in _logs(seeded)] == ["RuntimeError", "RuntimeError"]
    assert _rows(seeded)[0].status == ExplanationStatus.FAILED


# 17
def test_the_internal_route_queues_the_sweep_after_the_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[bool] = []
    monkeypatch.setattr(settings, "internal_job_secret", "test-only-job-secret")
    monkeypatch.setattr(service, "run_pending_in_new_session", lambda: ran.append(True))

    response = client.post(
        "/internal/merge-windows/close-due", headers={"X-Internal-Secret": "test-only-job-secret"}
    )

    assert response.status_code == 200
    assert ran == [True]


def test_a_rejected_tick_queues_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[bool] = []
    monkeypatch.setattr(settings, "internal_job_secret", "test-only-job-secret")
    monkeypatch.setattr(service, "run_pending_in_new_session", lambda: ran.append(True))

    response = client.post("/internal/merge-windows/close-due", headers={"X-Internal-Secret": "x"})

    assert response.status_code == 401 and ran == []


def test_demo_clock_advance_does_not_call_the_gateway(
    client: TestClient, seeded: Session, llm_on, gateway
) -> None:
    _requested_case(seeded)
    spy = gateway()

    response = client.post("/demo/clock/advance", json={"seconds": 60})

    assert response.status_code == 200
    assert spy.calls == 0
    assert _rows(seeded)[0].status == ExplanationStatus.PENDING


# --------------------------------------------------------------------------- #
# Round 6 PR B1: every attempt of the sweep goes through llm_gateway
# --------------------------------------------------------------------------- #
def _daily_used(db: Session) -> int:
    db.expire_all()
    return sum(db.scalars(select(LlmDailyUsage.used)))


def test_the_sweep_reaches_the_provider_only_through_the_gateway(
    seeded: Session, llm_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stand-in provider fails unless its attempt was counted and logged first."""
    calls: list[int] = []

    def provider(request: LlmRequest) -> LlmAttempt:
        calls.append(1)
        in_flight = seeded.scalars(
            select(LlmCallLog).where(LlmCallLog.status == LlmCallStatus.IN_FLIGHT)
        ).all()
        if len(in_flight) != 1 or in_flight[0].attempt != len(calls):
            pytest.fail("provider called without an IN_FLIGHT log row")
        if _daily_used(seeded) != len(calls):
            pytest.fail("provider called without a reserved quota unit")
        return _failure(LlmCallStatus.TIMEOUT) if len(calls) == 1 else fake.generate(request)

    monkeypatch.setattr(llm_service, "generate_explanation", provider)
    _requested_case(seeded)

    service.run_pending(seeded)

    assert len(calls) == 2
    assert _rows(seeded)[0].status == ExplanationStatus.READY
    assert _daily_used(seeded) == 2
    assert [log.work_type for log in _logs(seeded)] == [LlmWorkType.RANK_EXPLANATION] * 2


def test_a_used_up_day_skips_the_row_without_a_call(
    seeded: Session, llm_on, gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = gateway()
    _requested_case(seeded)
    monkeypatch.setattr(settings, "llm_daily_call_cap", 0)

    service.run_pending(seeded)

    assert spy.calls == 0 and _logs(seeded) == [] and _daily_used(seeded) == 0
    (row,) = _rows(seeded)
    assert row.status == ExplanationStatus.SKIPPED
    assert row.failure_reason == "QUOTA_EXHAUSTED" and row.attempts == 0 and row.claim is None


def test_the_cap_also_stops_a_retry(
    seeded: Session, llm_on, gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_daily_call_cap", 1)
    spy = gateway(LlmCallStatus.TIMEOUT)
    _requested_case(seeded)

    service.run_pending(seeded)

    assert spy.calls == 1 and _daily_used(seeded) == 1
    (row,) = _rows(seeded)
    assert (row.status, row.failure_reason, row.attempts) == (
        ExplanationStatus.SKIPPED,
        "QUOTA_EXHAUSTED",
        1,
    )
    assert [log.status for log in _logs(seeded)] == [LlmCallStatus.TIMEOUT]


def test_a_payload_over_the_input_cap_is_skipped_without_a_call(
    seeded: Session, llm_on, gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = gateway()
    _requested_case(seeded)
    monkeypatch.setattr(settings, "llm_max_input_tokens", 10)

    service.run_pending(seeded)

    assert spy.calls == 0 and _logs(seeded) == [] and _daily_used(seeded) == 0
    (row,) = _rows(seeded)
    assert (row.status, row.failure_reason) == (ExplanationStatus.SKIPPED, "INPUT_TOO_LARGE")


def test_a_sentence_with_a_number_not_in_the_payload_is_not_shown(
    client: TestClient, seeded: Session, llm_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = fake.generate

    def invented(request: LlmRequest) -> LlmAttempt:
        return replace(real(request), text="อันดับ 1 รวมได้ 12345 คะแนน")

    monkeypatch.setattr(fake, "generate", invented)
    case = _requested_case(seeded)

    service.run_pending(seeded)

    (row,) = _rows(seeded)
    assert (row.status, row.failure_reason, row.text) == (
        ExplanationStatus.FAILED,
        "INVALID_OUTPUT",
        None,
    )
    (log,) = _logs(seeded)
    assert log.error_type == llm_service.UNVERIFIED_NUMBER
    assert _explanation(client, case)["text"] is None


def test_the_row_lifetime_bound_caps_the_attempts(
    seeded: Session, llm_on, gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_max_attempts_per_row", 1)
    spy = gateway(LlmCallStatus.TIMEOUT)
    _requested_case(seeded)

    service.run_pending(seeded)

    assert spy.calls == 1
    (row,) = _rows(seeded)
    assert row.status == ExplanationStatus.FAILED and row.attempts == 1
