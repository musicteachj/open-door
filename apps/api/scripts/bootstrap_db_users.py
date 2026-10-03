"""Create or update the database login users, and grant each one its role.

Runs as the database owner (MIGRATION_DATABASE_URL), after the migrations have created the roles.
Each login's name and password come from its own URL, so each URL is the single source of truth
for its user:

- DATABASE_URL names the API's login, which gets od_app.
- CLEANUP_DATABASE_URL, if set, names the cleanup login, which gets od_cleanup.

A second run only resets the passwords, so `make db` runs it every time. Three rules keep it safe:

- Postgres quotes every name and value itself, through format('%I') for names and format('%L') for
  values, so nothing from a URL is ever pasted into SQL by hand.
- A login that already exists is reused only if it has no extra power. Granting od_app to a role
  that can bypass row-level security, for example, would give the API that power.
- The plaintext password never leaves this process. The script sends a SCRAM-SHA-256 verifier, so
  neither an error message nor the server's log (log_statement, log_min_error_statement) can
  contain the password. Errors are reduced to the name of their class for the same reason.
"""

import asyncio
import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings

ROLES = ("od_app", "od_cleanup")

CREATE_LOGIN = "CREATE ROLE %I WITH LOGIN PASSWORD %L"
ALTER_LOGIN = "ALTER ROLE %I WITH LOGIN PASSWORD %L"
# The login must inherit the role's privileges: the row-level security policies are written
# TO od_app, and they reach the login only through an inheriting membership.
GRANT_ROLE = "GRANT %I TO %I WITH INHERIT TRUE"

FORMAT = text("SELECT format(CAST(:template AS text), CAST(:first AS text), CAST(:second AS text))")

# The attributes an existing login must not have, with the name Postgres gives each one.
POWERS = (
    ("rolsuper", "SUPERUSER"),
    ("rolbypassrls", "BYPASSRLS"),
    ("rolcreaterole", "CREATEROLE"),
    ("rolcreatedb", "CREATEDB"),
    ("rolreplication", "REPLICATION"),
)
ATTRIBUTES = text(
    "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolreplication"
    " FROM pg_roles WHERE rolname = :user"
)
MEMBERSHIPS = text(
    "SELECT g.rolname, m.admin_option FROM pg_auth_members m"
    " JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles u ON u.oid = m.member"
    " WHERE u.rolname = :user ORDER BY g.rolname"
)

# The roles that belong to the login. They would inherit whatever the login is granted.
MEMBERS = text(
    "SELECT DISTINCT u.rolname FROM pg_auth_members m"
    " JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles u ON u.oid = m.member"
    " WHERE g.rolname = :user ORDER BY u.rolname"
)

SCRAM_ITERATIONS = 4096
SCRAM_SALT_BYTES = 16


@dataclass(frozen=True)
class Login:
    user: str
    password: str = field(repr=False)
    role: str
    variable: str


def scram_verifier(
    password: str, salt: bytes | None = None, iterations: int = SCRAM_ITERATIONS
) -> str:
    """The password as a Postgres SCRAM-SHA-256 secret (RFC 5802, RFC 7677).

    Postgres stores a value in this form as it is, instead of hashing it again. It runs SASLprep on
    a password first, which leaves printable ASCII unchanged, so login_from accepts only that.
    """
    salt = secrets.token_bytes(SCRAM_SALT_BYTES) if salt is None else salt
    salted_password = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    client_key = hmac.digest(salted_password, b"Client Key", "sha256")
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.digest(salted_password, b"Server Key", "sha256")

    def encoded(raw: bytes) -> str:
        return base64.b64encode(raw).decode("ascii")

    return f"SCRAM-SHA-256${iterations}:{encoded(salt)}${encoded(stored_key)}:{encoded(server_key)}"


def login_from(url: str, variable: str, role: str, owner: str) -> Login:
    parsed = make_url(url)
    if not parsed.username or not parsed.password:
        raise SystemExit(f"{variable} must include a user name and a password.")
    if parsed.username == owner or parsed.username in ROLES:
        raise SystemExit(
            f"{variable} names {parsed.username!r}. It needs a login user of its own, such as "
            f"{role}_login, so that row-level security applies to it. See apps/api/.env.example."
        )
    if not all(" " <= character <= "~" for character in parsed.password):
        raise SystemExit(
            f"The password in {variable} must use only printable ASCII characters (letters, "
            "digits, punctuation, and spaces). Postgres normalizes any other character before "
            "it hashes a password, and this script does not."
        )
    return Login(parsed.username, parsed.password, role, variable)


