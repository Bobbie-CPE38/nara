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

router = APIRouter(prefix="/gap", tags=["gap"])

BigintId = Annotated[int, Path(ge=1, le=MAX_BIGINT)]


@router.get("/shifts")
def list_shifts(
    db: DbSession,
    user: DemoUser,
    ward_id: Annotated[int, Query(ge=1, le=MAX_BIGINT)],
    day: Annotated[date, Query(alias="date")],
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
    """The gap of one shift by time slice, with its roster. 404 unknown, 403 not visible."""
    try:
        return gap_check_service.shift_detail(
            db, gap_check_service.ward_scope(db, user.staff), shift_id
        )
    except gap_check_service.ShiftNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except gap_check_service.WardNotVisibleError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error)) from error
