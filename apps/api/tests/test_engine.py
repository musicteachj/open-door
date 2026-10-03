import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.engine import create_engine, ping


async def test_ping_reports_an_unreachable_database_as_down() -> None:
    # Port 1 refuses connections at once, so this needs no running database.
    engine = create_engine("postgresql+asyncpg://nobody:nothing@127.0.0.1:1/nowhere")
    try:
        assert await ping(engine) is False
    finally:
        await engine.dispose()


class StalledConnection:
    async def execute(self, statement: object) -> None:
        await asyncio.sleep(3600)


class StalledEngine:
    """Connects instantly, then never answers: a half-open or overloaded database."""

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[StalledConnection]:
        yield StalledConnection()


async def test_ping_gives_up_on_a_database_that_connects_but_never_answers() -> None:
    engine = cast(AsyncEngine, StalledEngine())
    assert await ping(engine, timeout_seconds=0.05) is False
