"""POST /cases/{id}/explanation: the ranking explanation is made only when a user asks
(round 6 PR E1, docs/workflow.md 6.27 and 9.8).

The request never calls the LLM; the Job sweep does. A refused request changes no row,
adds no attempt and uses no quota. Everything is offline: the provider is replaced.
"""

import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import settings
from app.db.models import (
    CandidatePlan,
    LlmCallLog,
    LlmDailyUsage,
    RankExplanation,
    StaffingCase,
)
from app.db.session import SessionLocal
from app.domain.enums import CaseStatus, ExplanationStatus, LlmCallStatus
from app.integrations.llm import LlmAttempt, LlmRequest, fake
from app.main import app
from app.seed import load
from app.services import explanation_service as service
from app.services import llm_gateway, llm_service
from app.workflow.handlers import optimize
from tests.integration.case_rows import leave, make_case, record_gap


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


class Provider:
    """Replaces generate_explanation: plays a script of statuses, then succeeds."""

    def __init__(self, *statuses: LlmCallStatus) -> None:
        self.script = list(statuses)
        self.calls = 0

    def __call__(self, request: LlmRequest) -> LlmAttempt:
        self.calls += 1
        status = self.script.pop(0) if self.script else LlmCallStatus.SUCCEEDED
        return fake.generate(request) if status == LlmCallStatus.SUCCEEDED else _failure(status)


@pytest.fixture
def llm_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "fake")
    monkeypatch.setattr(settings, "llm_max_retries", 1)
    monkeypatch.setattr(settings, "llm_max_attempts_per_row", 4)


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Provider]:
    def install(*statuses: LlmCallStatus) -> Provider:
        spy = Provider(*statuses)
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
    """Committed: a refused request rolls the session back, as it would in a route."""
    leave(db, 105)
    case = make_case(db, CaseStatus.OPTIMIZING)
    record_gap(db, case)
    optimize.handle(db, case)
    db.commit()
    return case


def _another_case(db: Session) -> StaffingCase:
    """A second case of the same short shift, with its own plan."""
    case = make_case(db, CaseStatus.OPTIMIZING)
    record_gap(db, case)
    optimize.handle(db, case)
    db.commit()
    return case


def _rows(db: Session) -> list[RankExplanation]:
    db.expire_all()
    return list(db.scalars(select(RankExplanation).order_by(RankExplanation.id)))


def _logs(db: Session) -> list[LlmCallLog]:
    db.expire_all()
    return list(db.scalars(select(LlmCallLog).order_by(LlmCallLog.id)))


def _used(db: Session) -> int:
    db.expire_all()
    return sum(db.scalars(select(LlmDailyUsage.used)))


def _ask(client: TestClient, case: StaffingCase) -> Any:
    return client.post(f"/cases/{case.id}/explanation")


def _get(client: TestClient, case: StaffingCase) -> dict[str, Any]:
    response = client.get(f"/cases/{case.id}")
    assert response.status_code == 200
    explanation: dict[str, Any] = response.json()["explanation"]
    return explanation


def _refused(response: Any, status_code: int, code: str) -> None:
    assert response.status_code == status_code, response.text
    assert response.json()["detail"]["code"] == code
    assert response.json()["detail"]["message"]


def _snapshot(db: Session) -> list[tuple[Any, ...]]:
    return [
        (r.id, r.status, r.failure_reason, r.attempts, r.attempt_limit, r.text) for r in _rows(db)
    ]


# --------------------------------------------------------------------------- #
# No call without a user
# --------------------------------------------------------------------------- #
def test_ranking_queues_nothing_and_the_sweep_calls_nothing(
    client: TestClient, seeded: Session, llm_on, provider
) -> None:
    spy = provider()
    case = _planned_case(seeded)

    assert _rows(seeded) == []
    assert service.run_pending(seeded) == 0
    assert spy.calls == 0 and _logs(seeded) == [] and _used(seeded) == 0
    assert _get(client, case)["status"] == "NOT_REQUESTED"


def test_asking_queues_one_row_and_never_calls_in_the_request(
    client: TestClient, seeded: Session, llm_on, provider
) -> None:
    spy = provider()
    case = _planned_case(seeded)

    response = _ask(client, case)

    assert response.status_code == 200
    assert response.json() == {
        "status": "PENDING",
        "text": None,
        "provider": None,
        "model_id": None,
        "can_request": False,
        "request_blocked_reason": "PENDING",
    }
    (row,) = _rows(seeded)
    assert (row.status, row.attempts, row.attempt_limit) == (ExplanationStatus.PENDING, 0, 2)
    assert row.prompt_version == service.PROMPT_VERSION
    assert spy.calls == 0 and _logs(seeded) == [] and _used(seeded) == 0

    assert service.run_pending(seeded) == 1

    assert spy.calls == 1
    answer = _get(client, case)
    assert answer["status"] == "READY" and answer["text"].startswith("[fake] ")
    assert (answer["can_request"], answer["request_blocked_reason"]) == (False, "ALREADY_READY")


