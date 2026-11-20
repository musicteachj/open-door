"""`make prod-local`: how the production image is started on its own database. No Docker, no
network: it judges the arguments and settings `scripts/prod-local/start.py` builds."""

import importlib.util
import re
import signal
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import BaseModel

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "prod-local" / "start.py"
sys.path.insert(0, str(REPO / "scripts" / "image"))

# A real-looking keyring line, made for this file only.
KEYRING = "k1:3q2+7wDevR1g5t0Y8N4mZcX9bQhLpUoAaSdFgHjKl6w="
ANTHROPIC = "sk-ant-test-value-not-real"
VOYAGE = "pa-test-value-not-real"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("prod_local_start_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


start = load_script()
container = start.container


def pairs(args: list[str], flag: str) -> list[str]:
    return [args[i + 1] for i, arg in enumerate(args) if arg == flag]


def passwords() -> object:
    return start.Passwords.new()


def api_env(**overrides: object) -> dict[str, str]:
    values: dict[str, object] = {
        "port": start.DEFAULT_PORT,
        "passwords": passwords(),
        "keyring": KEYRING,
        "anthropic_api_key": ANTHROPIC,
        "voyage_api_key": None,
    }
    values.update(overrides)
    result: dict[str, str] = start.api_env(**values)
    return result


def test_the_api_runs_with_production_settings_on_a_loopback_origin() -> None:
    env = api_env()

    assert env["APP_ENV"] == "production"
    assert env["AI_TRANSPORT"] == "anthropic"
    assert env["APP_ORIGIN"] == "http://localhost:8300"
    assert env["PORT"] == "8300"
    assert env["ENCRYPTION_KEYRING"] == KEYRING
    assert env["ANTHROPIC_API_KEY"] == ANTHROPIC
    assert "VOYAGE_API_KEY" not in env


def test_the_api_gets_test_turnstile_keys_and_a_fresh_address_hash_key() -> None:
    from app.core.config import (
        DEVELOPMENT_IP_HASH_KEY,
        Settings,
        require_entry_settings_fit_for_production,
    )

    first, second = api_env(), api_env()
    # Cloudflare's public always-pass test keys: production accepts them on a loopback origin only,
    # and the API answers them itself.
    assert first["TURNSTILE_SITE_KEY"] == "1x00000000000000000000AA"
    assert first["TURNSTILE_SECRET_KEY"] == "1x0000000000000000000000000000000AA"  # noqa: S105
    assert len(first["SANDBOX_IP_HASH_KEY"]) >= 32
    assert first["SANDBOX_IP_HASH_KEY"] != DEVELOPMENT_IP_HASH_KEY
    assert first["SANDBOX_IP_HASH_KEY"] != second["SANDBOX_IP_HASH_KEY"]
    # And the API's startup check for production accepts all of it.
    require_entry_settings_fit_for_production(
        Settings(
            _env_file=None,
            database_url=first["DATABASE_URL"],
            app_env="production",
            app_origin=first["APP_ORIGIN"],
            turnstile_site_key=first["TURNSTILE_SITE_KEY"],
            turnstile_secret_key=first["TURNSTILE_SECRET_KEY"],
            sandbox_ip_hash_key=first["SANDBOX_IP_HASH_KEY"],
        )
    )


def test_the_voyage_key_goes_in_only_when_there_is_one() -> None:
    assert api_env(voyage_api_key=VOYAGE)["VOYAGE_API_KEY"] == VOYAGE


def test_the_api_reaches_its_own_database_as_the_app_login() -> None:
    env = api_env()

    assert env["DATABASE_URL"].startswith("postgresql+asyncpg://od_app_login:")
    assert f"@{start.DB_NAME}:5432/" in env["DATABASE_URL"]
    assert "MIGRATION_DATABASE_URL" not in env
    assert "CLEANUP_DATABASE_URL" not in env


def test_the_test_keyring_is_never_passed_to_the_production_image() -> None:
    with pytest.raises(start.LaunchError, match="test key"):
        api_env(keyring=container.TEST_KEYRING)


def test_port_5173_is_refused_and_so_is_a_port_that_is_not_one() -> None:
    for bad in (5173, 0, 70000):
        with pytest.raises(start.LaunchError):
            start.check_port(bad)
    assert start.check_port(8301) == 8301


def test_the_origin_follows_the_port() -> None:
    assert start.origin_for(8301) == "http://localhost:8301"
    assert api_env(port=8301)["APP_ORIGIN"] == "http://localhost:8301"


def test_run_args_hold_no_secret_value() -> None:
    p = passwords()
    env = api_env(passwords=p, voyage_api_key=VOYAGE)
    api = start.api_run_args(env, port=8300, detach=False)
    setup = start.setup_run_args(start.setup_env(p, start.origin_for(8300)))
    db = start.db_run_args(start.db_env(p))

    for args, secret_env in ((api, env), (setup, start.setup_env(p, "")), (db, start.db_env(p))):
        joined = "\n".join(args)
        for key, value in secret_env.items():
            if key in ("APP_ENV", "AI_TRANSPORT", "PORT", "APP_ORIGIN", "POSTGRES_USER"):
                continue
            assert value not in joined
            assert key in pairs(args, "--env")
    for args in (api, setup, db):
        assert all("=" not in value for value in pairs(args, "--env"))


def test_the_api_joins_the_private_network_and_publishes_on_loopback_only() -> None:
    args = start.api_run_args(api_env(), port=8300, detach=True)

    assert pairs(args, "--network") == [start.NETWORK]
    assert pairs(args, "--publish") == ["127.0.0.1:8300:8300"]
    assert args[-1] == container.PROD_TAG == "open-door:prod"
    assert pairs(args, "--name") == [start.API_NAME]


def test_the_database_is_throwaway_private_and_on_the_same_image_as_compose() -> None:
    args = start.db_run_args(start.db_env(passwords()))

    assert "--rm" in args
    assert "--detach" in args
    assert "--publish" not in args
    assert "--volume" not in args
    assert "-v" not in args
    assert pairs(args, "--network") == [start.NETWORK]
    assert args[-1] == start.POSTGRES_IMAGE


def test_the_postgres_tag_matches_composes() -> None:
    compose = (REPO / "compose.yaml").read_text(encoding="utf-8")
    match = re.search(r"^\s+image:\s*(pgvector/pgvector:\S+)\s*$", compose, re.MULTILINE)

    assert match is not None
    assert match.group(1) == start.POSTGRES_IMAGE


def test_the_setup_runs_its_own_entrypoint_with_no_keyring_and_no_api_keys() -> None:
    p = passwords()
    env = start.setup_env(p, start.origin_for(8300))
    args = start.setup_run_args(env)

    assert env["APP_ENV"] == "production"
    assert {"DATABASE_URL", "MIGRATION_DATABASE_URL", "CLEANUP_DATABASE_URL"} <= set(env)
    assert not {"ENCRYPTION_KEYRING", "ANTHROPIC_API_KEY", "VOYAGE_API_KEY"} & set(env)
    # Only the serving API checks the sandbox-entry settings; the setup tasks carry none.
    assert not {"TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY", "SANDBOX_IP_HASH_KEY"} & set(env)
    assert "--rm" in args
    assert pairs(args, "--entrypoint") == ["/app/setup.sh"]
    assert pairs(args, "--memory") == ["256m"]
    assert args[-1] == container.PROD_TAG


def test_the_cleanup_container_gets_only_its_own_login() -> None:
    p = passwords()
    env = start.cleanup_env(p)
    args = start.cleanup_run_args(env)

    assert set(env) == {"CLEANUP_DATABASE_URL"}
    assert env["CLEANUP_DATABASE_URL"].startswith("postgresql+asyncpg://od_cleanup_login:")
    assert pairs(args, "--entrypoint") == ["/app/cleanup.sh"]
    assert pairs(args, "--memory") == ["128m"]
    password = env["CLEANUP_DATABASE_URL"].split(":")[2].split("@")[0]
    assert password not in "\n".join(args)


def test_the_api_runs_with_productions_memory_limit_and_flags() -> None:
    args = start.api_run_args(api_env(), port=8300, detach=True)

    assert pairs(args, "--memory") == ["512m"]
    for flag in container.HARDENED_FLAGS:
        assert flag in args
    assert args[-1] == container.PROD_TAG


GOOD_CSP = (
    "default-src 'self'; script-src 'self' 'nonce-a' https://challenges.cloudflare.com; "
    "frame-src https://challenges.cloudflare.com; frame-ancestors 'none'"
)
SWAGGER = "<html><title>Open Door API - Swagger UI</title></html>"
SPA = '<html><meta name="csp-nonce" content="a" /></html>'


def judge(**changes: object) -> list[str]:
    seen: dict[str, object] = {
        "home_status": 200,
        "csp": GOOD_CSP,
        "live_status": 200,
        "health_status": 200,
        "availability_status": 200,
        "availability_body": {"available": True},
        "openapi_content_type": "text/html; charset=utf-8",
        "openapi_body": SPA,
        "docs_body": SPA,
    }
    seen.update(changes)
    problems: list[str] = start.problems_in_responses(**seen)
    return problems


def test_a_good_set_of_pages_has_no_problems() -> None:
    assert judge() == []


def test_the_page_check_wants_turnstile_the_flag_and_no_docs() -> None:
    no_script = GOOD_CSP.replace(
        "script-src 'self' 'nonce-a' https://challenges.cloudflare.com", "script-src 'self'"
    )
    no_frame = GOOD_CSP.replace("frame-src https://challenges.cloudflare.com", "frame-src 'self'")
    assert judge(csp=no_script)
    assert judge(csp=no_frame)
    # Turnstile named only outside script-src and frame-src does not count.
    assert judge(csp=no_script + "; connect-src https://challenges.cloudflare.com")
    assert judge(availability_body={"available": "yes"})
    assert judge(availability_body={})
    assert judge(availability_status=500)
    assert judge(health_status=503)
    assert judge(openapi_content_type="application/json", openapi_body='{"openapi": "3.1.0"}')
    assert judge(openapi_body='{"openapi": "3.1.0"}', openapi_content_type="application/json")
    assert judge(docs_body=SWAGGER)
    # The web app's page answering at these paths is fine.
    assert judge(openapi_body=SPA, docs_body=SPA) == []


def test_each_run_gets_new_passwords() -> None:
    first, second = start.Passwords.new(), start.Passwords.new()

    assert first != second
    assert len({first.owner, first.app, first.cleanup}) == 3


def test_without_an_anthropic_key_it_stops_and_says_questions_are_paid() -> None:
    for missing in (None, ""):
        with pytest.raises(start.LaunchError) as stopped:
            start.require_anthropic_key(missing)
        message = str(stopped.value)
        assert "ANTHROPIC_API_KEY" in message
        assert "paid" in message
    assert start.require_anthropic_key(ANTHROPIC) == ANTHROPIC


def test_the_launcher_has_no_em_dash() -> None:
    assert chr(0x2014) not in SCRIPT.read_text(encoding="utf-8")


class FakeDocker:
    """Records the docker steps instead of running them."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.steps: list[str] = []
        monkeypatch.setattr(start, "require_the_image", lambda: None)
        monkeypatch.setattr(start, "ensure_network", self.ensure_network)
        monkeypatch.setattr(container, "remove", lambda name: self.steps.append(f"remove {name}"))
        monkeypatch.setattr(start, "cleanup", self.cleanup)
        monkeypatch.setattr(start, "read_secrets", lambda: start.Secrets(ANTHROPIC, None, KEYRING))

    def ensure_network(self) -> bool:
        self.steps.append("network")
        return True

    def cleanup(self, *, made_network: bool) -> None:
        self.steps.append(f"cleanup network={made_network}")


def test_a_failed_setup_removes_the_database_and_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker = FakeDocker(monkeypatch)
    monkeypatch.setattr(start, "start_database", lambda _passwords: docker.steps.append("db"))

    def setup_fails(_env: dict[str, str]) -> None:
        raise start.LaunchError("The one-off setup failed")

    monkeypatch.setattr(start, "run_setup", setup_fails)

    assert start.main(["--check"]) == 1
    assert docker.steps[-1] == "cleanup network=True"


def test_a_stop_signal_during_startup_still_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    docker = FakeDocker(monkeypatch)

    def terminated_while_waiting(_passwords: object) -> None:
        docker.steps.append("db")
        # A closed terminal or `kill` while Postgres starts: the handler main installed runs.
        signal.raise_signal(signal.SIGTERM)

    monkeypatch.setattr(start, "start_database", terminated_while_waiting)
    previous = {signum: signal.getsignal(signum) for signum in start.STOP_SIGNALS}
    try:
        assert start.main(["--check"]) == 130
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    assert "cleanup network=True" in docker.steps


def test_without_a_key_main_stops_before_any_docker_step(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    docker = FakeDocker(monkeypatch)

    def no_key() -> object:
        return start.require_anthropic_key(None)

    monkeypatch.setattr(start, "read_secrets", no_key)

    assert start.main(["--check"]) == 1
    assert docker.steps == []
    assert "paid" in capsys.readouterr().err


def test_invalid_settings_name_the_field_and_never_its_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.config

    class Broken(BaseModel):
        database_url: int

    def broken_settings() -> object:
        return Broken.model_validate({"database_url": "postgresql://u:hunter2-secret@h/db"})

    monkeypatch.setattr(app.core.config, "Settings", broken_settings)

    with pytest.raises(start.LaunchError) as raised:
        start.read_secrets()

    assert "database_url" in str(raised.value)
    assert "hunter2-secret" not in str(raised.value)


def test_a_ctrl_c_before_the_api_container_exists_still_stops_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first `docker stop` finds no container yet; the stop is retried until `docker run`
    exits, so the run doesn't hang with the API up."""
    stops: list[str] = []

    class FakeRun:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.code: int | None = None

        def poll(self) -> int | None:
            return self.code

        def wait(self) -> int:
            deadline = time.monotonic() + 5
            while self.code is None:
                assert time.monotonic() < deadline, "the launcher hung with the API still up"
            return self.code

    runs: list[FakeRun] = []

    def fake_popen(*args: object, **kwargs: object) -> FakeRun:
        runs.append(FakeRun())
        return runs[-1]

    def fake_docker(*args: str, check: bool = True) -> object:
        if args[0] == "stop":
            stops.append(args[-1])
            # The container exists only from the third try (one each from the signal and the start
            # find nothing); then `docker run` exits.
            if len(stops) >= 3 and runs:
                runs[0].code = 143
        return None

    def banner_then_ctrl_c(*_args: object, **_kwargs: object) -> None:
        signal.raise_signal(signal.SIGINT)

    monkeypatch.setattr(start, "bring_up", lambda _secrets, _port: (False, {}))
    monkeypatch.setattr(start, "cleanup", lambda *, made_network: None)
    monkeypatch.setattr(start, "docker", fake_docker)
    monkeypatch.setattr(start.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(start.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr("builtins.print", banner_then_ctrl_c)
    previous = {signum: signal.getsignal(signum) for signum in start.STOP_SIGNALS}
    try:
        code = start.serve(start.Secrets(ANTHROPIC, None, KEYRING), start.DEFAULT_PORT)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)

    assert code == 0
    assert len(stops) >= 3


# --- Phase 8 Task 45 and 46: the recording and the live check reuse the launcher ---------------


def test_the_scripted_mode_runs_the_image_as_a_test_with_no_model_key() -> None:
    # The free dry run of the recording and the live check: production refuses the scripted model,
    # so the same image runs with APP_ENV=test, paced like the real model, and holds no API key.
    env = api_env(scripted=True)

    assert env["APP_ENV"] == "test"
    assert env["AI_TRANSPORT"] == "scripted"
    assert env["SCRIPTED_DELAY_PROFILE"] == "realistic"
    assert "ANTHROPIC_API_KEY" not in env
    assert env["APP_ORIGIN"] == "http://localhost:8300"


def test_a_run_can_lower_the_ai_budgets_for_a_capped_paid_run() -> None:
    env = api_env(budgets_usd={"daily": "0.66", "sandbox": "0.66"})

    assert env["AI_DAILY_BUDGET_USD"] == "0.66"
    assert env["AI_SANDBOX_BUDGET_USD"] == "0.66"
    assert env["APP_ENV"] == "production"


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "1e3", "NaN"])
def test_a_budget_must_be_a_positive_dollar_amount(bad: str) -> None:
    with pytest.raises(start.LaunchError, match="budget"):
        api_env(budgets_usd={"daily": bad})


