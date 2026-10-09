import pytest
from pydantic import ValidationError

from app.core.config import Settings

DATABASE_URL = "postgresql+psycopg://user:pass@localhost:5432/db"


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)


def test_cors_origins_is_required() -> None:
    with pytest.raises(ValidationError, match="cors_origins"):
        Settings(_env_file=None)


def test_cors_origins_rejects_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "[]")

    with pytest.raises(ValidationError, match="cors_origins"):
        Settings(_env_file=None)


def test_cors_origins_parses_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000", "http://localhost:3001"]')

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:3001"]
