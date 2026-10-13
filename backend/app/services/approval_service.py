"""Approval requests: opened after Safety passes, listed, and decided.

The orchestrator owns decision commits."""

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core import clock
from app.core.constants import HEAD_NURSE_ROLE, MAX_APPROVAL_REASON_LENGTH
from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    Role,
    Shift,
    StaffingCase,
)
from app.domain.constraints.codes import HardRuleCode
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    ActorName,
    ApprovalMode,
    AuditAction,
    CaseStatus,
    EntityType,
    OutreachStatus,
)
from app.schemas.approval import PendingApproval
from app.services import (
    actor_service,
    audit_service,
    case_facts_service,
    hard_rule_service,
    outreach_service,
    policy_service,
    roster_service,
)
from app.services.wave_service import plan_items
from app.workflow import orchestrator

_SCHEDULING_RULES = frozenset(
    {
        HardRuleCode.ALREADY_ON_SHIFT,
        HardRuleCode.SHIFT_CONFLICT,
        HardRuleCode.INSUFFICIENT_REST,
        HardRuleCode.DAILY_HOURS_EXCEEDED,
        HardRuleCode.WEEKLY_HOURS_EXCEEDED,
        HardRuleCode.CONSECUTIVE_SHIFTS_EXCEEDED,
    }
)


class ApprovalNotFoundError(LookupError):
    """No approval request has this ID."""


class ApproverRoleError(ValueError):
    """The authenticated staff member does not have the required role."""


class ApprovalNotPendingError(ValueError):
    """The request has already been decided."""


class ApprovalOfferConflictError(ValueError):
    """The selected request no longer has exactly one accepted offer."""


class ApprovalLockRetryError(ValueError):
    """Concurrent offer changes prevented acquiring a stable lock set; retry."""


class InvalidApprovalReasonError(ValueError):
    """A rejection needs a nonblank reason; all reasons must fit the length limit."""


def create_request(
    db: Session, *, case: StaffingCase, item: CandidateItem, outreach: CandidateOutreach
) -> ApprovalRequest:
    """Open the pending MANUAL request of one candidate who passed Safety (seam 5).

    safety_service calls this inside the transaction of the answer. Flushes and
    writes APPROVAL_REQUESTED. Never commits and never changes case.status.
    """
    # The two foreign keys do not prove the item was planned for this case
    plan = db.get(CandidatePlan, item.plan_id)
    if plan is None or plan.case_id != case.id:
        raise ValueError(f"Candidate item {item.id} does not belong to case {case.id}")
    if outreach.case_id != case.id or outreach.candidate_item_id != item.id:
        raise ValueError("Offer does not match the approval case and item")
    if outreach.status != OutreachStatus.ACCEPTED:
        raise ValueError("Approval requires an accepted offer")
    now = clock.now()
    request = ApprovalRequest(
        outreach_id=outreach.id,
        expires_at=now
        + timedelta(seconds=policy_service.get_approval_policy(db).approval_timeout_seconds),
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
        requested_at=now,
    )
    db.add(request)
    # The audit row needs the id, and SessionLocal has autoflush off
    db.flush()
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR),
        action=AuditAction.APPROVAL_REQUESTED,
        entity_type=EntityType.APPROVAL_REQUEST,
        entity_id=request.id,
        payload={"approval_id": request.id, "approval_mode": request.approval_mode.value},
    )
    return request


