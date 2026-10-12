"""Safety of one accepted candidate against the seeded PostgreSQL: rules, rows, approval, audit."""

from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    Actor,
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    RosterAssignment,
    SafetyValidation,
    Shift,
    Staff,
    StaffingCase,
    StaffingEvent,
    StaffUnavailability,
)
from app.domain.constraints.codes import HardRuleCode
from app.domain.enums import (
    ActorName,
    ApprovalMode,
    AssignmentType,
    AuditAction,
    AvailabilityReason,
    CandidateSource,
    CaseStatus,
    Channel,
    EntityType,
    EventStatus,
    EventType,
    OutreachStatus,
    RosterStatus,
    SolverStatus,
    StaffStatus,
)
from app.services import approval_service, policy_service, safety_service
from app.services.safety_service import ProposedShiftMismatchError
from tests.integration.conftest import DEMO_NOW

SHIFT_ID = 1
DAY_SHIFT_ID = 2
LEAVING_STAFF_ID = 105
ACCEPTING_STAFF_ID = 201
HEAD_NURSE_ROLE_ID = 2


def _make_case(db: Session, status: CaseStatus = CaseStatus.WAITING_RESPONSE) -> StaffingCase:
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=SHIFT_ID,
        occurred_at=DEMO_NOW,
        staff_id=LEAVING_STAFF_ID,
        status=EventStatus.PROCESSED,
        processed_at=DEMO_NOW,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        shift_id=SHIFT_ID,
        status=status,
        required_replacement_time=DEMO_NOW + timedelta(hours=2),
    )
    db.add(case)
    db.flush()
    event.case_id = case.id
    db.flush()
    return case


