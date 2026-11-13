"""The rule that production runs the real transport, checked when the API starts.

It is not on `Settings`, which alembic, the setup scripts, and the cleanup job build too.
"""

from pathlib import Path

import pytest
from pydantic import SecretStr

from app.ai.transport import require_a_transport_fit_for
from app.core.config import Settings

APP_URL = "postgresql+asyncpg://od_app_login:od_app_dev@localhost/opendoor"


def settings_for(app_env: str, transport: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=APP_URL,
        app_env=app_env,
        app_origin="https://opendoor.example.com",
        ai_transport=transport,
    )


@pytest.mark.parametrize("transport", ["scripted", "replay"])
def test_production_refuses_a_fake_transport(transport: str) -> None:
    with pytest.raises(ValueError, match="AI_TRANSPORT must be anthropic"):
        require_a_transport_fit_for(settings_for("production", transport))


def test_production_accepts_the_anthropic_transport() -> None:
    require_a_transport_fit_for(settings_for("production", "anthropic"))


@pytest.mark.parametrize("app_env", ["development", "test"])
@pytest.mark.parametrize("transport", ["scripted", "replay", "anthropic"])
def test_other_environments_accept_any_transport(app_env: str, transport: str) -> None:
    require_a_transport_fit_for(settings_for(app_env, transport))


def test_the_anthropic_transport_gets_the_anthropic_summarizer_on_its_client() -> None:
    from pydantic import SecretStr

    from app.ai.anthropic_transport import AnthropicSummarizer, AnthropicTransport, from_settings
    from app.ai.scripted import ScriptedSummarizer, ScriptedTransport
    from app.main import _build_summarizer

    real = Settings(
        _env_file=None,
        database_url=APP_URL,
        ai_transport="anthropic",
        anthropic_api_key=SecretStr("test-key"),
    )
    transport = from_settings(real)
    assert isinstance(transport, AnthropicTransport)

    summarizer = _build_summarizer(real, transport)

    assert isinstance(summarizer, AnthropicSummarizer)
    assert summarizer.client is transport.client
    # Every other transport gets the scripted one.
    assert isinstance(
        _build_summarizer(settings_for("development", "scripted"), ScriptedTransport()),
        ScriptedSummarizer,
    )


def test_the_anthropic_setting_with_another_transport_is_refused_at_startup() -> None:
    from app.ai.scripted import ScriptedTransport
    from app.main import _build_summarizer

    real = Settings(
        _env_file=None,
        database_url=APP_URL,
        ai_transport="anthropic",
        anthropic_api_key=SecretStr("test-key"),
    )

    with pytest.raises(ValueError, match="AnthropicTransport"):
        _build_summarizer(real, ScriptedTransport())


def profile_settings(app_env: str, transport: str, profile: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=APP_URL,
        app_env=app_env,
        app_origin="https://opendoor.example.com",
        ai_transport=transport,
        scripted_delay_profile=profile,
    )


def test_production_refuses_a_delay_profile_on_its_own() -> None:
    # Refused by itself: even with the real transport, where it would do nothing.
    with pytest.raises(ValueError, match="SCRIPTED_DELAY_PROFILE must be none"):
        require_a_transport_fit_for(profile_settings("production", "anthropic", "realistic"))


def test_production_accepts_no_delay_profile() -> None:
    require_a_transport_fit_for(profile_settings("production", "anthropic", "none"))


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_other_environments_accept_the_realistic_profile(app_env: str) -> None:
    require_a_transport_fit_for(profile_settings(app_env, "scripted", "realistic"))


def test_the_profile_defaults_to_none_and_the_example_env_lists_it() -> None:
    assert Settings(_env_file=None, database_url=APP_URL).scripted_delay_profile == "none"
    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "SCRIPTED_DELAY_PROFILE=none" in example