def decide(
    db: Session,
    *,
    approval_id: int,
    staff_id: int,
    role_id: int,
    actor_id: int,
    approved: bool,
    reason: str | None = None,
) -> tuple[ApprovalRequest, StaffingCase]:
    """Decide one candidate and execute immediately, then recompute the case.

    Lock Shift → Request → own-case and candidate's foreign Offers in one ID-
    ordered query → case → whole-plan Staff. Refresh state after lock waits.
    The decision/audit is outside D11; assignment and reserve promotion run in
    recompute's savepoint. Workflow failure preserves the decision, fails the
    case, and rolls back its assignment. Foreign notifications follow commit.
    """
    request, case, item, offers = lock_approval_attempt(db, approval_id, role_id)
    own = [
        row
        for row in offers
        if row.case_id == case.id
        and row.id == request.outreach_id
        and row.status == OutreachStatus.ACCEPTED
    ]
    if len(own) != 1:
        raise ApprovalOfferConflictError(
            "The request no longer has one accepted offer; refresh approvals"
        )
    live_offer_ids = {
        row.id
        for row in offers
        if row.case_id == case.id and row.status in {OutreachStatus.SENT, OutreachStatus.ACCEPTED}
    }
    if clock.now() >= request.expires_at:
        raise ApprovalNotPendingError("The approval request has expired")
    stored_reason = reason if approved or reason is None else reason.strip()
    if stored_reason is not None and len(stored_reason) > MAX_APPROVAL_REASON_LENGTH:
        raise InvalidApprovalReasonError(
            f"reason must be at most {MAX_APPROVAL_REASON_LENGTH} characters"
        )
    if not approved and not stored_reason:
        raise InvalidApprovalReasonError("A rejection requires a nonblank reason")
    outreach = own[0]
    request.approver_id = staff_id
    request.is_approved = approved
    request.reason = stored_reason
    request.decided_at = clock.now()
    request.is_pending = False
    payload = {"approval_id": request.id, "reason": request.reason}
    if not approved:
        outreach_service.cancel_offer(db, outreach)
        payload |= {"staff_id": item.staff_id, "outreach_id": outreach.id}
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_id,
        action=AuditAction.APPROVAL_APPROVED if approved else AuditAction.APPROVAL_REJECTED,
        entity_type=EntityType.APPROVAL_REQUEST,
        entity_id=request.id,
        payload=payload,
    )
    foreign_cases: set[int] = set()

    def prepare(db: Session, case: StaffingCase) -> None:
        if approved:
            assignment = roster_service.create_replacement(db, case, approval=request)
            cancelled = _cancel_conflicting_offers(db, case, item, offers)
            foreign_cases.update(row.case_id for row in cancelled)
            audit_service.log(
                db,
                case_id=case.id,
                actor_id=actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR),
                action=AuditAction.ASSIGNMENT_CREATED,
                entity_type=EntityType.ROSTER_ASSIGNMENT,
                entity_id=assignment.id,
                payload={
                    "assignment_id": assignment.id,
                    "staff_id": assignment.staff_id,
                    "assignment_type": assignment.assignment_type.value,
                    "cancelled_outreach_ids": [row.id for row in cancelled],
                },
            )
        outreach_service.promote_reserves(db, case)

    orchestrator.recompute(db, case.id, prepare=prepare)
    # Completion and failed promoted reserves release other staff commitments too.
    notify_staff = {item.staff_id}
    notify_staff.update(
        db.scalars(
            select(CandidateItem.staff_id)
            .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
            .where(
                CandidateOutreach.case_id == case.id,
                CandidateOutreach.id.in_(live_offer_ids),
                CandidateOutreach.status == OutreachStatus.CANCELLED,
            )
        )
    )
    for candidate_id in sorted(notify_staff):
        outreach_service.recompute_affected_cases(
            db,
            staff_id=candidate_id,
            own_case_id=case.id,
            additional_case_ids=foreign_cases if candidate_id == item.staff_id else (),
        )
    return request, case