def test_only_the_three_budgets_can_be_set() -> None:
    with pytest.raises(start.LaunchError, match="budget"):
        api_env(budgets_usd={"weekly": "1"})


def test_production_runs_get_the_portfolio_budgets() -> None:
    env = api_env()
    assert env["AI_MONTHLY_BUDGET_USD"] == "20"
    assert env["AI_SANDBOX_BUDGET_USD"] == "0.50"

    lowered = api_env(budgets_usd={"monthly": "2", "sandbox": "0.66"})
    assert lowered["AI_MONTHLY_BUDGET_USD"] == "2"
    assert lowered["AI_SANDBOX_BUDGET_USD"] == "0.66"


def test_only_the_monthly_budget_may_be_zero() -> None:
    assert start.budget_env({"monthly": "0"}) == {"AI_MONTHLY_BUDGET_USD": "0"}
    with pytest.raises(start.LaunchError, match="budget"):
        start.budget_env({"daily": "0"})


def test_the_database_query_runs_as_the_owner_inside_its_container() -> None:
    args = start.query_args("SELECT 1")

    assert args[:3] == ["docker", "exec", start.DB_NAME]
    assert args[args.index("-U") + 1] == start.DB_OWNER
    assert args[args.index("-d") + 1] == start.DB_DATABASE
    assert args[-2:] == ["-c", "SELECT 1"]
    assert "-At" in args


