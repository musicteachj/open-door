"""The async database engine, and a cheap check that the database answers."""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# Imported for its side effect: it registers the hook that scopes every ORM transaction to a
# tenant. Anything that builds an engine here therefore gets the hook, whether or not it imports
# app.db.tenancy itself.
import app.db.tenancy  # noqa: F401

logger = logging.getLogger(__name__)

PING_TIMEOUT_SECONDS = 5.0

# Set on every connection the engine opens, and by the bootstrap script on each login (a second
# line, for a connection the engine did not open). Postgres reads "10s" as ten seconds.
# The longest legitimate statement is seeding a sandbox, which runs in well under a second per
# statement; the turn's own end-of-turn writes are bounded at 10 s in code.
STATEMENT_TIMEOUT = "10s"
IDLE_IN_TRANSACTION_TIMEOUT = "30s"


def create_engine(
    database_url: str,
    *,
    statement_timeout: str = STATEMENT_TIMEOUT,
    idle_in_transaction_timeout: str = IDLE_IN_TRANSACTION_TIMEOUT,
) -> AsyncEngine:
    """Create the engine. Connections open lazily, so this never touches the database.

    Every connection gets a statement timeout and an idle-in-transaction timeout, so a hung query
    or a request that stalls inside a transaction can't hold a connection or a lock for good.
    """
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        # A failed statement's error and log line name the SQL but not the bound values, which can
        # be user-written text (a handbook question, later a conversation).
        hide_parameters=True,
        # asyncpg's connect timeout, in seconds: a dead database fails fast instead of hanging.
        connect_args={
            "timeout": 5,
            "server_settings": {
                "statement_timeout": statement_timeout,
                "idle_in_transaction_session_timeout": idle_in_transaction_timeout,
            },
        },
    )


async def ping(engine: AsyncEngine, timeout_seconds: float = PING_TIMEOUT_SECONDS) -> bool:
    """Return True if the database answers `SELECT 1` in time, False otherwise.

    The time limit covers connecting and the query, so a connection that opens but never answers
    still lets the health check report "degraded". It is not a hard wall-clock bound: if canceling
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
