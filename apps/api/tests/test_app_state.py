"""The lifespan builds the transport and the query embedder, and the app refuses a bad setup."""

import asyncio
import base64
from pathlib import Path
from typing import Any

import pytest
from anthropic import AsyncAnthropic
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.ai.anthropic_transport import AnthropicTransport
from app.ai.embeddings import QueryEmbeddingLru
from app.ai.scripted import ScriptedTransport
from app.api.deps import get_app_settings, get_embedder, get_keys, get_streams, get_transport
from app.core.config import Settings
from app.core.encryption import LocalKeyProvider
from app.main import create_app
from tests.conftest import TEST_KEYRING, UNREACHABLE_DATABASE_URL
from tests.test_deps import request_for

KEY = SecretStr("sk-ant-test-not-real")
VOYAGE = SecretStr("pa-test-not-real")


def settings_with(**overrides: Any) -> Settings:
    fields: dict[str, Any] = {
        "_env_file": None,
        "app_env": "test",
        "database_url": UNREACHABLE_DATABASE_URL,
        "migration_database_url": None,
        "cleanup_database_url": None,
        "anthropic_api_key": None,
        "voyage_api_key": None,
        "ai_transport": "scripted",
        "encryption_keyring_file": None,
        "encryption_keyring": TEST_KEYRING,
    }
    fields.update(overrides)
    return Settings(**fields)


def test_scripted_builds_the_scripted_transport_and_no_embedder() -> None:
    app = create_app(settings_with())
    with TestClient(app):
        assert isinstance(app.state.transport, ScriptedTransport)
        assert app.state.embedder is None


def test_scripted_never_gets_an_embedder_even_with_a_voyage_key() -> None:
    app = create_app(settings_with(voyage_api_key=VOYAGE))
    with TestClient(app):
        assert app.state.embedder is None


def test_anthropic_builds_the_anthropic_transport_and_a_cached_voyage_embedder() -> None:
    app = create_app(
        settings_with(ai_transport="anthropic", anthropic_api_key=KEY, voyage_api_key=VOYAGE)
    )
    with TestClient(app):
        assert isinstance(app.state.transport, AnthropicTransport)
        assert isinstance(app.state.embedder, QueryEmbeddingLru)


def test_anthropic_without_a_voyage_key_searches_by_full_text_only() -> None:
    app = create_app(settings_with(ai_transport="anthropic", anthropic_api_key=KEY))
    with TestClient(app):
        assert isinstance(app.state.transport, AnthropicTransport)
        assert app.state.embedder is None


def test_production_refuses_the_scripted_transport_at_boot() -> None:
    with pytest.raises(ValueError, match="AI_TRANSPORT must be anthropic"):
        create_app(settings_with(app_env="production"))


def test_replay_is_refused_for_the_app_at_boot() -> None:
    with pytest.raises(ValueError, match="replay"):
        create_app(settings_with(ai_transport="replay"))


def test_anthropic_without_a_key_is_refused_at_boot_not_at_the_first_request() -> None:
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        create_app(settings_with(ai_transport="anthropic"))


def test_the_dependencies_return_what_the_lifespan_built() -> None:
    app = create_app(
        settings_with(ai_transport="anthropic", anthropic_api_key=KEY, voyage_api_key=VOYAGE)
    )
    with TestClient(app):
        assert get_transport(request_for(app)) is app.state.transport
        assert get_embedder(request_for(app)) is app.state.embedder
        assert get_embedder(request_for(app)) is not None


def test_a_missing_embedder_is_none_not_an_error() -> None:
    app = create_app(settings_with())
    with TestClient(app):
        assert get_embedder(request_for(app)) is None


def test_the_dependencies_give_a_clear_error_without_the_lifespan(app: FastAPI) -> None:
    with pytest.raises(RuntimeError, match="lifespan"):
        get_transport(request_for(app))
    with pytest.raises(RuntimeError, match="lifespan"):
        get_embedder(request_for(app))


