"""Seam 7: decision checks, request transactions, audit and concurrent approvals."""

import threading
from collections.abc import Iterator
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.exception_handlers import register_exception_handlers
from app.api.routes import approvals
from app.db.base import Base
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidatePlan,
    StaffingCase,
    StaffingEvent,
)
from app.db.session import SessionLocal, engine
from app.domain.enums import (
    ApprovalMode,
    AuditAction,
    CandidateSource,
    CaseStatus,
    EntityType,
    EventStatus,
    EventType,
    SolverStatus,
)
from app.seed import load
from app.services import actor_service, approval_service
from app.services.actor_service import ActorNotFoundError
from app.workflow import orchestrator
from app.workflow.handlers.base import HandlerResult
from tests.integration.conftest import DEMO_NOW

HEADERS = {"X-Demo-User": "900"}


def _make_request(db: Session) -> ApprovalRequest:
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
        is_pending=True,
        approver_id=None,
        is_approved=None,
        reason=None,
        requested_at=DEMO_NOW,
        decided_at=None,
    )
    db.add(request)
    db.flush()
    return request


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(approvals.router)
    register_exception_handlers(app)
    return app


@pytest.fixture(autouse=True)
def execution_stand_in(monkeypatch: pytest.MonkeyPatch) -> None:
    # Person 2 owns seam 8. These tests verify the decision-to-execution handoff.
    def execute(db: Session, case: StaffingCase) -> HandlerResult:
        return HandlerResult(next_status=CaseStatus.RESOLVED)

    monkeypatch.setitem(orchestrator.HANDLERS, CaseStatus.EXECUTING, execute)


@pytest.fixture
def request_row(production_seeded: Session) -> ApprovalRequest:
    request = _make_request(production_seeded)
    production_seeded.commit()  # Release the fixture savepoint, not the outer transaction.
    return request


@pytest.fixture
def client(production_seeded: Session, request_row: ApprovalRequest) -> Iterator[TestClient]:
    app = _app()

    def request_db() -> Iterator[Session]:
        with Session(
            bind=production_seeded.get_bind(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as db:
            yield db

    app.dependency_overrides[get_db] = request_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _url(request: ApprovalRequest) -> str:
    return f"/approvals/{request.id}/decision"


def _unchanged(db: Session, request: ApprovalRequest) -> None:
    db.expire_all()
    assert request.is_pending is True
    assert request.is_approved is None
    assert request.approver_id is None
    assert request.reason is None
    assert request.decided_at is None
    assert db.scalar(select(AuditLog.id)) is None


@pytest.mark.parametrize("reason", [None, "Coverage confirmed"])
def test_approval_fields_response_and_audit(
    client: TestClient, production_seeded: Session, request_row: ApprovalRequest, reason: str | None
) -> None:
    response = client.post(
        _url(request_row), headers=HEADERS, json={"approved": True, "reason": reason}
    )
    assert response.status_code == 200
    assert response.json() == {
        "approval_id": request_row.id,
        "is_approved": True,
        "case_id": request_row.case_id,
        "case_status": "RESOLVED",
    }
    db = production_seeded
    db.expire_all()
    assert request_row.is_pending is False
    assert request_row.is_approved is True
    assert request_row.approver_id == 900
    assert request_row.reason == reason
    assert request_row.decided_at == DEMO_NOW
    rows = list(db.scalars(select(AuditLog).order_by(AuditLog.id)))
    assert [row.action for row in rows] == [
        AuditAction.APPROVAL_APPROVED,
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.CASE_STATUS_CHANGED,
    ]
    assert rows[0].actor_id == actor_service.user_id(db, 900)
    assert rows[0].case_id == request_row.case_id
    assert rows[0].entity_type is EntityType.APPROVAL_REQUEST
    assert rows[0].entity_id == request_row.id
    assert rows[0].payload == {"approval_id": request_row.id, "reason": reason}
    assert rows[0].created_at == DEMO_NOW
    assert rows[1].payload == {"from": "WAITING_APPROVAL", "to": "EXECUTING"}
    assert rows[2].payload == {"from": "EXECUTING", "to": "RESOLVED"}


@pytest.mark.parametrize("approved", [True, False])
def test_missing_request_is_404_before_role_and_answer(
    client: TestClient, production_seeded: Session, request_row: ApprovalRequest, approved: bool
) -> None:
    response = client.post(
        "/approvals/999/decision", headers={"X-Demo-User": "105"}, json={"approved": approved}
    )
    assert response.status_code == 404
    _unchanged(production_seeded, request_row)


@pytest.mark.parametrize("pending", [True, False])
@pytest.mark.parametrize("approved", [True, False])
def test_wrong_role_is_403_before_pending_and_answer(
    client: TestClient,
    production_seeded: Session,
    request_row: ApprovalRequest,
    pending: bool,
    approved: bool,
) -> None:
    request_row.is_pending = pending
    production_seeded.commit()
    response = client.post(
        _url(request_row), headers={"X-Demo-User": "105"}, json={"approved": approved}
    )
    assert response.status_code == 403
    production_seeded.expire_all()
    assert request_row.is_pending is pending
    assert request_row.is_approved is None
    assert production_seeded.scalar(select(AuditLog.id)) is None


@pytest.mark.parametrize("approved", [True, False])
def test_not_pending_is_409_before_answer(
    client: TestClient, production_seeded: Session, request_row: ApprovalRequest, approved: bool
) -> None:
    request_row.is_pending = False
    production_seeded.commit()
    response = client.post(_url(request_row), headers=HEADERS, json={"approved": approved})
    assert response.status_code == 409
    assert production_seeded.scalar(select(AuditLog.id)) is None


def test_role_and_approver_identity_follow_the_request_and_header(
    client: TestClient, production_seeded: Session, request_row: ApprovalRequest
) -> None:
    request_row.required_approver_role = 1
    production_seeded.commit()
    response = client.post(
        _url(request_row), headers={"X-Demo-User": "201"}, json={"approved": True}
    )
    assert response.status_code == 200
    production_seeded.expire_all()
    assert request_row.approver_id == 201
    audit = production_seeded.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.APPROVAL_APPROVED)
    ).one()
    assert audit.actor_id == actor_service.user_id(production_seeded, 201)


