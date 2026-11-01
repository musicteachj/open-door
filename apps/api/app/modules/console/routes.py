"""The AI Ops console's two reads, for HR only.

Both need `console.read`; anyone else gets the same 404 as any page they may not open. The
signed-in dependency has already opened the request's transaction and set the HR flag, which the
console table's row-level rule needs. Both send `Cache-Control: no-store`.

Nothing here reads a person, a conversation, or any text. A problem's text is fixed, and no log
line is written for a refusal.
"""

from typing import Annotated, Any, Final

from fastapi import APIRouter, Query, Request, Response, status

from app.ai.budget import Caps, sandbox_spent_usd
from app.api.deps import get_app_settings
from app.api.problems import problem_responses
from app.core.cache_control import CACHE_CONTROL_HEADER, NO_STORE
from app.core.problems import ProblemError
from app.modules.console import queries
from app.modules.console.metrics import compute_metrics
from app.modules.console.schemas import (
    ActionCountOut,
    ConsoleMetricsOut,
    ConsoleTurnOut,
    ConsoleTurnsPageOut,
    CostTileOut,
    EscalationTileOut,
    FirstTokenTileOut,
    InjectionTileOut,
    NotFoundTileOut,
    RefusalsTileOut,
    SafetyCheckTileOut,
    ToolOut,
)
from app.modules.identity.deps import SignedInDep
from app.policy import Action, Actor, PersonResource, can

router = APIRouter(prefix="/console", tags=["console"])

NOT_FOUND_CODE: Final = "console-not-found"
NOT_FOUND_TEXT: Final = "There is no such page."
INVALID_CURSOR_CODE: Final = "console-invalid-cursor"
INVALID_CURSOR_TEXT: Final = "That page of the list isn't available."

LIST_ERRORS = problem_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_422_UNPROCESSABLE_CONTENT,
)
METRICS_ERRORS = problem_responses(status.HTTP_401_UNAUTHORIZED, status.HTTP_404_NOT_FOUND)


def _require_console(actor: Actor) -> None:
    """`console.read` takes the actor as a person, like the case queue. A refusal is a 404."""
    if not can(actor, Action.CONSOLE_READ, PersonResource(actor.person_id)):
        raise ProblemError(404, NOT_FOUND_CODE, NOT_FOUND_TEXT)


def _turn_out(row: Any) -> ConsoleTurnOut:
    return ConsoleTurnOut(
        id=row.id,
        occurred_on=row.occurred_on,
        occurred_at=row.occurred_at,
        flagged=row.flagged,
        abandoned=row.abandoned,
        asker_role=row.asker_role,
        asker_location=row.asker_location,
        outcome=row.outcome,
        refusal_category=row.refusal_category,
        guard_category=row.guard_category,
        injection_suspected=row.injection_suspected,
        tools=None
        if row.tools is None
        else [
            ToolOut(name=tool["name"], ok=tool["ok"], duration_ms=tool["durationMs"])
            for tool in row.tools
        ],
        sections_retrieved=row.sections_retrieved,
        sections_cited=row.sections_cited,
        card_action=row.card_action,
        served_by=row.served_by,
        fallback=row.fallback,
        effort=row.effort,
        prompt_version=row.prompt_version,
        toolset_version=row.toolset_version,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cache_read_tokens=row.cache_read_tokens,
        cache_write_tokens=row.cache_write_tokens,
        cost_usd=float(row.cost_usd),
        guard_ms=row.guard_ms,
        first_text_ms=row.first_text_ms,
        total_ms=row.total_ms,
    )


@router.get(
    "/turns",
    operation_id="listConsoleTurns",
    summary="HR's turn list: labels, counts, and timings, newest first, no words",
    response_model=ConsoleTurnsPageOut,
    responses=LIST_ERRORS,
)
async def list_console_turns(
    signed_in: SignedInDep,
    response: Response,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> ConsoleTurnsPageOut:
    _require_console(signed_in.actor)
    try:
        start = None if cursor is None else queries.decode_cursor(cursor)
    except ValueError:
        raise ProblemError(422, INVALID_CURSOR_CODE, INVALID_CURSOR_TEXT) from None
    rows = await queries.turn_rows(signed_in.db, start, queries.PAGE_SIZE)
    page = rows[: queries.PAGE_SIZE]
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE
    return ConsoleTurnsPageOut(
        items=[_turn_out(row) for row in page],
        next_cursor=queries.encode_cursor(page[-1]) if len(rows) > queries.PAGE_SIZE else None,
    )


@router.get(
    "/metrics",
    operation_id="getConsoleMetrics",
    summary="HR's tiles over the sandbox's life: counts, percentiles, and sums, no words",
    response_model=ConsoleMetricsOut,
    responses=METRICS_ERRORS,
)
async def get_console_metrics(
    signed_in: SignedInDep, response: Response, request: Request
) -> ConsoleMetricsOut:
    _require_console(signed_in.actor)
    db = signed_in.db
    caps = Caps.from_settings(get_app_settings(request))
    # The sandbox's spend is the ledger's one sum (the daily ledger is not read): the safety check,
    # case screening, and case summaries all count, and no ledger row is returned.
    spent = await sandbox_spent_usd(db)
    metrics = compute_metrics(
        await queries.turn_facts(db),
        spend_usd=spent,
        cap_usd=caps.sandbox_usd,
        confirmed=await queries.confirmed_cards(db),
    )
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE
    return ConsoleMetricsOut(
        turns=metrics.turns,
        small_sample=metrics.small_sample,
        first_token=FirstTokenTileOut.model_validate(metrics.first_token, from_attributes=True),
        safety_check=SafetyCheckTileOut.model_validate(metrics.safety_check, from_attributes=True),
        cost=CostTileOut.model_validate(metrics.cost, from_attributes=True),
        escalation=EscalationTileOut.model_validate(metrics.escalation, from_attributes=True),
        refusals=RefusalsTileOut.model_validate(metrics.refusals, from_attributes=True),
        not_found=NotFoundTileOut.model_validate(metrics.not_found, from_attributes=True),
        cards_confirmed=[
            ActionCountOut.model_validate(item, from_attributes=True)
            for item in metrics.cards_confirmed
        ],
        injections=InjectionTileOut.model_validate(metrics.injections, from_attributes=True),
    )
