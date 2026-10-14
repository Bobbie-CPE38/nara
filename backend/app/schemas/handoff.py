"""Requests and answers of the manual exits of MANUAL_HANDOFF (docs/workflow.md, section 9.4)."""

from pydantic import BaseModel, Field

from app.core.constants import MAX_BIGINT
from app.domain.enums import CaseStatus
from app.schemas.types import AppDatetime


class HandoffCase(BaseModel):
    """One item of GET /cases?status=..."""

    id: int
    status: CaseStatus
    shift_id: int
    ward_id: int
    required_replacement_time: AppDatetime
    created_at: AppDatetime
    # null when the case has no gap row (it failed before ASSESSING stored one)
    headcount_gap: int | None
    assigned_count: int
    # Only a MANUAL_HANDOFF case can be staffed or closed by hand. FAILED is listed, not managed
    can_manage: bool


class HandoffCandidate(BaseModel):
    """One active staff member of the ward, with what stops a manual assignment."""

    staff_id: int
    first_name: str
    last_name: str
    role_id: int
    role_name: str
    # Hard Rule codes that fail now. Empty = can be assigned. Read without locks:
    # the assignment itself checks again and is the authority
    blocking_rules: list[str]
    # Running cases where this person has a live offer. An assignment may cancel those
    other_case_ids: list[int]


class ManualAssignmentRequest(BaseModel):
    staff_id: int = Field(gt=0, le=MAX_BIGINT)
    # A note. It never makes a failed Hard Rule pass. Length is checked in the service
    reason: str | None = None
    # Must be true to go ahead when the assignment cancels the person's offers elsewhere
    confirm_conflicts: bool = False


class ManualAssignmentResult(BaseModel):
    manual_assignment_id: int
    assignment_id: int
    staff_id: int
    case_id: int
    case_status: CaseStatus
    cancelled_outreach_ids: list[int]


class CloseCaseRequest(BaseModel):
    # Required and not blank. Checked in the service so the error order stays 404, 403, 409, 422
    reason: str | None = None


class CloseCaseResult(BaseModel):
    case_id: int
    case_status: CaseStatus
