"""The security headers: on every response, with the CSP only on the page."""

from collections.abc import AsyncIterator, Iterator, Mapping

import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, StreamingResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.security_headers import (
    COOP,
    HSTS,
    PERMISSIONS_POLICY,
    SecurityHeadersMiddleware,
    content_security_policy,
)
from app.main import create_app
from tests.conftest import TEST_KEYRING, UNREACHABLE_DATABASE_URL

# The spec's text (docs/specs/2026-11-05-phase-8-hardening-and-deploy-readiness.md), with the
# nonce in place. Written out here, apart from the constant, so a change to either must be seen.
SPEC_CSP = (
    "default-src 'self'; script-src 'self' https://challenges.cloudflare.com; "
    "style-src 'self' 'nonce-NONCE'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; frame-src https://challenges.cloudflare.com; media-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


def test_the_csp_equals_the_specs_text() -> None:
    assert content_security_policy("NONCE") == SPEC_CSP


def test_the_other_headers_have_the_specified_values() -> None:
    assert HSTS == "max-age=31536000; includeSubDomains"
    assert COOP == "same-origin"
    assert PERMISSIONS_POLICY == "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


async def answer(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


async def stream_events(request: Request) -> StreamingResponse:
    async def events() -> AsyncIterator[bytes]:
        yield b"data: one\n\n"
        yield b"data: two\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = Starlette(routes=[Route("/x", answer), Route("/stream", stream_events)])
    app.add_middleware(SecurityHeadersMiddleware)
    with TestClient(app) as test_client:
        yield test_client


def assert_has_the_headers(headers: Mapping[str, str]) -> None:
    got = {k.lower(): v for k, v in headers.items()}
    assert got["strict-transport-security"] == HSTS
    assert got["x-content-type-options"] == "nosniff"
    # Not `no-referrer`, which makes a browser send `Origin: null` on its own writes.
    assert got["referrer-policy"] == "same-origin"
    assert got["permissions-policy"] == PERMISSIONS_POLICY
    assert got["cross-origin-opener-policy"] == COOP
    assert "content-security-policy" not in got


def test_every_response_carries_the_headers_and_no_csp(client: TestClient) -> None:
    assert_has_the_headers(client.get("/x").headers)
    assert_has_the_headers(client.get("/stream").headers)
    assert_has_the_headers(client.get("/missing").headers)


async def test_it_never_buffers_a_stream() -> None:
    """Pure ASGI: each body message is forwarded as it arrives, before the next is produced."""
    events: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        events.append("produced one")
        await send({"type": "http.response.body", "body": b"one", "more_body": True})
        events.append("produced two")
        await send({"type": "http.response.body", "body": b"two", "more_body": False})

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        events.append(f"sent {message['type']}")

    scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    app: ASGIApp = SecurityHeadersMiddleware(inner)
    await app(scope, receive, send)

    assert events == [
        "sent http.response.start",
        "produced one",
        "sent http.response.body",
        "produced two",
        "sent http.response.body",
    ]


def make_app(**overrides: object) -> TestClient:
    fields: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "database_url": UNREACHABLE_DATABASE_URL,
        "app_origin": "http://localhost:5173",
        "encryption_keyring_file": None,
        "encryption_keyring": TEST_KEYRING,
    }
    fields.update(overrides)
    return TestClient(create_app(Settings(**fields)))  # type: ignore[arg-type]


def test_api_responses_carry_the_headers_and_keep_no_store() -> None:
    with make_app() as client:
        response = client.get("/api/v1/nothing-here")
    assert response.status_code == 404
    assert_has_the_headers(response.headers)
    assert response.headers["cache-control"] == "no-store"


def test_a_same_origin_refusal_carries_the_headers() -> None:
    with make_app() as client:
        response = client.post("/api/v1/anything", headers={"Origin": "http://evil.example"})
    assert response.status_code == 403
    assert_has_the_headers(response.headers)
    assert response.headers["cache-control"] == "no-store"


def test_an_oversized_body_refusal_carries_the_headers() -> None:
    with make_app() as client:
        response = client.post(
            "/api/v1/anything",
            content=b"x" * (64 * 1024 + 1),
            headers={"Origin": "http://localhost:5173"},
        )
    assert response.status_code == 413
    assert_has_the_headers(response.headers)
    assert response.headers["cache-control"] == "no-store"


def test_an_unhandled_error_carries_the_headers() -> None:
    # Starlette sends the 500 from outside every middleware, so the handler sets them itself.
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_url=UNREACHABLE_DATABASE_URL,
            app_origin="http://localhost:5173",
            encryption_keyring_file=None,
            encryption_keyring=TEST_KEYRING,
        )
    )

    @app.get("/api/v1/boom")
    async def boom() -> None:
        msg = "boom"
        raise RuntimeError(msg)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/boom")
    assert response.status_code == 500
    assert_has_the_headers(response.headers)
    assert response.headers["cache-control"] == "no-store"
