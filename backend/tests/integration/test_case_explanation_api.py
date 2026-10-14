"""`explanation` of GET /cases/{id} (round 3 PR X), on a real plan of the Solver.

Only the latest plan's newest row is read. FAILED and SKIPPED both read as
UNAVAILABLE, and nothing but a READY row exposes text, provider or model.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
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


def _planned_case(db: Session) -> StaffingCase:
    leave(db, 105)
    case = make_case(db, CaseStatus.OPTIMIZING)
    record_gap(db, case)
    optimize.handle(db, case)
    return case


def _plan(db: Session, case: StaffingCase) -> CandidatePlan:
    return db.scalars(select(CandidatePlan).where(CandidatePlan.case_id == case.id)).one()


def _row(
    db: Session,
    case: StaffingCase,
    plan: CandidatePlan,
    status: ExplanationStatus,
    **fields: Any,
) -> None:
    db.add(
        RankExplanation(
            case_id=case.id,
            plan_id=plan.id,
            prompt_version="v1",
            status=status,
            failure_reason="BOOM" if status == ExplanationStatus.FAILED else None,
            **fields,
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


def test_no_row_answers_null(client: TestClient, seeded: Session) -> None:
    case = _planned_case(seeded)

    assert _explanation(client, case) is None


def test_a_case_without_a_plan_answers_null(client: TestClient, seeded: Session) -> None:
    case = make_case(seeded, CaseStatus.OPTIMIZING)

    assert _explanation(client, case) is None


def test_pending_has_no_text(client: TestClient, seeded: Session) -> None:
    case = _planned_case(seeded)
    _row(seeded, case, _plan(seeded, case), ExplanationStatus.PENDING)

    assert _explanation(client, case) == {"status": "PENDING", **NULL_FIELDS}


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

    assert _explanation(client, case) == {
        "status": "READY",
        "text": "Staff 201 ranks first.",
        "provider": "bedrock",
        "model_id": "some-model",
    }


@pytest.mark.parametrize("status", [ExplanationStatus.FAILED, ExplanationStatus.SKIPPED])
def test_failed_and_skipped_are_unavailable(
    client: TestClient, seeded: Session, status: ExplanationStatus
) -> None:
    case = _planned_case(seeded)
    _row(seeded, case, _plan(seeded, case), status, provider="bedrock", model_id="m")

    assert _explanation(client, case) == {"status": "UNAVAILABLE", **NULL_FIELDS}


def test_the_latest_plans_row_is_used(client: TestClient, seeded: Session) -> None:
    case = _planned_case(seeded)
    first = _plan(seeded, case)
    second = CandidatePlan(
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
    seeded.add(second)
    seeded.flush()
    _row(
        seeded,
        case,
        first,
        ExplanationStatus.READY,
        text="old",
        provider="fake",
    )

    assert _explanation(client, case) is None

    _row(seeded, case, second, ExplanationStatus.PENDING)

    assert _explanation(client, case) == {"status": "PENDING", **NULL_FIELDS}
