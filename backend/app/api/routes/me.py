"""Nurse page "My shift offers" (docs/workflow.md, section 6.17) and own leave (6.33.4).

The staff member is the current user (X-Demo-User in demo mode, the session in session
mode) and nothing else: no route here takes a staff_id. Reading and answering use the
same service calls as the LINE simulator, so there is no second set of response rules.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import DbSession, DemoUser, forbidden
from app.api.offer_responses import ResponseResult, answer_offer
from app.core.constants import MAX_BIGINT
from app.domain.enums import CandidateResponse, CheckInSource, EventType
from app.domain.errors import ShiftNotFoundError
from app.schemas.attendance import CheckInResponse, MyCheckIn
from app.schemas.event import EventResult, SelfLeave
from app.schemas.handover import HandoverPage
from app.schemas.outreach import OfferView
from app.services import (
    attendance_service,
    event_service,
    handover_service,
    outreach_service,
    unavailability_service,
)
from app.services.requirement_service import RequirementNotFoundError

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/handovers")
def my_handovers(
    db: DbSession,
    user: DemoUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> HandoverPage:
    """Current handovers plus a bounded page of history for the header user only."""
    try:
        return handover_service.page_handovers(
            db, staff_id=user.staff.id, limit=limit, cursor=cursor
        )
    except handover_service.InvalidCursorError as error:
        raise HTTPException(422, "Invalid handover history cursor") from error


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


@router.post("/attendance/check-in")
def check_in(body: MyCheckIn, db: DbSession, user: DemoUser) -> CheckInResponse:
    """Check the header user in. 401 header, 422 body, 404 no shift or roster row, 422 window.
    409 when new offers kept arriving during a check-in after a NO_SHOW.

    A repeated check-in answers 200 with the first row (section 6.24).
    """
    try:
        result = attendance_service.check_in(
            db,
            staff_id=user.staff.id,
            shift_id=body.shift_id,
            source=CheckInSource.SELF,
            actor_id=user.actor_id,
        )
    except (ShiftNotFoundError, unavailability_service.NoAssignedRosterError) as error:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except attendance_service.CheckInOutsideWindowError as error:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except attendance_service.CheckInLockRetryError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return CheckInResponse(**vars(result))


@router.post("/unavailability", status_code=status.HTTP_201_CREATED)
def report_my_leave(body: SelfLeave, db: DbSession, user: DemoUser) -> EventResult:
    """Report your own leave from a shift you are rostered on. It takes effect at once:
    the same STAFF_UNAVAILABLE flow as before, with no approval of the leave (6.33.4).

    401 → 422 body → 404 unknown shift → 409 shift not set up for staffing → 403
    AUTH_FORBIDDEN when you have no assigned row in that shift → 422 end time. Every refusal
    writes nothing. The 403 is one answer for "never yours", "cancelled" and "a report already
    closed the window that cancelled it": it comes from the state the intake saw under its own
    lock, so a concurrent change cannot flip it and it does not tell which shifts a person was
    on. A repeat while the window is open follows the event rules (the second is IGNORED).
    """
    try:
        outcome = event_service.receive_event(
            db,
            staff_id=user.staff.id,
            actor_id=user.actor_id,
            role_id=user.staff.role_id,
            event_type=EventType.STAFF_UNAVAILABLE,
            shift_id=body.shift_id,
            end_at=body.end_at,
        )
    except event_service.ShiftNotFoundError as error:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except RequirementNotFoundError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except unavailability_service.NoAssignedRosterError:
        db.rollback()
        raise forbidden() from None
    except (event_service.InvalidLeaveEndError, event_service.InvalidEventDetailsError) as error:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return EventResult(
        event_id=outcome.event_id,
        event_status=outcome.event_status,
        case_id=outcome.case_id,
        case_status=outcome.case_status,
        joined_running_case=outcome.joined_running_case,
        ignored_reason=outcome.ignored_reason,
        window_closes_at=outcome.window_closes_at,
    )
