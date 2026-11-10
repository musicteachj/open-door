"""How the test image is started, shared by the image check, the browser-test launcher, and the
proxy check. No Docker, no network: it judges the arguments `scripts/image/container.py` builds."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "image" / "container.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("image_container_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


container = load_script()
ENV = {"APP_ENV": "test", "PORT": "8100"}


def pairs(args: list[str], flag: str) -> list[str]:
    return [args[i + 1] for i, arg in enumerate(args) if arg == flag]


def test_on_macos_the_port_is_published_on_loopback_only() -> None:
    args = container.run_args("od", ENV, port=8100, platform="darwin", detach=False)
    assert pairs(args, "--publish") == ["127.0.0.1:8100:8100"]
    assert "--network" not in args


def test_on_linux_the_container_shares_the_hosts_network() -> None:
    args = container.run_args("od", ENV, port=8100, platform="linux", detach=False)
    assert pairs(args, "--network") == ["host"]
    assert "--publish" not in args


def test_it_runs_the_test_image_as_deployed_with_only_the_given_settings() -> None:
    args = container.run_args("od", ENV, port=8100, platform="linux", detach=False)
    assert args[-1] == "open-door:test"
    # No init: uvicorn is PID 1, as the deploy runs it.
    assert "--init" not in args
    assert pairs(args, "--env") == ["APP_ENV", "PORT"]


def test_foreground_removes_itself_and_detached_stays_for_docker_wait() -> None:
    foreground = container.run_args("od", ENV, port=1, platform="linux", detach=False)
    detached = container.run_args("od", ENV, port=1, platform="linux", detach=True)
    assert "--rm" in foreground
    assert "--detach" not in foreground
    assert "--detach" in detached
    assert "--rm" not in detached


def test_the_keyring_comes_from_the_environment_else_the_fake_test_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENCRYPTION_KEYRING", raising=False)
    assert container.keyring_for_test() == container.TEST_KEYRING
    monkeypatch.setenv("ENCRYPTION_KEYRING", "")
    assert container.keyring_for_test() == container.TEST_KEYRING
    monkeypatch.setenv("ENCRYPTION_KEYRING", "ci:abc")
    assert container.keyring_for_test() == "ci:abc"


def test_the_api_env_carries_only_the_apis_own_settings() -> None:
    env = container.api_env(
        origin="http://localhost:8100",
        port=8100,
        platform="linux",
        heartbeat_seconds="1",
        daily_budget_usd="1000",
    )
    assert env["APP_ENV"] == "test"
    assert env["AI_TRANSPORT"] == "scripted"
    assert env["APP_ORIGIN"] == "http://localhost:8100"
    assert env["PORT"] == "8100"
    assert env["AI_HEARTBEAT_SECONDS"] == "1"
    assert env["AI_DAILY_BUDGET_USD"] == "1000"
    assert "FORWARDED_ALLOW_IPS" not in env
    assert set(env) <= {
        "APP_ENV",
        "APP_ORIGIN",
        "DATABASE_URL",
        "AI_TRANSPORT",
        "ENCRYPTION_KEYRING",
        "PORT",
        "HOST",
        "AI_HEARTBEAT_SECONDS",
        "AI_DAILY_BUDGET_USD",
    }


def test_on_linux_the_api_binds_the_loopback_or_the_host_asked_for_never_every_interface() -> None:
    linux = container.api_env(origin="http://localhost:8100", port=8100, platform="linux")
    assert linux["HOST"] == "127.0.0.1"
    bridge = container.api_env(
        origin="http://localhost:8200", port=8200, platform="linux", bind_host="172.17.0.1"
    )
    assert bridge["HOST"] == "172.17.0.1"


def test_on_macos_the_api_keeps_the_entrypoints_bind_for_the_published_port() -> None:
    mac = container.api_env(origin="http://localhost:8100", port=8100, platform="darwin")
    assert "HOST" not in mac


def test_no_setting_value_is_on_the_command_line_and_the_client_environment_holds_them() -> None:
    secret = {"ENCRYPTION_KEYRING": "test:secret-key-material", "PORT": "8100"}
    args = container.run_args("od", secret, port=8100, platform="linux", detach=True)
    assert "secret-key-material" not in " ".join(args)
    assert pairs(args, "--env") == ["ENCRYPTION_KEYRING", "PORT"]
    client = container.client_env(secret)
    assert client["ENCRYPTION_KEYRING"] == "test:secret-key-material"
    assert client["PORT"] == "8100"


def test_the_api_env_passes_the_port_through_to_the_entrypoint() -> None:
    env = container.api_env(origin="http://localhost:8200", port=8200, platform="linux")
    assert env["PORT"] == "8200"
    args = container.run_args("od", env, port=8200, platform="linux", detach=False)
    assert "PORT" in pairs(args, "--env")


def test_the_database_host_is_swapped_without_touching_the_password() -> None:
    url = "postgresql+asyncpg://od_app_login:localhost127@localhost:5433/opendoor"
    assert (
        container.database_url_for_container(url, platform="darwin")
        == "postgresql+asyncpg://od_app_login:localhost127@host.docker.internal:5433/opendoor"
    )


def test_ipv6_loopback_is_translated_and_other_hosts_and_linux_are_left_alone() -> None:
    v6 = "postgresql+asyncpg://u:p@[::1]:5433/db"
    assert (
        container.database_url_for_container(v6, platform="darwin")
        == "postgresql+asyncpg://u:p@host.docker.internal:5433/db"
    )
    assert container.database_url_for_container(v6, platform="linux") == v6
    remote = "postgresql+asyncpg://u:p@db.example.com:5432/db"
    assert container.database_url_for_container(remote, platform="darwin") == remote
    bare = "postgresql://localhost/db"
    assert (
        container.database_url_for_container(bare, platform="darwin")
        == "postgresql://host.docker.internal/db"
    )
