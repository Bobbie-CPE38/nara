"""Required ward identities and shared human authority for approval attempts."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.constants import HEAD_NURSE_ROLE, SUPERVISOR_ROLE
from app.db.models import (
    ApprovalRequest,
    ApprovalWardDecision,
    CandidateItem,
    Role,
    RosterAssignment,
    Shift,
)
from app.domain.enums import ApprovalSide
from app.domain.staffing.ward_authority import can_decide
from app.services import policy_service


class InvalidApprovalSideError(ValueError):
    """The side is invalid or ambiguous, after authorization and stale-state checks."""


def required_wards(db: Session, item: CandidateItem) -> dict[ApprovalSide, int]:
    destination = db.get(Shift, item.proposed_shift_id)
    if destination is None:
        raise LookupError(f"No shift {item.proposed_shift_id}")
    wards = {ApprovalSide.DESTINATION: destination.ward_id}
    if item.source_assignment_id is not None:
        source = db.scalar(
            select(Shift.ward_id)
            .join(RosterAssignment, RosterAssignment.shift_id == Shift.id)
            .where(RosterAssignment.id == item.source_assignment_id)
        )
        if source is None:
            raise LookupError(f"No source assignment {item.source_assignment_id}")
        wards[ApprovalSide.SOURCE] = source
    return wards


def supervisor_from(db: Session, request: ApprovalRequest) -> datetime:
    return request.requested_at + timedelta(
        seconds=policy_service.get_approval_policy(db).supervisor_after_seconds
    )


def authority(
    db: Session,
    request: ApprovalRequest,
    item: CandidateItem,
    *,
    role_id: int,
    home_ward_id: int | None,
    side: str | None,
) -> tuple[str | None, bool]:
    """Check rights before stale-state or semantic side validation (404→403→409→422)."""
    role = db.scalar(select(Role.name).where(Role.id == role_id))
    wards = required_wards(db, item)
    targets = [wards[ApprovalSide(side)]] if side in wards else list(wards.values())
    waited = clock.now() >= supervisor_from(db, request)
    allowed = any(
        can_decide(
            role=role,
            home_ward_id=home_ward_id,
            ward_id=ward,
            waited=waited,
        )
        for ward in targets
    )
    return role, allowed


def select_side(
    db: Session,
    request: ApprovalRequest,
    item: CandidateItem,
    *,
    role_id: int,
    home_ward_id: int | None,
    side: str | None,
) -> ApprovalSide:
    """Resolve a valid side only after all 409 checks; the caller checks duplicates."""
    wards = required_wards(db, item)
    if side is not None:
        if side not in wards:
            raise InvalidApprovalSideError("This request does not require that approval side")
        return ApprovalSide(side)
    role = db.scalar(select(Role.name).where(Role.id == role_id))
    if role == HEAD_NURSE_ROLE:
        choices = [key for key, ward in wards.items() if ward == home_ward_id]
    elif role == SUPERVISOR_ROLE:
        decided = set(
            db.scalars(
                select(ApprovalWardDecision.side).where(
                    ApprovalWardDecision.approval_request_id == request.id
                )
            )
        )
        choices = [key for key in wards if key not in decided]
    else:
        choices = []
    if len(choices) != 1:
        raise InvalidApprovalSideError("Specify which ward side to decide")
    return choices[0]
