from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.problems import install_problem_handlers
from app.core.request_id import RequestIdMiddleware


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_problem_handlers(app)

    @app.get("/items")
    async def list_items(limit: int) -> dict[str, int]:
        return {"limit": limit}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("database password is hunter2")

    @app.get("/managers-only")
    async def managers_only() -> None:
        raise HTTPException(403, detail="Managers only.")

    @app.get("/nonstandard-status")
    async def nonstandard_status() -> None:
        raise HTTPException(499)

    # The unhandled-error test needs the 500 response, not the exception re-raised.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_an_unknown_route_returns_problem_details(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "instance": "/does-not-exist",
        "requestId": response.headers["X-Request-ID"],
    }


def test_invalid_input_returns_problem_details_listing_each_error(client: TestClient) -> None:
    response = client.get("/items", params={"limit": "secret-value"})

    body = response.json()
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert body["detail"] == "The request did not pass validation."
    assert body["errors"][0]["loc"] == ["query", "limit"]
    assert "secret-value" not in response.text


def test_an_unhandled_error_hides_its_cause_and_keeps_the_request_id(client: TestClient) -> None:
    response = client.get("/boom")

    body = response.json()
    assert response.status_code == 500
    assert body["detail"] == "Something went wrong."
    assert "hunter2" not in response.text
    assert body["requestId"] == response.headers["X-Request-ID"]


def test_an_unhandled_error_is_logged_with_its_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    response = client.get("/boom")

    records = [record for record in caplog.records if record.name == "app.core.problems"]
    assert [record.__dict__.get("request_id") for record in records] == [
        response.headers["X-Request-ID"]
    ]


def test_a_method_not_allowed_response_keeps_its_allow_header(client: TestClient) -> None:
    response = client.post("/items")

    assert response.status_code == 405
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["allow"] == "GET"


def test_a_custom_error_detail_passes_through(client: TestClient) -> None:
    response = client.get("/managers-only")

    assert response.status_code == 403
    assert response.json()["detail"] == "Managers only."


def test_a_nonstandard_status_code_still_returns_problem_details(client: TestClient) -> None:
    response = client.get("/nonstandard-status")

    body = response.json()
    assert response.status_code == 499
    assert body["title"] == "Error"
    assert body["status"] == 499
    assert "detail" not in body
