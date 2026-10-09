"""
Safety check of the accepted candidate (docs/workflow.md, sections 6.4 and 8).

The walking skeleton has no hard rules yet. The accepted candidate is re-checked
with the Solver's rules (availability_service), because the situation can change
while the offer waits for an answer. If they still hold, the candidate passes and
the case waits for a head nurse's manual approval. The real rule engine replaces
the pass later; the lookups and the approval request stay.

Rules:
  * Never commits and writes no audit row. The `validate_safety` handler logs
    SAFETY_PASSED and APPROVAL_REQUESTED in the same round.
  * "Exactly one" lookups raise instead of taking the first row (section 6.4).
    Inside the handler the error turns the case FAILED (D11).
  * The accepted item must propose the case's own shift: Execute rosters the
    candidate onto item.proposed_shift_id (seam 8), so that has to be the shift
    checked here. A mismatch raises ProposedShiftMismatchError.
  * A candidate who can no longer take the shift raises before any row is
    written. Recording is_passed = false with SAFETY_FAILED and moving on to the
    next candidate needs a section 5 transition that does not exist yet.
"""

from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    Role,
    SafetyValidation,
    Shift,
    StaffingCase,
)
from app.domain.enums import ApprovalMode, OutreachStatus
from app.services import availability_service, policy_service

# No RoleName enum exists; the seed names role 2 this way (docs/workflow.md 10.2)
HEAD_NURSE_ROLE = "HEAD_NURSE"


class ProposedShiftMismatchError(ValueError):
    """The accepted candidate item proposes a different shift than the case's."""


class SafetyResult(NamedTuple):
    validation: SafetyValidation
    approval: ApprovalRequest
    candidate: CandidateItem


def validate_accepted_candidate(db: Session, case: StaffingCase) -> SafetyResult:
    """Pass the case's accepted candidate and open a pending MANUAL approval; flush only."""
    # Seam 4. resume() has flushed the caller's ACCEPTED update before this runs
    outreach = db.scalars(
        select(CandidateOutreach).where(
            CandidateOutreach.case_id == case.id,
            CandidateOutreach.status == OutreachStatus.ACCEPTED,
        )
    ).one()

    # Seam 5: the two foreign keys do not prove the item was planned for this case
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
    availability_service.assert_available(db, shift, item.staff_id)

    validation = SafetyValidation(
        case_id=case.id,
        candidate_item_id=item.id,
        hard_constraint_policy_id=policy_service.get_hard_constraint_policy(db).id,
        is_passed=True,
        failure_reason=None,
        validation_snapshot={},
        validated_at=clock.now(),
    )
    approval = ApprovalRequest(
        case_id=case.id,
        candidate_item_id=item.id,
        required_approver_role=db.scalars(
            select(Role.id).where(Role.name == HEAD_NURSE_ROLE)
        ).one(),
        approval_mode=ApprovalMode.MANUAL,
        is_pending=True,
        approver_id=None,
        is_approved=None,
        reason=None,
        decided_at=None,
        requested_at=clock.now(),
    )
    db.add_all([validation, approval])
    # The audit rows need both ids, and SessionLocal has autoflush off
    db.flush()
    return SafetyResult(validation=validation, approval=approval, candidate=item)
