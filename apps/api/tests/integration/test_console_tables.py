"""The console's table (migration 0016): who reads a row, what the schema holds on its own.

`ai_console_turns` has one row for each finished turn, copied as labels. It holds no person ID, no
conversation ID, and no text, and HR alone can read it. A flagged turn's row is redacted when it is
written, and a check constraint refuses a flagged row that holds more. The people in `make_tenant`:
Priya asked the sample turn, Leo is another employee, and Dana is HR. The seeded sandbox adds
Marcus, a manager.
"""

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.sandbox.seed import SeedCompany
from tests.integration.conftest import MakeTenant, SampleTenant

pytestmark = pytest.mark.integration

ENGINE: list[AsyncEngine] = []


@pytest.fixture(autouse=True)
def remember_the_engine(app_engine: AsyncEngine) -> None:
    ENGINE[:] = [app_engine]


@asynccontextmanager
async def as_person(
    tenant_id: UUID, person_id: UUID | None, *, hr: bool = False
) -> AsyncIterator[AsyncSession]:
    """A transaction for `person_id`, with the HR flag set the way the API sets it for Dana."""
    async with tenant_session(ENGINE[0], TenantContext(tenant_id, person_id)) as session:
        if hr:
            await set_is_hr(session, True)
        yield session


async def insert_row(session: AsyncSession, values: dict[str, Any]) -> UUID:
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)
    await session.execute(
        text(f"INSERT INTO ai_console_turns ({columns}) VALUES ({placeholders})"),  # noqa: S608
        values,
    )
    return values["id"]  # type: ignore[no-any-return]


def ordinary(tenant_id: UUID, **overrides: Any) -> dict[str, Any]:
    """An unflagged row with every required column."""
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "turn_id": uuid4(),
        "occurred_on": date(2026, 10, 30),
        "occurred_at": datetime(2026, 10, 30, 17, 0, tzinfo=UTC),
        "flagged": False,
        "asker_role": "manager",
        "asker_location": "Oakland, CA",
        "outcome": "answered",
        "injection_suspected": False,
        "tools": "[]",
        "sections_retrieved": [],
        "sections_cited": [],
        **overrides,
    }


def flagged(tenant_id: UUID, **overrides: Any) -> dict[str, Any]:
    """A redacted row: the date and the counts."""
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "occurred_on": date(2026, 10, 30),
        "flagged": True,
        "input_tokens": 120,
        "cost_usd": "0.004",
        **overrides,
    }


async def count_rows(session: AsyncSession) -> int:
    return int((await session.execute(text("SELECT count(*) FROM ai_console_turns"))).scalar_one())


# --- The table and its columns ---


async def test_the_table_has_the_specs_columns_and_none_that_names_a_person_or_holds_text(
    app_engine: AsyncEngine,
) -> None:
    query = text(
        "SELECT column_name, is_nullable FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = 'ai_console_turns'"
    )
    async with app_engine.connect() as connection:
        found = {name: nullable == "YES" for name, nullable in (await connection.execute(query))}

    not_null = {
        "id",
        "tenant_id",
        "occurred_on",
        "flagged",
        "abandoned",
        "served_by",
        "fallback",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "cost_usd",
    }
    null = {
        "turn_id",
        "occurred_at",
        "asker_role",
        "asker_location",
        "outcome",
        "refusal_category",
        "guard_category",
        "injection_suspected",
        "tools",
        "sections_retrieved",
        "sections_cited",
        "card_action",
        "effort",
        "prompt_version",
        "toolset_version",
        "guard_ms",
        "first_text_ms",
        "total_ms",
    }
    # The exact set: no person_id, conversation_id, or text column can be here unannounced.
    assert found == {**dict.fromkeys(not_null, False), **dict.fromkeys(null, True)}


async def test_no_key_links_a_console_row_to_a_turn_or_a_person(app_engine: AsyncEngine) -> None:
    query = text(
        "SELECT conname FROM pg_constraint"
        " WHERE conrelid = 'ai_console_turns'::regclass AND contype = 'f'"
    )
    async with app_engine.connect() as connection:
        keys: set[str] = set((await connection.execute(query)).scalars())

    assert keys == {"fk_ai_console_turns_tenant_id_tenants"}


