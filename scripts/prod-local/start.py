"""Run the production image with production settings on its own empty database: `make prod-local`.

It starts a throwaway Postgres (never the development database) on a private docker network, runs
the deploy's one-off setup (migrations, the login users, the handbook) as a separate container,
then runs the API container with `APP_ENV=production` and the real model transport on
`http://localhost:8300`. Stopping it (Ctrl-C) stops the API and the database and removes the
network; the database is not kept.

Any question asked through it is a paid call: production accepts only the `anthropic` transport.
`--check` starts everything, looks at the pages, and stops, asking the model nothing.

    uv run python ../../scripts/prod-local/start.py            # run in the foreground
    uv run python ../../scripts/prod-local/start.py --check    # prove it starts and serves pages

Run it from apps/api (the API's settings supply the keys and the keyring). Every secret travels in
the docker client's environment (`--env KEY`), never on a command line.
"""

import argparse
import secrets
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

import httpx
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "image"))
import container

# The same tag as compose.yaml's database (a test keeps them equal).
POSTGRES_IMAGE = "pgvector/pgvector:0.8.7-pg17"
NETWORK = "open-door-prod-local"
DB_NAME = "open-door-prod-local-db"
API_NAME = "open-door-prod-local-api"
DB_OWNER = "opendoor"
DB_DATABASE = "opendoor"
APP_LOGIN = "od_app_login"
CLEANUP_LOGIN = "od_cleanup_login"
DEFAULT_PORT = 8300
# Production refuses the development default origin, which is this port.
DEV_PORT = 5173
# uvicorn's graceful timeout plus the time it takes to save open streams, with room (as serve.py).
STOP_GRACE_SECONDS = 30
# What stops a run: Ctrl-C, `kill`, or a closed terminal.
STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
READY_TIMEOUT_SECONDS = 90
DB_READY_TIMEOUT_SECONDS = 60
LOG_LINES = 40
# The one-off setup, as a deploy runs it: migrate, create the login users, load the handbook. Run
# from the image's working directory (/app/apps/api).
SETUP_SCRIPT = (
    "alembic upgrade head"
    " && python scripts/bootstrap_db_users.py"
    " && python scripts/ingest_handbook.py ingest"
)


class LaunchError(Exception):
    """Something stops the run; the message is for a person and holds no secret."""


@dataclass(frozen=True)
class Passwords:
    """The three database passwords, and the key that hides visitors' addresses, made fresh for
    every run. (Production requires SANDBOX_IP_HASH_KEY and refuses the development value.)"""

    owner: str
    app: str
    cleanup: str
    sandbox_ip_hash_key: str

    @classmethod
    def new(cls) -> "Passwords":
        return cls(
            owner=secrets.token_urlsafe(24),
            app=secrets.token_urlsafe(24),
            cleanup=secrets.token_urlsafe(24),
            sandbox_ip_hash_key=secrets.token_urlsafe(48),
        )


@dataclass(frozen=True)
class Secrets:
    """What the API's own settings supply."""

    anthropic_api_key: str
    voyage_api_key: str | None
    keyring: str


# --- Settings: plain functions, tested offline ----------------------------------------------


def check_port(port: int) -> int:
    if port == DEV_PORT:
        raise LaunchError(
            f"Port {DEV_PORT} is the development origin, which production refuses. Use another."
        )
    if not 1024 <= port <= 65535:
        raise LaunchError(f"Port {port} is not a usable port (1024 to 65535).")
    return port


def origin_for(port: int) -> str:
    return f"http://localhost:{port}"


def require_anthropic_key(key: str | None) -> str:
    if not key:
        raise LaunchError(
            "ANTHROPIC_API_KEY is not set (add it to apps/api/.env). Production accepts only the"
            " anthropic transport, so this run needs the key, and every question asked through it"
            " is a paid call. `make prod-local-check` asks nothing but still needs the key to"
            " start."
        )
    return key


def _database_url(user: str, password: str) -> str:
    return f"postgresql+asyncpg://{user}:{password}@{DB_NAME}:5432/{DB_DATABASE}"


def db_env(passwords: Passwords) -> dict[str, str]:
    return {
        "POSTGRES_USER": DB_OWNER,
        "POSTGRES_PASSWORD": passwords.owner,
        "POSTGRES_DB": DB_DATABASE,
    }


