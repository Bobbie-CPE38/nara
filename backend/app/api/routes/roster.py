"""Roster of a shift or of a staff member (docs/workflow.md, sections 9.3 and 9.5). Read-only."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import DbSession, DemoUser
from app.core.constants import MAX_BIGINT
from app.domain.errors import ShiftNotFoundError, StaffNotFoundError
from app.schemas.roster import ShiftRoster, StaffRoster
from app.services import roster_service

router = APIRouter(prefix="/roster", tags=["roster"])

# Inside the bigint range: a larger number would reach PostgreSQL and come back
# as a 500
RosterId = Annotated[int | None, Query(ge=1, le=MAX_BIGINT)]


@router.get("")
def get_roster(
    db: DbSession, user: DemoUser, shift_id: RosterId = None, staff_id: RosterId = None
) -> ShiftRoster | StaffRoster:
    """Every roster row of one shift, or of one staff member, without writing.

    Exactly one of shift_id and staff_id: none or both is 422. Any active staff
    member reads any shift or person: the skeleton has no ward scoping. 404 for
    an unknown shift or person; no rows answers 200 with an empty list.
    """
    try:
        if shift_id is not None and staff_id is None:
            return roster_service.get_shift_roster(db, shift_id)
        if staff_id is not None and shift_id is None:
            return roster_service.get_staff_roster(db, staff_id)
    except (ShiftNotFoundError, StaffNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "Give exactly one of shift_id and staff_id"
    )
