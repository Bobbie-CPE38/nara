"""Approval requests: opened after Safety passes, listed, and decided.

The orchestrator owns decision commits."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import timedelta
from fractions import Fraction
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.engine import Connection, RowMapping, Transaction
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import ColumnElement, Select

from app.core import clock
from app.core.constants import HEAD_NURSE_ROLE, MAX_APPROVAL_REASON_LENGTH, SUPERVISOR_ROLE
from app.db.models import (
    ApprovalRequest,
    ApprovalWardDecision,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    Role,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    Ward,
)
from app.domain.constraints.score_breakdown import display_number
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    ActorName,
    ApprovalMode,
    ApprovalOutcome,
    ApprovalSide,
    ApproverCapacity,
    AuditAction,
    CandidateSource,
    CaseStatus,
    EntityType,
    OutreachStatus,
)
from app.schemas.approval import ApprovalDecisionResult, AutoApprovedApproval, PendingApproval
from app.services import (
    actor_service,
    approval_wards,
    audit_service,
    case_facts_service,
    hard_rule_service,
    offer_conflict_service,
    outreach_service,
    policy_service,
    roster_service,
)
from app.services.wave_service import plan_items
from app.workflow import orchestrator


class ApprovalNotFoundError(LookupError):
    """No approval request has this ID."""


class ApproverRoleError(ValueError):
    """The authenticated staff member does not have the required role."""


class ApproverWardError(ValueError):
    """The authenticated staff member is not of the ward the shift belongs to."""


class ApprovalNotPendingError(ValueError):
    """The request has already been decided."""


class ApprovalOfferConflictError(ValueError):
    """The selected request no longer has exactly one accepted offer."""


class ApprovalLockRetryError(ValueError):
    """Concurrent offer changes prevented acquiring a stable lock set; retry."""


class InvalidApprovalReasonError(ValueError):
    """A rejection needs a nonblank reason; all reasons must fit the length limit."""


@dataclass(frozen=True)
class AutoApprovalBatch:
    """Authorization for one locked ward snapshot, bound to its outer transaction."""

    ward_id: int
    pending_count: int
    approver_count: int
    cap: Fraction
    approval_ids: frozenset[int]
    connection: Connection
    transaction: Transaction


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
    staff_id: int | None,
    role_id: int | None,
    home_ward_id: int | None,
    actor_id: int,
    approved: bool,
    reason: str | None = None,
    side: str | None = None,
) -> tuple[ApprovalRequest, StaffingCase]:
    """Decide one candidate and execute immediately, then recompute the case.

    The approver needs the required role and must be of the ward of the shift
    (workflow.md section 6.12). Both refusals come before the pending check.

    Lock Ward → Shift → Request → own-case and candidate's foreign Offers in one ID-
    ordered query → case → whole-plan Staff. Refresh state after lock waits.
    The decision/audit is outside D11; assignment and reserve promotion run in
    recompute's savepoint. Workflow failure preserves the decision, fails the
    case, and rolls back its assignment. Foreign notifications follow commit.
    """
    if role_id is None or staff_id is None:
        raise ApproverRoleError("A manual decision requires an authenticated approver")
    return _decide(
        db,
        approval_id=approval_id,
        staff_id=staff_id,
        role_id=role_id,
        home_ward_id=home_ward_id,
        actor_id=actor_id,
        approved=approved,
        reason=reason,
        side=side,
    )


def decide_automatic(
    db: Session,
    *,
    approval_id: int,
    batch: AutoApprovalBatch,
    notifications: list[tuple[int, int, tuple[int, ...]]],
) -> tuple[ApprovalRequest, StaffingCase]:
    """System-only decision authorized by an explicit, still-locked ward snapshot."""
    if (
        not isinstance(batch, AutoApprovalBatch)
        or batch.connection is not db.connection()
        or batch.transaction is not db.connection().get_transaction()
        or not batch.transaction.is_active
        or batch.pending_count <= batch.cap
        or approval_id not in batch.approval_ids
    ):
        raise ApproverRoleError("Automatic approval requires a locked ward batch")
    return _decide(
        db,
        approval_id=approval_id,
        staff_id=None,
        role_id=None,
        home_ward_id=None,
        actor_id=None,
        approved=True,
        batch=batch,
        notifications=notifications,
    )


def _decide(
    db: Session,
    *,
    approval_id: int,
    staff_id: int | None,
    role_id: int | None,
    home_ward_id: int | None,
    actor_id: int | None,
    approved: bool,
    reason: str | None = None,
    batch: AutoApprovalBatch | None = None,
    side: str | None = None,
    notifications: list[tuple[int, int, tuple[int, ...]]] | None = None,
) -> tuple[ApprovalRequest, StaffingCase]:
    """Shared lock, validation, assignment and audit path for both decision entry points."""
    request, case, item, offers = lock_approval_attempt(
        db,
        approval_id,
        role_id,
        home_ward_id,
        lock_ward=True,
        restart_batch=batch is not None,
        side=side,
    )
    if batch is not None:
        target_shift = db.get(Shift, case.shift_id)
        if (
            not isinstance(batch, AutoApprovalBatch)
            or target_shift is None
            or target_shift.ward_id != batch.ward_id
            or item.source != CandidateSource.SAME_WARD
            or item.source_assignment_id is not None
        ):
            raise ApprovalNotPendingError("This request requires a human approver")
        actor_id = actor_service.component_id(db, ActorName.SYSTEM)
        staff_id = None
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
    selected_side = None
    if batch is None:
        assert role_id is not None
        selected_side = approval_wards.select_side(
            db,
            request,
            item,
            role_id=role_id,
            home_ward_id=home_ward_id,
            side=side,
        )
        if (
            db.scalar(
                select(ApprovalWardDecision.id).where(
                    ApprovalWardDecision.approval_request_id == request.id,
                    ApprovalWardDecision.side == selected_side,
                )
            )
            is not None
        ):
            raise ApprovalNotPendingError("This ward side has already decided")
    stored_reason = reason if approved or reason is None else reason.strip()
    if stored_reason is not None and len(stored_reason) > MAX_APPROVAL_REASON_LENGTH:
        raise InvalidApprovalReasonError(
            f"reason must be at most {MAX_APPROVAL_REASON_LENGTH} characters"
        )
    if not approved and not stored_reason:
        raise InvalidApprovalReasonError("A rejection requires a nonblank reason")
    if selected_side is not None:
        assert staff_id is not None
        role_name = db.scalar(select(Role.name).where(Role.id == role_id))
        capacity = (
            ApproverCapacity.SUPERVISOR
            if role_name == SUPERVISOR_ROLE
            else ApproverCapacity.HEAD_NURSE
        )
        wards = approval_wards.required_wards(db, item)
        db.add(
            ApprovalWardDecision(
                approval_request_id=request.id,
                ward_id=wards[selected_side],
                side=selected_side,
                approver_id=staff_id,
                decided_as=capacity,
                is_approved=approved,
                reason=stored_reason,
                decided_at=clock.now(),
            )
        )
        db.flush()
        approved_sides = set(
            db.scalars(
                select(ApprovalWardDecision.side).where(
                    ApprovalWardDecision.approval_request_id == request.id,
                    ApprovalWardDecision.is_approved.is_(True),
                )
            )
        )
        if approved and not set(wards) <= approved_sides:
            assert actor_id is not None
            audit_service.log(
                db,
                case_id=case.id,
                actor_id=actor_id,
                action=AuditAction.APPROVAL_WARD_APPROVED,
                entity_type=EntityType.APPROVAL_REQUEST,
                entity_id=request.id,
                payload={
                    "approval_id": request.id,
                    "ward_id": wards[selected_side],
                    "side": selected_side.value,
                    "decided_as": capacity.value,
                },
            )
            db.commit()
            return request, case
    outreach = own[0]
    if batch is not None:
        request.approval_mode = ApprovalMode.AUTO
    request.approver_id = staff_id
    request.is_approved = approved
    request.reason = stored_reason
    request.decided_at = clock.now()
    request.is_pending = False
    payload: dict[str, Any] = {"approval_id": request.id, "reason": request.reason}
    if isinstance(batch, AutoApprovalBatch):
        payload |= {
            "approval_mode": ApprovalMode.AUTO.value,
            "pending_count": batch.pending_count,
            "approver_count": batch.approver_count,
            "cap": display_number(batch.cap),
        }
    if not approved:
        outreach_service.cancel_offer(db, outreach)
        payload |= {"staff_id": item.staff_id, "outreach_id": outreach.id}
    assert actor_id is not None
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
            cancelled = offer_conflict_service.cancel_conflicting_offers(
                db,
                case=case,
                assignment=assignment,
                offers=offers,
                actor_id=actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR),
                source="APPROVAL",
            )
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
        additional = foreign_cases if candidate_id == item.staff_id else ()
        if notifications is not None:
            notifications.append((candidate_id, case.id, tuple(additional)))
        else:
            outreach_service.recompute_affected_cases(
                db,
                staff_id=candidate_id,
                own_case_id=case.id,
                additional_case_ids=additional,
            )
    return request, case


def lock_approval_attempt(
    db: Session,
    approval_id: int,
    role_id: int | None,
    home_ward_id: int | None = None,
    *,
    lock_ward: bool = False,
    restart_batch: bool = False,
    side: str | None = None,
) -> tuple[ApprovalRequest, StaffingCase, CandidateItem, list[CandidateOutreach]]:
    """Acquire the full lock set before writes; restart if an offer appeared while waiting.

    role_id=None skips role/ward authorization for the timeout job or a verified
    auto-approval batch. decide_automatic() validates it before calling this helper.
    HTTP decisions always pass both the authenticated role and home ward.
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
        if lock_ward:
            ward_id = db.scalar(select(Shift.ward_id).where(Shift.id == initial_case.shift_id))
            if ward_id is None:
                raise LookupError(f"No shift {initial_case.shift_id}")
            lock_ward_row(db, ward_id)
        # No application path moves a shift to another ward, so the ward read
        # before acquiring this Shift lock remains valid for the decision
        item_hint = db.get(CandidateItem, initial.candidate_item_id)
        if item_hint is None:
            raise LookupError(f"No candidate item {initial.candidate_item_id}")
        shift_ids = {initial_case.shift_id}
        if item_hint.source_assignment_id is not None:
            source_shift_id = db.scalar(
                select(RosterAssignment.shift_id).where(
                    RosterAssignment.id == item_hint.source_assignment_id
                )
            )
            if source_shift_id is None:
                raise LookupError(f"No source assignment {item_hint.source_assignment_id}")
            shift_ids.add(source_shift_id)
        list(
            db.scalars(
                select(Shift)
                .where(Shift.id.in_(shift_ids))
                .order_by(Shift.id)
                .with_for_update(key_share=True)
                .execution_options(populate_existing=True)
            )
        )
        request = db.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        ).one()
        if role_id is not None:
            role_name, allowed = approval_wards.authority(
                db,
                request,
                item_hint,
                role_id=role_id,
                home_ward_id=home_ward_id,
                side=side,
            )
            required_name = db.scalar(
                select(Role.name).where(Role.id == request.required_approver_role)
            )
            if required_name != HEAD_NURSE_ROLE or role_name not in {
                HEAD_NURSE_ROLE,
                SUPERVISOR_ROLE,
            }:
                raise ApproverRoleError("Only a Head Nurse or Supervisor may decide")
            if not allowed:
                message = (
                    "The staff member is not a head nurse of the shift's ward"
                    if role_name == HEAD_NURSE_ROLE and item_hint.source_assignment_id is None
                    else "The approver cannot decide this ward side yet"
                )
                raise ApproverWardError(message)
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
        if restart_batch:
            raise ApprovalLockRetryError("Restart the whole locked auto-approval batch")
        db.rollback()
    raise ApprovalLockRetryError(
        "Could not lock a stable offer set after five attempts; retry the decision"
    )


