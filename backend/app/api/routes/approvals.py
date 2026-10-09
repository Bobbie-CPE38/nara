"""Pending approval reads; decisions arrive separately in seam 7."""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AfterValidator

from app.api.dependencies import DbSession, DemoUser
from app.schemas.approval import PendingApproval
from app.services import approval_service

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _pending_only(value: bool) -> bool:
    if not value:
        raise ValueError("Only pending approvals are supported in the walking skeleton")
    return value


PendingFilter = Annotated[bool, Query(), AfterValidator(_pending_only)]


@router.get("")
def pending_approvals(
    db: DbSession, user: DemoUser, pending: PendingFilter = True
) -> list[PendingApproval]:
    """Return the pending list to an authenticated demo user, without writing."""
    return approval_service.list_pending(db)
