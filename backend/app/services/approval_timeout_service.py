"""Expire actionable approval attempts using the decision lock order (round 2 PR T)."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import ApprovalRequest, CandidateItem, StaffingCase
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    ActorName,
    AuditAction,
    EntityType,
    OutreachStatus,
)
from app.services import (
    actor_service,
    approval_service,
    audit_service,
    case_facts_service,
    outreach_service,
)
from app.services.offer_timeout_service import _clear_failures, _log_failure
from app.workflow import orchestrator

TIMEOUT_REASON = "The head nurse did not decide before the approval deadline"


@dataclass
class ExpiredApprovals:
    approval_ids: list[int] = field(default_factory=list)
    failed_case_ids: set[int] = field(default_factory=set)


def expire_due_approvals(db: Session) -> ExpiredApprovals:
    """No uncommitted caller writes. Recheck after locks, commit each request independently.

    Timeout and its audit stay outside D11; workflow failures preserve them.
    Historical requests without an accepted offer and stopped cases are untouched.
    Concurrent ticks/decisions serialize on Shift → Request → Offers → Case → Staff.
    """
    due = list(
        db.execute(
            select(ApprovalRequest.id, ApprovalRequest.case_id)
            .join(StaffingCase, StaffingCase.id == ApprovalRequest.case_id)
            .where(
                ApprovalRequest.is_pending.is_(True),
                ApprovalRequest.expires_at <= clock.now(),
                case_facts_service.accepted_offer_for_request(),
                StaffingCase.status.not_in(list(AUTOMATION_STOPPED_STATUSES)),
            )
            .order_by(ApprovalRequest.id)
        )
    )
    db.rollback()
    result = ExpiredApprovals()
    for approval_id, case_id in due:
        try:
            request, case, item, offers = approval_service._lock_decision(db, approval_id, None)
            own = next(
                (
                    row
                    for row in offers
                    if row.id == request.outreach_id
                    and row.case_id == case.id
                    and row.status == OutreachStatus.ACCEPTED
                ),
                None,
            )
            if own is None or clock.now() < request.expires_at:
                db.rollback()
                continue
            request.is_pending = False
            request.is_approved = False
            request.is_timed_out = True
            request.approver_id = None
            request.reason = TIMEOUT_REASON
            request.decided_at = clock.now()
            outreach_service.cancel_offer(db, own)
            audit_service.log(
                db,
                case_id=case.id,
                actor_id=actor_service.component_id(db, ActorName.WORKFLOW_ORCHESTRATOR),
                action=AuditAction.APPROVAL_TIMEOUT,
                entity_type=EntityType.APPROVAL_REQUEST,
                entity_id=request.id,
                payload={
                    "approval_id": request.id,
                    "staff_id": item.staff_id,
                    "outreach_id": own.id,
                    "reason": TIMEOUT_REASON,
                },
            )
            # Workflow completion can release other accepted reserves as well.
            own_items = {
                row.candidate_item_id
                for row in offers
                if row.case_id == case.id and row.status == OutreachStatus.ACCEPTED
            }
            own_items.add(item.id)
            orchestrator.recompute(db, case.id, prepare=outreach_service.promote_reserves)
            result.approval_ids.append(approval_id)
            _clear_failures("Approval expiry", case_id)
            for staff_id in db.scalars(
                select(CandidateItem.staff_id).where(CandidateItem.id.in_(own_items))
            ):
                outreach_service.recompute_affected_cases(
                    db, staff_id=staff_id, own_case_id=case.id
                )
        except approval_service.ApprovalNotPendingError:
            db.rollback()  # Another decision/tick or case completion won the locks.
        except Exception as error:
            db.rollback()
            _log_failure("Approval expiry", case_id, error)
            result.failed_case_ids.add(case_id)
    return result
