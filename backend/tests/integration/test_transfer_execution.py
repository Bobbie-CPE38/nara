"""Execution of a whole-shift transfer (round 4 PR C2, docs/workflow.md 6.19).

The final approval moves the person, or refuses the move with TRANSFER_CHECK_FAILED
when the check at the real move fails. A refusal ends the request and the offer, and
the case goes on with a reserve or the next wave: it is never FAILED.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.api.dependencies import get_db
from app.core import clock
from app.db.base import Base
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    RosterAssignment,
    Shift,
    StaffingCase,
    StaffingRequirement,
    StaffingRequirementRole,
)
from app.db.session import SessionLocal, engine
from app.domain.constraints.codes import HardRuleCode
from app.domain.enums import (
    AssignmentType,
    AuditAction,
    CandidateSource,
    CaseStatus,
    OutreachStatus,
    RosterStatus,
)
from app.main import app
from app.seed import load
from app.services import outreach_service
from tests.integration.case_rows import (
    RN,
    approval,
    make_case,
    make_plan,
    offer,
    record_gap,
    short_case,
)
from tests.integration.conftest import DEMO_NOW
from tests.integration.test_approval_decision import _add_other_ward_head_nurse
from tests.integration.test_approval_two_wards import build, decide
from tests.integration.test_cross_ward_pool import _duty, _rn, _shift, _ward

TRANSFER_CANCELLED = "TRANSFER_CANCELLED"
FAR = timedelta(days=2)


@pytest.fixture
def scene(production_seeded):
    db = production_seeded
    request_id, source_headers, _ = build(db)
    # The decisions below move the clock past the request's own deadline
    request = db.get(ApprovalRequest, request_id)
    request.expires_at = DEMO_NOW + FAR
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield db, client, request_id, source_headers
    finally:
        app.dependency_overrides.pop(get_db, None)


def approve_both(client, request_id, source_headers):
    first = decide(client, request_id)
    assert first.json()["outcome"] == "WAITING_OTHER_WARD"
    return decide(client, request_id, source_headers)


def rows_of(db, staff_id=201):
    db.expire_all()
    return list(
        db.scalars(
            select(RosterAssignment)
            .where(RosterAssignment.staff_id == staff_id)
            .order_by(RosterAssignment.id)
        )
    )


def failure_audit(db):
    db.expire_all()
    return db.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.TRANSFER_CHECK_FAILED)
    ).one()


def assert_refused(db, request_id, response, reason, failed_rules=()):
    """200, approved, TRANSFER_CANCELLED, nothing moved, offer ended, case not FAILED."""
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == TRANSFER_CANCELLED
    assert body["is_approved"] is True
    assert body["reason"] == reason
    assert body["failed_rules"] == list(failed_rules)
    assert body["case_status"] != CaseStatus.FAILED.value
    db.expire_all()
    request = db.get(ApprovalRequest, request_id)
    assert not request.is_pending and request.is_approved is True
    assert all(row.transferred_from_assignment_id is None for row in rows_of(db))
    assert all(row.status == RosterStatus.ASSIGNED for row in rows_of(db))
    outreach = db.get(CandidateOutreach, request.outreach_id)
    assert outreach.status == OutreachStatus.CANCELLED
    views = [v for v in outreach_service.list_offers(db, staff_id=201) if v.id == outreach.id]
    assert views[0].cancellation_reason == "TRANSFER_CHECK_FAILED"
    audit = failure_audit(db)
    assert audit.entity_id == request_id
    assert audit.payload == {
        "approval_id": request_id,
        "outreach_id": request.outreach_id,
        "staff_id": 201,
        "reason": reason,
        "failed_rules": list(failed_rules),
    }
    actions = list(db.scalars(select(AuditLog.action)))
    assert AuditAction.ASSIGNMENT_TRANSFERRED not in actions
    assert AuditAction.ASSIGNMENT_CREATED not in actions


def source_row(db):
    return next(row for row in rows_of(db) if row.assignment_type == AssignmentType.REGULAR)


def test_success_moves_the_person_and_resolves_the_case(scene):
    db, client, request_id, source_headers = scene
    response = approve_both(client, request_id, source_headers)
    assert response.json()["outcome"] == "ASSIGNED"
    assert response.json()["case_status"] == "RESOLVED"
    db.expire_all()
    request = db.get(ApprovalRequest, request_id)
    case = db.get(StaffingCase, request.case_id)
    shift = db.get(Shift, case.shift_id)
    old, new = rows_of(db)
    assert old.status == RosterStatus.CANCELLED
    assert new.status == RosterStatus.ASSIGNED and new.shift_id == case.shift_id
    assert new.transferred_from_assignment_id == old.id
    assert new.candidate_source == CandidateSource.CROSS_WARD
    assert new.actual_start_at is None and new.actual_end_at is None
    audit = db.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.ASSIGNMENT_TRANSFERRED)
    ).one()
    assert audit.entity_id == new.id and audit.case_id == case.id
    assert audit.payload == {
        "assignment_id": new.id,
        "from_assignment_id": old.id,
        "staff_id": 201,
        "from_shift_id": old.shift_id,
        "to_shift_id": case.shift_id,
        "transfer_at": shift.start_at.isoformat(),
        "from_status": "CANCELLED",
        "cancelled_outreach_ids": [],
    }
    actions = list(db.scalars(select(AuditLog.action)))
    assert AuditAction.ASSIGNMENT_CREATED not in actions
    assert AuditAction.TRANSFER_CHECK_FAILED not in actions
    assert db.get(CandidateOutreach, request.outreach_id).status == OutreachStatus.ACCEPTED


def test_destination_window_passed(scene):
    db, client, request_id, source_headers = scene
    assert decide(client, request_id).json()["outcome"] == "WAITING_OTHER_WARD"
    request = db.get(ApprovalRequest, request_id)
    shift = db.get(Shift, db.get(StaffingCase, request.case_id).shift_id)
    clock.set_time(shift.end_at)
    response = decide(client, request_id, source_headers)
    assert_refused(db, request_id, response, "DESTINATION_WINDOW_PASSED")


def test_source_shift_started_before_the_final_approval(scene):
    db, client, request_id, source_headers = scene
    # The source ward approves in time; the destination ward approves after the start
    assert decide(client, request_id, source_headers).json()["outcome"] == "WAITING_OTHER_WARD"
    request = db.get(ApprovalRequest, request_id)
    shift = db.get(Shift, db.get(StaffingCase, request.case_id).shift_id)
    clock.set_time(shift.start_at + timedelta(minutes=5))
    response = decide(client, request_id)
    assert_refused(db, request_id, response, "SOURCE_SHIFT_STARTED")
    assert source_row(db).actual_end_at is None


def test_source_row_cancelled_after_the_request(scene):
    db, client, request_id, source_headers = scene
    assert decide(client, request_id).json()["outcome"] == "WAITING_OTHER_WARD"
    source_row(db).status = RosterStatus.CANCELLED
    db.commit()
    response = decide(client, request_id, source_headers)
    body = response.json()
    assert body["outcome"] == TRANSFER_CANCELLED and body["reason"] == "SOURCE_COVERAGE_LOST"
    assert body["failed_rules"] == []
    audit = failure_audit(db)
    assert audit.payload["reason"] == "SOURCE_COVERAGE_LOST" and audit.payload["failed_rules"] == []
    # Nothing was linked to the dead row
    assert [row.transferred_from_assignment_id for row in rows_of(db)] == [None]


def test_source_gap_after_the_request(scene):
    db, client, request_id, source_headers = scene
    assert decide(client, request_id).json()["outcome"] == "WAITING_OTHER_WARD"
    # The other nurse of the source shift leaves: moving 201 would leave it short
    moved = source_row(db)
    other = db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.shift_id == moved.shift_id, RosterAssignment.staff_id != 201
        )
    ).one()
    other.status = RosterStatus.CANCELLED
    db.commit()
    response = decide(client, request_id, source_headers)
    assert_refused(db, request_id, response, "SOURCE_COVERAGE_LOST")


def test_a_conflicting_duty_added_after_safety_fails_the_hard_rule(scene):
    db, client, request_id, source_headers = scene
    assert decide(client, request_id).json()["outcome"] == "WAITING_OTHER_WARD"
    request = db.get(ApprovalRequest, request_id)
    shift = db.get(Shift, db.get(StaffingCase, request.case_id).shift_id)
    # A shift of a third ward that overlaps the night shift, taken after Safety passed
    other = _shift(
        db, _ward(db), shift.start_at - timedelta(hours=2), shift.end_at - timedelta(hours=2)
    )
    _duty(db, 201, other)
    db.commit()
    response = decide(client, request_id, source_headers)
    body = response.json()
    assert body["outcome"] == TRANSFER_CANCELLED and body["reason"] == "HARD_RULE_FAILED"
    assert HardRuleCode.SHIFT_CONFLICT.value in body["failed_rules"]
    order = [code.value for code in HardRuleCode]
    assert body["failed_rules"] == sorted(body["failed_rules"], key=order.index)
    assert all(code in order[3:10] for code in body["failed_rules"])
    assert_refused(db, request_id, response, "HARD_RULE_FAILED", body["failed_rules"])


def test_a_reserve_is_promoted_after_a_refused_move(scene):
    db, client, request_id, source_headers = scene
    assert decide(client, request_id).json()["outcome"] == "WAITING_OTHER_WARD"
    request = db.get(ApprovalRequest, request_id)
    item_202 = db.scalars(
        select(CandidateItem).where(
            CandidateItem.plan_id == db.get(CandidateItem, request.candidate_item_id).plan_id,
            CandidateItem.staff_id == 202,
        )
    ).one()
    reserve = offer(db, db.get(StaffingCase, request.case_id), item_202, OutreachStatus.ACCEPTED)
    source_row(db).status = RosterStatus.CANCELLED
    db.commit()
    response = decide(client, request_id, source_headers)
    assert response.json()["outcome"] == TRANSFER_CANCELLED
    assert response.json()["case_status"] == CaseStatus.WAITING_APPROVAL.value
    db.expire_all()
    promoted = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.outreach_id == reserve.id)
    ).one()
    assert promoted.is_pending and promoted.candidate_item_id == item_202.id


def test_the_next_wave_is_sent_when_there_is_no_reserve(scene):
    db, client, request_id, source_headers = scene
    assert decide(client, request_id).json()["outcome"] == "WAITING_OTHER_WARD"
    source_row(db).status = RosterStatus.CANCELLED
    db.commit()
    response = decide(client, request_id, source_headers)
    assert response.json()["outcome"] == TRANSFER_CANCELLED
    assert response.json()["case_status"] == CaseStatus.WAITING_RESPONSE.value
    db.expire_all()
    request = db.get(ApprovalRequest, request_id)
    sent = list(
        db.scalars(
            select(CandidateItem.staff_id)
            .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
            .where(
                CandidateOutreach.case_id == request.case_id,
                CandidateOutreach.status == OutreachStatus.SENT,
            )
        )
    )
    assert sent and 201 not in sent


def test_a_conflicting_foreign_offer_is_cancelled_by_the_move(scene):
    db, client, request_id, source_headers = scene
    request = db.get(ApprovalRequest, request_id)
    shift = db.get(Shift, db.get(StaffingCase, request.case_id).shift_id)
    # Another ward's case, overlapping the night shift, has a live offer to 201
    other = _shift(
        db, _ward(db), shift.start_at - timedelta(hours=2), shift.end_at - timedelta(hours=2)
    )
    requirement = StaffingRequirement(
        shift_id=other, required_staff=1, minimum_staff=1, created_at=DEMO_NOW
    )
    db.add(requirement)
    db.flush()
    db.add(
        StaffingRequirementRole(
            staffing_requirement_id=requirement.id, role_id=RN, required_count=1
        )
    )
    foreign = make_case(db, CaseStatus.WAITING_RESPONSE, shift_id=other)
    record_gap(db, foreign)
    foreign_item = make_plan(db, foreign, (201,))[201]
    foreign_offer = offer(db, foreign, foreign_item)
    db.commit()
    response = approve_both(client, request_id, source_headers)
    assert response.json()["outcome"] == "ASSIGNED"
    db.expire_all()
    assert db.get(CandidateOutreach, foreign_offer.id).status == OutreachStatus.CANCELLED
    transferred = db.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.ASSIGNMENT_TRANSFERRED)
    ).one()
    assert transferred.payload["cancelled_outreach_ids"] == [foreign_offer.id]
    views = [v for v in outreach_service.list_offers(db, staff_id=201) if v.id == foreign_offer.id]
    assert views[0].cancellation_reason == "CONFLICTING_ASSIGNMENT"


@pytest.fixture
def committed_race(frozen_clock):
    """Two cases in two wards move one nurse each off one source shift with a surplus of 1."""
    with SessionLocal() as db:
        load(db)
        case_a, items_a = short_case(db, 105, status=CaseStatus.WAITING_APPROVAL)
        night = db.get(Shift, case_a.shift_id)
        source_ward, source_headers = _add_other_ward_head_nurse(db)
        ward_b, headers_b = _add_other_ward_head_nurse(db)
        source_shift = _shift(db, source_ward, night.start_at, night.end_at)
        shift_b = _shift(db, ward_b, night.start_at, night.end_at)
        for shift_id, required in ((source_shift, 2), (shift_b, 1)):
            requirement = StaffingRequirement(
                shift_id=shift_id,
                required_staff=required,
                minimum_staff=required,
                created_at=DEMO_NOW,
            )
            db.add(requirement)
            db.flush()
            db.add(
                StaffingRequirementRole(
                    staffing_requirement_id=requirement.id, role_id=RN, required_count=required
                )
            )
        movers = [201, _rn(db, source_ward), _rn(db, source_ward)]
        for staff_id in movers:
            _duty(db, staff_id, source_shift)
        case_b = make_case(db, CaseStatus.WAITING_APPROVAL, shift_id=shift_b)
        record_gap(db, case_b)
        items_b = make_plan(db, case_b, (movers[1],))
        requests = []
        for case, item in ((case_a, items_a[201]), (case_b, items_b[movers[1]])):
            row = db.scalars(
                select(RosterAssignment).where(
                    RosterAssignment.staff_id == item.staff_id,
                    RosterAssignment.shift_id == source_shift,
                )
            ).one()
            item.source_assignment_id = row.id
            item.source = CandidateSource.CROSS_WARD
            requests.append(approval(db, case, item).id)
        db.commit()
        result = requests, (case_a.id, case_b.id), source_headers, headers_b
    try:
        yield result
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        engine.dispose()


def test_two_final_approvals_race_for_the_last_surplus_of_one_source_shift(committed_race):
    (request_a, request_b), case_ids, source_headers, headers_b = committed_race
    with TestClient(app) as client:
        # Each destination ward approves first; the source ward's decisions are the final ones
        assert decide(client, request_a).json()["outcome"] == "WAITING_OTHER_WARD"
        assert decide(client, request_b, headers_b).json()["outcome"] == "WAITING_OTHER_WARD"
    barrier = threading.Barrier(2, timeout=10)

    def final(request_id):
        with TestClient(app) as client:
            barrier.wait()
            response = decide(client, request_id, source_headers)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(final, request_a), pool.submit(final, request_b)]
        results = [job.result(timeout=30) for job in jobs]
    assert [code for code, _ in results] == [200, 200]
    assert sorted(body["outcome"] for _, body in results) == ["ASSIGNED", TRANSFER_CANCELLED]
    refused = next(body for _, body in results if body["outcome"] == TRANSFER_CANCELLED)
    assert refused["reason"] == "SOURCE_COVERAGE_LOST" and refused["failed_rules"] == []
    with SessionLocal() as db:
        actions = list(db.scalars(select(AuditLog.action)))
        assert actions.count(AuditAction.ASSIGNMENT_TRANSFERRED) == 1
        assert actions.count(AuditAction.TRANSFER_CHECK_FAILED) == 1
        assert AuditAction.WORKFLOW_FAILED not in actions
        for case_id in case_ids:
            assert db.get(StaffingCase, case_id).status != CaseStatus.FAILED
        (moved,) = db.scalars(
            select(RosterAssignment).where(
                RosterAssignment.transferred_from_assignment_id.isnot(None)
            )
        )
        assert db.get(RosterAssignment, moved.transferred_from_assignment_id).status == (
            RosterStatus.CANCELLED
        )
