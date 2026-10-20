"""Delete the daily AI ledger rows a browser test run created, so the run leaves none behind.

A stopped or failed turn keeps its model reservation, and `ai_spend_daily` has no tenant, so
cleaning up a run's sandboxes leaves its reservations in the daily ledger. A full browser run adds
about $10 of them, which pushes the day past the real $3 cap and then fails the API's own tests.

    uv run python scripts/clear_browser_test_spend.py --now
    uv run python scripts/clear_browser_test_spend.py --since 2026-10-18T15:04:05.123456+00:00

`--now` prints the database's clock. A run asks for it before it starts and passes it back as
`--since` when it ends, so the cutoff is on the same clock that stamps the rows (`created_at` is
set by the database, and a Docker host's clock can differ from the machine's).

`--since` deletes every row with `created_at >= since` and prints how many and their sum. It is
required, it must be a timestamp with a zone (a bare date or a time with no zone is refused,
because a wrong guess would delete the wrong rows), and it must be at most 24 hours old, a guard
against wiping a day by mistake.

Runs as the database owner (MIGRATION_DATABASE_URL, as bootstrap_db_users.py does), the only login
that can delete from the ledger. Rows from anything else that used the same database during the
run go too (a dev server answering a question, a pytest run). That is acceptable for a local test
database, and the reason this must never be pointed at a database that matters.
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings

MAX_AGE = timedelta(hours=24)

DATABASE_CLOCK = text("SELECT clock_timestamp()")
DELETE_SINCE = text("DELETE FROM ai_spend_daily WHERE created_at >= :since RETURNING amount_usd")


def parse_since(value: str) -> datetime:
    """A timestamp with a zone, in UTC. Anything else is refused with a message."""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not an ISO timestamp, such as 2026-10-18T15:04:05+00:00."
        ) from None
    if moment.tzinfo is None:
        raise argparse.ArgumentTypeError(
            f"{value!r} has no time zone. Give it in UTC, such as 2026-10-18T15:04:05+00:00 "
            "or 2026-10-18T15:04:05Z."
        )
    return moment.astimezone(UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument(
        "--since",
        type=parse_since,
        help="delete rows created at or after this UTC timestamp (at most 24 hours ago)",
    )
    which.add_argument(
        "--now",
        action="store_true",
        help="print the database's clock as an ISO UTC timestamp, and delete nothing",
    )
    return parser


async def database_now(engine: AsyncEngine) -> datetime:
    async with engine.connect() as connection:
        moment: datetime = (await connection.execute(DATABASE_CLOCK)).scalar_one()
    return moment.astimezone(UTC)


async def clear_since(engine: AsyncEngine, since: datetime) -> tuple[int, Decimal]:
    """Delete the rows created at or after `since`. Returns how many, and what they added up to."""
    now = await database_now(engine)
    if now - since > MAX_AGE:
        raise SystemExit(
            f"--since {since.isoformat()} is more than 24 hours before the database's clock "
            f"({now.isoformat()}). Nothing was deleted."
        )
    async with engine.begin() as connection:
        result = await connection.execute(DELETE_SINCE, {"since": since})
        amounts: list[Decimal] = list(result.scalars())
    return len(amounts), sum(amounts, Decimal(0))


async def main(arguments: argparse.Namespace) -> None:
    settings = get_settings()
    if settings.migration_database_url is None:
        raise SystemExit("MIGRATION_DATABASE_URL is not set. See apps/api/.env.example.")
    # hide_parameters keeps bound values out of SQLAlchemy's error messages.
    engine = create_async_engine(str(settings.migration_database_url), hide_parameters=True)
    try:
        if arguments.now:
            print((await database_now(engine)).isoformat())
            return
        count, total = await clear_since(engine, arguments.since)
        print(
            f"Deleted {count} ai_spend_daily rows created since {arguments.since.isoformat()}, "
            f"adding up to ${total:f}."
        )
    except DBAPIError as error:
        # Name only the error's class: SQLAlchemy's own message includes the statement.
        raise SystemExit(
            f"Clearing the ledger failed ({type(error.orig).__name__}). Check that "
            "MIGRATION_DATABASE_URL names the database owner."
        ) from None
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(build_parser().parse_args()))
