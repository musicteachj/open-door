from copy import deepcopy
from decimal import Decimal
from pathlib import Path
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
        "ANTHROPIC_API_KEY",
        "AI_TRANSPORT",
        "AI_SANDBOX_BUDGET_USD",
        "AI_DAILY_BUDGET_USD",
        "AI_HEARTBEAT_SECONDS",
        "ENCRYPTION_KEYRING",
        "ENCRYPTION_KEYRING_FILE",
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


@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_anthropic_key_counts_as_unset(value: str) -> None:
    # An agent shell may export ANTHROPIC_API_KEY as an empty string, which would shadow .env.
    settings = Settings(_env_file=None, database_url=APP_URL, anthropic_api_key=value)
    assert settings.anthropic_api_key is None


def test_an_empty_voyage_key_still_counts_as_unset() -> None:
    assert Settings(_env_file=None, database_url=APP_URL, voyage_api_key="").voyage_api_key is None


def test_the_anthropic_key_stays_out_of_the_settings_repr() -> None:
    settings = Settings(_env_file=None, database_url=APP_URL, anthropic_api_key="sk-ant-hunter2")
    assert "hunter2" not in repr(settings)


def test_the_assistant_defaults_match_the_spec() -> None:
    settings = Settings(_env_file=None, database_url=APP_URL)
    assert settings.anthropic_api_key is None
    assert settings.ai_transport == "scripted"
    assert settings.ai_sandbox_budget_usd == Decimal("1.00")
    assert settings.ai_daily_budget_usd == Decimal("3.00")
    assert settings.ai_heartbeat_seconds == 15


@pytest.mark.parametrize("transport", ["scripted", "replay", "anthropic"])
def test_settings_accept_production_with_any_transport(transport: str) -> None:
    # Alembic, the setup scripts, and the future cleanup job build Settings in production and never
    # call the model, so they must not need the assistant's variables. The rule that production
    # runs `anthropic` is checked when the API starts (app.ai.transport).
    settings = Settings(
        _env_file=None, database_url=APP_URL, app_env="production", ai_transport=transport
    )
    assert settings.ai_transport == transport


def test_production_accepts_the_anthropic_transport_with_a_key() -> None:
    settings = Settings(
        _env_file=None,
        database_url=APP_URL,
        app_env="production",
        ai_transport="anthropic",
        anthropic_api_key="sk-ant-test",
    )
    assert settings.ai_transport == "anthropic"


@pytest.mark.parametrize("env", ["development", "test", "production"])
@pytest.mark.parametrize("key", [None, "", " "])
def test_settings_accept_the_anthropic_transport_with_no_key(env: str, key: str | None) -> None:
    # Alembic, the setup scripts, and the tests build Settings and never call the model. Only
    # building the Anthropic transport needs the key (anthropic_transport.from_settings).
    settings = Settings(
        _env_file=None,
        database_url=APP_URL,
        app_env=env,
        ai_transport="anthropic",
        anthropic_api_key=key,
    )
    assert settings.ai_transport == "anthropic"
    assert settings.anthropic_api_key is None


def test_an_unknown_transport_is_refused() -> None:
    with pytest.raises(ValidationError, match="ai_transport"):
        Settings(_env_file=None, database_url=APP_URL, ai_transport="openai")


@pytest.mark.parametrize("field", ["ai_sandbox_budget_usd", "ai_daily_budget_usd"])
@pytest.mark.parametrize("amount", ["0", "-1", "-0.01"])
def test_the_budgets_must_be_positive(field: str, amount: str) -> None:
    budgets: dict[str, Any] = {field: Decimal(amount)}
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None, database_url=APP_URL, **budgets)


def test_the_heartbeat_can_be_turned_off_but_not_negative() -> None:
    off = Settings(_env_file=None, database_url=APP_URL, ai_heartbeat_seconds=0)
    assert off.ai_heartbeat_seconds == 0
    with pytest.raises(ValidationError, match="ai_heartbeat_seconds"):
        Settings(_env_file=None, database_url=APP_URL, ai_heartbeat_seconds=-1)


