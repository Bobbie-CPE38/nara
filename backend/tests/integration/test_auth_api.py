"""Login API and the session-mode current user (docs/workflow.md 6.33.2-3, round 6 PR AU1).

Accounts are made with the account functions the script uses; the seeded Golden Case
has none. Staff 105 is an RN (role staff), 900 the ICU head nurse, 950 the supervisor.
The client talks HTTPS, so the Secure cookie travels as it does on AWS.
"""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import rate_limit
from app.api.dependencies import SESSION_COOKIE, get_db
from app.core import auth_clock
from app.core.config import settings
from app.db.models import Actor, AuthAccount, AuthSession, Staff
from app.domain.enums import StaffStatus
from app.main import app
from app.services import auth_service

PASSWORD = "first password 105"
NEW_PASSWORD = "second password 105"
ORIGIN = settings.cors_origins[0]


@pytest.fixture(autouse=True)
def fresh_limits() -> Iterator[None]:
    rate_limit.limiter.clear()
    yield
    rate_limit.limiter.clear()


@pytest.fixture
def db(production_seeded: Session) -> Session:
    auth_service.create_account(production_seeded, 105, PASSWORD, must_change_password=False)
    return production_seeded


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app, base_url="https://testserver", headers={"Origin": ORIGIN}) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def session_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_mode", "session")


class MovableClock:
    def __init__(self) -> None:
        self.now = auth_clock.now()

    def __call__(self):  # type: ignore[no-untyped-def]
        return self.now


@pytest.fixture
def real_time(monkeypatch: pytest.MonkeyPatch) -> MovableClock:
    moving = MovableClock()
    monkeypatch.setattr(auth_clock, "now", moving)
    return moving


