"""The case tables (migration 0013): who sees a row, what the API may change, and the rules the
schema holds on its own.

A case is a matter a person sent to HR. Postgres shows it only to the person who opened it and to
HR, and lets only HR change it, never on their own case. Its summary and its timeline are HR's
alone. Triggers stop code running as the person from forging either one, and move a case's status
one way. The people in `make_tenant`: Priya opened the sample case, Leo is another employee (a
manager gets nothing more, since Postgres knows no managers), and Dana is HR.
"""

import importlib.util
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.audit.service import record_event
from tests.integration.conftest import OPAQUE, MakeTenant, SampleTenant, write_assistant_rows
from tests.integration.test_cleanup import rows_left

pytestmark = pytest.mark.integration

MIGRATION = Path(__file__).resolve().parents[2] / "migrations/versions/0013_cases.py"
MIGRATION_0015 = (
    Path(__file__).resolve().parents[2] / "migrations/versions/0015_case_event_limits.py"
)
CASE_TABLES = ("cases", "case_summaries", "case_events")


# The engine of the test that is running, set by the fixture below, so that `as_person` reads like
# the request's own transaction in every test without passing the engine around.
ENGINE: list[AsyncEngine] = []


@pytest.fixture(autouse=True)
def remember_the_engine(app_engine: AsyncEngine) -> None:
    ENGINE[:] = [app_engine]


@asynccontextmanager
async def as_person(
    tenant: SampleTenant, person_id: UUID | None, *, hr: bool = False
) -> AsyncIterator[AsyncSession]:
    """A transaction for `person_id` (or for no one), with the HR flag set the way the API sets it
    for Dana."""
    async with tenant_session(ENGINE[0], TenantContext(tenant.id, person_id)) as session:
        if hr:
            await set_is_hr(session, True)
        yield session


