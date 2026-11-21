"""Whether the live assistant is available: the public flag the landing page reads.

True when today's room is at least what a first question needs. The answer is the same for every
visitor, so each process keeps it for a moment and one computation runs at a time (the shape of
`ReadinessCache`, `app/api/v1/health.py`).
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Final

from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.budget import Caps, day_room

# What a first question reserves (the guard's call and the model's, from a new sandbox) is about
# $0.19 today; a test proves it fits under this and is more than $0.15.
LANDING_ROOM_USD: Final = Decimal("0.25")
AVAILABILITY_TTL_SECONDS: Final = 30
# A computation gets what the readiness ping gets (`READINESS_PING_TIMEOUT_SECONDS`), and a caller
# queued behind it waits a little longer than that (`READINESS_WAIT_SECONDS`), so one slow database
# read can't hold every visitor's page.
AVAILABILITY_COMPUTE_SECONDS: Final = 2.0
AVAILABILITY_WAIT_SECONDS: Final = AVAILABILITY_COMPUTE_SECONDS + 0.5


class AvailabilityCache:
    """The last answer, kept for the TTL, with one computation in flight.

    A caller that arrives while one runs waits for the lock and then finds that answer fresh. The
    wait and the computation are each bounded, and either limit raises `TimeoutError` (the route
    answers 503). A computation that fails keeps nothing, so the next caller asks again.
    """

    def __init__(
        self,
        ttl_seconds: float = AVAILABILITY_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        compute_seconds: float = AVAILABILITY_COMPUTE_SECONDS,
        wait_seconds: float = AVAILABILITY_WAIT_SECONDS,
    ) -> None:
        self._compute_seconds = compute_seconds
        self._wait_seconds = wait_seconds
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = asyncio.Lock()
        self._answer: bool | None = None
        self._asked_at = 0.0

    async def get(self, compute: Callable[[], Awaitable[bool]]) -> bool:
        async with asyncio.timeout(self._wait_seconds):
            await self._lock.acquire()
        try:
            if self._answer is not None and self._clock() - self._asked_at < self._ttl_seconds:
                return self._answer
            async with asyncio.timeout(self._compute_seconds):
                answer = await compute()
            self._answer = answer
            self._asked_at = self._clock()
            return answer
        finally:
            self._lock.release()


async def live_assistant_available(engine: AsyncEngine, caps: Caps) -> bool:
    """Today's room, read on a plain connection (the API's login may read every daily-ledger row,
    migration 0019), against what a first question needs."""
    async with engine.connect() as connection:
        room = await day_room(connection, caps)
    return room.limit_usd - room.spent_today_usd >= LANDING_ROOM_USD
