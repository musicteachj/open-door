"""The six time-off tools: three that read, one that checks, and three that propose.

None takes an actor from the model (invariant 1). Each runs in its own short transaction as the
signed-in person, so row-level security applies, and the policy layer is asked for every person
and request a result names. `person_name` is the one input that names someone, and it is matched
only among the people the asker may read for time off.

The model never writes (invariant 3): a proposal tool builds the card with the same builders the
page's confirm uses, stores it with `create_proposal` (its own transaction: the proposal and its
audit event, nothing else), and hands the card to the turn on the outcome. The model gets the
engine's labels and a sentence that a person must confirm, never the card itself. Results are
described in `timeoff_results.py`.
"""

import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.conversations import TurnFinished
from app.ai.proposal_cards import (
    CancelCard,
    CancelPayload,
    DecideCard,
    DecidePayload,
    RequestCard,
    RequestPayload,
    cancel_card,
    decide_card,
    request_card_for,
)
from app.ai.proposals import ProposalOut, create_proposal
from app.ai.text import error_name
from app.ai.tools.base import (
    Tool,
    ToolContext,
    ToolInput,
    ToolOutcome,
    describe_problem,
    failure,
    json_block,
    shortened,
    validation_problems,
)
from app.ai.tools.timeoff_results import (
    balance_result,
    cancel_card_result,
    check_result,
    decide_card_result,
    problem_sentences,
    request_card_result,
    request_row,
    with_replacement,
)
from app.db.models import Person
from app.db.tenancy import tenant_session
from app.domain.timeoff.evaluate import NewRequest
from app.domain.timeoff.today import today_at
from app.modules.handbook.search import clean_query
from app.modules.timeoff import queries, service
from app.modules.timeoff.service import Preview, Refused
from app.modules.timeoff.texts import refusal_text
from app.modules.timeoff.window import DEFAULT_DAYS_AHEAD, DEFAULT_DAYS_BACK
from app.policy import Action, PersonResource, can

logger = logging.getLogger(__name__)

BALANCE_NAME = "get_time_off_balance"
LIST_NAME = "list_time_off_requests"
CHECK_NAME = "check_time_off"
REQUEST_NAME = "propose_time_off_request"
DECISION_NAME = "propose_time_off_decision"
CANCEL_NAME = "propose_cancel_time_off"

MAX_REQUESTS = 20
MAX_NAME_CHARACTERS = 100
# The most names an ambiguous match lists. They are directory information.
MAX_LISTED_NAMES = 10
MAX_SICK_HOURS = 8
HALF_DAY_MINUTES = 240

TURN_ENDED = "This answer has ended, so no card was made."
NO_MATCH = "No one you can see time off for matches that name."
UNREADABLE = "The time-off data couldn't be read. Try again, or say you couldn't look it up."

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


# ---------------------------------------------------------------------------------------------
# Definitions


def _date_property(what: str) -> dict[str, Any]:
    return {
        "type": "string",
        "format": "date",
        "description": f"{what}, written YYYY-MM-DD.",
    }


def _check_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["pto", "sick"]},
            "start_date": _date_property("The first day"),
            "end_date": _date_property("The last day, the same as the first for one day"),
            "half_day": {
                "type": "boolean",
                "description": "True for half a day, on a single day. Otherwise false.",
            },
            "hours": {
                "type": ["integer", "null"],
                "description": (
                    f"Whole hours, 1 to {MAX_SICK_HOURS}, for part of one day of sick time. "
                    "Null for PTO, for whole days, and for a half day."
                ),
            },
        },
        "required": ["type", "start_date", "end_date", "half_day", "hours"],
        "additionalProperties": False,
    }


_PERSON_NAME: dict[str, Any] = {
    "type": "string",
    "description": (
        "Optional. A person's name, given and family or just one of them, among the people the "
        f"asker may read, up to {MAX_NAME_CHARACTERS} characters. Leave it out for the asker."
    ),
}

