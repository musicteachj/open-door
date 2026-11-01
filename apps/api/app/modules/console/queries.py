"""The console's reads: `ai_console_turns`, the spend ledger as one sum, and audit counts.

Row-level security already limits every read to the sandbox, and to HR; these queries add no filter
for either. They never select `turn_id` (the API's own lookup key, not the console's to send), and
they read `ai_spend` only through `budget_state`'s sum, never per turn, and never return an audit
row (ADR 0016's amendment).
"""

import base64
import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AiConsoleTurn, AuditEvent
from app.modules.console.metrics import TurnFacts

PAGE_SIZE = 50

# A cursor's day or time outside these years is not one of ours (and the extremes overflow once
# converted to UTC for the database).
CURSOR_FIRST_YEAR = 2000
CURSOR_LAST_YEAR = 9998

# Every column the list sends. `turn_id` is not one.
LIST_COLUMNS = (
    AiConsoleTurn.id,
    AiConsoleTurn.occurred_on,
    AiConsoleTurn.occurred_at,
    AiConsoleTurn.flagged,
    AiConsoleTurn.abandoned,
    AiConsoleTurn.asker_role,
    AiConsoleTurn.asker_location,
    AiConsoleTurn.outcome,
    AiConsoleTurn.refusal_category,
    AiConsoleTurn.guard_category,
    AiConsoleTurn.injection_suspected,
    AiConsoleTurn.tools,
    AiConsoleTurn.sections_retrieved,
    AiConsoleTurn.sections_cited,
    AiConsoleTurn.card_action,
    AiConsoleTurn.served_by,
    AiConsoleTurn.fallback,
    AiConsoleTurn.effort,
    AiConsoleTurn.prompt_version,
    AiConsoleTurn.toolset_version,
    AiConsoleTurn.input_tokens,
    AiConsoleTurn.output_tokens,
    AiConsoleTurn.cache_read_tokens,
    AiConsoleTurn.cache_write_tokens,
    AiConsoleTurn.cost_usd,
    AiConsoleTurn.guard_ms,
    AiConsoleTurn.first_text_ms,
    AiConsoleTurn.total_ms,
)

type Cursor = tuple[date, datetime | None, UUID]


def encode_cursor(row: Any) -> str:
    """The cursor for a page's last row: its day, its time (null for a flagged row), and its ID."""
    key = [
        row.occurred_on.isoformat(),
        row.occurred_at.isoformat() if row.occurred_at is not None else None,
        str(row.id),
    ]
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def decode_cursor(cursor: str) -> Cursor:
    """The sort key a cursor names. Raises ValueError for anything that is not one of ours."""
    try:
        key = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if not isinstance(key, list) or len(key) != 3:
            raise ValueError
        day, moment, row_id = key
        if not isinstance(day, str) or not isinstance(row_id, str):
            raise ValueError
        if moment is not None and not isinstance(moment, str):
            raise ValueError
        parsed_moment = None if moment is None else datetime.fromisoformat(moment)
        if parsed_moment is not None:
            if parsed_moment.tzinfo is None:
                raise ValueError
            parsed_moment = parsed_moment.astimezone(UTC)
            if not CURSOR_FIRST_YEAR <= parsed_moment.year <= CURSOR_LAST_YEAR:
                raise ValueError
        parsed_day = date.fromisoformat(day)
        if not CURSOR_FIRST_YEAR <= parsed_day.year <= CURSOR_LAST_YEAR:
            raise ValueError
        return parsed_day, parsed_moment, UUID(row_id)
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError("not a cursor") from None


def _after(cursor: Cursor) -> Any:
    """Rows that come after the cursor's row in the list's order: newest day first, then a day's
    timed rows newest first, then its flagged rows (no time), each group by ID ascending.

    A tuple comparison is wrong here, because a flagged row's time is null, which compares as
    neither earlier nor later. So the two cases are written out.
    """
    day, moment, row_id = cursor
    earlier_day = AiConsoleTurn.occurred_on < day
    same_day = AiConsoleTurn.occurred_on == day
    if moment is None:
        # The cursor row is flagged: only flagged rows of the day with a larger ID are left.
        return or_(
            earlier_day,
            and_(same_day, AiConsoleTurn.occurred_at.is_(None), AiConsoleTurn.id > row_id),
        )
    return or_(
        earlier_day,
        and_(
            same_day,
            or_(
                # Every flagged row of the day comes after its timed rows.
                AiConsoleTurn.occurred_at.is_(None),
                AiConsoleTurn.occurred_at < moment,
                and_(AiConsoleTurn.occurred_at == moment, AiConsoleTurn.id > row_id),
            ),
        ),
    )


def turns_query(cursor: Cursor | None, limit: int) -> Select[Any]:
    query = (
        select(*LIST_COLUMNS)
        .order_by(
            AiConsoleTurn.occurred_on.desc(),
            AiConsoleTurn.occurred_at.desc().nulls_last(),
            AiConsoleTurn.id.asc(),
        )
        .limit(limit + 1)
    )
    return query if cursor is None else query.where(_after(cursor))


async def turn_rows(db: AsyncSession, cursor: Cursor | None, limit: int) -> list[Any]:
    """One page plus one row (the extra says there is a next page)."""
    return list((await db.execute(turns_query(cursor, limit))).all())


async def turn_facts(db: AsyncSession) -> list[TurnFacts]:
    """What the tiles read from every console row of the sandbox.

    A sandbox's rows are bounded (it lives 24 hours and its spend is capped), so loading these
    narrow columns for the tiles is fine.
    """
    query = select(
        AiConsoleTurn.flagged,
        AiConsoleTurn.abandoned,
        AiConsoleTurn.outcome,
        AiConsoleTurn.fallback,
        AiConsoleTurn.injection_suspected,
        AiConsoleTurn.first_text_ms,
        AiConsoleTurn.guard_ms,
        AiConsoleTurn.cost_usd,
        AiConsoleTurn.sections_retrieved,
    )
    return [
        TurnFacts(
            flagged=row.flagged,
            abandoned=row.abandoned,
            outcome=row.outcome,
            fallback=row.fallback,
            injection_suspected=row.injection_suspected,
            first_text_ms=row.first_text_ms,
            guard_ms=row.guard_ms,
            cost_usd=row.cost_usd,
            sections_retrieved=row.sections_retrieved,
        )
        for row in (await db.execute(query)).all()
    ]


async def confirmed_cards(db: AsyncSession) -> dict[str, int]:
    """Counts of `proposal.confirmed` audit events by the proposal's action (`after->>'action'`).
    Counts only: no audit row leaves this function, and `ai_proposals` isn't read (HR can't)."""
    action = AuditEvent.after["action"].astext
    query = (
        select(action, func.count())
        .where(AuditEvent.action == "proposal.confirmed")
        .group_by(action)
    )
    return {name: count for name, count in (await db.execute(query)).all() if name is not None}