def test_running_stops_everything_when_the_body_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(start, "bring_up", lambda *_a, **_k: (True, {"PORT": "8300"}))
    monkeypatch.setattr(start.container, "run", lambda *_a, **_k: calls.append("run"))
    monkeypatch.setattr(start, "wait_until_ready", lambda _base: calls.append("ready"))
    monkeypatch.setattr(
        start, "cleanup", lambda *, made_network: calls.append(f"cleanup {made_network}")
    )

    def body() -> None:
        with start.running(object(), 8300) as base:
            calls.append(base)
            raise RuntimeError

    with pytest.raises(RuntimeError):
        body()

    assert calls == ["run", "ready", "http://localhost:8300", "cleanup True"]


def test_running_passes_the_mode_and_budgets_to_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_bring_up(
        _secrets: object, _port: int, **options: object
    ) -> tuple[bool, dict[str, str]]:
        seen.update(options)
        return False, {}

    monkeypatch.setattr(start, "bring_up", fake_bring_up)
    monkeypatch.setattr(start.container, "run", lambda *_a, **_k: None)
    monkeypatch.setattr(start, "wait_until_ready", lambda _base: None)
    monkeypatch.setattr(start, "cleanup", lambda *, made_network: None)

    with start.running(object(), 8300, scripted=True, budgets_usd={"daily": "1"}):
        pass

    assert seen == {"scripted": True, "budgets_usd": {"daily": "1"}}


