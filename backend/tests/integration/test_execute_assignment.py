"""Per-candidate roster creation and finalization of already staffed cases."""

from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ApprovalRequest, AuditLog, RosterAssignment, Shift, Staff, StaffingCase
from app.domain.enums import (
    AssignmentType,
    AuditAction,
    CandidateSource,
    CaseStatus,
    OutreachStatus,
    RosterStatus,
    StaffStatus,
)
from app.services import roster_service
from app.workflow import orchestrator
from app.workflow.handlers import execute_assignment
from tests.integration.case_rows import approval, assign, make_case, make_plan, offer, short_case
from tests.integration.test_cross_ward_pool import _duty, _shift, _ward


def replacements(db: Session) -> list[RosterAssignment]:
    return list(
        db.scalars(
            select(RosterAssignment)
            .where(RosterAssignment.assignment_type == AssignmentType.REPLACEMENT)
            .order_by(RosterAssignment.id)
        )
    )


@pytest.mark.parametrize("source", list(CandidateSource))
def test_replacement_uses_selected_approval_not_another_approved_item(
    production_seeded: Session, source: CandidateSource
) -> None:
    db = production_seeded
    case, items = short_case(db, 104, 105, status=CaseStatus.WAITING_APPROVAL)
    approval(db, case, items[202], approved=True)
    chosen = approval(db, case, items[201], approved=True)
    items[201].source = source
    make_plan(db, case, (203,))  # A newer plan is not the selected request.
    with patch.object(db, "commit", side_effect=AssertionError("service committed")):
        row = roster_service.create_replacement(db, case, approval=chosen)
    assert row.staff_id == 201
    assert row.shift_id == case.shift_id
    assert row.status == RosterStatus.ASSIGNED
    assert row.assignment_type == AssignmentType.REPLACEMENT
    assert row.candidate_source == source
    assert list(db.scalars(select(AuditLog.action).order_by(AuditLog.id))) == [
        AuditAction.CASE_OPENED,
        AuditAction.HANDOVER_GENERATED,
    ]


@pytest.mark.parametrize("approved", [None, False])
def test_unapproved_request_cannot_create_assignment(
    production_seeded: Session, approved: bool | None
) -> None:
    db = production_seeded
    case, items = short_case(db)
    request = approval(db, case, items[201], approved=approved)
    with pytest.raises(ValueError, match="decided, approved"):
        roster_service.create_replacement(db, case, approval=request)
    assert replacements(db) == []


@pytest.mark.parametrize("mismatch", ["request_case", "plan_case", "shift"])
def test_reference_mismatch_cannot_create_assignment(
    production_seeded: Session, mismatch: str
) -> None:
    db = production_seeded
    case, items = short_case(db)
    request = approval(db, case, items[201], approved=True)
    other = make_case(db)
    if mismatch == "request_case":
        request.case_id = other.id
    elif mismatch == "plan_case":
        items[201].plan_id = make_plan(db, other, (201,))[201].plan_id
    else:
        items[201].proposed_shift_id = 2
    with pytest.raises(ValueError):
        roster_service.create_replacement(db, case, approval=request)
    assert replacements(db) == []


def _move(db: Session) -> tuple[StaffingCase, ApprovalRequest, RosterAssignment]:
    """An approved move of 201 off a row on a shift of the same hours in another ward."""
    case, items = short_case(db)
    destination = db.get(Shift, case.shift_id)
    assert destination is not None
    ward_id = _ward(db)
    shift_id = _shift(db, ward_id, destination.start_at, destination.end_at)
    _duty(db, 201, shift_id)
    source = db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == 201, RosterAssignment.shift_id == shift_id
        )
    ).one()
    items[201].source_assignment_id = source.id
    items[201].source = CandidateSource.CROSS_WARD
    return case, approval(db, case, items[201], approved=True), source


def test_create_replacement_refuses_a_move_out_of_another_shift(
    production_seeded: Session,
) -> None:
    """The plain writer would leave one person on two shifts, so a move needs create_transfer."""
    db = production_seeded
    case, request, _ = _move(db)
    with pytest.raises(ValueError, match="create_transfer"):
        roster_service.create_replacement(db, case, approval=request)
    assert replacements(db) == []