# --- The checks ---


async def test_a_flagged_row_with_only_its_counts_is_accepted(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    async with as_person(tenant.id, tenant.employee_id) as session:
        await insert_row(
            session,
            flagged(
                tenant.id,
                served_by=["claude-opus-5-5"],
                effort="medium",
                prompt_version="v1",
                toolset_version="v1",
                guard_ms=300,
                first_text_ms=900,
                total_ms=2000,
            ),
        )


FORBIDDEN_ON_A_FLAGGED_ROW: dict[str, Any] = {
    "turn_id": uuid4(),
    "occurred_at": datetime(2026, 10, 30, 17, 0, tzinfo=UTC),
    "asker_role": "employee",
    "asker_location": "Oakland, CA",
    "outcome": "answered",
    "refusal_category": "general_harms",
    "guard_category": "harassment",
    "injection_suspected": False,
    "tools": "[]",
    "sections_retrieved": ["2.2"],
    "sections_cited": ["2.2"],
    "card_action": "timeoff.request",
}


@pytest.mark.parametrize("column", sorted(FORBIDDEN_ON_A_FLAGGED_ROW))
async def test_the_check_refuses_a_flagged_row_that_holds_anything_but_its_counts(
    make_tenant: MakeTenant, column: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match="ck_ai_console_turns_flagged_row_is_redacted"):
        async with as_person(tenant.id, tenant.employee_id) as session:
            await insert_row(
                session, flagged(tenant.id, **{column: FORBIDDEN_ON_A_FLAGGED_ROW[column]})
            )


@pytest.mark.parametrize(
    "column",
    [
        "turn_id",
        "occurred_at",
        "asker_role",
        "asker_location",
        "outcome",
        "injection_suspected",
        "tools",
        "sections_retrieved",
        "sections_cited",
    ],
)
async def test_the_check_refuses_an_unflagged_row_with_a_required_column_missing(
    make_tenant: MakeTenant, column: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match="ck_ai_console_turns_unflagged_row_is_complete"):
        async with as_person(tenant.id, tenant.employee_id) as session:
            await insert_row(session, ordinary(tenant.id, **{column: None}))


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"outcome": "great"}, "ck_ai_console_turns_outcome"),
        ({"asker_role": "intern"}, "ck_ai_console_turns_asker_role"),
        ({"card_action": "timeoff.approve"}, "ck_ai_console_turns_card_action"),
        ({"input_tokens": -1}, "ck_ai_console_turns_counts_not_negative"),
        ({"output_tokens": -1}, "ck_ai_console_turns_counts_not_negative"),
        ({"cache_read_tokens": -1}, "ck_ai_console_turns_counts_not_negative"),
        ({"cache_write_tokens": -1}, "ck_ai_console_turns_counts_not_negative"),
        ({"cost_usd": "-0.01"}, "ck_ai_console_turns_counts_not_negative"),
        ({"guard_ms": -1}, "ck_ai_console_turns_counts_not_negative"),
        ({"first_text_ms": -1}, "ck_ai_console_turns_counts_not_negative"),
        ({"total_ms": -1}, "ck_ai_console_turns_counts_not_negative"),
    ],
)
async def test_the_checks_refuse_values_outside_the_planned_ones(
    make_tenant: MakeTenant, overrides: dict[str, Any], constraint: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match=constraint):
        async with as_person(tenant.id, tenant.employee_id) as session:
            await insert_row(session, ordinary(tenant.id, **overrides))


@pytest.mark.parametrize("verdict", ["sensitive", "crisis"])
async def test_the_check_refuses_an_unflagged_row_whose_verdict_is_not_ordinary(
    make_tenant: MakeTenant, verdict: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match="ck_ai_console_turns_unflagged_row_is_ordinary"):
        async with as_person(tenant.id, tenant.employee_id) as session:
            await insert_row(session, ordinary(tenant.id, guard_category=verdict))


@pytest.mark.parametrize("verdict", [None, "ordinary"])
async def test_an_unflagged_row_with_an_ordinary_or_no_verdict_is_accepted(
    make_tenant: MakeTenant, verdict: str | None
) -> None:
    tenant = await make_tenant()

    async with as_person(tenant.id, tenant.employee_id) as session:
        await insert_row(session, ordinary(tenant.id, guard_category=verdict))


