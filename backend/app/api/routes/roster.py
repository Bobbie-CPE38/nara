"""Roster of a shift (docs/workflow.md, section 9.3). Read-only."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import DbSession, DemoUser
from app.core.constants import MAX_BIGINT
from app.domain.errors import ShiftNotFoundError
from app.schemas.roster import ShiftRoster
from app.services import roster_service

router = APIRouter(prefix="/roster", tags=["roster"])

# Required, and inside the bigint range: a larger number would reach PostgreSQL
# and come back as a 500
ShiftId = Annotated[int, Query(ge=1, le=MAX_BIGINT)]


@router.get("")
def get_roster(shift_id: ShiftId, db: DbSession, user: DemoUser) -> ShiftRoster:
    """Every roster row of the shift for an authenticated demo user, without writing.

    Any active staff member reads any shift: the skeleton has no ward scoping.
    404 for an unknown shift; a shift without rows answers 200 with an empty list.
    """
    try:
        return roster_service.get_shift_roster(db, shift_id)
    except ShiftNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
