"""Login and registration API (workflow 6.33.3 and 6.33.6).

Auth routes work in both modes. Identity checks use only the session cookie,
never X-Demo-User. All /auth responses are no-store. POST needs an allowed Origin.
"""

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request, Response, status

from app.api.dependencies import AUTH_REQUIRED, SESSION_COOKIE, DbSession, SessionUserDep
from app.api.rate_limit import (
    LOGIN_PER_ACCOUNT,
    LOGIN_PER_IP,
    REGISTER_PER_IP,
    REGISTER_PER_SUBJECT,
    Limit,
    limiter,
)
from app.core.config import settings
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
    return _me(user)


@router.get("/me")
def read_me(user: SessionUserDep) -> AuthMe:
    return _me(user)


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


def _me(user: auth_service.SessionUser) -> AuthMe:
    return AuthMe(
        staff_id=user.staff.id,
        role=user.role,
        home_ward_id=user.staff.home_ward_id,
        must_change_password=user.must_change_password,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, db: DbSession) -> RegisteredAccount:
    # Gate before lookup: a reset cannot replace identity/code tables during signup.
    auth_service.hold_auth_gate(db)
    client = request.client.host if request.client else "unknown"
    subject = registration_service.subject_for_code(db, body.code)
    limits = [Limit(f"register:ip:{client}", REGISTER_PER_IP)]
    if subject is not None:
        limits.append(Limit(f"register:subject:{subject}", REGISTER_PER_SUBJECT))
    wait = limiter.hit(limits)
    if wait is not None:
        db.rollback()
        raise HTTPException(429, AUTH_RATE_LIMITED, headers={"Retry-After": str(wait)})
    try:
        staff_id = registration_service.register(db, body.code, body.password)
        db.commit()
    except registration_service.RegistrationError:
        db.rollback()
        raise HTTPException(400, "AUTH_INVALID_REGISTRATION") from None
    return RegisteredAccount(staff_id=staff_id)
