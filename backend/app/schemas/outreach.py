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
