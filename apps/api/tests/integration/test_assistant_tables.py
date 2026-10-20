"""The assistant's tables (migration 0008): who sees a row, what the API may change, and the rules
the schema holds on its own.

A person's conversations, messages, turns, and feedback are visible to that person alone. HR is
not an exception in Phase 4. The sandbox's spending ledger is the sandbox's own.
"""

from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import AiConversation, AiFeedback, AiMessage, AiTurn
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.sandbox.seed import SeedCompany
from tests.integration.conftest import (
    AssistantRows,
    MakeTenant,
    SampleTenant,
    write_assistant_rows,
)
from tests.integration.test_cleanup import delete_tenant, rows_left

pytestmark = pytest.mark.integration

PERSON_OWNED_TABLES = ("ai_conversations", "ai_messages", "ai_turns", "ai_feedback")
TENANT_TABLES = (*PERSON_OWNED_TABLES, "ai_spend")
# What write_assistant_rows adds: one conversation, one turn, two messages, one thumbs-up, one
# spend row.
ROWS_WRITTEN = {
    "ai_conversations": 1,
    "ai_messages": 2,
    "ai_turns": 1,
    "ai_feedback": 1,
    "ai_spend": 1,
}


def persona(company: SeedCompany, key: str) -> UUID:
    return next(p.id for p in company.people if p.persona_key == key)