def entry_env(passwords: Passwords) -> dict[str, str]:
    """What production needs for starting sandboxes: this run's address-hash key, and Cloudflare's
    always-pass Turnstile test keys. Production refuses test keys unless the origin is loopback,
    which this run's is, and the API answers them locally, never calling Cloudflare."""
    from app.core.config import (  # imported here: needs apps/api on the path.
        TURNSTILE_PASS_SECRET,
        TURNSTILE_PASS_SITE_KEY,
    )

    return {
        "SANDBOX_IP_HASH_KEY": passwords.sandbox_ip_hash_key,
        "TURNSTILE_SITE_KEY": TURNSTILE_PASS_SITE_KEY,
        "TURNSTILE_SECRET_KEY": TURNSTILE_PASS_SECRET,
    }


def setup_env(passwords: Passwords, origin: str) -> dict[str, str]:
    """What the one-off setup needs: the three URLs (alembic and the scripts read the owner's and
    the logins') and the production settings that validate the origin. No keyring, no API keys, and
    none of the sandbox-entry settings (`entry_env`): only the serving API checks those."""
    return {
        "APP_ENV": "production",
        "APP_ORIGIN": origin,
        "DATABASE_URL": _database_url(APP_LOGIN, passwords.app),
        "MIGRATION_DATABASE_URL": _database_url(DB_OWNER, passwords.owner),
        "CLEANUP_DATABASE_URL": _database_url(CLEANUP_LOGIN, passwords.cleanup),
    }


def api_env(
    *,
    port: int,
    passwords: Passwords,
    keyring: str,
    anthropic_api_key: str,
    voyage_api_key: str | None,
) -> dict[str, str]:
    """The API's settings: production, the real transport, a loopback origin, the API's login only
    (never the owner's or the cleanup login's URL). The test keyring is refused."""
    from app.core.encryption import LocalKeyProvider  # imported here: needs apps/api on the path.

    if keyring == container.TEST_KEYRING or LocalKeyProvider.from_keyring(keyring).uses_test_key:
        raise LaunchError("The keyring holds the test key, which production refuses.")
    env = {
        "APP_ENV": "production",
        "AI_TRANSPORT": "anthropic",
        "APP_ORIGIN": origin_for(port),
        "PORT": str(port),
        "DATABASE_URL": _database_url(APP_LOGIN, passwords.app),
        "ENCRYPTION_KEYRING": keyring,
        "ANTHROPIC_API_KEY": anthropic_api_key,
        **entry_env(passwords),
    }
    if voyage_api_key:
        env["VOYAGE_API_KEY"] = voyage_api_key
    return env


def read_secrets() -> Secrets:
    """The keys and the keyring from the API's settings (apps/api/.env, the environment, and the
    keyring file). Nothing here is printed."""
    from app.core.config import Settings  # imported here: needs apps/api on the path.
    from app.core.encryption import load_key_provider, resolve_keyring_path

    try:
        settings = Settings()
    except ValidationError as error:
        # The fields and reasons only: an input value could be a password in a database URL.
        reasons = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors(include_input=False, include_url=False)
        )
        raise LaunchError(f"The API's settings are not valid: {reasons}") from None
    anthropic = settings.anthropic_api_key
    key = require_anthropic_key(None if anthropic is None else anthropic.get_secret_value())
    ring, ring_file = settings.encryption_keyring, settings.encryption_keyring_file
    try:
        keys = load_key_provider(
            keyring=None if ring is None else ring.get_secret_value(),
            keyring_file=None if ring_file is None else ring_file.get_secret_value(),
        )
    except ValueError as error:
        # The message names the problem, never the key.
        raise LaunchError(f"{error} (`make keyring` writes the file.)") from None
    if keys.uses_test_key:
        raise LaunchError("The keyring holds the test key, which production refuses.")
    if ring is not None:
        keyring = ring.get_secret_value()
    else:
        assert ring_file is not None  # noqa: S101  # load_key_provider needed one of the two.
        keyring = resolve_keyring_path(ring_file.get_secret_value()).read_text(encoding="utf-8")
    voyage = settings.voyage_api_key
    return Secrets(key, None if voyage is None else voyage.get_secret_value(), keyring)


# --- docker arguments --------------------------------------------------------------------------


def _env_flags(env: dict[str, str]) -> list[str]:
    args: list[str] = []
    for key in env:
        args += ["--env", key]
    return args


