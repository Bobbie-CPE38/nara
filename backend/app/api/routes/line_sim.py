"""LINE simulator: the authenticated candidate answers their open offer."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import DbSession, DemoUser
from app.domain.enums import CandidateResponse, CaseStatus, OutreachStatus
from app.services import outreach_service

router = APIRouter(prefix="/demo/line-sim", tags=["line-sim"])


class ResponseRequest(BaseModel):
    """The header identifies the responder; the body only contains the answer."""

    model_config = ConfigDict(extra="forbid")
    response: CandidateResponse


class ResponseResult(BaseModel):
    outreach_id: int
    outreach_status: OutreachStatus
    case_id: int
    case_status: CaseStatus


@router.post("/respond", response_model=ResponseResult)
def respond(body: ResponseRequest, db: DbSession, user: DemoUser) -> ResponseResult:
    try:
        outreach, case = outreach_service.record_response(
            db,
            staff_id=user.staff.id,
            actor_id=user.actor_id,
            response=body.response,
        )
    except outreach_service.OpenOfferConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    except outreach_service.UnsupportedResponseError as error:
        raise HTTPException(422, detail=str(error)) from error
    return ResponseResult(
        outreach_id=outreach.id,
        outreach_status=outreach.status,
        case_id=case.id,
        case_status=case.status,
    )