def test_decline_is_422_without_writes(
    client: TestClient, production_seeded: Session, request_row: ApprovalRequest
) -> None:
    response = client.post(
        _url(request_row), headers=HEADERS, json={"approved": False, "reason": "No"}
    )
    assert response.status_code == 422
    _unchanged(production_seeded, request_row)


def test_null_required_role_does_not_authorize_anyone(
    client: TestClient, production_seeded: Session, request_row: ApprovalRequest
) -> None:
    request_row.required_approver_role = None
    production_seeded.commit()
    assert (
        client.post(_url(request_row), headers=HEADERS, json={"approved": True}).status_code == 403
    )
    _unchanged(production_seeded, request_row)


def test_repeat_does_not_overwrite_reason_or_write_a_second_audit(
    client: TestClient, production_seeded: Session, request_row: ApprovalRequest
) -> None:
    assert (
        client.post(
            _url(request_row), headers=HEADERS, json={"approved": True, "reason": "First"}
        ).status_code
        == 200
    )
    response = client.post(
        _url(request_row), headers=HEADERS, json={"approved": True, "reason": "Second"}
    )
    assert response.status_code == 409
    production_seeded.expire_all()
    assert request_row.reason == "First"
    actions = list(production_seeded.scalars(select(AuditLog.action)))
    assert actions.count(AuditAction.APPROVAL_APPROVED) == 1


@pytest.mark.parametrize("headers", [{}, {"X-Demo-User": "abc"}, {"X-Demo-User": "999"}])
def test_requires_demo_auth(
    client: TestClient,
    production_seeded: Session,
    request_row: ApprovalRequest,
    headers: dict[str, str],
) -> None:
    assert (
        client.post(_url(request_row), headers=headers, json={"approved": True}).status_code == 401
    )
    _unchanged(production_seeded, request_row)


