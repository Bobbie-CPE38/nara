from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    # Origins allowed to call the API from a browser (JSON list in .env).
    # Required and non-empty, so a missing value stops startup instead of blocking the browser
    cors_origins: list[str] = Field(min_length=1)


settings = Settings()
