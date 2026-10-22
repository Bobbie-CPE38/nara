"""Roster of a shift or of a staff member (docs/workflow.md, sections 9.3 and 9.5). Read-only."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import DbSession, DemoUser, access_viewer, forbidden, session_mode
from app.core.constants import MAX_BIGINT
from app.domain.errors import ShiftNotFoundError, StaffNotFoundError
from app.schemas.roster import ShiftRoster, StaffRoster
from app.services import access_service, roster_service

router = APIRouter(prefix="/roster", tags=["roster"])

# Inside the bigint range: a larger number would reach PostgreSQL and come back
# as a 500
RosterId = Annotated[int | None, Query(ge=1, le=MAX_BIGINT)]


@router.get("")
def get_roster(
    db: DbSession, user: DemoUser, shift_id: RosterId = None, staff_id: RosterId = None
) -> ShiftRoster | StaffRoster:
    """Every roster row of one shift, or of one staff member, without writing.

    Exactly one of shift_id and staff_id: none or both is 422. 404 for an unknown shift
    or person; no rows answers 200 with an empty list.

    Demo mode: any active staff member reads any shift or person. Session mode (6.33.4):
    a shift needs its ward visible (home ward, every ward for a supervisor); your own
    rows come from every ward; someone else's need their home ward visible and keep only
    the rows of shifts in wards you see. Anything else is 403.
    """
    viewer = access_viewer(db, user) if session_mode() else None
    try:
        if shift_id is not None and staff_id is None:
            roster = roster_service.get_shift_roster(db, shift_id)
            if viewer is not None and not access_service.sees_ward(viewer, roster.shift.ward_id):
                raise forbidden()
            return roster
        if staff_id is not None and shift_id is None:
            if (
                viewer is not None
                and access_service.sees_staff_roster(db, viewer, staff_id) is False
            ):
                raise forbidden()
            # Someone else's roster: only the rows of shifts in wards the reader sees (in the query)
            others = (
                viewer is not None and staff_id != viewer.staff_id and viewer.role != "supervisor"
            )
            return roster_service.get_staff_roster(
                db,
                staff_id,
                access_service.roster_shift_condition(viewer) if others and viewer else None,
            )
    except (ShiftNotFoundError, StaffNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "Give exactly one of shift_id and staff_id"
    )
