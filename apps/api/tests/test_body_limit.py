"""The 64 KiB body cap (by Content-Length and by counting a stream) and the schema ceilings."""

import json
from typing import Any

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.types import Message, Receive, Scope, Send

from app.core.body_limit import MAX_BODY_BYTES, BodyLimitMiddleware
from app.core.problems import install_problem_handlers
from app.core.request_id import RequestIdMiddleware
from app.modules.assistant.schemas import ConfirmIn, TurnIn
from app.modules.cases.api_schemas import OpenCaseBody

JSON = {"Content-Type": "application/json"}


def small_app() -> tuple[FastAPI, list[int]]:
    """An app with the real middleware that reads each body fully and reports how much it read."""
    app = FastAPI()
    read: list[int] = []

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        body = await request.body()
        read.append(len(body))
        return {"bytes": len(body)}

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(RequestIdMiddleware)
    install_problem_handlers(app)
    return app, read


def client_for(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_a_body_over_the_cap_by_content_length_is_refused_unread() -> None:
    app, read = small_app()
    async with client_for(app) as client:
        response = await client.post("/echo", content=b"x" * (MAX_BODY_BYTES + 1), headers=JSON)

    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == 413
    assert response.json()["requestId"] == response.headers["x-request-id"]
    assert read == []  # the route never ran


async def test_the_content_length_check_never_reads_the_body() -> None:
    sent: list[Message] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        raise AssertionError("the app ran")

    async def receive() -> Message:
        raise AssertionError("the body was read")

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/echo",
        "root_path": "",
        "query_string": b"",
        "headers": [(b"content-length", str(MAX_BODY_BYTES + 1).encode())],
    }
    await BodyLimitMiddleware(inner)(scope, receive, send)

    assert sent[0]["status"] == 413


async def test_a_body_at_the_cap_passes() -> None:
    app, read = small_app()
    async with client_for(app) as client:
        response = await client.post("/echo", content=b"x" * MAX_BODY_BYTES, headers=JSON)

    assert response.status_code == 200
    assert read == [MAX_BODY_BYTES]


async def test_a_chunked_body_that_crosses_the_cap_is_cut_with_413() -> None:
    app, read = small_app()
    chunk = b"x" * 10_000

    async def chunks() -> Any:
        for _ in range(20):  # 200,000 bytes, with no Content-Length
            yield chunk

    async with client_for(app) as client:
        response = await client.post("/echo", content=chunks(), headers=JSON)

    assert response.status_code == 413
    assert response.json()["status"] == 413
    assert read == []


async def test_a_streamed_body_under_the_cap_passes() -> None:
    app, read = small_app()

    async def chunks() -> Any:
        for _ in range(5):
            yield b"x" * 10_000

    async with client_for(app) as client:
        response = await client.post("/echo", content=chunks(), headers=JSON)

    assert response.status_code == 200
    assert read == [50_000]


async def test_a_lying_content_length_does_not_get_past_the_count() -> None:
    """A small declared length with a big body: the count, not the header, decides."""
    calls: list[Message] = []
    sent: list[Message] = []
    big = {"type": "http.request", "body": b"x" * (MAX_BODY_BYTES + 1), "more_body": False}

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        message = await receive()
        calls.append(message)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive() -> Message:
        return big

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/echo",
        "root_path": "",
        "query_string": b"",
        "headers": [(b"content-length", b"10")],
    }
    await BodyLimitMiddleware(inner)(scope, receive, send)

    assert sent[0]["status"] == 413
    assert all(
        message["type"] != "http.response.body" or message["body"] != b"ok" for message in sent
    )


async def test_a_get_is_untouched() -> None:
    app, _ = small_app()
    async with client_for(app) as client:
        response = await client.get("/ping")

    assert response.status_code == 200


def test_the_largest_body_the_schemas_allow_fits_under_the_cap() -> None:
    """Case words at the ceiling, in four-byte characters, as a browser's JSON.stringify sends
    them (not escaped as surrogate pairs)."""
    words = "\U0001f600" * 8_000
    body = json.dumps(
        {
            "submissionId": "00000000-0000-0000-0000-000000000000",
            "category": "other",
            "text": words,
            "turnId": None,
        },
        ensure_ascii=False,
    ).encode()

    assert len(body) < MAX_BODY_BYTES
    assert len(body) > 32_000
    OpenCaseBody.model_validate_json(body)


@pytest.mark.parametrize(
    ("model", "field", "ceiling"),
    [(TurnIn, "question", 4_000), (OpenCaseBody, "text", 8_000), (ConfirmIn, "note", 600)],
)
def test_the_early_reject_ceilings_are_twice_the_real_limits(
    model: Any, field: str, ceiling: int
) -> None:
    metadata = model.model_fields[field].metadata
    limits = [m.max_length for m in metadata if hasattr(m, "max_length")]
    assert limits == [ceiling]


def test_the_real_app_refuses_an_oversized_body_with_the_problem_headers(
    client: Any,
) -> None:
    response = client.post(
        "/api/v1/sandboxes",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={**JSON, "Sec-Fetch-Site": "same-origin"},
    )

    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"] == "application/problem+json"


async def test_a_cut_after_the_response_started_sends_no_second_start() -> None:
    sent: list[Message] = []
    chunks = [
        {"type": "http.request", "body": b"x" * 40_000, "more_body": True},
        {"type": "http.request", "body": b"x" * 40_000, "more_body": True},
        {"type": "http.request", "body": b"", "more_body": False},
    ]

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        while (await receive())["type"] == "http.request":
            pass
        await send({"type": "http.response.body", "body": b"late"})

    async def receive() -> Message:
        return chunks.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/stream",
        "root_path": "",
        "query_string": b"",
        "headers": [],
    }
    await BodyLimitMiddleware(inner)(scope, receive, send)

    assert [m["type"] for m in sent] == ["http.response.start"]
    assert sent[0]["status"] == 200
