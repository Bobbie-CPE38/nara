"""LINE simulator: view a selected staff member's offers and answer as the demo user.

Session mode (6.33.5, round 6 PR AU2): both the Demo Basic Auth on AWS and a session; the
selected staff member must be the signed-in user, and an answer is checked against the
owner of the offer in the database (outreach_service.record_response).
"""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import DbSession, DemoUser, forbidden, session_mode
from app.api.offer_responses import ResponseResult, answer_offer
from app.core.constants import MAX_BIGINT
from app.domain.enums import CandidateResponse
from app.schemas.outreach import OfferView
from app.services import outreach_service

router = APIRouter(prefix="/demo/line-sim", tags=["line-sim"])


@router.get("/offers")
def offers(
    staff_id: Annotated[int, Query(gt=0, le=MAX_BIGINT)], db: DbSession, user: DemoUser
) -> list[OfferView]:
    """Read offer history for the simulator's selected staff member (only yourself in
    session mode: 403 otherwise)."""
    if session_mode() and staff_id != user.staff.id:
        raise forbidden()
    return outreach_service.list_offers(db, staff_id=staff_id)


class ResponseRequest(BaseModel):
    """The header identifies the responder; outreach_id identifies the offer they saw."""

    model_config = ConfigDict(extra="forbid")
    outreach_id: int = Field(strict=True, ge=1, le=MAX_BIGINT)
    response: CandidateResponse


@router.post("/respond", response_model=ResponseResult)
def respond(body: ResponseRequest, db: DbSession, user: DemoUser) -> ResponseResult:
    return answer_offer(db, user, body.outreach_id, body.response)
