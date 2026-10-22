"""Change the end of a leave period (docs/workflow.md, section 9.5)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status

from app.api.dependencies import DbSession, DemoUser, access_viewer
from app.core.constants import MAX_BIGINT
from app.schemas.unavailability import EndAtChange, EndAtChangeResult, OverlappingOfferView
from app.services import unavailability_service

router = APIRouter(prefix="/unavailability", tags=["unavailability"])

UnavailabilityId = Annotated[int, Path(ge=1, le=MAX_BIGINT)]


@router.patch("/{unavailability_id}")
def change_end_at(
    unavailability_id: UnavailabilityId, body: EndAtChange, db: DbSession, user: DemoUser
) -> EndAtChangeResult:
    """401 header → 422 body shape → 404 → 403 → 422 end not after start.

    FastAPI checks the header dependency, then the body, before this runs. Then
    the change and its audit row in one commit.
    """
    try:
        update = unavailability_service.update_end_at(
            db,
            unavailability_id=unavailability_id,
            end_at=body.end_at,
            role=access_viewer(db, user).role,
            home_ward_id=user.staff.home_ward_id,
            actor_id=user.actor_id,
        )
    except unavailability_service.UnavailabilityNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except unavailability_service.UnavailabilityForbiddenError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except unavailability_service.InvalidUnavailabilityEndError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    period = update.unavailability
    assert period.end_at is not None
    return EndAtChangeResult(
        unavailability_id=period.id,
        staff_id=period.staff_id,
        start_at=period.start_at,
        end_at=period.end_at,
        previous_end_at=update.previous_end_at,
        overlapping_assignment_ids=update.overlapping_assignment_ids,
        overlapping_offers=[
            OverlappingOfferView(
                outreach_id=offer.outreach_id, case_id=offer.case_id, status=offer.status
            )
            for offer in update.overlapping_offers
        ],
    )
