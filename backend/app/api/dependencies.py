"""
Shared FastAPI dependencies.

The skeleton has no login (docs/workflow.md, D9). A request says who is acting
with the header `X-Demo-User: <staff_id>`, for example 105 to report leave,
201 to accept an offer and 900 to approve.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import MAX_BIGINT
from app.db.models import Actor, Staff
from app.db.session import SessionLocal
from app.domain.enums import StaffStatus

DEMO_USER_HEADER = "X-Demo-User"

# Positive integer without sign, spaces or leading zero. 19 digits can still
# exceed STAFF.id (bigint), so the value is also checked against MAX_STAFF_ID
_STAFF_ID_PATTERN = re.compile(r"[1-9][0-9]{0,18}")
MAX_STAFF_ID = MAX_BIGINT


def get_db() -> Iterator[Session]:
    """One session per request. Services and the orchestrator commit, not this."""
    with SessionLocal() as db:
        yield db


DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": DEMO_USER_HEADER},
    )


@dataclass(frozen=True)
class CurrentUser:
    """Who is acting in this request: the staff member and their audit actor."""

    staff: Staff
    # ACTORS.id of this staff member, ready for audit_service.log(actor_id=...)
    actor_id: int


def get_demo_user(
    db: DbSession,
    x_demo_user: Annotated[str | None, Header(alias=DEMO_USER_HEADER)] = None,
) -> CurrentUser:
    """Return the active staff member named by X-Demo-User, or respond 401.

    The staff member must have a user actor. Its ID comes back in the same
    query, so an audited route does not call `actor_service.user_id()` again.

    Reads with a SELECT, and SessionLocal has autoflush off: a Staff or Actor row
    added earlier in the same session is visible only after `db.flush()`.
    """
    if x_demo_user is None:
        raise _unauthorized(f"Missing {DEMO_USER_HEADER} header")
    if _STAFF_ID_PATTERN.fullmatch(x_demo_user) is None:
        raise _unauthorized(f"{DEMO_USER_HEADER} must be a staff ID")
    staff_id = int(x_demo_user)
    if staff_id > MAX_STAFF_ID:
        raise _unauthorized(f"{DEMO_USER_HEADER} must be a staff ID")

    # The join drops staff who have no actor row
    row = db.execute(
        select(Staff, Actor.id).join(Actor, Actor.staff_id == Staff.id).where(Staff.id == staff_id)
    ).first()
    # `!=`, not `is not`: a row written earlier in this session with the plain
    # string "ACTIVE" still holds that string until it is reloaded
    if row is None or row[0].status != StaffStatus.ACTIVE:
        raise _unauthorized(f"Staff {staff_id} is unknown, inactive or has no actor")
    staff, actor_id = row
    return CurrentUser(staff=staff, actor_id=actor_id)


DemoUser = Annotated[CurrentUser, Depends(get_demo_user)]
