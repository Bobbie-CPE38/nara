"""LLM ranking explanation (round 3 PR X): enqueue in the plan, generate in the Job sweep.

Everything is offline: the gateway or the adapter functions are replaced, and the fake
adapter is the only one that really runs.
"""

import hashlib
import json
import logging
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core import clock
from app.core.config import settings
from app.db.models import AuditLog, LlmCallLog, RankExplanation, Staff, StaffingCase
from app.db.session import SessionLocal
from app.domain.enums import AuditAction, CaseStatus, ExplanationStatus, LlmCallStatus
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


# 2
def test_enabled_enqueues_one_pending_row_in_the_plan_transaction(
    seeded: Session, llm_on, gateway
) -> None:
    spy = gateway()
    leave(seeded, 105)
    case = make_case(seeded, CaseStatus.OPTIMIZING)
    record_gap(seeded, case)

    savepoint = seeded.begin_nested()
    optimize.handle(seeded, case)
    rows = _rows(seeded)
    assert [(r.status, r.prompt_version) for r in rows] == [
        (ExplanationStatus.PENDING, service.PROMPT_VERSION)
    ]
    assert rows[0].case_id == case.id and rows[0].input_payload is None
    savepoint.rollback()

    assert _rows(seeded) == []
    assert spy.calls == 0


# 3
def test_sweep_makes_the_sentence_and_logs_the_call(seeded: Session, llm_on) -> None:
    _planned_case(seeded)

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
    _planned_case(seeded)
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


# 6
def test_polling_never_calls_the_llm(client: TestClient, seeded: Session, llm_on, gateway) -> None:
    case = _planned_case(seeded)
    spy = gateway()

    for _ in range(5):
        assert _explanation(client, case) == {
            "status": "PENDING",
            "text": None,
            "provider": None,
            "model_id": None,
        }

    assert spy.calls == 0


# 7
def test_a_second_sweep_after_ready_makes_no_call(seeded: Session, llm_on, gateway) -> None:
    _planned_case(seeded)
    spy = gateway()

    assert service.run_pending(seeded) == 1
    assert service.run_pending(seeded) == 0

    assert spy.calls == 1
    assert len(_logs(seeded)) == 1


# 8
def test_a_timeout_is_retried_once_then_gives_up(seeded: Session, llm_on, gateway) -> None:
    _planned_case(seeded)
    spy = gateway(LlmCallStatus.TIMEOUT)
    service.run_pending(seeded)
    assert spy.calls == 2
    assert [(log.attempt, log.status) for log in _logs(seeded)] == [
        (1, LlmCallStatus.TIMEOUT),
        (2, LlmCallStatus.SUCCEEDED),
    ]
    assert _rows(seeded)[0].status == ExplanationStatus.READY


def test_two_timeouts_end_failed_without_a_third_call(seeded: Session, llm_on, gateway) -> None:
    _planned_case(seeded)
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
    _planned_case(seeded)
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
    case = _planned_case(seeded)
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
    case = _planned_case(seeded)

    service.run_pending(seeded)

    assert len(bedrock_calls) == 1 and fake_calls == []
    assert _explanation(client, case) == {
        "status": "UNAVAILABLE",
        "text": None,
        "provider": None,
        "model_id": None,
    }


# 12
def test_a_crash_cannot_exceed_the_attempt_bound(seeded: Session, llm_on, gateway) -> None:
    _planned_case(seeded)
    spy = gateway()
    (row,) = _rows(seeded)
    row.attempts = 2
    row.claim = service.uuid.uuid4()
    row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    seeded.add(
        LlmCallLog(
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
    _planned_case(seeded)
    spy = gateway()
    (row,) = _rows(seeded)
    row.claim = service.uuid.uuid4()
    row.lease_until = datetime.now(UTC) + timedelta(seconds=30)
    seeded.flush()

    assert service.run_pending(seeded) == 0
    assert spy.calls == 0


# 13
def test_a_plan_without_weights_is_skipped_without_a_call(seeded: Session, llm_on, gateway) -> None:
    case = _planned_case(seeded)
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
    case = _planned_case(seeded)
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
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(settings, "llm_model_id", None)
    monkeypatch.setattr(settings, "aws_region", "region-value-xyz")
    spy = gateway()
    _planned_case(seeded)

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
        _planned_case(db)
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
        _planned_case(db)
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
    _planned_case(seeded)

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
    _planned_case(seeded)

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
    _planned_case(seeded)
    spy = gateway()

    response = client.post("/demo/clock/advance", json={"seconds": 60})

    assert response.status_code == 200
    assert spy.calls == 0
    assert _rows(seeded)[0].status == ExplanationStatus.PENDING
