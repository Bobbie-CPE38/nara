"""PR T: immutable deadlines, attempt isolation, one retry and PostgreSQL races."""

import threading
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text

from app.core import clock
from app.db.models import (
    ApprovalPolicy,
    ApprovalRequest,
    AuditLog,
    CandidateOutreach,
    SafetyValidation,
    Shift,
    Staff,
    StaffingCase,
)
from app.db.session import SessionLocal
from app.domain.enums import AuditAction, CandidateResponse, CaseStatus, OutreachStatus, StaffStatus
from app.seed import load
from app.services import (
    actor_service,
    approval_service,
    approval_timeout_service,
    case_facts_service,
    case_service,
    job_service,
    outreach_service,
    safety_service,
    wave_service,
)
from tests.integration.case_rows import (
    approval,
    make_case,
    make_plan,
    offer,
    record_gap,
    short_case,
)
from tests.integration.conftest import DEMO_NOW


def accept(db, row, staff=201):
    return outreach_service.record_response(
        db,
        staff_id=staff,
        actor_id=actor_service.user_id(db, staff),
        outreach_id=row.id,
        response=CandidateResponse.ACCEPT,
    )


def decide(db, request, approved=True):
    return approval_service.decide(
        db,
        approval_id=request.id,
        staff_id=900,
        role_id=2,
        home_ward_id=db.get(Staff, 900).home_ward_id,
        actor_id=actor_service.user_id(db, 900),
        approved=approved,
        reason=None if approved else "not selected",
    )


def pending(db, *, candidates=(201, 202, 203)):
    case, _ = short_case(db, status=CaseStatus.WAITING_APPROVAL)
    items = make_plan(db, case, candidates)
    row = offer(db, case, items[candidates[0]], OutreachStatus.ACCEPTED)
    result = safety_service.validate_accepted_candidate(db, case, outreach_id=row.id)
    db.commit()
    return case, items, row, result.approval


def test_deadline_is_policy_snapshot_and_boundary_is_read_only(production_seeded):
    db = production_seeded
    policy = db.get(ApprovalPolicy, 1)
    policy.supervisor_after_seconds = 30
    policy.approval_timeout_seconds = 60
    case, _, row, request = pending(db)
    assert request.expires_at == DEMO_NOW + timedelta(seconds=60)
    policy.approval_timeout_seconds = 900
    db.commit()
    assert approval_service.list_pending(db)[0].expires_at == request.expires_at
    before = db.scalar(select(func.count()).select_from(AuditLog))
    clock.advance(timedelta(seconds=60))
    for approved in (True, False):
        with pytest.raises(approval_service.ApprovalNotPendingError, match="expired"):
            decide(db, request, approved)
        db.rollback()
    db.refresh(request)
    assert request.is_pending and not request.is_timed_out
    assert db.get(CandidateOutreach, row.id).status == OutreachStatus.ACCEPTED
    assert db.scalar(select(func.count()).select_from(AuditLog)) == before
    assert db.get(StaffingCase, case.id).status == CaseStatus.WAITING_APPROVAL


def test_decision_just_before_deadline_is_allowed(production_seeded):
    db = production_seeded
    case, _, _, request = pending(db)
    clock.advance(timedelta(seconds=900, microseconds=-1))
    decide(db, request)
    assert case.status == CaseStatus.RESOLVED
    clock.advance(timedelta(microseconds=1))
    assert approval_timeout_service.expire_due_approvals(db).approval_ids == []


def test_timeout_audit_stage_and_offer_reason_are_distinct_from_rejection(production_seeded):
    db = production_seeded
    case, _, row, request = pending(db)
    clock.advance(timedelta(seconds=900))
    work = job_service.run_due_work(db)
    assert work.timed_out_approval_request_ids == [request.id]
    db.refresh(request)
    assert request.is_timed_out and request.is_approved is False and not request.is_pending
    assert request.approver_id is None and request.decided_at == clock.now()
    assert db.get(CandidateOutreach, row.id).status == OutreachStatus.CANCELLED
    assert (
        outreach_service.list_offers(db, staff_id=201)[0].cancellation_reason == "APPROVAL_TIMEOUT"
    )
    assert case_service.get_case_detail(db, case.id).candidates[0].stage == "APPROVAL_TIMEOUT"
    logs = list(db.scalars(select(AuditLog).where(AuditLog.action == AuditAction.APPROVAL_TIMEOUT)))
    assert len(logs) == 1 and logs[0].payload["outreach_id"] == row.id
    assert job_service.run_due_work(db).timed_out_approval_request_ids == []