async def count(session: AsyncSession, table: str) -> int:
    # The table name comes from the constants above, never from input.
    return (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608


async def counts(session: AsyncSession) -> dict[str, int]:
    return {table: await count(session, table) for table in TENANT_TABLES}


async def priyas_rows(app_engine: AsyncEngine, company: SeedCompany) -> AssistantRows:
    priya = persona(company, "priya")
    async with tenant_session(app_engine, TenantContext(company.tenant_id, priya)) as session:
        return await write_assistant_rows(session, company.tenant_id, priya)


async def test_a_person_sees_their_own_rows(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    await priyas_rows(app_engine, seeded_sandbox)
    priya = persona(seeded_sandbox, "priya")

    async with tenant_session(
        app_engine, TenantContext(seeded_sandbox.tenant_id, priya)
    ) as session:
        assert await counts(session) == ROWS_WRITTEN


@pytest.mark.parametrize("who", ["marcus", "dana"])
async def test_nobody_else_sees_a_persons_conversation_not_even_hr(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, who: str
) -> None:
    await priyas_rows(app_engine, seeded_sandbox)
    other = persona(seeded_sandbox, who)

    async with tenant_session(
        app_engine, TenantContext(seeded_sandbox.tenant_id, other)
    ) as session:
        # Dana is HR. The flag opens the private-details rule, and must not open this one.
        await set_is_hr(session, who == "dana")
        seen = await counts(session)

    for table in PERSON_OWNED_TABLES:
        assert seen[table] == 0, table
    # The spending ledger has no person: the sandbox's budget is everyone's together.
    assert seen["ai_spend"] == ROWS_WRITTEN["ai_spend"]


async def test_a_session_with_no_person_sees_no_conversations(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    await priyas_rows(app_engine, seeded_sandbox)

    async with tenant_session(app_engine, TenantContext(seeded_sandbox.tenant_id, None)) as session:
        seen = await counts(session)

    assert {table: seen[table] for table in PERSON_OWNED_TABLES} == dict.fromkeys(
        PERSON_OWNED_TABLES, 0
    )


async def test_a_person_cannot_write_a_row_that_belongs_to_someone_else(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    rows = await priyas_rows(app_engine, seeded_sandbox)
    priya, marcus = persona(seeded_sandbox, "priya"), persona(seeded_sandbox, "marcus")
    tenant_id = seeded_sandbox.tenant_id

    # Each is a row for Priya, written in Marcus's transaction.
    def conversation() -> object:
        return AiConversation(
            tenant_id=tenant_id,
            person_id=priya,
            model="m",
            guard_model="g",
            effort="medium",
            prompt_version="1",
            toolset_version="1",
        )

    def turn() -> object:
        return AiTurn(
            tenant_id=tenant_id,
            person_id=priya,
            conversation_id=rows.conversation_id,
            question="q",
            status="completed",
        )

    def message() -> object:
        return AiMessage(
            tenant_id=tenant_id,
            person_id=priya,
            conversation_id=rows.conversation_id,
            turn_id=rows.turn_id,
            position=9,
            role="user",
            content=[],
        )

    def feedback() -> object:
        return AiFeedback(tenant_id=tenant_id, person_id=priya, turn_id=rows.turn_id, helpful=False)

    for make in (conversation, turn, message, feedback):
        with pytest.raises(DBAPIError, match="violates row-level security policy"):
            async with tenant_session(app_engine, TenantContext(tenant_id, marcus)) as session:
                session.add(make())


async def test_a_person_cannot_add_to_someone_elses_conversation(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    # Marcus writes rows that are his own, but name Priya's conversation and turn. Postgres checks
    # foreign keys without row-level security, so the keys themselves must carry the owner.
    rows = await priyas_rows(app_engine, seeded_sandbox)
    priya, marcus = persona(seeded_sandbox, "priya"), persona(seeded_sandbox, "marcus")
    tenant_id = seeded_sandbox.tenant_id
    # A turn of hers with no feedback yet: the unique rule would otherwise answer first.
    unrated_turn = uuid4()
    async with tenant_session(app_engine, TenantContext(tenant_id, priya)) as session:
        session.add(
            AiTurn(
                id=unrated_turn,
                tenant_id=tenant_id,
                person_id=priya,
                conversation_id=rows.conversation_id,
                question="q",
                status="completed",
            )
        )

    def turn_in_her_conversation() -> object:
        return AiTurn(
            tenant_id=tenant_id,
            person_id=marcus,
            conversation_id=rows.conversation_id,
            question="q",
            status="completed",
        )

    def message_in_her_conversation() -> object:
        return AiMessage(
            tenant_id=tenant_id,
            person_id=marcus,
            conversation_id=rows.conversation_id,
            turn_id=rows.turn_id,
            position=9,
            role="user",
            content=[],
        )

    def feedback_on_her_turn() -> object:
        return AiFeedback(tenant_id=tenant_id, person_id=marcus, turn_id=unrated_turn, helpful=True)

    for make in (turn_in_her_conversation, message_in_her_conversation, feedback_on_her_turn):
        with pytest.raises(IntegrityError, match="violates foreign key constraint"):
            async with tenant_session(app_engine, TenantContext(tenant_id, marcus)) as session:
                session.add(make())


# Statements the API's login must not be allowed to run. Postgres refuses them at the privilege
# check, before any row is touched, so they need no matching rows and no tenant.
NOT_ALLOWED = [
    *(
        (table, verb)
        for table in (
            "ai_conversations",
            "ai_messages",
            "ai_feedback",
            "ai_spend",
            "ai_spend_daily",
        )
        for verb in ("UPDATE", "DELETE")
    ),
    ("ai_turns", "DELETE"),
]
# Every table named above has a created_at except ai_turns, which is listed for DELETE only.
STATEMENTS = {
    "UPDATE": "UPDATE {table} SET created_at = created_at",
    "DELETE": "DELETE FROM {table}",
}


@pytest.mark.parametrize(("table", "verb"), NOT_ALLOWED)
async def test_the_api_cannot_change_or_delete_what_it_has_added(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, table: str, verb: str
) -> None:
    await priyas_rows(app_engine, seeded_sandbox)
    priya = persona(seeded_sandbox, "priya")
    statement = STATEMENTS[verb].format(table=table)

    with pytest.raises(DBAPIError, match=f"permission denied for table {table}"):
        async with tenant_session(
            app_engine, TenantContext(seeded_sandbox.tenant_id, priya)
        ) as session:
            await session.execute(text(statement))


@pytest.mark.parametrize(
    "column", ["id", "tenant_id", "person_id", "conversation_id", "question", "started_at"]
)
async def test_a_turns_identity_question_and_start_can_never_be_updated(
    app_engine: AsyncEngine, make_tenant: MakeTenant, column: str
) -> None:
    tenant = await make_tenant()
    context = TenantContext(tenant.id, tenant.employee_id)
    async with tenant_session(app_engine, context) as session:
        await new_turn(session, tenant, await a_conversation(session), "running")

    # Even while the turn is running, so it is the grant that refuses, not the trigger.
    with pytest.raises(DBAPIError, match="permission denied for table ai_turns"):
        async with tenant_session(app_engine, context) as session:
            await session.execute(text(f"UPDATE ai_turns SET {column} = {column}"))  # noqa: S608


async def test_a_running_turn_can_be_finished_once(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    context = TenantContext(tenant.id, tenant.employee_id)
    async with tenant_session(app_engine, context) as session:
        turn_id = await new_turn(session, tenant, await a_conversation(session), "running")

    async with tenant_session(app_engine, context) as session:
        # The answer so far, then the end: a running turn can be updated more than once.
        await session.execute(
            text("UPDATE ai_turns SET answer_text = 'Partly' WHERE id = :id"), {"id": turn_id}
        )
        finished = await session.scalars(
            text(
                "UPDATE ai_turns SET status = 'completed', ended_at = now(),"
                " answer_text = 'Done', cost_usd = 0.12, tool_calls = '[]'::jsonb"
                " WHERE id = :id RETURNING id"
            ),
            {"id": turn_id},
        )
        assert list(finished) == [turn_id]

    for statement in (
        "UPDATE ai_turns SET answer_text = 'Changed' WHERE id = :id",
        "UPDATE ai_turns SET status = 'running' WHERE id = :id",
        "UPDATE ai_turns SET cost_usd = 0 WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="a finished turn cannot be changed") as raised:
            async with tenant_session(app_engine, context) as session:
                await session.execute(text(statement), {"id": turn_id})
        # A code of its own (class OD is ours, like 0005's OD001), so code can tell this refusal
        # from any other without reading the message.
        assert getattr(raised.value.orig, "sqlstate", None) == "OD002"


async def test_an_abandoned_running_turn_can_be_marked_failed(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    context = TenantContext(tenant.id, tenant.employee_id)
    async with tenant_session(app_engine, context) as session:
        turn_id = await new_turn(session, tenant, await a_conversation(session), "running")

    async with tenant_session(app_engine, context) as session:
        marked = await session.scalars(
            text(
                "UPDATE ai_turns SET status = 'failed', error_code = 'internal', ended_at = now()"
                " WHERE id = :id RETURNING id"
            ),
            {"id": turn_id},
        )
        assert list(marked) == [turn_id]


TODAY = "(now() AT TIME ZONE 'UTC')::date"

# Both ledgers refuse the same nonsense, under their own constraint names. A reservation is never
# negative, and no amount passes 10 either way: one call's worst case is under $1, so the bound
# only stops a runaway or hostile row from resetting a cap.
AMOUNT_VIOLATIONS = [
    ("reserve", "-0.01", "reserve_not_negative"),
    ("settle", "10.01", "amount_range"),
    ("settle", "-10.01", "amount_range"),
    ("reserve", "10.01", "amount_range"),
]
AMOUNTS_ACCEPTED = [("reserve", "0.5"), ("reserve", "0"), ("settle", "-0.2"), ("settle", "0.05")]


async def insert_spend(session: AsyncSession, tenant: SampleTenant, kind: str, amount: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ai_spend (tenant_id, turn_id, kind, amount_usd)"
            " SELECT tenant_id, id, :kind, :amount FROM ai_turns"
        ),
        {"kind": kind, "amount": Decimal(amount)},
    )


@pytest.mark.parametrize(("kind", "amount", "constraint"), AMOUNT_VIOLATIONS)
async def test_the_sandbox_ledger_refuses_nonsense_amounts(
    app_engine: AsyncEngine, make_tenant: MakeTenant, kind: str, amount: str, constraint: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match=f"ck_ai_spend_{constraint}"):
        async with tenant_session(
            app_engine, TenantContext(tenant.id, tenant.employee_id)
        ) as session:
            await insert_spend(session, tenant, kind, amount)


@pytest.mark.parametrize(("kind", "amount"), AMOUNTS_ACCEPTED)
async def test_the_sandbox_ledger_takes_a_reserve_and_a_negative_settle(
    app_engine: AsyncEngine, make_tenant: MakeTenant, kind: str, amount: str
) -> None:
    tenant = await make_tenant()

    async with tenant_session(app_engine, TenantContext(tenant.id, tenant.employee_id)) as session:
        await insert_spend(session, tenant, kind, amount)


async def insert_daily(
    engine: AsyncEngine,
    tenant: SampleTenant,
    kind: str,
    amount: str,
    *,
    day: str = TODAY,
    created_at: str = "now()",
) -> UUID:
    row_id = uuid4()
    async with tenant_session(engine, TenantContext(tenant.id, tenant.employee_id)) as session:
        await session.execute(
            text(
                "INSERT INTO ai_spend_daily (id, kind, amount_usd, day, created_at)"  # noqa: S608
                f" VALUES (:id, :kind, :amount, {day}, {created_at})"
            ),
            {"id": row_id, "kind": kind, "amount": Decimal(amount)},
        )
    return row_id


@pytest.fixture
async def daily_rows(owner_engine: AsyncEngine) -> AsyncIterator[list[UUID]]:
    """The ledger rows a test added. The API can't delete them, so the owner does afterward."""
    ids: list[UUID] = []
    yield ids
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM ai_spend_daily WHERE id = ANY(:ids)"), {"ids": ids}
        )


@pytest.mark.parametrize(("kind", "amount", "constraint"), AMOUNT_VIOLATIONS)
async def test_the_daily_ledger_refuses_nonsense_amounts(
    app_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_rows: list[UUID],
    kind: str,
    amount: str,
    constraint: str,
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match=f"ck_ai_spend_daily_{constraint}"):
        daily_rows.append(await insert_daily(app_engine, tenant, kind, amount))


async def test_the_daily_ledger_refuses_an_unknown_kind(
    app_engine: AsyncEngine, make_tenant: MakeTenant, daily_rows: list[UUID]
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match="ck_ai_spend_daily_kind"):
        daily_rows.append(await insert_daily(app_engine, tenant, "refund", "1"))


@pytest.mark.parametrize("day", [f"{TODAY} - 1", f"{TODAY} + 1", "DATE '2000-01-01'"])
async def test_the_daily_ledger_refuses_a_row_for_another_day(
    app_engine: AsyncEngine, make_tenant: MakeTenant, daily_rows: list[UUID], day: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match="ck_ai_spend_daily_day_matches_created_at"):
        daily_rows.append(await insert_daily(app_engine, tenant, "reserve", "0.5", day=day))


async def test_a_settle_row_may_land_on_the_reservations_day_across_midnight(
    app_engine: AsyncEngine, make_tenant: MakeTenant, daily_rows: list[UUID]
) -> None:
    # A reservation made at 23:59:59 and settled at 00:00:05 belongs to the day before. Forcing the
    # settle onto the new day would credit it with yesterday's unused reservation.
    tenant = await make_tenant()
    daily_rows.append(await insert_daily(app_engine, tenant, "settle", "-0.2", day=f"{TODAY} - 1"))


@pytest.mark.parametrize(
    ("kind", "amount", "day"),
    [
        ("reserve", "0.1", f"{TODAY} - 1"),
        ("settle", "-0.1", f"{TODAY} - 2"),
        ("settle", "-0.1", f"{TODAY} + 1"),
    ],
)
async def test_only_a_settle_may_be_dated_yesterday_and_nothing_else_off_today(
    app_engine: AsyncEngine,
    make_tenant: MakeTenant,
    daily_rows: list[UUID],
    kind: str,
    amount: str,
    day: str,
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match="ck_ai_spend_daily_day_matches_created_at"):
        daily_rows.append(await insert_daily(app_engine, tenant, kind, amount, day=day))


async def test_the_daily_ledger_stamps_its_own_time_and_day(
    app_engine: AsyncEngine, make_tenant: MakeTenant, daily_rows: list[UUID]
) -> None:
    tenant = await make_tenant()
    # A caller that picks a created_at in the past, to match a back-dated day, is overruled.
    with pytest.raises(IntegrityError, match="ck_ai_spend_daily_day_matches_created_at"):
        daily_rows.append(
            await insert_daily(
                app_engine,
                tenant,
                "reserve",
                "0.5",
                day="DATE '2000-01-01'",
                created_at="TIMESTAMPTZ '2000-01-01 12:00+00'",
            )
        )

    # Omitting both takes today, from the same moment.
    row_id = uuid4()
    daily_rows.append(row_id)
    async with tenant_session(app_engine, TenantContext(tenant.id, tenant.employee_id)) as session:
        await session.execute(
            text("INSERT INTO ai_spend_daily (id, kind, amount_usd) VALUES (:id, 'reserve', 0.5)"),
            {"id": row_id},
        )
        stamped = (
            await session.execute(
                text(
                    "SELECT day = (now() AT TIME ZONE 'UTC')::date, created_at = now()"
                    " FROM ai_spend_daily WHERE id = :id"
                ),
                {"id": row_id},
            )
        ).one()
    assert tuple(stamped) == (True, True)


async def test_the_daily_ledger_takes_rows_with_no_tenant(
    app_engine: AsyncEngine, make_tenant: MakeTenant, daily_rows: list[UUID]
) -> None:
    sandbox, other = await make_tenant(), await make_tenant()
    query = "SELECT coalesce(sum(amount_usd), 0) FROM ai_spend_daily WHERE day = " + TODAY  # noqa: S608
    total = text(query)

    async def sandbox_sees() -> Decimal:
        async with tenant_session(
            app_engine, TenantContext(sandbox.id, sandbox.employee_id)
        ) as session:
            return (await session.execute(total)).scalar_one()

    before = await sandbox_sees()
    # Each sandbox adds to the same day, and each sees the other's amount: that is its purpose. A
    # settle takes back part of a reservation.
    daily_rows.append(await insert_daily(app_engine, sandbox, "reserve", "0.50"))
    daily_rows.append(await insert_daily(app_engine, other, "reserve", "0.25"))
    daily_rows.append(await insert_daily(app_engine, other, "settle", "-0.10"))

    assert await sandbox_sees() - before == Decimal("0.65")


async def test_a_message_can_carry_its_search_sources(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    rows = await priyas_rows(app_engine, seeded_sandbox)
    priya = persona(seeded_sandbox, "priya")
    tenant_id = seeded_sandbox.tenant_id
    sources = [
        {
            "sectionId": "CA-4.3",
            "passageIds": [["p1", "p2"]],
            "title": "Sick leave",
            "groupName": "California addendum",
            "audienceLabel": "California",
            "lastUpdated": "2026-09-12",
            "deepLink": "/handbook/CA-4.3?passage=p1",
        }
    ]

    async with tenant_session(app_engine, TenantContext(tenant_id, priya)) as session:
        session.add(
            AiMessage(
                tenant_id=tenant_id,
                person_id=priya,
                conversation_id=rows.conversation_id,
                turn_id=rows.turn_id,
                position=2,
                role="user",
                content=[],
                sources=sources,
            )
        )
    async with tenant_session(app_engine, TenantContext(tenant_id, priya)) as session:
        stored = (
            await session.execute(text("SELECT position, sources FROM ai_messages ORDER BY 1"))
        ).all()

    # The fixture's two messages have none; the third has its sources back, as written.
    assert [tuple(row) for row in stored] == [(0, None), (1, None), (2, sources)]


async def test_the_ledgers_are_indexed_for_the_sums_under_the_lock(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as connection:
        indexes = set(
            await connection.scalars(
                text(
                    "SELECT indexname FROM pg_indexes"
                    " WHERE tablename IN ('ai_spend', 'ai_spend_daily')"
                )
            )
        )

    # The sandbox's sum is served by the prefix of (tenant_id, turn_id), which the foreign key to
    # the turn needs as well. The old tenant_id-only index is gone.
    assert {"ix_ai_spend_tenant_id_turn_id", "ix_ai_spend_daily_day"} <= indexes
    assert "ix_ai_spend_tenant_id" not in indexes


FOREIGN_KEY_COLUMNS = """
    SELECT c.conrelid::regclass::text, c.conname,
           ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(attnum, ord)
                 JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
                 ORDER BY k.ord)::text[]
    FROM pg_constraint c
    WHERE c.contype = 'f' AND c.conrelid::regclass::text LIKE 'ai\\_%' ESCAPE '\\'
"""
INDEX_COLUMNS = """
    SELECT i.indrelid::regclass::text,
           ARRAY(SELECT a.attname FROM unnest(i.indkey::int2[]) WITH ORDINALITY k(attnum, ord)
                 JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                 WHERE k.attnum > 0 ORDER BY k.ord)::text[]
    FROM pg_index i
    WHERE i.indrelid::regclass::text LIKE 'ai\\_%' ESCAPE '\\'
"""


async def test_every_foreign_key_of_the_assistant_tables_has_an_index_to_check_deletes_with(
    app_engine: AsyncEngine,
) -> None:
    # Deleting a sandbox deletes its turns, and each deleted turn looks for rows that refer to it.
    # Without an index that starts with the referencing columns, each look is a scan of the
    # sandbox's rows. The keys' first two columns are tenant_id and the thing referred to.
    async with app_engine.connect() as connection:
        foreign_keys = (await connection.execute(text(FOREIGN_KEY_COLUMNS))).all()
        indexes = (await connection.execute(text(INDEX_COLUMNS))).all()

    assert len(foreign_keys) >= 10
    unindexed = [
        (table, name)
        for table, name, columns in foreign_keys
        if not any(
            index_table == table and index_columns[: min(len(columns), 2)] == columns[:2]
            for index_table, index_columns in indexes
        )
    ]
    assert unindexed == []


# The rule that makes a row visible only to its person is the second, restrictive policy.
POLICIES = """
    SELECT c.relname, p.polname, p.polpermissive, p.polcmd::text, p.polroles::regrole[]::text[],
           pg_get_expr(p.polqual, p.polrelid), pg_get_expr(p.polwithcheck, p.polrelid)
    FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
    WHERE c.relname = ANY(:tables) AND NOT p.polpermissive
"""


async def test_the_person_rule_is_a_restrictive_policy_on_exactly_the_four_person_tables(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as connection:
        rows = (await connection.execute(text(POLICIES), {"tables": list(TENANT_TABLES)})).all()

    expression = "(person_id = ( SELECT app.current_person_id() AS current_person_id))"
    assert sorted(rows) == sorted(
        (table, "own_rows", False, "*", ["od_app"], expression, expression)
        for table in PERSON_OWNED_TABLES
    )


# Postgres `json` keeps the text it was given. Task 5's history must go back to the API with its
# keys in the order the API sent them, because a thinking block is signed over its exact bytes.
EXACT_JSON = '[{"type":"thinking",  "signature": "abc", "thinking": "b a",  "z": 1, "a": 2}]'


async def test_message_content_comes_back_byte_for_byte(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    rows = await priyas_rows(app_engine, seeded_sandbox)
    priya = persona(seeded_sandbox, "priya")
    tenant_id = seeded_sandbox.tenant_id

    async with tenant_session(app_engine, TenantContext(tenant_id, priya)) as session:
        await session.execute(
            text(
                "INSERT INTO ai_messages (tenant_id, person_id, conversation_id, turn_id,"
                " position, role, content) VALUES (:tenant_id, :person_id, :conversation_id,"
                " :turn_id, 2, 'assistant', CAST(:content AS json))"
            ),
            {
                "tenant_id": tenant_id,
                "person_id": priya,
                "conversation_id": rows.conversation_id,
                "turn_id": rows.turn_id,
                "content": EXACT_JSON,
            },
        )
        stored: str = (
            await session.execute(text("SELECT content::text FROM ai_messages WHERE position = 2"))
        ).scalar_one()

    assert stored == EXACT_JSON


async def test_a_message_position_is_used_once_per_conversation(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    rows = await priyas_rows(app_engine, seeded_sandbox)
    priya = persona(seeded_sandbox, "priya")
    tenant_id = seeded_sandbox.tenant_id

    with pytest.raises(IntegrityError, match="uq_ai_messages_tenant_id_conversation_id_position"):
        async with tenant_session(app_engine, TenantContext(tenant_id, priya)) as session:
            session.add(
                AiMessage(
                    tenant_id=tenant_id,
                    person_id=priya,
                    conversation_id=rows.conversation_id,
                    turn_id=rows.turn_id,
                    position=1,  # write_assistant_rows already used 0 and 1.
                    role="user",
                    content=[],
                )
            )


async def test_a_turn_gets_one_feedback_row(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    rows = await priyas_rows(app_engine, seeded_sandbox)
    priya = persona(seeded_sandbox, "priya")
    tenant_id = seeded_sandbox.tenant_id

    with pytest.raises(IntegrityError, match="uq_ai_feedback_tenant_id_turn_id"):
        async with tenant_session(app_engine, TenantContext(tenant_id, priya)) as session:
            session.add(
                AiFeedback(
                    tenant_id=tenant_id, person_id=priya, turn_id=rows.turn_id, helpful=False
                )
            )


@pytest.mark.parametrize(("length", "allowed"), [(500, True), (501, False)])
async def test_feedback_reasons_are_at_most_500_characters(
    app_engine: AsyncEngine, make_tenant: MakeTenant, length: int, allowed: bool
) -> None:
    tenant = await make_tenant()
    context = TenantContext(tenant.id, tenant.employee_id)
    # The fixture's own turn already has its feedback, so the feedback goes on a new turn.
    async with tenant_session(app_engine, context) as session:
        turn_id = await new_turn(session, tenant, await a_conversation(session), "completed")

    async def add_feedback() -> None:
        async with tenant_session(app_engine, context) as session:
            session.add(
                AiFeedback(
                    tenant_id=tenant.id,
                    person_id=tenant.employee_id,
                    turn_id=turn_id,
                    helpful=False,
                    reason="x" * length,
                )
            )

    if allowed:
        await add_feedback()
    else:
        with pytest.raises(IntegrityError, match="ck_ai_feedback_reason_length"):
            await add_feedback()


async def new_turn(
    session: AsyncSession, tenant: SampleTenant, conversation_id: UUID, status: str
) -> UUID:
    turn_id = uuid4()
    session.add(
        AiTurn(
            id=turn_id,
            tenant_id=tenant.id,
            person_id=tenant.employee_id,
            conversation_id=conversation_id,
            question="q",
            status=status,
        )
    )
    await session.flush()
    return turn_id


async def a_conversation(session: AsyncSession) -> UUID:
    return (await session.execute(text("SELECT id FROM ai_conversations"))).scalar_one()


async def test_a_conversation_has_one_running_turn_at_a_time(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    context = TenantContext(tenant.id, tenant.employee_id)
    async with tenant_session(app_engine, context) as session:
        conversation_id = await a_conversation(session)
        await new_turn(session, tenant, conversation_id, "running")

    with pytest.raises(IntegrityError, match="uq_ai_turns_one_running_per_conversation"):
        async with tenant_session(app_engine, context) as session:
            await new_turn(session, tenant, conversation_id, "running")


async def test_a_new_turn_can_run_once_the_last_one_has_ended(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    context = TenantContext(tenant.id, tenant.employee_id)
    async with tenant_session(app_engine, context) as session:
        conversation_id = await a_conversation(session)
        first = await new_turn(session, tenant, conversation_id, "running")

    async with tenant_session(app_engine, context) as session:
        await session.execute(
            text("UPDATE ai_turns SET status = 'completed' WHERE id = :id"), {"id": first}
        )
        await new_turn(session, tenant, conversation_id, "running")
        # Ended turns are never limited: any number of them may sit beside the running one.
        await new_turn(session, tenant, conversation_id, "stopped")
        await new_turn(session, tenant, conversation_id, "failed")


async def test_a_second_conversation_can_run_beside_the_first(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    context = TenantContext(tenant.id, tenant.employee_id)
    async with tenant_session(app_engine, context) as session:
        await new_turn(session, tenant, await a_conversation(session), "running")
        other = AiConversation(
            id=uuid4(),
            tenant_id=tenant.id,
            person_id=tenant.employee_id,
            model="m",
            guard_model="g",
            effort="medium",
            prompt_version="1",
            toolset_version="1",
        )
        session.add(other)
        await session.flush()
        await new_turn(session, tenant, other.id, "running")


@pytest.mark.parametrize(
    ("constraint", "statement"),
    [
        (
            "ck_ai_turns_status",
            "INSERT INTO ai_turns (tenant_id, person_id, conversation_id, question, status)"
            " SELECT tenant_id, person_id, id, 'q', 'done' FROM ai_conversations",
        ),
        (
            "ck_ai_messages_role",
            "INSERT INTO ai_messages (tenant_id, person_id, conversation_id, turn_id, position,"
            " role, content) SELECT tenant_id, person_id, conversation_id, id, 7, 'tool', '[]'"
            " FROM ai_turns",
        ),
        (
            "ck_ai_spend_kind",
            "INSERT INTO ai_spend (tenant_id, turn_id, kind, amount_usd)"
            " SELECT tenant_id, id, 'refund', 1 FROM ai_turns",
        ),
    ],
)
async def test_the_check_constraints_refuse_unknown_values(
    app_engine: AsyncEngine, make_tenant: MakeTenant, constraint: str, statement: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match=constraint):
        async with tenant_session(
            app_engine, TenantContext(tenant.id, tenant.employee_id)
        ) as session:
            await session.execute(text(statement))


async def test_deleting_an_expired_sandbox_removes_every_assistant_row(
    cleanup_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    expired = await make_tenant(expired=True)
    before = await rows_left(owner_engine, expired.id)

    deleted = await delete_tenant(cleanup_engine, expired.id)
    after = await rows_left(owner_engine, expired.id)

    assert deleted == 1
    assert {table: before[table] for table in TENANT_TABLES} == ROWS_WRITTEN
    assert {table: after[table] for table in TENANT_TABLES} == dict.fromkeys(TENANT_TABLES, 0)
