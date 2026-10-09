"""Pending approval reads; decisions arrive separately in seam 7."""

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import DbSession, DemoUser
from app.schemas.approval import PendingApproval
from app.services import approval_service

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[PendingApproval])
def pending_approvals(db: DbSession, user: DemoUser, pending: bool = True) -> list[PendingApproval]:
    """Return the pending list to an authenticated demo user, without writing."""
    if not pending:
        raise HTTPException(
            422, detail="Only pending approvals are supported in the walking skeleton"
        )
    try:
        requests = approval_service.list_pending(db)
    except approval_service.DuplicatePendingApprovalError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    return [PendingApproval.model_validate(request) for request in requests]
