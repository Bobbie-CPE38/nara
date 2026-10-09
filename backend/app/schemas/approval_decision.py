from pydantic import BaseModel, ConfigDict, StrictBool

from app.domain.enums import CaseStatus


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
