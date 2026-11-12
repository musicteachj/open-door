"""Inspect the production image: `make image-check`.

Run it with `make image-check`, after `make db`: it builds `open-door:prod` and `open-door:test`
(the same image with the component gallery; `SKIP_BUILD=1` uses images already built, as CI does
after its cached build), inspects them, and starts the test image against the development
database. It checks:

- the image runs as a fixed non-root user, and holds no `.env`, `.keys`, shell history, keyring
  file, test file, or keyring setting;
- `zoneinfo` loads America/Denver (the `tzdata` package is installed);
- the OS certificate store holds no emSign root (the Anthropic SDK reads it through truststore);
- the entrypoint and the health check are what the deploy expects;
- the production web app has no component gallery, and the test image does (the control that shows
  the check can fail);
- the image starts and answers `/`, a deep link, an asset, and the live health check with the
  security headers, a fresh nonce on every page, and the CSP that names it;
- a forged `X-Forwarded-For` is not trusted when `FORWARDED_ALLOW_IPS` is empty, and is trusted
  from the one address named when it is set (the control).

Everything it starts is stopped at the end. The judgment (`problems_in_*`, `emsign_roots_in`) is
plain functions, tested offline in `apps/api/tests/test_image_check_script.py`.
"""

import json
import os
import re
import shutil
import socket
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import container
from container import (
    TEST_KEYRING,
    TEST_TAG,
    ContainerError,
    remove,
    run,
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
API_DIR = REPO / "apps" / "api"
CHECK_NO_GALLERY = REPO / "apps" / "web" / "scripts" / "check-no-gallery.mjs"

PROD_TAG = "open-door:prod"
CONTAINER = "open-door-image-check"
CONTAINER_UID = 10001
HOST_PORT = 8300
FORGED_CLIENT = "203.0.113.9"
# The requests the running check makes that the access log keeps (not the health check): the page,
# the deep link, an asset, a missing asset, and the forged one.
LOGGED_REQUESTS_MINIMUM = 5

EXPECTED_ENTRYPOINT = ["/app/entrypoint.sh"]
# The health check calls the live route on the port the entrypoint listens on (PORT, else 8000).
HEALTH_PATH = "/api/v1/health/live"
# The security headers every response carries, and the values the spec fixes.
EXPECTED_HEADERS = {
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "cross-origin-opener-policy": "same-origin",
}
NONCE_META = re.compile(r'<meta name="csp-nonce" content="([^"]+)"')
# The access log is JSON lines, so the request's quotes arrive escaped: `1.2.3.4:5 - \"GET / ...`.
CLIENT_IN_ACCESS_LOG = re.compile(r'(\d+\.\d+\.\d+\.\d+):\d+ - \\?"(?:GET|HEAD|POST)')


CheckError = ContainerError


# --- Judgment: plain functions on what was seen ------------------------------------------------


def emsign_roots_in(names: list[str]) -> list[str]:
    """The certificate file names that are emSign roots."""
    return sorted(name for name in names if "emsign" in name.lower())


def problems_in_user(config_user: str, whoami_uid: int) -> list[str]:
    problems = []
    if config_user != f"{CONTAINER_UID}:{CONTAINER_UID}":
        problems.append(f"the image's USER is {config_user!r}, not {CONTAINER_UID}:{CONTAINER_UID}")
    if whoami_uid == 0:
        problems.append("the image runs as root")
    return problems


def problems_in_files(found: list[str]) -> list[str]:
    """Anything a secret or a test could be hiding in."""
    return [f"the image holds {path}" for path in sorted(found)]


def problems_in_config(
    entrypoint: list[str] | None, health_test: list[str] | None, env: list[str]
) -> list[str]:
    problems = []
    if entrypoint != EXPECTED_ENTRYPOINT:
        problems.append(f"the entrypoint is {entrypoint}, not {EXPECTED_ENTRYPOINT}")
    command = " ".join(health_test or [])
    if HEALTH_PATH not in command or "PORT" not in command or "HOST" not in command:
        problems.append(
            f"the health check does not call {HEALTH_PATH} on the HOST and PORT it listens on"
        )
    if "APP_ENV=production" not in env:
        problems.append("the image does not set APP_ENV=production")
    problems.extend(
        f"the image sets {entry.split('=')[0]}"
        for entry in env
        if "KEYRING" in entry.upper() or "API_KEY" in entry.upper() or "DATABASE_URL" in entry
    )
    return problems


def problems_in_page(headers: Mapping[str, str], body: str, where: str) -> list[str]:
    """One HTML response: the security headers, no-store, and a CSP that names the page's nonce."""
    problems = problems_in_headers(headers, where)
    if headers.get("cache-control") != "no-store":
        problems.append(f"{where}: Cache-Control is {headers.get('cache-control')!r}, not no-store")
    match = NONCE_META.search(body)
    csp = headers.get("content-security-policy", "")
    if match is None:
        problems.append(f"{where}: the page has no nonce meta tag")
    elif f"'nonce-{match.group(1)}'" not in csp:
        problems.append(f"{where}: the CSP does not carry the page's nonce")
    if "frame-ancestors 'none'" not in csp:
        problems.append(f"{where}: the CSP lacks frame-ancestors 'none'")
    return problems


def problems_in_headers(headers: Mapping[str, str], where: str) -> list[str]:
    return [
        f"{where}: {name} is {headers.get(name)!r}, not {value!r}"
        for name, value in EXPECTED_HEADERS.items()
        if headers.get(name) != value
    ]


def problems_in_nonces(first: str | None, second: str | None) -> list[str]:
    if not first or not second:
        return ["a page had no nonce"]
    if first == second:
        return ["two pages carried the same nonce"]
    return []


def client_addresses_in(log: str) -> list[str]:
    """The client addresses uvicorn's access log shows."""
    return CLIENT_IN_ACCESS_LOG.findall(log)


def problems_in_forwarding(untrusted_log: str, trusted_log: str, peer: str | None) -> list[str]:
    """With no trusted proxy the forged address must not appear; from the one named it must."""
    problems = []
    if FORGED_CLIENT in client_addresses_in(untrusted_log):
        problems.append("a forged X-Forwarded-For was trusted with FORWARDED_ALLOW_IPS empty")
    if len(client_addresses_in(untrusted_log)) < LOGGED_REQUESTS_MINIMUM:
        problems.append("the empty-trust run did not log every request, so it proved nothing")
    if peer is None:
        problems.append("could not tell which address the requests came from")
    elif FORGED_CLIENT not in client_addresses_in(trusted_log):
        problems.append(
            "the control failed: X-Forwarded-For was not trusted from the one address named"
        )
    return problems


# --- Docker -------------------------------------------------------------------------------------


def build(tag: str, *extra: str) -> None:
    print(f"building {tag} ...")
    run("docker", "build", "-t", tag, *extra, str(REPO), timeout=1800)


def in_image(tag: str, script: str, *, user: str | None = None) -> str:
    args = ["docker", "run", "--rm", "--entrypoint", "sh"]
    if user:
        args += ["--user", user]
    return run(*args, tag, "-c", script).stdout


def inspect(tag: str, template: str) -> str:
    return run("docker", "inspect", "--format", template, tag).stdout.strip()


def extract_dist(tag: str, into: Path) -> Path:
    created = run("docker", "create", tag).stdout.strip()
    try:
        run("docker", "cp", f"{created}:/app/web-dist/.", str(into))
    finally:
        run("docker", "rm", "-f", created, check=False)
    return into


def no_gallery_ok(dist: Path) -> bool:
    result = run("node", str(CHECK_NO_GALLERY), str(dist), check=False)
    return result.returncode == 0


# --- The checks ---------------------------------------------------------------------------------


def check_contents(tag: str) -> list[str]:
    problems = problems_in_user(
        inspect(tag, "{{.Config.User}}"), int(in_image(tag, "id -u").strip())
    )
    found = in_image(
        tag,
        "find / -xdev \\( -name .env -o -name '.env.*' -o -name .keys -o -name keyring"
        " -o -name '.*_history' -o -name 'test_*.py' -o -name conftest.py -o -name tests \\)"
        " -not -path '*/site-packages/*' -not -path '/usr/*' -not -path '/proc/*' 2>/dev/null",
        user="root",
    ).split()
    problems += problems_in_files(found)
    fake_key = in_image(
        tag, f"grep -rl --exclude-dir=proc --exclude-dir=sys '{TEST_KEYRING}' /app || true"
    ).split()
    problems += [f"the test keyring is in {path}" for path in fake_key]
    entrypoint = inspect(tag, "{{json .Config.Entrypoint}}")
    health = inspect(tag, "{{json .Config.Healthcheck.Test}}")
    env = inspect(tag, "{{json .Config.Env}}")
    problems += problems_in_config(json.loads(entrypoint), json.loads(health), json.loads(env))
    zone = in_image(
        tag, "python -c \"import zoneinfo; print(zoneinfo.ZoneInfo('America/Denver'))\""
    ).strip()
    if zone != "America/Denver":
        problems.append("zoneinfo cannot load America/Denver")
    certs = in_image(tag, "ls /usr/share/ca-certificates/mozilla /etc/ssl/certs").split()
    roots = emsign_roots_in(certs)
    problems += [f"the CA store holds {name}" for name in roots]
    if not any(name.endswith(".pem") or name.endswith(".crt") for name in certs):
        problems.append("the CA store is empty, so the emSign check proved nothing")
    return problems


def check_gallery() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as prod_dir, tempfile.TemporaryDirectory() as test_dir:
        prod = extract_dist(PROD_TAG, Path(prod_dir))
        test = extract_dist(TEST_TAG, Path(test_dir))
        if not no_gallery_ok(prod):
            problems.append("the production image's web app contains the component gallery")
        if no_gallery_ok(test):
            problems.append("the test image has no gallery, so the gallery check proved nothing")
    return problems


def start_container(name: str, env: dict[str, str]) -> None:
    remove(name)
    run(*container.run_args(name, env, port=HOST_PORT, detach=True), env=env)


def wait_until_up(base: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base}/api/v1/health/live", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise CheckError("the container did not answer the live health check within 60 seconds")


def container_env(forwarded: str) -> dict[str, str]:
    return container.api_env(
        origin=f"http://127.0.0.1:{HOST_PORT}", port=HOST_PORT, forwarded=forwarded
    )


def base_url() -> str:
    return f"http://127.0.0.1:{HOST_PORT}"


def check_running() -> list[str]:
    problems: list[str] = []
    base = base_url()
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", HOST_PORT)) == 0:
            return [f"something already answers on 127.0.0.1:{HOST_PORT}; stop it first"]
    try:
        start_container(CONTAINER, container_env(forwarded=""))
        wait_until_up(base)
        lower = {"accept": "text/html"}
        with httpx.Client(base_url=base, timeout=10) as client:
            home = client.get("/", headers=lower)
            deep = client.get("/ask", headers=lower)
            problems += problems_in_page(home.headers, home.text, "/")
            problems += problems_in_page(deep.headers, deep.text, "/ask")
            if home.status_code != 200 or deep.status_code != 200:
                problems.append(f"/ answered {home.status_code} and /ask {deep.status_code}")
            first = NONCE_META.search(home.text)
            second = NONCE_META.search(deep.text)
            problems += problems_in_nonces(
                first.group(1) if first else None, second.group(1) if second else None
            )
            asset_path = re.search(r'src="(/assets/[^"]+\.js)"', home.text)
            if asset_path is None:
                problems.append("the page names no script under /assets/")
            else:
                asset = client.get(asset_path.group(1))
                problems += problems_in_headers(asset.headers, asset_path.group(1))
                if "immutable" not in asset.headers.get("cache-control", ""):
                    problems.append("an asset is not served as immutable")
                if "content-security-policy" in asset.headers:
                    problems.append("an asset carries a CSP")
                if client.get("/assets/missing.js").status_code != 404:
                    problems.append("a missing asset did not answer 404")
            live = client.get("/api/v1/health/live")
            problems += problems_in_headers(live.headers, "/api/v1/health/live")
            if live.headers.get("cache-control") != "no-store" or live.status_code != 200:
                problems.append("the live health check is not a 200 with no-store")
            # Not a health path: the access log leaves those out.
            client.get("/", headers={"X-Forwarded-For": FORGED_CLIENT})
        time.sleep(1)  # let the access log line reach `docker logs`, as the trusted run does
        logs = run("docker", "logs", CONTAINER)
        untrusted_log = logs.stdout + logs.stderr
        peer = next(iter(client_addresses_in(untrusted_log)), None)
        trusted_log = ""
        if peer:
            remove(CONTAINER)
            start_container(CONTAINER, container_env(forwarded=peer))
            wait_until_up(base)
            httpx.get(f"{base}/", headers={"X-Forwarded-For": FORGED_CLIENT}, timeout=5)
            time.sleep(1)  # let the access log line reach `docker logs`
            logs = run("docker", "logs", CONTAINER)
            trusted_log = logs.stdout + logs.stderr
        problems += problems_in_forwarding(untrusted_log, trusted_log, peer)
    finally:
        remove(CONTAINER)
    return problems


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    if shutil.which("docker") is None or shutil.which("node") is None:
        print("image-check needs docker and node on the PATH.")
        return 2
    problems: list[str] = []
    try:
        if os.environ.get("IMAGE_CHECK_NO_BUILD") == "1":
            print("using the images already built (IMAGE_CHECK_NO_BUILD=1) ...")
        else:
            build(PROD_TAG)
            build(TEST_TAG, "--build-arg", "GALLERY=true")
        for tag in (PROD_TAG, TEST_TAG):
            print(f"inspecting {tag} ...")
            problems += [f"{tag}: {problem}" for problem in check_contents(tag)]
        print("checking the gallery ...")
        problems += check_gallery()
        print("starting the test image ...")
        problems += check_running()
    except CheckError as error:
        problems.append(str(error))
    if problems:
        print("\nimage-check FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nimage-check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
