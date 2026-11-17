"""Cloudflare Turnstile: is the visitor starting a sandbox a person? (ADR 0021)

`verify` answers `passed`, `failed`, or `unavailable`. The route turns `failed` into a 403 and
`unavailable` into a 503, so the check fails closed: if Cloudflare can't be reached, nobody starts.

A token passes only if Cloudflare says it succeeded, was issued for this app's host, and was issued
for the `start-sandbox` action, so a token from some other site, or for some other widget, is
refused.

Cloudflare's test secrets are answered here, without any network call: their real answers carry the
hostname `example.com` and no action, which our checks would always refuse, and tests, CI, and the
local production run must not reach Cloudflare. `TestKeyVerifier` mirrors the documented behavior.
Production never gets it with a real key (config refuses test keys there unless the origin is a
loopback one).
"""

import logging
from enum import StrEnum
from typing import Any, Final, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.core.config import (
    TURNSTILE_PASS_SECRET,
    TURNSTILE_TEST_SECRETS,
    Settings,
)

logger = logging.getLogger(__name__)

SITEVERIFY_URL: Final = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
SITEVERIFY_TIMEOUT_SECONDS: Final = 5.0
ACTION: Final = "start-sandbox"

# Source: Turnstile "Testing", https://developers.cloudflare.com/turnstile/troubleshooting/testing/,
# read from developers.cloudflare.com on 2026-11-11. A test secret accepts only this dummy token;
# the secret 1x...AA passes it, 2x...AA always fails, 3x...AA answers `timeout-or-duplicate`.
DUMMY_TOKEN: Final = "XXXX.DUMMY.TOKEN.XXXX"  # noqa: S105  # A public test value.

INTERNAL_ERROR: Final = "internal-error"
# Codes that say our own secret or request is wrong, not that the visitor is a bot. They are the
# app's fault, so nobody can start until it is fixed: unavailable, with an error in the log.
MISCONFIGURED_CODES: Final = frozenset(
    {"invalid-input-secret", "missing-input-secret", "bad-request"}
)


class Verdict(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class TurnstileVerifier(Protocol):
    async def verify(self, token: str, remote_ip: str | None) -> Verdict: ...


class CloudflareVerifier:
    """Asks Cloudflare's siteverify endpoint with one client for its whole life (a connection
    pool, so a start does not pay for a new TLS handshake). `client` is injectable for a mock
    transport. The app's lifespan calls `aclose` at shutdown."""

    def __init__(self, secret: str, app_origin: str, client: httpx.AsyncClient | None = None):
        self._secret = secret
        self._hostname = urlsplit(app_origin).hostname
        self._client = client if client is not None else httpx.AsyncClient()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def verify(self, token: str, remote_ip: str | None) -> Verdict:
        if not token:
            return Verdict.FAILED
        form = {"secret": self._secret, "response": token, "idempotency_key": str(uuid4())}
        if remote_ip:
            form["remoteip"] = remote_ip
        try:
            response = await self._client.post(
                SITEVERIFY_URL, data=form, timeout=SITEVERIFY_TIMEOUT_SECONDS
            )
        except httpx.HTTPError as error:
            logger.warning("Turnstile siteverify unreachable: %s", type(error).__name__)
            return Verdict.UNAVAILABLE
        if response.status_code != httpx.codes.OK:
            logger.warning("Turnstile siteverify answered %s", response.status_code)
            return Verdict.UNAVAILABLE
        try:
            body: Any = response.json()
        except ValueError:
            logger.warning("Turnstile siteverify answered unreadable JSON")
            return Verdict.UNAVAILABLE
        if not isinstance(body, dict):
            return Verdict.UNAVAILABLE
        codes = body.get("error-codes")
        if isinstance(codes, list):
            if INTERNAL_ERROR in codes:
                return Verdict.UNAVAILABLE
            misconfigured = sorted(MISCONFIGURED_CODES.intersection(codes))
            if misconfigured:
                # Never the secret or the token: the code names the problem.
                logger.error(
                    "Turnstile siteverify refused our request (%s): check TURNSTILE_SECRET_KEY",
                    ", ".join(misconfigured),
                )
                return Verdict.UNAVAILABLE
        if (
            body.get("success") is True
            and body.get("hostname") == self._hostname
            and body.get("action") == ACTION
        ):
            return Verdict.PASSED
        return Verdict.FAILED


class TestKeyVerifier:
    """Answers for Cloudflare's test secrets without a network call."""

    __test__ = False  # Not a pytest class, whatever its name starts with.

    def __init__(self, secret: str) -> None:
        self._secret = secret

    async def verify(self, token: str, remote_ip: str | None) -> Verdict:
        if self._secret == TURNSTILE_PASS_SECRET and token == DUMMY_TOKEN:
            return Verdict.PASSED
        return Verdict.FAILED


def build_verifier(settings: Settings) -> TurnstileVerifier:
    """The verifier the settings call for: the local one for a Cloudflare test secret."""
    secret = settings.turnstile_secret_key
    assert secret is not None  # noqa: S101  # Settings fills it outside production and requires it in it.
    value = secret.get_secret_value()
    if value in TURNSTILE_TEST_SECRETS:
        return TestKeyVerifier(value)
    return CloudflareVerifier(value, settings.app_origin)
