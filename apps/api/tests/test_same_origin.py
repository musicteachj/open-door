"""The same-origin check, on a small app with the real middleware and problem handlers."""

import json
import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.problems import install_problem_handlers
from app.core.request_id import RequestIdMiddleware
from app.modules.identity.same_origin import SameOriginMiddleware

APP_ORIGIN = "http://localhost:5173"
SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}
CROSS_SITE = {"Sec-Fetch-Site": "cross-site"}


async def mounted_asgi_app(scope: Scope, receive: Receive, send: Send) -> None:
    """A bare ASGI app, as one mounted under the API would be: it answers 200 to any method."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def send_raw(app: ASGIApp, method: str, path: str, headers: dict[str, str]) -> int:
    """Call an ASGI app directly and return the status code.

    The test client uppercases methods, but a server hands the app whatever the client sent.
    """
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "client": ("testclient", 50000),
        "server": ("testserver", 443),
        "headers": [(b"host", b"testserver")]
        + [(key.lower().encode(), value.encode()) for key, value in headers.items()],
    }
    statuses: list[int] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    await app(scope, receive, send)
    return statuses[0]


def build_app() -> FastAPI:
    app = FastAPI()
    # As in create_app: the request-ID middleware is added last, so it wraps this check.
    app.add_middleware(SameOriginMiddleware, app_origin=APP_ORIGIN)
    app.add_middleware(RequestIdMiddleware)
    install_problem_handlers(app)

    @app.get("/things")
    async def list_things() -> list[str]:
        return []

    @app.get("/api/things")
    async def list_api_things() -> list[str]:
        return []

    @app.post("/things")
    async def add_thing(thing: dict[str, str] | None = None) -> dict[str, str]:
        return thing or {}

    @app.delete("/things")
    async def clear_things() -> None:
        return None

    @app.api_route("/things", methods=["PURGE"])
    async def purge_things() -> None:
        return None

    app.mount("/mounted", mounted_asgi_app)
    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(build_app(), base_url="https://testserver") as test_client:
        yield test_client


@pytest.mark.parametrize(
    "headers",
    [
        SAME_ORIGIN,
        # Sec-Fetch-Site wins over Origin, which can then be anything.
        {**SAME_ORIGIN, "Origin": "https://elsewhere.example"},
        # Without Fetch Metadata, Origin must be the app's.
        {"Origin": APP_ORIGIN},
    ],
)
def test_a_request_from_the_app_passes(client: TestClient, headers: dict[str, str]) -> None:
    assert client.post("/things", json={"name": "lamp"}, headers=headers).status_code == 200
    assert client.delete("/things", headers=headers).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Sec-Fetch-Site": "none"},
        {"Sec-Fetch-Site": "cross-site", "Origin": APP_ORIGIN},
        {"Origin": "https://elsewhere.example"},
        {"Origin": "null"},
        # A trailing slash is a different origin.
        {"Origin": f"{APP_ORIGIN}/"},
        {},
    ],
)
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a_request_from_anywhere_else_is_refused(
    client: TestClient, method: str, headers: dict[str, str]
) -> None:
    response = client.request(method, "/things", headers=headers)

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Forbidden",
        "status": 403,
        "instance": "/things",
        "detail": "Requests that change data must come from the Open Door app, as JSON.",
        "requestId": response.headers["X-Request-ID"],
    }


@pytest.mark.parametrize(
    ("content_type", "status_code"),
    [
        ("application/json", 200),
        ("application/json; charset=utf-8", 200),
        ("text/plain", 403),
        ("application/x-www-form-urlencoded", 403),
        ("multipart/form-data; boundary=x", 403),
        (None, 403),
    ],
)
def test_a_body_must_be_json(
    client: TestClient, content_type: str | None, status_code: int
) -> None:
    headers = dict(SAME_ORIGIN)
    if content_type is not None:
        headers["Content-Type"] = content_type

    response = client.post("/things", content=b'{"name": "lamp"}', headers=headers)

    assert response.status_code == status_code


def test_reads_need_no_origin_headers(client: TestClient) -> None:
    assert client.get("/things").status_code == 200


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "TRACE"])
def test_a_read_of_the_api_from_another_site_is_refused(
    client: TestClient, method: str, site: str
) -> None:
    response = client.request(method, "/api/things", headers={"Sec-Fetch-Site": site})

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"


def test_a_read_of_the_api_behind_a_root_path_from_another_site_is_refused() -> None:
    # As `uvicorn --root-path /od` builds it: scope["path"] keeps the prefix, and the router
    # strips it, so the check must judge the path the router matches.
    with TestClient(build_app(), base_url="https://testserver", root_path="/od") as behind_root:
        routed = behind_root.get("/od/api/things", headers=SAME_ORIGIN)
        refused = behind_root.get("/od/api/things", headers=CROSS_SITE)

    assert routed.status_code == 200
    assert refused.status_code == 403


def test_a_refused_read_says_the_api_is_for_the_app(client: TestClient) -> None:
    response = client.get("/api/things", headers=CROSS_SITE)

    assert response.json() == {
        "type": "about:blank",
        "title": "Forbidden",
        "status": 403,
        "instance": "/api/things",
        "detail": "Requests to the API must come from the Open Door app.",
        "requestId": response.headers["X-Request-ID"],
    }


def test_a_refused_read_is_logged_as_a_security_event(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="app.security")

    response = client.get("/api/things", headers={"Sec-Fetch-Site": "same-site"})

    [record] = [record for record in caplog.records if record.name == "app.security"]
    assert record.getMessage() == "security.origin_rejected"
    assert record.__dict__["request_id"] == response.headers["X-Request-ID"]
    assert record.__dict__["fields"]["reason"] == "a read from another site"


@pytest.mark.parametrize(
    "headers",
    [
        SAME_ORIGIN,
        # A URL typed in the address bar, or a bookmark.
        {"Sec-Fetch-Site": "none"},
        # A script or an old browser sends no Fetch Metadata.
        {},
    ],
)
def test_a_read_of_the_api_from_the_app_a_typed_url_or_a_script_passes(
    client: TestClient, headers: dict[str, str]
) -> None:
    assert client.get("/api/things", headers=headers).status_code == 200


def test_a_refusal_is_logged_as_a_security_event(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="app.security")
    headers = {"Sec-Fetch-Site": "cross-site", "Cookie": "__Host-od_session=a-raw-session-token"}

    response = client.post("/things", json={}, headers=headers)

    [record] = [record for record in caplog.records if record.name == "app.security"]
    assert record.getMessage() == "security.origin_rejected"
    assert record.__dict__["request_id"] == response.headers["X-Request-ID"]
    fields = record.__dict__["fields"]
    assert fields["event"] == "security.origin_rejected"
    assert fields["reason"] == "Sec-Fetch-Site is not same-origin"
    assert fields["clientIp"] == "testclient"
    assert len(fields["tokenHashPrefix"]) == 8
    # No session lookup happens here, so the tenant and actor are unknown.
    assert (fields["tenantId"], fields["actorId"]) == (None, None)
    assert "a-raw-session-token" not in json.dumps(fields)


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "TRACE"])
def test_outside_the_api_the_safe_methods_skip_the_check(client: TestClient, method: str) -> None:
    # The route may answer 405 for a method it doesn't serve, but the check never refuses it.
    assert client.request(method, "/things", headers=CROSS_SITE).status_code != 403


def test_a_custom_method_gets_the_full_check(client: TestClient) -> None:
    # The check guards everything except the safe methods, so a verb it has never heard of, on a
    # route declared with it, is refused like any other.
    assert client.request("PURGE", "/things", headers=SAME_ORIGIN).status_code == 200

    response = client.request("PURGE", "/things", headers=CROSS_SITE)

    assert response.status_code == 403


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete", "get", "purge"])
async def test_a_lowercase_method_reaching_a_mounted_app_gets_the_full_check(
    client: TestClient, method: str
) -> None:
    app = client.app

    assert await send_raw(app, method, "/mounted/ping", SAME_ORIGIN) == 200
    assert await send_raw(app, method, "/mounted/ping", CROSS_SITE) == 403


async def test_a_lowercase_method_is_refused_without_any_origin_header(
    client: TestClient,
) -> None:
    assert await send_raw(client.app, "post", "/mounted/ping", {}) == 403


def test_a_chunked_body_must_be_json_too(client: TestClient) -> None:
    # Without a Content-Length, httpx sends the body chunked: only Transfer-Encoding shows it.
    headers = {**SAME_ORIGIN, "Content-Type": "text/plain"}

    response = client.post("/things", content=iter([b'{"name": "lamp"}']), headers=headers)

    assert "content-length" not in response.request.headers
    assert response.request.headers["transfer-encoding"] == "chunked"
    assert response.status_code == 403


@pytest.mark.parametrize(
    "origin",
    [
        "http://LOCALHOST:5173",
        "HTTP://localhost:5173",
        APP_ORIGIN.upper(),
    ],
)
def test_the_origin_must_match_exactly_including_case(client: TestClient, origin: str) -> None:
    # A browser sends its origin in lowercase, so only an exact copy of APP_ORIGIN is the app's.
    assert client.post("/things", json={}, headers={"Origin": APP_ORIGIN}).status_code == 200

    response = client.post("/things", json={}, headers={"Origin": origin})

    assert response.status_code == 403