def login(client: TestClient, staff_id: int = 105, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/auth/login", json={"staff_id": staff_id, "password": password})


# Config, login and me


def test_config_is_public_and_no_store(client: TestClient) -> None:
    response = client.get("/auth/config")

    assert response.status_code == 200
    assert response.json() == {"auth_mode": "demo"}
    assert response.headers["cache-control"] == "no-store"


def test_config_follows_the_backend_mode(client: TestClient, session_mode: None) -> None:
    assert client.get("/auth/config").json() == {"auth_mode": "session"}


def test_login_sets_a_hardened_cookie_and_answers_like_me(client: TestClient, db: Session) -> None:
    response = login(client)

    assert response.status_code == 200
    me = {
        "staff_id": 105,
        "role": "staff",
        "home_ward_id": 1,
        "home_ward_name": "ICU",
        "must_change_password": False,
    }
    assert response.json() == me
    assert response.headers["cache-control"] == "no-store"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    attributes = {part.strip().lower() for part in cookie.split(";")[1:]}
    assert {"httponly", "secure", "path=/", "samesite=lax"} <= attributes
    assert not any(part.startswith("domain") for part in attributes)
    assert f"max-age={settings.auth_session_max_age_seconds}" in attributes

    token = client.cookies[SESSION_COOKIE]
    stored = db.scalars(select(AuthSession)).one()
    assert stored.token_hash != token and token not in stored.token_hash
    assert client.get("/auth/me").json() == me


@pytest.mark.parametrize(
    ("staff_id", "role"), [(900, "head_nurse"), (950, "supervisor"), (201, "staff")]
)
def test_me_maps_the_role_on_the_backend(
    client: TestClient, db: Session, staff_id: int, role: str
) -> None:
    auth_service.create_account(db, staff_id, PASSWORD, must_change_password=False)

    assert login(client, staff_id).json()["role"] == role


def test_every_login_gets_a_new_token(client: TestClient, db: Session) -> None:
    login(client)
    first = client.cookies[SESSION_COOKIE]
    login(client)

    assert client.cookies[SESSION_COOKIE] != first
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 2


@pytest.mark.parametrize(
    "case", ["wrong password", "no account", "unknown staff", "disabled", "inactive", "no actor"]
)
def test_failed_login_is_one_answer_whatever_the_reason(
    client: TestClient, db: Session, case: str
) -> None:
    staff_id, password = 105, PASSWORD
    if case == "wrong password":
        password = PASSWORD + "!"
    elif case == "no account":
        staff_id = 201
    elif case == "unknown staff":
        staff_id = 123456
    elif case == "disabled":
        auth_service.set_disabled(db, 105, True)
    elif case == "inactive":
        db.get(Staff, 105).status = StaffStatus.INACTIVE  # type: ignore[union-attr]
        db.commit()
    else:
        db.query(Actor).filter(Actor.staff_id == 105).delete()
        db.commit()

    response = login(client, staff_id, password)

    assert response.status_code == 401
    assert response.json() == {"detail": "AUTH_INVALID_CREDENTIALS"}
    assert "www-authenticate" not in response.headers
    assert "set-cookie" not in response.headers
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_legacy_staff_password_hash_is_not_a_password(client: TestClient) -> None:
    # STAFF.password_hash is "!" in the seed; 201 has no account
    assert login(client, 201, "!").status_code in (401, 422)
    assert login(client, 201, "!" * 12).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"staff_id": 105, "password": PASSWORD, "role": "supervisor"},
        {"staff_id": "105", "password": PASSWORD},
        {"staff_id": 0, "password": PASSWORD},
        {"staff_id": 105},
        {"staff_id": 105, "password": "x" * 1025},
    ],
)
def test_login_body_is_strict(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/auth/login", json=body).status_code == 422


# Origin


@pytest.mark.parametrize("origin", [None, "null", "https://evil.example", ORIGIN + "/"])
def test_auth_posts_need_an_allowed_origin_even_in_demo_mode(
    client: TestClient, db: Session, origin: str | None
) -> None:
    headers = {"Origin": origin} if origin else {}
    if origin is None:
        client.headers.pop("Origin")

    response = client.post(
        "/auth/login", json={"staff_id": 105, "password": PASSWORD}, headers=headers
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "AUTH_ORIGIN_FORBIDDEN"}
    assert response.headers["cache-control"] == "no-store"
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_session_mode_checks_origin_on_every_state_change_but_not_webhook_or_internal(
    client: TestClient, session_mode: None
) -> None:
    client.headers.pop("Origin")

    assert client.post("/demo/clock/freeze").json() == {"detail": "AUTH_ORIGIN_FORBIDDEN"}
    # Exempt: the LINE signature or the job secret is the check; neither got this far
    webhook = client.post("/line/webhook", content=b"{}")
    assert webhook.json() != {"detail": "AUTH_ORIGIN_FORBIDDEN"}
    internal = client.post("/internal/merge-windows/close-due")
    assert internal.json() != {"detail": "AUTH_ORIGIN_FORBIDDEN"}
    # Only that exact path is exempt
    assert client.post("/line/webhook/").json() == {"detail": "AUTH_ORIGIN_FORBIDDEN"}
    # Reads are not checked
    assert client.get("/clock").status_code == 200


def test_demo_mode_leaves_other_routes_without_an_origin_check(client: TestClient) -> None:
    client.headers.pop("Origin")

    assert client.post("/demo/clock/freeze").status_code == 200


# Rate limit


def test_eleventh_login_in_a_minute_is_429_before_any_hash(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for _ in range(10):
        assert login(client, password="wrong password!!").status_code == 401
    verified: list[str] = []
    monkeypatch.setattr(
        auth_service.passwords, "verify_password", lambda *args: verified.append("x") or True
    )

    response = login(client)

    assert response.status_code == 429
    assert response.json() == {"detail": "AUTH_RATE_LIMITED"}
    assert int(response.headers["retry-after"]) >= 1
    assert verified == []


# Session checks on every request


def test_session_mode_uses_the_cookie_and_ignores_x_demo_user(
    client: TestClient, session_mode: None
) -> None:
    anonymous = client.get("/me/offers", headers={"X-Demo-User": "900"})
    assert anonymous.status_code == 401
    assert anonymous.json() == {"detail": "AUTH_REQUIRED"}
    assert "www-authenticate" not in anonymous.headers

    login(client)
    # Logged in as 105: the header naming 900 changes nothing
    assert client.get("/me/offers", headers={"X-Demo-User": "900"}).status_code == 200


def test_demo_mode_still_takes_x_demo_user(client: TestClient) -> None:
    assert client.get("/me/offers", headers={"X-Demo-User": "105"}).status_code == 200
    assert client.get("/me/offers").status_code == 401


def test_session_is_checked_against_the_database_each_time(
    client: TestClient, db: Session, session_mode: None
) -> None:
    login(client)
    assert client.get("/me/offers").status_code == 200

    db.get(Staff, 105).status = StaffStatus.INACTIVE  # type: ignore[union-attr]
    db.commit()
    assert client.get("/me/offers").status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_absolute_expiry_ends_even_a_busy_session(
    client: TestClient, real_time: MovableClock, session_mode: None
) -> None:
    login(client)
    step = timedelta(seconds=1500)
    elapsed = timedelta()
    # One request every 25 minutes keeps it from going idle, until max age
    while elapsed + step < timedelta(seconds=settings.auth_session_max_age_seconds):
        real_time.now += step
        elapsed += step
        assert client.get("/me/offers").status_code == 200

    real_time.now += step
    assert client.get("/me/offers").status_code == 401


def test_session_ends_exactly_at_expires_at(
    client: TestClient, db: Session, real_time: MovableClock
) -> None:
    login(client)
    session = db.scalars(select(AuthSession)).one()
    real_time.now = session.expires_at - timedelta(microseconds=1)
    # Idle would end it first: move last_seen along without touching expires_at
    db.execute(
        AuthSession.__table__.update().values(last_seen_at=real_time.now - timedelta(seconds=1))
    )
    db.commit()
    assert client.get("/auth/me").status_code == 200

    real_time.now = session.expires_at
    assert client.get("/auth/me").status_code == 401


def test_idle_expiry_and_last_seen_moves_without_extending_expiry(
    client: TestClient, db: Session, real_time: MovableClock
) -> None:
    login(client)
    session = db.scalars(select(AuthSession)).one()
    expires_at = session.expires_at
    idle = timedelta(seconds=settings.auth_session_idle_seconds)

    real_time.now += idle - timedelta(seconds=1)
    assert client.get("/auth/me").status_code == 200
    db.expire_all()
    session = db.scalars(select(AuthSession)).one()
    assert session.last_seen_at == real_time.now
    assert session.expires_at == expires_at

    real_time.now += idle
    assert client.get("/auth/me").status_code == 401
    # An expired session is not woken up by the failed request
    db.expire_all()
    assert db.scalars(select(AuthSession)).one().last_seen_at == real_time.now - idle


def test_demo_clock_does_not_move_sessions(client: TestClient) -> None:
    # production_seeded froze the Demo Clock at D 21:00; sessions use real time anyway
    login(client)
    response = client.post("/demo/clock/advance", json={"seconds": 86400 * 3})

    assert response.status_code == 200
    assert client.get("/auth/me").status_code == 200


def test_tampered_or_unknown_cookie_is_401(client: TestClient) -> None:
    login(client)
    token = client.cookies[SESSION_COOKIE]
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, token[:-1] + ("A" if token[-1] != "A" else "B"))

    assert client.get("/auth/me").status_code == 401


def test_token_is_only_taken_from_the_cookie(client: TestClient) -> None:
    login(client)
    token = client.cookies[SESSION_COOKIE]
    client.cookies.clear()

    assert client.get(f"/auth/me?{SESSION_COOKIE}={token}").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# Logout


def test_logout_revokes_and_clears_the_cookie_and_is_idempotent(
    client: TestClient, db: Session
) -> None:
    login(client)
    token = client.cookies[SESSION_COOKIE]

    response = client.post("/auth/logout")

    assert response.status_code == 204
    cleared = response.headers["set-cookie"].lower()
    assert cleared.startswith(f"{SESSION_COOKIE}=") and "max-age=0" in cleared
    assert {"httponly", "secure", "path=/", "samesite=lax"} <= {
        p.strip() for p in cleared.split(";")
    }
    assert db.scalars(select(AuthSession)).one().revoked_at is not None
    client.cookies.set(SESSION_COOKIE, token)
    assert client.get("/auth/me").status_code == 401
    # Again, with the dead cookie and with none
    assert client.post("/auth/logout").status_code == 204
    client.cookies.clear()
    assert client.post("/auth/logout").status_code == 204


# Password change and must_change_password


def test_change_password_revokes_every_session_and_needs_a_new_login(
    client: TestClient, db: Session
) -> None:
    other = TestClient(app, base_url="https://testserver", headers={"Origin": ORIGIN})
    login(other)
    login(client)

    response = client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert db.scalar(select(func.count()).where(AuthSession.revoked_at.is_(None))) == 0
    assert other.get("/auth/me").status_code == 401
    account = db.scalars(select(AuthAccount)).one()
    assert account.credential_version == 2
    assert login(client).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_wrong_current_password_is_400_and_changes_nothing(client: TestClient, db: Session) -> None:
    login(client)

    response = client.post(
        "/auth/change-password",
        json={"current_password": "not my password", "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "AUTH_INVALID_PASSWORD"}
    assert client.get("/auth/me").status_code == 200
    assert db.scalars(select(AuthAccount)).one().credential_version == 1


@pytest.mark.parametrize("new_password", ["short", "x" * 129, "x" * 11])
def test_new_password_must_be_12_to_128_characters(client: TestClient, new_password: str) -> None:
    login(client)

    response = client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": new_password},
    )

    assert response.status_code == 422


def test_change_password_needs_a_session(client: TestClient) -> None:
    response = client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "AUTH_REQUIRED"}


def test_must_change_password_allows_only_me_logout_and_change(
    client: TestClient, db: Session, session_mode: None
) -> None:
    auth_service.reset_password(db, 105, PASSWORD)
    me = login(client).json()
    assert me["must_change_password"] is True

    blocked = client.get("/me/offers")
    assert blocked.status_code == 403
    assert blocked.json() == {"detail": "AUTH_PASSWORD_CHANGE_REQUIRED"}
    assert client.get("/auth/me").status_code == 200

    client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert login(client, password=NEW_PASSWORD).json()["must_change_password"] is False
    assert client.get("/me/offers").status_code == 200


def test_session_of_an_older_credential_version_is_dead(
    client: TestClient, db: Session, session_mode: None
) -> None:
    login(client)
    # As if a password change had committed without revoking (belt and braces)
    db.execute(
        AuthAccount.__table__.update().values(credential_version=AuthAccount.credential_version + 1)
    )
    db.commit()

    assert client.get("/me/offers").status_code == 401


def test_nothing_secret_in_responses(client: TestClient, db: Session) -> None:
    body = login(client).text + client.get("/auth/me").text
    account = db.scalars(select(AuthAccount)).one()
    session = db.scalars(select(AuthSession)).one()

    for secret in (PASSWORD, account.password_hash, session.token_hash, "argon2"):
        assert secret not in body


SECRET = "Sekr1t-never-echoed"
LOGIN_BAD_BODIES = [
    # Too long for the login bound
    {"staff_id": 105, "password": SECRET * 60},
    # Wrong type next to a password
    {"staff_id": "x", "password": SECRET},
    # Extra field: FastAPI's default echoes its value as `input`
    {"staff_id": 105, "password": SECRET, "role": SECRET},
    # Password not a string
    {"staff_id": 105, "password": [SECRET]},
    # Not an object at all: the whole body becomes `input`
    [SECRET, SECRET],
]
CHANGE_BAD_BODIES = [
    # The reviewer's case: an 11-character new password
    {"current_password": PASSWORD, "new_password": SECRET[:11]},
    {"current_password": PASSWORD, "new_password": SECRET * 10},
    {"current_password": SECRET * 60, "new_password": NEW_PASSWORD},
    {"current_password": PASSWORD, "new_password": NEW_PASSWORD, "extra": SECRET},
    {"current_password": {"nested": SECRET}, "new_password": NEW_PASSWORD},
]


def _assert_sanitized(response) -> None:  # type: ignore[no-untyped-def]
    assert response.status_code == 422
    assert SECRET not in response.text and SECRET[:11] not in response.text
    assert PASSWORD not in response.text and NEW_PASSWORD not in response.text
    for item in response.json()["detail"]:
        assert set(item) <= {"type", "loc", "msg"}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("body", LOGIN_BAD_BODIES)
def test_login_validation_errors_never_echo_the_password(client: TestClient, body: object) -> None:
    _assert_sanitized(client.post("/auth/login", json=body))


@pytest.mark.parametrize("body", CHANGE_BAD_BODIES)
def test_change_password_validation_errors_never_echo_a_password(
    client: TestClient, body: object
) -> None:
    login(client)

    _assert_sanitized(client.post("/auth/change-password", json=body))


def test_malformed_json_is_not_echoed(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        content=f'{{"staff_id": 105, "password": "{SECRET}"'.encode(),
        headers={"Content-Type": "application/json"},
    )

    _assert_sanitized(response)


def test_other_routes_keep_the_default_validation_detail(client: TestClient) -> None:
    response = client.post("/demo/clock/advance", json={"seconds": "soon"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["input"] == "soon"
