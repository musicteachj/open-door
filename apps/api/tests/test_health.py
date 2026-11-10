import asyncio
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app import __version__
from app.api.v1.health import (
    READINESS_PING_TIMEOUT_SECONDS,
    READINESS_WAIT_SECONDS,
    DatabasePing,
    ReadinessCache,
    get_database_ping,
)


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


def test_liveness_never_touches_the_database(app: FastAPI, client: TestClient) -> None:
    class NoDatabase:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"liveness touched the engine: {name}")

    real_engine = app.state.engine
    app.state.engine = NoDatabase()
    try:
        response = client.get("/api/v1/health/live")
    finally:
        app.state.engine = real_engine  # the lifespan disposes it on the way out

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
    assert response.headers["cache-control"] == "no-store"


def test_liveness_is_200_while_readiness_is_503_with_the_database_down(client: TestClient) -> None:
    # The lifespan's engine points at port 1, which refuses at once.
    assert client.get("/api/v1/health/live").status_code == 200
    assert client.get("/api/v1/health").status_code == 503


def test_readiness_sends_no_store(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_database_ping] = lambda: database_answers(True)

    assert client.get("/api/v1/health").headers["cache-control"] == "no-store"


def test_the_readiness_ping_is_bounded_at_two_seconds() -> None:
    from app.api.v1.health import READINESS_PING_TIMEOUT_SECONDS

    assert READINESS_PING_TIMEOUT_SECONDS == 2.0


async def test_the_readiness_result_is_cached_for_one_second() -> None:
    now = [100.0]
    calls = 0

    async def ping() -> bool:
        nonlocal calls
        calls += 1
        return calls == 1  # the first answer is up, any later one is down

    cache = ReadinessCache(ttl_seconds=1.0, clock=lambda: now[0])

    assert await cache.check(ping) is True
    now[0] += 0.9
    assert await cache.check(ping) is True  # still the first answer
    assert calls == 1
    now[0] += 0.2
    assert await cache.check(ping) is False  # past one second: asked again
    assert calls == 2


async def test_only_one_readiness_check_is_in_flight() -> None:
    calls = 0
    release = asyncio.Event()

    async def ping() -> bool:
        nonlocal calls
        calls += 1
        await release.wait()
        return True

    cache = ReadinessCache()
    waiting = [asyncio.create_task(cache.check(ping)) for _ in range(10)]
    await asyncio.sleep(0.05)
    release.set()

    assert await asyncio.gather(*waiting) == [True] * 10
    assert calls == 1


async def test_ten_requests_at_once_ask_the_database_once(app: FastAPI) -> None:
    calls = 0

    async def ping() -> bool:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.1)
        return True

    app.dependency_overrides[get_database_ping] = lambda: ping
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
        responses = await asyncio.gather(*(http.get("/api/v1/health") for _ in range(10)))

    assert [r.status_code for r in responses] == [200] * 10
    assert calls == 1


async def test_callers_behind_a_stalled_check_answer_unavailable_within_the_budget() -> None:
    calls = 0

    async def hung() -> bool:
        nonlocal calls
        calls += 1
        await asyncio.Event().wait()
        return True

    cache = ReadinessCache(wait_seconds=0.2)
    first = asyncio.create_task(cache.check(hung))
    await asyncio.sleep(0.02)
    started = time.monotonic()
    answers = await asyncio.gather(*(cache.check(hung) for _ in range(5)))
    waited = time.monotonic() - started
    first.cancel()

    assert answers == [False] * 5
    assert waited < 1.0
    assert calls == 1


async def test_callers_behind_a_stalled_check_get_the_last_answer_only_inside_the_window() -> None:
    now = [100.0]
    stall = False

    async def ping() -> bool:
        if stall:
            await asyncio.Event().wait()
        return True

    cache = ReadinessCache(ttl_seconds=1.0, clock=lambda: now[0], wait_seconds=0.1)
    assert await cache.check(ping) is True
    now[0] += 5  # the answer is stale, so the next caller asks again and stalls
    stall = True
    first = asyncio.create_task(cache.check(ping))
    await asyncio.sleep(0.02)

    assert await cache.check(ping) is False  # the last "ok" is 5 s old: not served
    first.cancel()


async def test_a_queued_caller_within_the_window_gets_the_last_answer() -> None:
    now = [100.0]
    stall = False

    async def ping() -> bool:
        if stall:
            await asyncio.Event().wait()
        return True

    cache = ReadinessCache(ttl_seconds=1.0, clock=lambda: now[0], wait_seconds=0.1)
    assert await cache.check(ping) is True
    now[0] += 0.5
    stall = True
    # The lock is held by something else, so this caller times out its wait with a fresh answer.
    await cache._lock.acquire()
    try:
        assert await cache.check(ping) is True
    finally:
        cache._lock.release()


async def test_the_queue_wait_outlasts_the_ping_budget() -> None:
    assert READINESS_WAIT_SECONDS > READINESS_PING_TIMEOUT_SECONDS
