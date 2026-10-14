from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @field_validator("llm_input_price_per_mtok_usd", "llm_output_price_per_mtok_usd", mode="before")
    @classmethod
    def _blank_price_is_unset(cls, value: Any) -> Any:
        # Compose passes unset variables as "", which means "no price"
        if isinstance(value, str) and not value.strip():
            return None
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
    def llm_ready(self) -> bool:
        if not self.llm_enabled:
            return False
        if self.llm_provider == "fake":
            return True
        return bool(self.llm_model_id and self.aws_region)


settings = Settings()
