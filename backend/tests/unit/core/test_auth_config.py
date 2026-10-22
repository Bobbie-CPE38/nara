"""AUTH_MODE, APP_ENV and the session settings (docs/workflow.md 6.33.1-2, PR AU1)."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/db")
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    for name in (
        "APP_ENV",
        "AUTH_MODE",
        "AUTH_COOKIE_SECURE",
        "AUTH_SESSION_MAX_AGE_SECONDS",
        "AUTH_SESSION_IDLE_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_dev_demo_with_secure_cookie_and_team_timeouts() -> None:
    settings = Settings(_env_file=None)

    assert (settings.app_env, settings.auth_mode) == ("dev", "demo")
    assert settings.auth_cookie_secure is True
    assert settings.auth_session_max_age_seconds == 43200
    assert settings.auth_session_idle_seconds == 1800


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AUTH_MODE", "sessions"),
        ("AUTH_MODE", ""),
        ("AUTH_MODE", "Session"),
        ("APP_ENV", "prod"),
        ("APP_ENV", ""),
    ],
)
def test_unknown_mode_or_env_stops_startup_instead_of_falling_back(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=name.lower()):
        Settings(_env_file=None)


def test_insecure_cookie_is_refused_on_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "aws")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")

    with pytest.raises(ValidationError, match="AUTH_COOKIE_SECURE"):
        Settings(_env_file=None)


def test_insecure_cookie_is_allowed_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")

    assert Settings(_env_file=None).auth_cookie_secure is False


@pytest.mark.parametrize(
    ("max_age", "idle"), [("0", "1"), ("10", "0"), ("-5", "1"), ("100", "101")]
)
def test_timeouts_are_positive_and_idle_fits_in_max_age(
    monkeypatch: pytest.MonkeyPatch, max_age: str, idle: str
) -> None:
    monkeypatch.setenv("AUTH_SESSION_MAX_AGE_SECONDS", max_age)
    monkeypatch.setenv("AUTH_SESSION_IDLE_SECONDS", idle)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
