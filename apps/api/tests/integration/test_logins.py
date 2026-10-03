"""The login users get their privileges only through od_app or od_cleanup, and bypass nothing."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

# pg_has_role(..., 'USAGE') asks whether the login has the role's privileges, which holds only if
# its membership passes them on (INHERIT). Policies written TO od_app reach the login the same way.
WHO_AM_I = """
    SELECT rolname, rolsuper, rolbypassrls, rolcanlogin,
           pg_has_role(current_user, 'od_app', 'USAGE'),
           pg_has_role(current_user, 'od_cleanup', 'USAGE')
    FROM pg_roles WHERE rolname = current_user
"""

# Objects owned by the two roles or by any login that is a member of either.
OWNED_BY_ROLES_OR_LOGINS = """
    WITH accounts AS (
        SELECT oid FROM pg_roles WHERE rolname IN ('od_app', 'od_cleanup')
        UNION
        SELECT member FROM pg_auth_members
        WHERE roleid IN ('od_app'::regrole, 'od_cleanup'::regrole)
    )
    SELECT (SELECT count(*) FROM pg_class WHERE relowner IN (SELECT oid FROM accounts))
         + (SELECT count(*) FROM pg_namespace WHERE nspowner IN (SELECT oid FROM accounts))
         + (SELECT count(*) FROM pg_proc WHERE proowner IN (SELECT oid FROM accounts))
"""

# Privileges granted to a login directly, instead of through its role.
GRANTED_TO_LOGINS = """
    WITH logins AS (
        SELECT member AS oid FROM pg_auth_members
        WHERE roleid IN ('od_app'::regrole, 'od_cleanup'::regrole)
    )
    SELECT c.relname FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a
    WHERE a.grantee IN (SELECT oid FROM logins)
    UNION ALL
    SELECT n.nspname FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a
    WHERE a.grantee IN (SELECT oid FROM logins)
"""

# The roles that a role is a member of (the roles it was granted).
MEMBER_OF = """
    SELECT g.rolname
    FROM pg_auth_members m
    JOIN pg_roles g ON g.oid = m.roleid
    JOIN pg_roles u ON u.oid = m.member
    WHERE u.rolname = :name
    ORDER BY g.rolname
"""


async def member_of(engine: AsyncEngine, name: str) -> list[str]:
    async with engine.connect() as connection:
        return list(await connection.scalars(text(MEMBER_OF), {"name": name}))


async def current_user(engine: AsyncEngine) -> str:
    async with engine.connect() as connection:
        return str((await connection.execute(text("SELECT current_user"))).scalar_one())


async def who_am_i(engine: AsyncEngine) -> tuple[object, ...]:
    async with engine.connect() as connection:
        return tuple((await connection.execute(text(WHO_AM_I))).one())


async def test_the_api_logs_in_as_its_own_user_with_only_the_app_role(
    app_engine: AsyncEngine,
) -> None:
    name, superuser, bypass_rls, can_login, has_app, has_cleanup = await who_am_i(app_engine)

    assert name not in ("od_app", "od_cleanup")
    assert (superuser, bypass_rls, can_login) == (False, False, True)
    assert (has_app, has_cleanup) == (True, False)


async def test_the_cleanup_login_has_only_the_cleanup_role(cleanup_engine: AsyncEngine) -> None:
    name, superuser, bypass_rls, can_login, has_app, has_cleanup = await who_am_i(cleanup_engine)

    assert name not in ("od_app", "od_cleanup")
    assert (superuser, bypass_rls, can_login) == (False, False, True)
    assert (has_app, has_cleanup) == (False, True)


async def test_the_roles_cannot_log_in_or_bypass_row_level_security(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT rolname, rolsuper, rolbypassrls, rolcanlogin FROM pg_roles"
                " WHERE rolname IN ('od_app', 'od_cleanup') ORDER BY rolname"
            )
        )
        roles = [tuple(row) for row in rows]

    assert roles == [("od_app", False, False, False), ("od_cleanup", False, False, False)]


async def test_the_roles_and_their_logins_own_nothing(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        owned: int = (await connection.execute(text(OWNED_BY_ROLES_OR_LOGINS))).scalar_one()

    assert owned == 0


async def test_the_logins_have_no_privileges_of_their_own(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        direct = (await connection.execute(text(GRANTED_TO_LOGINS))).all()

    assert direct == []


async def test_each_login_belongs_to_its_own_role_and_nothing_else(
    app_engine: AsyncEngine, cleanup_engine: AsyncEngine
) -> None:
    assert await member_of(app_engine, await current_user(app_engine)) == ["od_app"]
    assert await member_of(cleanup_engine, await current_user(cleanup_engine)) == ["od_cleanup"]


async def test_the_roles_belong_to_no_other_role(app_engine: AsyncEngine) -> None:
    assert await member_of(app_engine, "od_app") == []
    assert await member_of(app_engine, "od_cleanup") == []


async def test_nobody_holds_either_role_with_the_admin_option(app_engine: AsyncEngine) -> None:
    # WITH ADMIN OPTION would let the holder grant the role to others.
    async with app_engine.connect() as connection:
        holders = await connection.scalars(
            text(
                "SELECT u.rolname FROM pg_auth_members m"
                " JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles u ON u.oid = m.member"
                " WHERE g.rolname IN ('od_app', 'od_cleanup') AND m.admin_option"
            )
        )
        names = list(holders)

    assert names == []