def _decision_offer_query(case_id: int, staff_id: int) -> Select[CandidateOutreach]:
    """One definition for initial offer locks and the post-Staff phantom check."""
    return decision_offers_query({case_id}, {staff_id})


def decision_offers_query(
    case_ids: Collection[int], staff_ids: Collection[int]
) -> Select[CandidateOutreach]:
    return (
        select(CandidateOutreach)
        .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
        .where(
            or_(
                CandidateOutreach.case_id.in_(case_ids),
                CandidateItem.staff_id.in_(staff_ids)
                & CandidateOutreach.status.in_([OutreachStatus.SENT, OutreachStatus.ACCEPTED]),
            )
        )
    )


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
            .where(*actionable_pending())
            .order_by(ApprovalRequest.id)
        ).mappings()
        return [PendingApproval.model_validate(row) for row in _enrich_wards(db, list(rows))]


def actionable_pending() -> tuple[ColumnElement[bool], ...]:
    """Requests a person or the auto-approval job can still decide right now.

    One definition for the pending list and the auto-approval queue. The query
    must join STAFFING_CASES. Read the clock when the query is built.
    """
    return (
        ApprovalRequest.is_pending.is_(True),
        ApprovalRequest.expires_at > clock.now(),
        case_facts_service.accepted_offer_for_request(),
        StaffingCase.status.not_in(list(AUTOMATION_STOPPED_STATUSES)),
    )