# --- the check with live AI off (Phase 9a) ------------------------------------------------------


def test_the_ai_off_check_sets_a_zero_monthly_budget() -> None:
    secrets = start.ai_off_secrets(start.Secrets("", None, KEYRING))

    env = api_env(
        anthropic_api_key=secrets.anthropic_api_key,
        voyage_api_key=secrets.voyage_api_key,
        budgets_usd=start.AI_OFF_BUDGETS_USD,
    )

    assert env["AI_MONTHLY_BUDGET_USD"] == "0"
    assert env["APP_ENV"] == "production"
    assert env["AI_TRANSPORT"] == "anthropic"


def test_the_ai_off_check_never_passes_the_real_key(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[dict[str, object]] = []
    ran: list[bool] = []

    def read_without_a_key(**kwargs: object) -> object:
        asked.append(kwargs)
        return start.Secrets("", None, KEYRING)

    def check(secrets_: object, port: int, *, ai_off: bool = False) -> int:
        ran.append(ai_off)
        return 0

    monkeypatch.setattr(start, "read_secrets", read_without_a_key)
    monkeypatch.setattr(start, "check", check)

    assert start.main(["--check", "--ai-off"]) == 0

    # The key is never asked for, and a run that has none still starts.
    assert asked == [{"require_key": False}]
    assert ran == [True]
    # The key the image gets is a made-up one: an accidental model call fails and is never billed.
    fake = start.ai_off_secrets(start.Secrets("a-real-looking-key", "pa-real", KEYRING))
    assert fake.anthropic_api_key == "not-a-real-key-ai-off-check"
    assert fake.voyage_api_key is None
    assert api_env(anthropic_api_key=fake.anthropic_api_key)["ANTHROPIC_API_KEY"] == (
        "not-a-real-key-ai-off-check"
    )


def test_the_ai_off_flag_needs_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(start, "read_secrets", lambda **_: start.Secrets("", None, KEYRING))
    with pytest.raises(SystemExit):
        start.main(["--ai-off"])
