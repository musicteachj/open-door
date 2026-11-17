"""The cleanup job: delete what has outlived its retention, as the cleanup login.

    uv run python -m app.jobs.cleanup        (or `make cleanup`)

It reads only `CleanupSettings` (CLEANUP_DATABASE_URL), never the API's settings, and connects as
the cleanup login (a member of od_cleanup). Every rule it enforces is also a row-level policy for
that login (migrations 0003 and 0019), so a bug here can't delete more than the policies allow.

Each step is its own transaction and starts with `SET LOCAL statement_timeout = '60s'`: the
engine's per-connection default is 10 s (right for the API), and it would win over the login's own
60 s role default. In order:

1. Expired sandboxes (tenants), in batches of 50 so no one delete runs long. Their rows cascade.
2. `ai_spend_daily` rows whose UTC day is more than 30 days back.
3. `sandbox_starts` rows more than 24 hours old.
4. Handbook versions that are not the newest published one, were created before it was published
   (so a version still being loaded survives), and are not in use. The cleanup login can't see
   live sandboxes, so it can't know which versions they are pinned to: it deletes each candidate
   under a savepoint, and the foreign key from `tenants` (RESTRICT) refuses a pinned one (SQLSTATE
   23503). That, or the trigger's refusal of the newest published version (OD006), skips it.
   Sections and chunks go by cascade.

It then logs one JSON line with the counts and exits 0. Any error is logged (its class only, never
the URL or the SQL) and the exit code is 1. A second run finds nothing to delete.
"""

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import TextClause, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.logging import configure_logging
from app.core.owner_settings import DatabaseUrlError, cleanup_database_url
from app.db.engine import create_engine
from app.db.errors import has_sqlstate

logger = logging.getLogger("app.jobs.cleanup")

STEP_TIMEOUT = "60s"
TENANT_BATCH_SIZE = 50
FOREIGN_KEY_VIOLATION = "23503"
NEWEST_VERSION_REFUSED = "OD006"

DELETE_TENANT_BATCH = text(
    "DELETE FROM tenants WHERE id IN (SELECT id FROM tenants WHERE expires_at < now() LIMIT :batch)"
)
DELETE_OLD_SPEND = text(
    "DELETE FROM ai_spend_daily WHERE day < (now() AT TIME ZONE 'UTC')::date - 30"
)
DELETE_OLD_STARTS = text(
    "DELETE FROM sandbox_starts WHERE created_at < now() - interval '24 hours'"
)
# The same order 0005's pin trigger uses to choose the newest published version.
UNUSED_VERSION_CANDIDATES = text(
    """
    WITH newest AS (
        SELECT id, published_at FROM handbook_versions
        WHERE published_at IS NOT NULL
        ORDER BY published_at DESC, created_at DESC, id DESC
        LIMIT 1
    )
    SELECT v.id FROM handbook_versions v, newest
    WHERE v.id <> newest.id AND v.created_at < newest.published_at
    ORDER BY v.created_at, v.id
    """
)
DELETE_VERSION = text("DELETE FROM handbook_versions WHERE id = :id")


@dataclass(frozen=True)
class CleanupCounts:
    tenants: int = 0
    spend_rows: int = 0
    starts: int = 0
    handbook_versions: int = 0
    handbook_versions_skipped: int = 0

    def as_fields(self) -> dict[str, int]:
        """The counts under camelCase names, as the log line carries them."""
        return {
            "tenants": self.tenants,
            "spendRows": self.spend_rows,
            "starts": self.starts,
            "handbookVersions": self.handbook_versions,
            "handbookVersionsSkipped": self.handbook_versions_skipped,
        }


@asynccontextmanager
async def step(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """One transaction with the job's own 60 s statement timeout, which beats the engine's."""
    async with engine.begin() as connection:
        await connection.execute(text(f"SET LOCAL statement_timeout = '{STEP_TIMEOUT}'"))
        yield connection


async def delete_expired_tenants(engine: AsyncEngine) -> int:
    total = 0
    while True:
        async with step(engine) as connection:
            result = await connection.execute(DELETE_TENANT_BATCH, {"batch": TENANT_BATCH_SIZE})
        total += result.rowcount
        if result.rowcount < TENANT_BATCH_SIZE:
            return total


async def delete_rows(engine: AsyncEngine, statement: TextClause) -> int:
    async with step(engine) as connection:
        return (await connection.execute(statement)).rowcount


async def delete_unused_handbook_versions(engine: AsyncEngine) -> tuple[int, int]:
    """Returns (deleted, skipped because a sandbox uses it or it became the newest)."""
    deleted = skipped = 0
    async with step(engine) as connection:
        candidates: list[UUID] = list(
            (await connection.execute(UNUSED_VERSION_CANDIDATES)).scalars()
        )
        for version_id in candidates:
            try:
                async with connection.begin_nested():
                    await connection.execute(DELETE_VERSION, {"id": version_id})
            except DBAPIError as error:
                if has_sqlstate(error, FOREIGN_KEY_VIOLATION) or has_sqlstate(
                    error, NEWEST_VERSION_REFUSED
                ):
                    skipped += 1
                    continue
                raise
            deleted += 1
    return deleted, skipped


async def run_cleanup(engine: AsyncEngine) -> CleanupCounts:
    tenants = await delete_expired_tenants(engine)
    spend_rows = await delete_rows(engine, DELETE_OLD_SPEND)
    starts = await delete_rows(engine, DELETE_OLD_STARTS)
    versions, skipped = await delete_unused_handbook_versions(engine)
    return CleanupCounts(tenants, spend_rows, starts, versions, skipped)


async def run() -> int:
    """Run the job against CLEANUP_DATABASE_URL. Returns the process exit code."""
    configure_logging("INFO")
    try:
        url = cleanup_database_url()
    except DatabaseUrlError as error:
        logger.error("cleanup failed: %s", error)
        return 1
    engine = create_engine(url)
    try:
        counts = await run_cleanup(engine)
    except (SQLAlchemyError, OSError, TimeoutError) as error:
        # The class only: SQLAlchemy's message includes the SQL, and a connection error the host.
        cause = getattr(error, "orig", None) or error
        logger.error("cleanup failed: %s", type(cause).__name__)
        return 1
    finally:
        await engine.dispose()
    logger.info("cleanup finished", extra={"fields": counts.as_fields()})
    return 0


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