@pytest.mark.parametrize(
    "category",
    ["", "has space", "9lives", "-dash", "a" * 41, "\u00e9t\u00e9", "good\n", "x;DROP"],
)
async def test_the_check_refuses_a_refusal_category_that_is_not_a_short_word(
    make_tenant: MakeTenant, category: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match="ck_ai_console_turns_refusal_category_is_a_word"):
        async with as_person(tenant.id, tenant.employee_id) as session:
            await insert_row(session, ordinary(tenant.id, refusal_category=category))


@pytest.mark.parametrize("category", [None, "general_harms", "a", "Cyber-harms", "a" * 40])
async def test_a_short_word_refusal_category_is_accepted(
    make_tenant: MakeTenant, category: str | None
) -> None:
    tenant = await make_tenant()

    async with as_person(tenant.id, tenant.employee_id) as session:
        await insert_row(session, ordinary(tenant.id, refusal_category=category))


async def test_the_check_refuses_an_abandoned_row_that_is_not_flagged(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match="ck_ai_console_turns_abandoned_row_is_flagged"):
        async with as_person(tenant.id, tenant.employee_id) as session:
            await insert_row(session, ordinary(tenant.id, abandoned=True))


async def test_an_abandoned_flagged_row_is_accepted_and_the_mark_defaults_to_false(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()

    async with as_person(tenant.id, tenant.employee_id) as session:
        await insert_row(session, flagged(tenant.id, abandoned=True))
        await insert_row(session, flagged(tenant.id))
    async with as_person(tenant.id, tenant.hr_id, hr=True) as session:
        marks: Any = (
            (
                await session.execute(
                    text("SELECT abandoned FROM ai_console_turns WHERE flagged ORDER BY abandoned")
                )
            )
            .scalars()
            .all()
        )
    assert list(marks) == [False, True]


async def test_the_card_action_check_allows_exactly_the_proposal_actions(
    make_tenant: MakeTenant, app_engine: AsyncEngine
) -> None:
    from typing import get_args

    from app.ai.proposal_cards import ProposalAction

    query = text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
        " WHERE conname = 'ck_ai_console_turns_card_action'"
    )
    async with app_engine.connect() as connection:
        definition: str = (await connection.execute(query)).scalar_one()

    allowed = set(re.findall(r"'([a-z.]+)'", definition))
    assert allowed == set(get_args(ProposalAction.__value__))


async def test_the_table_has_no_guard_kind_column(app_engine: AsyncEngine) -> None:
    query = text(
        "SELECT count(*) FROM information_schema.columns"
        " WHERE table_name = 'ai_console_turns' AND column_name = 'guard_kind'"
    )
    async with app_engine.connect() as connection:
        assert (await connection.execute(query)).scalar_one() == 0


@pytest.mark.parametrize(
    "outcome",
    ["answered", "not_found", "refused", "stopped", "failed", "budget", "guard_unavailable"],
)
async def test_every_outcome_the_spec_names_is_accepted(
    make_tenant: MakeTenant, outcome: str
) -> None:
    tenant = await make_tenant()

    async with as_person(tenant.id, tenant.employee_id) as session:
        await insert_row(session, ordinary(tenant.id, outcome=outcome))


@pytest.mark.parametrize("role", ["employee", "manager", "hr"])
async def test_every_asker_role_the_spec_names_is_accepted(
    make_tenant: MakeTenant, role: str
) -> None:
    tenant = await make_tenant()

    async with as_person(tenant.id, tenant.employee_id) as session:
        await insert_row(session, ordinary(tenant.id, asker_role=role))


# --- The rules, as the catalog holds them ---


