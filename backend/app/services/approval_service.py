"""Approval lookups for the walking skeleton; decisions arrive in seam 7."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ApprovalRequest


class DuplicatePendingApprovalError(ValueError):
    """A case has several pending requests, violating the skeleton contract."""


def list_pending(db: Session) -> list[ApprovalRequest]:
    """Read pending requests by ID, without commits, explicit flushes or locks.

    A case may have at most one pending request. Do not hide duplicates by
    picking a first row or returning an ambiguous list to the approver.
    """
    requests = list(
        db.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.is_pending.is_(True))
            .order_by(ApprovalRequest.id)
        )
    )
    seen: set[int] = set()
    for request in requests:
        if request.case_id in seen:
            raise DuplicatePendingApprovalError(
                f"Case {request.case_id} has more than one pending approval request"
            )
        seen.add(request.case_id)
    return requests
