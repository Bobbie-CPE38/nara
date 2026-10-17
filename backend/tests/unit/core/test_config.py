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
    # Compose passes unset LLM_* variables as "" into the container: test the defaults only
    for name in (
        "LLM_ENABLED",
        "LLM_PROVIDER",
        "LLM_MODEL_ID",
        "AWS_REGION",
        "LLM_MAX_OUTPUT_TOKENS",
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "LLM_MAX_RETRIES",
        "LLM_INPUT_PRICE_PER_MTOK_USD",
        "LLM_OUTPUT_PRICE_PER_MTOK_USD",
    ):
        monkeypatch.delenv(name, raising=False)

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


QUOTA_VARIABLES = (
    "LLM_DAILY_CALL_CAP",
    "LLM_QUOTA_TIMEZONE",
    "LLM_MONTHLY_BUDGET_USD",
    "LLM_MAX_INPUT_TOKENS",
    "LLM_MAX_ATTEMPTS_PER_ROW",
    "LLM_TRIAL_CALL_CAP",
)


def test_llm_quota_defaults_come_from_the_constants(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    for name in QUOTA_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_daily_call_cap == 100
    assert settings.llm_quota_timezone == "Asia/Bangkok"
    assert settings.llm_monthly_budget_usd == Decimal(20)
    assert settings.llm_max_input_tokens == 5_000
    assert settings.llm_max_attempts_per_row == 4
    assert settings.llm_trial_call_cap == 180


def test_blank_llm_quota_variables_keep_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # Compose passes an unset variable as ""
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    for name in QUOTA_VARIABLES:
        monkeypatch.setenv(name, "")

    settings = Settings(_env_file=None)

    assert settings.llm_daily_call_cap == 100 and settings.llm_trial_call_cap == 180
    assert settings.llm_quota_timezone == "Asia/Bangkok"


def test_llm_quota_can_change_without_a_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "40")
    monkeypatch.setenv("LLM_MAX_INPUT_TOKENS", "3000")

    settings = Settings(_env_file=None)

    assert settings.llm_daily_call_cap == 40 and settings.llm_max_input_tokens == 3000


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLM_DAILY_CALL_CAP", "-1"),
        ("LLM_MAX_INPUT_TOKENS", "0"),
        ("LLM_MAX_ATTEMPTS_PER_ROW", "0"),
        ("LLM_TRIAL_CALL_CAP", "-1"),
        ("LLM_MONTHLY_BUDGET_USD", "-1"),
    ],
)
def test_llm_quota_bounds_are_validated(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=name.lower()):
        Settings(_env_file=None)


@pytest.mark.parametrize("zone", ["Asia/Bangkokk", "Not/AZone", "../etc/passwd"])
def test_an_unknown_quota_timezone_fails_at_startup(monkeypatch: pytest.MonkeyPatch, zone) -> None:
    """Review of PR #108: PostgreSQL would reject it only at the first reservation."""
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    monkeypatch.setenv("LLM_QUOTA_TIMEZONE", zone)

    with pytest.raises(ValidationError, match="llm_quota_timezone"):
        Settings(_env_file=None)


def test_a_known_quota_timezone_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    monkeypatch.setenv("LLM_QUOTA_TIMEZONE", "UTC")

    assert Settings(_env_file=None).llm_quota_timezone == "UTC"