async def test_row_level_security_is_forced_and_the_restrictive_rule_is_hr_only(
    app_engine: AsyncEngine,
) -> None:
    flags = text(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class"
        " WHERE relname = 'ai_console_turns'"
    )
    policies = text(
        """
        SELECT p.polname, p.polpermissive, p.polcmd::text,
               pg_get_expr(p.polqual, p.polrelid)
        FROM pg_policy p
        WHERE p.polrelid = 'ai_console_turns'::regclass
        ORDER BY p.polname
        """
    )
    async with app_engine.connect() as connection:
        enabled, forced = (await connection.execute(flags)).one()
        rules = [tuple(row) for row in (await connection.execute(policies)).all()]

    assert (enabled, forced) == (True, True)
    assert [(name, permissive, command) for name, permissive, command, _ in rules] == [
        ("console_hr_only", False, "r"),
        ("tenant_isolation", True, "*"),
    ]
    assert "current_is_hr" in rules[0][3]


# --- Who reads a row ---


async def test_only_hr_reads_a_console_row_even_the_asker(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    async with as_person(tenant.id, tenant.hr_id, hr=True) as session:
        hr = await count_rows(session)
    async with as_person(tenant.id, tenant.employee_id) as session:
        asker = await count_rows(session)
    async with as_person(tenant.id, tenant.colleague_id) as session:
        coworker = await count_rows(session)
    async with as_person(tenant.id, tenant.hr_id) as session:
        # Dana's session without the HR flag is an ordinary person's.
        unflagged_hr = await count_rows(session)
    async with as_person(tenant.id, None) as session:
        seed_without_hr = await count_rows(session)

    assert (hr, asker, coworker, unflagged_hr, seed_without_hr) == (1, 0, 0, 0, 0)


async def test_a_manager_reads_no_console_row(seeded_sandbox: SeedCompany) -> None:
    tenant_id = seeded_sandbox.tenant_id
    async with as_person(tenant_id, None) as session:
        marcus: Any = (
            await session.execute(
                text("SELECT id FROM people WHERE persona_key = 'marcus' AND tenant_id = :t"),
                {"t": tenant_id},
            )
        ).scalar_one()
    async with as_person(tenant_id, UUID(str(marcus))) as session:
        await insert_row(session, ordinary(tenant_id))
        # His own transaction wrote the row, and still cannot read it.
        assert await count_rows(session) == 0
    async with as_person(tenant_id, UUID(str(marcus))) as session:
        assert await count_rows(session) == 0


async def test_a_person_can_write_the_row_without_reading_it_back(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()

    async with as_person(tenant.id, tenant.colleague_id) as session:
        await insert_row(session, ordinary(tenant.id))
        assert await count_rows(session) == 0

    async with as_person(tenant.id, tenant.hr_id, hr=True) as session:
        assert await count_rows(session) == 2


async def test_another_sandbox_reads_no_row_even_as_hr(make_tenant: MakeTenant) -> None:
    mine, theirs = await make_tenant(), await make_tenant()

    async with as_person(theirs.id, theirs.hr_id, hr=True) as session:
        found = await session.execute(
            text("SELECT count(*) FROM ai_console_turns WHERE tenant_id = :t"), {"t": mine.id}
        )
    async with as_person(theirs.id, mine.hr_id, hr=True) as session:
        as_a_foreign_hr_id = await count_rows(session)

    assert found.scalar_one() == 0
    assert as_a_foreign_hr_id == 1  # theirs only


async def test_a_row_cannot_be_written_for_another_sandbox(make_tenant: MakeTenant) -> None:
    mine, theirs = await make_tenant(), await make_tenant()

    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_person(mine.id, mine.employee_id) as session:
            await insert_row(session, ordinary(theirs.id))


# --- What the app's login may do ---


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ai_console_turns SET outcome = 'answered'",
        "UPDATE ai_console_turns SET flagged = false",
        "DELETE FROM ai_console_turns",
        "TRUNCATE ai_console_turns",
    ],
)
async def test_the_app_cannot_change_or_delete_a_console_row(
    make_tenant: MakeTenant, statement: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_person(tenant.id, tenant.hr_id, hr=True) as session:
            await session.execute(text(statement))


async def test_the_rows_go_with_their_sandbox(
    make_tenant: MakeTenant, owner_engine: AsyncEngine
) -> None:
    tenant: SampleTenant = await make_tenant()
    async with owner_engine.begin() as connection:
        await connection.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": tenant.id})
        left = await connection.execute(
            text("SELECT count(*) FROM ai_console_turns WHERE tenant_id = :t"), {"t": tenant.id}
        )

    assert left.scalar_one() == 0
