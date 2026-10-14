"""PATCH /unavailability/{id} (docs/workflow.md, section 9.5)."""

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.domain.enums import OutreachStatus
from app.schemas.types import AppDatetime


class EndAtChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Required and timezone-aware. An open end (null) cannot be set back
    end_at: AwareDatetime


class OverlappingOfferView(BaseModel):
    outreach_id: int
    case_id: int
    status: OutreachStatus


class EndAtChangeResult(BaseModel):
    unavailability_id: int
    staff_id: int
    start_at: AppDatetime
    end_at: AppDatetime
    previous_end_at: AppDatetime | None
    # Reported, not changed: the head nurse decides what to do with them
    overlapping_assignment_ids: list[int]
    overlapping_offers: list[OverlappingOfferView]
