"""Seam 7: decision checks, request transactions, audit and concurrent approvals."""

import threading
from collections.abc import Iterator
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.base import Base
from app.db.models import (
    Actor,
    ApprovalRequest,
    AuditLog,
    Shift,
    Staff,
    StaffingCase,
    Ward,
)
from app.db.session import SessionLocal, engine
from app.domain.enums import (
    ActorType,
    AuditAction,
    CaseStatus,
    EntityType,
    StaffStatus,
)
from app.main import app
from app.seed import load
from app.services import actor_service, approval_service
from app.services.actor_service import ActorNotFoundError
from app.workflow import orchestrator
from app.workflow.handlers.base import HandlerResult
from tests.integration.conftest import DEMO_NOW

HEADERS = {"X-Demo-User": "900"}
# A head nurse whose home ward is not the ward of the seeded shifts
OTHER_WARD_HEADERS = {"X-Demo-User": "901"}


def _add_other_ward_head_nurse(db: Session) -> None:
    template = db.get(Staff, 900)
    assert template is not None
    db.add(Ward(id=2, name="ER", is_active=True, created_at=DEMO_NOW, updated_at=DEMO_NOW))
    db.flush()
    db.add(
        Staff(
            id=901,
            first_name="Other",
            last_name="Ward",
            email="901@demo.local",
            password_hash="!",
            role_id=template.role_id,
            home_ward_id=2,
            status=StaffStatus.ACTIVE,
            created_at=DEMO_NOW,
            updated_at=DEMO_NOW,
        )
    )
    db.flush()
    db.add(Actor(name="901", actor_type=ActorType.USER, staff_id=901))
    db.flush()


def _make_request(db: Session) -> ApprovalRequest:
    from app.domain.enums import OutreachStatus
    from tests.integration.case_rows import approval, offer, safety, short_case

    case, items = short_case(db, status=CaseStatus.WAITING_APPROVAL)
    offer(db, case, items[201], OutreachStatus.ACCEPTED)
    safety(db, case, items[201], passed=True)
    return approval(db, case, items[201])


@pytest.fixture
def request_row(production_seeded: Session) -> ApprovalRequest:
    request = _make_request(production_seeded)
    production_seeded.commit()  # Release the fixture savepoint, not the outer transaction.
    return request


@pytest.fixture
def client(production_seeded: Session, request_row: ApprovalRequest) -> Iterator[TestClient]:
    def request_db() -> Iterator[Session]:
        with Session(
            bind=production_seeded.get_bind(),
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        ) as db:
            yield db

    app.dependency_overrides[get_db] = request_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


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
        AuditAction.ASSIGNMENT_CREATED,
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.CASE_RESOLVED,
        AuditAction.CASE_STATUS_CHANGED,
    ]
    assert rows[0].actor_id == actor_service.user_id(db, 900)
    assert rows[0].case_id == request_row.case_id
    assert rows[0].entity_type is EntityType.APPROVAL_REQUEST
    assert rows[0].entity_id == request_row.id
    assert rows[0].payload == {"approval_id": request_row.id, "reason": reason}
    assert rows[0].created_at == DEMO_NOW
    assert rows[2].payload == {"from": "WAITING_APPROVAL", "to": "EXECUTING"}
    assert rows[4].payload == {"from": "EXECUTING", "to": "RESOLVED"}


def test_approved_request_leaves_pending_list(
    client: TestClient, request_row: ApprovalRequest
) -> None:
    before = client.get("/approvals?pending=true", headers=HEADERS)
    assert before.status_code == 200
    assert [row["id"] for row in before.json()] == [request_row.id]

    decision = client.post(_url(request_row), headers=HEADERS, json={"approved": True})
    assert decision.status_code == 200

    after = client.get("/approvals?pending=true", headers=HEADERS)
    assert after.status_code == 200
    assert after.json() == []


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


