"""Round 6 PR EV9 (docs/workflow.md 6.39): auto-approval per ward side and the Supervisor queue.

`build()` of the two-ward tests gives one move: 201 leaves a shift of a new ward (the SOURCE,
with its own head nurse) for the night shift of ICU (the DESTINATION, head nurse 900). Each
test makes the queue it is about go over its cap and checks which sides the job approves.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.api.dependencies import get_db
from app.core import clock
from app.core.constants import SUPERVISOR_ROLE
from app.db.models import (
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalWardDecision,
    AuditLog,
    CandidateItem,
    Role,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingRequirement,
)
from app.domain.enums import (
    ActorName,
    ApprovalMode,
    ApprovalSide,
    ApproverCapacity,
    AssignmentType,
    AuditAction,
    CandidateSource,
    CaseStatus,
    RosterStatus,
    StaffStatus,
)
from app.main import app
from app.services import actor_service, approval_service, auto_approval_service
from tests.integration.conftest import DEMO_NOW
from tests.integration.test_approval_two_wards import build, decide, moved_rows
from tests.integration.test_auto_approval import queue


def policy(db, **values) -> None:
    row = db.scalar(select(ApprovalPolicy))
    for name, value in values.items():
        setattr(row, name, value)
    db.commit()


def sides(db, request_id):
    """(side, mode, basis, queue, cap, approvers, approver) of each decided side."""
    return {
        row.side: (
            row.approval_mode,
            row.decided_as,
            row.queue_count,
            row.queue_cap,
            row.queue_approver_count,
            row.approver_id,
        )
        for row in db.scalars(
            select(ApprovalWardDecision).where(
                ApprovalWardDecision.approval_request_id == request_id
            )
        )
    }


def deactivate(db, *staff_ids) -> None:
    for staff_id in staff_ids:
        db.get(Staff, staff_id).status = StaffStatus.INACTIVE
    db.commit()


def supervisors(db) -> list[int]:
    return list(
        db.scalars(
            select(Staff.id)
            .join(Role, Role.id == Staff.role_id)
            .where(Role.name == SUPERVISOR_ROLE, Staff.status == StaffStatus.ACTIVE)
        )
    )


@pytest.fixture
def move(production_seeded):
    db = production_seeded
    request_id, source_headers, supervisor_headers = build(db)
    source_head = int(source_headers["X-Demo-User"])
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield db, client, request_id, source_head, source_headers
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_only_the_source_queue_over_its_cap_approves_only_the_source(move):
    db, _, request_id, source_head, _ = move
    # No active head nurse in the source ward: its cap is 0 and its queue is 1
    deactivate(db, source_head)
    assert auto_approval_service.approve_due_requests(db).approval_ids == [request_id]
    request = db.get(ApprovalRequest, request_id)
    assert request.is_pending and request.approval_mode == ApprovalMode.MANUAL
    assert sides(db, request_id) == {
        ApprovalSide.SOURCE: (ApprovalMode.AUTO, ApproverCapacity.HEAD_NURSE, 1, 0, 0, None)
    }
    audit = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.APPROVAL_WARD_APPROVED))
    assert audit.actor_id == actor_service.component_id(db, ActorName.SYSTEM)
    assert audit.payload | {"ward_id": 0} == {
        "approval_id": request_id,
        "ward_id": 0,
        "side": "SOURCE",
        "decided_as": "HEAD_NURSE",
        "approval_mode": "AUTO",
        "basis": "HEAD_NURSE_QUEUE",
        "pending_count": 1,
        "approver_count": 0,
        "cap": 0,
    }
    # Nobody moved: the destination still waits for its head nurse
    assert moved_rows(db) == []
    assert auto_approval_service.approve_due_requests(db).approval_ids == []


def test_only_the_destination_queue_over_its_cap_approves_only_the_destination(move):
    db, _, request_id, _, _ = move
    deactivate(db, 900)
    assert auto_approval_service.approve_due_requests(db).approval_ids == [request_id]
    assert db.get(ApprovalRequest, request_id).is_pending
    assert list(sides(db, request_id)) == [ApprovalSide.DESTINATION]
    assert moved_rows(db) == []


def test_both_queues_over_their_caps_approve_both_sides_and_move_the_person(move):
    db, _, request_id, _, _ = move
    policy(db, incoming_count=0)
    assert auto_approval_service.approve_due_requests(db).approval_ids == [request_id]
    request = db.get(ApprovalRequest, request_id)
    assert not request.is_pending and request.is_approved
    assert request.approval_mode == ApprovalMode.AUTO and request.approver_id is None
    assert {side: row[0] for side, row in sides(db, request_id).items()} == {
        ApprovalSide.SOURCE: ApprovalMode.AUTO,
        ApprovalSide.DESTINATION: ApprovalMode.AUTO,
    }
    assert len(moved_rows(db)) == 1
    assert db.get(StaffingCase, request.case_id).status == CaseStatus.RESOLVED


def test_a_person_approves_one_side_and_the_system_the_other(move):
    db, client, request_id, source_head, _ = move
    assert decide(client, request_id).status_code == 200
    deactivate(db, source_head)
    assert auto_approval_service.approve_due_requests(db).approval_ids == [request_id]
    request = db.get(ApprovalRequest, request_id)
    assert not request.is_pending and request.is_approved and request.approver_id is None
    decided = sides(db, request_id)
    assert decided[ApprovalSide.DESTINATION][0] == ApprovalMode.MANUAL
    assert decided[ApprovalSide.DESTINATION][5] == 900
    assert decided[ApprovalSide.SOURCE][0] == ApprovalMode.AUTO
    assert len(moved_rows(db)) == 1

    # The case page names the person for one side and no person for the other
    overview = client.get(f"/cases/{request.case_id}", headers={"X-Demo-User": "900"}).json()[
        "overview"
    ]
    by_side = {side["side"]: side for side in overview["requests"][0]["sides"]}
    assert by_side["DESTINATION"]["status"] == "APPROVED"
    assert by_side["DESTINATION"]["by"]["staff_id"] == 900
    assert by_side["DESTINATION"]["auto"] is None
    assert by_side["SOURCE"]["status"] == "AUTO_APPROVED"
    assert by_side["SOURCE"]["by"] is None
    assert by_side["SOURCE"]["auto"] == {
        "basis": "HEAD_NURSE_QUEUE",
        "queue_count": 1,
        "cap": 0.0,
        "approver_count": 0,
    }
    kinds = [(row["kind"], row["side"], row["by"]["staff_id"]) for row in overview["decisions"]]
    assert ("APPROVED", "DESTINATION", 900) in kinds
    assert ("AUTO_APPROVED", "SOURCE", None) in kinds
    # One line per side: the request's final audit is not listed a second time
    assert sum(kind == "AUTO_APPROVED" for kind, _, _ in kinds) == 1


def test_a_rejected_side_is_never_approved_by_the_other_queue(move):
    db, client, request_id, _, source_headers = move
    response = decide(client, request_id, source_headers, approved=False, reason="Needed here")
    assert response.status_code == 200
    policy(db, incoming_count=0)
    assert auto_approval_service.approve_due_requests(db).approval_ids == []
    assert db.get(ApprovalRequest, request_id).is_approved is False
    assert [row[0] for row in sides(db, request_id).values()] == [ApprovalMode.MANUAL]
    assert moved_rows(db) == []


def test_a_move_that_would_leave_the_source_short_is_left_for_a_person(move):
    db, _, request_id, _, _ = move
    item = db.get(CandidateItem, db.get(ApprovalRequest, request_id).candidate_item_id)
    source_shift = db.scalar(
        select(RosterAssignment.shift_id).where(RosterAssignment.id == item.source_assignment_id)
    )
    # Two of two are needed on the source shift now: moving 201 would leave one
    requirement = db.scalar(
        select(StaffingRequirement).where(StaffingRequirement.shift_id == source_shift)
    )
    requirement.minimum_staff = 2
    requirement.required_staff = 2
    policy(db, incoming_count=0)
    assert auto_approval_service.approve_due_requests(db).approval_ids == []
    assert db.get(ApprovalRequest, request_id).is_pending
    assert sides(db, request_id) == {}
    assert moved_rows(db) == []


def test_supervisor_queue_waits_for_supervisor_time_and_its_own_cap(move):
    db, _, request_id, _, _ = move
    policy(db, supervisor_incoming_count=0)
    # Before supervisor_from the Supervisor may not decide: not in that queue
    assert auto_approval_service.approve_due_requests(db).approval_ids == []
    clock.set_time(DEMO_NOW + timedelta(seconds=600))
    policy(db, supervisor_incoming_count=1)
    # One request against a cap of one: equal is not over
    assert auto_approval_service.approve_due_requests(db).approval_ids == []
    policy(db, supervisor_incoming_count=0)
    assert auto_approval_service.approve_due_requests(db).approval_ids == [request_id]
    count = len(supervisors(db))
    assert count >= 1
    assert sides(db, request_id) == {
        side: (ApprovalMode.AUTO, ApproverCapacity.SUPERVISOR, 1, 0, count, None)
        for side in (ApprovalSide.SOURCE, ApprovalSide.DESTINATION)
    }
    assert len(moved_rows(db)) == 1


def test_supervisor_queue_uses_ratio_times_active_supervisors(move):
    db, _, request_id, _, _ = move
    clock.set_time(DEMO_NOW + timedelta(seconds=600))
    # 0.5 per active Supervisor, at most 10: with two or more Supervisors the cap is at least 1
    count = len(supervisors(db))
    policy(db, supervisor_ratio=Decimal("0.5"))
    expected = [request_id] if Decimal("0.5") * count < 1 else []
    assert auto_approval_service.approve_due_requests(db).approval_ids == expected


def test_no_active_supervisor_never_approves_by_the_supervisor_queue(move):
    db, _, request_id, _, _ = move
    deactivate(db, *supervisors(db))
    clock.set_time(DEMO_NOW + timedelta(seconds=600))
    policy(db, supervisor_incoming_count=0, supervisor_ratio=0)
    assert auto_approval_service.approve_due_requests(db).approval_ids == []
    assert db.get(ApprovalRequest, request_id).is_pending


def test_a_side_its_ward_queue_covers_keeps_that_reason(move):
    db, _, request_id, source_head, _ = move
    deactivate(db, source_head)
    clock.set_time(DEMO_NOW + timedelta(seconds=600))
    policy(db, supervisor_incoming_count=0)
    assert auto_approval_service.approve_due_requests(db).approval_ids == [request_id]
    decided = sides(db, request_id)
    assert decided[ApprovalSide.SOURCE][1] == ApproverCapacity.HEAD_NURSE
    assert decided[ApprovalSide.DESTINATION][1] == ApproverCapacity.SUPERVISOR


def test_each_ward_counts_its_own_side_once(production_seeded):
    db = production_seeded
    request_id, _, _ = build(db)
    rows = queue(db, (CandidateSource.SAME_WARD,) * 2)
    # Ward 1 waits for three requests (two of its own and the move's destination), cap 2
    result = auto_approval_service.approve_due_requests(db)
    # rows[0] is 201 again, who the move puts on the night shift first: the hard rules,
    # checked again under the locks, leave that one to a person instead of a double booking
    assert result.approval_ids == [request_id, rows[1].id]
    assert db.get(ApprovalRequest, rows[0].id).is_pending
    decided = sides(db, request_id)
    assert list(decided) == [ApprovalSide.DESTINATION]
    assert decided[ApprovalSide.DESTINATION][2:4] == (3, 2)
    # The source ward waits for one request against its own cap of 2: still a person's
    assert db.get(ApprovalRequest, request_id).is_pending


def test_a_move_within_one_ward_counts_once_in_that_ward(production_seeded):
    db = production_seeded
    request_id, _, _ = build(db)
    item = db.get(CandidateItem, db.get(ApprovalRequest, request_id).candidate_item_id)
    source_shift = db.scalar(
        select(Shift)
        .join(RosterAssignment, RosterAssignment.shift_id == Shift.id)
        .where(RosterAssignment.id == item.source_assignment_id)
    )
    source_shift.ward_id = 1
    db.commit()
    rows = queue(db, (CandidateSource.SAME_WARD,) * 2)
    result = auto_approval_service.approve_due_requests(db)
    # Three requests in ward 1, not four, although the move needs ward 1 twice (rows[0] is
    # 201 again, already moved onto the night shift, so it stays with a person)
    assert result.approval_ids == [request_id, rows[1].id]
    decided = sides(db, request_id)
    assert {side: row[2:4] for side, row in decided.items()} == {
        ApprovalSide.SOURCE: (3, 2),
        ApprovalSide.DESTINATION: (3, 2),
    }


def test_auto_history_lists_partly_and_fully_approved_requests(move):
    db, client, request_id, _, _ = move
    # The destination's queue is over its cap (900 inactive): its side is the system's
    deactivate(db, 900)
    auto_approval_service.approve_due_requests(db)
    supervisor = {"X-Demo-User": str(supervisors(db)[0])}
    history = client.get("/approvals/auto", headers=supervisor).json()
    assert [(row["id"], row["is_pending"]) for row in history] == [(request_id, True)]
    assert {
        ward["side"]: (ward["status"], ward["approval_mode"]) for ward in history[0]["wards"]
    } == {
        "DESTINATION": ("APPROVED", "AUTO"),
        "SOURCE": ("PENDING", None),
    }


def test_a_head_nurse_reads_only_the_automatic_side_of_their_own_ward(move):
    db, client, request_id, source_head, source_headers = move
    # The source ward's queue is over its cap: the system approves the source side only
    deactivate(db, source_head)
    auto_approval_service.approve_due_requests(db)
    # The destination head nurse sees the request to decide, but not the other ward's side
    assert client.get("/approvals/auto", headers={"X-Demo-User": "900"}).json() == []
    pending = client.get("/approvals", headers={"X-Demo-User": "900"}).json()
    assert [row["id"] for row in pending] == [request_id]
    db.get(Staff, source_head).status = StaffStatus.ACTIVE
    db.commit()
    own = client.get("/approvals/auto", headers=source_headers).json()
    assert [row["id"] for row in own] == [request_id]
    assert [(w["side"], w["approval_mode"]) for w in own[0]["wards"]] == [("SOURCE", "AUTO")]
    assert decide(client, request_id).status_code == 200
    own = client.get("/approvals/auto", headers=source_headers).json()
    assert [(row["id"], row["is_pending"]) for row in own] == [(request_id, False)]


def test_automatic_side_requires_the_locked_batch_for_that_side(move):
    db, _, request_id, _, _ = move
    with pytest.raises(approval_service.ApproverRoleError):
        approval_service.decide_automatic(
            db,
            approval_id=request_id,
            side=ApprovalSide.SOURCE,
            batch=None,
            notifications=[],
        )


def test_emergency_short_of_fourteen_reports_each_group_and_side(production_seeded):
    """An Emergency-like ward short of 14 with many answers: what the job decides, by queue.

    Ward 1 has one head nurse (cap 2) and 14 accepted requests of every kind: 8 of its own
    nurses, 2 from the Float Pool, 2 free nurses of other wards, and 2 moves off another
    ward's shift. That ward's queue (14 > 2) approves every destination side. The source
    ward waits for 2 moves against its own cap of 2, so those two stay with its head nurse
    until a person decides or the Supervisor's time comes.
    """
    from tests.integration.case_rows import approval, make_case, make_plan, record_gap
    from tests.integration.test_approval_decision import _add_other_ward_head_nurse
    from tests.integration.test_cross_ward_pool import _rn

    db = production_seeded
    destination = Shift(
        ward_id=1,
        patient_count=14,
        start_at=DEMO_NOW + timedelta(hours=2),
        end_at=DEMO_NOW + timedelta(hours=10),
        shift_type=destination_type(db),
        is_active=True,
    )
    db.add(destination)
    db.flush()
    db.add(StaffingRequirement(shift_id=destination.id, required_staff=14, minimum_staff=14))
    db.flush()
    case = make_case(db, CaseStatus.WAITING_APPROVAL, shift_id=destination.id)
    record_gap(db, case)
    source_ward, _ = _add_other_ward_head_nurse(db)
    source = Shift(
        ward_id=source_ward,
        patient_count=1,
        start_at=destination.start_at,
        end_at=destination.end_at,
        shift_type=destination.shift_type,
        is_active=True,
    )
    db.add(source)
    db.flush()
    db.add(StaffingRequirement(shift_id=source.id, required_staff=0, minimum_staff=0))
    groups = {
        CandidateSource.SAME_WARD: [_rn(db, 1) for _ in range(8)],
        CandidateSource.FLOAT_POOL: [_rn(db, 1) for _ in range(2)],
        CandidateSource.CROSS_WARD: [_rn(db, source_ward) for _ in range(2)],
        "MOVE": [_rn(db, source_ward) for _ in range(2)],
    }
    staff = [staff_id for ids in groups.values() for staff_id in ids]
    items = make_plan(db, case, tuple(staff))
    requests: dict[object, list[int]] = {}
    for group, ids in groups.items():
        for staff_id in ids:
            item = items[staff_id]
            if group == "MOVE":
                row = RosterAssignment(
                    staff_id=staff_id,
                    shift_id=source.id,
                    status=RosterStatus.ASSIGNED,
                    assignment_type=AssignmentType.REGULAR,
                )
                db.add(row)
                db.flush()
                item.source = CandidateSource.CROSS_WARD
                item.source_assignment_id = row.id
            else:
                item.source = group
            requests.setdefault(group, []).append(approval(db, case, item).id)
    db.commit()

    result = auto_approval_service.approve_due_requests(db)
    assert result.failed_ward_ids == set()
    decided = list(db.scalars(select(ApprovalWardDecision)))
    by_group: dict[tuple[object, str, str], int] = {}
    for row in decided:
        group = next(name for name, ids in requests.items() if row.approval_request_id in ids)
        key = (group, row.side.value, row.decided_as.value)
        by_group[key] = by_group.get(key, 0) + 1
        assert row.approval_mode == ApprovalMode.AUTO and row.queue_count == 14
        assert row.queue_cap == 2
    assert by_group == {
        (CandidateSource.SAME_WARD, "DESTINATION", "HEAD_NURSE"): 8,
        (CandidateSource.FLOAT_POOL, "DESTINATION", "HEAD_NURSE"): 2,
        (CandidateSource.CROSS_WARD, "DESTINATION", "HEAD_NURSE"): 2,
        ("MOVE", "DESTINATION", "HEAD_NURSE"): 2,
    }
    # The 12 without a source shift are on the shift; the 2 moves wait for their source ward
    assigned = set(
        db.scalars(
            select(RosterAssignment.staff_id).where(
                RosterAssignment.shift_id == destination.id,
                RosterAssignment.status == RosterStatus.ASSIGNED,
            )
        )
    )
    assert assigned == set(staff) - set(groups["MOVE"])
    assert all(db.get(ApprovalRequest, request_id).is_pending for request_id in requests["MOVE"])


def destination_type(db):
    return db.get(Shift, 1).shift_type


@pytest.fixture
def committed_move(frozen_clock):
    """A move with real commits, so two connections can race for it."""
    from app.db.base import Base
    from app.db.session import SessionLocal, engine
    from app.seed import load

    with SessionLocal() as db:
        load(db)
        request_id, _, _ = build(db)
        policy(db, incoming_count=0)
    try:
        yield request_id
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


@pytest.mark.parametrize("human", [False, True], ids=["job-job", "job-human"])
def test_competing_connections_decide_each_side_once_and_move_once(committed_move, human):
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
                    approval_id=committed_move,
                    staff_id=staff.id,
                    role_id=staff.role_id,
                    home_ward_id=staff.home_ward_id,
                    actor_id=actor_id,
                    approved=True,
                )
                return [committed_move]
            except approval_service.ApprovalNotPendingError:
                db.rollback()
                return []

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_job), pool.submit(run_human if human else run_job)]
        [future.result(timeout=30) for future in futures]
    with SessionLocal() as db:
        request = db.get(ApprovalRequest, committed_move)
        decisions = list(
            db.scalars(
                select(ApprovalWardDecision).where(
                    ApprovalWardDecision.approval_request_id == committed_move
                )
            )
        )
        # Each side once, by whoever came first; the move itself once
        assert sorted(row.side for row in decisions) == [
            ApprovalSide.DESTINATION,
            ApprovalSide.SOURCE,
        ]
        assert not request.is_pending and request.is_approved
        assert len(moved_rows(db)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.APPROVAL_APPROVED)
            )
            == 1
        )
