"""Admit only Open Door's own roles to its database (Phase 9a, task 9).

A new database lets every role connect: `CONNECT` is granted to PUBLIC. On a Postgres server shared
with another app, that would let the other app's logins open this database, although row-level
security would still stop them reading tenant rows. This migration takes `CONNECT` from PUBLIC and
gives it to `od_app` and `od_cleanup`, which the logins inherit (0002 and 0019 grant the logins
their role, never the database). Granting it to the roles rather than the logins keeps the bootstrap
free of database-level grants, and a new login needs nothing more than its role.

The migration runs as the database owner, who may change the database's privileges. It names the
database through `current_database()`, so it is right whatever the database is called.

The downgrade is the reverse: the two roles lose `CONNECT` and PUBLIC gets it back, which is what a
new database starts with.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN"
        " EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', current_database());"
        " EXECUTE format('GRANT CONNECT ON DATABASE %I TO od_app, od_cleanup', current_database());"
        " END $$"
    )


def downgrade() -> None:
    # This restores 0019's exact state. On the shared server the init SQL
    # (scripts/image/postgres-open-door.sql) had already revoked CONNECT from PUBLIC, so after a
    # downgrade there the revoke must be run again by hand.
    op.execute(
        "DO $$ BEGIN"
        " EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM od_app, od_cleanup',"
        " current_database());"
        " EXECUTE format('GRANT CONNECT ON DATABASE %I TO PUBLIC', current_database());"
        " END $$"
    )
