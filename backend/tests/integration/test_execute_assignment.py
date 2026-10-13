"""Per-candidate roster creation and finalization of already staffed cases."""

from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, RosterAssignment, Staff
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
    assert db.scalar(select(AuditLog.id)) is None


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
    audit = db.scalars(select(AuditLog)).one()
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
    assert db.scalar(select(AuditLog.id)) is None
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