def lock_ward_row(db: Session, ward_id: int) -> None:
    """Lock the WARD row so decisions of one ward run one at a time (6.11, 6.22).

    with_for_update(key_share=True) without read=True renders FOR NO KEY UPDATE
    on PostgreSQL, which conflicts with another FOR NO KEY UPDATE.
    """
    db.scalars(select(Ward).where(Ward.id == ward_id).with_for_update(key_share=True)).one()


def list_auto_approved(
    db: Session, *, role_id: int, home_ward_id: int
) -> list[AutoApprovedApproval]:
    """Newest 50 system decisions: own ward for Head Nurse, all wards for Supervisor."""
    with db.no_autoflush:
        role = db.scalar(select(Role.name).where(Role.id == role_id))
        if role not in {HEAD_NURSE_ROLE, SUPERVISOR_ROLE}:
            raise ApproverRoleError("Only Head Nurses and Supervisors can read auto approvals")
        query = (
            select(
                ApprovalRequest.id,
                ApprovalRequest.case_id,
                ApprovalRequest.candidate_item_id,
                ApprovalRequest.required_approver_role,
                ApprovalRequest.approval_mode,
                ApprovalRequest.is_pending,
                ApprovalRequest.requested_at,
                ApprovalRequest.expires_at,
                ApprovalRequest.decided_at,
                CandidateItem.staff_id,
                CandidateItem.proposed_shift_id,
            )
            .join(CandidateItem, CandidateItem.id == ApprovalRequest.candidate_item_id)
            .join(StaffingCase, StaffingCase.id == ApprovalRequest.case_id)
            .join(Shift, Shift.id == StaffingCase.shift_id)
            .where(
                ApprovalRequest.approval_mode == ApprovalMode.AUTO,
                ApprovalRequest.is_pending.is_(False),
                ApprovalRequest.is_approved.is_(True),
                ApprovalRequest.decided_at.is_not(None),
            )
        )
        if role == HEAD_NURSE_ROLE:
            query = query.where(Shift.ward_id == home_ward_id)
        rows = db.execute(
            query.order_by(ApprovalRequest.decided_at.desc(), ApprovalRequest.id.desc()).limit(50)
        ).mappings()
        return [AutoApprovedApproval.model_validate(row) for row in _enrich_wards(db, list(rows))]


