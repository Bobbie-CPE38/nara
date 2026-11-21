"""GET /dashboard (docs/workflow.md 6.31, 9.8, round 6 PR F1). Read-only."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import DbSession, DemoUser, managers_only
from app.schemas.dashboard import Dashboard
from app.schemas.types import MAX_BIGINT
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def read_dashboard(
    db: DbSession,
    user: DemoUser,
    ward_id: Annotated[int | None, Query(ge=1, le=MAX_BIGINT)] = None,
) -> Dashboard:
    """What needs attention in the caller's wards; a Supervisor sees every ward. In session
    mode a nurse gets 403: the Dashboard is for head nurses and supervisors (round 6 PR EV8).
    `ward_id` narrows the numbers to one of those wards: 403 for any other (6.36.4)."""
    managers_only(db, user)
    try:
        return dashboard_service.build(db, user.staff, ward_id=ward_id)
    except dashboard_service.WardNotVisibleError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error)) from error
