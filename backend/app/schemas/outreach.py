"""Offer list shown by the demo LINE simulator."""

from pydantic import BaseModel

from app.domain.enums import CaseStatus, Channel, OutreachStatus
from app.schemas.types import AppDatetime


class OfferView(BaseModel):
    id: int
    case_id: int
    candidate_item_id: int
    staff_id: int
    proposed_shift_id: int
    status: OutreachStatus
    case_status: CaseStatus
    channel: Channel
    sent_at: AppDatetime | None
    response_at: AppDatetime | None
    ward_id: int
    ward_name: str
    shift_start_at: AppDatetime
    shift_end_at: AppDatetime
    can_accept: bool
    can_reject: bool
    blocked_reason: str | None
    cancellation_reason: str | None
    is_assigned: bool
    is_reserve: bool
