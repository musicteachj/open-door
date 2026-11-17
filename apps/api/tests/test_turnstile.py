"""Turnstile verification, with siteverify stubbed by httpx.MockTransport. Nothing here calls
Cloudflare."""

import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import (
    TURNSTILE_ALREADY_SPENT_SECRET as ALREADY_SPENT_SECRET,
)
from app.core.config import (
    TURNSTILE_ALWAYS_FAIL_SECRET as ALWAYS_FAIL_SECRET,
)
from app.core.config import Settings
from app.modules.sandbox.turnstile import (
    DUMMY_TOKEN,
    SITEVERIFY_URL,
    CloudflareVerifier,
    TestKeyVerifier,
    Verdict,
    build_verifier,
)

SECRET = "0x4AAAAAAA-real-looking-secret"  # noqa: S105
ORIGIN = "https://open-door.example.org"
GOOD = {"success": True, "hostname": "open-door.example.org", "action": "start-sandbox"}


def verifier(handler: Callable[[httpx.Request], httpx.Response]) -> CloudflareVerifier:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return CloudflareVerifier(SECRET, ORIGIN, client)


def answering(body: Any, status: int = 200) -> CloudflareVerifier:
    return verifier(lambda _: httpx.Response(status, json=body))


async def test_a_good_answer_passes() -> None:
    assert await answering(GOOD).verify("tok", "203.0.113.5") is Verdict.PASSED


async def test_the_request_carries_the_secret_token_address_and_a_fresh_key() -> None:
    seen: list[dict[str, list[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == SITEVERIFY_URL
        seen.append(parse_qs(request.content.decode()))
        return httpx.Response(200, json=GOOD)

    check = verifier(handler)
    await check.verify("tok-1", "203.0.113.5")
    await check.verify("tok-2", None)
    first, second = seen
    assert first["secret"] == [SECRET]
    assert first["response"] == ["tok-1"]
    assert first["remoteip"] == ["203.0.113.5"]
    assert "remoteip" not in second
    assert first["idempotency_key"] != second["idempotency_key"]


async def test_no_token_fails_without_a_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no call expected")

    assert await verifier(handler).verify("", "203.0.113.5") is Verdict.FAILED


@pytest.mark.parametrize(
    "body",
    [
        {"success": False, "error-codes": ["invalid-input-response"]},
        {"success": False, "error-codes": ["timeout-or-duplicate"]},
        {**GOOD, "hostname": "evil.example.com"},
        {**GOOD, "action": "login"},
        {key: value for key, value in GOOD.items() if key != "action"},
        {"success": "true", "hostname": GOOD["hostname"], "action": GOOD["action"]},
        {},
    ],
)
async def test_everything_else_fails(body: dict[str, Any]) -> None:
    assert await answering(body).verify("tok", None) is Verdict.FAILED


@pytest.mark.parametrize(
    "check",
    [
        answering({"success": False, "error-codes": ["internal-error"]}),
        answering(GOOD, status=500),
        answering(GOOD, status=403),
        verifier(lambda _: httpx.Response(200, content=b"<html>not json")),
        answering(["a", "list"]),
    ],
)
async def test_an_unusable_answer_is_unavailable(check: CloudflareVerifier) -> None:
    assert await check.verify("tok", None) is Verdict.UNAVAILABLE


@pytest.mark.parametrize("code", ["invalid-input-secret", "missing-input-secret", "bad-request"])
async def test_our_own_misconfiguration_is_unavailable_and_logged_without_secrets(
    code: str, caplog: pytest.LogCaptureFixture
) -> None:
    # These codes mean the app's secret or request is wrong, not that the visitor is a bot.
    body = {"success": False, "error-codes": [code]}
    with caplog.at_level(logging.ERROR, logger="app.modules.sandbox.turnstile"):
        verdict = await answering(body).verify("visitor-token-123", "203.0.113.5")
    assert verdict is Verdict.UNAVAILABLE
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert code in errors[0].getMessage()
    assert SECRET not in caplog.text
    assert "visitor-token-123" not in caplog.text


async def test_the_verifier_keeps_one_client_for_its_life_and_closes_it() -> None:
    check = CloudflareVerifier(SECRET, ORIGIN)
    client = check._client
    assert not client.is_closed
    await check.aclose()
    assert client.is_closed


async def test_the_injected_client_is_the_one_used() -> None:
    clients_seen: list[httpx.AsyncClient] = []
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=GOOD))
    )
    check = CloudflareVerifier(SECRET, ORIGIN, client)
    await check.verify("a", None)
    await check.verify("b", None)
    clients_seen.append(check._client)
    assert clients_seen == [client]
    await check.aclose()


@pytest.mark.parametrize("error", [httpx.ConnectTimeout("t"), httpx.ConnectError("c")])
async def test_a_timeout_or_connection_error_is_unavailable(error: Exception) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    assert await verifier(handler).verify("tok", None) is Verdict.UNAVAILABLE


async def test_the_pass_secret_accepts_only_the_dummy_token() -> None:
    check = TestKeyVerifier("1x0000000000000000000000000000000AA")
    assert await check.verify(DUMMY_TOKEN, None) is Verdict.PASSED
    assert await check.verify("anything-else", None) is Verdict.FAILED
    assert await check.verify("", None) is Verdict.FAILED


@pytest.mark.parametrize("secret", [ALWAYS_FAIL_SECRET, ALREADY_SPENT_SECRET])
async def test_the_other_test_secrets_always_fail(secret: str) -> None:
    assert await TestKeyVerifier(secret).verify(DUMMY_TOKEN, None) is Verdict.FAILED


def settings_with(secret: str | None, **extra: Any) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost:5433/db",
        # Outside production the pair is set together or not at all.
        turnstile_site_key="" if secret is None else "1x00000000000000000000AA",
        turnstile_secret_key=None if secret is None else SecretStr(secret),
        **extra,
    )


@pytest.mark.parametrize(
    "secret",
    [None, "1x0000000000000000000000000000000AA", ALWAYS_FAIL_SECRET, ALREADY_SPENT_SECRET],
)
def test_the_factory_picks_the_test_verifier_for_test_secrets(secret: str | None) -> None:
    assert isinstance(build_verifier(settings_with(secret)), TestKeyVerifier)


def test_the_factory_picks_cloudflare_for_a_real_secret() -> None:
    assert isinstance(build_verifier(settings_with(SECRET)), CloudflareVerifier)
