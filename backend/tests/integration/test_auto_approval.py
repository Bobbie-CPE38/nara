"""Round 4 auto approval: locked ward snapshots, normal decisions, no new migration."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core import clock
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    Shift,
    Staff,
    StaffingCase,
    StaffingRequirement,
)
from app.domain.enums import (
    ActorName,
    ApprovalMode,
    AuditAction,
    CandidateSource,
    CaseStatus,
    ShiftType,
    StaffStatus,
)
from app.main import app
from app.services import actor_service, approval_service, auto_approval_service, roster_service
from tests.integration.case_rows import approval, make_case, make_plan, record_gap
from tests.integration.conftest import DEMO_NOW


def queue(db: Session, sources=(CandidateSource.SAME_WARD,) * 3):
    requests = []
    for i, source in enumerate(sources):
        shift = Shift(
            ward_id=1,
            patient_count=1,
            start_at=DEMO_NOW + timedelta(hours=2),
            end_at=DEMO_NOW + timedelta(hours=10),
            shift_type=ShiftType.NIGHT,
            is_active=True,
        )
        db.add(shift)
        db.flush()
        db.add(StaffingRequirement(shift_id=shift.id, required_staff=1, minimum_staff=1))
        db.flush()
        case = make_case(db, CaseStatus.WAITING_APPROVAL, shift_id=shift.id)
        record_gap(db, case)
        item = make_plan(db, case, (201 + i,))[201 + i]
        item.source = source
        requests.append(approval(db, case, item))
    db.commit()
    return requests


def test_overloaded_snapshot_drains_all_requests_not_just_the_excess(production_seeded):
    db = production_seeded
    requests = queue(db)
    result = auto_approval_service.approve_due_requests(db)
    assert result.failed_ward_ids == set()
    assert result.approval_ids == [r.id for r in requests]
    for row in requests:
        db.refresh(row)
        assert row.approval_mode == ApprovalMode.AUTO
        assert row.approver_id is None and row.is_approved is True and not row.is_pending
        assert db.get(StaffingCase, row.case_id).status == CaseStatus.RESOLVED
    audits = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.action == AuditAction.APPROVAL_APPROVED)
            .order_by(AuditLog.id)
        )
    )
    assert len(audits) == 3
    assert all(row.actor_id == actor_service.component_id(db, ActorName.SYSTEM) for row in audits)
    assert all(
        row.payload["pending_count"] == 3
        and row.payload["approver_count"] == 1
        and row.payload["cap"] == 2
        and row.payload["approval_mode"] == "AUTO"
        for row in audits
    )
    assert auto_approval_service.approve_due_requests(db).approval_ids == []


def test_queue_equal_to_capacity_is_left_for_people(production_seeded):
    db = production_seeded
    rows = queue(db, (CandidateSource.SAME_WARD,) * 2)
    assert auto_approval_service.approve_due_requests(db).approval_ids == []
    assert all(db.get(ApprovalRequest, row.id).is_pending for row in rows)


def test_manual_only_requests_count_toward_threshold_but_are_never_approved(production_seeded):
    db = production_seeded
    rows = queue(
        db, (CandidateSource.SAME_WARD, CandidateSource.CROSS_WARD, CandidateSource.FLOAT_POOL)
    )
    assert auto_approval_service.approve_due_requests(db).approval_ids == [rows[0].id]
    assert all(db.get(ApprovalRequest, row.id).is_pending for row in rows[1:])


def test_recorded_source_prevents_auto_even_with_same_ward_source(production_seeded):
    from app.db.models import RosterAssignment

    db = production_seeded
    rows = queue(db)
    item = db.get(CandidateItem, rows[0].candidate_item_id)
    item.source_assignment_id = db.scalar(
        select(RosterAssignment.id).where(RosterAssignment.staff_id == 202).limit(1)
    )
    db.commit()
    result = auto_approval_service.approve_due_requests(db)
    assert rows[0].id not in result.approval_ids
    assert db.get(ApprovalRequest, rows[0].id).is_pending
    assert len(result.approval_ids) == 2


def test_no_active_head_nurse_means_zero_capacity(production_seeded):
    db = production_seeded
    rows = queue(db, (CandidateSource.SAME_WARD,))
    db.get(Staff, 900).status = StaffStatus.INACTIVE
    db.commit()
    assert auto_approval_service.approve_due_requests(db).approval_ids == [rows[0].id]


def test_expired_requests_are_not_auto_approved(production_seeded):
    db = production_seeded
    rows = queue(db)
    clock.set_time(DEMO_NOW + timedelta(seconds=900))
    assert auto_approval_service.approve_due_requests(db).approval_ids == []
    assert all(db.get(ApprovalRequest, row.id).is_pending for row in rows)


def test_oldest_request_is_decided_first(production_seeded):
    db = production_seeded
    rows = queue(db)
    rows[-1].requested_at -= timedelta(seconds=30)
    db.commit()
    result = auto_approval_service.approve_due_requests(db)
    assert result.approval_ids == [rows[2].id, rows[0].id, rows[1].id]


def test_automatic_entry_point_requires_a_locked_batch(production_seeded):
    db = production_seeded
    rows = queue(db)
    with pytest.raises(approval_service.ApproverRoleError):
        approval_service.decide_automatic(
            db,
            approval_id=rows[0].id,
            batch=None,
            notifications=[],
        )


def test_d11_keeps_auto_decision_but_rolls_back_failed_assignment(production_seeded):
    db = production_seeded
    rows = queue(db)
    with patch.object(
        roster_service, "create_replacement", side_effect=RuntimeError("execution failed")
    ):
        result = auto_approval_service.approve_due_requests(db)
    assert len(result.approval_ids) == 3
    assert result.failed_ward_ids == set()
    assert all(db.get(ApprovalRequest, row.id).is_approved is True for row in rows)
    assert all(db.get(StaffingCase, row.case_id).status == CaseStatus.FAILED for row in rows)


def test_auto_history_is_readable_by_head_nurse_but_not_candidate(production_seeded):
    db = production_seeded
    rows = queue(db)
    auto_approval_service.approve_due_requests(db)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            response = client.get("/approvals/auto", headers={"X-Demo-User": "900"})
            assert response.status_code == 200
            assert [row["id"] for row in response.json()] == [r.id for r in reversed(rows)]
            assert all(row["decided_at"] == DEMO_NOW.isoformat() for row in response.json())
            assert client.get("/approvals/auto", headers={"X-Demo-User": "201"}).status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    "ratio,incoming,count,expected", [("2.5", 10, 2, 0), ("2.5", 10, 3, 3), ("10", 2, 3, 3)]
)
def test_capacity_keeps_fractional_ratio_and_applies_incoming_ceiling(
    production_seeded, ratio, incoming, count, expected
):
    from decimal import Decimal

    from app.db.models import ApprovalPolicy

    db = production_seeded
    rows = queue(db, (CandidateSource.SAME_WARD,) * count)
    policy = db.scalar(select(ApprovalPolicy))
    policy.ratio = Decimal(ratio)
    policy.incoming_count = incoming
    db.commit()
    result = auto_approval_service.approve_due_requests(db)
    assert len(result.approval_ids) == expected
    assert result.failed_ward_ids == set()
    assert sum(db.get(ApprovalRequest, row.id).is_pending for row in rows) == count - expected


def test_unexpected_batch_failure_rolls_back_all_decisions_and_retries_next_tick(production_seeded):
    db = production_seeded
    rows = queue(db)
    original = approval_service.decide_automatic
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("batch interrupted")
        return original(*args, **kwargs)

    with patch.object(approval_service, "decide_automatic", side_effect=fail_second):
        result = auto_approval_service.approve_due_requests(db)
    assert result.approval_ids == []
    assert result.failed_ward_ids == {1}
    assert all(db.get(ApprovalRequest, row.id).is_pending for row in rows)
    assert (
        list(db.scalars(select(AuditLog).where(AuditLog.action == AuditAction.APPROVAL_APPROVED)))
        == []
    )
    assert auto_approval_service.approve_due_requests(db).approval_ids == [row.id for row in rows]


@pytest.fixture
def committed_queue(frozen_clock):
    """Real commits and independent connections, isolated from the live demo DB."""
    from sqlalchemy import text

    from app.db.base import Base
    from app.db.session import SessionLocal, engine
    from app.seed import load

    with SessionLocal() as db:
        load(db)
        ids = [row.id for row in queue(db)]
    try:
        yield ids
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


@pytest.mark.parametrize("human", [False, True], ids=["job-job", "job-human"])
def test_competing_connections_serialize_the_ward_snapshot(committed_queue, human):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from app.db.session import SessionLocal

    barrier = threading.Barrier(2, timeout=10)

    def run_job():
        with SessionLocal() as db:
            barrier.wait()
            result = auto_approval_service.approve_due_requests(db)
            assert result.failed_ward_ids == set()
            return result.approval_ids

    def run_human():
        with SessionLocal() as db:
            staff = db.get(Staff, 900)
            actor_id = actor_service.user_id(db, staff.id)
            barrier.wait()
            try:
                approval_service.decide(
                    db,
                    approval_id=committed_queue[0],
                    staff_id=staff.id,
                    role_id=staff.role_id,
                    home_ward_id=staff.home_ward_id,
                    actor_id=actor_id,
                    approved=True,
                )
                return [committed_queue[0]]
            except approval_service.ApprovalNotPendingError:
                db.rollback()
                return []

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_job), pool.submit(run_human if human else run_job)]
        first, second = [future.result(timeout=20) for future in futures]
    assert len(first + second) == len(set(first + second))
    if human:
        assert (len(first), len(second)) in {(3, 0), (0, 1)}
    else:
        assert sorted(first + second) == committed_queue
    with SessionLocal() as db:
        audits = list(
            db.scalars(select(AuditLog).where(AuditLog.action == AuditAction.APPROVAL_APPROVED))
        )
        assert len(audits) == len(first + second)
        assert sum(
            db.get(ApprovalRequest, row_id).is_pending for row_id in committed_queue
        ) == 3 - len(audits)


def test_cancelled_offer_and_stopped_case_do_not_inflate_queue(production_seeded):
    from app.db.models import CandidateOutreach
    from app.domain.enums import OutreachStatus

    db = production_seeded
    rows = queue(db)
    db.get(CandidateOutreach, rows[0].outreach_id).status = OutreachStatus.CANCELLED
    db.get(StaffingCase, rows[1].case_id).status = CaseStatus.FAILED
    db.commit()
    assert auto_approval_service.approve_due_requests(db).approval_ids == []
    assert all(db.get(ApprovalRequest, row.id).is_pending for row in rows)


def test_history_is_ward_scoped_and_supervisor_can_read_all_wards(production_seeded):
    from app.db.models import Role, Ward

    db = production_seeded
    rows = queue(db)
    auto_approval_service.approve_due_requests(db)
    db.add(Ward(id=2, name="Other ward", is_active=True))
    supervisor = Role(id=99, name="SUPERVISOR")
    db.add(supervisor)
    db.flush()
    case = db.get(StaffingCase, rows[-1].case_id)
    db.get(Shift, case.shift_id).ward_id = 2
    db.commit()
    head_role = db.get(Staff, 900).role_id
    supervisor_role = db.scalar(select(Role.id).where(Role.name == "SUPERVISOR"))
    assert [
        row.id for row in approval_service.list_auto_approved(db, role_id=head_role, home_ward_id=1)
    ] == [rows[1].id, rows[0].id]
    assert [
        row.id
        for row in approval_service.list_auto_approved(db, role_id=supervisor_role, home_ward_id=1)
    ] == [row.id for row in reversed(rows)]


def test_history_is_newest_first_and_limited_to_fifty(production_seeded):
    db = production_seeded
    original = queue(db, (CandidateSource.SAME_WARD,))[0]
    rows = []
    for i in range(55):
        row = ApprovalRequest(
            case_id=original.case_id,
            candidate_item_id=original.candidate_item_id,
            outreach_id=original.outreach_id,
            required_approver_role=original.required_approver_role,
            approval_mode=ApprovalMode.AUTO,
            is_pending=False,
            is_approved=True,
            requested_at=DEMO_NOW,
            expires_at=original.expires_at,
            decided_at=DEMO_NOW + timedelta(seconds=i),
        )
        db.add(row)
        rows.append(row)
    db.commit()
    history = approval_service.list_auto_approved(
        db, role_id=db.get(Staff, 900).role_id, home_ward_id=1
    )
    assert [row.id for row in history] == [row.id for row in reversed(rows[5:])]


def test_foreign_case_notifications_run_after_outer_ward_commit(committed_queue):
    from app.db.models import Ward
    from app.db.session import SessionLocal

    notified = []

    def probe(_db, *, staff_id, own_case_id, additional_case_ids):
        # NOWAIT on another connection would fail if the batch retained its Ward lock.
        with SessionLocal() as other:
            other.scalars(select(Ward).where(Ward.id == 1).with_for_update(nowait=True)).one()
            assert all(
                not other.get(ApprovalRequest, row_id).is_pending for row_id in committed_queue
            )
        notified.append(own_case_id)

    with (
        SessionLocal() as db,
        patch.object(
            auto_approval_service.outreach_service, "recompute_affected_cases", side_effect=probe
        ),
    ):
        result = auto_approval_service.approve_due_requests(db)
    assert result.approval_ids == committed_queue
    assert len(notified) == 3


def test_timeout_job_never_times_out_an_automatically_decided_request(production_seeded):
    from app.services import approval_timeout_service

    db = production_seeded
    rows = queue(db)
    assert auto_approval_service.approve_due_requests(db).approval_ids == [row.id for row in rows]
    clock.set_time(max(row.expires_at for row in rows) + timedelta(seconds=1))
    assert approval_timeout_service.expire_due_approvals(db).approval_ids == []
    assert auto_approval_service.approve_due_requests(db).approval_ids == []
    for row in rows:
        db.refresh(row)
        assert row.is_approved is True
        assert row.is_timed_out is False
        assert row.is_pending is False
    actions = list(db.scalars(select(AuditLog.action)))
    assert actions.count(AuditAction.APPROVAL_APPROVED) == len(rows)
    assert AuditAction.APPROVAL_TIMEOUT not in actions


@pytest.mark.parametrize("route", ["/demo/clock/advance", "/internal/merge-windows/close-due"])
def test_due_work_routes_report_actual_auto_approvals(production_seeded, monkeypatch, route):
    from app.core.config import settings

    db = production_seeded
    rows = queue(db)
    monkeypatch.setattr(settings, "internal_job_secret", "test-auto-approval")
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            response = client.post(
                route,
                headers={"X-Internal-Secret": "test-auto-approval"},
                **({"json": {"seconds": 1}} if route.startswith("/demo") else {}),
            )
        assert response.status_code == 200
        assert response.json()["auto_approved_request_ids"] == [row.id for row in rows]
        assert response.json()["failed_auto_approval_ward_ids"] == []
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_job_result_preserves_failed_auto_approval_wards(production_seeded):
    from app.services import job_service

    with patch.object(
        auto_approval_service,
        "approve_due_requests",
        return_value=auto_approval_service.AutomaticApprovals([], {8, 2}),
    ):
        result = job_service.run_due_work(production_seeded)
    assert result.failed_auto_approval_ward_ids == [2, 8]


def test_failed_post_commit_recompute_is_explicitly_best_effort(production_seeded, caplog):
    db = production_seeded
    rows = queue(db)
    with patch.object(
        auto_approval_service.outreach_service,
        "recompute_affected_cases",
        side_effect=RuntimeError("post-commit error"),
    ):
        result = auto_approval_service.approve_due_requests(db)
    assert result.approval_ids == [row.id for row in rows]
    assert result.failed_ward_ids == set()
    assert all(db.get(ApprovalRequest, row.id).is_approved for row in rows)
    assert "no queued retry" in caplog.text
