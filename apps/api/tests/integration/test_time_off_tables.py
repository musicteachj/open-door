"""The time-off tables (migration 0009): who sees a row, what the API may change, and the rules the
schema holds on its own.

A request is a tenant row: Postgres shows it to the whole sandbox, and the policy layer decides who
reads which. A proposal belongs to the one person it was made for, HR included, like the assistant's
other tables. Both only move forward: a trigger refuses every status change but the planned ones.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.sandbox.seed import SeedCompany
from tests.integration.conftest import (
    MakeTenant,
    SampleTenant,
    write_assistant_rows,
    write_time_off_rows,
)
from tests.integration.test_cleanup import delete_tenant, rows_left

pytestmark = pytest.mark.integration

NEW_TABLES = ("time_off_openings", "time_off_requests", "ai_proposals")
# Far enough ahead of the request make_tenant writes (30 days out) that no range below overlaps it.
START = datetime.now(UTC).date() + timedelta(days=100)
NOW = datetime(2026, 12, 1, 15, 0, tzinfo=UTC)
STATUSES = ("pending", "approved", "denied", "recorded", "canceled")


def persona(company: SeedCompany, key: str) -> UUID:
    return next(p.id for p in company.people if p.persona_key == key)


def as_employee(tenant: SampleTenant) -> TenantContext:
    return TenantContext(tenant.id, tenant.employee_id)


async def scalar(session: AsyncSession, query: str, **params: Any) -> Any:
    return (await session.execute(text(query), params)).scalar_one()


# Each helper below builds its INSERT from column names written in this file, never from input.


async def insert_request(session: AsyncSession, tenant: SampleTenant, **overrides: Any) -> UUID:
    """A request for the employee. The defaults are a one-day pending PTO request made on the
    page; `overrides` replace any column."""
    values: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": tenant.id,
        "person_id": tenant.employee_id,
        "type": "pto",
        "start_date": START,
        "end_date": START,
        "amount_minutes": 480,
        "status": "pending",
        "created_via": "ui",
        **overrides,
    }
    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)
    await session.execute(
        text(f"INSERT INTO time_off_requests ({columns}) VALUES ({placeholders})"),  # noqa: S608
        values,
    )
    return values["id"]  # type: ignore[no-any-return]


# A request in each state a trigger test starts from, with the columns that state needs.
def state_columns(tenant: SampleTenant, request_type: str, status: str) -> dict[str, Any]:
    columns: dict[str, Any] = {"type": request_type, "status": status}
    if status in ("approved", "denied"):
        columns |= {"decided_by": tenant.hr_id, "decided_at": NOW}
    if status == "denied":
        columns["decision_note"] = "Coverage is thin that week."
    if status == "canceled":
        columns["canceled_at"] = NOW
    return columns


async def a_conversation_and_turn(session: AsyncSession) -> tuple[UUID, UUID]:
    conversation_id = await scalar(session, "SELECT id FROM ai_conversations")
    turn_id = await scalar(session, "SELECT id FROM ai_turns")
    return conversation_id, turn_id


async def insert_proposal(
    session: AsyncSession, tenant: SampleTenant, *, expires_in: str = "15 minutes", **overrides: Any
) -> UUID:
    """A pending `timeoff.request` proposal in the employee's own conversation and turn, unless
    `overrides` names a conversation and a turn. It expires `expires_in` after the database's
    clock (an interval such as '15 minutes'), unless `overrides` gives an `expires_at`. Leave
    `created_at` out: the database stamps it."""
    values: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": tenant.id,
        "person_id": tenant.employee_id,
        "action": "timeoff.request",
        "payload": "{}",
        "card": "{}",
        "status": "pending",
        **overrides,
    }
    if "conversation_id" not in values:
        # A conversation of its own: the sample tenant's one already holds a pending proposal, and
        # a conversation may hold only one (migration 0010).
        rows = await write_assistant_rows(session, tenant.id, values["person_id"])
        values["conversation_id"], values["turn_id"] = rows.conversation_id, rows.turn_id
    sql_values = {name: f":{name}" for name in values}
    for name in ("payload", "card", "outcome"):
        if name in values:
            sql_values[name] = f"CAST(:{name} AS jsonb)"
    if "expires_at" not in values:
        sql_values["expires_at"] = "now() + CAST(CAST(:expires_in AS text) AS interval)"
        values["expires_in"] = expires_in
    columns = ", ".join(sql_values)
    placeholders = ", ".join(sql_values.values())
    await session.execute(
        text(f"INSERT INTO ai_proposals ({columns}) VALUES ({placeholders})"),  # noqa: S608
        values,
    )
    return values["id"]  # type: ignore[no-any-return]


# --- Who sees a proposal -----------------------------------------------------------------------


async def prepare_priyas_rows(app_engine: AsyncEngine, company: SeedCompany) -> tuple[UUID, UUID]:
    """Priya's proposal and the request it made, in a seeded sandbox. Returns both IDs."""
    priya = persona(company, "priya")
    async with tenant_session(app_engine, TenantContext(company.tenant_id, priya)) as session:
        assistant = await write_assistant_rows(session, company.tenant_id, priya)
        rows = await write_time_off_rows(session, company.tenant_id, priya, assistant)
    return rows.proposal_id, rows.request_id