BALANCE_DEFINITION: dict[str, Any] = {
    "name": BALANCE_NAME,
    "description": (
        "Get PTO and sick time balances: earned, taken, booked, pending, available, the ceiling, "
        "and the next earning date for PTO, and each calendar year of sick time, every figure as "
        "the label to quote, with the handbook sections they rest on. With no input it is the "
        "signed-in person's own. 'person_name' (optional) names someone the asker may read: a "
        "manager's reports, or anyone for HR. Never work out a balance yourself."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"person_name": _PERSON_NAME},
        "required": [],
        "additionalProperties": False,
    },
}

LIST_DEFINITION: dict[str, Any] = {
    "name": LIST_NAME,
    "description": (
        f"List time-off requests, up to {MAX_REQUESTS}: each one's ID, the person's name, type, "
        "dates, amount, status, and who decided it, never a note. 'scope' is 'mine' (the asker's "
        "own), 'team' (everyone below the asker), or 'waiting_for_me' (PTO waiting for the "
        "asker's decision). 'person_name' (optional) narrows the list to one person the asker may "
        "read, and then 'mine' and 'team' both mean that person. 'from' and 'to' (optional, "
        f"YYYY-MM-DD) set the window of dates: the default is {DEFAULT_DAYS_BACK} days back to "
        f"{DEFAULT_DAYS_AHEAD} days ahead, and 'waiting_for_me' ignores it. The result says "
        f'"truncated": true when more matched than the {MAX_REQUESTS} returned.'
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "scope": {"type": "string", "enum": ["mine", "team", "waiting_for_me"]},
            "person_name": _PERSON_NAME,
            "from": _date_property("Optional. The first day of the window"),
            "to": _date_property("Optional. The last day of the window"),
        },
        "required": ["scope"],
        "additionalProperties": False,
    },
}

CHECK_DEFINITION: dict[str, Any] = {
    "name": CHECK_NAME,
    "description": (
        "Check what a time-off request would use, for the signed-in person. It writes nothing. "
        "Returns whether the request can be made and why not, the days counted and skipped, the "
        "amount, the balance before and after (one entry per calendar year for sick time that "
        "crosses New Year), warnings, and the handbook sections. 'type' is 'pto' or 'sick'. "
        "Turn words like 'next Friday' into dates from today's date in the context, and ask when "
        "a date could mean two days. 'half_day' is true for half a day on a single day. 'hours' "
        f"is 1 to {MAX_SICK_HOURS} whole hours of one day of sick time, otherwise null; give "
        "'half_day' or 'hours', not both. Never count days or hours yourself."
    ),
    "input_schema": _check_schema(),
}

REQUEST_DEFINITION: dict[str, Any] = {
    "name": REQUEST_NAME,
    "description": (
        "Propose a time-off request for the signed-in person, with the same input as "
        "check_time_off. If it can be made, a confirm card is shown to the person, and nothing is "
        "booked until they confirm, so never say it is booked. If it can't, you get the reason as "
        "an error. Use it only when the person asks to book PTO or record sick time."
    ),
    "input_schema": _check_schema(),
}

DECISION_DEFINITION: dict[str, Any] = {
    "name": DECISION_NAME,
    "description": (
        "Propose approving or denying one PTO request that waits for the signed-in manager. "
        "'request_id' is a request's ID from list_time_off_requests. A confirm card is shown to "
        "the manager, and nothing is decided until they confirm. Use it only when a manager asks "
        "to approve or deny a specific request. Never recommend a decision."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "request_id": {
                "type": "string",
                "description": "The request's ID, from list_time_off_requests.",
            },
            "decision": {"type": "string", "enum": ["approve", "deny"]},
        },
        "required": ["request_id", "decision"],
        "additionalProperties": False,
    },
}

CANCEL_DEFINITION: dict[str, Any] = {
    "name": CANCEL_NAME,
    "description": (
        "Propose canceling one of the signed-in person's own requests. 'request_id' is its ID "
        "from list_time_off_requests. A confirm card is shown to the person, and nothing is "
        "canceled until they confirm. Use it only when they ask to cancel a request."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "request_id": {
                "type": "string",
                "description": "The request's ID, from list_time_off_requests.",
            },
        },
        "required": ["request_id"],
        "additionalProperties": False,
    },
}


# ---------------------------------------------------------------------------------------------
# Inputs


