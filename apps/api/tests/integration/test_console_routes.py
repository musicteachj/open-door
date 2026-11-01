"""The console routes over HTTP, as HR's browser calls them.

The sandbox is the seeded company: Dana is HR, Marcus a manager, Priya and Mateo employees. Console
rows are written straight to the table (the turn's own write is tested in
`test_console_rows_written.py`), so every row's figures are known.
"""

import base64
import json
import logging
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.models import AiConsoleTurn, AiSpend, AuditEvent, Person
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.console import queries
from app.modules.console.metrics import TurnFacts
from tests.integration.conftest import Browser
from tests.test_console_metrics import CAP, HAND_WORKED, SPEND

pytestmark = pytest.mark.integration

TURNS = "/api/v1/console/turns"
METRICS = "/api/v1/console/metrics"
PLANTED = "Zebra-stripe-quokka-7731 about the layoff rumor"
UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
HQ_DAY = date(2026, 10, 30)


def switch(browser: Browser, persona: str) -> None:
    response = browser.client.put(
        "/api/v1/session/persona", json={"persona": persona}, headers=browser.csrf
    )
    assert response.status_code == 200, response.text


def sandbox_as(browser: Browser, persona: str = "dana") -> UUID:
    return UUID(browser.start_sandbox(persona)["tenant"]["id"])


def cursor_of(*parts: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(list(parts)).encode()).decode()


def timed(
    tenant_id: UUID,
    at: datetime,
    *,
    day: date | None = None,
    row_id: UUID | None = None,
    **changes: Any,
) -> dict[str, Any]:
    """A complete, unflagged console row."""
    return {
        "id": row_id or uuid4(),
        "tenant_id": tenant_id,
        "turn_id": uuid4(),
        "occurred_on": day or at.date(),
        "occurred_at": at,
        "flagged": False,
        "asker_role": "employee",
        "asker_location": "Oakland, CA",
        "outcome": "answered",
        "guard_category": "ordinary",
        "injection_suspected": False,
        "tools": [{"name": "search_handbook", "ok": True, "durationMs": 120}],
        "sections_retrieved": ["CA-4.3"],
        "sections_cited": ["CA-4.3"],
        **changes,
    }


def flagged(
    tenant_id: UUID, day: date = HQ_DAY, *, row_id: UUID | None = None, **changes: Any
) -> dict[str, Any]:
    return {
        "id": row_id or uuid4(),
        "tenant_id": tenant_id,
        "occurred_on": day,
        "flagged": True,
        "cost_usd": Decimal("0.003"),
        **changes,
    }


async def write_rows(engine: AsyncEngine, tenant_id: UUID, rows: Sequence[dict[str, Any]]) -> None:
    """Insert console rows as the sandbox's own login (a Core insert, with no RETURNING)."""
    async with tenant_session(engine, TenantContext(tenant_id, None)) as db:
        for row in rows:
            await db.execute(insert(AiConsoleTurn).values(**row))


def facts_row(tenant_id: UUID, index: int, facts: TurnFacts) -> dict[str, Any]:
    """The database row for one of `HAND_WORKED`'s facts."""
    at = datetime(2026, 10, 30, 17, 0, tzinfo=UTC) + timedelta(minutes=index)
    changes: dict[str, Any] = {
        "abandoned": facts.abandoned,
        "outcome": facts.outcome,
        "fallback": facts.fallback,
        "injection_suspected": facts.injection_suspected,
        "first_text_ms": facts.first_text_ms,
        "guard_ms": facts.guard_ms,
        "cost_usd": facts.cost_usd,
    }
    if facts.flagged:
        return flagged(tenant_id, HQ_DAY, **{k: v for k, v in changes.items() if k in KEPT})
    return timed(tenant_id, at, **changes, sections_retrieved=list(facts.sections_retrieved or ()))


# What a flagged row may hold besides its date.
KEPT = {"abandoned", "fallback", "first_text_ms", "guard_ms", "cost_usd"}


async def add_spend(
    engine: AsyncEngine, tenant_id: UUID, amount: str, *, purpose: str, kind: str = "reserve"
) -> None:
    async with tenant_session(engine, TenantContext(tenant_id, None)) as db:
        db.add(
            AiSpend(
                tenant_id=tenant_id,
                turn_id=None,
                purpose=purpose,
                kind=kind,
                amount_usd=Decimal(amount),
            )
        )