def test_create_transfer_cancels_the_source_row_and_links_the_destination(
    production_seeded: Session,
) -> None:
    db = production_seeded
    case, request, source = _move(db)
    shift = db.get(Shift, case.shift_id)
    assert shift is not None
    with patch.object(db, "commit", side_effect=AssertionError("service committed")):
        row, cut = roster_service.create_transfer(
            db, case, approval=request, transfer_at=shift.start_at
        )
    assert cut is source and source.status == RosterStatus.CANCELLED
    assert source.actual_start_at is None and source.actual_end_at is None
    assert row.staff_id == 201 and row.shift_id == case.shift_id
    assert row.status == RosterStatus.ASSIGNED
    assert row.assignment_type == AssignmentType.REPLACEMENT
    assert row.candidate_source == CandidateSource.CROSS_WARD
    assert row.transferred_from_assignment_id == source.id
    assert row.actual_start_at is None and row.actual_end_at is None
    assert list(db.scalars(select(AuditLog.action).order_by(AuditLog.id))) == [
        AuditAction.CASE_OPENED,
        AuditAction.HANDOVER_GENERATED,
    ]


def test_create_transfer_needs_a_source_assignment(production_seeded: Session) -> None:
    db = production_seeded
    case, items = short_case(db)
    request = approval(db, case, items[201], approved=True)
    shift = db.get(Shift, case.shift_id)
    assert shift is not None
    with pytest.raises(ValueError, match="source assignment"):
        roster_service.create_transfer(db, case, approval=request, transfer_at=shift.start_at)


def test_execution_does_not_recheck_safety(production_seeded: Session) -> None:
    db = production_seeded
    case, items = short_case(db)
    request = approval(db, case, items[201], approved=True)
    staff = db.get(Staff, 201)
    assert staff is not None
    staff.status = StaffStatus.INACTIVE  # Changed after the recorded Safety pass (Q38).
    with patch(
        "app.services.hard_rule_service.check_items", side_effect=AssertionError("rechecked")
    ):
        row = roster_service.create_replacement(db, case, approval=request)
    assert row.staff_id == 201


def test_finalization_keeps_assignment_history_and_cancels_sent_and_reserves(
    production_seeded: Session,
) -> None:
    db = production_seeded
    case, items = short_case(db, status=CaseStatus.EXECUTING)
    assign(db, case, items[201])
    assigned = offer(db, case, items[201], OutreachStatus.ACCEPTED)
    sent = offer(db, case, items[202])
    reserve = offer(db, case, items[203], OutreachStatus.ACCEPTED)
    before = len(replacements(db))
    with patch.object(db, "commit", side_effect=AssertionError("handler committed")):
        result = execute_assignment.handle(db, case)
    assert result.next_status == CaseStatus.RESOLVED
    assert case.status == CaseStatus.EXECUTING  # Only the orchestrator writes status.
    assert len(replacements(db)) == before
    assert assigned.status == OutreachStatus.ACCEPTED
    assert sent.status == reserve.status == OutreachStatus.CANCELLED
    assert list(db.scalars(select(AuditLog.action).order_by(AuditLog.id))) == [
        AuditAction.CASE_OPENED,
        AuditAction.CASE_RESOLVED,
    ]
    audit = db.scalars(select(AuditLog).where(AuditLog.action == AuditAction.CASE_RESOLVED)).one()
    assert audit.action == AuditAction.CASE_RESOLVED
    assert audit.payload == {
        "assignment_ids": [replacements(db)[0].id],
        "cancelled_outreach_ids": [sent.id, reserve.id],
    }


def test_finalization_requires_actual_assigned_gap_coverage(production_seeded: Session) -> None:
    db = production_seeded
    case, items = short_case(db, 104, 105, status=CaseStatus.EXECUTING)
    assign(db, case, items[201])
    with pytest.raises(ValueError, match="do not close"):
        execute_assignment.handle(db, case)
    assert list(db.scalars(select(AuditLog.action).order_by(AuditLog.id))) == [
        AuditAction.CASE_OPENED
    ]
    assert len(replacements(db)) == 1


def test_finalization_round_commits_once_and_replay_creates_nothing(
    production_seeded: Session,
) -> None:
    db = production_seeded
    case, items = short_case(db, status=CaseStatus.WAITING_APPROVAL)
    assign(db, case, items[201])
    offer(db, case, items[202])
    with patch.object(db, "commit", wraps=db.commit) as commit:
        assert orchestrator.recompute(db, case.id) == CaseStatus.RESOLVED
    assert commit.call_count == 1
    before = db.scalar(select(func.count()).select_from(AuditLog))
    orchestrator.recompute(db, case.id)
    assert db.scalar(select(func.count()).select_from(AuditLog)) == before
    assert len(replacements(db)) == 1
