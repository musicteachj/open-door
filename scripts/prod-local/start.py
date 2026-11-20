"""Run the production image with production settings on its own empty database: `make prod-local`.

It starts a throwaway Postgres (never the development database) on a private docker network, runs
the deploy's one-off setup (migrations, the login users, the handbook) as a separate container,
then runs the API container with `APP_ENV=production` and the real model transport on
`http://localhost:8300`. Stopping it (Ctrl-C) stops the API and the database and removes the
network; the database is not kept.

Any question asked through it is a paid call: production accepts only the `anthropic` transport.
`--check` starts everything, looks at the pages, and stops, asking the model nothing.
`--check --ai-off` starts it with live AI turned off (a $0 monthly budget) and checks what a visitor
sees then; it needs no model key and is handed a made-up one.

    uv run python ../../scripts/prod-local/start.py            # run in the foreground
    uv run python ../../scripts/prod-local/start.py --check    # prove it starts and serves pages
    uv run python ../../scripts/prod-local/start.py --check --ai-off   # and that live AI off works

Run it from apps/api (the API's settings supply the keys and the keyring). Every secret travels in
the docker client's environment (`--env KEY`), never on a command line.
"""

import argparse
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

import httpx
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "image"))
import container

# The same tag as compose.yaml's database (a test keeps them equal).
POSTGRES_IMAGE = container.POSTGRES_IMAGE
NETWORK = "open-door-prod-local"
DB_NAME = "open-door-prod-local-db"
API_NAME = "open-door-prod-local-api"
DB_OWNER = container.DB_OWNER
DB_DATABASE = container.DB_DATABASE
APP_LOGIN = container.APP_LOGIN
CLEANUP_LOGIN = container.CLEANUP_LOGIN
API_MEMORY = "512m"  # Production's hard limit for the API task.
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


# What the live-AI-off check hands the image as its model key. It is not a key: if anything calls
# the model by mistake, the call is refused unbilled. The real key is never passed to that check.
AI_OFF_API_KEY = "not-a-real-key-ai-off-check"  # Deliberately not a secret.
AI_OFF_BUDGETS_USD = {"monthly": "0"}


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
    return container.database_url(user, password, DB_NAME)


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


def cleanup_env(passwords: Passwords) -> dict[str, str]:
    """The cleanup job reads one setting: its own login's URL."""
    return {"CLEANUP_DATABASE_URL": _database_url(CLEANUP_LOGIN, passwords.cleanup)}


# The AI budgets a run may lower (the recording's per-take cap, the live check's cap), by name.
BUDGET_SETTINGS = {
    "daily": "AI_DAILY_BUDGET_USD",
    "sandbox": "AI_SANDBOX_BUDGET_USD",
    "monthly": "AI_MONTHLY_BUDGET_USD",
}
# What production runs on (Phase 9a): a $20 month and $0.50 a sandbox, unless a run lowers them.
PORTFOLIO_BUDGETS_USD = {"monthly": "20", "sandbox": "0.50"}
DOLLARS = re.compile(r"\d{1,4}(\.\d{1,2})?")


def budget_env(budgets_usd: Mapping[str, str] | None) -> dict[str, str]:
    """The AI budget settings for `budgets_usd` ({"daily": "0.66"}): positive dollars only, except
    the monthly budget, where 0 turns live AI off."""
    env: dict[str, str] = {}
    for name, amount in (budgets_usd or {}).items():
        setting = BUDGET_SETTINGS.get(name)
        if setting is None:
            raise LaunchError(
                f"Only the daily, sandbox, and monthly budgets can be set, not {name!r}."
            )
        floor = 0 if name == "monthly" else 1e-9
        if not DOLLARS.fullmatch(amount) or float(amount) < floor:
            kind = "non-negative" if name == "monthly" else "positive"
            raise LaunchError(f"The {name} budget must be a {kind} dollar amount, not {amount!r}.")
        env[setting] = amount
    return env