async def add_confirmed(
    engine: AsyncEngine,
    tenant_id: UUID,
    actions: Sequence[str],
    *,
    event: str = "proposal.confirmed",
) -> None:
    async with tenant_session(engine, TenantContext(tenant_id, None)) as db:
        for action in actions:
            db.add(
                AuditEvent(
                    tenant_id=tenant_id,
                    via="ui",
                    action=event,
                    target_type="proposal",
                    target_id=uuid4(),
                    before={"status": "pending"},
                    after={"action": action, "status": "executed"},
                )
            )


def get_ok(browser: Browser, path: str, **params: Any) -> Any:
    response = browser.client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def ids(page: dict[str, Any]) -> list[str]:
    return [item["id"] for item in page["items"]]


# --- Who may call ---------------------------------------------------------------------------


@pytest.mark.parametrize("persona", ["priya", "marcus", "mateo"])
@pytest.mark.parametrize("path", [TURNS, METRICS])
async def test_anyone_but_hr_gets_the_pages_not_found(
    browser: Browser, app_engine: AsyncEngine, persona: str, path: str
) -> None:
    tenant_id = sandbox_as(browser, "dana")
    await write_rows(
        app_engine, tenant_id, [timed(tenant_id, datetime(2026, 10, 30, 17, tzinfo=UTC))]
    )
    switch(browser, persona)

    response = browser.client.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "console-not-found"
    assert set(body) <= {"type", "title", "status", "detail", "instance", "requestId"}
    assert "items" not in body
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", [TURNS, METRICS])
def test_a_call_with_no_session_is_a_401(browser: Browser, path: str) -> None:
    assert browser.client.get(path).status_code == 401


# --- HR reads ---------------------------------------------------------------------------------


@pytest.mark.parametrize("path", [TURNS, METRICS])
def test_both_routes_send_no_store(browser: Browser, path: str) -> None:
    sandbox_as(browser)

    response = browser.client.get(path)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_a_new_sandbox_has_no_turns_and_zeroed_tiles(
    browser: Browser, database_settings: Settings
) -> None:
    sandbox_as(browser)

    assert get_ok(browser, TURNS) == {"items": [], "nextCursor": None}
    tiles = get_ok(browser, METRICS)
    assert tiles["turns"] == 0
    assert tiles["firstToken"]["p50Ms"] is None
    assert tiles["cost"]["perAnsweredQuestionUsd"] is None
    assert tiles["cost"]["sandboxSpendUsd"] == 0
    assert tiles["cost"]["sandboxCapUsd"] == float(database_settings.ai_sandbox_budget_usd)
    assert tiles["escalation"]["rate"] is None
    assert [card["count"] for card in tiles["cardsConfirmed"]] == [0, 0, 0]