async def test_a_person_sees_their_own_proposal_and_can_end_it(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    proposal_id, _ = await prepare_priyas_rows(app_engine, seeded_sandbox)
    context = TenantContext(seeded_sandbox.tenant_id, persona(seeded_sandbox, "priya"))

    async with tenant_session(app_engine, context) as session:
        assert await scalar(session, "SELECT count(*) FROM ai_proposals") == 1
        result = await session.execute(
            text("UPDATE ai_proposals SET status = 'canceled', ended_at = now() WHERE id = :id"),
            {"id": proposal_id},
        )
        assert result.rowcount == 1  # type: ignore[attr-defined]


@pytest.mark.parametrize("who", ["marcus", "dana"])
async def test_nobody_else_sees_or_changes_a_proposal_not_even_hr(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany, who: str
) -> None:
    proposal_id, _ = await prepare_priyas_rows(app_engine, seeded_sandbox)
    other = persona(seeded_sandbox, who)

    async with tenant_session(
        app_engine, TenantContext(seeded_sandbox.tenant_id, other)
    ) as session:
        # Dana is HR. The flag opens the private-details rule, and must not open this one.
        await set_is_hr(session, who == "dana")
        seen = await scalar(session, "SELECT count(*) FROM ai_proposals")
        updated = await session.execute(
            text("UPDATE ai_proposals SET status = 'canceled', ended_at = now() WHERE id = :id"),
            {"id": proposal_id},
        )

    assert seen == 0
    assert updated.rowcount == 0  # type: ignore[attr-defined]
    async with tenant_session(
        app_engine, TenantContext(seeded_sandbox.tenant_id, persona(seeded_sandbox, "priya"))
    ) as session:
        assert await scalar(session, "SELECT status FROM ai_proposals") == "pending"


async def test_a_person_cannot_write_a_proposal_for_someone_else(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        conversation_id, turn_id = await a_conversation_and_turn(session)

    # A proposal for Priya, written in her colleague's transaction.
    with pytest.raises(DBAPIError, match="violates row-level security policy"):
        async with tenant_session(
            app_engine, TenantContext(tenant.id, tenant.colleague_id)
        ) as session:
            await session.execute(
                text(
                    "INSERT INTO ai_proposals (tenant_id, person_id, conversation_id, turn_id,"
                    " action, payload, card, status, expires_at) VALUES (:tenant_id, :person_id,"
                    " :conversation_id, :turn_id, 'timeoff.request', '{}', '{}', 'pending',"
                    " now() + interval '15 minutes')"
                ),
                {
                    "tenant_id": tenant.id,
                    "person_id": tenant.employee_id,
                    "conversation_id": conversation_id,
                    "turn_id": turn_id,
                },
            )


async def test_requests_and_openings_are_visible_across_the_sandbox(
    app_engine: AsyncEngine, seeded_sandbox: SeedCompany
) -> None:
    # They carry the tenant rule only: the policy layer decides who reads whose.
    _, request_id = await prepare_priyas_rows(app_engine, seeded_sandbox)
    marcus = persona(seeded_sandbox, "marcus")

    async with tenant_session(
        app_engine, TenantContext(seeded_sandbox.tenant_id, marcus)
    ) as session:
        # Everything in the sandbox: the seed's history and openings, and Priya's one new request.
        # Priya already had her opening from the seed, so no second one was added.
        assert await scalar(session, "SELECT count(*) FROM time_off_requests") == (
            len(seeded_sandbox.time_off_requests) + 1
        )
        assert await scalar(session, "SELECT count(*) FROM time_off_openings") == (
            len(seeded_sandbox.time_off_openings)
        )
        assert await scalar(
            session, "SELECT person_id FROM time_off_requests WHERE id = :id", id=request_id
        ) == persona(seeded_sandbox, "priya")


# --- Request status changes --------------------------------------------------------------------

REQUEST_STARTS = (
    ("pto", "pending"),
    ("pto", "approved"),
    ("pto", "denied"),
    ("pto", "canceled"),
    ("sick", "recorded"),
    ("sick", "canceled"),
)
LEGAL_REQUEST_MOVES = {
    ("pending", "approved"),
    ("pending", "denied"),
    ("pending", "canceled"),
    ("approved", "canceled"),
    ("recorded", "canceled"),
}
ILLEGAL_REQUEST_MOVES = [
    (request_type, start, target)
    for request_type, start in REQUEST_STARTS
    for target in STATUSES
    if (start, target) not in LEGAL_REQUEST_MOVES
]
# The columns that go with each legal move.
LEGAL_REQUEST_UPDATES = [
    ("pto", "pending", "approved", "status = 'approved', decided_by = :hr, decided_at = now()"),
    (
        "pto",
        "pending",
        "denied",
        "status = 'denied', decided_by = :hr, decided_at = now(), decision_note = 'Not that week'",
    ),
    ("pto", "pending", "canceled", "status = 'canceled', canceled_at = now()"),
    ("pto", "approved", "canceled", "status = 'canceled', canceled_at = now()"),
    ("sick", "recorded", "canceled", "status = 'canceled', canceled_at = now()"),
]


@pytest.mark.parametrize(("request_type", "start", "target", "assignments"), LEGAL_REQUEST_UPDATES)
async def test_a_request_may_make_each_planned_status_change(
    app_engine: AsyncEngine,
    make_tenant: MakeTenant,
    request_type: str,
    start: str,
    target: str,
    assignments: str,
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        request_id = await insert_request(
            session, tenant, **state_columns(tenant, request_type, start)
        )

    async with tenant_session(app_engine, as_employee(tenant)) as session:
        result = await session.execute(
            text(f"UPDATE time_off_requests SET {assignments} WHERE id = :id"),  # noqa: S608
            {"id": request_id, "hr": tenant.hr_id},
        )
        assert result.rowcount == 1  # type: ignore[attr-defined]
        assert (
            await scalar(
                session, "SELECT status FROM time_off_requests WHERE id = :id", id=request_id
            )
            == target
        )


@pytest.mark.parametrize(("request_type", "start", "target"), ILLEGAL_REQUEST_MOVES)
async def test_a_request_refuses_every_other_status_change(
    app_engine: AsyncEngine, make_tenant: MakeTenant, request_type: str, start: str, target: str
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        request_id = await insert_request(
            session, tenant, **state_columns(tenant, request_type, start)
        )

    # Nothing leaves denied or canceled, a status can't repeat, and no move goes backward or
    # sideways (a same-status update is in the list: start == target).
    with pytest.raises(DBAPIError, match="cannot change") as raised:
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text("UPDATE time_off_requests SET status = :target WHERE id = :id"),
                {"id": request_id, "target": target},
            )
    assert getattr(raised.value.orig, "sqlstate", None) == "OD003"


async def test_a_request_refuses_a_status_that_does_not_exist(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        request_id = await insert_request(session, tenant)

    with pytest.raises(DBAPIError, match="cannot change") as raised:
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text("UPDATE time_off_requests SET status = 'archived' WHERE id = :id"),
                {"id": request_id},
            )
    assert getattr(raised.value.orig, "sqlstate", None) == "OD003"


@pytest.mark.parametrize(
    "assignments",
    [
        "decided_by = :other",
        "decided_at = now() + interval '1 day'",
        "decision_note = 'Changed after the fact'",
        "decided_by = NULL, decided_at = NULL",
    ],
)
async def test_the_decision_cannot_change_when_an_approved_request_is_canceled(
    app_engine: AsyncEngine, make_tenant: MakeTenant, assignments: str
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        request_id = await insert_request(
            session, tenant, **state_columns(tenant, "pto", "approved")
        )

    with pytest.raises(DBAPIError, match="decision") as raised:
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text(
                    "UPDATE time_off_requests SET status = 'canceled', canceled_at = now(),"  # noqa: S608
                    f" {assignments} WHERE id = :id"
                ),
                {"id": request_id, "other": tenant.colleague_id},
            )
    assert getattr(raised.value.orig, "sqlstate", None) == "OD003"


@pytest.mark.parametrize(
    "assignments",
    [
        "status = 'approved', decided_by = :employee, decided_at = now()",
        "status = 'denied', decided_by = :employee, decided_at = now(), decision_note = 'No'",
    ],
)
async def test_a_person_cannot_decide_their_own_request(
    app_engine: AsyncEngine, make_tenant: MakeTenant, assignments: str
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        request_id = await insert_request(session, tenant)

    # The trigger allows the move and the foreign key allows the person: the check refuses.
    with pytest.raises(IntegrityError, match="ck_time_off_requests_no_self_decision"):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text(f"UPDATE time_off_requests SET {assignments} WHERE id = :id"),  # noqa: S608
                {"id": request_id, "employee": tenant.employee_id},
            )


async def test_the_decision_is_kept_when_an_approved_request_is_canceled(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        request_id = await insert_request(
            session, tenant, **state_columns(tenant, "pto", "approved")
        )

    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await session.execute(
            text(
                "UPDATE time_off_requests SET status = 'canceled', canceled_at = now()"
                " WHERE id = :id"
            ),
            {"id": request_id},
        )
        row = (
            await session.execute(
                text(
                    "SELECT decided_by, decided_at IS NOT NULL FROM time_off_requests"
                    " WHERE id = :id"
                ),
                {"id": request_id},
            )
        ).one()
    assert row == (tenant.hr_id, True)


async def test_canceled_at_changes_only_with_a_move_to_canceled(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        request_id = await insert_request(session, tenant)

    with pytest.raises(DBAPIError, match="canceled_at") as raised:
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text(
                    "UPDATE time_off_requests SET status = 'approved', decided_by = :hr,"
                    " decided_at = now(), canceled_at = now() WHERE id = :id"
                ),
                {"id": request_id, "hr": tenant.hr_id},
            )
    assert getattr(raised.value.orig, "sqlstate", None) == "OD003"


async def test_a_decision_is_written_only_when_a_pending_request_is_approved_or_denied(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        request_id = await insert_request(session, tenant)

    # A pending request that is canceled can't pick up a decision on the way.
    with pytest.raises(DBAPIError, match="decision") as raised:
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text(
                    "UPDATE time_off_requests SET status = 'canceled', canceled_at = now(),"
                    " decided_by = :hr, decided_at = now() WHERE id = :id"
                ),
                {"id": request_id, "hr": tenant.hr_id},
            )
    assert getattr(raised.value.orig, "sqlstate", None) == "OD003"


REQUEST_COLUMNS_NOT_UPDATABLE = (
    "id",
    "tenant_id",
    "person_id",
    "type",
    "start_date",
    "end_date",
    "partial_minutes",
    "amount_minutes",
    "created_at",
    "created_via",
    "proposal_id",
)


@pytest.mark.parametrize("column", REQUEST_COLUMNS_NOT_UPDATABLE)
async def test_a_requests_identity_dates_amount_and_origin_can_never_be_updated(
    app_engine: AsyncEngine, make_tenant: MakeTenant, column: str
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await insert_request(session, tenant)

    # While it is pending, so it is the grant that refuses, not the trigger.
    with pytest.raises(DBAPIError, match="permission denied for table time_off_requests"):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text(f"UPDATE time_off_requests SET {column} = {column}")  # noqa: S608
            )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE time_off_openings SET amount_minutes = 0",
        "UPDATE time_off_openings SET as_of = as_of",
        "DELETE FROM time_off_openings",
        "DELETE FROM time_off_requests",
        "DELETE FROM ai_proposals",
    ],
)
async def test_the_api_cannot_delete_rows_or_change_an_opening(
    app_engine: AsyncEngine, make_tenant: MakeTenant, statement: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(DBAPIError, match="permission denied for table"):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(text(statement))


# --- Proposal status changes -------------------------------------------------------------------

PROPOSAL_FINAL = ("executed", "failed", "canceled", "expired")


@pytest.mark.parametrize("target", PROPOSAL_FINAL)
async def test_a_pending_proposal_can_end_once_in_each_final_status(
    app_engine: AsyncEngine, make_tenant: MakeTenant, target: str
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        proposal_id = await insert_proposal(session, tenant)

    async with tenant_session(app_engine, as_employee(tenant)) as session:
        result = await session.execute(
            text(
                "UPDATE ai_proposals SET status = :target, ended_at = now(),"
                ' outcome = CAST(\'{"requestId": "abc"}\' AS jsonb) WHERE id = :id'
            ),
            {"id": proposal_id, "target": target},
        )
        assert result.rowcount == 1  # type: ignore[attr-defined]

    # A final status can't change, not even to itself.
    for again in PROPOSAL_FINAL:
        with pytest.raises(DBAPIError, match="cannot change") as raised:
            async with tenant_session(app_engine, as_employee(tenant)) as session:
                await session.execute(
                    text("UPDATE ai_proposals SET status = :again WHERE id = :id"),
                    {"id": proposal_id, "again": again},
                )
        assert getattr(raised.value.orig, "sqlstate", None) == "OD003"
    with pytest.raises(DBAPIError, match="cannot change") as raised:
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text("UPDATE ai_proposals SET outcome = NULL WHERE id = :id"),
                {"id": proposal_id},
            )
    assert getattr(raised.value.orig, "sqlstate", None) == "OD003"


@pytest.mark.parametrize("target", ["pending", "approved", "archived"])
async def test_a_pending_proposal_cannot_move_anywhere_but_a_final_status(
    app_engine: AsyncEngine, make_tenant: MakeTenant, target: str
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        proposal_id = await insert_proposal(session, tenant)

    with pytest.raises(DBAPIError, match="cannot change") as raised:
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text("UPDATE ai_proposals SET status = :target WHERE id = :id"),
                {"id": proposal_id, "target": target},
            )
    assert getattr(raised.value.orig, "sqlstate", None) == "OD003"


async def test_a_pending_proposal_cannot_get_an_outcome_without_ending(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        proposal_id = await insert_proposal(session, tenant)

    with pytest.raises(DBAPIError, match="cannot change") as raised:
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text("UPDATE ai_proposals SET outcome = '{}' WHERE id = :id"),
                {"id": proposal_id},
            )
    assert getattr(raised.value.orig, "sqlstate", None) == "OD003"


PROPOSAL_COLUMNS_NOT_UPDATABLE = (
    "id",
    "tenant_id",
    "person_id",
    "conversation_id",
    "turn_id",
    "action",
    "payload",
    "card",
    "created_at",
    "expires_at",
)


@pytest.mark.parametrize("column", PROPOSAL_COLUMNS_NOT_UPDATABLE)
async def test_a_proposals_identity_payload_card_and_expiry_can_never_be_updated(
    app_engine: AsyncEngine, make_tenant: MakeTenant, column: str
) -> None:
    tenant = await make_tenant()

    # While it is pending, so it is the grant that refuses, not the trigger.
    with pytest.raises(DBAPIError, match="permission denied for table ai_proposals"):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(text(f"UPDATE ai_proposals SET {column} = {column}"))  # noqa: S608


# --- The checks --------------------------------------------------------------------------------

LONG_NOTE = "x" * 301
REQUEST_CHECKS = [
    ("ck_time_off_requests_type", {"type": "vacation"}),
    ("ck_time_off_requests_status", {"status": "archived"}),
    ("ck_time_off_requests_created_via", {"created_via": "email"}),
    # A PTO request is never recorded, and a sick one is only recorded or canceled.
    ("ck_time_off_requests_status_matches_type", {"type": "pto", "status": "recorded"}),
    ("ck_time_off_requests_status_matches_type", {"type": "sick", "status": "pending"}),
    (
        "ck_time_off_requests_status_matches_type",
        {"type": "sick", "status": "approved", "decided_by": "hr", "decided_at": NOW},
    ),
    (
        "ck_time_off_requests_status_matches_type",
        {"type": "sick", "status": "denied", "decided_by": "hr", "decided_at": NOW},
    ),
    ("ck_time_off_requests_dates_in_order", {"end_date": START - timedelta(days=1)}),
    ("ck_time_off_requests_at_most_31_days", {"end_date": START + timedelta(days=31)}),
    ("ck_time_off_requests_partial_minutes_match_the_engine", {"partial_minutes": 120}),
    (
        "ck_time_off_requests_partial_minutes_match_the_engine",
        {"partial_minutes": 240, "end_date": START + timedelta(days=1)},
    ),
    (
        "ck_time_off_requests_partial_minutes_match_the_engine",
        {"type": "sick", "status": "recorded", "partial_minutes": 90},
    ),
    (
        "ck_time_off_requests_partial_minutes_match_the_engine",
        {"type": "sick", "status": "recorded", "partial_minutes": 30},
    ),
    (
        "ck_time_off_requests_partial_minutes_match_the_engine",
        {"type": "sick", "status": "recorded", "partial_minutes": 540},
    ),
    (
        "ck_time_off_requests_partial_minutes_match_the_engine",
        {"type": "sick", "status": "recorded", "partial_minutes": 0},
    ),
    ("ck_time_off_requests_amount_is_positive", {"amount_minutes": 0}),
    ("ck_time_off_requests_amount_is_positive", {"amount_minutes": -480}),
    # Decision columns must fit the status.
    ("ck_time_off_requests_decision_matches_status", {"decided_by": "hr"}),
    ("ck_time_off_requests_decision_matches_status", {"canceled_at": NOW}),
    ("ck_time_off_requests_decision_matches_status", {"status": "approved"}),
    (
        "ck_time_off_requests_decision_matches_status",
        {"status": "approved", "decided_by": "hr", "decided_at": NOW, "canceled_at": NOW},
    ),
    (
        "ck_time_off_requests_decision_matches_status",
        {"status": "denied", "decided_by": "hr"},
    ),
    ("ck_time_off_requests_decision_matches_status", {"status": "canceled"}),
    (
        "ck_time_off_requests_decision_matches_status",
        {"status": "canceled", "canceled_at": NOW, "decided_by": "hr"},
    ),
    (
        "ck_time_off_requests_decision_matches_status",
        {"type": "sick", "status": "recorded", "decided_by": "hr", "decided_at": NOW},
    ),
    # A note on a pending request breaks both the decision check and the note check. Postgres
    # reports one of them (the first by name), so either name will do: the row is refused.
    (
        "ck_time_off_requests_decision_matches_status|"
        "ck_time_off_requests_decision_note_is_a_short_denial_note",
        {"decision_note": "ok"},
    ),
    # A denial is not a cancellation.
    (
        "ck_time_off_requests_decision_matches_status",
        {
            "status": "denied",
            "decided_by": "hr",
            "decided_at": NOW,
            "decision_note": "No",
            "canceled_at": NOW,
        },
    ),
    # A note is a denial's alone, and short.
    (
        "ck_time_off_requests_decision_note_is_a_short_denial_note",
        {"status": "approved", "decided_by": "hr", "decided_at": NOW, "decision_note": "ok"},
    ),
    (
        "ck_time_off_requests_decision_note_is_a_short_denial_note",
        {"status": "canceled", "canceled_at": NOW, "decision_note": "ok"},
    ),
    (
        "ck_time_off_requests_decision_note_is_a_short_denial_note",
        {"status": "denied", "decided_by": "hr", "decided_at": NOW, "decision_note": LONG_NOTE},
    ),
    # Nobody decides their own request, however the row gets there.
    (
        "ck_time_off_requests_no_self_decision",
        {"status": "approved", "decided_by": "employee", "decided_at": NOW},
    ),
    (
        "ck_time_off_requests_no_self_decision",
        {
            "status": "denied",
            "decided_by": "employee",
            "decided_at": NOW,
            "decision_note": "No",
        },
    ),
    # The proposal and the way it was made go together.
    ("ck_time_off_requests_proposal_matches_created_via", {"created_via": "assistant"}),
    (
        "ck_time_off_requests_proposal_matches_created_via",
        {"created_via": "ui", "proposal_id": uuid4()},
    ),
]


@pytest.mark.parametrize(("constraint", "overrides"), REQUEST_CHECKS)
async def test_the_request_checks_refuse_a_bad_row(
    app_engine: AsyncEngine, make_tenant: MakeTenant, constraint: str, overrides: dict[str, Any]
) -> None:
    tenant = await make_tenant()
    columns = {"hr": tenant.hr_id, "employee": tenant.employee_id}
    overrides = {
        key: columns.get(value, value) if isinstance(value, str) else value
        for key, value in overrides.items()
    }

    with pytest.raises(IntegrityError, match=constraint):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await insert_request(session, tenant, **overrides)


async def test_a_good_request_of_every_kind_is_accepted(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    # The mirror of the checks above: the boundary rows they must not refuse.
    tenant = await make_tenant()
    day = START
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        for overrides in (
            # Thirty-one days is the longest.
            {"end_date": day + timedelta(days=30)},
            {"type": "pto", "partial_minutes": 240, "amount_minutes": 240},
            {"type": "sick", "status": "recorded", "partial_minutes": 60, "amount_minutes": 60},
            {"type": "sick", "status": "recorded", "partial_minutes": 480},
            {"type": "sick", "status": "canceled", "canceled_at": NOW},
            {
                "status": "denied",
                "decided_by": tenant.hr_id,
                "decided_at": NOW,
                "decision_note": "x" * 300,
            },
            {
                "status": "canceled",
                "canceled_at": NOW,
                "decided_by": tenant.hr_id,
                "decided_at": NOW,
            },
        ):
            # Each in a savepoint that is rolled back, so the rows don't overlap one another.
            async with session.begin_nested() as savepoint:
                await insert_request(session, tenant, **overrides)
                await savepoint.rollback()


PROPOSAL_CHECKS = [
    ("ck_ai_proposals_action", {"action": "timeoff.approve"}),
    # A proposal lives for 15 minutes at most, counted from the database's clock.
    ("ck_ai_proposals_expires_after_created", {"expires_in": "0 seconds"}),
    ("ck_ai_proposals_expires_after_created", {"expires_in": "-1 minutes"}),
    ("ck_ai_proposals_expires_within_15_minutes", {"expires_in": "16 minutes"}),
    ("ck_ai_proposals_expires_within_15_minutes", {"expires_in": "15 minutes 1 second"}),
]


@pytest.mark.parametrize(("constraint", "overrides"), PROPOSAL_CHECKS)
async def test_the_proposal_checks_refuse_a_bad_row(
    app_engine: AsyncEngine, make_tenant: MakeTenant, constraint: str, overrides: dict[str, Any]
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match=constraint):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await insert_proposal(session, tenant, **overrides)


@pytest.mark.parametrize("expires_in", ["1 second", "14 minutes", "15 minutes"])
async def test_a_proposal_may_live_for_up_to_fifteen_minutes(
    app_engine: AsyncEngine, make_tenant: MakeTenant, expires_in: str
) -> None:
    tenant = await make_tenant()

    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await insert_proposal(session, tenant, expires_in=expires_in)


PROPOSAL_STATUS_CHECKS = [
    ("ck_ai_proposals_status", {"status": "approved", "ended_at": NOW}),
    ("ck_ai_proposals_ended_at_matches_status", {"status": "executed"}),
    ("ck_ai_proposals_ended_at_matches_status", {"status": "pending", "ended_at": NOW}),
]


@pytest.mark.parametrize(("constraint", "overrides"), PROPOSAL_STATUS_CHECKS)
async def test_the_proposal_status_checks_hold_when_the_triggers_are_off(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    constraint: str,
    overrides: dict[str, Any],
) -> None:
    # Through the API, the triggers refuse these rows first (a proposal is born pending, and its
    # ended_at is the server's). These checks are the second wall, so the owner (a superuser, which
    # may turn user triggers off for one transaction) proves them on their own.
    tenant = await make_tenant()
    async with owner_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(text("SET LOCAL session_replication_role = replica"))
            conversation_id, turn_id = (
                await connection.execute(
                    text("SELECT conversation_id, id FROM ai_turns WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant.id},
                )
            ).one()
            values = {
                "tenant_id": tenant.id,
                "person_id": tenant.employee_id,
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "status": "pending",
                "ended_at": None,
                **overrides,
            }
            with pytest.raises(IntegrityError, match=constraint):
                await connection.execute(
                    text(
                        "INSERT INTO ai_proposals (tenant_id, person_id, conversation_id, turn_id,"
                        " action, payload, card, status, ended_at, expires_at) VALUES (:tenant_id,"
                        " :person_id, :conversation_id, :turn_id, 'timeoff.request', '{}', '{}',"
                        " :status, :ended_at, now() + interval '15 minutes')"
                    ),
                    values,
                )
        finally:
            await transaction.rollback()


# --- A proposal is born pending, and its clock is the server's ---------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "executed", "ended_at": NOW},
        {"status": "failed", "ended_at": NOW},
        {"status": "canceled", "ended_at": NOW},
        {"status": "expired", "ended_at": NOW},
        # The same, with the ended_at the status check would also want left out.
        {"status": "executed"},
        {"status": "pending", "ended_at": NOW},
        {"status": "pending", "outcome": '{"requestId": "abc"}'},
    ],
)
async def test_a_proposal_must_be_inserted_pending_and_unended(
    app_engine: AsyncEngine, make_tenant: MakeTenant, overrides: dict[str, Any]
) -> None:
    tenant = await make_tenant()

    with pytest.raises(DBAPIError, match="must be pending") as raised:
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await insert_proposal(session, tenant, **overrides)
    assert getattr(raised.value.orig, "sqlstate", None) == "OD003"


async def test_the_database_stamps_when_a_proposal_was_created(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    # A created_at ten minutes back, with an expiry that fits it: only the stamp makes it false.
    backdated = datetime.now(UTC) - timedelta(minutes=10)

    async with tenant_session(app_engine, as_employee(tenant)) as session:
        proposal_id = await insert_proposal(
            session, tenant, created_at=backdated, expires_in="5 minutes"
        )
        stamped = await scalar(
            session,
            "SELECT created_at = now() FROM ai_proposals WHERE id = :id",
            id=proposal_id,
        )

    assert stamped is True


async def test_a_proposal_ends_at_the_servers_time_whatever_the_update_says(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        first = await insert_proposal(session, tenant)
        second = await insert_proposal(session, tenant)

    async with tenant_session(app_engine, as_employee(tenant)) as session:
        # One names another time, and one names none (the ended_at check would refuse that, if
        # the trigger didn't fill it in first).
        await session.execute(
            text("UPDATE ai_proposals SET status = 'canceled', ended_at = :then WHERE id = :id"),
            {"id": first, "then": NOW},
        )
        await session.execute(
            text("UPDATE ai_proposals SET status = 'canceled' WHERE id = :id"), {"id": second}
        )
        ended = await scalar(
            session,
            "SELECT count(*) FROM ai_proposals WHERE id IN (:first, :second) AND ended_at = now()",
            first=first,
            second=second,
        )

    assert ended == 2


async def test_an_expired_proposal_cannot_be_executed_but_can_still_end_otherwise(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        ids = {
            name: await insert_proposal(session, tenant, expires_in="1 second")
            for name in ("executed", "expired", "canceled", "failed")
        }
    # now() is the start of a transaction, so a new one after the expiry sees the later time.
    await asyncio.sleep(1.2)

    with pytest.raises(DBAPIError, match="expired proposal cannot be executed") as raised:
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text("UPDATE ai_proposals SET status = 'executed' WHERE id = :id"),
                {"id": ids["executed"]},
            )
    assert getattr(raised.value.orig, "sqlstate", None) == "OD003"
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        assert (
            await scalar(
                session, "SELECT status FROM ai_proposals WHERE id = :id", id=ids["executed"]
            )
            == "pending"
        )
        for status in ("expired", "canceled", "failed"):
            result = await session.execute(
                text("UPDATE ai_proposals SET status = :status WHERE id = :id"),
                {"id": ids[status], "status": status},
            )
            assert result.rowcount == 1  # type: ignore[attr-defined]


async def test_an_opening_refuses_a_negative_amount_and_a_second_row_for_a_person(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    other = tenant.colleague_id
    insert = (
        "INSERT INTO time_off_openings (tenant_id, person_id, as_of, amount_minutes)"
        " VALUES (:tenant_id, :person_id, :as_of, :amount)"
    )

    with pytest.raises(IntegrityError, match="ck_time_off_openings_amount_not_negative"):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text(insert),
                {"tenant_id": tenant.id, "person_id": other, "as_of": START, "amount": -1},
            )
    # make_tenant already wrote one for the employee.
    with pytest.raises(IntegrityError, match="uq_time_off_openings_tenant_id_person_id"):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(
                text(insert),
                {
                    "tenant_id": tenant.id,
                    "person_id": tenant.employee_id,
                    "as_of": START,
                    "amount": 0,
                },
            )
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await session.execute(
            text(insert), {"tenant_id": tenant.id, "person_id": other, "as_of": START, "amount": 0}
        )


# --- Overlaps ----------------------------------------------------------------------------------

OVERLAP = "ex_time_off_requests_no_overlap"


async def test_two_overlapping_open_requests_for_one_person_are_refused(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await insert_request(session, tenant, end_date=START + timedelta(days=2))

    # One day inside the range, and a range that ends on the first day.
    for start, end in ((START + timedelta(days=1),) * 2, (START - timedelta(days=3), START)):
        with pytest.raises(IntegrityError, match=OVERLAP):
            async with tenant_session(app_engine, as_employee(tenant)) as session:
                await insert_request(session, tenant, start_date=start, end_date=end)


@pytest.mark.parametrize("first", ["pending", "approved"])
async def test_a_booked_or_pending_request_blocks_an_overlap_and_a_recorded_one_too(
    app_engine: AsyncEngine, make_tenant: MakeTenant, first: str
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await insert_request(session, tenant, **state_columns(tenant, "pto", first))
        await insert_request(
            session,
            tenant,
            **state_columns(tenant, "sick", "recorded"),
            start_date=START + timedelta(days=7),
            end_date=START + timedelta(days=7),
        )

    for day in (START, START + timedelta(days=7)):
        with pytest.raises(IntegrityError, match=OVERLAP):
            async with tenant_session(app_engine, as_employee(tenant)) as session:
                await insert_request(session, tenant, start_date=day, end_date=day)


async def test_two_people_may_take_the_same_days(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await insert_request(session, tenant)
        await insert_request(session, tenant, person_id=tenant.colleague_id)


async def test_a_canceled_or_denied_request_does_not_block_the_days(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await insert_request(session, tenant, **state_columns(tenant, "pto", "canceled"))
        await insert_request(session, tenant, **state_columns(tenant, "pto", "denied"))
        await insert_request(session, tenant)


async def test_canceling_a_request_frees_its_days(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        request_id = await insert_request(session, tenant)

    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await session.execute(
            text(
                "UPDATE time_off_requests SET status = 'canceled', canceled_at = now()"
                " WHERE id = :id"
            ),
            {"id": request_id},
        )
        await insert_request(session, tenant)


async def test_ranges_that_touch_but_do_not_overlap_are_accepted(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await insert_request(session, tenant, end_date=START + timedelta(days=2))
        # The next day, and the day before: both ends are inclusive, so these are adjacent.
        await insert_request(
            session,
            tenant,
            start_date=START + timedelta(days=3),
            end_date=START + timedelta(days=4),
        )
        await insert_request(
            session,
            tenant,
            start_date=START - timedelta(days=2),
            end_date=START - timedelta(days=1),
        )


# --- Whose proposal, whose conversation --------------------------------------------------------


async def test_a_proposal_cannot_name_another_persons_conversation(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        # A conversation with no pending proposal, so the one-pending index (0010) isn't what
        # refuses the insert before the key does.
        rows = await write_assistant_rows(session, tenant.id, tenant.employee_id)
        conversation_id, turn_id = rows.conversation_id, rows.turn_id

    # The colleague writes their own proposal (the person rule allows that) but names Priya's
    # conversation and turn. The row-level rule can't see those rows, and a foreign key check
    # ignores it, so the three-column key is what refuses.
    with pytest.raises(IntegrityError, match="fk_ai_proposals_conversation_owner"):
        async with tenant_session(
            app_engine, TenantContext(tenant.id, tenant.colleague_id)
        ) as session:
            await session.execute(
                text(
                    "INSERT INTO ai_proposals (tenant_id, person_id, conversation_id, turn_id,"
                    " action, payload, card, status, expires_at) VALUES (:tenant_id, :person_id,"
                    " :conversation_id, :turn_id, 'timeoff.request', '{}', '{}', 'pending',"
                    " now() + interval '15 minutes')"
                ),
                {
                    "tenant_id": tenant.id,
                    "person_id": tenant.colleague_id,
                    "conversation_id": conversation_id,
                    "turn_id": turn_id,
                },
            )


async def test_a_proposal_cannot_name_a_turn_from_another_conversation(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        _, turn_id = await a_conversation_and_turn(session)
        second = await scalar(
            session,
            "INSERT INTO ai_conversations (tenant_id, person_id, model, guard_model, effort,"
            " prompt_version, toolset_version, key_id, wrapped_key) VALUES (:tenant_id, :person_id,"
            " 'm', 'g', 'medium', '1', '1', 'test', '\\x01'::bytea) RETURNING id",
            tenant_id=tenant.id,
            person_id=tenant.employee_id,
        )

    # Her own conversation, and her own turn, but the turn belongs to the first conversation.
    with pytest.raises(IntegrityError, match="fk_ai_proposals_turn_owner"):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await insert_proposal(session, tenant, conversation_id=second, turn_id=turn_id)


async def test_a_request_cannot_name_another_persons_proposal(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        # One no request has used, so it is the owner key that refuses, not the unique index.
        proposal_id = await insert_proposal(session, tenant)

    with pytest.raises(IntegrityError, match="fk_time_off_requests_proposal_owner"):
        async with tenant_session(
            app_engine, TenantContext(tenant.id, tenant.colleague_id)
        ) as session:
            await insert_request(
                session,
                tenant,
                person_id=tenant.colleague_id,
                created_via="assistant",
                proposal_id=proposal_id,
            )


async def test_a_request_may_name_its_own_persons_proposal(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        proposal_id = await insert_proposal(session, tenant)
        await insert_request(
            session,
            tenant,
            start_date=START + timedelta(days=60),
            end_date=START + timedelta(days=60),
            created_via="assistant",
            proposal_id=proposal_id,
        )


async def test_a_proposal_makes_at_most_one_request(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        # make_tenant's request already names this proposal.
        proposal_id = await scalar(session, "SELECT proposal_id FROM time_off_requests")

    # A second request for the same proposal, on days that overlap nothing.
    with pytest.raises(IntegrityError, match="uq_time_off_requests_tenant_id_proposal_id"):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await insert_request(
                session,
                tenant,
                start_date=START + timedelta(days=60),
                end_date=START + timedelta(days=60),
                created_via="assistant",
                proposal_id=proposal_id,
            )


async def test_many_requests_may_have_no_proposal(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    # The unique index covers only requests made through the assistant.
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await insert_request(session, tenant)
        await insert_request(
            session,
            tenant,
            start_date=START + timedelta(days=5),
            end_date=START + timedelta(days=5),
        )


async def test_a_request_cannot_be_decided_by_someone_outside_the_sandbox(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant, other = await make_tenant(), await make_tenant()

    with pytest.raises(IntegrityError, match="fk_time_off_requests_tenant_id_decided_by_people"):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await insert_request(
                session,
                tenant,
                **state_columns(tenant, "pto", "approved") | {"decided_by": other.hr_id},
            )


# --- The audit trail ---------------------------------------------------------------------------

INSERT_AUDIT = (
    "INSERT INTO audit_events (tenant_id, actor_person_id, via, action, proposal_id)"
    " VALUES (:tenant_id, :actor, 'assistant', 'timeoff.requested', :proposal_id)"
)


async def test_an_audit_event_may_name_a_proposal_of_its_own_sandbox_only(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant, other = await make_tenant(), await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        mine = await scalar(session, "SELECT id FROM ai_proposals")
    async with tenant_session(app_engine, as_employee(other)) as session:
        theirs = await scalar(session, "SELECT id FROM ai_proposals")

    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await session.execute(
            text(INSERT_AUDIT),
            {"tenant_id": tenant.id, "actor": tenant.employee_id, "proposal_id": mine},
        )
    for proposal_id in (theirs, uuid4()):
        with pytest.raises(IntegrityError, match="fk_audit_events_tenant_id_proposal_id"):
            async with tenant_session(app_engine, as_employee(tenant)) as session:
                await session.execute(
                    text(INSERT_AUDIT),
                    {
                        "tenant_id": tenant.id,
                        "actor": tenant.employee_id,
                        "proposal_id": proposal_id,
                    },
                )


async def test_an_audit_event_with_no_proposal_is_still_accepted(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        await session.execute(
            text(INSERT_AUDIT),
            {"tenant_id": tenant.id, "actor": tenant.employee_id, "proposal_id": None},
        )


# --- Deleting a sandbox ------------------------------------------------------------------------


async def test_deleting_an_expired_sandbox_removes_every_time_off_row(
    cleanup_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    make_tenant: MakeTenant,
    app_engine: AsyncEngine,
) -> None:
    expired = await make_tenant(expired=True)
    # An audit event that names the proposal, so the cascade runs through both tables that the
    # new foreign key joins.
    async with tenant_session(
        app_engine, TenantContext(expired.id, expired.employee_id)
    ) as session:
        proposal_id = await scalar(session, "SELECT id FROM ai_proposals")
        await session.execute(
            text(INSERT_AUDIT),
            {"tenant_id": expired.id, "actor": expired.employee_id, "proposal_id": proposal_id},
        )
    before = await rows_left(owner_engine, expired.id)

    deleted = await delete_tenant(cleanup_engine, expired.id)
    after = await rows_left(owner_engine, expired.id)

    assert deleted == 1
    assert {table: before[table] for table in NEW_TABLES} == dict.fromkeys(NEW_TABLES, 1)
    assert after == dict.fromkeys(after, 0)


# --- A person's schedule -----------------------------------------------------------------------

INSERT_PERSON = """
    INSERT INTO people (id, tenant_id, given_name, family_name, title, department_id, location_id,
                        work_email, employment_type, hire_date, scheduled_weekdays)
    SELECT gen_random_uuid(), tenant_id, 'Sam', 'Tester', title, department_id, location_id,
           'sam@juniperrow.example', employment_type, hire_date, CAST(:days AS smallint[])
    FROM people WHERE id = :me
    RETURNING scheduled_weekdays
"""


@pytest.mark.parametrize("days", [[], [0], [8], [1, 9], [-1]])
async def test_scheduled_weekdays_refuses_an_empty_list_and_values_outside_1_to_7(
    app_engine: AsyncEngine, make_tenant: MakeTenant, days: list[int]
) -> None:
    tenant = await make_tenant()

    with pytest.raises(IntegrityError, match="ck_people_scheduled_weekdays"):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await session.execute(text(INSERT_PERSON), {"days": days, "me": tenant.employee_id})


@pytest.mark.parametrize("days", [[3, 4, 5, 6, 7], [1], [1, 2, 3, 4, 5, 6, 7], [7, 1]])
async def test_scheduled_weekdays_accepts_a_real_schedule(
    app_engine: AsyncEngine, make_tenant: MakeTenant, days: list[int]
) -> None:
    tenant = await make_tenant()

    async with tenant_session(app_engine, as_employee(tenant)) as session:
        stored = await scalar(session, INSERT_PERSON, days=days, me=tenant.employee_id)

    assert stored == days


async def test_a_person_added_without_a_schedule_works_monday_to_friday(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    # The default is kept on purpose: sandboxes made before this migration, and any insert that
    # says nothing, get Monday to Friday. The seed writes every person's days explicitly.
    tenant = await make_tenant()

    async with tenant_session(app_engine, as_employee(tenant)) as session:
        result = await session.execute(text("SELECT DISTINCT scheduled_weekdays FROM people"))
        days: list[Any] = list(result.scalars())

    assert days == [[1, 2, 3, 4, 5]]


async def test_a_conversation_cannot_hold_two_pending_proposals(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    # The sample employee's conversation already holds one pending proposal.
    async with tenant_session(app_engine, as_employee(tenant)) as session:
        conversation_id, turn_id = await a_conversation_and_turn(session)

    with pytest.raises(IntegrityError, match="uq_ai_proposals_one_pending_per_conversation"):
        async with tenant_session(app_engine, as_employee(tenant)) as session:
            await insert_proposal(session, tenant, conversation_id=conversation_id, turn_id=turn_id)