def api_env(
    *,
    port: int,
    passwords: Passwords,
    keyring: str,
    anthropic_api_key: str,
    voyage_api_key: str | None,
    scripted: bool = False,
    budgets_usd: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The API's settings: production, the real transport, a loopback origin, the API's login only
    (never the owner's or the cleanup login's URL). The test keyring is refused.

    `scripted` runs the same image as a test with the scripted model, paced like the real one, and
    no model key: production refuses that transport, and a dry run must cost nothing.
    `budgets_usd` lowers the AI budgets, so a paid run can't pass its cap."""
    from app.core.encryption import LocalKeyProvider  # imported here: needs apps/api on the path.

    if keyring == container.TEST_KEYRING or LocalKeyProvider.from_keyring(keyring).uses_test_key:
        raise LaunchError("The keyring holds the test key, which production refuses.")
    env = {
        "APP_ENV": "test" if scripted else "production",
        "AI_TRANSPORT": "scripted" if scripted else "anthropic",
        "APP_ORIGIN": origin_for(port),
        "PORT": str(port),
        "DATABASE_URL": _database_url(APP_LOGIN, passwords.app),
        "ENCRYPTION_KEYRING": keyring,
        **entry_env(passwords),
        **budget_env({**PORTFOLIO_BUDGETS_USD, **(budgets_usd or {})}),
    }
    if scripted:
        env["SCRIPTED_DELAY_PROFILE"] = "realistic"
    else:
        env["ANTHROPIC_API_KEY"] = anthropic_api_key
        if voyage_api_key:
            env["VOYAGE_API_KEY"] = voyage_api_key
    return env


def ai_off_secrets(secrets_: Secrets) -> Secrets:
    """The secrets for the live-AI-off check: the keyring, and made-up model keys (no Voyage key).
    Nothing the caller read for the model is passed on."""
    return Secrets(AI_OFF_API_KEY, None, secrets_.keyring)


def read_secrets(*, require_key: bool = True) -> Secrets:
    """The keys and the keyring from the API's settings (apps/api/.env, the environment, and the
    keyring file). Nothing here is printed. With `require_key=False` (the live-AI-off check) a
    missing Anthropic key is fine, and the Secrets carry an empty one."""
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
    if require_key:
        key = require_anthropic_key(None if anthropic is None else anthropic.get_secret_value())
    else:
        key = ""
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


def db_run_args(env: dict[str, str]) -> list[str]:
    return container.database_run_args(DB_NAME, NETWORK, env)


def setup_run_args(env: dict[str, str]) -> list[str]:
    return container.setup_run_args(f"{API_NAME}-setup", NETWORK, env)


def cleanup_run_args(env: dict[str, str]) -> list[str]:
    return container.cleanup_run_args(f"{API_NAME}-cleanup", NETWORK, env)


def api_run_args(env: dict[str, str], *, port: int, detach: bool) -> list[str]:
    """The API with production's memory limit and hardened flags."""
    return container.run_args(
        API_NAME,
        env,
        port=port,
        detach=detach,
        image=container.PROD_TAG,
        network=NETWORK,
        extra_args=["--memory", API_MEMORY, *container.HARDENED_FLAGS],
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
    if not container.postgres_ready(DB_NAME, timeout_seconds=DB_READY_TIMEOUT_SECONDS):
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
    container.remove(f"{API_NAME}-cleanup")
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


TURNSTILE_ORIGIN = "https://challenges.cloudflare.com"


def directive_sources(csp: str, name: str) -> list[str]:
    """The sources a Content-Security-Policy lists for one directive (empty if it has none)."""
    for directive in csp.split(";"):
        words = directive.split()
        if words and words[0] == name:
            return words[1:]
    return []


def serves_the_schema_or_swagger(content_type: str, body: str) -> bool:
    """True when a response is the API's schema (JSON) or Swagger's page. The web app's own page
    answering at the same path is fine."""
    return "json" in content_type.lower() or "swagger" in body.lower()


def problems_in_responses(
    *,
    home_status: int,
    csp: str,
    live_status: int,
    health_status: int,
    availability_status: int,
    availability_body: object,
    openapi_content_type: str,
    openapi_body: str,
    docs_body: str,
) -> list[str]:
    """What the page check concludes from what it saw. Plain data in, problems out."""
    problems: list[str] = []
    if home_status != 200:
        problems.append(f"/ answered {home_status}")
    if "'nonce-" not in csp:
        problems.append("/ has no Content-Security-Policy with a nonce")
    for directive in ("script-src", "frame-src"):
        if TURNSTILE_ORIGIN not in directive_sources(csp, directive):
            problems.append(f"the Content-Security-Policy's {directive} does not name Turnstile")
    if live_status != 200:
        problems.append(f"/api/v1/health/live answered {live_status}")
    if health_status != 200:
        problems.append(f"/api/v1/health answered {health_status}")
    if availability_status != 200:
        problems.append(f"/api/v1/assistant/availability answered {availability_status}")
    elif not (
        isinstance(availability_body, dict) and isinstance(availability_body.get("available"), bool)
    ):
        problems.append("/api/v1/assistant/availability has no boolean `available`")
    if serves_the_schema_or_swagger(openapi_content_type, openapi_body):
        problems.append("/openapi.json serves the API schema in production")
    if serves_the_schema_or_swagger("", docs_body):
        problems.append("/docs serves Swagger in production")
    return problems


def json_or_none(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return None


def problems_in_pages(base: str) -> list[str]:
    """Fetch the home page and the routes that need no session. No model call, no sandbox."""
    with httpx.Client(base_url=base, timeout=10) as client:
        home = client.get("/", headers={"accept": "text/html"})
        live = client.get("/api/v1/health/live")
        health = client.get("/api/v1/health")
        availability = client.get("/api/v1/assistant/availability")
        openapi = client.get("/openapi.json")
        docs = client.get("/docs")
    return problems_in_responses(
        home_status=home.status_code,
        csp=home.headers.get("content-security-policy", ""),
        live_status=live.status_code,
        health_status=health.status_code,
        availability_status=availability.status_code,
        availability_body=json_or_none(availability),
        openapi_content_type=openapi.headers.get("content-type", ""),
        openapi_body=openapi.text,
        docs_body=docs.text,
    )


CLEANUP_DONE_LINE = "cleanup finished"


def problems_in_cleanup(exit_code: int, output: str) -> list[str]:
    problems = []
    if exit_code != 0:
        problems.append(f"the cleanup container exited {exit_code}")
    if CLEANUP_DONE_LINE not in output:
        problems.append(f"the cleanup container did not print {CLEANUP_DONE_LINE!r}")
    return problems


def run_cleanup_job(env: dict[str, str]) -> list[str]:
    """Run the cleanup container once, as the deploy's schedule would, and judge it."""
    result = subprocess.run(  # noqa: S603
        cleanup_run_args(env),
        env=container.client_env(env),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    output = result.stdout + result.stderr
    problems = problems_in_cleanup(result.returncode, output)
    if problems:
        tail = "\n".join(output.strip().splitlines()[-LOG_LINES:])
        problems.append(tail)
    return problems


# --- the two ways to run -----------------------------------------------------------------------


def bring_up(
    secrets_: Secrets,
    port: int,
    *,
    scripted: bool = False,
    budgets_usd: Mapping[str, str] | None = None,
    passwords: Passwords | None = None,
) -> tuple[bool, dict[str, str]]:
    """Start the database and run the setup; returns whether this run made the network and the
    API's settings. Cleans up after itself if a step fails. A caller that needs the passwords
    afterward (the check runs the cleanup job) makes them and passes them in."""
    passwords = passwords or Passwords.new()
    require_the_image()
    # A stale container of the same name is removed first.
    container.remove(API_NAME)
    container.remove(f"{API_NAME}-setup")
    container.remove(f"{API_NAME}-cleanup")
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
            scripted=scripted,
            budgets_usd=budgets_usd,
        )
    except BaseException:
        cleanup(made_network=made_network)
        raise
    return made_network, env


@contextmanager
def running(
    secrets_: Secrets,
    port: int,
    *,
    scripted: bool = False,
    budgets_usd: Mapping[str, str] | None = None,
) -> Iterator[str]:
    """The API running on its own database for the length of the block, at its loopback origin
    (what a browser must use: the API checks the origin). Everything is stopped and removed after,
    however the block ends. For the recording and the live check."""
    made_network, env = bring_up(secrets_, port, scripted=scripted, budgets_usd=budgets_usd)
    try:
        container.run(*api_run_args(env, port=port, detach=True), env=env)
        wait_until_ready(f"http://127.0.0.1:{port}")
        yield origin_for(port)
    finally:
        cleanup(made_network=made_network)


def query_args(sql: str) -> list[str]:
    """`psql` in the run's database container, as the owner, printing bare values."""
    return [
        "docker", "exec", DB_NAME,
        "psql", "-U", DB_OWNER, "-d", DB_DATABASE, "-v", "ON_ERROR_STOP=1", "-At", "-c", sql,
    ]  # fmt: skip


def query(sql: str) -> str:
    """Run `sql` in the run's database and return what it printed. Only while `running`."""
    result = subprocess.run(query_args(sql), capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise LaunchError(f"The query failed: {result.stderr.strip()}")
    return result.stdout.strip()


def problems_with_ai_off(base: str, origin: str) -> list[str]:
    """What a visitor meets when live AI is off: the flag says false, a sandbox still starts (with
    Turnstile's always-pass dummy token), and a question is refused with the daily text and no
    Retry-After (the month isn't coming back). No model is called: the budget stops it first."""
    from app.ai.fixed_texts import BUDGET_DAILY_TEXT  # imported here: needs apps/api on the path.
    from app.modules.sandbox.turnstile import DUMMY_TOKEN

    problems: list[str] = []
    same_origin = {"Origin": origin, "Sec-Fetch-Site": "same-origin"}
    with httpx.Client(base_url=base, timeout=30) as client:
        flag = client.get("/api/v1/assistant/availability")
        if flag.status_code != 200 or flag.json() != {"available": False}:
            return [f"the availability flag answered {flag.status_code} {flag.text[:200]}"]
        # The cookies are set by hand: `__Host-` cookies are Secure, and a client's cookie jar won't
        # send them over plain http.
        started = client.post(
            "/api/v1/sandboxes", json={"turnstileToken": DUMMY_TOKEN}, headers=same_origin
        )
        if started.status_code != 201:
            return [f"starting a sandbox answered {started.status_code} {started.text[:200]}"]
        session = started.cookies.get("__Host-od_session")
        csrf = started.cookies.get("__Host-od_csrf")
        if not session or not csrf:
            return ["starting a sandbox did not set the session cookies"]
        headers = {
            **same_origin,
            "Cookie": f"__Host-od_session={session}; __Host-od_csrf={csrf}",
            "X-CSRF-Token": csrf,
        }
        conversation = client.post("/api/v1/assistant/conversations", json={}, headers=headers)
        if conversation.status_code != 201:
            return [f"a new conversation answered {conversation.status_code}"]
        asked = client.post(
            f"/api/v1/assistant/conversations/{conversation.json()['id']}/turns",
            json={"question": "How many sick days do I get?"},
            headers=headers,
        )
        body = asked.json() if asked.headers.get("content-type", "").endswith("json") else {}
        if asked.status_code != 429 or body.get("type") != "budget-daily":
            problems.append(f"a question answered {asked.status_code}, not 429 budget-daily")
        elif body.get("detail") != BUDGET_DAILY_TEXT:
            problems.append("the refusal is not the approved daily text")
        if "retry-after" in asked.headers:
            problems.append("the refusal promises a retry (Retry-After), but the month is used")
    return problems


def check(secrets_: Secrets, port: int, *, ai_off: bool = False) -> int:
    if ai_off:
        secrets_ = ai_off_secrets(secrets_)
    passwords = Passwords.new()
    made_network, env = bring_up(
        secrets_, port, budgets_usd=AI_OFF_BUDGETS_USD if ai_off else None, passwords=passwords
    )
    base = f"http://127.0.0.1:{port}"
    try:
        container.run(*api_run_args(env, port=port, detach=True), env=env)
        wait_until_ready(base)
        problems = problems_in_pages(base)
        problems += run_cleanup_job(cleanup_env(passwords))
        if ai_off:
            problems += problems_with_ai_off(base, origin_for(port))
        if problems:
            raise LaunchError("\n".join(problems) + "\n" + last_logs(API_NAME))
    finally:
        cleanup(made_network=made_network)
    print(f"prod-local check passed: {container.PROD_TAG} served {base} with production settings")
    if ai_off:
        print("With live AI off: the flag said false, a sandbox started, and a question was")
        print("refused with the daily text. No model was called.")
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
    parser.add_argument(
        "--ai-off",
        action="store_true",
        help="with --check: run with live AI turned off ($0 monthly budget); no model key needed",
    )
    options = parser.parse_args(argv)
    if options.ai_off and not options.check:
        parser.error("--ai-off goes with --check: serving with live AI off has nothing to ask")
    # Until `serve` takes over, a stop signal unwinds like Ctrl-C, so the cleanup in `bring_up`
    # and `check` runs and no database container or network is left behind.
    for signum in STOP_SIGNALS:
        signal.signal(signum, _interrupt)
    try:
        port = check_port(options.port)
        if options.ai_off:
            return check(read_secrets(require_key=False), port, ai_off=True)
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