def _enrich_wards(db: Session, rows: Sequence[RowMapping]) -> list[dict[str, Any]]:
    """Enrich pending requests and approved AUTO history, never rejected history.

    A general closed-request list must add REJECTED side status before reusing this helper.
    """
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    source_shift = aliased(Shift)
    metadata = {
        approval_id: (home, destination, source)
        for approval_id, home, destination, source in db.execute(
            select(ApprovalRequest.id, Staff.home_ward_id, Shift.ward_id, source_shift.ward_id)
            .join(CandidateItem, CandidateItem.id == ApprovalRequest.candidate_item_id)
            .join(Staff, Staff.id == CandidateItem.staff_id)
            .join(Shift, Shift.id == CandidateItem.proposed_shift_id)
            .outerjoin(RosterAssignment, RosterAssignment.id == CandidateItem.source_assignment_id)
            .outerjoin(source_shift, source_shift.id == RosterAssignment.shift_id)
            .where(ApprovalRequest.id.in_(ids))
        )
    }
    decided = set(
        db.execute(
            select(
                ApprovalWardDecision.approval_request_id,
                ApprovalWardDecision.side,
            ).where(
                ApprovalWardDecision.approval_request_id.in_(ids),
                ApprovalWardDecision.is_approved.is_(True),
            )
        )
    )
    delay = policy_service.get_approval_policy(db).supervisor_after_seconds
    result = []
    for row in rows:
        home, destination, source = metadata[row["id"]]
        wards = {ApprovalSide.DESTINATION: destination}
        if source is not None:
            wards[ApprovalSide.SOURCE] = source
        result.append(
            dict(row)
            | {
                "home_ward_id": home,
                "source_ward_id": source,
                "supervisor_from": row["requested_at"] + timedelta(seconds=delay),
                "wards": [
                    {
                        "ward_id": ward_id,
                        "side": side,
                        "status": "APPROVED"
                        if (row["id"], side) in decided
                        or (not row["is_pending"] and row["approval_mode"] == ApprovalMode.AUTO)
                        else "PENDING",
                    }
                    for side, ward_id in wards.items()
                ],
            }
        )
    return result