def db_run_args(env: dict[str, str]) -> list[str]:
    """A throwaway Postgres: detached, removed when stopped, no volume, not published to the host.
    The pgvector image's own entrypoint, so the settings are the image's POSTGRES_* ones."""
    return [
        "docker",
        "run",
        "--detach",
        "--rm",
        "--name",
        DB_NAME,
        "--network",
        NETWORK,
        *_env_flags(env),
        POSTGRES_IMAGE,
    ]


def setup_run_args(env: dict[str, str]) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        f"{API_NAME}-setup",
        "--network",
        NETWORK,
        *_env_flags(env),
        "--entrypoint",
        "sh",
        container.PROD_TAG,
        "-c",
        SETUP_SCRIPT,
    ]


def api_run_args(env: dict[str, str], *, port: int, detach: bool) -> list[str]:
    return container.run_args(
        API_NAME,
        env,
        port=port,
        detach=detach,
        image=container.PROD_TAG,
        network=NETWORK,
    )


# --- docker steps ------------------------------------------------------------------------------


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return container.run("docker", *args, check=check)


def require_the_image() -> None:
    if docker("image", "inspect", container.PROD_TAG, check=False).returncode != 0:
        raise LaunchError(
            f"The {container.PROD_TAG} image is not built. Run `make image` (or `make prod-local`,"
            " which builds it)."
        )


def ensure_network() -> bool:
    """Create the private network if it is missing. True when this run made it (and removes it)."""
    if docker("network", "inspect", NETWORK, check=False).returncode == 0:
        return False
    docker("network", "create", NETWORK)
    return True


def wait_for_postgres() -> None:
    deadline = time.monotonic() + DB_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        # Over TCP: on a fresh database, Postgres first runs a socket-only setup server.
        probe = docker(
            "exec", DB_NAME, "pg_isready", "-h", "127.0.0.1", "-U", DB_OWNER, "-d", DB_DATABASE,
            check=False,
        )  # fmt: skip
        if probe.returncode == 0:
            return
        time.sleep(1)
    raise LaunchError(
        f"The database did not become ready in {DB_READY_TIMEOUT_SECONDS} seconds.\n"
        + last_logs(DB_NAME)
    )


def last_logs(name: str) -> str:
    result = docker("logs", "--tail", str(LOG_LINES), name, check=False)
    return (result.stdout + result.stderr).strip()


def run_setup(env: dict[str, str]) -> None:
    result = subprocess.run(  # noqa: S603
        setup_run_args(env),
        env=container.client_env(env),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-LOG_LINES:])
        raise LaunchError(f"The one-off setup (migrations, users, handbook) failed:\n{tail}")


def start_database(passwords: Passwords) -> None:
    env = db_env(passwords)
    container.run(*db_run_args(env), env=env)
    wait_for_postgres()


def cleanup(*, made_network: bool) -> None:
    """Stop everything this run started. Safe to call twice."""
    docker("stop", "--time", str(STOP_GRACE_SECONDS), API_NAME, check=False)
    container.remove(API_NAME)
    container.remove(f"{API_NAME}-setup")
    docker("stop", "--time", "5", DB_NAME, check=False)
    container.remove(DB_NAME)
    if made_network:
        docker("network", "rm", NETWORK, check=False)


def wait_until_ready(base: str) -> None:
    """The database ping route answers 200 once the API is up and can reach its database."""
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        state = docker("inspect", "-f", "{{.State.Running}}", API_NAME, check=False)
        if state.stdout.strip() == "false":
            raise LaunchError("The API container exited early.\n" + last_logs(API_NAME))
        try:
            if httpx.get(f"{base}/api/v1/health", timeout=3).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise LaunchError(
        f"The API did not become ready in {READY_TIMEOUT_SECONDS} seconds.\n" + last_logs(API_NAME)
    )


def problems_in_pages(base: str) -> list[str]:
    """Fetch the home page and one route that needs no session. No model call, no sandbox."""
    problems: list[str] = []
    with httpx.Client(base_url=base, timeout=10) as client:
        home = client.get("/", headers={"accept": "text/html"})
        csp = home.headers.get("content-security-policy", "")
        if home.status_code != 200:
            problems.append(f"/ answered {home.status_code}")
        if "'nonce-" not in csp:
            problems.append("/ has no Content-Security-Policy with a nonce")
        live = client.get("/api/v1/health/live")
        if live.status_code != 200:
            problems.append(f"/api/v1/health/live answered {live.status_code}")
    return problems


