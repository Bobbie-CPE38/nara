"""Login and registration API (workflow 6.33.3 and 6.33.6).

Auth routes work in both modes. Identity checks use only the session cookie,
never X-Demo-User. All /auth responses are no-store. POST needs an allowed Origin.
"""

import re
from typing import Annotated
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Body, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.dependencies import (
    AUTH_FORBIDDEN,
    AUTH_PASSWORD_CHANGE_REQUIRED,
    AUTH_REQUIRED,
    SESSION_COOKIE,
    DbSession,
    SessionUserDep,
)
from app.core.config import settings
from app.core.rate_limit import (
    LOGIN_PER_ACCOUNT,
    LOGIN_PER_IP,
    REGISTER_PER_IP,
    REGISTER_PER_SUBJECT,
    Limit,
    limiter,
)
from app.db.models import Ward
from app.schemas.auth import (
    AuthConfig,
    AuthMe,
    ChangePasswordRequest,
    LoginRequest,
    RegisteredAccount,
    RegisterRequest,
)
from app.services import auth_service, registration_service

router = APIRouter(prefix="/auth", tags=["auth"])

AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
AUTH_INVALID_PASSWORD = "AUTH_INVALID_PASSWORD"
AUTH_RATE_LIMITED = "AUTH_RATE_LIMITED"


@router.get("/config")
def read_config() -> AuthConfig:
    """Public: which flow the web page shows. Never a reason to allow anything."""
    return AuthConfig(auth_mode=settings.auth_mode)


@router.post("/login")
def login(
    body: Annotated[LoginRequest, Body()], request: Request, response: Response, db: DbSession
) -> AuthMe:
    # Before the hash: a refused attempt costs no Argon2 work
    client = request.client.host if request.client else "unknown"
    wait = limiter.hit(
        [
            Limit(f"login:ip:{client}", LOGIN_PER_IP),
            Limit(f"login:staff:{body.staff_id}", LOGIN_PER_ACCOUNT),
        ]
    )
    if wait is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=AUTH_RATE_LIMITED,
            headers={"Retry-After": str(wait)},
        )
    result = auth_service.login(db, body.staff_id, body.password)
    if result is None:
        # Same answer for no account, a wrong password and a closed account
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTH_INVALID_CREDENTIALS
        )
    token, user = result
    # No Domain: the cookie stays on the host that set it
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.auth_session_max_age_seconds,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return _me(user, db)


@router.get("/me")
def read_me(user: SessionUserDep, db: DbSession) -> AuthMe:
    return _me(user, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession) -> None:
    """Idempotent: an ended, unknown or missing session still clears the cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        auth_service.logout(db, token)
    _clear_cookie(response)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: Annotated[ChangePasswordRequest, Body()],
    user: SessionUserDep,
    response: Response,
    db: DbSession,
) -> None:
    """Every session of the account ends, this one too: log in with the new password."""
    try:
        changed = auth_service.change_password(db, user, body.current_password, body.new_password)
    except auth_service.SessionGoneError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTH_REQUIRED
        ) from None
    if not changed:
        # 400, not 401: the session is fine, and the page must not treat it as gone
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=AUTH_INVALID_PASSWORD)
    _clear_cookie(response)


def _clear_cookie(response: Response) -> None:
    # The same attributes as the login's Set-Cookie, or a browser keeps the old cookie
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _me(user: auth_service.SessionUser, db: DbSession) -> AuthMe:
    return AuthMe(
        staff_id=user.staff.id,
        role=user.role,
        home_ward_id=user.staff.home_ward_id,
        home_ward_name=db.scalar(select(Ward.name).where(Ward.id == user.staff.home_ward_id)),
        must_change_password=user.must_change_password,
    )


# The canonical Demo page paths that Caddy lets through (deploy/aws/Caddyfile)
_DEMO_PAGE = re.compile(r"/demo(/[a-z0-9_-]+)*/?")
# Where a nurse goes instead of a Demo page: their home page (lib/routeAccess.ts)
STAFF_HOME = "/me/offers"


@router.get("/demo-gate", status_code=status.HTTP_204_NO_CONTENT)
def demo_gate(
    request: Request,
    db: DbSession,
    x_forwarded_uri: Annotated[str | None, Header()] = None,
) -> Response:
    """Who may reach the Demo pages, asked by Caddy before its Basic Auth (round 6 PR EV8).

    Caddy's forward_auth sends the visitor's request here with the address in
    X-Forwarded-Uri. 204 lets Caddy go on to the Basic Auth, so only a head nurse or a
    supervisor ever sees that box. Any other answer goes back to the visitor as it is: a
    page goes to /login (no session), /change-password, or the nurse's home page; an
    /api/demo call gets the JSON error of the API. Demo mode has no sessions: always 204.
    It decides nothing on its own: every /demo route still checks its caller."""
    if settings.auth_mode != "session":
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    path = urlsplit(x_forwarded_uri or "").path
    token = request.cookies.get(SESSION_COOKIE)
    user = auth_service.resolve(db, token) if token else None
    if user is None:
        page = path if _DEMO_PAGE.fullmatch(path) else "/demo/control"
        login = f"/login?next={quote(page)}"
        return _refuse(path, status.HTTP_401_UNAUTHORIZED, AUTH_REQUIRED, login)
    if user.must_change_password:
        return _refuse(
            path, status.HTTP_403_FORBIDDEN, AUTH_PASSWORD_CHANGE_REQUIRED, "/change-password"
        )
    if user.role == "staff":
        return _refuse(path, status.HTTP_403_FORBIDDEN, AUTH_FORBIDDEN, STAFF_HOME)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _refuse(path: str, code: int, detail: str, page: str) -> Response:
    """The error of the API for an /api/demo call, a redirect for a page. Like every /auth
    answer it is no-store (origin_guard)."""
    if path.startswith("/api/"):
        return JSONResponse({"detail": detail}, status_code=code)
    return Response(status_code=status.HTTP_302_FOUND, headers={"Location": page})


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, db: DbSession) -> RegisteredAccount:
    # Preflight releases its reset gate/transaction before rate limiting and hashing.
    prepared = registration_service.prepare_registration(db, body.code)
    client = request.client.host if request.client else "unknown"
    limits = [Limit(f"register:ip:{client}", REGISTER_PER_IP)]
    if prepared is not None:
        limits.append(Limit(f"register:subject:{prepared.subject}", REGISTER_PER_SUBJECT))
    wait = limiter.hit(limits)
    if wait is not None:
        db.rollback()
        raise HTTPException(429, AUTH_RATE_LIMITED, headers={"Retry-After": str(wait)})
    try:
        staff_id = registration_service.complete_registration(db, prepared, body.password)
        db.commit()
    except registration_service.RegistrationError:
        db.rollback()
        raise HTTPException(400, "AUTH_INVALID_REGISTRATION") from None
    return RegisteredAccount(staff_id=staff_id)
