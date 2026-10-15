"""The rule that production runs the real transport, checked when the API starts.

It is not on `Settings`, which alembic, the setup scripts, and the cleanup job build too.
"""

import pytest

from app.ai.transport import require_a_transport_fit_for
from app.core.config import Settings

APP_URL = "postgresql+asyncpg://od_app_login:od_app_dev@localhost/opendoor"


def settings_for(app_env: str, transport: str) -> Settings:
    return Settings(_env_file=None, database_url=APP_URL, app_env=app_env, ai_transport=transport)


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
