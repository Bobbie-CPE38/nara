from decimal import Decimal

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


def test_llm_defaults_keep_it_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')

    settings = Settings(_env_file=None)

    assert settings.llm_enabled is False
    assert settings.llm_provider == "fake"
    assert settings.llm_model_id is None
    assert settings.aws_region is None
    assert settings.llm_max_output_tokens == 1024
    assert settings.llm_request_timeout_seconds == 15
    assert settings.llm_max_retries == 1
    assert settings.llm_input_price_per_mtok_usd is None
    assert settings.llm_output_price_per_mtok_usd is None
    assert settings.llm_ready is False


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLM_MAX_RETRIES", "2"),
        ("LLM_MAX_RETRIES", "-1"),
        ("LLM_REQUEST_TIMEOUT_SECONDS", "0"),
        ("LLM_REQUEST_TIMEOUT_SECONDS", "-1"),
        ("LLM_REQUEST_TIMEOUT_SECONDS", "61"),
        ("LLM_MAX_OUTPUT_TOKENS", "0"),
        ("LLM_MAX_OUTPUT_TOKENS", "4097"),
        ("LLM_PROVIDER", "openai"),
    ],
)
def test_llm_bounds_are_validated(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=name.lower()):
        Settings(_env_file=None)


def test_blank_llm_prices_mean_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    monkeypatch.setenv("LLM_INPUT_PRICE_PER_MTOK_USD", "")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_PER_MTOK_USD", "15.5")

    settings = Settings(_env_file=None)

    assert settings.llm_input_price_per_mtok_usd is None
    assert settings.llm_output_price_per_mtok_usd == Decimal("15.5")


def test_llm_ready_needs_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("LLM_PROVIDER", "fake")

    assert Settings(_env_file=None).llm_ready is False


def test_llm_ready_for_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    monkeypatch.setenv("LLM_ENABLED", "true")

    assert Settings(_env_file=None).llm_ready is True


@pytest.mark.parametrize(
    ("model_id", "region"),
    [(None, None), ("model-x", None), (None, "ap-southeast-1"), ("", "ap-southeast-1")],
)
def test_llm_not_ready_for_bedrock_without_model_and_region(
    monkeypatch: pytest.MonkeyPatch, model_id: str | None, region: str | None
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    if model_id is not None:
        monkeypatch.setenv("LLM_MODEL_ID", model_id)
    if region is not None:
        monkeypatch.setenv("AWS_REGION", region)

    assert Settings(_env_file=None).llm_ready is False


def test_llm_ready_for_bedrock_with_model_and_region(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("LLM_MODEL_ID", "model-x")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-1")

    assert Settings(_env_file=None).llm_ready is True