def test_full_retry_gets_fresh_safety_and_request_and_can_be_approved(production_seeded):
    db = production_seeded
    case, items, first, request = pending(db, candidates=(201, 202))
    clock.advance(timedelta(seconds=900))
    job_service.run_due_work(db)
    next_offer = db.scalars(
        select(CandidateOutreach).where(
            CandidateOutreach.case_id == case.id, CandidateOutreach.status == OutreachStatus.SENT
        )
    ).one()
    assert next_offer.candidate_item_id == items[202].id
    outreach_service.record_response(
        db,
        staff_id=202,
        actor_id=actor_service.user_id(db, 202),
        outreach_id=next_offer.id,
        response=CandidateResponse.REJECT,
    )
    second = db.scalars(
        select(CandidateOutreach).where(
            CandidateOutreach.case_id == case.id, CandidateOutreach.status == OutreachStatus.SENT
        )
    ).one()
    assert second.id != first.id and second.candidate_item_id == items[201].id
    assert case_service.get_case_detail(db, case.id).candidates[0].stage == "OFFER_SENT"
    accept(db, second)
    fresh = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.outreach_id == second.id)
    ).one()
    assert fresh.id != request.id and fresh.expires_at == clock.now() + timedelta(seconds=900)
    assert fresh.is_pending and not fresh.is_timed_out
    assert case_facts_service.staff_waiting_case_ids(db, 201) == {case.id}
    assert case_facts_service.pending_staff_ids(db, case.id) == {201}
    assert case_service.get_case_detail(db, case.id).candidates[0].stage == "WAITING_APPROVAL"
    assert (
        db.scalar(
            select(func.count())
            .select_from(SafetyValidation)
            .where(SafetyValidation.candidate_item_id == items[201].id)
        )
        == 2
    )
    decide(db, fresh)
    assert case.status == CaseStatus.RESOLVED
    assert case_service.get_case_detail(db, case.id).assigned_count == 1
    assert request.is_timed_out
    history = outreach_service.list_offers(db, staff_id=201)
    assert not history[0].is_assigned and history[1].is_assigned


def test_second_timeout_has_no_third_offer(production_seeded):
    db = production_seeded
    case, _, _, request = pending(db, candidates=(201,))
    clock.advance(timedelta(seconds=900))
    job_service.run_due_work(db)
    second = db.scalars(
        select(CandidateOutreach).where(
            CandidateOutreach.case_id == case.id, CandidateOutreach.status == OutreachStatus.SENT
        )
    ).one()
    accept(db, second)
    clock.advance(timedelta(seconds=900))
    job_service.run_due_work(db)
    assert (
        db.scalar(
            select(func.count())
            .select_from(CandidateOutreach)
            .where(CandidateOutreach.case_id == case.id)
        )
        == 2
    )
    assert db.get(StaffingCase, case.id).status == CaseStatus.MANUAL_HANDOFF
    assert not case_facts_service.pending_staff_ids(db, case.id)


def test_inactive_history_is_not_expired(production_seeded):
    db = production_seeded
    case, items = short_case(db, status=CaseStatus.WAITING_APPROVAL)
    orphan = approval(db, case, items[201])
    db.get(CandidateOutreach, orphan.outreach_id).status = OutreachStatus.CANCELLED
    decided = approval(db, case, items[202], approved=False)
    stopped_case = make_case(db, CaseStatus.MANUAL_HANDOFF)
    stopped_items = make_plan(db, stopped_case, (203,))
    stopped = approval(db, stopped_case, stopped_items[203])
    db.commit()
    clock.advance(timedelta(seconds=900))
    assert approval_timeout_service.expire_due_approvals(db).approval_ids == []
    assert not any(db.get(ApprovalRequest, r.id).is_timed_out for r in (orphan, decided, stopped))