# --- the two ways to run -----------------------------------------------------------------------


def bring_up(secrets_: Secrets, port: int) -> tuple[bool, dict[str, str]]:
    """Start the database and run the setup; returns whether this run made the network and the
    API's settings. Cleans up after itself if a step fails."""
    passwords = Passwords.new()
    require_the_image()
    # A stale container of the same name is removed first.
    container.remove(API_NAME)
    container.remove(f"{API_NAME}-setup")
    container.remove(DB_NAME)
    made_network = ensure_network()
    try:
        start_database(passwords)
        run_setup(setup_env(passwords, origin_for(port)))
        env = api_env(
            port=port,
            passwords=passwords,
            keyring=secrets_.keyring,
            anthropic_api_key=secrets_.anthropic_api_key,
            voyage_api_key=secrets_.voyage_api_key,
        )
    except BaseException:
        cleanup(made_network=made_network)
        raise
    return made_network, env


def check(secrets_: Secrets, port: int) -> int:
    made_network, env = bring_up(secrets_, port)
    base = f"http://127.0.0.1:{port}"
    try:
        container.run(*api_run_args(env, port=port, detach=True), env=env)
        wait_until_ready(base)
        problems = problems_in_pages(base)
        if problems:
            raise LaunchError("\n".join(problems) + "\n" + last_logs(API_NAME))
    finally:
        cleanup(made_network=made_network)
    print(f"prod-local check passed: {container.PROD_TAG} served {base} with production settings")
    return 0


def serve(secrets_: Secrets, port: int) -> int:
    made_network, env = bring_up(secrets_, port)
    stopping = threading.Event()
    started: list[subprocess.Popen[bytes]] = []

    def stop_api() -> None:
        # A signal can arrive after `docker run` started but before the container exists, when
        # `docker stop` finds nothing, so it is retried until `docker run` has exited (or the
        # grace period and a margin pass), as `scripts/image/serve.py` does.
        if not started:
            return
        process = started[0]
        deadline = time.monotonic() + STOP_GRACE_SECONDS + 10
        while process.poll() is None and time.monotonic() < deadline:
            docker("stop", "--time", str(STOP_GRACE_SECONDS), API_NAME, check=False)
            if process.poll() is None:
                time.sleep(0.5)

    def stop_in_background() -> None:
        # Off the signal handler, so the main thread keeps waiting on `docker run`.
        threading.Thread(target=stop_api, daemon=True).start()

    def on_signal(_signum: int, _frame: FrameType | None) -> None:
        # A signal before `docker run` starts only sets the flag: the start below sees it.
        if not stopping.is_set():
            stopping.set()
            stop_in_background()

    try:
        for signum in STOP_SIGNALS:
            signal.signal(signum, on_signal)
        print(
            f"Open Door ({container.PROD_TAG}, production settings) at {origin_for(port)}\n"
            "Every question asked here is a paid call to the model. Ctrl-C stops it and the"
            " database."
        )
        process = subprocess.Popen(  # noqa: S603
            api_run_args(env, port=port, detach=False), env=container.client_env(env)
        )
        started.append(process)
        if stopping.is_set():
            stop_in_background()
        code = process.wait()
    finally:
        cleanup(made_network=made_network)
    return 0 if stopping.is_set() or code in (0, 143) else code


def _interrupt(_signum: int, _frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="start everything, fetch the pages, stop; asks the model nothing",
    )
    options = parser.parse_args(argv)
    # Until `serve` takes over, a stop signal unwinds like Ctrl-C, so the cleanup in `bring_up`
    # and `check` runs and no database container or network is left behind.
    for signum in STOP_SIGNALS:
        signal.signal(signum, _interrupt)
    try:
        port = check_port(options.port)
        secrets_ = read_secrets()
        return check(secrets_, port) if options.check else serve(secrets_, port)
    except (LaunchError, container.ContainerError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        # A stop between `bring_up` returning and the cleanup taking over: remove what may run.
        # (Safe to call twice; a network this run made is left for the next run to reuse.)
        cleanup(made_network=False)
        print(
            "Stopped before the API started; everything this run started is removed.",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    sys.exit(main())
