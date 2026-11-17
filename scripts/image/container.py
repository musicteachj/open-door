"""Pieces shared by everything that starts the `open-door:test` image: `check.py` (the image
check), `serve.py` (the launcher the browser tests use), and `scripts/proxy-check/check.py`.

Only the API's own settings go into the container, never the keyring file: `ENCRYPTION_KEYRING` is
passed through the environment. The tests run with `APP_ENV=test`, where the API accepts the fixed
fake key (`TEST_KEYRING`), so a sandbox the tests make is throwaway and nothing real is needed.

The settings' values never appear on a command line, where `ps` would show them: `run_args` emits
`--env KEY` only, and the values travel in the `docker` client's environment (`client_env`).

On Linux the container shares the host's network (`--network host`), so it reaches the
development database on the host's loopback, and uvicorn is told to bind (`HOST`) only where it
must be reached: the loopback for the browser tests and the image check, or the docker bridge's
gateway for the proxy check, whose nginx runs in Docker. Never every interface.
"""

import os
import re
import subprocess
import sys
import time
from collections.abc import Sequence
from urllib.parse import urlsplit, urlunsplit

TEST_TAG = "open-door:test"
# The production image: no component gallery. `make prod-local` runs it.
PROD_TAG = "open-door:prod"
# The fake keyring the tests use (app.core.encryption); the API accepts it only with APP_ENV=test.
TEST_KEYRING = "test:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


# The database image (the same tag as compose.yaml's; a test keeps them equal) and the logins of a
# throwaway database, shared by `make prod-local` and `make load`.
POSTGRES_IMAGE = "pgvector/pgvector:0.8.7-pg17"
DB_OWNER = "opendoor"
DB_DATABASE = "opendoor"
APP_LOGIN = "od_app_login"
CLEANUP_LOGIN = "od_cleanup_login"
# The one-off setup, as a deploy runs it: migrate, create the login users, load the handbook. Run
# from the image's working directory (/app/apps/api).
SETUP_SCRIPT = (
    "alembic upgrade head"
    " && python scripts/bootstrap_db_users.py"
    " && python scripts/ingest_handbook.py ingest"
)
# The access log is JSON lines, so the request's quotes arrive escaped: `1.2.3.4:5 - \"GET / ...`.
CLIENT_IN_ACCESS_LOG = re.compile(r'(\d+\.\d+\.\d+\.\d+):\d+ - \\?"(?:GET|HEAD|POST)')


class ContainerError(Exception):
    """Docker said no; the message is for a person."""


def database_url_for_container(url: str, *, platform: str) -> str:
    """The development database's URL as a container reaches it. On macOS, Docker Desktop forwards
    `host.docker.internal` to the host's loopback; on Linux the container shares the host's
    network (`--network host`), so the URL is unchanged. The host is swapped in a rebuilt netloc,
    so a password that happens to contain "localhost" is left alone."""
    if platform != "darwin":
        return url
    parts = urlsplit(url)
    if parts.hostname not in ("127.0.0.1", "localhost", "::1"):
        return url
    userinfo = ""
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo += f":{parts.password}"
        userinfo += "@"
    port = f":{parts.port}" if parts.port is not None else ""
    return urlunsplit(parts._replace(netloc=f"{userinfo}host.docker.internal{port}"))


def keyring_for_test() -> str:
    """The keyring in the environment (CI sets the fake test key), else the fake test key."""
    return os.environ.get("ENCRYPTION_KEYRING") or TEST_KEYRING


def api_env(
    *,
    origin: str,
    port: int,
    platform: str = sys.platform,
    forwarded: str | None = None,
    heartbeat_seconds: str | None = None,
    daily_budget_usd: str | None = None,
    bind_host: str | None = None,
) -> dict[str, str]:
    """The API's settings for a test container: nothing else of the host's environment goes in.

    On Linux the container shares the host's network, so `HOST` is set to `bind_host`, or the
    loopback by default. On macOS the container keeps its own network and publishes the port on
    the host's loopback, so uvicorn binds the container's 0.0.0.0 (the entrypoint's default)."""
    from app.core.config import Settings  # imported here: needs apps/api on the path.

    env = {
        "APP_ENV": "test",
        "APP_ORIGIN": origin,
        "DATABASE_URL": database_url_for_container(
            Settings().database_url.unicode_string(), platform=platform
        ),
        "AI_TRANSPORT": "scripted",
        "ENCRYPTION_KEYRING": keyring_for_test(),
        # The entrypoint listens on PORT: the container publishes (macOS) or shares the host's
        # network (Linux) on this one number, so the port outside is the port inside.
        "PORT": str(port),
        # The browser tests and the proxy check start many sandboxes from one address. APP_ENV=test
        # defaults the Turnstile keys to Cloudflare's test keys, so no key is passed here.
        "SANDBOX_STARTS_PER_HOUR": "1000000",
        "SANDBOX_STARTS_PER_DAY": "1000000",
        "SANDBOX_STARTS_DAILY_TOTAL": "1000000",
    }
    if platform != "darwin":
        env["HOST"] = bind_host or "127.0.0.1"
    if forwarded is not None:
        env["FORWARDED_ALLOW_IPS"] = forwarded
    if heartbeat_seconds is not None:
        env["AI_HEARTBEAT_SECONDS"] = heartbeat_seconds
    if daily_budget_usd is not None:
        env["AI_DAILY_BUDGET_USD"] = daily_budget_usd
    return env


