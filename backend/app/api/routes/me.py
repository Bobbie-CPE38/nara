"""Nurse page "My shift offers" (docs/workflow.md, section 6.17).

The staff member is the X-Demo-User header and nothing else: no route here
takes a staff_id. Reading and answering use the same service calls as the LINE
simulator, so there is no second set of response rules.
"""

from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import DbSession, DemoUser
from app.api.routes.line_sim import ResponseResult, answer_offer
from app.core.constants import MAX_BIGINT
from app.domain.enums import CandidateResponse
from app.schemas.outreach import OfferView
from app.services import outreach_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/offers")
def my_offers(db: DbSession, user: DemoUser) -> list[OfferView]:
    """Offers of the header user only. A staff_id query parameter is ignored."""
    return outreach_service.list_offers(db, staff_id=user.staff.id)


class MyResponseRequest(BaseModel):
    """Only the answer: the offer is in the path and the responder is the header."""

    model_config = ConfigDict(extra="forbid")
    response: CandidateResponse


@router.post("/offers/{outreach_id}/response", response_model=ResponseResult)
def answer_my_offer(
    outreach_id: Annotated[int, Path(ge=1, le=MAX_BIGINT)],
    body: MyResponseRequest,
    db: DbSession,
    user: DemoUser,
) -> ResponseResult:
    return answer_offer(db, user, outreach_id, body.response)
