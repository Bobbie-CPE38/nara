"""Offer list shown by the demo LINE simulator."""

from typing import Literal

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
    expires_at: AppDatetime | None
    ward_id: int
    ward_name: str
    shift_start_at: AppDatetime
    shift_end_at: AppDatetime
    can_accept: bool
    can_reject: bool
    blocked_reason: Literal["CASE_STOPPED", "OFFER_EXPIRED", "AWAITING_OTHER_CASE"] | None
    cancellation_reason: str | None
    final_outcome: str | None = None
    final_message: str | None = None
    final_delivery_status: str | None = None
    is_assigned: bool
    is_reserve: bool