def test_skipped_first_contact_does_not_block_retry_and_skip_does_not_consume_it(production_seeded):
    db = production_seeded
    case, items, _, request = pending(db, candidates=(201, 202))
    request.is_pending = False
    request.is_approved = False
    request.is_timed_out = True
    db.get(CandidateOutreach, request.outreach_id).status = OutreachStatus.CANCELLED
    db.get(Staff, 202).status = StaffStatus.INACTIVE
    db.get(Staff, 201).status = StaffStatus.INACTIVE
    db.flush()
    shift = db.get(Shift, case.shift_id)
    assert wave_service.select_wave(db, case_id=case.id, shift=shift).items == ()
    db.get(Staff, 201).status = StaffStatus.ACTIVE
    db.flush()
    selection = wave_service.select_wave(db, case_id=case.id, shift=shift)
    assert [item.id for item in selection.items] == [items[201].id]
    assert db.scalar(select(func.count()).select_from(CandidateOutreach)) == 1


def test_workflow_failure_preserves_timeout_but_rolls_back_new_wave(production_seeded):
    db = production_seeded
    case, _, _, request = pending(db)
    clock.advance(timedelta(seconds=900))
    with patch.object(outreach_service, "promote_reserves", side_effect=RuntimeError("broken")):
        result = approval_timeout_service.expire_due_approvals(db)
    assert result.approval_ids == [request.id]
    assert db.get(StaffingCase, case.id).status == CaseStatus.FAILED
    assert db.get(ApprovalRequest, request.id).is_timed_out
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.APPROVAL_TIMEOUT)
        )
        == 1
    )


@pytest.fixture
def committed_approval(frozen_clock, restore_empty_database):
    with SessionLocal() as db:
        load(db)
        case, _, _, request = pending(db, candidates=(201,))
        ids = case.id, request.id
    yield ids


@pytest.mark.parametrize("decision_race", [False, True])
def test_two_connections_expire_once_and_never_assign_after_deadline(
    committed_approval, decision_race
):
    case_id, request_id = committed_approval
    clock.advance(timedelta(seconds=900))
    barrier = threading.Barrier(2)
    errors = []
    outcomes = []

    def run(deciding):
        try:
            with SessionLocal() as db:
                db.execute(text("SET lock_timeout = '5s'"))
                barrier.wait(5)
                if deciding:
                    request = db.get(ApprovalRequest, request_id)
                    try:
                        decide(db, request)
                    except approval_service.ApprovalNotPendingError:
                        db.rollback()
                        outcomes.append("expired")
                else:
                    outcomes.extend(approval_timeout_service.expire_due_approvals(db).approval_ids)
        except Exception as error:
            errors.append(error)

    threads = [
        threading.Thread(target=run, args=(False,), daemon=True),
        threading.Thread(target=run, args=(decision_race,), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    assert not any(thread.is_alive() for thread in threads)
    assert not errors, errors
    assert outcomes.count(request_id) == 1
    with SessionLocal() as db:
        assert db.get(ApprovalRequest, request_id).is_timed_out
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.APPROVAL_TIMEOUT)
            )
            == 1
        )
        assert db.get(StaffingCase, case_id).status == CaseStatus.WAITING_RESPONSE


def test_transient_lock_failure_is_isolated_and_retried_next_tick(production_seeded):
    db = production_seeded
    first, _, _, request = pending(db, candidates=(201,))
    second = make_case(db, CaseStatus.WAITING_APPROVAL)
    record_gap(db, second)
    items = make_plan(db, second, (202,))
    other = approval(db, second, items[202])
    db.commit()
    clock.advance(timedelta(seconds=900))
    real_lock = approval_service.lock_approval_attempt

    def lock(db, approval_id, role_id, home_ward_id=None):
        if approval_id == request.id:
            raise approval_service.ApprovalLockRetryError("try later")
        return real_lock(db, approval_id, role_id, home_ward_id)

    with patch.object(approval_service, "lock_approval_attempt", side_effect=lock):
        result = approval_timeout_service.expire_due_approvals(db)
    assert result.approval_ids == [other.id] and result.failed_case_ids == {first.id}
    assert db.get(ApprovalRequest, request.id).is_pending
    assert approval_timeout_service.expire_due_approvals(db).approval_ids == [request.id]


