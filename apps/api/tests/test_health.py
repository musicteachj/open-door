from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import __version__
from app.api.v1.health import DatabasePing, get_database_ping


def database_answers(answer: bool) -> DatabasePing:
    async def check() -> bool:
        return answer

    return check


def test_health_is_ok_when_the_database_answers(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_database_ping] = lambda: database_answers(True)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "version": __version__}


def test_health_is_degraded_when_the_database_is_down(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_database_ping] = lambda: database_answers(False)

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "database": "unavailable",
        "version": __version__,
    }


def test_the_app_serves_problem_details_and_request_ids(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["requestId"] == response.headers["X-Request-ID"]


def test_health_checks_the_database_through_the_real_engine(client: TestClient) -> None:
    # No override: the lifespan's engine points at port 1, which refuses at once.
    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"