def test_the_anthropic_client_is_closed_on_exit_and_the_engine_is_disposed() -> None:
    app = create_app(settings_with(ai_transport="anthropic", anthropic_api_key=KEY))
    with TestClient(app):
        client = app.state.transport.client
        assert client.is_closed() is False
    assert client.is_closed() is True


def test_a_failure_closing_the_client_still_disposes_the_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposed: list[bool] = []

    class FakeEngine:
        async def dispose(self) -> None:
            disposed.append(True)

    async def close(self: AsyncAnthropic) -> None:
        msg = "close failed"
        raise RuntimeError(msg)

    monkeypatch.setattr("app.main.create_engine", lambda url: FakeEngine())
    monkeypatch.setattr(AsyncAnthropic, "close", close)
    app = create_app(settings_with(ai_transport="anthropic", anthropic_api_key=KEY))

    with pytest.raises(RuntimeError, match="close failed"), TestClient(app):
        pass

    assert disposed == [True]


def test_a_second_lifespan_run_gets_a_working_client_not_a_closed_one() -> None:
    app = create_app(settings_with(ai_transport="anthropic", anthropic_api_key=KEY))
    with TestClient(app):
        first = app.state.transport.client
        assert first.is_closed() is False
    assert first.is_closed() is True

    with TestClient(app):
        second = app.state.transport.client
        assert second is not first
        assert second.is_closed() is False


def test_an_app_whose_lifespan_never_runs_builds_no_client() -> None:
    app = create_app(settings_with(ai_transport="anthropic", anthropic_api_key=KEY))
    assert not hasattr(app.state, "transport")


class RecordingEngine:
    """Stands in for the engine and records what was open when it was closed."""

    def __init__(self, app_ref: list[FastAPI]) -> None:
        self.app_ref = app_ref
        self.open_when_disposed: list[int] = []

    async def dispose(self) -> None:
        self.open_when_disposed.append(self.app_ref[0].state.streams.open_count)


async def test_the_shutdown_waits_for_open_turn_streams_before_it_closes_the_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holder: list[FastAPI] = []
    engine = RecordingEngine(holder)
    monkeypatch.setattr("app.main.create_engine", lambda url: engine)
    app = create_app(settings_with())
    holder.append(app)

    async with app.router.lifespan_context(app):
        app.state.streams.opened()
        asyncio.get_running_loop().call_later(0.3, app.state.streams.closed)

    assert engine.open_when_disposed == [0]


async def test_the_shutdown_does_not_wait_forever_for_a_stuck_stream(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    holder: list[FastAPI] = []
    engine = RecordingEngine(holder)
    monkeypatch.setattr("app.main.create_engine", lambda url: engine)
    monkeypatch.setattr("app.main.STREAM_DRAIN_SECONDS", 0.2)
    app = create_app(settings_with())
    holder.append(app)

    async with app.router.lifespan_context(app):
        app.state.streams.opened()  # Never closed.

    assert engine.open_when_disposed == [1]
    assert "turn stream(s) did not close before shutdown" in caplog.text


def test_the_app_keeps_the_settings_it_was_built_with() -> None:
    settings = settings_with(ai_heartbeat_seconds=7)
    app = create_app(settings)

    assert get_app_settings(request_for(app)) is settings


def test_the_settings_dependency_gives_a_clear_error_for_an_app_without_them() -> None:
    with pytest.raises(RuntimeError, match="settings"):
        get_app_settings(request_for(FastAPI()))


def test_the_stream_tracker_dependency_returns_the_one_the_lifespan_built() -> None:
    app = create_app(settings_with())
    with TestClient(app):
        assert get_streams(request_for(app)) is app.state.streams


def test_the_stream_tracker_dependency_gives_a_clear_error_without_the_lifespan(
    app: FastAPI,
) -> None:
    with pytest.raises(RuntimeError, match="lifespan"):
        get_streams(request_for(app))


REAL_KEYRING = SecretStr("k1:" + base64.b64encode(bytes(range(32))).decode())


def write_keyring(path: Path, text: str, mode: int) -> Path:
    path.write_text(text)
    path.chmod(mode)
    return path


def test_no_keyring_stops_the_app_at_boot(tmp_path: Path) -> None:
    missing = SecretStr(str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="keyring"):
        create_app(settings_with(encryption_keyring=None, encryption_keyring_file=missing))
    with pytest.raises(ValueError, match="keyring"):
        create_app(settings_with(encryption_keyring=None, encryption_keyring_file=None))


def test_a_bad_keyring_stops_the_app_and_the_error_holds_no_key() -> None:
    with pytest.raises(ValueError, match="keyring") as excinfo:
        create_app(settings_with(encryption_keyring=SecretStr("k1:c2hvcnQ=")))
    assert "c2hvcnQ=" not in str(excinfo.value)


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o644, 0o660, 0o666])
def test_a_keyring_file_others_can_read_is_refused(tmp_path: Path, mode: int) -> None:
    path = write_keyring(tmp_path / "keyring", REAL_KEYRING.get_secret_value(), mode)
    with pytest.raises(ValueError, match="readable by"):
        create_app(
            settings_with(encryption_keyring=None, encryption_keyring_file=SecretStr(str(path)))
        )


