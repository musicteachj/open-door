"""The image check's own judgment, and the entrypoint's forwarding rule. No Docker, no network.

`scripts/image/check.py` inspects the built image; this proves that what it concludes from what it
saw is right, and that an empty FORWARDED_ALLOW_IPS means "trust no proxy" all the way through
`scripts/image/entrypoint.sh` and uvicorn's proxy-header middleware.
"""

import importlib.util
import os
import stat
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "image" / "check.py"
ENTRYPOINT = REPO / "scripts" / "image" / "entrypoint.sh"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("image_check_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load_script()

GOOD_HEADERS = {
    **check.EXPECTED_HEADERS,
    "cache-control": "no-store",
    "content-security-policy": "default-src 'self'; style-src 'self' 'nonce-abc'; "
    "frame-ancestors 'none'",
}
GOOD_BODY = '<meta name="csp-nonce" content="abc" />'


def test_emsign_roots_are_found_by_name() -> None:
    names = ["ISRG_Root_X1.crt", "emSign_Root_CA_-_C1.crt", "emSign_ECC_Root_CA_-_C3.crt"]
    assert check.emsign_roots_in(names) == [
        "emSign_ECC_Root_CA_-_C3.crt",
        "emSign_Root_CA_-_C1.crt",
    ]
    assert check.emsign_roots_in(["ISRG_Root_X1.crt"]) == []


def test_a_root_user_is_caught() -> None:
    assert check.problems_in_user("10001:10001", 10001) == []
    assert check.problems_in_user("", 0)
    assert check.problems_in_user("0:0", 0)


def test_files_that_should_not_be_there_are_each_reported() -> None:
    assert check.problems_in_files([]) == []
    assert len(check.problems_in_files(["/app/.env", "/app/tests"])) == 2


def test_the_config_must_match_the_deploy() -> None:
    health = [
        "CMD",
        "python",
        "-c",
        "host = os.environ.get('HOST'); port = os.environ.get('PORT'); "
        f"urlopen(f'...{{host}}:{{port}}{check.HEALTH_PATH}')",
    ]
    good_env = ["PATH=/bin", "APP_ENV=production"]
    assert check.problems_in_config(["/app/entrypoint.sh"], health, good_env) == []
    # Without APP_ENV a deploy that forgot it would start with the development defaults.
    assert check.problems_in_config(["/app/entrypoint.sh"], health, ["PATH=/bin"])
    assert check.problems_in_config(["sh"], health, [])
    assert check.problems_in_config(["/app/entrypoint.sh"], None, [])
    assert check.problems_in_config(["/app/entrypoint.sh"], ["CMD", "true"], [])
    assert check.problems_in_config(["/app/entrypoint.sh"], health, ["ENCRYPTION_KEYRING=x"])
    # A health check pinned to :8000 fails every container started with another PORT.
    pinned = ["CMD", "python", "-c", f"urlopen('http://127.0.0.1:8000{check.HEALTH_PATH}')"]
    assert check.problems_in_config(["/app/entrypoint.sh"], pinned, [])


def test_a_good_page_has_no_problems() -> None:
    assert check.problems_in_page(GOOD_HEADERS, GOOD_BODY, "/") == []


@pytest.mark.parametrize(
    ("change", "body"),
    [
        ({"cache-control": "max-age=60"}, GOOD_BODY),
        ({"strict-transport-security": "max-age=1"}, GOOD_BODY),
        ({"content-security-policy": "default-src 'self'; frame-ancestors 'none'"}, GOOD_BODY),
        ({}, "<html></html>"),
        ({"content-security-policy": "default-src 'self'"}, GOOD_BODY),
    ],
)
def test_a_bad_page_is_caught(change: dict[str, str], body: str) -> None:
    assert check.problems_in_page({**GOOD_HEADERS, **change}, body, "/")


def test_repeated_nonces_are_caught() -> None:
    assert check.problems_in_nonces("a", "b") == []
    assert check.problems_in_nonces("a", "a")
    assert check.problems_in_nonces(None, "a")


def test_client_addresses_are_read_from_the_access_log() -> None:
    log = 'INFO:     172.17.0.1:5432 - "GET /api/v1/health/live HTTP/1.1" 200 OK\n'
    assert check.client_addresses_in(log) == ["172.17.0.1"]
    json_log = (
        '{"logger": "uvicorn.access", "message": "172.17.0.1:64170 - \\"GET / HTTP/1.1\\" 200"}'
    )
    assert check.client_addresses_in(json_log) == ["172.17.0.1"]


def test_forwarding_judgment_catches_a_trusted_forgery_and_a_failed_control() -> None:
    forged = check.FORGED_CLIENT
    untrusted_ok = (
        'INFO:     172.17.0.1:1 - "GET /x HTTP/1.1" 200 OK\n' * check.LOGGED_REQUESTS_MINIMUM
    )
    trusted_ok = f'INFO:     {forged}:0 - "GET /x HTTP/1.1" 200 OK'
    assert check.problems_in_forwarding(untrusted_ok, trusted_ok, "172.17.0.1") == []
    assert check.problems_in_forwarding(trusted_ok, trusted_ok, "172.17.0.1")
    assert check.problems_in_forwarding(untrusted_ok, untrusted_ok, "172.17.0.1")
    assert check.problems_in_forwarding("", trusted_ok, "172.17.0.1")
    one_line = 'INFO:     172.17.0.1:1 - "GET /x HTTP/1.1" 200 OK\n'
    assert check.problems_in_forwarding(one_line, trusted_ok, "172.17.0.1")
    assert check.problems_in_forwarding(untrusted_ok, trusted_ok, None)


def test_the_database_host_is_rewritten_only_on_macos() -> None:
    url = "postgresql+asyncpg://u:p@127.0.0.1:5433/opendoor"
    assert (
        check.container.database_url_for_container(url, platform="darwin")
        == "postgresql+asyncpg://u:p@host.docker.internal:5433/opendoor"
    )
    assert check.container.database_url_for_container(url, platform="linux") == url
    remote = "postgresql+asyncpg://u:p@db.example:5432/x"
    assert check.container.database_url_for_container(remote, platform="darwin") == remote


# --- The entrypoint ---------------------------------------------------------------------------


def run_entrypoint(tmp_path: Path, **env: str) -> list[str]:
    """Run the real entrypoint with a stand-in `uvicorn` that prints its arguments and the
    FORWARDED_ALLOW_IPS it was started with."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "uvicorn"
    fake.write_text('#!/bin/sh\necho "args: $*"\necho "env: [${FORWARDED_ALLOW_IPS-unset}]"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    environment = {"PATH": f"{bin_dir}:/usr/bin:/bin", **env}
    result = subprocess.run(  # noqa: S603
        ["/bin/sh", str(ENTRYPOINT)],
        capture_output=True,
        text=True,
        env=environment,
        check=True,
    )
    return result.stdout.splitlines()


COMMON = (
    "--factory app.main:create_app --host 0.0.0.0 --port 8000 --proxy-headers"
    " --no-server-header --timeout-graceful-shutdown 15"
)


def test_the_entrypoint_is_executable() -> None:
    assert os.access(ENTRYPOINT, os.X_OK)


@pytest.mark.parametrize("env", [{}, {"FORWARDED_ALLOW_IPS": ""}])
def test_an_empty_or_unset_variable_passes_no_flag_and_exports_empty(
    tmp_path: Path, env: dict[str, str]
) -> None:
    lines = run_entrypoint(tmp_path, **env)
    assert lines == [f"args: {COMMON}", "env: []"]


def test_host_sets_the_bind_address_and_defaults_to_every_interface(tmp_path: Path) -> None:
    lines = run_entrypoint(tmp_path, HOST="127.0.0.1")
    assert lines[0] == f"args: {COMMON.replace('--host 0.0.0.0', '--host 127.0.0.1')}"


def test_port_sets_the_listening_port_and_defaults_to_8000(tmp_path: Path) -> None:
    lines = run_entrypoint(tmp_path, PORT="8100")
    assert lines[0] == f"args: {COMMON.replace('--port 8000', '--port 8100')}"


def test_a_set_variable_is_passed_as_the_flag(tmp_path: Path) -> None:
    lines = run_entrypoint(tmp_path, FORWARDED_ALLOW_IPS="10.0.1.5,10.0.2.0/24")
    assert lines[0] == f"args: {COMMON} --forwarded-allow-ips 10.0.1.5,10.0.2.0/24"


async def forged_client_seen_by_the_app(monkeypatch: pytest.MonkeyPatch, env: str | None) -> Any:
    """What the app sees as the client, when a request from 127.0.0.1 forges X-Forwarded-For and
    uvicorn is configured the way the entrypoint leaves it."""
    import uvicorn

    if env is None:
        monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    else:
        monkeypatch.setenv("FORWARDED_ALLOW_IPS", env)
    config = uvicorn.Config("app.main:create_app", factory=True, proxy_headers=True)
    seen: list[Any] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["client"])

    middleware = ProxyHeadersMiddleware(app, trusted_hosts=config.forwarded_allow_ips)
    scope = {
        "type": "http",
        "client": ("127.0.0.1", 5000),
        "headers": [(b"x-forwarded-for", b"203.0.113.9")],
    }
    await middleware(scope, None, None)  # type: ignore[arg-type]
    return seen[0]


async def test_uvicorn_trusts_no_proxy_when_the_variable_is_exported_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (await forged_client_seen_by_the_app(monkeypatch, "")) == ("127.0.0.1", 5000)


async def test_control_unset_falls_back_to_loopback_so_the_entrypoint_must_export_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Why the entrypoint exports an empty value instead of leaving the variable unset: unset
    # makes uvicorn trust 127.0.0.1, and so would believe this forged header.
    assert (await forged_client_seen_by_the_app(monkeypatch, None))[0] == "203.0.113.9"
