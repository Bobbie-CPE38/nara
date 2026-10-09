from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import ApprovalMode


class PendingApproval(BaseModel):
    """One item of GET /approvals?pending=true (workflow.md, seam 6)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    candidate_item_id: int
    required_approver_role: int | None
    approval_mode: ApprovalMode
    is_pending: bool
    requested_at: datetime
