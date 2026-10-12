"""
Safety check of one accepted candidate (docs/workflow.md, sections 6.4 and 8).

Safety is not a step of the case (Q31). It runs once per accepted offer, inside the
transaction of the answer. outreach_service.promote_reserves() calls it for the
candidate who just accepted and for a reserve that moves up. The candidate is
re-checked with hard_rule_service.check_items(), the loader wave selection uses,
because the situation can change while the offer waits.

  * Passed: one SAFETY_VALIDATION row and SAFETY_PASSED, then approval_service opens
    the request and writes APPROVAL_REQUESTED.
  * Failed: one row with every failed code and SAFETY_FAILED. The offer becomes
    CANCELLED through outreach_service.cancel_offer(). No approval request. The
    caller recomputes the case status.

Rules:
  * Never commits, never changes case.status and takes no row lock: it runs under
    the locks of the response path (workflow.md 6.11).
  * A broken rule is a recorded result, never an exception. Malformed data (an offer
    that is not the case's or not ACCEPTED, an item of another case or shift) still
    raises before any row is written, and the case becomes FAILED (D11).
  * The offer cap is not checked: the accepted offer is the candidate's own.
"""

from typing import Any, NamedTuple

from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    SafetyValidation,
    Shift,
    StaffingCase,
)
from app.domain.enums import ActorName, AuditAction, EntityType, OutreachStatus
from app.services import (
    actor_service,
    approval_service,
    audit_service,
    hard_rule_service,
    outreach_service,
    policy_service,
)


class ProposedShiftMismatchError(ValueError):
    """The accepted candidate item proposes a different shift than the case's."""


class SafetyResult(NamedTuple):
    validation: SafetyValidation
    # None when the candidate failed Safety
    approval: ApprovalRequest | None
    candidate: CandidateItem


def validate_accepted_candidate(
    db: Session, case: StaffingCase, *, outreach_id: int
) -> SafetyResult:
    """Check one accepted offer against the Hard Rules and record the outcome; flush only."""
    # Seam 4: Safety is given the offer. A case can hold several ACCEPTED offers
    outreach = db.get(CandidateOutreach, outreach_id)
    if outreach is None or outreach.case_id != case.id:
        raise ValueError("The accepted offer does not belong to this case")
    if outreach.status is not OutreachStatus.ACCEPTED:
        raise ValueError("Safety requires an ACCEPTED offer")

    # The two foreign keys do not prove the item was planned for this case
    item = db.get(CandidateItem, outreach.candidate_item_id)
    if item is None:
        raise LookupError(f"No candidate item {outreach.candidate_item_id}")
    plan = db.get(CandidatePlan, item.plan_id)
    if plan is None:
        raise LookupError(f"No candidate plan {item.plan_id}")
    if plan.case_id != case.id:
        raise ValueError(f"Candidate item {item.id} belongs to case {plan.case_id}, not {case.id}")
    if item.proposed_shift_id != case.shift_id:
        raise ProposedShiftMismatchError(
            f"Candidate item {item.id} proposes shift {item.proposed_shift_id}, "
            f"not the case's shift {case.shift_id}"
        )
    shift = db.get(Shift, case.shift_id)
    if shift is None:
        raise LookupError(f"No shift {case.shift_id}")

    # The loader reads without autoflush (seam 12)
    db.flush()
    result = hard_rule_service.check_items(db, shift=shift, items=[item])[item.id].result
    policy_id = policy_service.get_hard_constraint_policy(db).id
    failed_rules = [code.value for code in result.failed_rules]
    validation = SafetyValidation(
        case_id=case.id,
        candidate_item_id=item.id,
        hard_constraint_policy_id=policy_id,
        is_passed=result.passed,
        failure_reason=",".join(failed_rules) or None,
        validation_snapshot={
            "staff_id": item.staff_id,
            "shift_id": shift.id,
            "policy_id": policy_id,
            "checked_rules": [code.value for code in result.checked_rules],
            "failed_rules": failed_rules,
            "details": dict(result.details),
        },
        validated_at=clock.now(),
    )
    db.add(validation)
    # The audit row needs the id, and SessionLocal has autoflush off
    db.flush()
    payload: dict[str, Any] = {"validation_id": validation.id, "staff_id": item.staff_id}
    if not result.passed:
        payload |= {"outreach_id": outreach.id, "failed_rules": failed_rules}
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.component_id(db, ActorName.SAFETY_RULE_ENGINE),
        action=AuditAction.SAFETY_PASSED if result.passed else AuditAction.SAFETY_FAILED,
        entity_type=EntityType.SAFETY_VALIDATION,
        entity_id=validation.id,
        payload=payload,
    )
    if result.passed:
        approval = approval_service.create_request(db, case=case, item=item)
        return SafetyResult(validation=validation, approval=approval, candidate=item)
    # Q7, Q8: a dropped candidate's offer is CANCELLED by the one shared function.
    # This transaction already holds the lock of that row (workflow.md 6.11)
    outreach_service.cancel_offer(db, outreach)
    db.flush()
    return SafetyResult(validation=validation, approval=None, candidate=item)