@pytest.mark.parametrize("name", ["ANTHROPIC_API_KEY", "VOYAGE_API_KEY"])
def test_an_empty_environment_variable_does_not_override_the_env_file(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # An agent shell can export these as empty strings. That used to shadow the key in .env.
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={APP_URL}\n{name}=sk-from-the-file\n")
    monkeypatch.setenv(name, "")

    settings = Settings(_env_file=env_file)

    key = settings.anthropic_api_key if name == "ANTHROPIC_API_KEY" else settings.voyage_api_key
    assert key is not None
    assert key.get_secret_value() == "sk-from-the-file"


def test_an_empty_value_in_the_env_file_still_means_no_key(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={APP_URL}\nANTHROPIC_API_KEY=\n")

    assert Settings(_env_file=env_file).anthropic_api_key is None


def test_a_real_environment_variable_still_overrides_the_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={APP_URL}\nANTHROPIC_API_KEY=sk-from-the-file\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-the-shell")

    key = Settings(_env_file=env_file).anthropic_api_key

    assert key is not None
    assert key.get_secret_value() == "sk-from-the-shell"


@pytest.mark.parametrize("name", ["APP_ENV", "AI_TRANSPORT"])
def test_an_empty_environment_variable_still_fails_validation_for_other_settings(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Only the API keys' empty values are ignored. A template that renders APP_ENV= empty must not
    # quietly become development and skip the production checks.
    monkeypatch.setenv(name, "")

    with pytest.raises(ValidationError, match=name.lower()):
        Settings(_env_file=None, database_url=APP_URL)


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_shell_key_does_not_override_the_env_file(
    value: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={APP_URL}\nANTHROPIC_API_KEY=sk-from-the-file\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", value)

    key = Settings(_env_file=env_file).anthropic_api_key

    assert key is not None
    assert key.get_secret_value() == "sk-from-the-file"


def test_the_keyring_file_defaults_to_the_development_path_and_no_keyring_is_set() -> None:
    settings = Settings(_env_file=None, database_url=APP_URL)
    assert settings.encryption_keyring is None
    assert settings.encryption_keyring_file is not None
    assert settings.encryption_keyring_file.get_secret_value() == ".keys/keyring"


def test_a_blank_keyring_file_in_dotenv_counts_as_unset(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={APP_URL}\nENCRYPTION_KEYRING_FILE=\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.encryption_keyring_file is not None
    assert settings.encryption_keyring_file.get_secret_value() == ".keys/keyring"


def test_a_blank_keyring_file_beside_an_inline_keyring_is_not_two_keyrings(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"DATABASE_URL={APP_URL}\nENCRYPTION_KEYRING=k1:abc\nENCRYPTION_KEYRING_FILE=\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.encryption_keyring is not None


def test_settings_rebuilt_from_a_copy_of_their_dump_are_not_refused(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"DATABASE_URL={APP_URL}\nENCRYPTION_KEYRING=k1:abc\nENCRYPTION_KEYRING_FILE=\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=env_file)

    # A copy shares no object with the settings, so nothing can tell a blank file by identity.
    rebuilt = Settings.model_validate(deepcopy(settings.model_dump(exclude_unset=True)))

    assert rebuilt.encryption_keyring is not None
    assert rebuilt.encryption_keyring_file is not None
    assert rebuilt.encryption_keyring_file.get_secret_value() == ".keys/keyring"


def test_the_keyring_settings_read_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", APP_URL)
    monkeypatch.setenv("ENCRYPTION_KEYRING", "k1:abc")
    settings = Settings(_env_file=None)
    assert settings.encryption_keyring is not None
    assert settings.encryption_keyring.get_secret_value() == "k1:abc"

    monkeypatch.delenv("ENCRYPTION_KEYRING")
    monkeypatch.setenv("ENCRYPTION_KEYRING_FILE", "/tmp/ring")  # noqa: S108
    settings = Settings(_env_file=None)
    assert settings.encryption_keyring_file is not None
    assert settings.encryption_keyring_file.get_secret_value() == "/tmp/ring"  # noqa: S108


def test_neither_keyring_setting_ever_prints() -> None:
    settings = Settings(
        _env_file=None, database_url=APP_URL, encryption_keyring="topsecretid:c2VjcmV0"
    )
    assert "topsecretid" not in repr(settings)
    assert "topsecretid" not in str(settings)
    assert ".keys/keyring" not in repr(settings)
    assert "topsecretid" not in repr(settings.encryption_keyring)


def test_setting_both_the_keyring_and_the_keyring_file_is_refused() -> None:
    with pytest.raises(ValidationError, match="not both") as excinfo:
        Settings(
            _env_file=None,
            database_url=APP_URL,
            encryption_keyring="topsecretid:c2VjcmV0",
            encryption_keyring_file="/tmp/ring",  # noqa: S108
        )
    assert "topsecretid" not in str(excinfo.value)


def test_an_explicit_keyring_file_that_spells_the_default_beside_a_keyring_is_refused() -> None:
    with pytest.raises(ValidationError, match="not both"):
        Settings(
            _env_file=None,
            database_url=APP_URL,
            encryption_keyring="k1:abc",
            encryption_keyring_file=".keys/keyring",
        )


def test_an_explicit_default_keyring_file_in_dotenv_beside_a_keyring_is_refused(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"DATABASE_URL={APP_URL}\nENCRYPTION_KEYRING=k1:abc\n"
        "ENCRYPTION_KEYRING_FILE=.keys/keyring\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="not both"):
        Settings(_env_file=env_file)


def test_both_set_in_the_environment_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", APP_URL)
    monkeypatch.setenv("ENCRYPTION_KEYRING", "k1:abc")
    monkeypatch.setenv("ENCRYPTION_KEYRING_FILE", "/tmp/ring")  # noqa: S108
    with pytest.raises(ValidationError, match="not both"):
        Settings(_env_file=None)


def test_a_blank_keyring_in_the_environment_is_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A shell can export it empty; the value in .env must still win.
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={APP_URL}\nENCRYPTION_KEYRING=k1:fromdotenv\n")
    monkeypatch.setenv("ENCRYPTION_KEYRING", "   ")
    settings = Settings(_env_file=env_file)
    assert settings.encryption_keyring is not None
    assert settings.encryption_keyring.get_secret_value() == "k1:fromdotenv"


def test_a_blank_keyring_counts_as_unset() -> None:
    settings = Settings(_env_file=None, database_url=APP_URL, encryption_keyring="  ")
    assert settings.encryption_keyring is None


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_keyring_file_in_the_environment_is_ignored(
    value: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={APP_URL}\nENCRYPTION_KEYRING_FILE=/from/dotenv\n")
    monkeypatch.setenv("ENCRYPTION_KEYRING_FILE", value)
    settings = Settings(_env_file=env_file)
    assert settings.encryption_keyring_file is not None
    assert settings.encryption_keyring_file.get_secret_value() == "/from/dotenv"


def test_a_blank_keyring_file_in_the_environment_leaves_the_default_without_a_dotenv_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={APP_URL}\n")
    monkeypatch.setenv("ENCRYPTION_KEYRING_FILE", "")
    settings = Settings(_env_file=env_file)
    assert settings.encryption_keyring_file is not None
    assert settings.encryption_keyring_file.get_secret_value() == ".keys/keyring"