def test_retry_is_rechecked_against_concurrent_offer_limit(production_seeded):
    from app.db.models import OutreachPolicy

    db = production_seeded
    case, items, _, request = pending(db, candidates=(201,))
    request.is_pending = False
    request.is_timed_out = True
    request.is_approved = False
    db.get(CandidateOutreach, request.outreach_id).status = OutreachStatus.CANCELLED
    foreign = make_case(db)
    foreign_items = make_plan(db, foreign, (201,))
    held = offer(db, foreign, foreign_items[201])
    db.get(OutreachPolicy, 1).maximum_concurrent_offers_per_staff = 1
    db.flush()
    shift = db.get(Shift, case.shift_id)
    skipped = wave_service.select_wave(db, case_id=case.id, shift=shift)
    assert skipped.items == ()
    assert skipped.skipped == ({"staff_id": 201, "reason": "OFFER_LIMIT_REACHED"},)
    held.status = OutreachStatus.CANCELLED
    db.flush()
    assert [
        item.id for item in wave_service.select_wave(db, case_id=case.id, shift=shift).items
    ] == [items[201].id]
    assert (
        db.scalar(
            select(func.count())
            .select_from(CandidateOutreach)
            .where(CandidateOutreach.case_id == case.id)
        )
        == 1
    )


def test_committed_timeout_is_not_failed_when_foreign_notification_raises(production_seeded):
    db = production_seeded
    case, _, _, request = pending(db, candidates=(201,))
    clock.advance(timedelta(seconds=900))
    with patch.object(
        outreach_service,
        "recompute_affected_cases",
        side_effect=RuntimeError("notification failed"),
    ):
        result = approval_timeout_service.expire_due_approvals(db)
    assert result.approval_ids == [request.id]
    assert result.failed_case_ids == set()
    assert db.get(ApprovalRequest, request.id).is_timed_out
    assert db.get(StaffingCase, case.id).status == CaseStatus.WAITING_RESPONSE
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.APPROVAL_TIMEOUT)
        )
        == 1
    )
    assert approval_timeout_service.expire_due_approvals(db).approval_ids == []


def test_expired_pending_list_is_read_only_but_coverage_waits_for_job(production_seeded):
    db = production_seeded
    case, _, _, request = pending(db, candidates=(201,))
    clock.advance(timedelta(seconds=900, microseconds=-1))
    assert [row.id for row in approval_service.list_pending(db)] == [request.id]
    before = db.scalar(select(func.count()).select_from(AuditLog))
    clock.advance(timedelta(microseconds=1))
    assert approval_service.list_pending(db) == []
    assert case_facts_service.pending_staff_ids(db, case.id) == {201}
    assert case_facts_service.staff_waiting_case_ids(db, 201) == {case.id}
    assert db.scalar(select(func.count()).select_from(AuditLog)) == before
    assert db.get(ApprovalRequest, request.id).is_pending
    approval_timeout_service.expire_due_approvals(db)
    assert not case_facts_service.pending_staff_ids(db, case.id)


def test_timeout_job_does_not_require_a_head_nurse_ward(production_seeded):
    db = production_seeded
    _, _, _, request = pending(db, candidates=(201,))
    clock.advance(timedelta(seconds=900))
    with patch.object(
        approval_service.approval_wards,
        "authority",
        side_effect=AssertionError("job is not an approver"),
    ) as check:
        result = approval_timeout_service.expire_due_approvals(db)
    check.assert_not_called()
    assert result.approval_ids == [request.id] and not result.failed_case_ids