@pytest.mark.parametrize(
    "body", [{}, {"approved": "true"}, {"approved": 1}, {"approved": True, "approver_id": 105}]
)
def test_body_requires_boolean_and_does_not_accept_identity(
    client: TestClient,
    production_seeded: Session,
    request_row: ApprovalRequest,
    body: dict[str, object],
) -> None:
    assert client.post(_url(request_row), headers=HEADERS, json=body).status_code == 422
    _unchanged(production_seeded, request_row)


@pytest.mark.parametrize("approval_id", [0, -1, 2**63, "abc"])
def test_invalid_id_is_422(client: TestClient, approval_id: int | str) -> None:
    assert (
        client.post(
            f"/approvals/{approval_id}/decision", headers=HEADERS, json={"approved": True}
        ).status_code
        == 422
    )


def test_service_delegates_commit_and_status_to_orchestrator(
    production_seeded: Session, request_row: ApprovalRequest
) -> None:
    db = production_seeded
    with patch.object(orchestrator, "resume") as resume, patch.object(db, "commit") as commit:
        request, case = approval_service.decide(
            db,
            approval_id=request_row.id,
            staff_id=900,
            role_id=2,
            actor_id=actor_service.user_id(db, 900),
            approved=True,
        )
    resume.assert_called_once_with(db, request.case_id, CaseStatus.EXECUTING)
    commit.assert_not_called()
    assert case.status is CaseStatus.WAITING_APPROVAL


def test_invalid_transition_rolls_back_the_decision(
    client: TestClient, production_seeded: Session, request_row: ApprovalRequest
) -> None:
    case = production_seeded.get(StaffingCase, request_row.case_id)
    assert case is not None
    case.status = CaseStatus.RESOLVED
    production_seeded.commit()
    assert (
        client.post(_url(request_row), headers=HEADERS, json={"approved": True}).status_code == 409
    )
    _unchanged(production_seeded, request_row)
    assert case.status is CaseStatus.RESOLVED


def test_execution_failure_returns_200_failed_and_keeps_the_approval(
    client: TestClient,
    production_seeded: Session,
    request_row: ApprovalRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(db: Session, case: StaffingCase) -> HandlerResult:
        raise RuntimeError("execution failed")

    monkeypatch.setitem(orchestrator.HANDLERS, CaseStatus.EXECUTING, fail)
    response = client.post(_url(request_row), headers=HEADERS, json={"approved": True})
    assert response.status_code == 200
    assert response.json()["case_status"] == "FAILED"
    production_seeded.expire_all()
    assert request_row.is_approved is True
    assert request_row.is_pending is False
    actions = list(production_seeded.scalars(select(AuditLog.action).order_by(AuditLog.id)))
    assert actions == [
        AuditAction.APPROVAL_APPROVED,
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.WORKFLOW_FAILED,
    ]


def test_unrecordable_error_returns_500_and_rolls_back(
    client: TestClient, production_seeded: Session, request_row: ApprovalRequest
) -> None:
    with patch.object(actor_service, "component_id", side_effect=ActorNotFoundError("missing")):
        response = client.post(_url(request_row), headers=HEADERS, json={"approved": True})
    assert response.status_code == 500
    _unchanged(production_seeded, request_row)


@pytest.fixture
def committed_request(frozen_clock: datetime) -> Iterator[int]:
    with SessionLocal.begin() as db:
        load(db)
        request_id = _make_request(db).id
    try:
        yield request_id
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


def test_concurrent_decisions_write_one_approval(committed_request: int) -> None:
    barrier = threading.Barrier(2, timeout=10)
    results: list[int] = []
    errors: list[Exception] = []

    def approve() -> None:
        try:
            with TestClient(_app()) as client:
                barrier.wait()
                results.append(
                    client.post(
                        f"/approvals/{committed_request}/decision",
                        headers=HEADERS,
                        json={"approved": True},
                    ).status_code
                )
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=approve) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(results) == [200, 409]
    with SessionLocal() as db:
        request = db.get(ApprovalRequest, committed_request)
        assert request is not None
        assert request.approver_id == 900
        assert request.is_approved is True
        assert request.is_pending is False
        assert request.decided_at == DEMO_NOW
        actions = list(db.scalars(select(AuditLog.action)))
        assert actions.count(AuditAction.APPROVAL_APPROVED) == 1
