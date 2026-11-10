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
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

TEST_TAG = "open-door:test"
# The fake keyring the tests use (app.core.encryption); the API accepts it only with APP_ENV=test.
TEST_KEYRING = "test:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


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
    name: str, env: dict[str, str], *, port: int, platform: str = sys.platform, detach: bool
) -> list[str]:
    """`docker run` for the test image, as the deploy runs it: no `--init`, so uvicorn is PID 1
    and the shutdown the proxy check proves is the shipped one (uvicorn starts no child processes,
    so nothing needs reaping). Each setting is `--env KEY` with no value: Docker reads the value
    from its own environment, which the caller sets with `client_env(env)`."""
    args = ["docker", "run", "--name", name]
    args += ["--detach"] if detach else ["--rm"]
    if platform == "darwin":
        args += ["--publish", f"127.0.0.1:{port}:{port}"]
    else:
        args += ["--network", "host"]
    for key in env:
        args += ["--env", key]
    return [*args, TEST_TAG]


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