def _iso_date(value: object) -> date:
    """A calendar date written YYYY-MM-DD. `date.fromisoformat` alone also takes forms like
    "20261023", which the schema's `format: date` doesn't."""
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        msg = "must be a date written YYYY-MM-DD"
        raise ValueError(msg)
    try:
        return date.fromisoformat(value)
    except ValueError:
        msg = "must be a real date written YYYY-MM-DD"
        raise ValueError(msg) from None


def _request_id(value: object) -> str:
    if not isinstance(value, str):
        msg = "must be a request ID from list_time_off_requests"
        raise ValueError(msg)
    try:
        return str(UUID(value))
    except ValueError:
        msg = "must be a request ID from list_time_off_requests"
        raise ValueError(msg) from None


def _person_name(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        msg = "must be text"
        raise ValueError(msg)
    try:
        # The handbook search's cleaning: control, format, and surrogate characters go.
        cleaned = clean_query(value, max_characters=None)
    except ValueError:
        msg = "is empty. Leave 'person_name' out for the person asking"
        raise ValueError(msg) from None
    if len(cleaned) > MAX_NAME_CHARACTERS:
        msg = f"use at most {MAX_NAME_CHARACTERS} characters"
        raise ValueError(msg)
    return cleaned


type IsoDate = Annotated[date, BeforeValidator(_iso_date)]
type PersonName = Annotated[str | None, BeforeValidator(_person_name)]
type RequestId = Annotated[str, BeforeValidator(_request_id)]


class BalanceInput(ToolInput):
    person_name: PersonName = None


class ListInput(ToolInput):
    scope: Literal["mine", "team", "waiting_for_me"]
    person_name: PersonName = None
    from_date: IsoDate | None = Field(default=None, alias="from")
    to_date: IsoDate | None = Field(default=None, alias="to")

    @model_validator(mode="after")
    def _window_runs_forward(self) -> "ListInput":
        if self.from_date and self.to_date and self.to_date < self.from_date:
            msg = "'to' can't be before 'from'"
            raise ValueError(msg)
        return self


class CheckInput(ToolInput):
    type: Literal["pto", "sick"]
    start_date: IsoDate
    end_date: IsoDate
    half_day: bool
    hours: int | None

    @model_validator(mode="after")
    def _fits(self) -> "CheckInput":
        if self.end_date < self.start_date:
            msg = "'end_date' can't be before 'start_date'"
            raise ValueError(msg)
        if self.hours is not None:
            if self.type != "sick":
                msg = "'hours' is for sick time only: use 'half_day' for half a day of PTO"
                raise ValueError(msg)
            if not 1 <= self.hours <= MAX_SICK_HOURS:
                msg = f"'hours' is 1 to {MAX_SICK_HOURS}"
                raise ValueError(msg)
            if self.half_day:
                msg = "give 'half_day' or 'hours', not both"
                raise ValueError(msg)
        return self

    def new_request(self) -> NewRequest:
        """The engine's request: a half day is 240 minutes, hours are 60 each."""
        partial = HALF_DAY_MINUTES if self.half_day else None
        if self.hours is not None:
            partial = self.hours * 60
        return NewRequest(self.type, self.start_date, self.end_date, partial)


class DecisionInput(ToolInput):
    request_id: RequestId
    decision: Literal["approve", "deny"]


class CancelInput(ToolInput):
    request_id: RequestId


# ---------------------------------------------------------------------------------------------
# One parse for `describe`, `check`, and `run`


@dataclass(frozen=True)
class _Parsed[T: ToolInput]:
    arguments: T
    summary: str


def _parse[T: ToolInput](
    model: type[T], raw_input: Any, summarize: Callable[[T], str]
) -> _Parsed[T] | ToolOutcome:
    try:
        arguments = model.model_validate(raw_input)
    except ValidationError as error:
        return failure(describe_problem(error))
    return _Parsed(arguments, summarize(arguments))


def _tool[T: ToolInput](
    name: str,
    definition: dict[str, Any],
    model: type[T],
    summarize: Callable[[T], str],
    execute: Callable[[T, ToolContext, str], Awaitable[ToolOutcome]],
    *,
    proposes: bool = False,
) -> Tool:
    def describe(raw_input: Any) -> str:
        parsed = _parse(model, raw_input, summarize)
        return "" if isinstance(parsed, ToolOutcome) else parsed.summary

    def check(raw_input: Any) -> list[str]:
        try:
            model.model_validate(raw_input)
        except ValidationError as error:
            return validation_problems(error)
        return []

    async def run(raw_input: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        parsed = _parse(model, raw_input, summarize)
        if isinstance(parsed, ToolOutcome):
            return parsed
        try:
            return await execute(parsed.arguments, ctx, parsed.summary)
        except TurnFinished:
            # The turn ended while the tool ran: no card is stored, and the model is told.
            return failure(TURN_ENDED, parsed.summary)
        except Exception as error:
            logger.warning("%s failed: %s", name, error_name(error))
            return failure(UNREADABLE, parsed.summary)

    return Tool(name, definition, run, describe, check, proposes)


def _day_range(start: date, end: date) -> str:
    return start.isoformat() if start == end else f"{start.isoformat()} to {end.isoformat()}"


def _request_summary(arguments: CheckInput) -> str:
    summary = f"{arguments.type} {_day_range(arguments.start_date, arguments.end_date)}"
    if arguments.half_day:
        summary += ", half day"
    if arguments.hours is not None:
        summary += f", {arguments.hours} hours"
    return summary


# ---------------------------------------------------------------------------------------------
# person_name: only among the people the asker may read


def _normal(name: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", name).split()).casefold()


async def _readable_people(db: AsyncSession, ctx: ToolContext) -> list[tuple[UUID, str, str, str]]:
    """(ID, given name, family name, title) of each person the asker may read for time off."""
    actor = ctx.actor
    query = select(Person.id, Person.given_name, Person.family_name, Person.title).where(
        Person.tenant_id == actor.tenant_id
    )
    if not actor.is_hr_admin:
        # Everyone else may read themselves and their reports, which narrows the read itself.
        query = query.where(Person.id.in_({actor.person_id, *actor.report_ids}))
    rows = (await db.execute(query.order_by(Person.family_name, Person.given_name))).all()
    return [
        (row.id, row.given_name, row.family_name, row.title)
        for row in rows
        if can(actor, Action.TIMEOFF_READ, PersonResource(row.id))
    ]


def _ambiguous(matches: list[tuple[UUID, str, str, str]]) -> ToolOutcome:
    shown = matches[:MAX_LISTED_NAMES]
    listed = ", ".join(f"{given} {family} ({title})" for _, given, family, title in shown)
    more = len(matches) - len(shown)
    tail = f", and {more} more" if more else ""
    return failure(f"More than one person matches: {listed}{tail}. Use the full name.")


async def _resolve(
    db: AsyncSession, ctx: ToolContext, person_name: str | None
) -> tuple[UUID, str] | ToolOutcome:
    """The person a tool is about and their name. Omitted means the asker. A name is matched
    case-insensitively among the people the asker may read: the full name first, then a given or
    family name. No match is an error that names no one; several list those matches' names and
    titles, which are directory information."""
    people = await _readable_people(db, ctx)
    if person_name is None:
        own = next((p for p in people if p[0] == ctx.actor.person_id), None)
        if own is None:
            return failure(UNREADABLE)
        return own[0], f"{own[1]} {own[2]}"
    wanted = _normal(person_name)
    matches = [p for p in people if _normal(f"{p[1]} {p[2]}") == wanted]
    if not matches:
        matches = [p for p in people if wanted in (_normal(p[1]), _normal(p[2]))]
    if not matches:
        return failure(NO_MATCH)
    if len(matches) > 1:
        return _ambiguous(matches)
    [(found, given, family, _title)] = matches
    return found, f"{given} {family}"


# ---------------------------------------------------------------------------------------------
# The read tools


def _balance_summary(arguments: BalanceInput) -> str:
    if arguments.person_name is None:
        return "own balance"
    return f"person_name={shortened(arguments.person_name, 40)!r}"


async def _run_balance(arguments: BalanceInput, ctx: ToolContext, summary: str) -> ToolOutcome:
    async with tenant_session(ctx.engine, ctx.tenant_ctx) as db:
        resolved = await _resolve(db, ctx, arguments.person_name)
        if isinstance(resolved, ToolOutcome):
            return ToolOutcome(resolved.content, resolved.is_error, summary)
        person_id, name = resolved
        balances = await service.balances(db, ctx.actor, person_id, ctx.now)
    if isinstance(balances, Refused):
        return failure(refusal_text(balances.code), summary)
    return ToolOutcome([json_block(balance_result(name, balances))], summary=summary)


def _list_summary(arguments: ListInput) -> str:
    summary = f"scope={arguments.scope}"
    if arguments.person_name is not None:
        summary += f", person_name={shortened(arguments.person_name, 40)!r}"
    if arguments.from_date or arguments.to_date:
        first = arguments.from_date.isoformat() if arguments.from_date else ""
        last = arguments.to_date.isoformat() if arguments.to_date else ""
        summary += f", {first}..{last}"
    return summary


async def _run_list(arguments: ListInput, ctx: ToolContext, summary: str) -> ToolOutcome:
    actor = ctx.actor
    waiting = arguments.scope == "waiting_for_me"
    async with tenant_session(ctx.engine, ctx.tenant_ctx) as db:
        zone = await queries.timezone_of(db, actor.tenant_id, actor.person_id)
        if zone is None:
            return failure(UNREADABLE, summary)
        today = today_at(zone, ctx.now)
        first = arguments.from_date or today - timedelta(days=DEFAULT_DAYS_BACK)
        last = arguments.to_date or today + timedelta(days=DEFAULT_DAYS_AHEAD)
        # What waits for a decision ignores the window, so its bounds can't clash.
        if last < first and not waiting:
            if arguments.from_date and not arguments.to_date:
                return failure(
                    "'from' is after the default end of the window. Move 'from' earlier, "
                    "or give 'to' as well.",
                    summary,
                )
            if arguments.to_date and not arguments.from_date:
                return failure(
                    "'to' is before the default start of the window. Move 'to' later, "
                    "or give 'from' as well.",
                    summary,
                )
            return failure("The window can't end before it starts.", summary)
        if arguments.person_name is not None:
            resolved = await _resolve(db, ctx, arguments.person_name)
            if isinstance(resolved, ToolOutcome):
                return ToolOutcome(resolved.content, resolved.is_error, summary)
            people = frozenset({resolved[0]})
            if waiting:
                people &= actor.direct_report_ids
        else:
            people = {
                "mine": frozenset({actor.person_id}),
                "team": actor.report_ids,
                "waiting_for_me": actor.direct_report_ids,
            }[arguments.scope]
        rows = (
            await queries.load_request_rows(
                db,
                actor.tenant_id,
                person_ids=people,
                # What waits for a decision is shown whenever its days fall: it still needs one.
                overlapping=None if waiting else (first, last),
                pending_pto_only=waiting,
                limit=MAX_REQUESTS + 1,
            )
            if people
            else []
        )
    # The people were chosen by the policy's own sets; asking it for each row is a second guard.
    readable = [
        row for row in rows if can(actor, Action.TIMEOFF_READ, service.request_resource(row))
    ]
    result = {
        "window": None if waiting else {"from": first.isoformat(), "to": last.isoformat()},
        "requests": [request_row(row) for row in readable[:MAX_REQUESTS]],
        "truncated": len(readable) > MAX_REQUESTS,
    }
    return ToolOutcome([json_block(result)], summary=summary)


async def _run_check(arguments: CheckInput, ctx: ToolContext, summary: str) -> ToolOutcome:
    async with tenant_session(ctx.engine, ctx.tenant_ctx) as db:
        preview = await service.preview(db, ctx.actor, arguments.new_request(), ctx.now)
    return ToolOutcome([json_block(check_result(preview))], summary=summary)


# ---------------------------------------------------------------------------------------------
# The proposal tools


def _proposed(
    ref_id: UUID,
    action: Literal["timeoff.request", "timeoff.decide", "timeoff.cancel"],
    expires_at: datetime,
    card: RequestCard | DecideCard | CancelCard,
) -> ProposalOut:
    """The proposal as the conversation read will show it: pending, with its turn still running
    (Confirm waits until the answer ends)."""
    return ProposalOut(
        id=ref_id,
        action=action,
        status="pending",
        canceled_reason=None,
        expires_at=expires_at,
        card=card,
        failure=None,
        turn_running=True,
    )


async def _run_request(arguments: CheckInput, ctx: ToolContext, summary: str) -> ToolOutcome:
    new = arguments.new_request()
    async with tenant_session(ctx.engine, ctx.tenant_ctx) as db:
        card = await request_card_for(db, ctx.actor, new, ctx.now)
    if isinstance(card, Preview):
        return failure(problem_sentences(card), summary)
    ref = await create_proposal(
        ctx.engine,
        ctx.tenant_ctx,
        conversation_id=ctx.conversation_id,
        turn_id=ctx.turn_id,
        action="timeoff.request",
        payload=RequestPayload(
            type=new.type,
            start_date=new.start,
            end_date=new.end,
            partial_minutes=new.partial_minutes,
        ),
        card=card,
    )
    return ToolOutcome(
        [json_block(with_replacement(request_card_result(card), ref.replaced))],
        summary=summary,
        proposal=_proposed(ref.id, "timeoff.request", ref.expires_at, card),
    )


def _decision_summary(arguments: DecisionInput) -> str:
    return f"{arguments.decision} request {arguments.request_id}"


async def _run_decision(arguments: DecisionInput, ctx: ToolContext, summary: str) -> ToolOutcome:
    request_id = UUID(arguments.request_id)
    async with tenant_session(ctx.engine, ctx.tenant_ctx) as db:
        card = await decide_card(db, ctx.actor, request_id, arguments.decision, ctx.now)
    if isinstance(card, Refused):
        return failure(refusal_text(card.code), summary)
    ref = await create_proposal(
        ctx.engine,
        ctx.tenant_ctx,
        conversation_id=ctx.conversation_id,
        turn_id=ctx.turn_id,
        action="timeoff.decide",
        payload=DecidePayload(request_id=request_id, decision=arguments.decision),
        card=card,
    )
    return ToolOutcome(
        [
            json_block(
                with_replacement(decide_card_result(arguments.request_id, card), ref.replaced)
            )
        ],
        summary=summary,
        proposal=_proposed(ref.id, "timeoff.decide", ref.expires_at, card),
    )


def _cancel_summary(arguments: CancelInput) -> str:
    return f"cancel request {arguments.request_id}"


async def _run_cancel(arguments: CancelInput, ctx: ToolContext, summary: str) -> ToolOutcome:
    request_id = UUID(arguments.request_id)
    async with tenant_session(ctx.engine, ctx.tenant_ctx) as db:
        card = await cancel_card(db, ctx.actor, request_id, ctx.now)
    if isinstance(card, Refused):
        return failure(refusal_text(card.code), summary)
    ref = await create_proposal(
        ctx.engine,
        ctx.tenant_ctx,
        conversation_id=ctx.conversation_id,
        turn_id=ctx.turn_id,
        action="timeoff.cancel",
        payload=CancelPayload(request_id=request_id),
        card=card,
    )
    return ToolOutcome(
        [
            json_block(
                with_replacement(cancel_card_result(arguments.request_id, card), ref.replaced)
            )
        ],
        summary=summary,
        proposal=_proposed(ref.id, "timeoff.cancel", ref.expires_at, card),
    )


# The order is fixed: it is part of the cached prompt prefix, and the toolset version covers it.
TOOLS: tuple[Tool, ...] = (
    _tool(BALANCE_NAME, BALANCE_DEFINITION, BalanceInput, _balance_summary, _run_balance),
    _tool(LIST_NAME, LIST_DEFINITION, ListInput, _list_summary, _run_list),
    _tool(CHECK_NAME, CHECK_DEFINITION, CheckInput, _request_summary, _run_check),
    _tool(
        REQUEST_NAME,
        REQUEST_DEFINITION,
        CheckInput,
        _request_summary,
        _run_request,
        proposes=True,
    ),
    _tool(
        DECISION_NAME,
        DECISION_DEFINITION,
        DecisionInput,
        _decision_summary,
        _run_decision,
        proposes=True,
    ),
    _tool(CANCEL_NAME, CANCEL_DEFINITION, CancelInput, _cancel_summary, _run_cancel, proposes=True),
)
