"""Health: `GET /api/v1/health/live` (is the process up) and `GET /api/v1/health` (can it serve).

**Liveness** never touches the database. It is the container's check, so a database failover
doesn't get every task restarted.

**Readiness** is the load balancer's check. It pings the database with a 2-second limit (under the
probe's own timeout, so a blackholed database answers 503 instead of timing the probe out), keeps
the answer for 1 second, and runs one check at a time, so a flood of unauthenticated probes costs
the database one round trip a second. Both answer `Cache-Control: no-store`, and neither is logged.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.api.deps import get_engine
from app.core.cache_control import CACHE_CONTROL_HEADER, NO_STORE
from app.db.engine import ping

router = APIRouter(tags=["health"])

DatabasePing = Callable[[], Awaitable[bool]]

READINESS_PING_TIMEOUT_SECONDS = 2.0
READINESS_CACHE_SECONDS = 1.0
# Longer than the ping's budget, so a queued probe sees the ping that holds the lock finish.
READINESS_WAIT_SECONDS = READINESS_PING_TIMEOUT_SECONDS + 0.5


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    version: str


class LiveResponse(BaseModel):
    status: Literal["ok"]
    version: str


class ReadinessCache:
    """The last readiness answer, kept for a moment, with one check in flight.

    A caller that arrives while a check runs waits for the lock and then finds that check's answer
    fresh, so it asks nothing. The wait is a little longer than the ping's budget, so a probe queued
    behind a ping that times out normally gets that ping's fresh answer. Closing a canceled
    connection can outlast the ping's own limit, and a probe queued behind it must still answer
    before the load balancer gives up. After the wait it gets the last answer only if that is still
    inside the cache window, else "unavailable": a stale "ok" must not outlive a database that is
    down. The clock is a parameter so a test can move it.
    """

    def __init__(
        self,
        ttl_seconds: float = READINESS_CACHE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        wait_seconds: float = READINESS_WAIT_SECONDS,
    ) -> None:
        self._wait_seconds = wait_seconds
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = asyncio.Lock()
        self._answer: bool | None = None
        self._asked_at = 0.0

    async def check(self, database_ping: DatabasePing) -> bool:
        try:
            async with asyncio.timeout(self._wait_seconds):
                await self._lock.acquire()
        except TimeoutError:
            fresh = self._answer is not None and self._clock() - self._asked_at < self._ttl_seconds
            return bool(self._answer) if fresh else False
        try:
            if self._answer is not None and self._clock() - self._asked_at < self._ttl_seconds:
                return self._answer
            self._answer = await database_ping()
            self._asked_at = self._clock()
            return self._answer
        finally:
            self._lock.release()


def get_database_ping(engine: Annotated[AsyncEngine, Depends(get_engine)]) -> DatabasePing:
    """The database check, as a dependency so tests can replace it.

    It uses a bare connection, never a tenant session, so it stays independent of row-level
    security.
    """

    async def check() -> bool:
        return await ping(engine, READINESS_PING_TIMEOUT_SECONDS)

    return check


def get_readiness_cache(request: Request) -> ReadinessCache:
    """The app's one cache (created with the app, so every request shares it)."""
    cache: ReadinessCache = request.app.state.readiness
    return cache


@router.get(
    "/health/live",
    operation_id="getHealthLive",
    summary="Report that the API process is up, without touching the database",
    response_model=LiveResponse,
)
async def get_health_live(response: Response) -> LiveResponse:
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE
    return LiveResponse(status="ok", version=__version__)


@router.get(
    "/health",
    operation_id="getHealth",
    summary="Report whether the API and its database are up",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def get_health(
    response: Response,
    database_ping: Annotated[DatabasePing, Depends(get_database_ping)],
    cache: Annotated[ReadinessCache, Depends(get_readiness_cache)],
) -> HealthResponse:
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE
    if await cache.check(database_ping):
        return HealthResponse(status="ok", database="ok", version=__version__)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="degraded", database="unavailable", version=__version__)
