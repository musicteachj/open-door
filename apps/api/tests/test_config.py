from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

APP_URL = "postgresql+asyncpg://od_app_login:od_app_dev@localhost/opendoor"
DATABASE_URL_FIELDS = ("database_url", "migration_database_url", "cleanup_database_url")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests read the real environment, and CI sets APP_ENV, so start each one clean."""
    for name in (
        "APP_ENV",
        "DATABASE_URL",
        "MIGRATION_DATABASE_URL",
        "CLEANUP_DATABASE_URL",
        "APP_ORIGIN",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_a_missing_database_url_stops_startup() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


@pytest.mark.parametrize("field", DATABASE_URL_FIELDS)
def test_every_database_url_must_use_the_asyncpg_driver(field: str) -> None:
    urls: dict[str, Any] = {
        "database_url": APP_URL,
        field: "postgresql://opendoor:opendoor@localhost/opendoor",
    }
    with pytest.raises(ValidationError, match=rf"{field.upper()} must use the postgresql\+asyncpg"):
        Settings(_env_file=None, **urls)


def test_defaults_apply_when_only_the_database_url_is_set() -> None:
    settings = Settings(_env_file=None, database_url=APP_URL)
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.migration_database_url is None
    assert settings.cleanup_database_url is None
    assert settings.app_origin == "http://localhost:5173"


@pytest.mark.parametrize("field", DATABASE_URL_FIELDS)
def test_a_malformed_database_url_does_not_leak_its_password(field: str) -> None:
    urls: dict[str, Any] = {"database_url": APP_URL, field: "postgresql://app:hunter2@db/app"}
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, **urls)

    assert "hunter2" not in str(excinfo.value)


def test_no_database_password_appears_in_the_settings_repr() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://app:hunter2@localhost/app",
        migration_database_url="postgresql+asyncpg://owner:swordfish@localhost/app",
        cleanup_database_url="postgresql+asyncpg://cleanup:letmein@localhost/app",
    )

    for password in ("hunter2", "swordfish", "letmein"):
        assert password not in repr(settings)


@pytest.mark.parametrize(
    "origin", ["http://localhost:5173", "https://opendoor.example.com", "http://127.0.0.1:8080"]
)
def test_the_app_origin_accepts_a_bare_origin(origin: str) -> None:
    assert Settings(_env_file=None, database_url=APP_URL, app_origin=origin).app_origin == origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173/",
        "http://localhost:5173/app",
        "http://localhost:5173?next=1",
        "localhost:5173",
        "ftp://localhost",
        "HTTP://LOCALHOST:5173",
        "http://user@localhost:5173",
    ],
)
def test_the_app_origin_must_be_scheme_host_and_port_only(origin: str) -> None:
    with pytest.raises(ValidationError, match="APP_ORIGIN must look like"):
        Settings(_env_file=None, database_url=APP_URL, app_origin=origin)


@pytest.mark.parametrize("origin", ["http://localhost:80", "https://example.com:443"])
def test_the_app_origin_must_leave_out_a_default_port(origin: str) -> None:
    # Browsers omit the default port from the Origin header, so this value could never match.
    with pytest.raises(ValidationError, match="leave the default port out"):
        Settings(_env_file=None, database_url=APP_URL, app_origin=origin)


@pytest.mark.parametrize(
    "origin", ["http://localhost:0", "http://localhost:65536", "http://localhost:99999"]
)
def test_the_app_origin_port_must_be_between_1_and_65535(origin: str) -> None:
    with pytest.raises(ValidationError, match="port must be between 1 and 65535"):
        Settings(_env_file=None, database_url=APP_URL, app_origin=origin)


@pytest.mark.parametrize("origin", ["http://localhost:05173", "http://localhost:0080"])
def test_the_app_origin_port_must_be_written_without_leading_zeros(origin: str) -> None:
    # Browsers send the port as a plain number, so 05173 would never match 5173.
    with pytest.raises(ValidationError, match="without leading zeros"):
        Settings(_env_file=None, database_url=APP_URL, app_origin=origin)


@pytest.mark.parametrize(
    "origin", ["https://example.com:8443", "http://localhost:5173", "http://localhost:443"]
)
def test_the_app_origin_accepts_a_port_that_is_not_the_default_for_its_scheme(origin: str) -> None:
    assert Settings(_env_file=None, database_url=APP_URL, app_origin=origin).app_origin == origin
