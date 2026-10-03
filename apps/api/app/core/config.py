"""Application settings, read from the environment and validated once at startup."""

import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# What a browser sends in its Origin header: a lowercase scheme and host, an optional port, and
# nothing after them. The same-origin check compares that header with APP_ORIGIN character for
# character, so a trailing slash or a path here would refuse every request. IPv6 literals such as
# http://[::1]:5173 are not supported.
ORIGIN_PATTERN = re.compile(r"(https?)://[a-z0-9.-]+(?::([0-9]{1,5}))?")
# Browsers leave the default port out of the Origin header, so it can never appear in APP_ORIGIN.
DEFAULT_PORTS = {"http": 80, "https": 443}


class Settings(BaseSettings):
    """Every setting the API reads. A missing or malformed value stops the process at boot."""

    model_config = SettingsConfigDict(
        # Relative to the working directory: `make` and CI always run the API from apps/api.
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # A malformed database URL would otherwise print its password in the startup error.
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    # The API's own login, a member of od_app. Row-level security applies to it.
    database_url: PostgresDsn = Field(repr=False)
    # The database owner, for Alembic and the bootstrap script. The API never uses it.
    migration_database_url: PostgresDsn | None = Field(default=None, repr=False)
    # The cleanup login, a member of od_cleanup: its tests now, and the cleanup job in Phase 8.
    cleanup_database_url: PostgresDsn | None = Field(default=None, repr=False)
    # The web app's origin, for the same-origin check on requests that change state.
    app_origin: str = "http://localhost:5173"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url", "migration_database_url", "cleanup_database_url")
    @classmethod
    def require_asyncpg_driver(
        cls, value: PostgresDsn | None, info: ValidationInfo
    ) -> PostgresDsn | None:
        if value is not None and value.scheme != "postgresql+asyncpg":
            msg = f"{str(info.field_name).upper()} must use the postgresql+asyncpg:// scheme"
            raise ValueError(msg)
        return value

    @field_validator("app_origin")
    @classmethod
    def require_bare_origin(cls, value: str) -> str:
        match = ORIGIN_PATTERN.fullmatch(value)
        if match is None:
            msg = (
                "APP_ORIGIN must look like http://localhost:5173: lowercase, "
                "with no path and no trailing slash"
            )
            raise ValueError(msg)
        scheme, port = match.groups()
        if port is not None:
            if not 1 <= int(port) <= 65535:
                msg = "APP_ORIGIN port must be between 1 and 65535"
                raise ValueError(msg)
            if port.startswith("0"):
                # Browsers send the port as a plain number, so 05173 would never equal 5173.
                msg = "APP_ORIGIN port must be written without leading zeros"
                raise ValueError(msg)
            if int(port) == DEFAULT_PORTS[scheme]:
                msg = "APP_ORIGIN must leave the default port out, because browsers omit it"
                raise ValueError(msg)
        return value


@lru_cache
def get_settings() -> Settings:
    """Read settings once per process."""
    return Settings()
