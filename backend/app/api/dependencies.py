"""
Shared FastAPI dependencies.

Who is acting comes from one dependency, get_current_user (docs/workflow.md D9, 6.33.2):
  * AUTH_MODE=demo: the header `X-Demo-User: <staff_id>`, for example 105 to report
    leave, 201 to accept an offer and 900 to approve. No password.
  * AUTH_MODE=session: the `nara_session` cookie of a login, checked in the database on
    every request. X-Demo-User is never read, whatever it says.
`DemoUser` is the old name of the same dependency, kept so routes need no change.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import BackgroundTasks, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import MAX_BIGINT
from app.db.models import Actor, Staff
from app.db.session import SessionLocal
from app.domain.enums import StaffStatus
from app.services import auth_service

DEMO_USER_HEADER = "X-Demo-User"
SESSION_COOKIE = "nara_session"
# Error codes of docs/workflow.md 6.33.3; the web page translates them
AUTH_REQUIRED = "AUTH_REQUIRED"
AUTH_PASSWORD_CHANGE_REQUIRED = "AUTH_PASSWORD_CHANGE_REQUIRED"

# Positive integer without sign, spaces or leading zero. 19 digits can still
# exceed STAFF.id (bigint), so the value is also checked against MAX_STAFF_ID
_STAFF_ID_PATTERN = re.compile(r"[1-9][0-9]{0,18}")
MAX_STAFF_ID = MAX_BIGINT


def get_db(background_tasks: BackgroundTasks) -> Iterator[Session]:
    """One session per request. Services and the orchestrator commit, not this."""
    with SessionLocal() as db:
        from app.services import line_background_service

        # All HTTP entry points can create waves, including event, demo and
        # internal job routes. Defer LINE I/O until their response is sent.
        # A test reusing a Session across requests retains these schedulers in
        # db.info; configure replaces them for each new BackgroundTasks object.
        line_background_service.configure(db, background_tasks)
        yield db


# Close request transactions before sending the response and running LINE tasks.
# Request-scoped teardown would retain read locks until background delivery ends.
DbSession = Annotated[Session, Depends(get_db, scope="function")]


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
    # AUTH_SESSION.id in session mode, None in demo mode
    session_id: int | None = None


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


def _auth_required() -> HTTPException:
    # No WWW-Authenticate: neither Basic nor X-Demo-User is a way in (6.33.3)
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTH_REQUIRED)


def get_session_user(request: Request, db: DbSession) -> auth_service.SessionUser:
    """The live session of the request's cookie, or 401 AUTH_REQUIRED, in either mode.

    Allows a user who must still change their password: /auth/me, /auth/logout and
    /auth/change-password use this one. Other routes use get_current_user.
    The check commits (it moves last_seen_at), so it adds nothing to the route's
    transaction except the Staff row it loads afterwards.
    """
    token = request.cookies.get(SESSION_COOKIE)
    user = auth_service.resolve(db, token) if token else None
    if user is None:
        raise _auth_required()
    return user


SessionUserDep = Annotated[auth_service.SessionUser, Depends(get_session_user)]


def get_current_user(
    request: Request,
    db: DbSession,
    x_demo_user: Annotated[str | None, Header(alias=DEMO_USER_HEADER)] = None,
) -> CurrentUser:
    """The one current-user dependency. See the module docstring for the two modes."""
    if settings.auth_mode != "session":
        return get_demo_user(db, x_demo_user)
    user = get_session_user(request, db)
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=AUTH_PASSWORD_CHANGE_REQUIRED
        )
    return CurrentUser(staff=user.staff, actor_id=user.actor_id, session_id=user.session_id)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
DemoUser = CurrentUserDep