def lock_approval_attempt(
    db: Session,
    approval_id: int,
    role_id: int | None,
) -> tuple[ApprovalRequest, StaffingCase, CandidateItem, list[CandidateOutreach]]:
    """Acquire the full lock set before writes; restart if an offer appeared while waiting.

    role_id=None is reserved for the timeout job; HTTP decisions always pass a role.
    Caller must have no uncommitted writes: a phantom restart rolls back.

    Staff locks prevent another wave sending once held, but a wave may have
    committed between our offer query and that lock. Never acquire those new
    Offer locks after case/Staff: release and restart the agreed order instead.
    """
    for _ in range(5):
        initial = db.get(ApprovalRequest, approval_id)
        if initial is None:
            raise ApprovalNotFoundError(f"No approval request {approval_id}")
        initial_case = db.get(StaffingCase, initial.case_id)
        if initial_case is None:
            raise LookupError(f"No case {initial.case_id}")
        db.scalar(
            select(Shift).where(Shift.id == initial_case.shift_id).with_for_update(key_share=True)
        )
        request = db.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        ).one()
        if role_id is not None and role_id != request.required_approver_role:
            raise ApproverRoleError("The staff member does not have the required approver role")
        if not request.is_pending:
            raise ApprovalNotPendingError(f"Approval request {approval_id} is not pending")
        item = db.get(CandidateItem, request.candidate_item_id)
        if item is None:
            raise LookupError(f"No candidate item {request.candidate_item_id}")
        offer_query = _decision_offer_query(request.case_id, item.staff_id)
        offers = list(
            db.scalars(
                offer_query.order_by(CandidateOutreach.id)
                .with_for_update(key_share=True, of=CandidateOutreach)
                .execution_options(populate_existing=True)
            )
        )
        case = db.scalars(
            select(StaffingCase)
            .where(StaffingCase.id == request.case_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        ).one()
        if case.status in AUTOMATION_STOPPED_STATUSES:
            raise ApprovalNotPendingError("This case has stopped; the request cannot be decided")
        if case.status not in {CaseStatus.WAITING_RESPONSE, CaseStatus.WAITING_APPROVAL}:
            raise ApprovalNotPendingError("This case is not waiting for a decision")
        hard_rule_service.lock_staff(
            db, [candidate.staff_id for candidate in plan_items(db, case.id)] + [item.staff_id]
        )
        current_ids = set(db.scalars(offer_query.with_only_columns(CandidateOutreach.id)))
        if current_ids <= {row.id for row in offers}:
            return request, case, item, offers
        db.rollback()
    raise ApprovalLockRetryError(
        "Could not lock a stable offer set after five attempts; retry the decision"
    )


def _decision_offer_query(case_id: int, staff_id: int) -> Select[CandidateOutreach]:
    """One definition for initial offer locks and the post-Staff phantom check."""
    return (
        select(CandidateOutreach)
        .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
        .where(
            or_(
                CandidateOutreach.case_id == case_id,
                (CandidateItem.staff_id == staff_id)
                & CandidateOutreach.status.in_([OutreachStatus.SENT, OutreachStatus.ACCEPTED]),
            )
        )
    )


def _cancel_conflicting_offers(
    db: Session, case: StaffingCase, item: CandidateItem, offers: list[CandidateOutreach]
) -> list[CandidateOutreach]:
    """After assignment, cancel foreign offers unsafe against the new roster.

    This is not execution validation of the approved candidate (Q38). It checks
    the other proposed shifts for overlap, rest, hours and consecutive shifts.
    Safety's shared evaluator and current policy provide the exact semantics.
    """
    cancelled = []
    for row in offers:
        if row.case_id == case.id or row.status not in {
            OutreachStatus.SENT,
            OutreachStatus.ACCEPTED,
        }:
            continue
        foreign_case = db.get(StaffingCase, row.case_id)
        if foreign_case is None or foreign_case.status in AUTOMATION_STOPPED_STATUSES:
            continue
        candidate = db.get(CandidateItem, row.candidate_item_id)
        assert candidate is not None and candidate.staff_id == item.staff_id
        shift = db.get(Shift, candidate.proposed_shift_id)
        if shift is None:
            raise LookupError(f"No shift {candidate.proposed_shift_id}")
        check = hard_rule_service.check_items(db, shift=shift, items=[candidate])[candidate.id]
        if _SCHEDULING_RULES.intersection(check.result.failed_rules):
            outreach_service.cancel_offer(db, row)
            cancelled.append(row)
    db.flush()
    return cancelled


def list_pending(db: Session) -> list[PendingApproval]:
    """Read pending requests of running cases by ID, without writes or locks.

    Do not hide other cases when a case has duplicate pending requests. Any
    uniqueness enforcement belongs at creation, not on this list read.
    Include the candidate's identity and proposed shift for the UI. Stopped
    cases keep undecided requests as history, but those cannot be acted on and
    are excluded here, including requests left behind by D11 failures. Pending
    requests whose offers were cancelled are also excluded on running cases.
    """
    with db.no_autoflush:
        rows = db.execute(
            select(
                ApprovalRequest.id,
                ApprovalRequest.case_id,
                ApprovalRequest.candidate_item_id,
                ApprovalRequest.required_approver_role,
                ApprovalRequest.approval_mode,
                ApprovalRequest.is_pending,
                ApprovalRequest.requested_at,
                ApprovalRequest.expires_at,
                CandidateItem.staff_id,
                CandidateItem.proposed_shift_id,
            )
            .join(CandidateItem, CandidateItem.id == ApprovalRequest.candidate_item_id)
            .join(StaffingCase, StaffingCase.id == ApprovalRequest.case_id)
            .where(
                ApprovalRequest.is_pending.is_(True),
                ApprovalRequest.expires_at > clock.now(),
                case_facts_service.accepted_offer_for_request(),
                StaffingCase.status.not_in(list(AUTOMATION_STOPPED_STATUSES)),
            )
            .order_by(ApprovalRequest.id)
        ).mappings()
        return [PendingApproval.model_validate(row) for row in rows]