@pytest.mark.parametrize("mode", [0o600, 0o400])
def test_a_keyring_file_only_its_owner_can_read_is_accepted(tmp_path: Path, mode: int) -> None:
    path = write_keyring(tmp_path / "keyring", REAL_KEYRING.get_secret_value(), mode)
    app = create_app(
        settings_with(
            app_env="development",
            encryption_keyring=None,
            encryption_keyring_file=SecretStr(str(path)),
        )
    )
    assert isinstance(app.state.keys, LocalKeyProvider)
    assert app.state.keys.key_ids == ("k1",)


def test_the_test_key_is_refused_outside_the_test_environment() -> None:
    for env in ("development", "production"):
        with pytest.raises(ValueError, match="test key"):
            create_app(settings_with(app_env=env, ai_transport="anthropic", anthropic_api_key=KEY))


def test_the_test_key_in_a_file_is_refused_outside_the_test_environment(tmp_path: Path) -> None:
    path = write_keyring(tmp_path / "keyring", TEST_KEYRING.get_secret_value(), 0o600)
    with pytest.raises(ValueError, match="test key"):
        create_app(
            settings_with(
                app_env="development",
                encryption_keyring=None,
                encryption_keyring_file=SecretStr(str(path)),
            )
        )


def test_a_real_key_is_accepted_in_every_environment() -> None:
    app = create_app(settings_with(app_env="development", encryption_keyring=REAL_KEYRING))
    assert app.state.keys.key_ids == ("k1",)


def test_the_app_holds_one_key_provider_and_the_dependency_returns_it() -> None:
    app = create_app(settings_with())
    assert isinstance(app.state.keys, LocalKeyProvider)
    with TestClient(app):
        assert get_keys(request_for(app)) is app.state.keys
        assert get_keys(request_for(app)) is get_keys(request_for(app))


def test_the_key_dependency_gives_a_clear_error_for_an_app_without_keys() -> None:
    with pytest.raises(RuntimeError, match="keyring"):
        get_keys(request_for(FastAPI()))


def test_the_key_dependency_refuses_a_keys_attribute_that_is_not_a_provider() -> None:
    app = FastAPI()
    app.state.keys = object()
    with pytest.raises(RuntimeError, match="not a key provider"):
        get_keys(request_for(app))


def test_the_key_dependency_accepts_any_object_with_wrap_and_unwrap() -> None:
    class FakeKeys:
        def wrap(self, data_key: bytes, *, aad: bytes) -> tuple[str, bytes]:
            return "fake", data_key

        def unwrap(self, key_id: str, wrapped: bytes, *, aad: bytes) -> bytes:
            return wrapped

    app = FastAPI()
    fake = FakeKeys()
    app.state.keys = fake
    assert get_keys(request_for(app)) is fake
