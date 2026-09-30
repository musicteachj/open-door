import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests read the real environment, and CI sets APP_ENV, so start each one clean."""
    for name in ("APP_ENV", "DATABASE_URL", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)


def test_a_missing_database_url_stops_startup() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_the_database_url_must_use_the_asyncpg_driver() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg"):
        Settings(_env_file=None, database_url="postgresql://opendoor:opendoor@localhost/opendoor")


def test_defaults_apply_when_only_the_database_url_is_set() -> None:
    settings = Settings(
        _env_file=None, database_url="postgresql+asyncpg://opendoor:opendoor@localhost/opendoor"
    )
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"


def test_a_malformed_database_url_does_not_leak_its_password() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, database_url="postgresql://app:hunter2@db/app")

    assert "hunter2" not in str(excinfo.value)


def test_the_database_password_stays_out_of_the_settings_repr() -> None:
    settings = Settings(
        _env_file=None, database_url="postgresql+asyncpg://app:hunter2@localhost/app"
    )

    assert "hunter2" not in repr(settings)
