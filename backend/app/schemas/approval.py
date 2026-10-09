from pydantic import BaseModel, ConfigDict, StrictBool

from app.domain.enums import ApprovalMode, CaseStatus
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


class ApprovalDecision(BaseModel):
    """The approver comes from X-Demo-User, never from the body."""

    model_config = ConfigDict(extra="forbid")
    approved: StrictBool
    reason: str | None = None


class ApprovalDecisionResult(BaseModel):
    approval_id: int
    is_approved: bool
    case_id: int
    case_status: CaseStatus
