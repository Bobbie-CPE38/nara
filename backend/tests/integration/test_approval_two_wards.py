"""PR S: per-side decisions, Supervisor authority and execution only after both wards."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.api.dependencies import get_db
from app.core import clock
from app.db.base import Base
from app.db.models import (
    Actor,
    ApprovalRequest,
    ApprovalWardDecision,
    AuditLog,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    Ward,
)
from app.db.session import SessionLocal, engine
from app.domain.enums import (
    ActorType,
    AssignmentType,
    AuditAction,
    CandidateSource,
    CaseStatus,
    RosterStatus,
    StaffStatus,
)
from app.main import app
from app.seed import load
from app.services import approval_service, approval_timeout_service, handoff_service, roster_service
from tests.integration.case_rows import approval, short_case
from tests.integration.conftest import DEMO_NOW
from tests.integration.test_approval_decision import _add_other_ward_head_nurse

DEST = {"X-Demo-User": "900"}


def build(db, *, transfer=True):
    case, items = short_case(db, 105, status=CaseStatus.WAITING_APPROVAL)
    ward_id, source_headers = _add_other_ward_head_nurse(db)
    supervisor_id = int(source_headers["X-Demo-User"]) + 1
    db.add(
        Staff(
            id=supervisor_id,
            first_name="Supervisor",
            last_name="Demo",
            email=f"{supervisor_id}@demo.local",
            password_hash="!",
            role_id=3,
            home_ward_id=1,
            status=StaffStatus.ACTIVE,
        )
    )
    db.flush()
    db.add(Actor(name=str(supervisor_id), actor_type=ActorType.USER, staff_id=supervisor_id))
    destination = db.get(Shift, case.shift_id)
    source = Shift(
        ward_id=ward_id,
        patient_count=1,
        start_at=destination.start_at,
        end_at=destination.end_at,
        shift_type=destination.shift_type,
        is_active=True,
    )
    db.add(source)
    db.flush()
    row = RosterAssignment(
        staff_id=201,
        shift_id=source.id,
        status=RosterStatus.ASSIGNED,
        assignment_type=AssignmentType.REGULAR,
    )
    db.add(row)
    db.flush()
    if transfer:
        items[201].source_assignment_id = row.id
        items[201].source = CandidateSource.CROSS_WARD
    request = approval(db, case, items[201])
    db.commit()
    return request.id, source_headers, {"X-Demo-User": str(supervisor_id)}


@pytest.fixture
def scene(production_seeded):
    db = production_seeded
    built = build(db)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield db, client, built
    finally:
        app.dependency_overrides.pop(get_db, None)


def decide(client, request_id, headers=DEST, *, approved=True, side=None, reason=None):
    body = {"approved": approved}
    if side is not None:
        body["side"] = side
    if reason is not None:
        body["reason"] = reason
    return client.post(f"/approvals/{request_id}/decision", headers=headers, json=body)


def transfer_stub(db, case, *, approval):
    """Test stand-in for the future C2 writer; PR S itself never implements a move."""
    from app.db.models import CandidateItem

    item = db.get(CandidateItem, approval.candidate_item_id)
    source_id = item.source_assignment_id
    db.get(RosterAssignment, source_id).status = RosterStatus.CANCELLED
    item.source_assignment_id = None
    assignment = _create_replacement(db, case, approval=approval)
    item.source_assignment_id = source_id
    assignment.transferred_from_assignment_id = source_id
    db.flush()
    return assignment


_create_replacement = roster_service.create_replacement


@pytest.mark.parametrize("source_first", [False, True])
def test_both_wards_are_required_and_only_last_approval_executes(scene, source_first):
    db, client, (request_id, source, _) = scene
    first_headers, last_headers = (source, DEST) if source_first else (DEST, source)
    with patch.object(roster_service, "create_replacement", side_effect=transfer_stub) as writer:
        first = decide(client, request_id, first_headers)
        assert first.status_code == 200
        assert first.json()["is_approved"] is None
        assert first.json()["outcome"] == "WAITING_OTHER_WARD"
        assert writer.call_count == 0
        request = db.get(ApprovalRequest, request_id)
        assert request.is_pending and request.approver_id is None and request.decided_at is None
        last = decide(client, request_id, last_headers)
        assert last.status_code == 200
        assert last.json()["outcome"] == "ASSIGNED"
        assert last.json()["is_approved"] is True
        assert writer.call_count == 1
    assert db.scalar(select(func.count()).select_from(ApprovalWardDecision)) == 2
    actions = list(db.scalars(select(AuditLog.action)))
    assert actions.count(AuditAction.APPROVAL_WARD_APPROVED) == 1
    assert actions.count(AuditAction.APPROVAL_APPROVED) == 1


@pytest.mark.parametrize("first_approved", [False, True])
def test_either_ward_rejection_finishes_request_without_execution(scene, first_approved):
    db, client, (request_id, source, _) = scene
    if first_approved:
        assert decide(client, request_id).json()["outcome"] == "WAITING_OTHER_WARD"
    with patch.object(roster_service, "create_replacement") as writer:
        response = decide(client, request_id, source, approved=False, reason="  cannot release  ")
        assert response.status_code == 200
        assert response.json()["outcome"] == "REJECTED"
        assert response.json()["is_approved"] is False
        writer.assert_not_called()
    request = db.get(ApprovalRequest, request_id)
    assert not request.is_pending and request.reason == "cannot release"
    assert decide(client, request_id).status_code == 409


def test_wrong_side_is_forbidden_and_duplicate_side_is_conflict(scene):
    _, client, (request_id, source, _) = scene
    assert decide(client, request_id, side="SOURCE").status_code == 403
    assert decide(client, request_id, source, side="DESTINATION").status_code == 403
    assert decide(client, request_id).status_code == 200
    assert decide(client, request_id, side="DESTINATION", reason="x" * 501).status_code == 409


def test_supervisor_wait_boundary_and_one_decision_per_click(scene):
    db, client, (request_id, _, supervisor) = scene
    clock.set_time(DEMO_NOW + timedelta(seconds=600, microseconds=-1))
    assert decide(client, request_id, supervisor, side="DESTINATION").status_code == 403
    clock.set_time(DEMO_NOW + timedelta(seconds=600))
    assert decide(client, request_id, supervisor).status_code == 422
    assert (
        decide(client, request_id, supervisor, side="SOURCE").json()["outcome"]
        == "WAITING_OTHER_WARD"
    )
    with patch.object(roster_service, "create_replacement", side_effect=transfer_stub):
        result = decide(client, request_id, supervisor)
    assert result.json()["outcome"] == "ASSIGNED"
    rows = list(db.scalars(select(ApprovalWardDecision)))
    assert len(rows) == 2
    assert all(row.approver_id == int(supervisor["X-Demo-User"]) for row in rows)
    assert all(row.decided_as.value == "SUPERVISOR" for row in rows)


def test_supervisor_before_wait_gets_403_even_on_already_decided_side(scene):
    _, client, (request_id, source, supervisor) = scene
    assert decide(client, request_id, source).status_code == 200
    assert decide(client, request_id, supervisor, side="SOURCE").status_code == 403
    clock.set_time(DEMO_NOW + timedelta(seconds=600))
    assert decide(client, request_id, supervisor, side="SOURCE").status_code == 409


def test_pending_list_reports_home_source_sides_and_supervisor_time(scene):
    db, client, (request_id, _, _) = scene
    # The fixture adds the source ward after every seeded ward (round 4 PR W4 seeds 2 and 3)
    source_ward = db.scalar(select(func.max(Ward.id)))
    assert decide(client, request_id).status_code == 200
    row = client.get("/approvals", headers=DEST).json()[0]
    assert row["home_ward_id"] == 1
    assert row["source_ward_id"] == source_ward
    assert row["wards"] == [
        {"ward_id": 1, "side": "DESTINATION", "status": "APPROVED"},
        {"ward_id": source_ward, "side": "SOURCE", "status": "PENDING"},
    ]
    assert row["supervisor_from"] == (DEMO_NOW + timedelta(seconds=600)).isoformat()


def test_partial_approval_keeps_original_timeout_and_history(scene):
    db, client, (request_id, source, _) = scene
    assert decide(client, request_id).status_code == 200
    clock.set_time(DEMO_NOW + timedelta(seconds=900))
    assert decide(client, request_id, source).status_code == 409
    assert approval_timeout_service.expire_due_approvals(db).approval_ids == [request_id]
    assert db.get(ApprovalRequest, request_id).is_timed_out
    assert db.scalar(select(func.count()).select_from(ApprovalWardDecision)) == 1
    assert approval_timeout_service.expire_due_approvals(db).approval_ids == []


def test_transfer_writer_guard_preserves_both_approvals_and_reports_execution_failed(scene):
    db, client, (request_id, source, _) = scene
    decide(client, request_id)
    response = decide(client, request_id, source)
    assert response.json()["outcome"] == "EXECUTION_FAILED"
    assert response.json()["is_approved"] is True
    assert response.json()["case_status"] == "FAILED"
    assert db.scalar(select(func.count()).select_from(ApprovalWardDecision)) == 2


def test_single_ward_source_is_422_and_supervisor_can_decide_destination(production_seeded):
    db = production_seeded
    request_id, _, supervisor = build(db, transfer=False)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            assert decide(client, request_id, side="SOURCE").status_code == 422
            clock.set_time(DEMO_NOW + timedelta(seconds=600))
            assert (
                decide(
                    client, request_id, supervisor, approved=False, reason="not selected"
                ).status_code
                == 200
            )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_supervisor_can_manage_foreign_handoff_immediately(scene):
    db, _, (request_id, source, supervisor) = scene
    request = db.get(ApprovalRequest, request_id)
    case = db.get(StaffingCase, request.case_id)
    case.status = CaseStatus.MANUAL_HANDOFF
    db.commit()
    supervisor_staff = db.get(Staff, int(supervisor["X-Demo-User"]))
    supervisor_staff.home_ward_id = 2
    db.commit()
    rows = handoff_service.list_cases(
        db, role_id=3, home_ward_id=2, statuses=[CaseStatus.MANUAL_HANDOFF]
    )
    assert case.id in [row.id for row in rows]
    handoff_service.close(
        db,
        case_id=case.id,
        role_id=3,
        home_ward_id=2,
        actor_id=next(db.scalars(select(Actor.id).where(Actor.staff_id == supervisor_staff.id))),
        reason="No safe replacement",
    )
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.case_id == case.id, AuditLog.action == AuditAction.CASE_CLOSED_UNRESOLVED
        )
    )
    assert audit.payload["closed_by"] == "SUPERVISOR"


@pytest.fixture
def committed_scene(frozen_clock):
    with SessionLocal() as db:
        load(db)
        result = build(db)
    try:
        yield result
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


@pytest.mark.parametrize("same_side", [False, True], ids=["two-wards", "same-side"])
def test_two_connections_never_execute_before_both_sides_or_twice(committed_scene, same_side):
    request_id, source, _ = committed_scene
    barrier = threading.Barrier(2, timeout=10)

    def run(headers):
        with TestClient(app) as client:
            barrier.wait()
            response = decide(client, request_id, headers)
            return response.status_code, response.json()

    with patch.object(roster_service, "create_replacement", side_effect=transfer_stub) as writer:
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(run, DEST), pool.submit(run, DEST if same_side else source)]
            results = [job.result(timeout=20) for job in jobs]
        assert sorted(code for code, _ in results) == ([200, 409] if same_side else [200, 200])
        assert writer.call_count == (0 if same_side else 1)
    with SessionLocal() as db:
        request = db.get(ApprovalRequest, request_id)
        assert request.is_pending is same_side
        assert db.scalar(select(func.count()).select_from(ApprovalWardDecision)) == (
            1 if same_side else 2
        )
        if not same_side:
            assert sorted(body["outcome"] for _, body in results) == [
                "ASSIGNED",
                "WAITING_OTHER_WARD",
            ]


def test_two_connections_final_decision_racing_timeout_keeps_first_ward_history(committed_scene):
    request_id, source, _ = committed_scene
    with TestClient(app) as client:
        assert decide(client, request_id).json()["outcome"] == "WAITING_OTHER_WARD"
    clock.set_time(DEMO_NOW + timedelta(seconds=900))
    barrier = threading.Barrier(2, timeout=10)

    def timeout():
        with SessionLocal() as db:
            barrier.wait()
            return approval_timeout_service.expire_due_approvals(db).approval_ids

    def human():
        with TestClient(app) as client:
            barrier.wait()
            return decide(client, request_id, source).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(timeout), pool.submit(human)
        assert a.result(timeout=20) == [request_id]
        assert b.result(timeout=20) == 409
    with SessionLocal() as db:
        assert db.get(ApprovalRequest, request_id).is_timed_out
        assert db.scalar(select(func.count()).select_from(ApprovalWardDecision)) == 1
        actions = list(db.scalars(select(AuditLog.action)))
        assert actions.count(AuditAction.APPROVAL_TIMEOUT) == 1
        assert AuditAction.ASSIGNMENT_CREATED not in actions


def test_role_policy_cannot_grant_a_nurse_approval_authority(scene):
    db, client, (request_id, _, _) = scene
    db.get(ApprovalRequest, request_id).required_approver_role = 1
    db.commit()
    assert decide(client, request_id, {"X-Demo-User": "201"}).status_code == 403
    assert decide(client, request_id).status_code == 403
    assert db.scalar(select(func.count()).select_from(ApprovalWardDecision)) == 0


@pytest.mark.parametrize("side", ["invalid", "SOURCE"])
def test_missing_wrong_role_stale_and_bad_side_follow_error_order(scene, side):
    db, client, (request_id, _, supervisor) = scene
    assert decide(client, 999999, side=side, reason="x" * 501).status_code == 404
    assert decide(client, request_id, {"X-Demo-User": "201"}, side=side).status_code == 403
    request = db.get(ApprovalRequest, request_id)
    request.is_pending = False
    db.commit()
    assert decide(client, request_id, side=side, reason="x" * 501).status_code == (
        403 if side == "SOURCE" else 409
    )
    assert decide(client, request_id, supervisor, side=side).status_code == 403


def test_supervisor_does_not_gain_head_nurse_event_or_leave_permissions(scene):
    from app.db.models import StaffUnavailability
    from app.domain.enums import AvailabilityReason

    db, client, (_, _, supervisor) = scene
    assert (
        client.post(
            "/events",
            headers=supervisor,
            json={
                "event_type": "PATIENT_SURGE",
                "shift_id": 1,
                "patient_count": 20,
            },
        ).status_code
        == 403
    )
    row = StaffUnavailability(
        staff_id=201, start_at=DEMO_NOW, reason=AvailabilityReason.UNPLANNED_LEAVE
    )
    db.add(row)
    db.flush()
    assert (
        client.patch(
            f"/unavailability/{row.id}",
            headers=supervisor,
            json={"end_at": (DEMO_NOW + timedelta(days=1)).isoformat()},
        ).status_code
        == 403
    )


def test_automatic_decisions_write_no_human_ward_rows(production_seeded):
    from app.services import auto_approval_service
    from tests.integration.test_auto_approval import queue

    db = production_seeded
    rows = queue(db)
    assert auto_approval_service.approve_due_requests(db).approval_ids == [row.id for row in rows]
    assert db.scalar(select(func.count()).select_from(ApprovalWardDecision)) == 0
    history = approval_service.list_auto_approved(db, role_id=2, home_ward_id=1)
    assert all(row.wards[0].status == "APPROVED" for row in history)


def test_transfer_cancelled_result_keeps_approval_and_accepts_historical_reason(scene):
    from app.domain.enums import EntityType
    from app.services import actor_service, audit_service

    db, _, (request_id, _, _) = scene
    request = db.get(ApprovalRequest, request_id)
    request.is_pending = False
    request.is_approved = True
    request.decided_at = DEMO_NOW
    audit_service.log(
        db,
        case_id=request.case_id,
        actor_id=actor_service.user_id(db, 900),
        action=AuditAction.TRANSFER_CHECK_FAILED,
        entity_type=EntityType.APPROVAL_REQUEST,
        entity_id=request.id,
        payload={
            "outreach_id": request.outreach_id,
            "reason": "LEGACY_REASON",
            "failed_rules": ["SHIFT_CONFLICT"],
        },
    )
    db.flush()
    result = approval_service.decision_result(
        db, request=request, case=db.get(StaffingCase, request.case_id)
    )
    assert result.is_approved is True and result.outcome.value == "TRANSFER_CANCELLED"
    assert result.reason == "LEGACY_REASON" and result.failed_rules == ["SHIFT_CONFLICT"]


def test_invalid_side_or_rejection_reason_writes_no_ward_decision(scene):
    db, client, (request_id, _, _) = scene
    assert decide(client, request_id, side="bad-side").status_code == 422
    assert decide(client, request_id, approved=False, reason="  ").status_code == 422
    assert db.scalar(select(func.count()).select_from(ApprovalWardDecision)) == 0
    assert db.get(ApprovalRequest, request_id).is_pending
