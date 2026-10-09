"""Approval lookups for the walking skeleton; decisions arrive in seam 7."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ApprovalRequest, CandidateItem
from app.schemas.approval import PendingApproval


def list_pending(db: Session) -> list[PendingApproval]:
    """Read all pending requests by ID, without flushes, commits or locks.

    Do not hide other cases when a case has duplicate pending requests. Any
    uniqueness enforcement belongs at creation, not on this list read.
    Include the approved candidate's identity and proposed shift for the UI.
    """
    rows = db.execute(
        select(
            ApprovalRequest.id,
            ApprovalRequest.case_id,
            ApprovalRequest.candidate_item_id,
            ApprovalRequest.required_approver_role,
            ApprovalRequest.approval_mode,
            ApprovalRequest.is_pending,
            ApprovalRequest.requested_at,
            CandidateItem.staff_id,
            CandidateItem.proposed_shift_id,
        )
        .join(CandidateItem, CandidateItem.id == ApprovalRequest.candidate_item_id)
        .where(ApprovalRequest.is_pending.is_(True))
        .order_by(ApprovalRequest.id)
    ).mappings()
    return [PendingApproval.model_validate(row) for row in rows]
