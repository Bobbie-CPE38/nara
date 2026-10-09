from pydantic import BaseModel

from app.domain.enums import ApprovalMode
from app.schemas.types import AppDatetime


class PendingApproval(BaseModel):
    """One item of GET /approvals?pending=true (workflow.md, seam 6)."""

    id: int
    case_id: int
    candidate_item_id: int
    required_approver_role: int | None
    approval_mode: ApprovalMode
    is_pending: bool
    staff_id: int
    proposed_shift_id: int
    requested_at: AppDatetime
