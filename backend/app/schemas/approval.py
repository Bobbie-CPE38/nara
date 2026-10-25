from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.domain.enums import ApprovalMode, ApprovalOutcome, ApprovalSide, CaseStatus
from app.schemas.types import AppDatetime


class ApprovalWardView(BaseModel):
    ward_id: int
    side: ApprovalSide
    status: Literal["PENDING", "APPROVED"]
    # Who approved an APPROVED side: a person (MANUAL) or the system (AUTO, 6.39); None while
    # PENDING
    approval_mode: ApprovalMode | None = None


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
    expires_at: AppDatetime
    home_ward_id: int
    source_ward_id: int | None
    wards: list[ApprovalWardView]
    supervisor_from: AppDatetime


class AutoApprovedApproval(PendingApproval):
    """History is a decision result; approval alone does not guarantee assignment.

    Since round 6 PR EV9 (6.39) a request is here once the system approved any of its sides:
    `is_pending` true means another side still waits; `decided_at` is when the system last
    approved a side of it.
    """

    decided_at: AppDatetime


class ApprovalDecision(BaseModel):
    """The approver comes from X-Demo-User, never from the body."""

    model_config = ConfigDict(extra="forbid")
    approved: StrictBool
    # Semantic reason validation runs after 404/403/409 checks in the service.
    reason: str | None = None
    # Parse semantic values after authorization/stale checks, preserving error order.
    side: str | None = None


class ApprovalDecisionResult(BaseModel):
    approval_id: int
    is_approved: bool | None
    case_id: int
    case_status: CaseStatus
    outcome: ApprovalOutcome
    reason: str | None = None
    failed_rules: list[str] = Field(default_factory=list)
