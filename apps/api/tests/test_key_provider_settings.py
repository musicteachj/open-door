"""The keyring in production: it starts with a real one, and refuses anything else.

A refusal's message and the logs never hold key bytes.
"""

import base64
import logging
import os
import secrets
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.encryption import KeyProvider, LocalKeyProvider
from app.main import build_key_provider, create_app

APP_URL = "postgresql+asyncpg://od_app_login:od_app_dev@localhost/opendoor"
TEST_KEYRING = "test:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def real_keyring() -> tuple[str, str]:
    """A fresh keyring line and the key's base64, for checking it never leaks."""
    encoded = base64.b64encode(secrets.token_bytes(32)).decode()
    return f"k1:{encoded}", encoded


def production(
    *,
    keyring: str | None = None,
    keyring_file: str | None = None,
    app_env: str = "production",
) -> Settings:
    return Settings(
        _env_file=None,
        database_url=APP_URL,
        app_env=app_env,
        app_origin="http://localhost:8300",
        ai_transport="anthropic",
        anthropic_api_key=SecretStr("dummy-key-for-a-startup-test"),
        # The API's startup check wants these in production (a loopback origin needs no proxy list).
        turnstile_site_key="0x4AAAAAAAreal",
        turnstile_secret_key=SecretStr("0x4AAAAAAAreal-secret"),
        sandbox_ip_hash_key=SecretStr("k" * 40),
        encryption_keyring=None if keyring is None else SecretStr(keyring),
        encryption_keyring_file=None if keyring_file is None else SecretStr(keyring_file),
    )


def test_production_starts_with_a_real_keyring() -> None:
    keyring, _ = real_keyring()

    app = create_app(production(keyring=keyring))

    assert app is not None


def test_the_provider_is_returned_as_the_protocol() -> None:
    keyring, _ = real_keyring()

    keys: KeyProvider = build_key_provider(production(keyring=keyring))

    assert isinstance(keys, LocalKeyProvider)
    assert keys.wrap(bytes(32), aad=b"a")[0] == "k1"


def test_production_refuses_the_test_key_without_naming_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ValueError, match="only APP_ENV=test accepts") as refused:
        create_app(production(keyring=TEST_KEYRING))

    assert TEST_KEYRING.partition(":")[2] not in str(refused.value) + caplog.text


def test_production_refuses_no_keyring_at_all(tmp_path: Path) -> None:
    missing = str(tmp_path / "no-such-keyring")

    with pytest.raises(ValueError, match="missing or unreadable"):
        create_app(production(keyring_file=missing))
    with pytest.raises(ValueError, match="No keyring"):
        build_key_provider(production())


@pytest.mark.skipif(os.name == "nt", reason="file modes")
@pytest.mark.parametrize("mode", [0o640, 0o604, 0o644, 0o660])
def test_production_refuses_a_keyring_file_others_can_read(
    tmp_path: Path, mode: int, caplog: pytest.LogCaptureFixture
) -> None:
    keyring, encoded = real_keyring()
    path = tmp_path / "keyring"
    path.write_text(keyring + "\n", encoding="utf-8")
    path.chmod(mode)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ValueError, match="readable by group or others") as refused:
        create_app(production(keyring_file=str(path)))

    assert encoded not in str(refused.value) + caplog.text


@pytest.mark.skipif(os.name == "nt", reason="file modes")
def test_production_starts_with_a_private_keyring_file(tmp_path: Path) -> None:
    keyring, _ = real_keyring()
    path = tmp_path / "keyring"
    path.write_text(keyring + "\n", encoding="utf-8")
    path.chmod(0o600)

    assert create_app(production(keyring_file=str(path))) is not None


def test_a_malformed_keyring_names_the_line_and_not_the_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, encoded = real_keyring()
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ValueError, match="Line 1") as refused:
        create_app(production(keyring=f"k1:{encoded}AAAA"))

    assert encoded not in str(refused.value) + caplog.text


def test_a_working_start_logs_no_key_material(caplog: pytest.LogCaptureFixture) -> None:
    keyring, encoded = real_keyring()
    caplog.set_level(logging.DEBUG)

    create_app(production(keyring=keyring))

    assert encoded not in caplog.text