def sqlstate(error: DBAPIError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


async def scalar(session: AsyncSession, query: str, **params: Any) -> Any:
    return (await session.execute(text(query), params)).scalar_one()


# Each helper below builds its INSERT from column names written in this file, never from input.


async def insert_row(session: AsyncSession, table: str, values: dict[str, Any]) -> UUID:
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)
    await session.execute(
        text(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"),  # noqa: S608
        values,
    )
    return values["id"]  # type: ignore[no-any-return]


async def insert_case(
    session: AsyncSession, tenant: SampleTenant, person_id: UUID, **overrides: Any
) -> UUID:
    """A case for `person_id` that comes from "My cases" (no turn). `overrides` replace columns."""
    return await insert_row(
        session,
        "cases",
        {
            "id": uuid4(),
            "tenant_id": tenant.id,
            "person_id": person_id,
            "submission_id": uuid4(),
            "category": "other",
            "reply_by": datetime.now(UTC).date() + timedelta(days=2),
            "screening": "ordinary",
            "key_id": "test",
            "wrapped_key": OPAQUE,
            "text_ciphertext": OPAQUE,
            **overrides,
        },
    )


async def insert_summary(
    session: AsyncSession, tenant: SampleTenant, case_id: UUID, **overrides: Any
) -> UUID:
    return await insert_row(
        session,
        "case_summaries",
        {
            "id": uuid4(),
            "tenant_id": tenant.id,
            "case_id": case_id,
            "status": "written",
            "ciphertext": OPAQUE,
            "model": "test",
            "prompt_version": "test",
            **overrides,
        },
    )


async def insert_event(
    session: AsyncSession, tenant: SampleTenant, case_id: UUID, kind: str, **overrides: Any
) -> UUID:
    return await insert_row(
        session,
        "case_events",
        {"id": uuid4(), "tenant_id": tenant.id, "case_id": case_id, "kind": kind, **overrides},
    )


async def count(session: AsyncSession, table: str, **filters: Any) -> int:
    where = " AND ".join(f"{name} = :{name}" for name in filters) or "true"
    return int(await scalar(session, f"SELECT count(*) FROM {table} WHERE {where}", **filters))  # noqa: S608


# --- The tables and their columns ---


async def test_the_three_tables_have_the_specs_columns(app_engine: AsyncEngine) -> None:
    query = text(
        "SELECT table_name, column_name, is_nullable FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = ANY(:tables)"
    )
    async with app_engine.connect() as connection:
        rows = (await connection.execute(query, {"tables": list(CASE_TABLES)})).all()
    found: dict[str, dict[str, bool]] = {}
    for table, column, nullable in rows:
        found.setdefault(table, {})[column] = nullable == "YES"

    def columns(*not_null: str, null: tuple[str, ...] = ()) -> dict[str, bool]:
        return {**dict.fromkeys(not_null, False), **dict.fromkeys(null, True)}

    assert found == {
        "cases": columns(
            "id",
            "tenant_id",
            "person_id",
            "submission_id",
            "category",
            "status",
            "status_changed_at",
            "created_at",
            "reply_by",
            "screening",
            "key_id",
            "wrapped_key",
            "text_ciphertext",
            null=("conversation_id", "turn_id"),
        ),
        "case_summaries": columns(
            "id",
            "tenant_id",
            "case_id",
            "status",
            "created_at",
            "written_by_hr",
            null=("reason", "ciphertext", "model", "prompt_version"),
        ),
        "case_events": columns(
            "id",
            "tenant_id",
            "case_id",
            "occurred_at",
            "kind",
            "written_by_hr",
            null=("actor_person_id", "from_status", "to_status"),
        ),
    }


async def insert_in_one_transaction(
    tenant: SampleTenant, table: str, overrides: dict[str, Any]
) -> None:
    """As the seed would (no person set): a case for Priya, then one row of `table` with
    `overrides`."""
    async with as_person(tenant, None, hr=True) as session:
        case_id = await insert_case(session, tenant, tenant.employee_id)
        if table == "cases":
            await insert_case(session, tenant, tenant.colleague_id, **overrides)
        elif table == "case_summaries":
            await insert_summary(session, tenant, case_id, **overrides)
        else:
            await insert_event(
                session,
                tenant,
                case_id,
                overrides["kind"],
                **{name: value for name, value in overrides.items() if name != "kind"},
            )


@pytest.mark.parametrize(
    ("table", "overrides"),
    [
        ("cases", {"category": "gossip"}),
        ("cases", {"status": "reopened"}),
        ("cases", {"screening": "fine"}),
        ("cases", {"conversation_id": uuid4()}),  # a conversation without a turn
        ("case_summaries", {"status": "pending"}),
        ("case_summaries", {"status": "failed", "reason": "gremlins", "ciphertext": None}),
        ("case_summaries", {"status": "written", "ciphertext": None}),
        ("case_summaries", {"status": "failed", "reason": "timeout"}),  # a failure with text
        ("case_summaries", {"reason": "timeout"}),  # a written summary with a reason
        ("case_events", {"kind": "deleted"}),
        ("case_events", {"kind": "status_changed"}),  # a change without its two statuses
        ("case_events", {"kind": "viewed", "to_status": "closed"}),
        ("case_events", {"kind": "status_changed", "from_status": "new", "to_status": "gone"}),
    ],
)
async def test_the_checks_refuse_values_outside_the_planned_ones(
    make_tenant: MakeTenant, table: str, overrides: dict[str, Any]
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match="violates check constraint"):
        await insert_in_one_transaction(tenant, table, overrides)


@pytest.mark.parametrize(
    "reason", ["transport", "refusal", "timeout", "budget", "checks", "screening-conflict"]
)
async def test_a_failed_summary_names_its_reason(make_tenant: MakeTenant, reason: str) -> None:
    tenant = await make_tenant()

    async with as_person(tenant, None, hr=True) as session:
        case_id = await insert_case(session, tenant, tenant.colleague_id)
        await insert_summary(
            session, tenant, case_id, status="failed", reason=reason, ciphertext=None
        )


# --- The keys ---


async def test_the_unique_rules_and_the_turn_key_have_the_specified_shape(
    app_engine: AsyncEngine,
) -> None:
    unique = text(
        """
        SELECT i.relname,
               (SELECT string_agg(a.attname, ', ' ORDER BY k.ord)
                FROM unnest(x.indkey::int2[]) WITH ORDINALITY AS k(attnum, ord)
                JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attnum = k.attnum),
               pg_get_expr(x.indpred, x.indrelid)
        FROM pg_index x
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_class t ON t.oid = x.indrelid
        WHERE t.relname IN ('cases', 'case_summaries') AND x.indisunique AND NOT x.indisprimary
        """
    )
    turn_key = text(
        """
        SELECT pg_get_constraintdef(oid) FROM pg_constraint
        WHERE conrelid = 'cases'::regclass AND conname = 'fk_cases_turn_owner'
        """
    )
    async with app_engine.connect() as connection:
        indexes = {
            name: (columns, predicate)
            for name, columns, predicate in (await connection.execute(unique)).all()
        }
        turn_definition: str = (await connection.execute(turn_key)).scalar_one()

    assert indexes == {
        "uq_cases_tenant_id_id": ("tenant_id, id", None),
        "uq_cases_tenant_id_person_id_submission_id": (
            "tenant_id, person_id, submission_id",
            None,
        ),
        "uq_cases_tenant_id_person_id_turn_id": (
            "tenant_id, person_id, turn_id",
            "(turn_id IS NOT NULL)",
        ),
        "uq_case_summaries_one_not_by_hr_per_case": ("tenant_id, case_id", "(NOT written_by_hr)"),
    }
    assert turn_definition.startswith("FOREIGN KEY (tenant_id, turn_id, person_id)")
    assert "ai_turns(tenant_id, id, person_id)" in turn_definition


async def test_a_submission_id_makes_one_case_per_person(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    submission = uuid4()
    async with as_person(tenant, tenant.employee_id) as session:
        await insert_case(session, tenant, tenant.employee_id, submission_id=submission)

    with pytest.raises(IntegrityError, match="uq_cases_tenant_id_person_id_submission_id"):
        async with as_person(tenant, tenant.employee_id) as session:
            await insert_case(session, tenant, tenant.employee_id, submission_id=submission)

    # The same ID from someone else is a different send, and says nothing about the first.
    async with as_person(tenant, tenant.colleague_id) as session:
        await insert_case(session, tenant, tenant.colleague_id, submission_id=submission)


async def test_one_turn_opens_one_case(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()  # the sample case already used the employee's turn
    async with as_person(tenant, tenant.employee_id) as session:
        turn_id = await scalar(
            session, "SELECT turn_id FROM cases WHERE id = :id", id=tenant.case_id
        )
        conversation_id = await scalar(
            session, "SELECT conversation_id FROM cases WHERE id = :id", id=tenant.case_id
        )

    with pytest.raises(IntegrityError, match="uq_cases_tenant_id_person_id_turn_id"):
        async with as_person(tenant, tenant.employee_id) as session:
            await insert_case(
                session,
                tenant,
                tenant.employee_id,
                turn_id=turn_id,
                conversation_id=conversation_id,
            )


async def test_a_case_cannot_name_someone_elses_turn(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, tenant.employee_id) as session:
        turn_id = await scalar(
            session, "SELECT turn_id FROM cases WHERE id = :id", id=tenant.case_id
        )
        conversation_id = await scalar(
            session, "SELECT conversation_id FROM cases WHERE id = :id", id=tenant.case_id
        )

    # Leo names Priya's turn. The key carries person_id, so the turn is not found for him.
    with pytest.raises(IntegrityError, match="fk_cases_turn_owner"):
        async with as_person(tenant, tenant.colleague_id) as session:
            await insert_case(
                session,
                tenant,
                tenant.colleague_id,
                turn_id=turn_id,
                conversation_id=conversation_id,
            )


async def test_a_case_can_come_from_the_persons_own_new_turn(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    async with as_person(tenant, tenant.colleague_id) as session:
        rows = await write_assistant_rows(session, tenant.id, tenant.colleague_id)
        await insert_case(
            session,
            tenant,
            tenant.colleague_id,
            turn_id=rows.turn_id,
            conversation_id=rows.conversation_id,
        )


# --- The rules, as the catalog holds them ---

RESTRICTIVE_POLICIES = text(
    """
    SELECT c.relname, p.polname, p.polcmd::text
    FROM pg_policy p
    JOIN pg_class c ON c.oid = p.polrelid
    WHERE NOT p.polpermissive AND c.relname = ANY(:tables)
    ORDER BY c.relname, p.polname
    """
)


async def test_the_restrictive_rules_are_the_planned_ones(app_engine: AsyncEngine) -> None:
    # A restrictive rule that is missing, or written for a different command, is the leak. Reads
    # (r) and updates (w) only: seeding and the person's own inserts are left to the triggers.
    async with app_engine.connect() as connection:
        rows = (
            await connection.execute(
                RESTRICTIVE_POLICIES, {"tables": [*CASE_TABLES, "audit_events"]}
            )
        ).all()

    assert [tuple(row) for row in rows] == [
        ("audit_events", "case_audit_hr_only", "r"),
        ("case_events", "event_hr_only", "r"),
        ("case_summaries", "summary_hr_only", "r"),
        ("cases", "case_hr_not_own", "w"),
        ("cases", "case_insert_own_new", "a"),
        ("cases", "case_opener_or_hr", "r"),
    ]


# --- Who reads a case ---


async def test_the_opener_and_hr_read_a_case_and_no_one_else_does(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    async with as_person(tenant, tenant.employee_id) as session:
        opener = await count(session, "cases", id=tenant.case_id)
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        hr = await count(session, "cases", id=tenant.case_id)
    async with as_person(tenant, tenant.colleague_id) as session:
        # By ID and by scan: neither shows a row.
        coworker_by_id = await count(session, "cases", id=tenant.case_id)
        coworker_all = await count(session, "cases")
    async with as_person(tenant, tenant.hr_id) as session:
        # Dana's session without the HR flag is an ordinary person's.
        unflagged = await count(session, "cases")

    assert (opener, hr, coworker_by_id, coworker_all, unflagged) == (1, 1, 0, 0, 0)


async def test_another_sandbox_sees_no_case_even_as_hr(make_tenant: MakeTenant) -> None:
    mine, theirs = await make_tenant(), await make_tenant()

    async with as_person(theirs, theirs.hr_id, hr=True) as session:
        found = await count(session, "cases", id=mine.case_id)
    async with tenant_session(ENGINE[0], TenantContext(theirs.id, mine.hr_id)) as session:
        await set_is_hr(session, True)
        found_as_a_foreign_hr_id = await count(session, "cases", id=mine.case_id)

    assert (found, found_as_a_foreign_hr_id) == (0, 0)


async def test_a_case_cannot_be_opened_for_another_sandbox_or_a_stranger(
    make_tenant: MakeTenant,
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()

    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_person(mine, mine.employee_id) as session:
            await insert_case(session, theirs, mine.employee_id)
    # Someone from another sandbox is not a person here: the key to people refuses them. (With no
    # person set, as the seed runs, so the insert rule lets the row reach the key.)
    with pytest.raises(IntegrityError, match="fk_cases_tenant_id_person_id_people"):
        async with as_person(mine, None) as session:
            await insert_case(session, mine, theirs.employee_id)


async def test_a_unique_clash_tells_a_person_nothing_about_someone_elses_case(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, tenant.employee_id) as session:
        submission = await scalar(
            session, "SELECT submission_id FROM cases WHERE id = :id", id=tenant.case_id
        )

    # Leo sends the same submission ID that Priya used: his case opens, with no clash.
    async with as_person(tenant, tenant.colleague_id) as session:
        await insert_case(session, tenant, tenant.colleague_id, submission_id=submission)


# --- Who changes a case ---


async def test_only_hr_changes_a_case_and_never_their_own(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        own = await insert_case(session, tenant, tenant.hr_id)
    update = "UPDATE cases SET status = 'in_review' WHERE id = :id"
    moved: dict[str, int] = {}

    for label, person, hr, case_id in (
        ("opener", tenant.employee_id, False, tenant.case_id),
        ("coworker", tenant.colleague_id, False, tenant.case_id),
        ("hr_without_flag", tenant.hr_id, False, tenant.case_id),
        ("hr_on_own", tenant.hr_id, True, own),
        ("hr_on_another", tenant.hr_id, True, tenant.case_id),
    ):
        async with as_person(tenant, person, hr=hr) as session:
            result = await session.execute(text(update), {"id": case_id})
            moved[label] = result.rowcount  # type: ignore[attr-defined]

    assert moved == {
        "opener": 0,
        "coworker": 0,
        "hr_without_flag": 0,
        "hr_on_own": 0,
        "hr_on_another": 1,
    }


async def test_a_status_change_leaves_every_other_column_alone(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    for column in ("text_ciphertext", "category", "person_id", "reply_by", "created_at"):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_person(tenant, tenant.hr_id, hr=True) as session:
                await session.execute(
                    text(f"UPDATE cases SET {column} = {column} WHERE id = :id"),  # noqa: S608
                    {"id": tenant.case_id},
                )


async def test_nothing_is_deleted(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    for table in CASE_TABLES:
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_person(tenant, tenant.hr_id, hr=True) as session:
                await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608


@pytest.mark.parametrize("table", ["case_summaries", "case_events"])
async def test_a_summary_and_an_event_are_never_updated(
    make_tenant: MakeTenant, table: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_person(tenant, tenant.hr_id, hr=True) as session:
            await session.execute(text(f"UPDATE {table} SET tenant_id = tenant_id"))  # noqa: S608


# --- The status trigger ---

ALLOWED = [("new", "in_review"), ("in_review", "closed"), ("new", "closed")]
REFUSED = [
    ("new", "new"),
    ("in_review", "new"),
    ("in_review", "in_review"),
    ("closed", "new"),
    ("closed", "in_review"),
    ("closed", "closed"),
]


async def case_in_status(tenant: SampleTenant, status: str) -> UUID:
    # With no person set, as the seed runs: a person can only open a case that is new.
    async with as_person(tenant, None) as session:
        return await insert_case(
            session,
            tenant,
            tenant.colleague_id,
            status=status,
            status_changed_at=datetime.now(UTC) - timedelta(days=1),
        )


@pytest.mark.parametrize(("old", "new"), ALLOWED)
async def test_a_status_moves_forward_and_is_stamped(
    make_tenant: MakeTenant, old: str, new: str
) -> None:
    tenant = await make_tenant()
    case_id = await case_in_status(tenant, old)

    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        # The statement tries to set its own time. The trigger writes the database's clock.
        await session.execute(
            text(
                "UPDATE cases SET status = :new,"
                " status_changed_at = now() - interval '5 days' WHERE id = :id"
            ),
            {"new": new, "id": case_id},
        )
        stamped_now = await scalar(
            session, "SELECT status_changed_at = now() FROM cases WHERE id = :id", id=case_id
        )

    assert stamped_now is True


@pytest.mark.parametrize(("old", "new"), REFUSED)
async def test_a_status_never_moves_back_or_stays(
    make_tenant: MakeTenant, old: str, new: str
) -> None:
    tenant = await make_tenant()
    case_id = await case_in_status(tenant, old)

    with pytest.raises(DBAPIError) as raised:
        async with as_person(tenant, tenant.hr_id, hr=True) as session:
            await session.execute(
                text("UPDATE cases SET status = :new WHERE id = :id"), {"new": new, "id": case_id}
            )

    assert sqlstate(raised.value) == "OD004"


async def test_the_stamp_alone_cannot_be_moved(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    with pytest.raises(DBAPIError) as raised:
        async with as_person(tenant, tenant.hr_id, hr=True) as session:
            await session.execute(
                text("UPDATE cases SET status_changed_at = now() WHERE id = :id"),
                {"id": tenant.case_id},
            )

    assert sqlstate(raised.value) == "OD004"


# --- The screening write-back (migration 0014) ---

SCREENING_REFUSED = "OD005"


async def unscreened_case(tenant: SampleTenant) -> UUID:
    """Someone else's case the safety check could not screen, written as the seed would."""
    async with as_person(tenant, None) as session:
        return await insert_case(session, tenant, tenant.colleague_id, screening="unscreened")


async def set_screening(
    tenant: SampleTenant,
    case_id: UUID,
    verdict: str,
    *,
    person: UUID | None,
    hr: bool,
    set_sql: str = "",
) -> int:
    async with as_person(tenant, person, hr=hr) as session:
        result = await session.execute(
            text(f"UPDATE cases SET screening = :verdict{set_sql} WHERE id = :id"),  # noqa: S608
            {"verdict": verdict, "id": case_id},
        )
        return int(result.rowcount)  # type: ignore[attr-defined]


@pytest.mark.parametrize("verdict", ["ordinary", "sensitive", "crisis"])
async def test_hr_screens_an_unscreened_case_and_leaves_the_status_alone(
    make_tenant: MakeTenant, verdict: str
) -> None:
    tenant = await make_tenant()
    case_id = await unscreened_case(tenant)
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        before = await scalar(
            session, "SELECT status_changed_at FROM cases WHERE id = :id", id=case_id
        )

    moved = await set_screening(tenant, case_id, verdict, person=tenant.hr_id, hr=True)

    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        row = (
            await session.execute(
                text("SELECT screening, status, status_changed_at FROM cases WHERE id = :id"),
                {"id": case_id},
            )
        ).one()
    # The status and its stamp are untouched: the status trigger does not run for this change.
    assert (moved, row.screening, row.status, row.status_changed_at) == (1, verdict, "new", before)


ALLOWED_MOVES = [
    ("unscreened", "ordinary"),
    ("unscreened", "sensitive"),
    ("unscreened", "crisis"),
    ("ordinary", "crisis"),
    ("sensitive", "crisis"),
]
REFUSED_MOVES = [
    ("ordinary", "sensitive"),
    ("sensitive", "ordinary"),
    ("ordinary", "unscreened"),
    ("sensitive", "unscreened"),
    ("crisis", "ordinary"),
    ("crisis", "sensitive"),
    ("crisis", "unscreened"),
]


async def case_labeled(tenant: SampleTenant, label: str) -> UUID:
    async with as_person(tenant, None) as session:
        return await insert_case(session, tenant, tenant.colleague_id, screening=label)


async def screening_now(tenant: SampleTenant, case_id: UUID) -> str:
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        return str(await scalar(session, "SELECT screening FROM cases WHERE id = :id", id=case_id))


@pytest.mark.parametrize(("old", "new"), ALLOWED_MOVES)
async def test_hr_may_make_the_two_allowed_screening_moves(
    make_tenant: MakeTenant, old: str, new: str
) -> None:
    tenant = await make_tenant()
    case_id = await case_labeled(tenant, old)

    moved = await set_screening(tenant, case_id, new, person=tenant.hr_id, hr=True)

    assert (moved, await screening_now(tenant, case_id)) == (1, new)


@pytest.mark.parametrize(("old", "new"), REFUSED_MOVES)
async def test_every_other_screening_move_is_refused(
    make_tenant: MakeTenant, old: str, new: str
) -> None:
    tenant = await make_tenant()
    case_id = await case_labeled(tenant, old)

    with pytest.raises(DBAPIError) as raised:
        await set_screening(tenant, case_id, new, person=tenant.hr_id, hr=True)

    assert sqlstate(raised.value) == SCREENING_REFUSED
    assert await screening_now(tenant, case_id) == old


@pytest.mark.parametrize("old", ["ordinary", "sensitive"])
async def test_a_raised_crisis_stays(make_tenant: MakeTenant, old: str) -> None:
    tenant = await make_tenant()
    case_id = await case_labeled(tenant, old)
    await set_screening(tenant, case_id, "crisis", person=tenant.hr_id, hr=True)

    with pytest.raises(DBAPIError) as raised:
        await set_screening(tenant, case_id, old, person=tenant.hr_id, hr=True)

    assert sqlstate(raised.value) == SCREENING_REFUSED
    assert await screening_now(tenant, case_id) == "crisis"


async def test_a_case_cannot_be_moved_back_to_unscreened_or_to_a_made_up_label(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    # tenant.case_id is "ordinary" already: moving it anywhere is refused by the trigger.
    with pytest.raises(DBAPIError) as raised:
        await set_screening(tenant, tenant.case_id, "unscreened", person=tenant.hr_id, hr=True)
    assert sqlstate(raised.value) == SCREENING_REFUSED

    case_id = await unscreened_case(tenant)
    with pytest.raises(DBAPIError) as bad:
        await set_screening(tenant, case_id, "banana", person=tenant.hr_id, hr=True)
    # The column's check or the trigger: the label is refused either way.
    assert sqlstate(bad.value) in {SCREENING_REFUSED, "23514"}


async def test_only_hr_screens_a_case_and_never_their_own(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    case_id = await unscreened_case(tenant)
    raised_case = await case_labeled(tenant, "ordinary")
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        own = await insert_case(session, tenant, tenant.hr_id, screening="unscreened")
        own_ordinary = await insert_case(session, tenant, tenant.hr_id, screening="ordinary")

    moved = {
        "opener": await set_screening(
            tenant, case_id, "crisis", person=tenant.colleague_id, hr=False
        ),
        "other_person": await set_screening(
            tenant, case_id, "crisis", person=tenant.employee_id, hr=False
        ),
        "hr_without_flag": await set_screening(
            tenant, case_id, "crisis", person=tenant.hr_id, hr=False
        ),
        "no_person_with_flag": await set_screening(tenant, case_id, "crisis", person=None, hr=True),
        "no_person_no_flag": await set_screening(tenant, case_id, "crisis", person=None, hr=False),
        "hr_on_own": await set_screening(tenant, own, "crisis", person=tenant.hr_id, hr=True),
        # Raising an ordinary case to crisis has the same conditions.
        "raise_as_opener": await set_screening(
            tenant, raised_case, "crisis", person=tenant.colleague_id, hr=False
        ),
        "raise_without_flag": await set_screening(
            tenant, raised_case, "crisis", person=tenant.hr_id, hr=False
        ),
        "raise_on_own": await set_screening(
            tenant, own_ordinary, "crisis", person=tenant.hr_id, hr=True
        ),
    }

    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        left = [
            await scalar(session, "SELECT screening FROM cases WHERE id = :id", id=c)
            for c in (case_id, own, raised_case, own_ordinary)
        ]
    assert set(moved.values()) == {0}
    assert left == ["unscreened", "unscreened", "ordinary", "ordinary"]


async def test_the_openers_own_screening_is_not_theirs_to_change(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, tenant.employee_id) as session:
        own = await insert_case(session, tenant, tenant.employee_id, screening="unscreened")

    assert await set_screening(tenant, own, "ordinary", person=tenant.employee_id, hr=False) == 0


@pytest.mark.parametrize(
    "also", [", status = 'in_review'", ", status_changed_at = now() - interval '3 days'"]
)
@pytest.mark.parametrize("old", ["unscreened", "ordinary", "sensitive"])
async def test_nothing_else_changes_with_the_screening(
    make_tenant: MakeTenant, also: str, old: str
) -> None:
    tenant = await make_tenant()
    case_id = await case_labeled(tenant, old)

    with pytest.raises(DBAPIError) as raised:
        await set_screening(tenant, case_id, "crisis", person=tenant.hr_id, hr=True, set_sql=also)
    assert sqlstate(raised.value) == SCREENING_REFUSED
    assert await screening_now(tenant, case_id) == old


async def test_screening_cannot_change_another_column_alongside_it(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    case_id = await unscreened_case(tenant)

    for column in ("text_ciphertext", "category", "reply_by"):
        with pytest.raises(DBAPIError, match="permission denied"):
            await set_screening(
                tenant,
                case_id,
                "crisis",
                person=tenant.hr_id,
                hr=True,
                set_sql=f", {column} = {column}",
            )


# --- The summaries ---


async def test_hr_alone_reads_summaries_and_events(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    seen: dict[str, tuple[int, int]] = {}

    for label, person, hr in (
        ("hr", tenant.hr_id, True),
        # The opener wrote both rows, and cannot read either back.
        ("opener", tenant.employee_id, False),
        ("coworker", tenant.colleague_id, False),
        ("hr_without_flag", tenant.hr_id, False),
    ):
        async with as_person(tenant, person, hr=hr) as session:
            seen[label] = (
                await count(session, "case_summaries"),
                await count(session, "case_events"),
            )

    assert seen == {"hr": (1, 1), "opener": (0, 0), "coworker": (0, 0), "hr_without_flag": (0, 0)}


async def test_the_person_adds_one_summary_to_their_own_new_case(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()  # the sample case has its summary already
    async with as_person(tenant, tenant.employee_id) as session:
        fresh = await insert_case(session, tenant, tenant.employee_id)
        await insert_summary(session, tenant, fresh)

    # A second one from the person is refused, though they cannot see the first.
    with pytest.raises(IntegrityError, match="uq_case_summaries_one_not_by_hr_per_case"):
        async with as_person(tenant, tenant.employee_id) as session:
            await insert_summary(session, tenant, fresh)
    with pytest.raises(IntegrityError, match="uq_case_summaries_one_not_by_hr_per_case"):
        async with as_person(tenant, tenant.employee_id) as session:
            await insert_summary(session, tenant, tenant.case_id)


async def test_hr_retries_a_summary_and_the_newest_counts(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        await insert_summary(session, tenant, tenant.case_id)
        await insert_summary(session, tenant, tenant.case_id)
        total = await count(session, "case_summaries", case_id=tenant.case_id)
        by_hr = await count(session, "case_summaries", case_id=tenant.case_id, written_by_hr=True)

    assert (total, by_hr) == (3, 2)


async def test_hr_on_their_own_case_is_held_to_the_persons_summary_rules(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, None) as session:
        stale = await insert_case(
            session,
            tenant,
            tenant.hr_id,
            created_at=datetime.now(UTC) - timedelta(minutes=11),
        )
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        own = await insert_case(session, tenant, tenant.hr_id)
        await insert_summary(session, tenant, own)
        # Dana reads other people's cases freely, so the flag is not set for them.
        flagged = await scalar(
            session, "SELECT written_by_hr FROM case_summaries WHERE case_id = :id", id=own
        )

    assert flagged is False
    # One summary, as for any person.
    with pytest.raises(IntegrityError, match="uq_case_summaries_one_not_by_hr_per_case"):
        async with as_person(tenant, tenant.hr_id, hr=True) as session:
            await insert_summary(session, tenant, own)
    # And only in the case's first 10 minutes.
    with pytest.raises(DBAPIError) as raised:
        async with as_person(tenant, tenant.hr_id, hr=True) as session:
            await insert_summary(session, tenant, stale)
    assert sqlstate(raised.value) == "OD003"
    # On someone else's case HR still adds as many as they like, flagged as HR's.
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        await insert_summary(session, tenant, tenant.case_id)
        by_hr = await count(session, "case_summaries", case_id=tenant.case_id, written_by_hr=True)
    assert by_hr == 1


async def test_a_summary_after_ten_minutes_is_refused_for_the_person_but_not_hr(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    # Backdated, which only a transaction with no person set can do (the seed's).
    async with as_person(tenant, None) as session:
        stale = await insert_case(
            session,
            tenant,
            tenant.employee_id,
            created_at=datetime.now(UTC) - timedelta(minutes=11),
        )
        recent = await insert_case(
            session, tenant, tenant.employee_id, created_at=datetime.now(UTC) - timedelta(minutes=9)
        )
    async with as_person(tenant, tenant.employee_id) as session:
        await insert_summary(session, tenant, recent)

    with pytest.raises(DBAPIError) as raised:
        async with as_person(tenant, tenant.employee_id) as session:
            await insert_summary(session, tenant, stale)
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        await insert_summary(session, tenant, stale)

    assert sqlstate(raised.value) == "OD003"


async def test_a_summary_for_someone_elses_case_or_a_missing_one_is_refused(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, tenant.colleague_id) as session:
        leos = await insert_case(session, tenant, tenant.colleague_id)

    for case_id in (leos, uuid4()):
        with pytest.raises((DBAPIError, IntegrityError)) as raised:
            async with as_person(tenant, tenant.employee_id) as session:
                await insert_summary(session, tenant, case_id)
        assert sqlstate(raised.value) in {"OD003", "23503"}
    # Leo cannot summarize Priya's case either, even a fresh one.
    async with as_person(tenant, tenant.employee_id) as session:
        fresh = await insert_case(session, tenant, tenant.employee_id)
    with pytest.raises(DBAPIError) as raised:
        async with as_person(tenant, tenant.colleague_id) as session:
            await insert_summary(session, tenant, fresh)
    assert sqlstate(raised.value) == "OD003"


async def test_the_written_by_hr_flag_is_the_databases_not_the_statements(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, tenant.employee_id) as session:
        fresh = await insert_case(session, tenant, tenant.employee_id)
        # The person claims HR wrote it, to get past the one-summary rule later.
        await insert_summary(session, tenant, fresh, written_by_hr=True)
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        flagged = await scalar(
            session,
            "SELECT written_by_hr FROM case_summaries WHERE case_id = :id",
            id=fresh,
        )
    with pytest.raises(IntegrityError, match="uq_case_summaries_one_not_by_hr_per_case"):
        async with as_person(tenant, tenant.employee_id) as session:
            await insert_summary(session, tenant, fresh)

    assert flagged is False


# --- The timeline ---


@pytest.mark.parametrize("kind", ["opened", "summary_written", "summary_failed"])
async def test_the_person_adds_their_own_three_kinds_of_event(
    make_tenant: MakeTenant, kind: str
) -> None:
    tenant = await make_tenant()

    # A fresh case, as the open transaction makes it: each kind once, in its first 10 minutes.
    async with as_person(tenant, tenant.employee_id) as session:
        fresh = await insert_case(session, tenant, tenant.employee_id)
        await insert_event(session, tenant, fresh, kind, actor_person_id=tenant.employee_id)


@pytest.mark.parametrize("kind", ["opened", "summary_written", "summary_failed"])
async def test_the_person_cannot_repeat_an_event_or_add_it_late(
    make_tenant: MakeTenant, kind: str
) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, None) as session:
        stale = await insert_case(
            session,
            tenant,
            tenant.employee_id,
            created_at=datetime.now(UTC) - timedelta(minutes=11),
        )
    async with as_person(tenant, tenant.employee_id) as session:
        fresh = await insert_case(session, tenant, tenant.employee_id)
        await insert_event(session, tenant, fresh, kind)

    # A second one on the same case, and a first one on a case past its first 10 minutes.
    for case_id in (fresh, stale):
        with pytest.raises(IntegrityError if case_id == fresh else DBAPIError) as raised:
            async with as_person(tenant, tenant.employee_id) as session:
                await insert_event(session, tenant, case_id, kind)
        assert sqlstate(raised.value) in {"OD003", "23505"}


async def test_the_person_gets_one_summary_event_of_either_kind(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, tenant.employee_id) as session:
        fresh = await insert_case(session, tenant, tenant.employee_id)
        await insert_event(session, tenant, fresh, "summary_failed")

    with pytest.raises(IntegrityError) as raised:
        async with as_person(tenant, tenant.employee_id) as session:
            await insert_event(session, tenant, fresh, "summary_written")

    assert sqlstate(raised.value) == "23505"


async def test_the_open_paths_each_keep_their_events(make_tenant: MakeTenant) -> None:
    """Opened plus the summary_failed of a crisis or unscreened case, in one transaction; then
    HR's retries on top, as many as they like."""
    tenant = await make_tenant()
    async with as_person(tenant, tenant.employee_id) as session:
        fresh = await insert_case(session, tenant, tenant.employee_id, screening="crisis")
        await insert_event(session, tenant, fresh, "opened", actor_person_id=tenant.employee_id)
        await insert_event(session, tenant, fresh, "summary_failed")
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        for kind in ("summary_failed", "summary_written", "summary_written"):
            await insert_event(session, tenant, fresh, kind, actor_person_id=tenant.hr_id)
        recorded = await count(session, "case_events", case_id=fresh)
        by_hr = await count(session, "case_events", case_id=fresh, written_by_hr=True)
    assert (recorded, by_hr) == (5, 3)


@pytest.mark.parametrize("kind", ["viewed", "text_read"])
async def test_the_person_cannot_forge_hrs_reading(make_tenant: MakeTenant, kind: str) -> None:
    tenant = await make_tenant()

    with pytest.raises(DBAPIError) as raised:
        async with as_person(tenant, tenant.employee_id) as session:
            await insert_event(session, tenant, tenant.case_id, kind)

    assert sqlstate(raised.value) == "OD003"


async def test_the_person_cannot_forge_a_status_change(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    with pytest.raises(DBAPIError) as raised:
        async with as_person(tenant, tenant.employee_id) as session:
            await insert_event(
                session,
                tenant,
                tenant.case_id,
                "status_changed",
                from_status="new",
                to_status="closed",
            )

    assert sqlstate(raised.value) == "OD003"


async def test_an_event_on_someone_elses_case_or_in_their_name_is_refused(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()

    # Leo adds an `opened` event to Priya's case.
    with pytest.raises(DBAPIError) as on_hers:
        async with as_person(tenant, tenant.colleague_id) as session:
            await insert_event(session, tenant, tenant.case_id, "opened")
    # Priya adds one in Dana's name.
    with pytest.raises(DBAPIError) as in_her_name:
        async with as_person(tenant, tenant.employee_id) as session:
            await insert_event(
                session, tenant, tenant.case_id, "opened", actor_person_id=tenant.hr_id
            )

    assert (sqlstate(on_hers.value), sqlstate(in_her_name.value)) == ("OD003", "OD003")


async def test_hr_adds_any_kind_of_event(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        for kind in ("viewed", "text_read", "opened"):
            await insert_event(session, tenant, tenant.case_id, kind, actor_person_id=tenant.hr_id)
        await insert_event(
            session,
            tenant,
            tenant.case_id,
            "status_changed",
            actor_person_id=tenant.hr_id,
            from_status="new",
            to_status="in_review",
        )


async def test_hr_on_their_own_case_is_held_to_the_persons_event_limits(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, None) as session:
        stale = await insert_case(
            session,
            tenant,
            tenant.hr_id,
            created_at=datetime.now(UTC) - timedelta(minutes=11),
        )
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        own = await insert_case(session, tenant, tenant.hr_id)
        await insert_event(session, tenant, own, "opened")
        flagged = await scalar(
            session, "SELECT written_by_hr FROM case_events WHERE case_id = :id", id=own
        )
    assert flagged is False

    # A second `opened` or summary event pair, as the person could not add.
    with pytest.raises(IntegrityError, match="uq_case_events_one_opened_not_by_hr_per_case"):
        async with as_person(tenant, tenant.hr_id, hr=True) as session:
            await insert_event(session, tenant, own, "opened")
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        await insert_event(session, tenant, own, "summary_written")
    with pytest.raises(IntegrityError, match="uq_case_events_one_summary_not_by_hr_per_case"):
        async with as_person(tenant, tenant.hr_id, hr=True) as session:
            await insert_event(session, tenant, own, "summary_failed")
    # A late event, and a kind only HR may add elsewhere.
    for kind in ("opened", "summary_written", "text_read"):
        with pytest.raises(DBAPIError) as raised:
            async with as_person(tenant, tenant.hr_id, hr=True) as session:
                await insert_event(session, tenant, stale, kind)
        assert sqlstate(raised.value) == "OD003"


async def test_hr_on_someone_elses_case_adds_events_without_limit(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        for kind in ("opened", "opened", "summary_written", "summary_failed", "summary_written"):
            await insert_event(session, tenant, tenant.case_id, kind)
        by_hr = await count(session, "case_events", case_id=tenant.case_id, written_by_hr=True)
    assert by_hr == 5


async def test_a_seeded_event_is_not_by_hr(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    old = datetime.now(UTC) - timedelta(days=3)
    async with as_person(tenant, None) as session:
        case_id = await insert_case(
            session, tenant, tenant.colleague_id, created_at=old, status_changed_at=old
        )
        for kind in ("opened", "summary_written"):
            await insert_event(session, tenant, case_id, kind, occurred_at=old)
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        flags = await scalar(
            session,
            "SELECT array_agg(written_by_hr) FROM case_events WHERE case_id = :id",
            id=case_id,
        )
    assert flags == [False, False]


# --- Seeding: no person set ---


async def test_with_no_person_set_every_insert_is_accepted(make_tenant: MakeTenant) -> None:
    """The sandbox seed clears `app.person_id` around its case block (Phase 6, stage 2, batch C),
    so it can write cases from people who aren't the visitor, with backdated summaries and Dana's
    `text_read`. A person-less transaction is the only bypass: the HR flag alone is not."""
    tenant = await make_tenant()
    old = datetime.now(UTC) - timedelta(days=3)

    async with as_person(tenant, None) as session:
        case_id = await insert_case(
            session,
            tenant,
            tenant.colleague_id,
            status="in_review",
            created_at=old,
            status_changed_at=old,
        )
        await insert_summary(session, tenant, case_id, created_at=old)
        for kind in ("opened", "summary_written", "viewed", "text_read"):
            await insert_event(
                session, tenant, case_id, kind, actor_person_id=tenant.hr_id, occurred_at=old
            )
        # A second summary for the same case from the seed would still hit the one-per-case
        # index, since no person is not HR.


async def insert_as_the_person(tenant: SampleTenant, case_id: UUID, attempt: str) -> None:
    async with as_person(tenant, tenant.employee_id) as session:
        if attempt == "summary":
            await insert_summary(session, tenant, case_id)
        else:
            await insert_event(session, tenant, case_id, attempt)


@pytest.mark.parametrize("attempt", ["summary", "text_read", "viewed"])
async def test_with_a_person_set_the_refusals_hold(make_tenant: MakeTenant, attempt: str) -> None:
    tenant = await make_tenant()
    old = datetime.now(UTC) - timedelta(days=3)
    async with as_person(tenant, None) as session:
        stale = await insert_case(session, tenant, tenant.employee_id, created_at=old)

    with pytest.raises(DBAPIError) as raised:
        await insert_as_the_person(tenant, stale, attempt)

    assert sqlstate(raised.value) == "OD003"


async def test_the_hr_flag_is_not_a_way_around_the_status_trigger(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    closed = await case_in_status(tenant, "closed")

    with pytest.raises(DBAPIError) as raised:
        async with as_person(tenant, tenant.hr_id, hr=True) as session:
            await session.execute(
                text("UPDATE cases SET status = 'new' WHERE id = :id"), {"id": closed}
            )

    assert sqlstate(raised.value) == "OD004"


async def test_the_hr_flag_with_no_person_changes_no_case(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        own = await insert_case(session, tenant, tenant.hr_id)

    async with as_person(tenant, None, hr=True) as session:
        moved = [
            (
                await session.execute(
                    text("UPDATE cases SET status = 'in_review' WHERE id = :id"), {"id": case_id}
                )
            ).rowcount  # type: ignore[attr-defined]
            for case_id in (tenant.case_id, own)
        ]

    assert moved == [0, 0]


# --- Who opens a case, and the clock ---


async def test_a_person_opens_only_their_own_new_case(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    # Priya reads her own case back, so a plain ORM-style RETURNING insert works for her.
    async with as_person(tenant, tenant.employee_id) as session:
        opened = await insert_case(session, tenant, tenant.employee_id, status="new")
        returned: Any = (
            await session.execute(
                text(
                    "INSERT INTO cases (tenant_id, person_id, submission_id, category, reply_by,"
                    " screening, key_id, wrapped_key, text_ciphertext)"
                    " VALUES (:t, :p, :s, 'pay', current_date, 'ordinary', 'k', :b, :b)"
                    " RETURNING id"
                ),
                {"t": tenant.id, "p": tenant.employee_id, "s": uuid4(), "b": OPAQUE},
            )
        ).scalar_one()
    refused = {}
    for label, person, overrides in (
        ("for_leo", tenant.colleague_id, {}),
        ("closed", tenant.employee_id, {"status": "closed"}),
        ("in_review", tenant.employee_id, {"status": "in_review"}),
    ):
        with pytest.raises(DBAPIError) as raised:
            async with as_person(tenant, tenant.employee_id) as session:
                await insert_case(session, tenant, person, **overrides)
        refused[label] = "row-level security" in str(raised.value)

    assert opened != returned
    assert refused == {"for_leo": True, "closed": True, "in_review": True}


async def test_hr_opens_a_case_for_someone_else_no_more_than_anyone(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()

    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_person(tenant, tenant.hr_id, hr=True) as session:
            await insert_case(session, tenant, tenant.employee_id)
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        await insert_case(session, tenant, tenant.hr_id)


async def test_with_no_person_set_any_case_is_accepted(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    async with as_person(tenant, None) as session:
        for status in ("new", "in_review", "closed"):
            await insert_case(session, tenant, tenant.colleague_id, status=status)


FORGED_EARLY = datetime(1999, 1, 1, tzinfo=UTC)
FORGED_LATE = datetime(2100, 1, 1, tzinfo=UTC)
TIMESTAMPS = text(
    """
    SELECT
      (SELECT created_at FROM cases WHERE id = :case),
      (SELECT status_changed_at FROM cases WHERE id = :case),
      (SELECT created_at FROM case_summaries WHERE case_id = :case
         ORDER BY created_at DESC LIMIT 1),
      (SELECT occurred_at FROM case_events WHERE case_id = :case AND kind = 'opened'
         ORDER BY occurred_at DESC LIMIT 1),
      now()
    """
)


async def forged_stamps(tenant: SampleTenant, person: UUID | None, *, hr: bool) -> list[Any]:
    """Insert a case, a summary, and an event that each name a faked time, as `person`; then read
    the four times back as HR, with the database's clock."""
    async with as_person(tenant, person, hr=hr) as session:
        case_id = await insert_case(
            session,
            tenant,
            person or tenant.employee_id,
            created_at=FORGED_LATE,
            status_changed_at=FORGED_EARLY,
        )
        await insert_summary(session, tenant, case_id, created_at=FORGED_LATE)
        await insert_event(session, tenant, case_id, "opened", occurred_at=FORGED_EARLY)
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        row = (await session.execute(TIMESTAMPS, {"case": case_id})).one()
    return list(row)


@pytest.mark.parametrize("who", ["employee", "hr"])
async def test_a_persons_own_clock_is_replaced_by_the_databases(
    make_tenant: MakeTenant, who: str
) -> None:
    tenant = await make_tenant()
    person = tenant.employee_id if who == "employee" else tenant.hr_id

    *stamps, now = await forged_stamps(tenant, person, hr=who == "hr")

    # Every one of the four lies within the last minute of the transaction that read them.
    assert all(timedelta(0) <= now - stamp < timedelta(minutes=1) for stamp in stamps), stamps


async def test_with_no_person_set_the_supplied_times_are_kept(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    created, changed, summarized, occurred, _ = await forged_stamps(tenant, None, hr=False)

    assert (created, changed, summarized, occurred) == (
        FORGED_LATE,
        FORGED_EARLY,
        FORGED_LATE,
        FORGED_EARLY,
    )


# --- Every accepted value ---


@pytest.mark.parametrize(
    "category", ["harassment_discrimination", "safety", "medical_accommodation", "pay", "other"]
)
@pytest.mark.parametrize("screening", ["ordinary", "sensitive", "crisis", "unscreened"])
async def test_every_category_and_screening_value_is_accepted(
    make_tenant: MakeTenant, category: str, screening: str
) -> None:
    tenant = await make_tenant()

    async with as_person(tenant, tenant.colleague_id) as session:
        await insert_case(
            session, tenant, tenant.colleague_id, category=category, screening=screening
        )


@pytest.mark.parametrize(
    "reason",
    ["transport", "refusal", "timeout", "budget", "checks", "crisis", "unscreened"],
)
async def test_every_failure_reason_is_accepted_with_no_model_call(
    make_tenant: MakeTenant, reason: str
) -> None:
    tenant = await make_tenant()

    async with as_person(tenant, None, hr=True) as session:
        case_id = await insert_case(session, tenant, tenant.colleague_id)
        await insert_summary(
            session,
            tenant,
            case_id,
            status="failed",
            reason=reason,
            ciphertext=None,
            model=None,
            prompt_version=None,
        )


@pytest.mark.parametrize(
    "kind", ["opened", "summary_written", "summary_failed", "viewed", "text_read"]
)
async def test_every_event_kind_without_statuses_is_accepted(
    make_tenant: MakeTenant, kind: str
) -> None:
    tenant = await make_tenant()

    async with as_person(tenant, None) as session:
        # A new case: the sample one already has its `opened` from the seed, and the seed's rows
        # are held to one per case like the person's.
        case_id = await insert_case(session, tenant, tenant.colleague_id)
        await insert_event(session, tenant, case_id, kind)


@pytest.mark.parametrize(
    ("from_status", "to_status"), [("new", "in_review"), ("in_review", "closed"), ("new", "closed")]
)
async def test_a_status_change_event_names_two_statuses(
    make_tenant: MakeTenant, from_status: str, to_status: str
) -> None:
    tenant = await make_tenant()

    async with as_person(tenant, None) as session:
        await insert_event(
            session,
            tenant,
            tenant.case_id,
            "status_changed",
            from_status=from_status,
            to_status=to_status,
        )


# --- The audit log ---


async def audit(
    session: AsyncSession, tenant: SampleTenant, action: str, target_type: str, actor: UUID
) -> UUID:
    return await insert_row(
        session,
        "audit_events",
        {
            "id": uuid4(),
            "tenant_id": tenant.id,
            "actor_person_id": actor,
            "via": "system",
            "action": action,
            "target_type": target_type,
        },
    )


async def test_a_case_audit_row_is_written_by_anyone_but_read_only_by_hr(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()

    async with as_person(tenant, tenant.employee_id) as session:
        # The same Core insert, with no RETURNING, that record_event uses.
        await record_event(
            session,
            tenant_id=tenant.id,
            actor_id=tenant.employee_id,
            action="escalation.offered",
            target_type="case",
            target_id=tenant.case_id,
        )
        own_case_rows = await count(session, "audit_events", target_type="case")
    async with as_person(tenant, tenant.hr_id, hr=True) as session:
        hr_case_rows = await count(session, "audit_events", target_type="case")

    assert own_case_rows == 0  # the insert succeeded, and Priya cannot read it back
    assert hr_case_rows == 1


async def test_marcus_reads_no_case_row_and_no_one_elses_offer(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, tenant.employee_id) as session:
        await audit(session, tenant, "case.opened", "case", tenant.employee_id)
        await audit(session, tenant, "escalation.offered", "person", tenant.employee_id)
        await audit(session, tenant, "proposal.created", "proposal", tenant.employee_id)

    reads: dict[str, set[str]] = {}
    for label, person, hr in (
        ("priya", tenant.employee_id, False),
        ("leo", tenant.colleague_id, False),
        ("dana", tenant.hr_id, True),
    ):
        async with as_person(tenant, person, hr=hr) as session:
            rows = await session.execute(
                text(
                    "SELECT action FROM audit_events"
                    " WHERE action IN ('case.opened', 'escalation.offered', 'proposal.created')"
                )
            )
            reads[label] = {row[0] for row in rows}

    assert reads == {
        # An offer is its actor's to read; a case row is HR's alone.
        "priya": {"escalation.offered", "proposal.created"},
        "leo": {"proposal.created"},
        "dana": {"case.opened", "escalation.offered", "proposal.created"},
    }


async def test_every_other_audit_row_stays_open_to_the_sandbox(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()

    async with as_person(tenant, tenant.colleague_id) as session:
        created = await count(session, "audit_events", action="sandbox.created")

    assert created == 1


# --- Spending ---


async def test_spending_has_a_purpose_and_only_a_turns_row_needs_its_turn(
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    async with as_person(tenant, tenant.employee_id) as session:
        for purpose in ("case_screen", "case_summary"):
            await session.execute(
                text(
                    "INSERT INTO ai_spend (tenant_id, kind, amount_usd, purpose)"
                    " VALUES (:tenant_id, 'reserve', 0.01, :purpose)"
                ),
                {"tenant_id": tenant.id, "purpose": purpose},
            )
        turn_rows = await scalar(
            session,
            "SELECT count(*) FROM ai_spend WHERE purpose = 'turn' AND tenant_id = :t",
            t=tenant.id,
        )
        total = await scalar(
            session, "SELECT sum(amount_usd) FROM ai_spend WHERE tenant_id = :t", t=tenant.id
        )

    assert turn_rows == 1  # the sample turn's row defaults to purpose turn
    assert float(total) == pytest.approx(0.07)


@pytest.mark.parametrize("purpose", ["turn", "mystery"])
async def test_a_turn_row_without_its_turn_or_an_unknown_purpose_is_refused(
    make_tenant: MakeTenant, purpose: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match="violates check constraint"):
        async with as_person(tenant, tenant.employee_id) as session:
            await session.execute(
                text(
                    "INSERT INTO ai_spend (tenant_id, kind, amount_usd, purpose)"
                    " VALUES (:tenant_id, 'reserve', 0.01, :purpose)"
                ),
                {"tenant_id": tenant.id, "purpose": purpose},
            )


async def test_the_daily_cap_ledger_has_no_purpose_and_counts_every_call(
    app_engine: AsyncEngine,
) -> None:
    query = text(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_name = 'ai_spend_daily' AND table_schema = 'public'"
    )
    async with app_engine.connect() as connection:
        columns: set[str] = set((await connection.execute(query)).scalars())

    assert "purpose" not in columns
    assert {"day", "kind", "amount_usd"} <= columns


# --- Sandbox deletion and the migration ---


async def test_a_sandbox_delete_removes_its_cases(
    owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    before = await rows_left(owner_engine, tenant.id)
    async with owner_engine.begin() as connection:
        await connection.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant.id})
    after = await rows_left(owner_engine, tenant.id)

    assert all(before[table] > 0 for table in CASE_TABLES)
    assert all(after[table] == 0 for table in CASE_TABLES)


def load_migration(path: Path = MIGRATION) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_the_downgrade_deletes_non_turn_spending_before_it_restores_the_turn_key(
    owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    """Runs the downgrade's own statements in a transaction that always rolls back, so the test
    sandboxes survive. Without the delete, restoring NOT NULL on turn_id would fail."""
    tenant = await make_tenant()
    statements: tuple[str, ...] = load_migration().DOWNGRADE_SPENDING
    async with as_person(tenant, tenant.employee_id) as session:
        await session.execute(
            text(
                "INSERT INTO ai_spend (tenant_id, kind, amount_usd, purpose)"
                " VALUES (:tenant_id, 'reserve', 0.01, 'case_summary')"
            ),
            {"tenant_id": tenant.id},
        )

    async with owner_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            for statement in statements:
                await connection.exec_driver_sql(statement)
            nullable: Any = (
                await connection.execute(
                    text(
                        "SELECT is_nullable FROM information_schema.columns"
                        " WHERE table_name = 'ai_spend' AND column_name = 'turn_id'"
                    )
                )
            ).scalar_one()
            purposes: Any = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns"
                        " WHERE table_name = 'ai_spend' AND column_name = 'purpose'"
                    )
                )
            ).scalar_one()
            forced: Any = (
                await connection.execute(
                    text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'ai_spend'")
                )
            ).scalar_one()
        finally:
            await transaction.rollback()

    assert (nullable, purposes, forced) == ("NO", 0, True)


async def test_the_0015_backfill_runs_inside_the_force_bracket_and_stamps_hr_rows_of_every_kind(
    owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    """The backfill's statements are bracketed by NO FORCE and FORCE on both tables it touches
    (the development and CI owner is a superuser, which skips row-level security, so this test
    cannot show the difference for a non-superuser owner; it proves the order). Inside, it stamps
    the trigger's definition on every kind: HR acting on someone else's case is true, else false."""
    statements: tuple[str, ...] = load_migration(MIGRATION_0015).BACKFILL_STATEMENTS
    assert [s.split()[0:5] for s in statements[:2]] == [
        ["ALTER", "TABLE", "case_events", "NO", "FORCE"],
        ["ALTER", "TABLE", "cases", "NO", "FORCE"],
    ]
    assert statements[2].lstrip().startswith("UPDATE case_events")
    assert [s.split()[0:5] for s in statements[3:]] == [
        ["ALTER", "TABLE", "case_events", "FORCE", "ROW"],
        ["ALTER", "TABLE", "cases", "FORCE", "ROW"],
    ]

    tenant = await make_tenant()
    base = datetime.now(UTC) - timedelta(days=3)
    async with as_person(tenant, None) as session:
        case_id = await insert_case(session, tenant, tenant.employee_id, created_at=base)
        rows: list[tuple[str, UUID | None]] = [
            ("opened", tenant.employee_id),
            ("summary_written", None),
            ("viewed", tenant.hr_id),
            ("text_read", tenant.hr_id),
            ("status_changed", tenant.hr_id),
            ("viewed", None),
        ]
        ids: list[UUID] = []
        for offset, (kind, actor) in enumerate(rows):
            extra = (
                {"from_status": "new", "to_status": "in_review"} if kind == "status_changed" else {}
            )
            ids.append(
                await insert_event(
                    session,
                    tenant,
                    case_id,
                    kind,
                    actor_person_id=actor,
                    occurred_at=base + timedelta(minutes=offset),
                    **extra,
                )
            )

    async with owner_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            # A second `opened` by the person, as only a row made before the index could be.
            await connection.exec_driver_sql(
                "DROP INDEX uq_case_events_one_opened_not_by_hr_per_case"
            )
            later = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO case_events (id, tenant_id, case_id, kind, actor_person_id,"
                    " occurred_at) VALUES (:id, :tenant, :case, 'opened', :actor, :at)"
                ),
                {
                    "id": later,
                    "tenant": tenant.id,
                    "case": case_id,
                    "actor": tenant.employee_id,
                    "at": base + timedelta(minutes=9),
                },
            )
            ids.append(later)
            for statement in statements:
                await connection.exec_driver_sql(statement)
            flags: Any = dict(
                (
                    await connection.execute(
                        text("SELECT id, written_by_hr FROM case_events WHERE case_id = :id"),
                        {"id": case_id},
                    )
                ).all()
            )
            forced: Any = (
                await connection.execute(
                    text(
                        "SELECT bool_and(relforcerowsecurity) FROM pg_class"
                        " WHERE relname IN ('cases', 'case_events')"
                    )
                )
            ).scalar_one()
        finally:
            await transaction.rollback()

    assert [flags[i] for i in ids] == [False, False, True, True, True, False, True]
    assert forced is True
