"""The stub safety step against the seeded PostgreSQL: validation, approval request, audit."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    Actor,
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    SafetyValidation,
    StaffingCase,
    StaffingEvent,
)
from app.domain.enums import (
    ActorName,
    ApprovalMode,
    AuditAction,
    CandidateSource,
    CaseStatus,
    Channel,
    EntityType,
    EventStatus,
    EventType,
    OutreachStatus,
    SolverStatus,
)
from app.services import actor_service
from app.services.actor_service import ActorNotFoundError
from app.workflow import orchestrator
from app.workflow.handlers import validate_safety
from tests.integration.conftest import DEMO_NOW

SHIFT_ID = 1
LEAVING_STAFF_ID = 105
ACCEPTING_STAFF_ID = 201
HEAD_NURSE_ROLE_ID = 2


def _make_case(db: Session, status: CaseStatus = CaseStatus.SAFETY_VALIDATION) -> StaffingCase:
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=SHIFT_ID,
        occurred_at=DEMO_NOW,
        staff_id=LEAVING_STAFF_ID,
        status=EventStatus.PROCESSED,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        event_id=event.id,
        shift_id=SHIFT_ID,
        status=status,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(case)
    db.flush()
    return case


def _offer(
    db: Session,
    case: StaffingCase,
    *,
    status: OutreachStatus = OutreachStatus.ACCEPTED,
    planned_for: StaffingCase | None = None,
) -> CandidateOutreach:
    """The rows Solver and Outreach leave behind, shaped as seams 1, 2 and 4 describe.

    `planned_for` puts the plan on another case, which seam 5 must reject.
    """
    plan = CandidatePlan(
        case_id=(planned_for or case).id,
        solver_status=SolverStatus.FEASIBLE,
        generated_at=clock.now(),
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
        staff_id=ACCEPTING_STAFF_ID,
        rank=1,
        source=CandidateSource.SAME_WARD,
        proposed_shift_id=case.shift_id,
    )
    db.add(item)
    db.flush()
    outreach = CandidateOutreach(
        case_id=case.id,
        candidate_item_id=item.id,
        channel=Channel.LINE,
        sent_at=clock.now(),
        response_at=clock.now() if status is OutreachStatus.ACCEPTED else None,
        status=status,
    )
    db.add(outreach)
    db.flush()
    return outreach


def _validations(db: Session, case: StaffingCase) -> list[SafetyValidation]:
    return list(db.scalars(select(SafetyValidation).where(SafetyValidation.case_id == case.id)))


def _approvals(db: Session, case: StaffingCase) -> list[ApprovalRequest]:
    return list(db.scalars(select(ApprovalRequest).where(ApprovalRequest.case_id == case.id)))


def _audit(db: Session, case: StaffingCase) -> list[AuditLog]:
    # Ordered by id: the frozen demo clock gives every row the same created_at
    return list(
        db.scalars(select(AuditLog).where(AuditLog.case_id == case.id).order_by(AuditLog.id))
    )


def _actor(db: Session, name: ActorName) -> int | None:
    return db.scalar(select(Actor.id).where(Actor.name == name.value))


# --------------------------------------------------------------------------- #
# The handler on its own
# --------------------------------------------------------------------------- #
def test_waits_for_approval_without_touching_the_case(seeded: Session) -> None:
    case = _make_case(seeded)
    _offer(seeded, case)

    result = validate_safety.handle(seeded, case)

    assert result.next_status is CaseStatus.WAITING_APPROVAL
    assert result.wait is True
    assert case.status is CaseStatus.SAFETY_VALIDATION


def test_passes_the_accepted_candidate(seeded: Session) -> None:
    case = _make_case(seeded)
    outreach = _offer(seeded, case)

    validate_safety.handle(seeded, case)

    [validation] = _validations(seeded, case)
    assert validation.candidate_item_id == outreach.candidate_item_id
    assert validation.hard_constraint_policy_id == 1
    assert validation.is_passed is True
    assert validation.failure_reason is None
    assert validation.validation_snapshot == {}
    assert validation.validated_at == DEMO_NOW


def test_opens_a_pending_manual_approval_for_a_head_nurse(seeded: Session) -> None:
    case = _make_case(seeded)
    outreach = _offer(seeded, case)

    validate_safety.handle(seeded, case)

    [approval] = _approvals(seeded, case)
    assert approval.candidate_item_id == outreach.candidate_item_id
    assert approval.required_approver_role == HEAD_NURSE_ROLE_ID
    assert approval.approval_mode is ApprovalMode.MANUAL
    assert approval.is_pending is True
    assert approval.requested_at == DEMO_NOW
    assert (approval.approver_id, approval.is_approved, approval.reason, approval.decided_at) == (
        None,
        None,
        None,
        None,
    )


def test_logs_safety_passed_then_approval_requested(seeded: Session) -> None:
    case = _make_case(seeded)
    _offer(seeded, case)

    validate_safety.handle(seeded, case)

    [validation] = _validations(seeded, case)
    [approval] = _approvals(seeded, case)
    passed, requested = _audit(seeded, case)
    assert passed.action is AuditAction.SAFETY_PASSED
    assert passed.actor_id == _actor(seeded, ActorName.SAFETY_RULE_ENGINE)
    assert passed.entity_type is EntityType.SAFETY_VALIDATION
    assert passed.entity_id == validation.id
    assert passed.payload == {"validation_id": validation.id, "staff_id": ACCEPTING_STAFF_ID}
    assert requested.action is AuditAction.APPROVAL_REQUESTED
    assert requested.actor_id == _actor(seeded, ActorName.WORKFLOW_ORCHESTRATOR)
    assert requested.entity_type is EntityType.APPROVAL_REQUEST
    assert requested.entity_id == approval.id
    assert requested.payload == {"approval_id": approval.id, "approval_mode": "MANUAL"}


# --------------------------------------------------------------------------- #
# Seams 4 and 5: exactly one accepted offer, planned for this case
# --------------------------------------------------------------------------- #
def test_no_offer_raises(seeded: Session) -> None:
    case = _make_case(seeded)

    with pytest.raises(NoResultFound):
        validate_safety.handle(seeded, case)


def test_an_offer_that_is_not_accepted_yet_raises(seeded: Session) -> None:
    case = _make_case(seeded)
    _offer(seeded, case, status=OutreachStatus.SENT)

    with pytest.raises(NoResultFound):
        validate_safety.handle(seeded, case)


def test_two_accepted_offers_raise(seeded: Session) -> None:
    case = _make_case(seeded)
    _offer(seeded, case)
    _offer(seeded, case)

    with pytest.raises(MultipleResultsFound):
        validate_safety.handle(seeded, case)


def test_an_accepted_offer_of_another_case_does_not_count(seeded: Session) -> None:
    case = _make_case(seeded)
    _offer(seeded, _make_case(seeded))

    with pytest.raises(NoResultFound):
        validate_safety.handle(seeded, case)


def test_an_item_planned_for_another_case_raises(seeded: Session) -> None:
    case = _make_case(seeded)
    _offer(seeded, case, planned_for=_make_case(seeded))

    with pytest.raises(ValueError, match="belongs to case"):
        validate_safety.handle(seeded, case)


# --------------------------------------------------------------------------- #
# Through the orchestrator
# --------------------------------------------------------------------------- #
def test_resume_after_an_unflushed_accept_stops_at_waiting_approval(
    production_seeded: Session,
) -> None:
    """Autoflush off, as Respond will call it: the ACCEPTED update is not flushed yet."""
    db = production_seeded
    case = _make_case(db, CaseStatus.WAITING_RESPONSE)
    outreach = _offer(db, case, status=OutreachStatus.SENT)
    outreach.status = OutreachStatus.ACCEPTED

    orchestrator.resume(db, case.id, CaseStatus.SAFETY_VALIDATION)

    db.expire_all()
    assert case.status is CaseStatus.WAITING_APPROVAL
    [approval] = _approvals(db, case)
    assert approval.is_pending is True
    assert [row.action for row in _audit(db, case)] == [
        AuditAction.CASE_STATUS_CHANGED,
        AuditAction.SAFETY_PASSED,
        AuditAction.APPROVAL_REQUESTED,
        AuditAction.CASE_STATUS_CHANGED,
    ]


def test_resume_without_an_accepted_offer_fails_the_case(seeded: Session) -> None:
    case = _make_case(seeded, CaseStatus.WAITING_RESPONSE)

    orchestrator.resume(seeded, case.id, CaseStatus.SAFETY_VALIDATION)

    seeded.expire_all()
    assert case.status is CaseStatus.FAILED
    failure = _audit(seeded, case)[-1]
    assert failure.action is AuditAction.WORKFLOW_FAILED
    assert failure.payload["failed_at"] == "SAFETY_VALIDATION"
    assert failure.payload["error_type"] == "NoResultFound"


def test_a_failure_after_the_rows_were_written_rolls_them_back(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The audit actor is looked up after the service flushed both rows (D11 savepoint)."""
    case = _make_case(seeded, CaseStatus.WAITING_RESPONSE)
    _offer(seeded, case)
    real_component_id = actor_service.component_id

    def no_rule_engine(db: Session, name: ActorName) -> int:
        if name is ActorName.SAFETY_RULE_ENGINE:
            raise ActorNotFoundError(f"No actor named {name.value!r}")
        return real_component_id(db, name)

    monkeypatch.setattr(actor_service, "component_id", no_rule_engine)

    orchestrator.resume(seeded, case.id, CaseStatus.SAFETY_VALIDATION)

    seeded.expire_all()
    assert case.status is CaseStatus.FAILED
    assert _audit(seeded, case)[-1].payload["error_type"] == "ActorNotFoundError"
    assert _validations(seeded, case) == []
    assert _approvals(seeded, case) == []
