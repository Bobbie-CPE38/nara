"""Read-only gap check of a shift, with or without a case (docs/workflow.md 6.31, 9.8).

Round 6 PR F1. Measures with `assess_shift()` and never `record_gap()`: no gap row,
event, audit row or case is written. There is no route here that opens a case
(R6-Q17 ก); that stays with Demo control.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.api.dependencies import DbSession, DemoUser
from app.schemas.gap_check import GapShiftDetail, GapShiftSummary
from app.schemas.types import MAX_BIGINT
from app.services import gap_check_service
from app.services.requirement_service import RequirementNotFoundError

router = APIRouter(prefix="/gap", tags=["gap"])

BigintId = Annotated[int, Path(ge=1, le=MAX_BIGINT)]

# `date` is a day of the calendar the app runs on. Bounds keep "day + 1" and the +07:00
# conversion away from the edges of datetime: 9999-12-31 would overflow into a 500
MIN_GAP_DATE = date(2000, 1, 1)
MAX_GAP_DATE = date(2999, 12, 31)


@router.get("/shifts")
def list_shifts(
    db: DbSession,
    user: DemoUser,
    ward_id: Annotated[int, Query(ge=1, le=MAX_BIGINT)],
    day: Annotated[date, Query(alias="date", ge=MIN_GAP_DATE, le=MAX_GAP_DATE)],
) -> list[GapShiftSummary]:
    """Active shifts of the ward starting on `date` (Asia/Bangkok) with their gap now."""
    try:
        return gap_check_service.list_shifts(
            db, gap_check_service.ward_scope(db, user.staff), ward_id=ward_id, day=day
        )
    except gap_check_service.WardNotVisibleError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error)) from error


@router.get("/shifts/{shift_id}")
def shift_gap(shift_id: BigintId, db: DbSession, user: DemoUser) -> GapShiftDetail:
    """The gap of one shift by time slice, with its roster. 404 unknown, 403 not visible,
    409 when the shift has no staffing requirement yet."""
    try:
        return gap_check_service.shift_detail(
            db, gap_check_service.ward_scope(db, user.staff), shift_id
        )
    except gap_check_service.ShiftNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RequirementNotFoundError as error:
        # The shift is not set up for staffing yet, as for POST /events
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    except gap_check_service.WardNotVisibleError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error)) from error