def decision_result(
    db: Session, *, request: ApprovalRequest, case: StaffingCase
) -> ApprovalDecisionResult:
    """Approval state and execution outcome are separate (workflow 9.6)."""
    reason = None
    failed_rules: list[str] = []
    if request.is_pending:
        outcome = ApprovalOutcome.WAITING_OTHER_WARD
    elif request.is_approved is False:
        outcome = ApprovalOutcome.REJECTED
    elif case.status == CaseStatus.FAILED:
        outcome = ApprovalOutcome.EXECUTION_FAILED
    else:
        outcome = ApprovalOutcome.ASSIGNED
        # C2 writes this audit when execution's final transfer checks refuse a move.
        # Read the raw reason so historical reason codes remain readable after C3.
        failure = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.case_id == case.id,
                AuditLog.action == AuditAction.TRANSFER_CHECK_FAILED,
                AuditLog.payload["outreach_id"].as_integer() == request.outreach_id,
            )
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
        if failure is not None:
            outcome = ApprovalOutcome.TRANSFER_CANCELLED
            reason = failure.payload.get("reason")
            failed_rules = failure.payload.get("failed_rules", [])
    return ApprovalDecisionResult(
        approval_id=request.id,
        is_approved=request.is_approved,
        case_id=case.id,
        case_status=case.status,
        outcome=outcome,
        reason=reason,
        failed_rules=failed_rules,
    )
