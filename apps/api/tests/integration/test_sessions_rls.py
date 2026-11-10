"""Sessions under row-level security (migration 0017), and the family a sign-out ends.

Everything here connects as the API's own login (`od_app_login`), the one the Phase 1 close-out
review used to insert a session in another sandbox from `psql`.
"""

import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.tenancy import NO_TENANT, TenantContext, tenant_session
from app.modules.identity.sessions import (
    SET_SESSION_LOOKUP,
    SessionGoneError,
    SessionRecord,
    end_session,
    end_session_family,
    find_session,
    rotate_session,
    start_session,
)
from app.modules.identity.tokens import SessionTokens
from tests.integration.conftest import MakeTenant, SampleTenant, sha256_of_random_token

pytestmark = pytest.mark.integration

FORGED_INSERT = text(
    "INSERT INTO sessions (token_hash, csrf_hash, tenant_id, person_id, expires_at, family_id)"
    " VALUES (:token_hash, :csrf_hash, :tenant_id, :person_id, :expires_at, gen_random_uuid())"
)
ALL_SESSIONS = text("SELECT token_hash FROM sessions")


async def start(engine: AsyncEngine, tenant: SampleTenant, person_id: UUID) -> SessionTokens:
    async with tenant_session(engine, TenantContext(tenant.id, None)) as session:
        return await start_session(session, tenant.id, person_id)


async def lookup(engine: AsyncEngine, tokens: SessionTokens) -> SessionRecord | None:
    async with tenant_session(engine, NO_TENANT) as session:
        return await find_session(session, tokens.session_hash)


async def tenant_expires_at(owner_engine: AsyncEngine, tenant_id: UUID):  # type: ignore[no-untyped-def]
    async with owner_engine.connect() as connection:
        return await connection.scalar(
            text("SELECT expires_at FROM tenants WHERE id = :id"), {"id": tenant_id}
        )


async def surviving(owner_engine: AsyncEngine, *hashes: bytes) -> set[bytes]:
    async with owner_engine.connect() as connection:
        rows = await connection.scalars(
            text("SELECT token_hash FROM sessions WHERE token_hash = ANY(:hashes)"),
            {"hashes": list(hashes)},
        )
        return set(rows)


# --- The table's rules ---------------------------------------------------------------------


async def test_row_level_security_is_on_and_forced_for_sessions(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        flags = (
            await connection.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity"
                    " FROM pg_class WHERE relname = 'sessions'"
                )
            )
        ).one()

    assert tuple(flags) == (True, True)


async def test_the_session_policies_are_exactly_these(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT polname, polcmd::text, polpermissive,"
                    " pg_get_expr(polqual, polrelid), pg_get_expr(polwithcheck, polrelid)"
                    " FROM pg_policy WHERE polrelid = 'sessions'::regclass ORDER BY polname"
                )
            )
        ).all()
    found = {
        name: (cmd, permissive, " ".join((using or "").split()), " ".join((check or "").split()))
        for name, cmd, permissive, using, check in rows
    }

    read_or_delete = (
        "((token_hash = ( SELECT app.current_session_token_hash() AS current_session_token_hash))"
        " OR (tenant_id = ( SELECT app.current_tenant_id() AS current_tenant_id)))"
    )
    assert found == {
        "session_delete": ("d", True, read_or_delete, ""),
        "session_select": ("r", True, read_or_delete, ""),
        "session_insert": (
            "a",
            True,
            "",
            "((tenant_id = ( SELECT app.current_tenant_id() AS current_tenant_id)) AND"
            " (expires_at <= ( SELECT t.expires_at FROM tenants t"
            " WHERE (t.id = sessions.tenant_id))))",
        ),
    }


