from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
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
    # Round 3 only uses "fake"; "bedrock" needs a model id and region. "lambda" (round 6
    # PR B3) reaches Bedrock through the API Gateway and Lambda proxy of deploy/aws/lambda,
    # because the EC2 instance has no IAM role: it needs the URL and the usage-plan API key.
    # The model and Region are the proxy's; LLM_MODEL_ID and AWS_REGION, when set, are only
    # the fallback the call log shows if the proxy does not answer with its own
    llm_enabled: bool = False
    llm_provider: Literal["fake", "bedrock", "lambda"] = "fake"
    llm_model_id: str | None = None
    aws_region: str | None = None
    llm_lambda_url: str | None = None
    llm_lambda_api_key: SecretStr | None = None
    # Round 6 PR EV7 (docs/workflow.md 6.37.9): a demo reset gives the test accounts of
    # demo_account_service this password, so they log in without LINE. Unset = no accounts.
    # From the machine's env file, never the repo
    # 12 characters at least, like every password of a web account (6.33.2)
    demo_account_password: SecretStr | None = Field(default=None, min_length=12)
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
    # Round 6 PR AU1 (docs/workflow.md 6.33). Any other value stops startup: an unknown
    # mode must never fall back to demo, where X-Demo-User names anyone
    app_env: Literal["dev", "aws"] = "dev"
    auth_mode: Literal["demo", "session"] = "demo"
    # Only APP_ENV=dev may turn it off, for a browser on plain-HTTP localhost
    auth_cookie_secure: bool = True
    auth_session_max_age_seconds: int = Field(43200, gt=0)
    auth_session_idle_seconds: int = Field(1800, gt=0)

    @model_validator(mode="after")
    def _auth_settings_agree(self) -> "Settings":
        if self.app_env == "aws" and not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE=false is allowed only with APP_ENV=dev")
        if self.auth_session_idle_seconds > self.auth_session_max_age_seconds:
            raise ValueError(
                "AUTH_SESSION_IDLE_SECONDS must not exceed AUTH_SESSION_MAX_AGE_SECONDS"
            )
        return self

    @field_validator(
        "llm_input_price_per_mtok_usd",
        "llm_output_price_per_mtok_usd",
        "llm_daily_call_cap",
        "llm_quota_timezone",
        "llm_monthly_budget_usd",
        "llm_max_input_tokens",
        "llm_max_attempts_per_row",
        "llm_trial_call_cap",
        "llm_lambda_url",
        "llm_lambda_api_key",
        "demo_account_password",
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

    @field_validator("llm_lambda_url")
    @classmethod
    def _https_proxy(cls, value: str | None) -> str | None:
        # The API key travels in a header: never over plain HTTP
        if value is not None and not value.startswith("https://"):
            raise ValueError("LLM_LAMBDA_URL must be an https:// URL")
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
        if self.llm_provider == "lambda":
            key = self.llm_lambda_api_key
            return bool(self.llm_lambda_url and key is not None and key.get_secret_value())
        return bool(self.llm_model_id and self.aws_region)

    @property
    def llm_ready(self) -> bool:
        return self.llm_enabled and self.llm_configured


settings = Settings()
