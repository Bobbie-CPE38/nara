"""`explanation` of GET /cases/{id} (round 3 PR X, round 6 PR E1), on a real plan of the
Solver.

Only the latest plan's newest row is read. FAILED and SKIPPED read as UNAVAILABLE, except a
row SKIPPED because the day's quota was used up. Nothing but a READY row exposes text,
provider or model. can_request and request_blocked_reason come with every answer.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import settings
from app.db.models import CandidatePlan, RankExplanation, StaffingCase
from app.domain.enums import CaseStatus, ExplanationStatus
from app.main import app
from app.workflow.handlers import optimize
from tests.integration.case_rows import leave, make_case, record_gap

NULL_FIELDS = {"text": None, "provider": None, "model_id": None}


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def llm_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "fake")


def _planned_case(db: Session) -> StaffingCase:
    leave(db, 105)
    case = make_case(db, CaseStatus.OPTIMIZING)
    record_gap(db, case)
    optimize.handle(db, case)
    return case


def _plans(db: Session, case: StaffingCase) -> list[CandidatePlan]:
    return list(
        db.scalars(
            select(CandidatePlan).where(CandidatePlan.case_id == case.id).order_by(CandidatePlan.id)
        )
    )


def _plan(db: Session, case: StaffingCase) -> CandidatePlan:
    (plan,) = _plans(db, case)
    return plan


def _row(
    db: Session,
    case: StaffingCase,
    plan: CandidatePlan,
    status: ExplanationStatus,
    **fields: Any,
) -> None:
    fields.setdefault("failure_reason", "TIMEOUT" if status == ExplanationStatus.FAILED else None)
    fields.setdefault("attempt_limit", 2)
    db.add(
        RankExplanation(
            case_id=case.id, plan_id=plan.id, prompt_version="v1", status=status, **fields
        )
    )
    db.flush()


def _explanation(client: TestClient, case: StaffingCase) -> dict[str, Any] | None:
    response = client.get(f"/cases/{case.id}")
    assert response.status_code == 200
    body = response.json()
    assert "explanation" in body
    explanation: dict[str, Any] | None = body["explanation"]
    return explanation


def _answer(status: str, blocked: str | None, **fields: Any) -> dict[str, Any]:
    return {
        "status": status,
        **NULL_FIELDS,
        **fields,
        "can_request": blocked is None,
        "request_blocked_reason": blocked,
    }


def test_no_row_is_not_requested(client: TestClient, seeded: Session, llm_on) -> None:
    case = _planned_case(seeded)

    assert _explanation(client, case) == _answer("NOT_REQUESTED", None)


def test_llm_off_cannot_be_asked_for(client: TestClient, seeded: Session) -> None:
    case = _planned_case(seeded)

    assert _explanation(client, case) == _answer("NOT_REQUESTED", "NOT_CONFIGURED")


def test_a_case_without_a_plan_answers_null(client: TestClient, seeded: Session) -> None:
    case = make_case(seeded, CaseStatus.OPTIMIZING)

    assert _explanation(client, case) is None


def test_pending_has_no_text(client: TestClient, seeded: Session, llm_on) -> None:
    case = _planned_case(seeded)
    _row(seeded, case, _plan(seeded, case), ExplanationStatus.PENDING)

    assert _explanation(client, case) == _answer("PENDING", "PENDING")


def test_a_row_queued_before_e1_waits_for_a_user(
    client: TestClient, seeded: Session, llm_on
) -> None:
    case = _planned_case(seeded)
    _row(seeded, case, _plan(seeded, case), ExplanationStatus.PENDING, attempt_limit=None)

    assert _explanation(client, case) == _answer("NOT_REQUESTED", None)


def test_ready_exposes_text_provider_and_model(client: TestClient, seeded: Session) -> None:
    case = _planned_case(seeded)
    _row(
        seeded,
        case,
        _plan(seeded, case),
        ExplanationStatus.READY,
        text="Staff 201 ranks first.",
        provider="bedrock",
        model_id="some-model",
    )

    # Readable with the LLM off: reading never calls it
    assert _explanation(client, case) == _answer(
        "READY",
        "ALREADY_READY",
        text="Staff 201 ranks first.",
        provider="bedrock",
        model_id="some-model",
    )


def test_ready_from_the_lambda_provider_is_readable(client: TestClient, seeded: Session) -> None:
    """PR B3: the provider the Lambda adapter stores must pass the response schema."""
    case = _planned_case(seeded)
    _row(
        seeded,
        case,
        _plan(seeded, case),
        ExplanationStatus.READY,
        text="Staff 201 ranks first.",
        provider="lambda",
        model_id="global.amazon.nova-2-lite-v1:0",
    )

    assert _explanation(client, case) == _answer(
        "READY",
        "ALREADY_READY",
        text="Staff 201 ranks first.",
        provider="lambda",
        model_id="global.amazon.nova-2-lite-v1:0",
    )


@pytest.mark.parametrize(
    ("status", "reason", "blocked"),
    [
        (ExplanationStatus.FAILED, "TIMEOUT", None),
        (ExplanationStatus.FAILED, "INVALID_OUTPUT", "INVALID_INPUT"),
        (ExplanationStatus.FAILED, "CONFIG_ERROR", None),
        (ExplanationStatus.SKIPPED, "INVALID_INPUT", "INVALID_INPUT"),
    ],
)
def test_failed_and_skipped_are_unavailable(
    client: TestClient,
    seeded: Session,
    llm_on,
    status: ExplanationStatus,
    reason: str,
    blocked: str | None,
) -> None:
    case = _planned_case(seeded)
    _row(
        seeded,
        case,
        _plan(seeded, case),
        status,
        failure_reason=reason,
        provider="bedrock",
        model_id="m",
        text="never shown",
    )

    assert _explanation(client, case) == _answer("UNAVAILABLE", blocked)


def test_a_quota_skip_reads_as_quota_exhausted(client: TestClient, seeded: Session, llm_on) -> None:
    case = _planned_case(seeded)
    _row(
        seeded,
        case,
        _plan(seeded, case),
        ExplanationStatus.SKIPPED,
        failure_reason="QUOTA_EXHAUSTED",
    )

    # The quota of today is free again, so the user may ask again
    assert _explanation(client, case) == _answer("QUOTA_EXHAUSTED", None)


def test_the_latest_plans_row_is_used(client: TestClient, seeded: Session, llm_on) -> None:
    case = _planned_case(seeded)
    first = _plan(seeded, case)
    _row(seeded, case, first, ExplanationStatus.READY, text="old", provider="fake")
    optimize.handle(seeded, case)  # ranked again: a new plan
    second = _plans(seeded, case)[-1]
    assert second.id != first.id

    assert _explanation(client, case) == _answer("NOT_REQUESTED", None)

    _row(seeded, case, second, ExplanationStatus.PENDING)

    assert _explanation(client, case) == _answer("PENDING", "PENDING")
