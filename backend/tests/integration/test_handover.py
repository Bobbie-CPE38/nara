"""H1: transactional snapshots, original-event provenance, reads and concurrent uniqueness."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text

from app.api.dependencies import get_db
from app.core import clock
from app.db.models import (
    AuditLog,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingEvent,
    StructuredHandover,
)
from app.db.session import SessionLocal
from app.domain.enums import (
    ActorName,
    AssignmentType,
    AuditAction,
    CandidateSource,
    EventStatus,
    EventType,
    HandoverReason,
    RosterStatus,
)
from app.main import app
from app.seed import load
from app.services import (
    actor_service,
    approval_service,
    auto_approval_service,
    handoff_service,
    handover_service,
    roster_service,
)
from tests.integration.case_rows import approval, make_case, short_case
from tests.integration.test_approval_decision import _make_request
from tests.integration.test_auto_approval import queue
from tests.integration.test_execute_assignment import _move


def created(db):
    case, items = short_case(db)
    request = approval(db, case, items[201], approved=True)
    assignment = roster_service.create_replacement(db, case, approval=request)
    handover = db.scalars(select(StructuredHandover)).one()
    return case, assignment, handover


def test_snapshot_is_database_only_and_immutable(production_seeded):
    db = production_seeded
    case, row, handover = created(db)
    content = handover.content
    assert set(content) == {
        "version",
        "shift",
        "cover_start_at",
        "cover_end_at",
        "reason",
        "patient_count",
        "requirement",
        "co_workers",
        "case_id",
    }
    assert content["version"] == 1 and content["case_id"] == case.id
    assert content["reason"] == "UNPLANNED_LEAVE"
    shift = db.get(Shift, case.shift_id)
    assert content["cover_start_at"] == shift.start_at.astimezone(clock.APP_TIMEZONE).isoformat()
    assert content["cover_end_at"] == shift.end_at.astimezone(clock.APP_TIMEZONE).isoformat()
    assert content["shift"]["ward_id"] == shift.ward_id
    assert content["patient_count"] == shift.patient_count
    assert {c["staff_id"] for c in content["co_workers"]} == {101, 102, 103, 104}
    assert all(c["name"] and c["role_name"] for c in content["co_workers"])
    assert content["requirement"]["roles"] and content["requirement"]["skills"]
    shift.patient_count += 10
    db.get(Staff, 101).first_name = "changed"
    db.flush()
    again = handover_service.ensure(
        db, case=case, assignment=row, actor_id=actor_service.component_id(db, ActorName.SYSTEM)
    )
    assert again.id == handover.id and again.content == content
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.HANDOVER_GENERATED)
        )
        == 1
    )


@pytest.mark.parametrize("reason", list(HandoverReason))
def test_reason_uses_the_threshold_passing_event_not_lowest_event_id(production_seeded, reason):
    db = production_seeded
    case, items = short_case(db)
    opened = db.scalars(
        select(AuditLog).where(
            AuditLog.case_id == case.id, AuditLog.action == AuditAction.CASE_OPENED
        )
    ).one()
    # The first event remains attached to the case but did not open it (Q42).
    later = StaffingEvent(
        case_id=case.id,
        shift_id=case.shift_id,
        event_type=EventType.STAFF_UNAVAILABLE
        if reason in (HandoverReason.UNPLANNED_LEAVE, HandoverReason.NO_SHOW)
        else EventType(reason.value),
        staff_id=105
        if reason
        in (
            HandoverReason.UNPLANNED_LEAVE,
            HandoverReason.NO_SHOW,
            HandoverReason.ASSIGNMENT_CANCELLED,
        )
        else None,
        occurred_at=clock.now(),
        processed_at=clock.now(),
        status=EventStatus.PROCESSED,
        payload={"reason": "NO_SHOW"} if reason == HandoverReason.NO_SHOW else {},
    )
    db.add(later)
    db.flush()
    opened.payload = {"event_id": later.id}
    request = approval(db, case, items[201], approved=True)
    roster_service.create_replacement(db, case, approval=request)
    assert db.scalars(select(StructuredHandover)).one().content["reason"] == reason.value


def test_missing_origin_rolls_back_assignment_and_handover(production_seeded):
    db = production_seeded
    case, items = short_case(db)
    request = approval(db, case, items[201], approved=True)
    db.execute(
        delete(AuditLog).where(
            AuditLog.case_id == case.id, AuditLog.action == AuditAction.CASE_OPENED
        )
    )
    with pytest.raises(ValueError, match="opening event"), db.begin_nested():
        roster_service.create_replacement(db, case, approval=request)
    assert db.scalar(select(func.count()).select_from(StructuredHandover)) == 0
    assert (
        db.scalar(
            select(RosterAssignment.id).where(
                RosterAssignment.staff_id == 201, RosterAssignment.shift_id == case.shift_id
            )
        )
        is None
    )


@pytest.mark.parametrize("missing_origin", [False, True])
def test_human_approval_and_d11_keep_handover_atomic(production_seeded, missing_origin):
    db = production_seeded
    request = _make_request(db)
    if missing_origin:
        db.execute(
            delete(AuditLog).where(
                AuditLog.case_id == request.case_id, AuditLog.action == AuditAction.CASE_OPENED
            )
        )
    db.commit()
    decided, case = approval_service.decide(
        db,
        approval_id=request.id,
        staff_id=900,
        role_id=2,
        home_ward_id=1,
        actor_id=actor_service.user_id(db, 900),
        approved=True,
    )
    assert decided.is_approved is True
    assert case.status.value == ("FAILED" if missing_origin else "RESOLVED")
    snapshots = list(db.scalars(select(StructuredHandover)))
    assert len(snapshots) == (0 if missing_origin else 1)
    if missing_origin:
        assert (
            db.scalar(
                select(RosterAssignment.id).where(
                    RosterAssignment.staff_id == 201, RosterAssignment.shift_id == case.shift_id
                )
            )
            is None
        )
        assert (
            db.scalar(
                select(AuditLog.id).where(
                    AuditLog.case_id == case.id, AuditLog.action == AuditAction.WORKFLOW_FAILED
                )
            )
            is not None
        )


def test_audit_failure_rolls_back_the_assignment_too(production_seeded):
    db = production_seeded
    case, items = short_case(db)
    request = approval(db, case, items[201], approved=True)
    with (
        pytest.raises(RuntimeError, match="audit failed"),
        db.begin_nested(),
        patch(
            "app.services.handover_service.audit_service.log",
            side_effect=RuntimeError("audit failed"),
        ),
    ):
        roster_service.create_replacement(db, case, approval=request)
    assert db.scalar(select(func.count()).select_from(StructuredHandover)) == 0
    assert (
        db.scalar(
            select(RosterAssignment.id).where(
                RosterAssignment.staff_id == 201, RosterAssignment.shift_id == case.shift_id
            )
        )
        is None
    )


@pytest.mark.parametrize("replacement", [False, True])
def test_late_arrival_seam_creates_handover_only_for_a_replacement(production_seeded, replacement):
    db = production_seeded
    actor = actor_service.component_id(db, ActorName.SYSTEM)
    if replacement:
        case, original, old = created(db)
    else:
        original = db.scalars(
            select(RosterAssignment).where(
                RosterAssignment.staff_id == 101, RosterAssignment.shift_id == 1
            )
        ).one()
    original.status = RosterStatus.CANCELLED
    shift = db.get(Shift, original.shift_id)
    arrived = shift.start_at + timedelta(hours=1)
    new = roster_service.restore_late_arrival(
        db, original=original, check_in_at=arrived, actor_id=actor
    )
    assert new.actual_start_at == arrived and new.assignment_type == original.assignment_type
    assert new.candidate_source == original.candidate_source
    snapshots = handover_service.list_handovers(db, staff_id=original.staff_id)
    assert len(snapshots) == (2 if replacement else 0)
    if replacement:
        assert snapshots[0].roster_assignment_id == new.id and snapshots[0].active
        assert (
            snapshots[0].content["cover_start_at"]
            == arrived.astimezone(clock.APP_TIMEZONE).isoformat()
        )
        assert snapshots[1].handover_id == old.id and not snapshots[1].active


def test_failed_transfer_handover_rolls_back_source_cut_and_destination(production_seeded):
    db = production_seeded
    case, request, source = _move(db)
    original_id = source.id
    shift = db.get(Shift, case.shift_id)
    moved_at = shift.start_at + timedelta(hours=1)
    with (
        pytest.raises(RuntimeError, match="audit failed"),
        db.begin_nested(),
        patch(
            "app.services.handover_service.audit_service.log",
            side_effect=RuntimeError("audit failed"),
        ),
    ):
        roster_service.create_transfer(db, case, approval=request, transfer_at=moved_at)
    db.expire_all()
    original = db.get(RosterAssignment, original_id)
    assert original.status == RosterStatus.ASSIGNED and original.actual_end_at is None
    assert db.scalar(select(StructuredHandover.id)) is None
    assert (
        db.scalar(
            select(RosterAssignment.id).where(
                RosterAssignment.transferred_from_assignment_id == original_id
            )
        )
        is None
    )


def test_transfer_chain_has_new_handover_and_hides_source_at_effective_end(production_seeded):
    db = production_seeded
    case, request, source = _move(db)
    shift = db.get(Shift, case.shift_id)
    at = shift.start_at + timedelta(hours=1)
    clock.set_time(at)
    row, _ = roster_service.create_transfer(db, case, approval=request, transfer_at=at)
    assert len(handover_service.list_handovers(db, staff_id=row.staff_id)) == 1
    # Continue to a third ward/shift using the same central assignment writer.
    other_shift = db.get(Shift, 2)
    other_case = make_case(db, shift_id=other_shift.id)
    moved_at = at + timedelta(minutes=30)
    row.actual_end_at = moved_at
    roster_service.create_assignment(
        db,
        case=other_case,
        shift=other_shift,
        staff_id=row.staff_id,
        candidate_source=CandidateSource.CROSS_WARD,
        actual_start_at=moved_at,
        transferred_from_assignment_id=row.id,
    )
    clock.set_time(moved_at)
    views = handover_service.list_handovers(db, staff_id=row.staff_id)
    assert len(views) == 2 and views[0].active and not views[1].active
    assert db.get(RosterAssignment, row.id).status == RosterStatus.ASSIGNED
    assert source.id not in {v.roster_assignment_id for v in views}


def test_auto_approval_generates_one_handover_per_assignment(production_seeded):
    db = production_seeded
    requests = queue(db)
    assert auto_approval_service.approve_due_requests(db).approval_ids == [r.id for r in requests]
    snapshots = list(db.scalars(select(StructuredHandover)))
    assert len(snapshots) == len(requests)
    assert len({h.roster_assignment_id for h in snapshots}) == len(requests)
    assert auto_approval_service.approve_due_requests(db).approval_ids == []
    assert db.scalar(select(func.count()).select_from(StructuredHandover)) == len(requests)


def test_manual_assignment_generates_handover_with_human_actor(production_seeded):
    from app.domain.enums import CaseStatus

    db = production_seeded
    case, _ = short_case(db, status=CaseStatus.MANUAL_HANDOFF)
    actor = actor_service.user_id(db, 900)
    result = handoff_service.assign(
        db,
        case_id=case.id,
        staff_id=201,
        assigned_by=900,
        role_id=2,
        home_ward_id=1,
        actor_id=actor,
    )
    snapshot = db.scalars(select(StructuredHandover)).one()
    assert snapshot.roster_assignment_id == result.assignment_id
    log = db.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.HANDOVER_GENERATED)
    ).one()
    assert log.actor_id == actor


def test_nurse_and_case_api_share_views_and_keep_history(production_seeded):
    db = production_seeded
    case, row, handover = created(db)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            assert client.get("/me/handovers").status_code == 401
            assert (
                client.get("/me/handovers?staff_id=201", headers={"X-Demo-User": "202"}).json()
                == []
            )
            mine = client.get("/me/handovers", headers={"X-Demo-User": "201"}).json()
            assert mine[0]["handover_id"] == handover.id and mine[0]["active"]
            assert client.get(f"/cases/{case.id}").json()["handovers"] == mine
            clock.set_time(db.get(Shift, row.shift_id).end_at)
            history = client.get("/me/handovers", headers={"X-Demo-User": "201"}).json()
            assert not history[0]["active"] and history[0]["content"] == mine[0]["content"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_two_connections_generate_one_handover_and_audit(frozen_clock, restore_empty_database):
    with SessionLocal() as db:
        load(db)
        case = make_case(db)
        # An already-created destination row, just before snapshot generation.
        row = RosterAssignment(
            staff_id=201,
            shift_id=case.shift_id,
            status=RosterStatus.ASSIGNED,
            assignment_type=AssignmentType.REPLACEMENT,
            candidate_source=CandidateSource.SAME_WARD,
        )
        db.add(row)
        db.flush()
        actor = actor_service.component_id(db, ActorName.SYSTEM)
        case_id, row_id = case.id, row.id
        db.commit()
    barrier = threading.Barrier(2)

    def work():
        with SessionLocal() as db:
            db.execute(text("SET LOCAL statement_timeout = '5s'"))
            case = db.get(StaffingCase, case_id)
            row = db.get(RosterAssignment, row_id)
            barrier.wait(timeout=5)
            result = handover_service.ensure(db, case=case, assignment=row, actor_id=actor)
            id = result.id
            db.commit()
            return id

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(work), pool.submit(work)
        assert a.result(timeout=10) == b.result(timeout=10)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(StructuredHandover)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.HANDOVER_GENERATED)
            )
            == 1
        )
