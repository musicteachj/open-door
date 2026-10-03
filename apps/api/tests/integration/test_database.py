from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.engine import create_engine, ping

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    # Reads DATABASE_URL from the environment (CI) or apps/api/.env (local development).
    engine = create_engine(str(Settings().database_url))
    yield engine
    await engine.dispose()


async def test_the_development_database_answers(engine: AsyncEngine) -> None:
    assert await ping(engine) is True


async def test_migrations_have_enabled_pgvector(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        assert result.scalar_one_or_none() == "vector"
