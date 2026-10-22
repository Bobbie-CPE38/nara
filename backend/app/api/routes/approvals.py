"""Pending approval reads and manual decisions (seams 6 and 7)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import AfterValidator

from app.api.dependencies import DbSession, DemoUser, access_viewer, forbidden, session_mode
from app.core.constants import MAX_BIGINT
from app.schemas.approval import (
    ApprovalDecision,
    ApprovalDecisionResult,
    AutoApprovedApproval,
    PendingApproval,
)
from app.services import approval_service, approval_wards

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
            home_ward_id=user.staff.home_ward_id,
            actor_id=user.actor_id,
            approved=body.approved,
            reason=body.reason,
            side=body.side,
        )
    except approval_service.ApprovalNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (approval_service.ApproverRoleError, approval_service.ApproverWardError) as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except (
        approval_service.ApprovalNotPendingError,
        approval_service.ApprovalOfferConflictError,
        approval_service.ApprovalLockRetryError,
    ) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    except (
        approval_service.InvalidApprovalReasonError,
        approval_wards.InvalidApprovalSideError,
    ) as error:
        raise HTTPException(422, detail=str(error)) from error
    return approval_service.decision_result(db, request=request, case=case)


def _pending_only(value: bool) -> bool:
    if not value:
        raise ValueError("Only pending approvals are supported in the walking skeleton")
    return value


PendingFilter = Annotated[bool, Query(), AfterValidator(_pending_only)]


@router.get("")
def pending_approvals(
    db: DbSession, user: DemoUser, pending: PendingFilter = True
) -> list[PendingApproval]:
    """The pending list, without writing.

    Demo mode: any demo user reads every request. Session mode (6.33.4): a staff member
    may not read it (403), a head nurse gets the requests with a side in their own ward,
    a supervisor every request.
    """
    if not session_mode():
        return approval_service.list_pending(db)
    viewer = access_viewer(db, user)
    if viewer.role == "staff":
        raise forbidden()
    requests = approval_service.list_pending(db)
    if viewer.role == "supervisor":
        return requests
    return [item for item in requests if any(w.ward_id == viewer.home_ward_id for w in item.wards)]


@router.get("/auto")
def auto_approvals(db: DbSession, user: DemoUser) -> list[AutoApprovedApproval]:
    """Return up to 50 automatic decisions visible to this Head Nurse or Supervisor."""
    try:
        return approval_service.list_auto_approved(
            db,
            role_id=user.staff.role_id,
            home_ward_id=user.staff.home_ward_id,
        )
    except approval_service.ApproverRoleError as error:
        raise HTTPException(403, detail=str(error)) from error
