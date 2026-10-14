"""Answer an offer as the X-Demo-User staff member, shared by two routes.

The LINE simulator (/demo/line-sim/respond) and the nurse page
(/me/offers/{outreach_id}/response) both answer through record_response(), so
the HTTP mapping of its refusals lives here once (docs/workflow.md, 6.17).
"""

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.domain.enums import CandidateResponse, CaseStatus, OutreachStatus
from app.services import outreach_service


class ResponseResult(BaseModel):
    outreach_id: int
    outreach_status: OutreachStatus
    case_id: int
    case_status: CaseStatus


def answer_offer(
    db: Session, user: CurrentUser, outreach_id: int, response: CandidateResponse
) -> ResponseResult:
    """409 when record_response() refuses, 503 with Retry-After when the lock is not stable."""
    try:
        outreach, case = outreach_service.record_response(
            db,
            staff_id=user.staff.id,
            actor_id=user.actor_id,
            outreach_id=outreach_id,
            response=response,
        )
    except outreach_service.OutreachLockRetryError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error), headers={"Retry-After": "1"}
        ) from error
    except outreach_service.OpenOfferConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    return ResponseResult(
        outreach_id=outreach.id,
        outreach_status=outreach.status,
        case_id=case.id,
        case_status=case.status,
    )
