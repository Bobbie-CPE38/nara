"""GET /dashboard (docs/workflow.md 6.31, 9.8, round 6 PR F1). Read-only."""

from fastapi import APIRouter

from app.api.dependencies import DbSession, DemoUser
from app.schemas.dashboard import Dashboard
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def read_dashboard(db: DbSession, user: DemoUser) -> Dashboard:
    """What needs attention in the caller's wards; a Supervisor sees every ward."""
    return dashboard_service.build(db, user.staff)
