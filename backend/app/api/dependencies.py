"""
Shared FastAPI dependencies.

The skeleton has no login (docs/workflow.md, D9). A request says who is acting
with the header `X-Demo-User: <staff_id>`, for example 105 to report leave,
201 to accept an offer and 900 to approve.
"""

import re
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Staff
from app.db.session import SessionLocal
from app.domain.enums import StaffStatus

DEMO_USER_HEADER = "X-Demo-User"

# Positive integer without sign, spaces or leading zero. 19 digits can still
# exceed STAFF.id (bigint), so the value is also checked against MAX_STAFF_ID
_STAFF_ID_PATTERN = re.compile(r"[1-9][0-9]{0,18}")
MAX_STAFF_ID = 2**63 - 1


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


def get_demo_user(
    db: DbSession,
    x_demo_user: Annotated[str | None, Header(alias=DEMO_USER_HEADER)] = None,
) -> Staff:
    """Return the active staff member named by X-Demo-User, or respond 401."""
    if x_demo_user is None:
        raise _unauthorized(f"Missing {DEMO_USER_HEADER} header")
    if _STAFF_ID_PATTERN.fullmatch(x_demo_user) is None or int(x_demo_user) > MAX_STAFF_ID:
        raise _unauthorized(f"{DEMO_USER_HEADER} must be a staff ID")

    staff = db.get(Staff, int(x_demo_user))
    if staff is None or staff.status is not StaffStatus.ACTIVE:
        raise _unauthorized(f"Unknown or inactive staff {x_demo_user}")
    return staff


DemoUser = Annotated[Staff, Depends(get_demo_user)]
