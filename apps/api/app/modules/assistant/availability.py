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


class AvailabilityCache:
    """The last answer, kept for the TTL, with one computation in flight.

    A caller that arrives while one runs waits for the lock and then finds that answer fresh. A
    computation that fails keeps nothing, so the next caller asks again.
    """

    def __init__(
        self,
        ttl_seconds: float = AVAILABILITY_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = asyncio.Lock()
        self._answer: bool | None = None
        self._asked_at = 0.0

    async def get(self, compute: Callable[[], Awaitable[bool]]) -> bool:
        async with self._lock:
            if self._answer is not None and self._clock() - self._asked_at < self._ttl_seconds:
                return self._answer
            answer = await compute()
            self._answer = answer
            self._asked_at = self._clock()
            return answer


async def live_assistant_available(engine: AsyncEngine, caps: Caps) -> bool:
    """Today's room, read on a plain connection (the API's login may read every daily-ledger row,
    migration 0019), against what a first question needs."""
    async with engine.connect() as connection:
        room = await day_room(connection, caps)
    return room.limit_usd - room.spent_today_usd >= LANDING_ROOM_USD
