from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import (
    LLM_DAILY_CALL_CAP,
    LLM_MAX_ATTEMPTS_PER_ROW,
    LLM_MAX_INPUT_TOKENS,
    LLM_MONTHLY_BUDGET_USD,
    LLM_QUOTA_TIMEZONE,
    LLM_TRIAL_CALL_CAP,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    # Origins allowed to call the API from a browser (JSON list in .env).
    # Required and non-empty, so a missing value stops startup instead of blocking the browser
    cors_origins: list[str] = Field(min_length=1)
    # Shared with the job service that calls the /internal routes. Unset = those
    # routes answer 503. The value comes from the environment, never from the repo
    internal_job_secret: str | None = Field(default=None, min_length=8)
    line_mode: Literal["simulation", "real"] = "simulation"
    line_channel_secret: SecretStr | None = None
    line_channel_access_token: SecretStr | None = None
    # LLM ranking explanation (round 3 PR X). Off by default: nothing is enqueued or called.
    # Round 3 only uses "fake"; "bedrock" needs a model id and region
    llm_enabled: bool = False
    llm_provider: Literal["fake", "bedrock"] = "fake"
    llm_model_id: str | None = None
    aws_region: str | None = None
    llm_max_output_tokens: int = Field(1024, ge=1, le=4096)
    # Per attempt
    llm_request_timeout_seconds: float = Field(15, gt=0, le=60)
    # Total attempts = 1 + this, so at most 2
    llm_max_retries: int = Field(1, ge=0, le=1)
    llm_input_price_per_mtok_usd: Decimal | None = None
    llm_output_price_per_mtok_usd: Decimal | None = None
    # Round 6 PR B1 (docs/workflow.md 6.27, 6.28). Defaults live in core/constants.py;
    # these let the team change them without a release. 0 for a cap means "no calls"
    llm_daily_call_cap: int = Field(LLM_DAILY_CALL_CAP, ge=0)
    llm_quota_timezone: str = Field(LLM_QUOTA_TIMEZONE, min_length=1)
    llm_monthly_budget_usd: Decimal = Field(Decimal(LLM_MONTHLY_BUDGET_USD), ge=0)
    llm_max_input_tokens: int = Field(LLM_MAX_INPUT_TOKENS, ge=1)
    llm_max_attempts_per_row: int = Field(LLM_MAX_ATTEMPTS_PER_ROW, ge=1)
    llm_trial_call_cap: int = Field(LLM_TRIAL_CALL_CAP, ge=0)

    @field_validator(
        "llm_input_price_per_mtok_usd",
        "llm_output_price_per_mtok_usd",
        "llm_daily_call_cap",
        "llm_quota_timezone",
        "llm_monthly_budget_usd",
        "llm_max_input_tokens",
        "llm_max_attempts_per_row",
        "llm_trial_call_cap",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, value: Any, info: ValidationInfo) -> Any:
        # Compose passes unset variables as "": no price, or the default of a limit
        if isinstance(value, str) and not value.strip():
            if info.field_name is None:
                return None
            return cls.model_fields[info.field_name].get_default()
        return value

    @field_validator("llm_quota_timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        # PostgreSQL would reject an unknown zone only at the first quota reservation
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"unknown time zone {value!r}") from error
        return value

    @property
    def real_line_enabled(self) -> bool:
        return bool(
            self.line_mode == "real"
            and self.line_channel_secret
            and self.line_channel_secret.get_secret_value()
            and self.line_channel_access_token
            and self.line_channel_access_token.get_secret_value()
        )

    @property
    def llm_configured(self) -> bool:
        """The provider has what it needs, whether or not LLM_ENABLED is on."""
        if self.llm_provider == "fake":
            return True
        return bool(self.llm_model_id and self.aws_region)

    @property
    def llm_ready(self) -> bool:
        return self.llm_enabled and self.llm_configured


settings = Settings()
