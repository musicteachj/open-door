"""Settings for the processes that hold a credential the API must not.

The API process loads only `DATABASE_URL` (app.core.config.Settings). The database owner's URL,
which bypasses row-level security, and the cleanup login's URL are read here, by the processes that
use them: Alembic and the owner-only scripts (OwnerSettings), and the cleanup job and its tests
(CleanupSettings). Each class loads only its own variable, from the environment or apps/api/.env,
and refuses to build without it. Neither needs an API key, so neither has the blank-key handling.
"""

from pydantic import Field, PostgresDsn, ValidationError, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import require_asyncpg_scheme

_CONFIG = SettingsConfigDict(
    # Relative to the working directory, like Settings: `make` and CI run from apps/api.
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore",
    # A malformed database URL would otherwise print its password in the startup error.
    hide_input_in_errors=True,
)


class _DatabaseUrlSettings(BaseSettings):
    """What the two classes share: their config, and the asyncpg check on their one URL."""

    model_config = _CONFIG

    @field_validator("migration_database_url", "cleanup_database_url", check_fields=False)
    @classmethod
    def require_asyncpg_driver(cls, value: PostgresDsn, info: ValidationInfo) -> PostgresDsn:
        return require_asyncpg_scheme(value, str(info.field_name))


class OwnerSettings(_DatabaseUrlSettings):
    """The database owner, for Alembic and the owner scripts. The API never loads it."""

    migration_database_url: PostgresDsn = Field(repr=False)


class CleanupSettings(_DatabaseUrlSettings):
    """The cleanup login, a member of od_cleanup. The API never loads it."""

    cleanup_database_url: PostgresDsn = Field(repr=False)


class DatabaseUrlError(Exception):
    """A required database URL is missing or malformed. The message never holds the URL."""


def _explain(error: ValidationError, variable: str) -> str:
    # include_input=False keeps the offending value, which may hold a password, out of the text.
    problems = error.errors(include_input=False)
    if all(problem["type"] == "missing" for problem in problems):
        return f"{variable} is not set. See apps/api/.env.example."
    return "; ".join(str(problem["msg"]).removeprefix("Value error, ") for problem in problems)


def owner_database_url() -> str:
    """The owner's URL, or `DatabaseUrlError` saying what is wrong with it."""
    try:
        return str(OwnerSettings().migration_database_url)
    except ValidationError as error:
        raise DatabaseUrlError(_explain(error, "MIGRATION_DATABASE_URL")) from None


def _load_cleanup_url() -> str:
    return str(CleanupSettings().cleanup_database_url)


def cleanup_database_url() -> str:
    """The cleanup login's URL, or `DatabaseUrlError` saying what is wrong with it."""
    try:
        return _load_cleanup_url()
    except ValidationError as error:
        raise DatabaseUrlError(_explain(error, "CLEANUP_DATABASE_URL")) from None


def optional_cleanup_database_url() -> str | None:
    """The cleanup login's URL, None if it is not set, or `DatabaseUrlError` if it is malformed."""
    try:
        return _load_cleanup_url()
    except ValidationError as error:
        if all(problem["type"] == "missing" for problem in error.errors(include_input=False)):
            return None
        raise DatabaseUrlError(_explain(error, "CLEANUP_DATABASE_URL")) from None
