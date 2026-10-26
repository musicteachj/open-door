"""Make one confirm card look 16 minutes older, so a browser test can see it expired.

A card lives 15 minutes (a fixed SQL interval, not a setting), and a test cannot wait that long.
This moves the proposal's created_at and expires_at back by 16 minutes, so the next Confirm or
Dismiss is refused as expired and the next read of the conversation shows the card expired.

    uv run python scripts/expire_proposal_for_tests.py 3f2c0d3e-6b0e-4c0e-9a55-0b3c1d7f1a10

Runs as the database owner (MIGRATION_DATABASE_URL, like clear_browser_test_spend.py), the only
login that may change these columns, with the table's triggers off for the one statement. That
makes it unsafe anywhere but a local test database, so it refuses any database whose host is not
this machine (including a `host` or `hostaddr` in the URL's query), a production app setting, and
any proposal that is not pending. Never point it at a database that matters.
"""

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
AGE_MINUTES = 16

AGE_PROPOSAL = text(
    "UPDATE ai_proposals SET created_at = created_at - make_interval(mins => :minutes),"
    " expires_at = expires_at - make_interval(mins => :minutes)"
    " WHERE id = :id AND status = 'pending' RETURNING id"
)


def refuse_unless_local(url: str) -> None:
    """Exit with a message unless the database is on this machine.

    A `host` or `hostaddr` in the query string overrides the URL's own host in the driver, so
    either one is refused outright."""
    parsed = make_url(url)
    overridden = sorted({"host", "hostaddr"} & set(parsed.query))
    if overridden:
        raise SystemExit(
            f"Refusing to run: the database URL's query names {overridden[0]!r}, which can point "
            "it at another machine. Nothing was changed."
        )
    host = parsed.host
    if host not in LOCAL_HOSTS:
        raise SystemExit(
            f"Refusing to run: the database host is {host!r}, not this machine. This script is "
            "for a local test database only. Nothing was changed."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("proposal_id", type=UUID, help="the pending proposal to expire")
    return parser


async def main(arguments: argparse.Namespace) -> None:
    settings = get_settings()
    if settings.migration_database_url is None:
        raise SystemExit("MIGRATION_DATABASE_URL is not set. See apps/api/.env.example.")
    if settings.app_env == "production":
        raise SystemExit("Refusing to run: the app is set to production. Nothing was changed.")
    url = str(settings.migration_database_url)
    refuse_unless_local(url)
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL session_replication_role = replica"))
            result = await connection.execute(
                AGE_PROPOSAL, {"minutes": AGE_MINUTES, "id": arguments.proposal_id}
            )
            found = result.first() is not None
        if not found:
            raise SystemExit(f"No pending proposal {arguments.proposal_id}. Nothing was changed.")
        print(f"Expired proposal {arguments.proposal_id}.")
    except DBAPIError as error:
        raise SystemExit(
            f"Expiring the proposal failed ({type(error.orig).__name__}). Check that "
            "MIGRATION_DATABASE_URL names the database owner."
        ) from None
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(build_parser().parse_args()))