@pytest.mark.parametrize("pending", [True, False])
@pytest.mark.parametrize("approved", [True, False])
def test_head_nurse_of_another_ward_is_403_before_pending_and_answer(
    client: TestClient,
    production_seeded: Session,
    request_row: ApprovalRequest,
    pending: bool,
    approved: bool,
) -> None:
    """The approver must be a head nurse of the shift's ward (workflow.md 6.12, R2-Q21)."""
    _add_other_ward_head_nurse(production_seeded)
    request_row.is_pending = pending
    production_seeded.commit()
    response = client.post(
        _url(request_row),
        headers=OTHER_WARD_HEADERS,
        json={"approved": approved, "reason": "Not my ward"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "The staff member is not a head nurse of the shift's ward"}
    production_seeded.expire_all()
    assert request_row.is_pending is pending
    assert request_row.is_approved is None
    assert request_row.approver_id is None
    assert production_seeded.scalar(select(AuditLog.id)) is None


def test_the_ward_rule_follows_the_shift_not_a_fixed_ward(
    client: TestClient, production_seeded: Session, request_row: ApprovalRequest
) -> None:
    """Move the shift to the other ward: its head nurse may decide, the old one may not."""
    db = production_seeded
    _add_other_ward_head_nurse(db)
    case = db.get(StaffingCase, request_row.case_id)
    assert case is not None
    shift = db.get(Shift, case.shift_id)
    assert shift is not None
    shift.ward_id = 2
    db.commit()

    refused = client.post(_url(request_row), headers=HEADERS, json={"approved": True})
    assert refused.status_code == 403
    _unchanged(db, request_row)

    decided = client.post(_url(request_row), headers=OTHER_WARD_HEADERS, json={"approved": True})
    assert decided.status_code == 200, decided.text
    db.expire_all()
    assert request_row.is_approved is True
    assert request_row.approver_id == 901


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


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_decline_requires_nonblank_reason(
    client: TestClient, production_seeded: Session, request_row: ApprovalRequest, reason: str | None
) -> None:
    response = client.post(
        _url(request_row), headers=HEADERS, json={"approved": False, "reason": reason}
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
    with (
        patch.object(orchestrator, "recompute") as recompute,
        patch("app.services.outreach_service.recompute_affected_cases"),
        patch.object(db, "commit") as commit,
    ):
        request, case = approval_service.decide(
            db,
            approval_id=request_row.id,
            staff_id=900,
            role_id=2,
            home_ward_id=1,
            actor_id=actor_service.user_id(db, 900),
            approved=True,
        )
    assert recompute.call_count == 1
    assert recompute.call_args.args == (db, request.case_id)
    assert callable(recompute.call_args.kwargs["prepare"])
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
            with TestClient(app) as client:
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


@pytest.mark.parametrize("approved", [True, False])
@pytest.mark.parametrize(
    "problem,expected",
    [
        ("missing", 404),
        ("wrong_role", 403),
        ("wrong_ward", 403),
        ("decided", 409),
        ("stopped", 409),
        ("cancelled_offer", 409),
    ],
)
def test_overlong_reason_does_not_override_decision_error_order(
    client: TestClient,
    production_seeded: Session,
    request_row: ApprovalRequest,
    approved: bool,
    problem: str,
    expected: int,
) -> None:
    from app.db.models import CandidateOutreach
    from app.domain.enums import OutreachStatus

    db = production_seeded
    url = _url(request_row)
    headers = HEADERS
    if problem == "missing":
        url = "/approvals/9223372036854775807/decision"
        headers = {"X-Demo-User": "105"}
    elif problem == "wrong_role":
        headers = {"X-Demo-User": "105"}
    elif problem == "wrong_ward":
        _add_other_ward_head_nurse(db)
        headers = OTHER_WARD_HEADERS
    elif problem == "decided":
        request_row.is_pending = False
    elif problem == "stopped":
        db.get(StaffingCase, request_row.case_id).status = CaseStatus.FAILED
    else:
        row = db.scalars(
            select(CandidateOutreach).where(
                CandidateOutreach.candidate_item_id == request_row.candidate_item_id
            )
        ).one()
        row.status = OutreachStatus.CANCELLED
    db.commit()
    pending_before = request_row.is_pending
    response = client.post(url, headers=headers, json={"approved": approved, "reason": "x" * 501})
    assert response.status_code == expected, response.text
    db.expire_all()
    assert request_row.is_pending == pending_before
    assert request_row.is_approved is None and request_row.reason is None
    assert db.scalar(select(AuditLog.id)) is None