def _offer(
    db: Session,
    case: StaffingCase,
    *,
    status: OutreachStatus = OutreachStatus.ACCEPTED,
    planned_for: StaffingCase | None = None,
    proposed_shift_id: int | None = None,
) -> CandidateOutreach:
    """The rows Solver and Outreach leave behind, shaped as seams 1, 2 and 4 describe.

    `planned_for` puts the plan on another case, which Safety must reject.
    `proposed_shift_id` defaults to the case's shift; another one must be rejected.
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
        proposed_shift_id=case.shift_id if proposed_shift_id is None else proposed_shift_id,
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


def _make_inactive(db: Session) -> None:
    staff = db.get(Staff, ACCEPTING_STAFF_ID)
    assert staff is not None
    staff.status = StaffStatus.INACTIVE
    db.flush()


def _assign_to_the_shift(db: Session) -> None:
    db.add(
        RosterAssignment(
            staff_id=ACCEPTING_STAFF_ID,
            shift_id=SHIFT_ID,
            status=RosterStatus.ASSIGNED,
            assignment_type=AssignmentType.REGULAR,
            candidate_source=None,
        )
    )
    db.flush()


def _mark_unavailable(db: Session) -> None:
    shift = db.get(Shift, SHIFT_ID)
    assert shift is not None
    db.add(
        StaffUnavailability(
            staff_id=ACCEPTING_STAFF_ID,
            start_at=shift.start_at - timedelta(hours=1),
            end_at=None,
            reason=AvailabilityReason.UNPLANNED_LEAVE,
        )
    )
    db.flush()


# --------------------------------------------------------------------------- #
# A candidate who passes
# --------------------------------------------------------------------------- #
def test_passes_the_accepted_candidate_and_records_the_snapshot(seeded: Session) -> None:
    case = _make_case(seeded)
    outreach = _offer(seeded, case)

    result = safety_service.validate_accepted_candidate(seeded, case, outreach_id=outreach.id)

    [validation] = _validations(seeded, case)
    assert result.validation is validation
    assert validation.candidate_item_id == outreach.candidate_item_id
    assert validation.hard_constraint_policy_id == 1
    assert validation.is_passed is True
    assert validation.failure_reason is None
    assert validation.validated_at == DEMO_NOW
    assert validation.validation_snapshot == {
        "staff_id": 201,
        "shift_id": 1,
        "policy_id": 1,
        "checked_rules": [code.value for code in HardRuleCode],
        "failed_rules": [],
        "details": {
            "daily_hours": 8,
            "daily_limit": 12,
            "weekly_hours": 8,
            "weekly_limit": 52,
            "projected_consecutive_shifts": 1,
            "consecutive_limit": 7,
        },
    }
    assert case.status is CaseStatus.WAITING_RESPONSE
    assert outreach.status is OutreachStatus.ACCEPTED


def test_opens_a_pending_manual_approval_for_a_head_nurse(seeded: Session) -> None:
    case = _make_case(seeded)
    outreach = _offer(seeded, case)

    result = safety_service.validate_accepted_candidate(seeded, case, outreach_id=outreach.id)

    [approval] = _approvals(seeded, case)
    assert result.approval is approval
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
    outreach = _offer(seeded, case)

    safety_service.validate_accepted_candidate(seeded, case, outreach_id=outreach.id)

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
# A candidate who fails: recorded, never raised
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("change", "code"),
    [
        (_make_inactive, "STAFF_NOT_ACTIVE"),
        (_assign_to_the_shift, "ALREADY_ON_SHIFT"),
        (_mark_unavailable, "UNAVAILABLE"),
    ],
    ids=["inactive", "already_on_the_shift", "unavailable"],
)
def test_a_broken_rule_is_recorded_and_the_offer_cancelled(
    seeded: Session, change: Callable[[Session], None], code: str
) -> None:
    """The situation changed while the offer waited for an answer."""
    case = _make_case(seeded)
    outreach = _offer(seeded, case)
    change(seeded)

    result = safety_service.validate_accepted_candidate(seeded, case, outreach_id=outreach.id)

    [validation] = _validations(seeded, case)
    assert validation.is_passed is False
    assert validation.failure_reason == code
    assert validation.validation_snapshot["failed_rules"] == [code]
    assert _approvals(seeded, case) == []
    assert result.approval is None
    assert outreach.status is OutreachStatus.CANCELLED
    assert outreach.response_at == DEMO_NOW
    [failed] = _audit(seeded, case)
    assert failed.action is AuditAction.SAFETY_FAILED
    assert failed.actor_id == _actor(seeded, ActorName.SAFETY_RULE_ENGINE)
    assert failed.entity_type is EntityType.SAFETY_VALIDATION
    assert failed.entity_id == validation.id
    assert failed.payload == {
        "validation_id": validation.id,
        "staff_id": ACCEPTING_STAFF_ID,
        "outreach_id": outreach.id,
        "failed_rules": [code],
    }
    assert case.status is CaseStatus.WAITING_RESPONSE


def test_every_failed_rule_is_recorded_in_contract_order(seeded: Session) -> None:
    case = _make_case(seeded)
    outreach = _offer(seeded, case)
    _make_inactive(seeded)
    _mark_unavailable(seeded)

    safety_service.validate_accepted_candidate(seeded, case, outreach_id=outreach.id)

    [validation] = _validations(seeded, case)
    assert validation.failure_reason == "STAFF_NOT_ACTIVE,UNAVAILABLE"


def test_a_rule_the_policy_switches_off_is_not_checked(seeded: Session) -> None:
    case = _make_case(seeded)
    outreach = _offer(seeded, case)
    policy_service.get_hard_constraint_policy(seeded).require_active_staff = False
    seeded.flush()
    _make_inactive(seeded)

    safety_service.validate_accepted_candidate(seeded, case, outreach_id=outreach.id)

    [validation] = _validations(seeded, case)
    assert validation.is_passed is True
    assert "STAFF_NOT_ACTIVE" not in validation.validation_snapshot["checked_rules"]


# --------------------------------------------------------------------------- #
# Malformed data raises before anything is written
# --------------------------------------------------------------------------- #
def _assert_nothing_written(db: Session, case: StaffingCase) -> None:
    assert _validations(db, case) == []
    assert _approvals(db, case) == []
    assert _audit(db, case) == []


def test_an_unknown_offer_raises(seeded: Session) -> None:
    case = _make_case(seeded)

    with pytest.raises(ValueError, match="does not belong"):
        safety_service.validate_accepted_candidate(seeded, case, outreach_id=999_999)

    _assert_nothing_written(seeded, case)


def test_an_offer_of_another_case_raises(seeded: Session) -> None:
    case = _make_case(seeded)
    other = _offer(seeded, _make_case(seeded))

    with pytest.raises(ValueError, match="does not belong"):
        safety_service.validate_accepted_candidate(seeded, case, outreach_id=other.id)

    _assert_nothing_written(seeded, case)


def test_an_offer_that_is_not_accepted_yet_raises(seeded: Session) -> None:
    case = _make_case(seeded)
    outreach = _offer(seeded, case, status=OutreachStatus.SENT)

    with pytest.raises(ValueError, match="ACCEPTED"):
        safety_service.validate_accepted_candidate(seeded, case, outreach_id=outreach.id)

    _assert_nothing_written(seeded, case)


def test_an_item_planned_for_another_case_raises(seeded: Session) -> None:
    case = _make_case(seeded)
    outreach = _offer(seeded, case, planned_for=_make_case(seeded))

    with pytest.raises(ValueError, match="belongs to case"):
        safety_service.validate_accepted_candidate(seeded, case, outreach_id=outreach.id)

    _assert_nothing_written(seeded, case)


def test_an_item_proposing_another_shift_raises_before_writing(seeded: Session) -> None:
    """Approval rosters onto proposed_shift_id, so it must be the shift Safety checks."""
    case = _make_case(seeded)
    outreach = _offer(seeded, case, proposed_shift_id=DAY_SHIFT_ID)

    with pytest.raises(ProposedShiftMismatchError):
        safety_service.validate_accepted_candidate(seeded, case, outreach_id=outreach.id)

    _assert_nothing_written(seeded, case)


def test_create_request_rejects_an_item_of_another_case(seeded: Session) -> None:
    case = _make_case(seeded)
    other = _make_case(seeded)
    outreach = _offer(seeded, case, planned_for=other)
    item = seeded.get(CandidateItem, outreach.candidate_item_id)
    assert item is not None

    with pytest.raises(ValueError, match="does not belong"):
        approval_service.create_request(seeded, case=case, item=item)

    assert _approvals(seeded, case) == []
    assert _approvals(seeded, other) == []