def logins_from(database_url: str, cleanup_database_url: str | None, owner_url: str) -> list[Login]:
    """The logins to create, from the URLs. Refuses anything that would weaken the roles."""
    owner = make_url(owner_url).username or ""
    logins = [login_from(database_url, "DATABASE_URL", "od_app", owner)]
    if cleanup_database_url is not None:
        logins.append(login_from(cleanup_database_url, "CLEANUP_DATABASE_URL", "od_cleanup", owner))
    if len({login.user for login in logins}) < len(logins):
        raise SystemExit("DATABASE_URL and CLEANUP_DATABASE_URL must name different users.")
    return logins


def error_name(error: DBAPIError) -> str:
    """The driver's name for an error, such as InsufficientPrivilegeError, and nothing else."""
    original = error.orig
    cause = getattr(original, "__cause__", None) or original
    return type(cause).__name__


async def server_formatted(
    connection: AsyncConnection, template: str, first: str, second: str
) -> str:
    """Fill in a format() template on the server, which quotes both values safely."""
    result = await connection.execute(
        FORMAT, {"template": template, "first": first, "second": second}
    )
    return str(result.scalar_one())


async def check_login(connection: AsyncConnection, login: Login) -> bool:
    """Return whether the login exists. Refuse, changing nothing, if it has extra power."""
    attributes = (
        (await connection.execute(ATTRIBUTES, {"user": login.user})).mappings().one_or_none()
    )
    if attributes is None:
        return False
    problems = [name for column, name in POWERS if attributes[column]]
    for group, admin_option in await connection.execute(MEMBERSHIPS, {"user": login.user}):
        if group != login.role:
            problems.append(f"it is a member of {group}")
        elif admin_option:
            # The holder could grant the role to any other role, which would then inherit it.
            problems.append(f"it holds {group} WITH ADMIN OPTION")
    members = (await connection.scalars(MEMBERS, {"user": login.user})).all()
    if members:
        # Granting the role to the login would grant it to them too.
        problems.append(f"it has members ({', '.join(members)}) who would inherit {login.role}")
    if problems:
        raise SystemExit(
            f"{login.variable} names {login.user!r}, which already exists and is not safe to give "
            f"{login.role}: {', '.join(problems)}. Nothing was changed. Drop that role, or choose "
            "another user name."
        )
    return True


async def ensure_login(connection: AsyncConnection, login: Login, exists: bool) -> str:
    template = ALTER_LOGIN if exists else CREATE_LOGIN
    # exec_driver_sql sends each statement exactly as Postgres built it. text() would read
    # ":name" inside a value as a bind parameter.
    await connection.exec_driver_sql(
        await server_formatted(connection, template, login.user, scram_verifier(login.password))
    )
    await connection.exec_driver_sql(
        await server_formatted(connection, GRANT_ROLE, login.role, login.user)
    )
    return f"{login.user}: {'password reset' if exists else 'created'}, with {login.role}"


async def main() -> None:
    settings = get_settings()
    if settings.migration_database_url is None:
        raise SystemExit("MIGRATION_DATABASE_URL is not set. See apps/api/.env.example.")
    owner_url = str(settings.migration_database_url)
    cleanup_url = settings.cleanup_database_url
    logins = logins_from(
        str(settings.database_url), None if cleanup_url is None else str(cleanup_url), owner_url
    )

    # hide_parameters keeps bound values out of SQLAlchemy's error messages.
    engine = create_async_engine(owner_url, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            existing = await connection.scalars(
                text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
                {"roles": list(ROLES)},
            )
            if set(existing) != set(ROLES):
                raise SystemExit("The od_app and od_cleanup roles don't exist. Run `make migrate`.")
            # Check every login before changing any, so a refusal leaves the database as it was.
            states = [(login, await check_login(connection, login)) for login in logins]
            messages = [await ensure_login(connection, login, exists) for login, exists in states]
    except DBAPIError as error:
        # SQLAlchemy's own message includes the failed statement. Name only the error's class.
        raise SystemExit(
            f"Setting up the login users failed ({error_name(error)}). Check that "
            "MIGRATION_DATABASE_URL names the database owner, who must be able to create roles."
        ) from None
    finally:
        await engine.dispose()
    print("\n".join(messages))


if __name__ == "__main__":
    asyncio.run(main())
