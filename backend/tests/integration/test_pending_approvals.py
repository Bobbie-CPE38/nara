"""Seam 6: authenticated, read-only pending approval lists from PostgreSQL."""

from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.routes import approvals
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidatePlan,
    Staff,
    StaffingCase,
    StaffingEvent,
)
from app.domain.enums import (
    ApprovalMode,
    CandidateSource,
    CaseStatus,
    EventStatus,
    EventType,
    SolverStatus,
    StaffStatus,
)
from app.services import approval_service
from tests.integration.conftest import DEMO_NOW

URL = "/approvals?pending=true"
HEADERS = {"X-Demo-User": "900"}


def _request(
    db: Session,
    *,
    case: StaffingCase | None = None,
    pending: bool = True,
    approved: bool | None = None,
) -> ApprovalRequest:
    if case is None:
        event = StaffingEvent(
            event_type=EventType.STAFF_UNAVAILABLE,
            shift_id=1,
            staff_id=105,
            occurred_at=DEMO_NOW,
            status=EventStatus.PROCESSED,
        )
        db.add(event)
        db.flush()
        case = StaffingCase(
            event_id=event.id,
            shift_id=1,
            status=CaseStatus.WAITING_APPROVAL,
            required_replacement_time=DEMO_NOW + timedelta(hours=2),
        )
        db.add(case)
        db.flush()
    plan = CandidatePlan(
        case_id=case.id,
        solver_status=SolverStatus.FEASIBLE,
        generated_at=DEMO_NOW,
        execution_time_ms=0,
        solver_version="stub",
        hard_constraint_policy_id=1,
        soft_constraint_policy_id=1,
        input_snapshot={},
    )
    db.add(plan)
    db.flush()
    item = CandidateItem(
        plan_id=plan.id,
        staff_id=201,
        rank=1,
        source=CandidateSource.SAME_WARD,
        proposed_shift_id=1,
    )
    db.add(item)
    db.flush()
    request = ApprovalRequest(
        case_id=case.id,
        candidate_item_id=item.id,
        required_approver_role=2,
        approval_mode=ApprovalMode.MANUAL,
        is_pending=pending,
        is_approved=approved,
        reason=None,
        requested_at=DEMO_NOW,
        approver_id=900 if approved is not None else None,
        decided_at=DEMO_NOW if approved is not None else None,
    )
    db.add(request)
    db.flush()
    return request


@pytest.fixture
def client(production_seeded: Session) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(approvals.router)
    app.dependency_overrides[get_db] = lambda: production_seeded
    with TestClient(app) as client:
        yield client


def test_empty_list_is_a_top_level_array(client: TestClient) -> None:
    response = client.get(URL, headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == []


def test_pending_response_contract(client: TestClient, production_seeded: Session) -> None:
    request = _request(production_seeded)
    response = client.get(URL, headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": request.id,
            "case_id": request.case_id,
            "candidate_item_id": request.candidate_item_id,
            "required_approver_role": 2,
            "approval_mode": "MANUAL",
            "is_pending": True,
            "requested_at": DEMO_NOW.isoformat(),
        }
    ]


def test_filters_non_pending_rows_and_sorts_by_id(
    client: TestClient, production_seeded: Session
) -> None:
    db = production_seeded
    first = _request(db)
    _request(db, pending=False, approved=True)
    second = _request(db)
    _request(db, pending=False, approved=False)
    first.requested_at = DEMO_NOW + timedelta(days=1)
    db.flush()
    response = client.get(URL, headers=HEADERS)
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [first.id, second.id]


def test_multiple_pending_rows_for_one_case_are_conflict(
    client: TestClient, production_seeded: Session
) -> None:
    first = _request(production_seeded)
    case = production_seeded.get(StaffingCase, first.case_id)
    assert case is not None
    _request(production_seeded, case=case)
    response = client.get(URL, headers=HEADERS)
    assert response.status_code == 409
    assert response.json() == {
        "detail": f"Case {case.id} has more than one pending approval request"
    }
    assert production_seeded.scalar(select(AuditLog.id)) is None


def test_a_completed_request_for_the_same_case_is_not_a_duplicate(
    client: TestClient, production_seeded: Session
) -> None:
    pending = _request(production_seeded)
    case = production_seeded.get(StaffingCase, pending.case_id)
    assert case is not None
    _request(production_seeded, case=case, pending=False, approved=True)
    response = client.get(URL, headers=HEADERS)
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [pending.id]


@pytest.mark.parametrize("staff_id", [105, 201, 900])
def test_reads_do_not_require_the_approver_role(
    client: TestClient, production_seeded: Session, staff_id: int
) -> None:
    request = _request(production_seeded)
    response = client.get(URL, headers={"X-Demo-User": str(staff_id)})
    assert response.status_code == 200
    assert response.json()[0]["id"] == request.id


@pytest.mark.parametrize("headers", [{}, {"X-Demo-User": "abc"}, {"X-Demo-User": "999"}])
def test_authentication_is_required(client: TestClient, headers: dict[str, str]) -> None:
    assert client.get(URL, headers=headers).status_code == 401


def test_inactive_user_cannot_read(client: TestClient, production_seeded: Session) -> None:
    staff = production_seeded.get(Staff, 900)
    assert staff is not None
    staff.status = StaffStatus.INACTIVE
    production_seeded.flush()
    assert client.get(URL, headers=HEADERS).status_code == 401


@pytest.mark.parametrize("url", ["/approvals?pending=false", "/approvals?pending=invalid"])
def test_unsupported_filter_is_422(client: TestClient, url: str) -> None:
    assert client.get(url, headers=HEADERS).status_code == 422


def test_pending_defaults_to_true(client: TestClient, production_seeded: Session) -> None:
    request = _request(production_seeded)
    assert client.get("/approvals", headers=HEADERS).json()[0]["id"] == request.id


def test_nullable_approver_role_is_preserved(
    client: TestClient, production_seeded: Session
) -> None:
    request = _request(production_seeded)
    request.required_approver_role = None
    production_seeded.flush()
    assert client.get(URL, headers=HEADERS).json()[0]["required_approver_role"] is None


def test_get_is_read_only(client: TestClient, production_seeded: Session) -> None:
    db = production_seeded
    request = _request(db)
    before = dict(vars(request))
    with (
        patch.object(db, "commit", wraps=db.commit) as commit,
        patch.object(db, "flush", wraps=db.flush) as flush,
    ):
        response = client.get(URL, headers=HEADERS)
    assert response.status_code == 200
    commit.assert_not_called()
    flush.assert_not_called()
    assert vars(request) == before
    assert not db.new
    assert not db.dirty
    case = db.get(StaffingCase, request.case_id)
    assert case is not None
    assert case.status is CaseStatus.WAITING_APPROVAL
    assert db.scalar(select(AuditLog.id)) is None


def test_service_reports_duplicate_without_hiding_rows(production_seeded: Session) -> None:
    db = production_seeded
    first = _request(db)
    case = db.get(StaffingCase, first.case_id)
    assert case is not None
    _request(db, case=case)
    with pytest.raises(approval_service.DuplicatePendingApprovalError):
        approval_service.list_pending(db)
