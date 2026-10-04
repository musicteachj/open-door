from collections.abc import AsyncIterator, Iterator

import pytest
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import PlainTextResponse, StreamingResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.cache_control import NoStoreMiddleware


async def answer(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


async def answer_with_its_own_cache_control(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok", headers={"Cache-Control": "public, max-age=60"})


async def stream_events(request: Request) -> StreamingResponse:
    async def events() -> AsyncIterator[bytes]:
        yield b"data: one\n\n"
        yield b"data: two\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


async def drive(app: ASGIApp, path: str, sent: list[Message]) -> None:
    """Call the middleware directly and collect what it sends, as it sends it."""

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
    }
    await NoStoreMiddleware(app)(scope, receive, send)


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = Starlette(
        routes=[
            Route("/api/v1/thing", answer),
            Route("/api/v1/stream", stream_events),
            Route("/api/v1/cached", answer_with_its_own_cache_control),
            Route("/health", answer),
            Route("/apiary", answer),
        ]
    )
    app.add_middleware(NoStoreMiddleware)
    with TestClient(app) as test_client:
        yield test_client


def test_a_response_under_api_is_marked_no_store(client: TestClient) -> None:
    response = client.get("/api/v1/thing")

    assert response.headers.get_list("cache-control") == ["no-store"]


def test_a_response_under_api_behind_a_root_path_is_marked_no_store(client: TestClient) -> None:
    # As `uvicorn --root-path /od` builds it: scope["path"] keeps the prefix, and the router
    # strips it, so the middleware must judge the path the router matches.
    with TestClient(client.app, root_path="/od") as behind_root:
        under_api = behind_root.get("/od/api/v1/thing")
        elsewhere = behind_root.get("/od/health")

    assert (under_api.status_code, elsewhere.status_code) == (200, 200)
    assert under_api.headers.get_list("cache-control") == ["no-store"]
    assert "cache-control" not in elsewhere.headers


def test_a_404_under_api_is_marked_no_store_too(client: TestClient) -> None:
    response = client.get("/api/v1/nothing-here")

    assert response.status_code == 404
    assert response.headers.get_list("cache-control") == ["no-store"]


@pytest.mark.parametrize("path", ["/health", "/apiary"])
def test_a_path_outside_api_is_left_alone(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert "cache-control" not in response.headers


def test_a_cache_control_the_route_set_is_kept(client: TestClient) -> None:
    response = client.get("/api/v1/cached")

    assert response.headers.get_list("cache-control") == ["public, max-age=60"]


def test_a_streamed_response_still_streams_and_is_marked_no_store(client: TestClient) -> None:
    response = client.get("/api/v1/stream")

    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers.get_list("cache-control") == ["no-store"]
    assert response.text == "data: one\n\ndata: two\n\n"


async def test_the_middleware_passes_each_chunk_on_as_it_arrives() -> None:
    sent: list[Message] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"one", "more_body": True})
        # A middleware that buffered the response would have passed nothing on yet.
        assert [message["type"] for message in sent] == [
            "http.response.start",
            "http.response.body",
        ]
        await send({"type": "http.response.body", "body": b"two", "more_body": False})

    await drive(app, "/api/v1/stream", sent)

    assert Headers(raw=sent[0]["headers"])["cache-control"] == "no-store"
    assert [message.get("body") for message in sent[1:]] == [b"one", b"two"]


async def test_a_response_start_without_a_headers_key_still_gets_the_header() -> None:
    # The ASGI spec makes "headers" optional on http.response.start.
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 204})
        await send({"type": "http.response.body", "body": b""})

    sent: list[Message] = []
    await drive(app, "/api/v1/session", sent)

    assert Headers(raw=sent[0]["headers"])["cache-control"] == "no-store"


async def test_a_non_http_scope_passes_straight_through() -> None:
    seen: list[Scope] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope)

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        raise AssertionError("nothing should be sent")

    scope: Scope = {"type": "lifespan", "path": "/api/v1/thing"}
    await NoStoreMiddleware(app)(scope, receive, send)

    assert seen == [scope]