async def test_a_bare_select_with_no_context_sees_nothing(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await start(app_engine, tenant, tenant.hr_id)

    async with tenant_session(app_engine, NO_TENANT) as session:
        visible: list[object] = list((await session.execute(ALL_SESSIONS)).all())

    assert visible == []


async def test_a_select_with_a_presented_hash_sees_that_row_only(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()
    tokens = await start(app_engine, mine, mine.hr_id)
    await start(app_engine, theirs, theirs.hr_id)

    async with tenant_session(app_engine, NO_TENANT) as session:
        await session.execute(SET_SESSION_LOOKUP, {"hash": tokens.session_hash.hex()})
        visible: list[bytes] = list((await session.execute(ALL_SESSIONS)).scalars())

    assert visible == [tokens.session_hash]


async def test_a_tenant_context_sees_that_sandboxs_sessions_and_no_others(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()
    mine_tokens = await start(app_engine, mine, mine.hr_id)
    theirs_tokens = await start(app_engine, theirs, theirs.hr_id)

    async with tenant_session(app_engine, TenantContext(mine.id, None)) as session:
        visible: set[bytes] = set((await session.execute(ALL_SESSIONS)).scalars())
        count = await session.scalar(text("SELECT count(*) FROM sessions"))

    assert mine_tokens.session_hash in visible
    assert theirs_tokens.session_hash not in visible
    assert count == 2  # make_tenant's own session, and the one started here.


async def test_with_its_own_context_or_none_the_login_cannot_insert_a_session_for_another_sandbox(
    app_engine: AsyncEngine, make_tenant: MakeTenant, owner_engine: AsyncEngine
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()
    forged = sha256_of_random_token()
    expires_at = await tenant_expires_at(owner_engine, theirs.id)
    values = {
        "token_hash": forged,
        "csrf_hash": sha256_of_random_token(),
        "tenant_id": theirs.id,
        "person_id": theirs.hr_id,
        "expires_at": expires_at,
    }

    # What this proves: with its own sandbox's context, or none, the app's login can't insert a
    # session for another sandbox. It does not stop raw SQL that sets another sandbox's context
    # first (see the accepted-risk test below).
    for context in (TenantContext(mine.id, None), NO_TENANT):
        with pytest.raises(ProgrammingError, match="row-level security"):
            async with tenant_session(app_engine, context) as session:
                await session.execute(FORGED_INSERT, values)

    assert await surviving(owner_engine, forged) == set()


async def test_accepted_risk_the_login_can_set_another_sandboxs_context_and_insert_there(
    app_engine: AsyncEngine, make_tenant: MakeTenant, owner_engine: AsyncEngine
) -> None:
    """Documents a residual risk the threat model accepts: the app's login password is a
    full-access secret. Row-level security trusts the transaction's own `app.tenant_id`, and raw
    SQL as `od_app_login` can set that itself. The insert then passes for any sandbox, but the
    expiry is still capped at that sandbox's."""
    mine, theirs = await make_tenant(), await make_tenant()
    expires_at = await tenant_expires_at(owner_engine, theirs.id)
    set_context = text("SELECT set_config('app.tenant_id', :tenant_id, true)")

    def values(token_hash: bytes, when) -> dict[str, object]:  # type: ignore[no-untyped-def]
        return {
            "token_hash": token_hash,
            "csrf_hash": sha256_of_random_token(),
            "tenant_id": theirs.id,
            "person_id": theirs.hr_id,
            "expires_at": when,
        }

    planted = sha256_of_random_token()
    async with tenant_session(app_engine, TenantContext(mine.id, None)) as session:
        await session.execute(set_context, {"tenant_id": str(theirs.id)})
        await session.execute(FORGED_INSERT, values(planted, expires_at))
    assert await surviving(owner_engine, planted) == {planted}

    too_late = sha256_of_random_token()
    late = values(too_late, expires_at + timedelta(seconds=1))

    async def insert_too_late() -> None:
        async with tenant_session(app_engine, TenantContext(mine.id, None)) as session:
            await session.execute(set_context, {"tenant_id": str(theirs.id)})
            await session.execute(FORGED_INSERT, late)

    with pytest.raises(ProgrammingError, match="row-level security"):
        await insert_too_late()
    assert await surviving(owner_engine, too_late) == set()


async def test_an_insert_cannot_outlive_its_sandbox(
    app_engine: AsyncEngine, make_tenant: MakeTenant, owner_engine: AsyncEngine
) -> None:
    tenant = await make_tenant()
    expires_at = await tenant_expires_at(owner_engine, tenant.id)
    base = {
        "csrf_hash": sha256_of_random_token(),
        "tenant_id": tenant.id,
        "person_id": tenant.hr_id,
    }
    too_late = {
        **base,
        "token_hash": sha256_of_random_token(),
        "expires_at": expires_at + timedelta(seconds=1),
    }
    just_right = {**base, "token_hash": sha256_of_random_token(), "expires_at": expires_at}

    with pytest.raises(ProgrammingError, match="row-level security"):
        async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
            await session.execute(FORGED_INSERT, too_late)
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        await session.execute(FORGED_INSERT, just_right)

    assert await surviving(owner_engine, too_late["token_hash"]) == set()
    assert await surviving(owner_engine, just_right["token_hash"]) == {just_right["token_hash"]}


async def test_a_delete_outside_the_sandbox_and_not_the_presented_hash_deletes_nothing(
    app_engine: AsyncEngine, make_tenant: MakeTenant, owner_engine: AsyncEngine
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()
    theirs_tokens = await start(app_engine, theirs, theirs.hr_id)
    other_tokens = await start(app_engine, mine, mine.hr_id)

    async with tenant_session(app_engine, TenantContext(mine.id, None)) as session:
        await session.execute(SET_SESSION_LOOKUP, {"hash": other_tokens.session_hash.hex()})
        result = await session.execute(
            text("DELETE FROM sessions WHERE token_hash = :hash"),
            {"hash": theirs_tokens.session_hash},
        )
        deleted_everything = await session.execute(text("DELETE FROM sessions WHERE true"))

    assert result.rowcount == 0  # type: ignore[attr-defined]
    assert deleted_everything.rowcount == 2  # type: ignore[attr-defined]  # mine only
    assert await surviving(owner_engine, theirs_tokens.session_hash) == {theirs_tokens.session_hash}


async def test_a_bare_delete_with_no_context_deletes_nothing(
    app_engine: AsyncEngine, make_tenant: MakeTenant, owner_engine: AsyncEngine
) -> None:
    tenant = await make_tenant()
    tokens = await start(app_engine, tenant, tenant.hr_id)

    async with tenant_session(app_engine, NO_TENANT) as session:
        result = await session.execute(text("DELETE FROM sessions"))

    assert result.rowcount == 0  # type: ignore[attr-defined]
    assert await surviving(owner_engine, tokens.session_hash) == {tokens.session_hash}


async def test_the_presented_hash_may_be_deleted_with_no_tenant(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    tokens = await start(app_engine, tenant, tenant.hr_id)

    async with tenant_session(app_engine, NO_TENANT) as session:
        assert await end_session(session, tokens.session_hash) is True

    assert await lookup(app_engine, tokens) is None


async def test_the_api_login_has_no_update_on_sessions(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
            await session.execute(text("UPDATE sessions SET expires_at = expires_at"))


# --- The family ---------------------------------------------------------------------------


async def test_family_id_is_required(
    app_engine: AsyncEngine, make_tenant: MakeTenant, owner_engine: AsyncEngine
) -> None:
    tenant = await make_tenant()
    async with owner_engine.connect() as connection:
        nullable = await connection.scalar(
            text(
                "SELECT is_nullable FROM information_schema.columns"
                " WHERE table_name = 'sessions' AND column_name = 'family_id'"
            )
        )
    expires_at = await tenant_expires_at(owner_engine, tenant.id)

    with pytest.raises(DBAPIError, match="family_id"):
        async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
            await session.execute(
                text(
                    "INSERT INTO sessions (token_hash, csrf_hash, tenant_id, person_id, expires_at)"
                    " VALUES (:t, :c, :tenant, :person, :expires)"
                ),
                {
                    "t": sha256_of_random_token(),
                    "c": sha256_of_random_token(),
                    "tenant": tenant.id,
                    "person": tenant.hr_id,
                    "expires": expires_at,
                },
            )

    assert nullable == "NO"


async def test_each_new_session_starts_a_family_and_a_switch_copies_it(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    first = await start(app_engine, tenant, tenant.employee_id)
    second = await start(app_engine, tenant, tenant.colleague_id)
    first_record, second_record = await lookup(app_engine, first), await lookup(app_engine, second)
    assert first_record is not None
    assert second_record is not None
    assert first_record.family_id != second_record.family_id

    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        rotated = await rotate_session(session, first_record, tenant.hr_id)
    rotated_record = await lookup(app_engine, rotated)

    assert rotated_record is not None
    assert rotated_record.family_id == first_record.family_id
    assert rotated_record.token_hash != first_record.token_hash


async def test_starting_a_session_in_a_named_family_joins_it(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    family = uuid4()
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        tokens = await start_session(session, tenant.id, tenant.hr_id, family_id=family)

    record = await lookup(app_engine, tokens)

    assert record is not None
    assert record.family_id == family


async def test_ending_a_family_deletes_every_session_in_it_and_no_others(
    app_engine: AsyncEngine, make_tenant: MakeTenant, owner_engine: AsyncEngine
) -> None:
    tenant = await make_tenant()
    family = uuid4()
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        one = await start_session(session, tenant.id, tenant.hr_id, family_id=family)
        two = await start_session(session, tenant.id, tenant.employee_id, family_id=family)
    unrelated = await start(app_engine, tenant, tenant.colleague_id)
    record = await lookup(app_engine, one)
    assert record is not None

    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        assert await end_session_family(session, record) is True
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        assert await end_session_family(session, record) is False

    assert await surviving(owner_engine, one.session_hash, two.session_hash) == set()
    assert await surviving(owner_engine, unrelated.session_hash) == {unrelated.session_hash}


async def test_a_family_never_reaches_into_another_sandbox(
    app_engine: AsyncEngine, make_tenant: MakeTenant, owner_engine: AsyncEngine
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()
    family = uuid4()
    async with tenant_session(app_engine, TenantContext(theirs.id, None)) as session:
        victim = await start_session(session, theirs.id, theirs.hr_id, family_id=family)
    own = await start(app_engine, mine, mine.hr_id)
    record = await lookup(app_engine, own)
    assert record is not None
    # A record that names the other sandbox's family, as a forged one would.
    forged = SessionRecord(
        record.token_hash, record.csrf_hash, mine.id, record.person_id, record.expires_at, family
    )

    async with tenant_session(app_engine, TenantContext(mine.id, None)) as session:
        await end_session_family(session, forged)

    assert await surviving(owner_engine, victim.session_hash) == {victim.session_hash}


# --- The family race ----------------------------------------------------------------------


async def test_a_sign_out_whose_lookup_came_before_a_switch_still_ends_the_replacement(
    app_engine: AsyncEngine, make_tenant: MakeTenant, owner_engine: AsyncEngine
) -> None:
    """The interleaving the backlog names: the sign-out finds T, a switch T -> T2 commits in
    another transaction, then the sign-out's delete runs. It must remove T2 too."""
    tenant = await make_tenant()
    tokens = await start(app_engine, tenant, tenant.employee_id)

    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as signing_out:
        found = await find_session(signing_out, tokens.session_hash)
        assert found is not None
        # The switch commits here, in a transaction of its own.
        async with tenant_session(app_engine, TenantContext(tenant.id, None)) as switching:
            replacement = await rotate_session(switching, found, tenant.hr_id)
        assert await surviving(owner_engine, replacement.session_hash) == {replacement.session_hash}
        ended = await end_session_family(signing_out, found)

    assert ended is True
    assert await surviving(owner_engine, tokens.session_hash, replacement.session_hash) == set()


async def test_a_sign_out_waits_for_a_switch_that_has_not_committed_and_then_ends_the_replacement(
    app_engine: AsyncEngine, make_tenant: MakeTenant, owner_engine: AsyncEngine
) -> None:
    """The window under READ COMMITTED: the switch has deleted T and inserted T2 but not
    committed. The sign-out's delete of T blocks on the switch's row lock, and its family delete
    then runs as a new statement, so it sees T2."""
    tenant = await make_tenant()
    tokens = await start(app_engine, tenant, tenant.employee_id)
    found = await lookup(app_engine, tokens)
    assert found is not None
    context = TenantContext(tenant.id, None)
    switch_has_written = asyncio.Event()
    sign_out_has_started = asyncio.Event()
    replacement: list[SessionTokens] = []

    async def switch() -> None:
        async with tenant_session(app_engine, context) as db:
            replacement.append(await rotate_session(db, found, tenant.hr_id))
            switch_has_written.set()
            await sign_out_has_started.wait()
            # Let the sign-out reach its blocked DELETE before this transaction commits.
            await asyncio.sleep(0.5)

    async def sign_out() -> bool:
        await switch_has_written.wait()
        async with tenant_session(app_engine, context) as db:
            sign_out_has_started.set()
            return await end_session_family(db, found)

    _, ended = await asyncio.gather(switch(), sign_out())

    assert ended is True
    assert await surviving(owner_engine, tokens.session_hash, replacement[0].session_hash) == set()


async def test_a_switch_that_starts_after_the_sign_out_finds_the_session_gone(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    tokens = await start(app_engine, tenant, tenant.employee_id)
    found = await lookup(app_engine, tokens)
    assert found is not None
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as db:
        await end_session_family(db, found)

    with pytest.raises(SessionGoneError):
        async with tenant_session(app_engine, TenantContext(tenant.id, None)) as db:
            await rotate_session(db, found, tenant.hr_id)
