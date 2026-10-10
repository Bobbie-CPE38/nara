"""Event intake (docs/workflow.md, section 3)."""

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import DbSession, DemoUser
from app.schemas.event import EventCreate, EventResult
from app.services import event_service
from app.services.event_service import (
    EventNotSupportedError,
    InvalidLeaveEndError,
    ShiftNotFoundError,
)
from app.services.unavailability_service import NoAssignedRosterError

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_event(body: EventCreate, db: DbSession, user: DemoUser) -> EventResult:
    """Report an event as the X-Demo-User staff member.

    201 also when the workflow ended in FAILED: that is a recorded result, shown
    in `case_status`. None of the errors below writes anything.
    """
    try:
        outcome = event_service.receive_event(
            db,
            staff_id=user.staff.id,
            actor_id=user.actor_id,
            event_type=body.event_type,
            shift_id=body.shift_id,
            end_at=body.end_at,
        )
    except ShiftNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except NoAssignedRosterError as error:
        # Not on that shift, or the leave was already reported
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except (EventNotSupportedError, InvalidLeaveEndError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return EventResult(
        event_id=outcome.event_id,
        event_status=outcome.event_status,
        case_id=outcome.case_id,
        case_status=outcome.case_status,
    )
