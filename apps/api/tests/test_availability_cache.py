"""The availability flag's cache: one computation in flight, its answer kept for a moment."""

import asyncio
import contextlib

import pytest

from app.modules.assistant.availability import AVAILABILITY_TTL_SECONDS, AvailabilityCache


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Counter:
    def __init__(self, answer: bool = True, pause: float = 0.0) -> None:
        self.calls = 0
        self.answer = answer
        self.pause = pause

    async def __call__(self) -> bool:
        self.calls += 1
        if self.pause:
            await asyncio.sleep(self.pause)
        return self.answer


def test_the_cache_keeps_an_answer_for_thirty_seconds() -> None:
    assert AVAILABILITY_TTL_SECONDS == 30


async def test_a_fresh_answer_is_reused() -> None:
    clock = Clock()
    cache = AvailabilityCache(clock=clock)
    compute = Counter(answer=False)

    assert await cache.get(compute) is False
    clock.now += AVAILABILITY_TTL_SECONDS - 1
    assert await cache.get(compute) is False

    assert compute.calls == 1


async def test_an_old_answer_is_computed_again() -> None:
    clock = Clock()
    cache = AvailabilityCache(clock=clock)
    compute = Counter()

    await cache.get(compute)
    clock.now += AVAILABILITY_TTL_SECONDS + 1
    compute.answer = False

    assert await cache.get(compute) is False
    assert compute.calls == 2


async def test_concurrent_callers_compute_once() -> None:
    cache = AvailabilityCache(clock=Clock())
    compute = Counter(pause=0.05)

    answers = await asyncio.gather(*(cache.get(compute) for _ in range(8)))

    assert answers == [True] * 8
    assert compute.calls == 1


async def test_a_failed_computation_is_not_kept() -> None:
    cache = AvailabilityCache(clock=Clock())
    calls = 0

    async def broken() -> bool:
        nonlocal calls
        calls += 1
        raise ConnectionError("down")

    for _ in range(2):
        with contextlib.suppress(ConnectionError):
            await cache.get(broken)

    assert calls == 2


async def test_a_computation_that_runs_too_long_times_out_and_keeps_nothing() -> None:
    cache = AvailabilityCache(clock=Clock(), compute_seconds=0.05, wait_seconds=0.5)
    slow = Counter(pause=1.0)

    with pytest.raises(TimeoutError):
        await cache.get(slow)

    fast = Counter()
    assert await cache.get(fast) is True


async def test_the_wait_for_the_lock_is_bounded() -> None:
    cache = AvailabilityCache(clock=Clock(), compute_seconds=5.0, wait_seconds=0.05)
    running = asyncio.create_task(cache.get(Counter(pause=0.5)))
    await asyncio.sleep(0.01)

    with pytest.raises(TimeoutError):
        await cache.get(Counter())

    assert await running is True
