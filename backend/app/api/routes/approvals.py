"""Pending approval reads and manual decisions (seams 6 and 7)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import AfterValidator

from app.api.dependencies import DbSession, DemoUser
from app.core.constants import MAX_BIGINT
from app.schemas.approval import PendingApproval
from app.schemas.approval_decision import ApprovalDecision, ApprovalDecisionResult
from app.services import approval_service

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("/{approval_id}/decision", response_model=ApprovalDecisionResult)
def decide(
    approval_id: Annotated[int, Path(gt=0, le=MAX_BIGINT)],
    body: ApprovalDecision,
    db: DbSession,
    user: DemoUser,
) -> ApprovalDecisionResult:
    try:
        request, case = approval_service.decide(
            db,
            approval_id=approval_id,
            staff_id=user.staff.id,
            role_id=user.staff.role_id,
            actor_id=user.actor_id,
            approved=body.approved,
            reason=body.reason,
        )
    except approval_service.ApprovalNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except approval_service.ApproverRoleError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except approval_service.ApprovalNotPendingError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    except approval_service.UnsupportedApprovalDecisionError as error:
        raise HTTPException(422, detail=str(error)) from error
    return ApprovalDecisionResult(
        approval_id=request.id,
        is_approved=request.is_approved is True,
        case_id=case.id,
        case_status=case.status,
    )


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
