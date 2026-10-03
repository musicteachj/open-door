"""The async database engine, and a cheap check that the database answers."""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

logger = logging.getLogger(__name__)

PING_TIMEOUT_SECONDS = 5.0


def create_engine(database_url: str) -> AsyncEngine:
    """Create the engine. Connections open lazily, so this never touches the database."""
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        # asyncpg's connect timeout, in seconds: a dead database fails fast instead of hanging.
        connect_args={"timeout": 5},
    )


async def ping(engine: AsyncEngine, timeout_seconds: float = PING_TIMEOUT_SECONDS) -> bool:
    """Return True if the database answers `SELECT 1` in time, False otherwise.

    The time limit covers connecting and the query, so a connection that opens but never answers
    still lets the health check report "degraded". It is not a hard wall-clock bound: if cancelling
    the query itself stalls on the network, closing the connection can take longer.
    """
    try:
        async with asyncio.timeout(timeout_seconds), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (OSError, TimeoutError, SQLAlchemyError) as exc:
        # SQLAlchemy wraps the driver's error. Its type tells a wrong password from a database
        # that is still starting or missing.
        cause = getattr(exc, "orig", None) or exc
        logger.warning("Database ping failed: %s", type(cause).__name__)
        return False
    return True