def run_args(
    name: str,
    env: dict[str, str],
    *,
    port: int,
    platform: str = sys.platform,
    detach: bool,
    image: str = TEST_TAG,
    network: str | None = None,
    extra_args: Sequence[str] = (),
) -> list[str]:
    """`docker run` for the test image, as the deploy runs it: no `--init`, so uvicorn is PID 1
    and the shutdown the proxy check proves is the shipped one (uvicorn starts no child processes,
    so nothing needs reaping). Each setting is `--env KEY` with no value: Docker reads the value
    from its own environment, which the caller sets with `client_env(env)`.

    With `network` (a user-defined docker network, as `make prod-local` uses to reach its own
    database) the container joins it and publishes the port on the host's loopback on every
    platform, since it is on a bridge, not the host's network. `extra_args` go before the settings
    (the load test's `--cpus` and `--memory`)."""
    args = ["docker", "run", "--name", name]
    args += ["--detach"] if detach else ["--rm"]
    if network is not None:
        args += ["--network", network, "--publish", f"127.0.0.1:{port}:{port}"]
    elif platform == "darwin":
        args += ["--publish", f"127.0.0.1:{port}:{port}"]
    else:
        args += ["--network", "host"]
    args += list(extra_args)
    return [*args, *env_flags(env), image]


def client_env(values: dict[str, str]) -> dict[str, str]:
    """The environment for the `docker` client: this process's, plus the container's settings."""
    return {**os.environ, **values}


def run(
    *args: str,
    check: bool = True,
    timeout: float = 600,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603  # Fixed argument lists only.
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=None if env is None else client_env(env),
    )
    if check and result.returncode != 0:
        raise ContainerError(f"{' '.join(args[:4])} failed:\n{result.stdout}\n{result.stderr}")
    return result


def remove(name: str) -> None:
    """Remove a container of this name, running or not; fine if there is none."""
    run("docker", "rm", "-f", name, check=False)


def docker_bridge_gateway() -> str | None:
    """The docker bridge network's gateway: the host's address as a container on that network
    (nginx in the proxy check) reaches it on Linux."""
    result = run(
        "docker",
        "network",
        "inspect",
        "bridge",
        "-f",
        "{{(index .IPAM.Config 0).Gateway}}",
        check=False,
    )
    gateway = result.stdout.strip()
    return gateway if result.returncode == 0 and gateway else None


def client_addresses_in(log: str) -> list[str]:
    """The client addresses uvicorn's access log shows."""
    return CLIENT_IN_ACCESS_LOG.findall(log)


def env_flags(env: dict[str, str]) -> list[str]:
    """`--env KEY` for each setting, no value: Docker reads it from the client's environment."""
    args: list[str] = []
    for key in env:
        args += ["--env", key]
    return args


def database_run_args(
    name: str,
    network: str,
    env: dict[str, str],
    *,
    cpus: str | None = None,
    memory: str | None = None,
) -> list[str]:
    """A throwaway Postgres: detached, removed when stopped, no volume, not published to the host,
    optionally limited. The pgvector image's own entrypoint, so the settings are its POSTGRES_*."""
    limits: list[str] = []
    if cpus is not None:
        limits += ["--cpus", cpus]
    if memory is not None:
        limits += ["--memory", memory]
    return [
        "docker",
        "run",
        "--detach",
        "--rm",
        "--name",
        name,
        "--network",
        network,
        *limits,
        *env_flags(env),
        POSTGRES_IMAGE,
    ]


def setup_run_args(name: str, network: str, env: dict[str, str]) -> list[str]:
    """The one-off setup container (migrations, the login users, the handbook) from the
    production image, on the database's network."""
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        network,
        *env_flags(env),
        "--entrypoint",
        "sh",
        PROD_TAG,
        "-c",
        SETUP_SCRIPT,
    ]


def database_url(user: str, password: str, host: str) -> str:
    """A throwaway database's URL as the other containers on its network reach it."""
    return f"postgresql+asyncpg://{user}:{password}@{host}:5432/{DB_DATABASE}"


def postgres_ready(name: str, *, timeout_seconds: float) -> bool:
    """Wait until the database container accepts connections (over TCP: on a fresh database,
    Postgres first runs a socket-only setup server)."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        probe = run(
            "docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", DB_OWNER, "-d",
            DB_DATABASE,
            check=False,
        )  # fmt: skip
        if probe.returncode == 0:
            return True
        time.sleep(1)
    return False
