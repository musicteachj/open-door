"""Alembic's entry point. The database URL comes from the app's settings, never from alembic.ini."""

import asyncio
from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

# Importing the models puts every table on Base.metadata, which `alembic check` compares.
from app.db import models  # noqa: F401
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def database_url() -> str:
    """The owner. Migrations create roles, tables, and policies, which the API's login can't."""
    url = get_settings().migration_database_url
    if url is None:
        msg = (
            "MIGRATION_DATABASE_URL is not set. Migrations run as the database owner, not as the "
            "API's login. Add it to apps/api/.env; see .env.example."
        )
        raise CommandError(msg)
    return str(url)


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(database_url(), poolclass=pool.NullPool, hide_parameters=True)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
