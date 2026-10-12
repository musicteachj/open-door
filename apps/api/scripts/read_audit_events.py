"""Print the audit events one person wrote, as JSON, for the browser tests.

Usage: uv run python scripts/read_audit_events.py <actor-person-id>

Reads straight from the database as its owner (MIGRATION_DATABASE_URL), so a browser test sees
what was really stored and not what the API chose to return. Read-only: the transaction is set
READ ONLY, so a write is refused. A person's ID belongs to one sandbox, so the actor alone picks
the events out.
"""

import asyncio
import json
import sys
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

QUERY = text(
    "SELECT action, via, target_type, target_id::text AS target_id, actor_person_id::text AS actor,"
    " after FROM audit_events WHERE actor_person_id = :actor ORDER BY occurred_at"
)


async def main(actor: UUID) -> None:
    url = get_settings().migration_database_url
    if url is None:
        sys.exit("MIGRATION_DATABASE_URL is not set")
    engine = create_async_engine(str(url), hide_parameters=True)
    try:
        async with engine.connect() as connection:
            # The first statement of the transaction, so nothing here can write.
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            rows = (await connection.execute(QUERY, {"actor": actor})).mappings().all()
    finally:
        await engine.dispose()
    print(json.dumps([dict(row) for row in rows]))


if __name__ == "__main__":
    asyncio.run(main(UUID(sys.argv[1])))
