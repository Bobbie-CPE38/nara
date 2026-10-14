from typing import Literal

from pydantic import Field, SecretStr
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

    @property
    def real_line_enabled(self) -> bool:
        return bool(
            self.line_mode == "real"
            and self.line_channel_secret
            and self.line_channel_secret.get_secret_value()
            and self.line_channel_access_token
            and self.line_channel_access_token.get_secret_value()
        )


settings = Settings()
