import re
from collections.abc import AsyncIterator, Iterator

import pytest
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import PlainTextResponse, StreamingResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_id import RequestIdMiddleware, request_id_var

GENERATED_ID = re.compile(r"[0-9a-f]{32}")


async def echo_request_id(request: Request) -> PlainTextResponse:
    """Report the ID the way the rest of the app sees it: the context variable and request state."""
    return PlainTextResponse(f"{request_id_var.get()}|{request.state.request_id}")


async def stream_events(request: Request) -> StreamingResponse:
    async def events() -> AsyncIterator[bytes]:
        yield b"data: one\n\n"
        yield b"data: two\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


async def drive(app: ASGIApp) -> list[Message]:
    """Call the middleware directly, in this task's context, and collect what it sends."""
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    await RequestIdMiddleware(app)(scope, receive, send)
    return sent


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = Starlette(routes=[Route("/", echo_request_id), Route("/stream", stream_events)])
    app.add_middleware(RequestIdMiddleware)
    with TestClient(app) as test_client:
        yield test_client


def test_every_response_carries_a_generated_request_id(client: TestClient) -> None:
    response = client.get("/")

    request_id = response.headers["X-Request-ID"]
    assert GENERATED_ID.fullmatch(request_id)
    assert response.text == f"{request_id}|{request_id}"


def test_a_well_formed_incoming_request_id_is_reused(client: TestClient) -> None:
    response = client.get("/", headers={"X-Request-ID": "trace-42.a_b"})

    assert response.headers["X-Request-ID"] == "trace-42.a_b"
    assert response.text == "trace-42.a_b|trace-42.a_b"


def test_a_malformed_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/", headers={"X-Request-ID": "not allowed; x=1"})

    assert GENERATED_ID.fullmatch(response.headers["X-Request-ID"])


def test_an_over_long_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/", headers={"X-Request-ID": "x" * 129})

    assert GENERATED_ID.fullmatch(response.headers["X-Request-ID"])


def test_a_streamed_response_carries_the_request_id(client: TestClient) -> None:
    response = client.get("/stream")

    assert response.headers["content-type"].startswith("text/event-stream")
    assert GENERATED_ID.fullmatch(response.headers["X-Request-ID"])
    assert response.text == "data: one\n\ndata: two\n\n"


async def test_the_request_id_does_not_leak_past_the_request() -> None:
    await drive(PlainTextResponse("ok"))

    assert request_id_var.get() is None


async def test_a_response_start_without_a_headers_key_still_gets_the_request_id() -> None:
    # The ASGI spec makes "headers" optional on http.response.start.
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 204})
        await send({"type": "http.response.body", "body": b""})

    sent = await drive(app)

    assert GENERATED_ID.fullmatch(Headers(raw=sent[0]["headers"])["X-Request-ID"])
