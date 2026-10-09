"""Seam 8: approved item to replacement, audit ownership, and D11 rollback."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.orm import Session

from app.db.models import (
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidatePlan,
    Role,
    RosterAssignment,
    StaffingCase,
    StaffingEvent,
)
from app.domain.enums import (
    ActorName,
    ApprovalMode,
    AssignmentType,
    AuditAction,
    CandidateSource,
    CaseStatus,
    EntityType,
    EventStatus,
    EventType,
    RosterStatus,
    SolverStatus,
)
from app.domain.workflow.transitions import InvalidTransitionError
from app.services import actor_service, audit_service, roster_service
from app.workflow import orchestrator
from app.workflow.handlers import execute_assignment
from tests.integration.conftest import DEMO_NOW


@pytest.fixture
def case(production_seeded: Session) -> StaffingCase:
    db = production_seeded
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=1,
        staff_id=105,
        occurred_at=DEMO_NOW,
        status=EventStatus.PROCESSED,
    )
    db.add(event)
    db.flush()
    row = StaffingCase(
        event_id=event.id,
        shift_id=1,
        status=CaseStatus.WAITING_APPROVAL,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(row)
    db.flush()
    return row


def _item(db: Session, case: StaffingCase, *, staff_id: int = 201, rank: int = 1) -> CandidateItem:
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
        staff_id=staff_id,
        rank=rank,
        source=CandidateSource.SAME_WARD,
        proposed_shift_id=case.shift_id,
    )
    db.add(item)
    db.flush()
    return item


def _approval(db: Session, case: StaffingCase, item: CandidateItem) -> ApprovalRequest:
    approval = ApprovalRequest(
        case_id=case.id,
        candidate_item_id=item.id,
        required_approver_role=db.scalars(select(Role.id).where(Role.name == "HEAD_NURSE")).one(),
        approval_mode=ApprovalMode.MANUAL,
        is_pending=False,
        is_approved=True,
        approver_id=900,
        reason=None,
        requested_at=DEMO_NOW,
        decided_at=DEMO_NOW,
    )
    db.add(approval)
    db.flush()
    return approval


@pytest.fixture
def approved(production_seeded: Session, case: StaffingCase) -> ApprovalRequest:
    return _approval(production_seeded, case, _item(production_seeded, case))


def _replacements(db: Session) -> list[RosterAssignment]:
    return list(
        db.scalars(
            select(RosterAssignment).where(
                RosterAssignment.assignment_type == AssignmentType.REPLACEMENT
            )
        )
    )


def _audits(db: Session, case: StaffingCase) -> list[AuditLog]:
    return list(
        db.scalars(select(AuditLog).where(AuditLog.case_id == case.id).order_by(AuditLog.id))
    )


@pytest.mark.parametrize("source", list(CandidateSource))
def test_handler_creates_replacement_and_audits_without_commit_or_status_change(
    production_seeded: Session,
    case: StaffingCase,
    approved: ApprovalRequest,
    source: CandidateSource,
) -> None:
    db = production_seeded
    item = db.get(CandidateItem, approved.candidate_item_id)
    assert item is not None
    item.source = source  # Unflushed: production autoflush is disabled.
    case.status = CaseStatus.EXECUTING
    with patch.object(db, "commit", wraps=db.commit) as commit:
        result = execute_assignment.handle(db, case)
    commit.assert_not_called()
    assert case.status is CaseStatus.EXECUTING
    assert result.next_status is CaseStatus.RESOLVED
    assert result.wait is False
    (assignment,) = _replacements(db)
    assert (assignment.staff_id, assignment.shift_id) == (item.staff_id, item.proposed_shift_id)
    assert assignment.status is RosterStatus.ASSIGNED
    assert assignment.candidate_source is source
    assert assignment.created_at == assignment.updated_at == DEMO_NOW
    rows = _audits(db, case)
    assert [row.action for row in rows] == [
        AuditAction.ASSIGNMENT_CREATED,
        AuditAction.CASE_RESOLVED,
    ]
    actor_id = actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR)
    assert all(row.actor_id == actor_id and row.created_at == DEMO_NOW for row in rows)
    assert rows[0].entity_type is EntityType.ROSTER_ASSIGNMENT
    assert rows[0].entity_id == assignment.id
    assert rows[0].payload == {
        "assignment_id": assignment.id,
        "staff_id": 201,
        "assignment_type": "REPLACEMENT",
    }
    assert rows[1].entity_type is EntityType.STAFFING_CASES
    assert rows[1].entity_id == case.id
    assert rows[1].payload == {"assignment_ids": [assignment.id]}
    db.rollback()
    assert _replacements(db) == []
    assert db.scalar(select(AuditLog.id)) is None


def test_service_uses_approved_item_not_latest_plan_or_rank_one(
    production_seeded: Session,
    case: StaffingCase,
    approved: ApprovalRequest,
) -> None:
    db = production_seeded
    item = db.get(CandidateItem, approved.candidate_item_id)
    assert item is not None
    item.rank = 2
    _item(db, case, staff_id=202)
    other = ApprovalRequest(
        case_id=case.id,
        candidate_item_id=item.id,
        required_approver_role=approved.required_approver_role,
        approval_mode=ApprovalMode.MANUAL,
        is_pending=True,
        is_approved=None,
        requested_at=DEMO_NOW,
    )
    db.add(other)
    with patch.object(db, "commit", wraps=db.commit) as commit:
        assignment = roster_service.create_replacement(db, case)
    commit.assert_not_called()
    assert assignment.staff_id == 201
    assert db.scalar(select(AuditLog.id)) is None
    assert case.status is CaseStatus.WAITING_APPROVAL


@pytest.mark.parametrize(
    "pending,approved_value", [(True, True), (True, None), (False, False), (False, None)]
)
def test_unapproved_requests_raise_before_assignment(
    production_seeded: Session,
    case: StaffingCase,
    approved: ApprovalRequest,
    pending: bool,
    approved_value: bool | None,
) -> None:
    approved.is_pending = pending
    approved.is_approved = approved_value
    with pytest.raises(NoResultFound):
        roster_service.create_replacement(production_seeded, case)
    assert _replacements(production_seeded) == []
    assert _audits(production_seeded, case) == []


def test_no_request_raises(production_seeded: Session, case: StaffingCase) -> None:
    with pytest.raises(NoResultFound):
        roster_service.create_replacement(production_seeded, case)
    assert _replacements(production_seeded) == []


def test_duplicate_approved_requests_raise(
    production_seeded: Session,
    case: StaffingCase,
    approved: ApprovalRequest,
) -> None:
    item = production_seeded.get(CandidateItem, approved.candidate_item_id)
    assert item is not None
    _approval(production_seeded, case, item)
    with pytest.raises(MultipleResultsFound):
        roster_service.create_replacement(production_seeded, case)
    assert _replacements(production_seeded) == []


def test_approved_request_of_other_case_is_not_used(
    production_seeded: Session,
    case: StaffingCase,
    approved: ApprovalRequest,
) -> None:
    other = StaffingCase(
        event_id=case.event_id,
        shift_id=case.shift_id,
        status=CaseStatus.EXECUTING,
        required_replacement_time=DEMO_NOW,
    )
    production_seeded.add(other)
    production_seeded.flush()
    with pytest.raises(NoResultFound):
        roster_service.create_replacement(production_seeded, other)
    assert _replacements(production_seeded) == []


@pytest.mark.parametrize("mismatch", ["plan_case", "shift"])
def test_inconsistent_item_references_fail_without_assignment(
    production_seeded: Session,
    case: StaffingCase,
    approved: ApprovalRequest,
    mismatch: str,
) -> None:
    db = production_seeded
    item = db.get(CandidateItem, approved.candidate_item_id)
    assert item is not None
    if mismatch == "shift":
        item.proposed_shift_id = 2
    else:
        other = StaffingCase(
            event_id=case.event_id,
            shift_id=case.shift_id,
            status=CaseStatus.EXECUTING,
            required_replacement_time=DEMO_NOW,
        )
        db.add(other)
        db.flush()
        other_item = _item(db, other)
        approved.candidate_item_id = other_item.id
    with pytest.raises(ValueError):
        roster_service.create_replacement(db, case)
    assert _replacements(db) == []
    assert _audits(db, case) == []


def test_resume_commits_assignment_and_resolution_once(
    production_seeded: Session,
    case: StaffingCase,
    approved: ApprovalRequest,
) -> None:
    db = production_seeded
    # Simulate seam 7 changing an approval in a session with autoflush=False.
    approved.is_pending = True
    approved.is_approved = None
    db.flush()
    approved.is_pending = False
    approved.is_approved = True
    with patch.object(db, "commit", wraps=db.commit) as commit:
        orchestrator.resume(db, case.id, CaseStatus.EXECUTING)
    assert commit.call_count == 1
    assert case.status is CaseStatus.RESOLVED
    assert len(_replacements(db)) == 1
    assert [row.action for row in _audits(db, case)] == [
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.ASSIGNMENT_CREATED,
        AuditAction.CASE_RESOLVED,
        AuditAction.CASE_STATUS_CHANGED,
    ]
    with pytest.raises(InvalidTransitionError):
        orchestrator.resume(db, case.id, CaseStatus.EXECUTING)
    assert len(_replacements(db)) == 1


@pytest.mark.parametrize("failure", ["missing_approval", "assignment_audit", "resolution_audit"])
def test_d11_rolls_back_assignment_and_execution_audits_but_keeps_approval(
    production_seeded: Session,
    case: StaffingCase,
    approved: ApprovalRequest,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    db = production_seeded
    if failure == "missing_approval":
        approved.is_approved = False
    else:
        action = (
            AuditAction.ASSIGNMENT_CREATED
            if failure == "assignment_audit"
            else AuditAction.CASE_RESOLVED
        )
        real_log = audit_service.log

        def fail_log(*args: object, **kwargs: object) -> None:
            if kwargs.get("action") is action:
                raise RuntimeError("execution audit failed")
            real_log(*args, **kwargs)

        monkeypatch.setattr(audit_service, "log", fail_log)
    orchestrator.resume(db, case.id, CaseStatus.EXECUTING)
    assert case.status is CaseStatus.FAILED
    assert approved.is_approved is (failure != "missing_approval")
    assert approved.is_pending is False
    assert _replacements(db) == []
    assert [row.action for row in _audits(db, case)] == [
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.WORKFLOW_FAILED,
    ]