def test_asking_again_while_pending_or_ready_changes_nothing(
    client: TestClient, seeded: Session, llm_on, provider
) -> None:
    spy = provider()
    case = _planned_case(seeded)
    assert _ask(client, case).status_code == 200
    pending = _snapshot(seeded)

    for _ in range(3):
        assert _ask(client, case).json()["status"] == "PENDING"
    assert _snapshot(seeded) == pending

    service.run_pending(seeded)
    ready = _snapshot(seeded)
    for _ in range(3):
        response = _ask(client, case)
        assert response.status_code == 200 and response.json()["status"] == "READY"
    assert service.run_pending(seeded) == 0

    assert _snapshot(seeded) == ready and spy.calls == 1 and _used(seeded) == 1


def test_a_ready_explanation_is_answered_even_with_the_llm_off(
    client: TestClient, seeded: Session, llm_on, provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider()
    case = _planned_case(seeded)
    _ask(client, case)
    service.run_pending(seeded)
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr(settings, "llm_daily_call_cap", 0)

    response = _ask(client, case)

    assert response.status_code == 200 and response.json()["status"] == "READY"


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #
def test_an_unknown_case_or_a_case_without_a_plan_is_not_found(
    client: TestClient, seeded: Session, llm_on
) -> None:
    _refused(client.post("/cases/999999/explanation"), 404, "CASE_NOT_FOUND")
    case = make_case(seeded, CaseStatus.OPTIMIZING)
    _refused(_ask(client, case), 404, "CASE_NOT_FOUND")
    assert _rows(seeded) == []


def test_llm_off_or_misconfigured_is_refused_without_a_row(
    client: TestClient, seeded: Session, provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = provider()
    case = _planned_case(seeded)

    _refused(_ask(client, case), 409, "LLM_UNAVAILABLE")

    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(settings, "llm_model_id", None)
    _refused(_ask(client, case), 409, "LLM_UNAVAILABLE")
    assert _get(client, case)["request_blocked_reason"] == "NOT_CONFIGURED"

    assert _rows(seeded) == [] and spy.calls == 0 and _used(seeded) == 0


def test_a_plan_that_cannot_be_explained_is_refused(
    client: TestClient, seeded: Session, llm_on
) -> None:
    case = _planned_case(seeded)
    plan = seeded.scalars(select(CandidatePlan).where(CandidatePlan.case_id == case.id)).one()
    snapshot = dict(plan.input_snapshot)
    del snapshot["weights"]
    plan.input_snapshot = snapshot
    seeded.commit()

    _refused(_ask(client, case), 409, "LLM_UNAVAILABLE")

    assert _get(client, case) == {
        "status": "NOT_REQUESTED",
        "text": None,
        "provider": None,
        "model_id": None,
        "can_request": False,
        "request_blocked_reason": "INVALID_INPUT",
    }
    assert _rows(seeded) == []


def test_a_payload_over_the_input_cap_is_refused(
    client: TestClient, seeded: Session, llm_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _planned_case(seeded)
    monkeypatch.setattr(settings, "llm_max_input_tokens", 10)

    _refused(_ask(client, case), 409, "LLM_UNAVAILABLE")
    assert _rows(seeded) == []


def test_a_plan_without_candidates_is_null_and_refused(
    client: TestClient, seeded: Session, llm_on
) -> None:
    case = _planned_case(seeded)
    first = seeded.scalars(select(CandidatePlan).where(CandidatePlan.case_id == case.id)).one()
    # Ranked again and nobody could take the shift: the latest plan has no candidates
    seeded.add(
        CandidatePlan(
            case_id=case.id,
            solver_status=first.solver_status,
            generated_at=first.generated_at,
            execution_time_ms=first.execution_time_ms,
            objective_score=first.objective_score,
            solver_version=first.solver_version,
            hard_constraint_policy_id=first.hard_constraint_policy_id,
            soft_constraint_policy_id=first.soft_constraint_policy_id,
            input_snapshot=first.input_snapshot,
        )
    )
    seeded.commit()

    assert _get(client, case) is None
    _refused(_ask(client, case), 409, "LLM_UNAVAILABLE")
    assert _rows(seeded) == []


def test_a_used_up_day_is_refused_without_a_row_or_quota(
    client: TestClient, seeded: Session, llm_on, provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = provider()
    monkeypatch.setattr(settings, "llm_daily_call_cap", 2)
    first = _planned_case(seeded)
    _ask(client, first)
    service.run_pending(seeded)
    # The second attempt of the day goes to a timeout retry of another plan
    llm_gateway._reserve_demo(seeded)
    seeded.commit()
    assert _used(seeded) == 2
    second = _another_case(seeded)

    _refused(_ask(client, second), 429, "LLM_QUOTA_EXHAUSTED")

    assert _get(client, second) == {
        "status": "NOT_REQUESTED",
        "text": None,
        "provider": None,
        "model_id": None,
        "can_request": False,
        "request_blocked_reason": "QUOTA_EXHAUSTED",
    }
    # The explained plan stays readable
    assert _get(client, first)["status"] == "READY"
    assert len(_rows(seeded)) == 1 and _used(seeded) == 2 and spy.calls == 1


def test_one_unit_left_and_two_accepted_requests_make_one_call(
    client: TestClient, seeded: Session, llm_on, provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = provider()
    monkeypatch.setattr(settings, "llm_daily_call_cap", 1)
    first = _planned_case(seeded)
    second = _another_case(seeded)
    assert _ask(client, first).status_code == 200
    assert _ask(client, second).status_code == 200

    service.run_pending(seeded)

    assert spy.calls == 1 and _used(seeded) == 1
    statuses = sorted(_get(client, case)["status"] for case in (first, second))
    assert statuses == ["QUOTA_EXHAUSTED", "READY"]
    skipped = next(
        case for case in (first, second) if _get(client, case)["status"] == "QUOTA_EXHAUSTED"
    )
    # Not READY, no text, and the button stays off until the quota frees up
    assert _get(client, skipped)["text"] is None
    assert _get(client, skipped)["request_blocked_reason"] == "QUOTA_EXHAUSTED"
    _refused(_ask(client, skipped), 429, "LLM_QUOTA_EXHAUSTED")

    # A new day (here: a larger cap) opens it again; the row is reused
    monkeypatch.setattr(settings, "llm_daily_call_cap", 2)
    assert _get(client, skipped)["can_request"] is True
    assert _ask(client, skipped).json()["status"] == "PENDING"
    service.run_pending(seeded)
    assert _get(client, skipped)["status"] == "READY"
    assert len(_rows(seeded)) == 2 and spy.calls == 2


# --------------------------------------------------------------------------- #
# Asking again after a failure
# --------------------------------------------------------------------------- #
def test_asking_again_after_a_passing_fault_keeps_attempts_and_quota(
    client: TestClient, seeded: Session, llm_on, provider
) -> None:
    spy = provider(*[LlmCallStatus.TIMEOUT] * 4)
    case = _planned_case(seeded)
    _ask(client, case)
    service.run_pending(seeded)

    (row,) = _rows(seeded)
    assert (row.status, row.failure_reason, row.attempts) == (
        ExplanationStatus.FAILED,
        "TIMEOUT",
        2,
    )
    answer = _get(client, case)
    assert (answer["status"], answer["can_request"]) == ("UNAVAILABLE", True)
    assert answer["text"] is None

    assert _ask(client, case).json()["status"] == "PENDING"
    (row,) = _rows(seeded)
    assert (row.attempts, row.attempt_limit, row.failure_reason) == (2, 4, None)
    assert _used(seeded) == 2  # asking again refunds nothing

    service.run_pending(seeded)

    (row,) = _rows(seeded)
    assert (row.status, row.attempts) == (ExplanationStatus.FAILED, 4)
    assert spy.calls == 4 and _used(seeded) == 4
    assert [log.attempt for log in _logs(seeded)] == [1, 2, 3, 4]

    before = _snapshot(seeded)
    _refused(_ask(client, case), 409, "LLM_ATTEMPTS_EXHAUSTED")
    assert _snapshot(seeded) == before and _used(seeded) == 4
    answer = _get(client, case)
    assert (answer["can_request"], answer["request_blocked_reason"]) == (
        False,
        "ATTEMPTS_EXHAUSTED",
    )
    assert service.run_pending(seeded) == 0 and spy.calls == 4


def test_attempts_exhausted_is_reported_before_a_used_up_day(
    client: TestClient, seeded: Session, llm_on, provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider(LlmCallStatus.TIMEOUT, LlmCallStatus.TIMEOUT)
    monkeypatch.setattr(settings, "llm_max_attempts_per_row", 2)
    case = _planned_case(seeded)
    _ask(client, case)
    service.run_pending(seeded)
    monkeypatch.setattr(settings, "llm_daily_call_cap", 2)
    assert _used(seeded) == 2

    _refused(_ask(client, case), 409, "LLM_ATTEMPTS_EXHAUSTED")
    assert _get(client, case)["request_blocked_reason"] == "ATTEMPTS_EXHAUSTED"


@pytest.mark.parametrize("status", [LlmCallStatus.INVALID_OUTPUT, LlmCallStatus.TRUNCATED])
def test_a_failure_asking_again_cannot_fix_is_refused(
    client: TestClient, seeded: Session, llm_on, provider, status: LlmCallStatus
) -> None:
    spy = provider(status)
    case = _planned_case(seeded)
    _ask(client, case)
    service.run_pending(seeded)
    before = _snapshot(seeded)

    _refused(_ask(client, case), 409, "LLM_UNAVAILABLE")

    assert _snapshot(seeded) == before and spy.calls == 1 and _used(seeded) == 1
    answer = _get(client, case)
    assert (answer["status"], answer["text"], answer["request_blocked_reason"]) == (
        "UNAVAILABLE",
        None,
        "INVALID_INPUT",
    )


def test_a_repaired_configuration_error_can_be_asked_for_again(
    client: TestClient, seeded: Session, llm_on, provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review of PR #110: denied Bedrock access or missing credentials are fixed outside the
    row. The user may ask again; the sweep never retries it on its own, and attempts and
    quota are kept."""
    broken = provider(LlmCallStatus.CONFIG_ERROR)
    case = _planned_case(seeded)
    _ask(client, case)
    service.run_pending(seeded)
    (row,) = _rows(seeded)
    assert (row.status, row.failure_reason, row.attempts) == (
        ExplanationStatus.FAILED,
        "CONFIG_ERROR",
        1,
    )
    assert service.run_pending(seeded) == 0 and broken.calls == 1  # no retry on its own
    answer = _get(client, case)
    assert (answer["status"], answer["can_request"]) == ("UNAVAILABLE", True)

    # Switched off: still NOT_CONFIGURED, nothing changes
    monkeypatch.setattr(settings, "llm_enabled", False)
    before = _snapshot(seeded)
    _refused(_ask(client, case), 409, "LLM_UNAVAILABLE")
    assert _get(client, case)["request_blocked_reason"] == "NOT_CONFIGURED"
    assert _snapshot(seeded) == before
    monkeypatch.setattr(settings, "llm_enabled", True)

    repaired = provider()
    assert _ask(client, case).json()["status"] == "PENDING"
    (row,) = _rows(seeded)
    assert (row.attempts, row.attempt_limit) == (1, 3)
    assert _used(seeded) == 1

    service.run_pending(seeded)

    assert repaired.calls == 1 and _used(seeded) == 2
    assert _get(client, case)["status"] == "READY"
    assert [log.attempt for log in _logs(seeded)] == [1, 2]


def test_a_configuration_error_still_ends_at_the_row_lifetime_limit(
    client: TestClient, seeded: Session, llm_on, provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_max_attempts_per_row", 2)
    spy = provider(LlmCallStatus.CONFIG_ERROR, LlmCallStatus.CONFIG_ERROR)
    case = _planned_case(seeded)
    _ask(client, case)
    service.run_pending(seeded)
    _ask(client, case)
    service.run_pending(seeded)
    before = _snapshot(seeded)

    _refused(_ask(client, case), 409, "LLM_ATTEMPTS_EXHAUSTED")

    assert spy.calls == 2 and _used(seeded) == 2 and _snapshot(seeded) == before


# --------------------------------------------------------------------------- #
# Plans and rows
# --------------------------------------------------------------------------- #
def test_a_new_plan_does_not_reuse_the_old_plans_explanation(
    client: TestClient, seeded: Session, llm_on, provider
) -> None:
    provider()
    case = _planned_case(seeded)
    _ask(client, case)
    service.run_pending(seeded)
    assert _get(client, case)["status"] == "READY"

    optimize.handle(seeded, case)  # ranked again
    seeded.commit()

    assert _get(client, case)["status"] == "NOT_REQUESTED"
    assert _ask(client, case).json()["status"] == "PENDING"
    old, new = _rows(seeded)
    assert old.plan_id != new.plan_id and new.status == ExplanationStatus.PENDING


def test_a_row_queued_before_e1_is_not_swept_until_a_user_asks(
    client: TestClient, seeded: Session, llm_on, provider
) -> None:
    spy = provider()
    case = _planned_case(seeded)
    plan = seeded.scalars(select(CandidatePlan).where(CandidatePlan.case_id == case.id)).one()
    seeded.add(
        RankExplanation(
            case_id=case.id,
            plan_id=plan.id,
            prompt_version="rank-explanation-v1",
            status=ExplanationStatus.PENDING,
        )
    )
    seeded.commit()

    assert service.run_pending(seeded) == 0 and spy.calls == 0
    assert _get(client, case)["status"] == "NOT_REQUESTED"

    assert _ask(client, case).json()["status"] == "PENDING"
    (row,) = _rows(seeded)  # the old row is taken, no second row
    assert (row.prompt_version, row.attempt_limit) == ("rank-explanation-v1", 2)
    assert service.run_pending(seeded) == 1 and spy.calls == 1


def test_an_older_prompt_version_keeps_its_sentence(
    client: TestClient, seeded: Session, llm_on, provider
) -> None:
    spy = provider()
    case = _planned_case(seeded)
    plan = seeded.scalars(select(CandidatePlan).where(CandidatePlan.case_id == case.id)).one()
    seeded.add(
        RankExplanation(
            case_id=case.id,
            plan_id=plan.id,
            prompt_version="rank-explanation-v1",
            status=ExplanationStatus.READY,
            text="old sentence",
            provider="fake",
        )
    )
    seeded.commit()

    response = _ask(client, case)

    assert response.json()["text"] == "old sentence"
    assert len(_rows(seeded)) == 1 and spy.calls == 0


# --------------------------------------------------------------------------- #
# Two connections
# --------------------------------------------------------------------------- #
def test_two_first_requests_at_once_make_one_row(
    frozen_clock, restore_empty_database, llm_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both requests see no row, both insert; the UNIQUE keeps one and both answer PENDING."""
    calls: list[LlmRequest] = []
    monkeypatch.setattr(llm_service, "generate_explanation", lambda r: calls.append(r))
    with SessionLocal() as db:
        load(db)
        case_id = _planned_case(db).id
        db.commit()
    both_checked = threading.Barrier(2, timeout=5)
    real_blocked = service._blocked

    def blocked_after_both_looked(db: Session, plan: CandidatePlan, row: Any) -> Any:
        result = real_blocked(db, plan, row)
        if row is None:
            both_checked.wait()
        return result

    monkeypatch.setattr(service, "_blocked", blocked_after_both_looked)
    answers: list[str] = []
    errors: list[BaseException] = []

    def ask() -> None:
        try:
            with SessionLocal() as db:
                answers.append(service.request(db, case_id).status.value)
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=ask) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert not errors and answers == ["PENDING", "PENDING"]
    with SessionLocal() as db:
        (row,) = _rows(db)
        assert (row.status, row.attempts, row.attempt_limit) == (ExplanationStatus.PENDING, 0, 2)
        assert _logs(db) == [] and _used(db) == 0
    assert calls == []


def test_two_requests_after_a_failure_queue_one_retry(
    frozen_clock, restore_empty_database, llm_on, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row lock serialises asking again: the second one sees PENDING and changes nothing."""
    spy = Provider(LlmCallStatus.TIMEOUT, LlmCallStatus.TIMEOUT)
    monkeypatch.setattr(llm_service, "generate_explanation", spy)
    with SessionLocal() as db:
        load(db)
        case_id = _planned_case(db).id
        service.request(db, case_id)
        service.run_pending(db)
        assert _rows(db)[0].status == ExplanationStatus.FAILED
    start = threading.Barrier(2, timeout=5)
    answers: list[str] = []
    errors: list[BaseException] = []

    def ask() -> None:
        try:
            with SessionLocal() as db:
                start.wait()
                answers.append(service.request(db, case_id).status.value)
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=ask) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert not errors and answers == ["PENDING", "PENDING"]
    with SessionLocal() as db:
        (row,) = _rows(db)
        # One more request's worth of attempts, not two
        assert (row.attempts, row.attempt_limit) == (2, 4)
        service.run_pending(db)
        assert spy.calls == 3 and _used(db) == 3
        assert _rows(db)[0].status == ExplanationStatus.READY