async def test_the_list_item_holds_the_rows_labels_and_never_a_turn(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id = sandbox_as(browser)
    turn_id = uuid4()
    row = timed(
        tenant_id,
        datetime(2026, 10, 30, 17, 5, tzinfo=UTC),
        turn_id=turn_id,
        tools=[
            {"name": "search_handbook", "ok": True, "durationMs": 120},
            {"name": "check_time_off", "ok": False, "durationMs": 40},
        ],
        sections_retrieved=["4.3", "CA-4.3"],
        card_action="timeoff.request",
        served_by=["claude-opus-5-5"],
        effort="medium",
        prompt_version="p1",
        toolset_version="t1",
        input_tokens=1000,
        output_tokens=200,
        cache_read_tokens=5000,
        cache_write_tokens=300,
        cost_usd=Decimal("0.042100"),
        guard_ms=310,
        first_text_ms=1450,
        total_ms=4200,
    )
    await write_rows(app_engine, tenant_id, [row])

    response = browser.client.get(TURNS)

    (item,) = response.json()["items"]
    assert item == {
        "id": str(row["id"]),
        "occurredOn": "2026-10-30",
        "occurredAt": "2026-10-30T17:05:00Z",
        "flagged": False,
        "abandoned": False,
        "askerRole": "employee",
        "askerLocation": "Oakland, CA",
        "outcome": "answered",
        "refusalCategory": None,
        "guardCategory": "ordinary",
        "injectionSuspected": False,
        "tools": [
            {"name": "search_handbook", "ok": True, "durationMs": 120},
            {"name": "check_time_off", "ok": False, "durationMs": 40},
        ],
        "sectionsRetrieved": ["4.3", "CA-4.3"],
        "sectionsCited": ["CA-4.3"],
        "cardAction": "timeoff.request",
        "servedBy": ["claude-opus-5-5"],
        "fallback": False,
        "effort": "medium",
        "promptVersion": "p1",
        "toolsetVersion": "t1",
        "inputTokens": 1000,
        "outputTokens": 200,
        "cacheReadTokens": 5000,
        "cacheWriteTokens": 300,
        "costUsd": 0.0421,
        "guardMs": 310,
        "firstTextMs": 1450,
        "totalMs": 4200,
    }
    # The console's id is the row's own, never the turn's.
    assert item["id"] != str(turn_id)
    assert str(turn_id) not in response.text
    assert "turnId" not in response.text


async def test_a_list_item_says_whether_the_turn_was_abandoned(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id = sandbox_as(browser)
    first, second, third = (ordered_id(tenant_id, number) for number in (1, 2, 3))
    await write_rows(
        app_engine,
        tenant_id,
        [
            flagged(tenant_id, row_id=first, abandoned=True),
            flagged(tenant_id, row_id=second),
            timed(tenant_id, datetime(2026, 10, 30, 17, 0, tzinfo=UTC), row_id=third),
        ],
    )

    items = get_ok(browser, TURNS)["items"]

    assert {item["id"]: item["abandoned"] for item in items} == {
        str(first): True,
        str(second): False,
        str(third): False,
    }


async def test_a_flagged_item_holds_only_its_date_its_counts_and_the_models_labels(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id = sandbox_as(browser)
    await write_rows(
        app_engine,
        tenant_id,
        [
            flagged(
                tenant_id,
                served_by=["claude-opus-5-5"],
                fallback=True,
                effort="medium",
                input_tokens=900,
                cost_usd=Decimal("0.0123"),
                guard_ms=300,
                first_text_ms=800,
                total_ms=2000,
            )
        ],
    )

    (item,) = get_ok(browser, TURNS)["items"]

    nulls = [
        "occurredAt",
        "askerRole",
        "askerLocation",
        "outcome",
        "refusalCategory",
        "guardCategory",
        "injectionSuspected",
        "tools",
        "sectionsRetrieved",
        "sectionsCited",
        "cardAction",
        "promptVersion",
        "toolsetVersion",
    ]
    assert all(item[name] is None for name in nulls)
    assert item["flagged"] is True
    assert item["occurredOn"] == "2026-10-30"
    assert (item["servedBy"], item["fallback"], item["effort"]) == (
        ["claude-opus-5-5"],
        True,
        "medium",
    )
    assert (item["inputTokens"], item["costUsd"]) == (900, 0.0123)
    assert (item["guardMs"], item["firstTextMs"], item["totalMs"]) == (300, 800, 2000)


# --- The order, the pages, and the cursor -----------------------------------------------------


def ordered_id(tenant_id: UUID, number: int) -> UUID:
    """A row ID that sorts by `number` within one sandbox and is unique across sandboxes."""
    return UUID(int=(tenant_id.int & ~0xFFFF) | number)


def day_set(tenant_id: UUID) -> tuple[list[dict[str, Any]], list[UUID]]:
    """Rows over two days, and their IDs in the order the list must give them.

    Oct 30: timed rows at 17:30, two sharing 17:00 (told apart by ID, smaller first), and 09:00,
    then two flagged rows (smaller ID first). Oct 29: timed rows at 20:00 and 08:00, then a flagged
    row. Newest day first; within a day, timed rows newest first, then its flagged rows.
    """

    def at(hour: int, minute: int, day: int, **changes: Any) -> dict[str, Any]:
        return timed(
            tenant_id,
            datetime(2026, 10, day, hour, minute, tzinfo=UTC),
            day=date(2026, 10, day),
            **changes,
        )

    def flag(day: int, number: int) -> dict[str, Any]:
        return flagged(tenant_id, date(2026, 10, day), row_id=ordered_id(tenant_id, number))

    rows = [
        at(17, 30, 30, row_id=ordered_id(tenant_id, 20)),
        at(17, 0, 30, row_id=ordered_id(tenant_id, 2)),
        at(17, 0, 30, row_id=ordered_id(tenant_id, 1)),
        at(9, 0, 30, row_id=ordered_id(tenant_id, 21)),
        flag(30, 11),
        flag(30, 12),
        at(20, 0, 29, row_id=ordered_id(tenant_id, 4)),
        at(8, 0, 29, row_id=ordered_id(tenant_id, 3)),
        flag(29, 13),
    ]
    # Some timed rows have larger IDs than the flagged ones, so an ID-only comparison would show.
    order = [20, 1, 2, 21, 11, 12, 4, 3, 13]
    return rows, [ordered_id(tenant_id, number) for number in order]


async def test_the_list_is_newest_first_with_each_days_flagged_rows_last(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id = sandbox_as(browser)
    rows, order = day_set(tenant_id)
    await write_rows(app_engine, tenant_id, rows[::-1])

    page = get_ok(browser, TURNS)

    assert ids(page) == [str(row_id) for row_id in order]
    assert page["nextCursor"] is None


@pytest.mark.parametrize("page_size", range(1, 10))
async def test_walking_the_pages_gives_every_row_once_in_order(
    browser: Browser, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, page_size: int
) -> None:
    # Page sizes 1 to 9 put a page's edge at every row: before and after a flagged row, between
    # two flagged rows of one day, between two timed rows that share a time, and across the day.
    monkeypatch.setattr(queries, "PAGE_SIZE", page_size)
    tenant_id = sandbox_as(browser)
    rows, order = day_set(tenant_id)
    await write_rows(app_engine, tenant_id, rows)

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(20):
        page = get_ok(browser, TURNS, **({"cursor": cursor} if cursor else {}))
        seen += ids(page)
        cursor = page["nextCursor"]
        if cursor is None:
            break

    assert seen == [str(row_id) for row_id in order]


async def test_after_a_flagged_row_no_timed_row_of_its_day_comes_back(
    browser: Browser, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(queries, "PAGE_SIZE", 5)
    tenant_id = sandbox_as(browser)
    rows, order = day_set(tenant_id)
    await write_rows(app_engine, tenant_id, rows)

    first = get_ok(browser, TURNS)
    # The first page ends on the day's first flagged row, with its four timed rows before it.
    assert ids(first)[-1] == str(ordered_id(tenant_id, 11))
    second = get_ok(browser, TURNS, cursor=first["nextCursor"])

    # The day's other flagged row is next; none of Oct 30's four timed rows reappears.
    assert ids(second)[0] == str(ordered_id(tenant_id, 12))
    assert not set(ids(second)) & {str(row_id) for row_id in order[:4]}


async def test_a_full_page_is_fifty_and_the_next_holds_the_rest(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id = sandbox_as(browser)
    base = datetime(2026, 10, 30, 8, 0, tzinfo=UTC)
    await write_rows(
        app_engine,
        tenant_id,
        [timed(tenant_id, base + timedelta(minutes=minute)) for minute in range(52)],
    )

    first = get_ok(browser, TURNS)
    second = get_ok(browser, TURNS, cursor=first["nextCursor"])

    assert (len(first["items"]), len(second["items"])) == (50, 2)
    assert second["nextCursor"] is None
    assert not set(ids(first)) & set(ids(second))


async def test_exactly_fifty_rows_have_no_next_page(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id = sandbox_as(browser)
    base = datetime(2026, 10, 30, 8, 0, tzinfo=UTC)
    await write_rows(
        app_engine,
        tenant_id,
        [timed(tenant_id, base + timedelta(minutes=minute)) for minute in range(50)],
    )

    page = get_ok(browser, TURNS)

    assert len(page["items"]) == 50
    assert page["nextCursor"] is None


@pytest.mark.parametrize(
    "cursor",
    [
        "not base64 at all!",
        base64.urlsafe_b64encode(b"not json").decode(),
        cursor_of(),
        cursor_of("2026-10-30", None),
        cursor_of("2026-10-30", None, str(uuid4()), "extra"),
        cursor_of("tomorrow", None, str(uuid4())),
        cursor_of("2026-10-30", "2026-10-30T17:00:00", str(uuid4())),  # no time zone
        cursor_of("2026-10-30", 5, str(uuid4())),
        cursor_of("2026-10-30", None, 7),
        cursor_of("2026-10-30", None, True),
        cursor_of("2026-10-30", None, "not-a-uuid"),
        cursor_of(20261030, None, str(uuid4())),
        base64.urlsafe_b64encode(json.dumps({"a": 1}).encode()).decode(),
        "x" * 600,
        # Valid ISO times that overflow when converted to UTC, or lie outside any real range.
        cursor_of("2026-10-30", "0001-01-01T00:00:00+14:00", str(uuid4())),
        cursor_of("2026-10-30", "9999-12-31T23:59:59-14:00", str(uuid4())),
        cursor_of("0001-01-01", None, str(uuid4())),
        cursor_of("9999-12-31", None, str(uuid4())),
        cursor_of("1999-12-31", "2026-10-30T17:00:00+00:00", str(uuid4())),
    ],
)
def test_a_malformed_cursor_is_a_422_problem(browser: Browser, cursor: str) -> None:
    sandbox_as(browser)

    response = browser.client.get(TURNS, params={"cursor": cursor})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert cursor not in response.text


@pytest.mark.parametrize(
    "cursor",
    [
        cursor_of(
            "2026-10-30", "0001-01-01T00:00:00+14:00", "00000000-0000-0000-0000-00000000cafe"
        ),
        cursor_of(
            "2026-10-30", "9999-12-31T23:59:59-14:00", "00000000-0000-0000-0000-00000000cafe"
        ),
    ],
)
def test_an_out_of_range_cursor_is_a_422_and_is_never_logged(
    browser: Browser, caplog: pytest.LogCaptureFixture, cursor: str
) -> None:
    sandbox_as(browser)
    caplog.set_level(logging.DEBUG)

    response = browser.client.get(TURNS, params={"cursor": cursor})

    assert response.status_code == 422
    assert response.json()["type"] == "console-invalid-cursor"
    log_text = "\n".join(str(record.__dict__) + record.getMessage() for record in caplog.records)
    for marker in ("0001-01-01", "9999-12-31", "cafe"):
        assert marker not in log_text


def test_a_bad_cursor_names_its_problem(browser: Browser) -> None:
    sandbox_as(browser)

    response = browser.client.get(TURNS, params={"cursor": "nonsense"})

    assert response.json()["type"] == "console-invalid-cursor"


async def test_the_route_applies_the_hr_flag_so_the_database_decides(
    browser: Browser, app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_id = sandbox_as(browser)
    await write_rows(
        app_engine, tenant_id, [timed(tenant_id, datetime(2026, 10, 30, 17, tzinfo=UTC))]
    )
    assert len(get_ok(browser, TURNS)["items"]) == 1

    async def no_flag(session: Any, value: bool) -> None:
        return None

    # HR's session without the flag reads no console rows: row-level security is what limits them.
    monkeypatch.setattr("app.modules.identity.deps.set_is_hr", no_flag)

    assert get_ok(browser, TURNS)["items"] == []
    assert get_ok(browser, METRICS)["turns"] == 0


# --- Another sandbox ---------------------------------------------------------------------------


async def test_another_sandboxs_rows_and_counts_never_appear(
    open_browser: Any, app_engine: AsyncEngine
) -> None:
    mine, theirs = open_browser(), open_browser()
    mine_id, theirs_id = sandbox_as(mine), sandbox_as(theirs)
    at = datetime(2026, 10, 30, 17, tzinfo=UTC)
    await write_rows(
        app_engine,
        mine_id,
        [timed(mine_id, at, cost_usd=Decimal("0.01"), first_text_ms=500, sections_retrieved=[])],
    )
    await write_rows(
        app_engine,
        theirs_id,
        [
            timed(
                theirs_id,
                at + timedelta(minutes=i),
                outcome="not_found",
                sections_retrieved=["9.9"],
                injection_suspected=True,
                fallback=True,
                first_text_ms=9000,
                guard_ms=9000,
                cost_usd=Decimal("0.5"),
            )
            for i in range(3)
        ]
        + [flagged(theirs_id)],
    )
    await add_spend(app_engine, theirs_id, "0.30", purpose="case_screen")
    await add_confirmed(app_engine, theirs_id, ["timeoff.cancel", "timeoff.cancel"])

    page, tiles = get_ok(mine, TURNS), get_ok(mine, METRICS)

    assert len(page["items"]) == 1
    assert tiles["turns"] == 1
    assert tiles["firstToken"]["p95Ms"] == 500
    assert tiles["cost"]["sandboxSpendUsd"] == 0
    assert tiles["escalation"]["flaggedCount"] == 0
    assert tiles["refusals"]["fallbackCount"] == 0
    assert tiles["notFound"] == {"count": 0, "turns": 1, "sections": [], "smallSample": True}
    assert tiles["injections"]["count"] == 0
    assert [card["count"] for card in tiles["cardsConfirmed"]] == [0, 0, 0]


# --- The tiles ----------------------------------------------------------------------------------


async def test_the_tiles_of_the_hand_worked_rows(
    browser: Browser, app_engine: AsyncEngine, database_settings: Settings
) -> None:
    # The same thirteen rows as tests/test_console_metrics.py, where each figure is worked by hand.
    tenant_id = sandbox_as(browser)
    await write_rows(
        app_engine, tenant_id, [facts_row(tenant_id, i, row) for i, row in enumerate(HAND_WORKED)]
    )
    await add_spend(app_engine, tenant_id, "0.40", purpose="case_screen")
    await add_confirmed(
        app_engine, tenant_id, ["timeoff.request", "timeoff.request", "timeoff.decide"]
    )

    tiles = get_ok(browser, METRICS)

    assert tiles["turns"] == 13
    assert tiles["smallSample"] is True
    # Time to first token: 9 values, p50 = 5th = 1600, p95 = 9th = 2600 (see the pure test).
    assert tiles["firstToken"] == {
        "p50Ms": 1600,
        "p95Ms": 2600,
        "targetMs": 3000,
        "sampleSize": 9,
        "smallSample": True,
    }
    # Safety check time: 11 values, p95 = 11th = 800.
    assert tiles["safetyCheck"] == {
        "p95Ms": 800,
        "targetMs": 800,
        "sampleSize": 11,
        "smallSample": True,
    }
    # Cost: six answered rows total 0.210, mean 0.035. Spend 0.40 of the cap.
    assert tiles["cost"]["answeredCount"] == 6
    assert tiles["cost"]["perAnsweredQuestionUsd"] == pytest.approx(0.035)
    assert tiles["cost"]["sandboxSpendUsd"] == pytest.approx(float(SPEND))
    assert (
        tiles["cost"]["sandboxCapUsd"]
        == float(CAP)
        == float(database_settings.ai_sandbox_budget_usd)
    )
    # Escalation: 2 flagged and not abandoned (row 13 is abandoned) of 13 = 2/13.
    assert (tiles["escalation"]["flaggedCount"], tiles["escalation"]["turns"]) == (2, 13)
    assert tiles["escalation"]["rate"] == pytest.approx(2 / 13)
    # Refusals and fallbacks: 1 refused, 2 fallbacks, 2 rows either (row 9 is both): 2/13.
    refusals = tiles["refusals"]
    assert (refusals["refusedCount"], refusals["fallbackCount"], refusals["affectedCount"]) == (
        1,
        2,
        2,
    )
    assert refusals["rate"] == pytest.approx(2 / 13)
    # Not found: rows 7 and 8; 4.3 twice, then 4.1 and CA-1.2 once each.
    assert tiles["notFound"]["count"] == 2
    assert tiles["notFound"]["sections"] == [
        {"sectionId": "4.3", "count": 2},
        {"sectionId": "4.1", "count": 1},
        {"sectionId": "CA-1.2", "count": 1},
    ]
    assert tiles["injections"]["count"] == 1
    assert tiles["cardsConfirmed"] == [
        {"action": "timeoff.request", "count": 2},
        {"action": "timeoff.decide", "count": 1},
        {"action": "timeoff.cancel", "count": 0},
    ]


async def test_the_spend_comes_from_the_ledger_not_from_the_console_rows(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    tenant_id = sandbox_as(browser)
    # No console row at all: a case screening and a case summary were charged.
    await add_spend(app_engine, tenant_id, "0.050", purpose="case_screen")
    await add_spend(app_engine, tenant_id, "0.200", purpose="case_summary")
    await add_spend(app_engine, tenant_id, "-0.020", purpose="case_summary", kind="settle")

    tiles = get_ok(browser, METRICS)

    assert tiles["turns"] == 0
    assert tiles["cost"]["sandboxSpendUsd"] == pytest.approx(0.23)


@pytest.mark.parametrize(("count", "small"), [(19, True), (20, False)])
async def test_nineteen_rows_are_a_small_sample_and_twenty_are_not(
    browser: Browser, app_engine: AsyncEngine, count: int, small: bool
) -> None:
    tenant_id = sandbox_as(browser)
    base = datetime(2026, 10, 30, 8, 0, tzinfo=UTC)
    await write_rows(
        app_engine,
        tenant_id,
        [
            timed(tenant_id, base + timedelta(minutes=i), first_text_ms=1000, guard_ms=100)
            for i in range(count)
        ],
    )

    tiles = get_ok(browser, METRICS)

    assert tiles["turns"] == count
    for tile in (
        "firstToken",
        "safetyCheck",
        "cost",
        "escalation",
        "refusals",
        "notFound",
        "injections",
    ):
        assert tiles[tile]["smallSample"] is small, tile
    assert tiles["smallSample"] is small


async def test_cards_confirmed_counts_this_sandboxs_events_by_action(
    open_browser: Any, app_engine: AsyncEngine
) -> None:
    mine, theirs = open_browser(), open_browser()
    mine_id, theirs_id = sandbox_as(mine), sandbox_as(theirs)
    await add_confirmed(
        app_engine, mine_id, ["timeoff.request", "timeoff.request", "timeoff.decide"]
    )
    # Events that are not a confirmed card, and another sandbox's.
    await add_confirmed(app_engine, mine_id, ["timeoff.cancel"], event="proposal.failed")
    await add_confirmed(app_engine, mine_id, ["timeoff.cancel"], event="proposal.created")
    await add_confirmed(app_engine, theirs_id, ["timeoff.cancel"] * 4)

    cards = get_ok(mine, METRICS)["cardsConfirmed"]

    assert [(card["action"], card["count"]) for card in cards] == [
        ("timeoff.request", 2),
        ("timeoff.decide", 1),
        ("timeoff.cancel", 0),
    ]
    assert set(get_ok(mine, METRICS)["cardsConfirmed"][0]) == {"action", "count"}


# --- No text and no person -----------------------------------------------------------------------


async def test_no_response_holds_a_name_a_planted_text_or_a_person_or_conversation_id(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    sandbox = browser.start_sandbox("priya")
    tenant_id = UUID(sandbox["tenant"]["id"])
    priya_id = UUID(sandbox["me"]["id"])
    # Priya sends HR a case in her own words, and one of her turns left an audit trail.
    sent = browser.client.post(
        "/api/v1/cases",
        json={"submissionId": str(uuid4()), "category": "pay", "text": PLANTED},
        headers=browser.csrf,
    )
    assert sent.status_code == 201, sent.text
    await add_confirmed(app_engine, tenant_id, ["timeoff.request"])
    async with tenant_session(app_engine, TenantContext(tenant_id, priya_id)) as db:
        await set_is_hr(db, True)
        people = (await db.execute(select(Person.id, Person.given_name, Person.family_name))).all()
    rows = [
        timed(tenant_id, datetime(2026, 10, 30, 17, tzinfo=UTC), cost_usd=Decimal("0.01")),
        flagged(tenant_id),
    ]
    await write_rows(app_engine, tenant_id, rows)
    switch(browser, "dana")

    list_text = browser.client.get(TURNS).text
    metrics_text = browser.client.get(METRICS).text

    row_ids = {str(row["id"]) for row in rows}
    for text in (list_text, metrics_text):
        assert PLANTED not in text
        assert "Zebra" not in text
        for person in people:
            assert str(person.id) not in text
            assert person.family_name not in text
            assert f"{person.given_name} {person.family_name}" not in text
    assert set(UUID_PATTERN.findall(list_text)) == row_ids
    assert UUID_PATTERN.findall(metrics_text) == []
    assert str(uuid5(tenant_id, "person:priya")) not in list_text + metrics_text


async def test_problems_and_log_lines_hold_no_name_or_text(
    browser: Browser, caplog: pytest.LogCaptureFixture
) -> None:
    sandbox = browser.start_sandbox("priya")
    priya_id = sandbox["me"]["id"]
    caplog.set_level(logging.DEBUG)

    refused = [browser.client.get(path) for path in (TURNS, METRICS)]
    switch(browser, "dana")
    invalid = browser.client.get(TURNS, params={"cursor": PLANTED})

    assert [response.status_code for response in refused] == [404, 404]
    assert invalid.status_code == 422
    log_text = "\n".join(str(record.__dict__) + record.getMessage() for record in caplog.records)
    for text in [response.text for response in (*refused, invalid)] + [log_text]:
        assert PLANTED not in text
        assert priya_id not in text
        assert "Raman" not in text
        assert "Whitfield" not in text
