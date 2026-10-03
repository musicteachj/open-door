"""Application settings, read from the environment and validated once at startup."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every setting the API reads. A missing or malformed value stops the process at boot."""

    model_config = SettingsConfigDict(
        # Relative to the working directory: `make` and CI always run the API from apps/api.
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # A malformed DATABASE_URL would otherwise print its password in the startup error.
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: PostgresDsn = Field(repr=False)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def require_asyncpg_driver(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+asyncpg":
            msg = "DATABASE_URL must use the postgresql+asyncpg:// scheme"
            raise ValueError(msg)
        return value


@lru_cache
def get_settings() -> Settings:
    """Read settings once per process."""
    return Settings()
