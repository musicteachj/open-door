"""`get_my_cases` and `list_cases`: the two tools that read cases, and neither returns a word a
person wrote.

A case is the person's own matter, opened by them with the form's button. The model never opens,
reads, or ranks one (invariants 1, 3, and 5). `get_my_cases` takes no input and returns the asker's
own cases as metadata: the category, the dates, and the status. `list_cases` is HR's alone: the
queue's metadata (who, what kind, when, how late), never the case's words or its summary. Both read
the actor from the server session. A tool opens its own session, where the HR flag is reset, so
`list_cases` sets it from the server's actor, never from input.
"""

import logging
from dataclasses import dataclass
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.ai.text import error_name
from app.ai.tools.base import (
    Tool,
    ToolContext,
    ToolInput,
    ToolOutcome,
    describe_problem,
    failure,
    input_problems,
    json_block,
    text_block,
)
from app.db.tenancy import set_is_hr, tenant_session
from app.domain.cases import CATEGORY_LABELS, HQ_TIMEZONE
from app.modules.audit.service import record_event
from app.modules.cases import service
from app.modules.cases.schemas import CaseStatusView, QueueItem
from app.policy import Action, PersonResource, can

logger = logging.getLogger(__name__)

MY_CASES_NAME = "get_my_cases"
MY_CASES_SUMMARY = "own cases"
LIST_NAME = "list_cases"
MAX_CASES = 20

# The one answer a non-HR asker gets, whatever cases exist and whatever the input was.
ONLY_HR_TEXT = "Only the HR team can see cases."
NO_CASES_TEXT = "You have no cases."

# The person's own words for a status, as My cases shows it.
PERSON_STATUS = {
    "new": "Sent to HR",
    "in_review": "HR is reviewing",
    "closed": "HR has finished its review",
}

MY_CASES_DEFINITION: dict[str, Any] = {
    "name": MY_CASES_NAME,
    "description": (
        "Get the signed-in person's own confidential cases: for each, the kind of case, the date "
        "it was sent, its status (Sent to HR, HR is reviewing, or HR has finished its review), "
        f"and the date HR replies by. Newest first, up to {MAX_CASES}. It takes no input and "
        "always returns the asker's own cases. It never returns what the person wrote or any "
        "summary of it, and you can't read those. Use it when they ask about the status of their "
        "own case."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
}

LIST_DEFINITION: dict[str, Any] = {
    "name": LIST_NAME,
    "description": (
        "List confidential cases for the HR team only. 'status' is 'open' (new and in review), "
        "'new', 'in_review', or 'closed'. Returns up to "
        f"{MAX_CASES} cases in the queue's order (new cases first, by the date HR replies by, "
        "then the rest, oldest first): the case ID, the kind of case, the person's name, title, "
        "and location, the date it was sent, the date HR replies by, the status, and whether a "
        "reply is due. List them in the order given. Leaves out any case you opened yourself; you "
        "see those with get_my_cases. It never returns what the person wrote or any summary of "
        "it, and you can't read those. Anyone who is not on the HR team gets an error."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["open", "new", "in_review", "closed"]},
        },
        "required": ["status"],
        "additionalProperties": False,
    },
}


class NoInput(ToolInput):
    pass


class ListInput(ToolInput):
    status: Literal["open", "new", "in_review", "closed"]


def _my_case(view: CaseStatusView) -> dict[str, Any]:
    """A case in the person's own view: no ID (nothing names a case to act on), no words."""
    zone = ZoneInfo(HQ_TIMEZONE)
    return {
        "category": CATEGORY_LABELS.get(view.category, "something else"),
        "sentOn": view.sent_at.astimezone(zone).date().isoformat(),
        "status": PERSON_STATUS.get(view.status, view.status),
        "replyBy": view.reply_by.isoformat(),
    }


async def run_my_cases(raw_input: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    try:
        NoInput.model_validate(raw_input)
    except ValidationError as error:
        return failure(describe_problem(error), MY_CASES_SUMMARY)
    try:
        async with tenant_session(ctx.engine, ctx.tenant_ctx) as db:
            views = await service.my_cases(db, ctx.actor, limit=MAX_CASES + 1)
    except Exception as error:
        logger.warning("get_my_cases failed: %s", error_name(error))
        return failure(
            "Your cases couldn't be read. Try again, or say you couldn't look them up.",
            MY_CASES_SUMMARY,
        )
    if not views:
        return ToolOutcome([text_block(NO_CASES_TEXT)], summary=MY_CASES_SUMMARY)
    shown = views[:MAX_CASES]
    data = {"cases": [_my_case(view) for view in shown], "truncated": len(views) > len(shown)}
    return ToolOutcome([json_block(data)], summary=MY_CASES_SUMMARY)


def describe_my_cases(raw_input: Any) -> str:
    return MY_CASES_SUMMARY


def check_my_cases(raw_input: Any) -> list[str]:
    return input_problems(NoInput, raw_input)


def _listed_case(item: QueueItem, today_iso: str) -> dict[str, Any]:
    """A queue row for HR: metadata only. Whether a reply is due is for a new case whose reply-by
    date is today or earlier in Denver (the counts' rule)."""
    return {
        "id": str(item.id),
        "category": CATEGORY_LABELS.get(item.category, "something else"),
        "person": f"{item.given_name} {item.family_name}",
        "title": item.title,
        "location": item.location_name,
        "sentOn": item.sent_at.astimezone(ZoneInfo(HQ_TIMEZONE)).date().isoformat(),
        "replyBy": item.reply_by.isoformat(),
        "status": item.status,
        "replyDue": item.status == "new" and item.reply_by.isoformat() <= today_iso,
    }


@dataclass(frozen=True)
class _ParsedList:
    status: str
    summary: str


def _parse_list(raw_input: Any) -> _ParsedList | ToolOutcome:
    try:
        arguments = ListInput.model_validate(raw_input)
    except ValidationError as error:
        return failure(describe_problem(error))
    return _ParsedList(arguments.status, f"status={arguments.status}")


def describe_list(raw_input: Any) -> str:
    parsed = _parse_list(raw_input)
    return parsed.summary if isinstance(parsed, _ParsedList) else ""


def _hr_only() -> ToolOutcome:
    return failure(ONLY_HR_TEXT)


async def run_list(raw_input: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    actor = ctx.actor
    # First, and before the input is looked at: anyone else gets this one answer, whatever the
    # input says and whether or not any case exists.
    if not can(actor, Action.CASE_LIST, PersonResource(actor.person_id)):
        return _hr_only()
    parsed = _parse_list(raw_input)
    if isinstance(parsed, ToolOutcome):
        return parsed
    try:
        async with tenant_session(ctx.engine, ctx.tenant_ctx) as db:
            # A tool's session starts with the HR flag off. It is set from the server's actor.
            await set_is_hr(db, actor.is_hr_admin)
            page = await service.queue(db, actor, parsed.status, None)
            # HR's own case is left out, as the counts leave it out: they can't act on it.
            items = [item for item in page.items if not item.is_own]
            shown = items[:MAX_CASES]
            await record_event(
                db,
                tenant_id=actor.tenant_id,
                actor_id=actor.person_id,
                action="case.listed",
                target_type="case",
                # The count and the filter only: never a name, a category, or any text.
                after={"count": len(shown), "status": parsed.status},
                via="assistant",
            )
    except Exception as error:
        logger.warning("list_cases failed: %s", error_name(error))
        return failure("The cases couldn't be listed. Try again.", parsed.summary)
    today_iso = ctx.now.astimezone(ZoneInfo(HQ_TIMEZONE)).date().isoformat()
    truncated = page.next_cursor is not None or len(items) > len(shown)
    data = {"cases": [_listed_case(item, today_iso) for item in shown], "truncated": truncated}
    return ToolOutcome([json_block(data)], summary=parsed.summary)


def check_list(raw_input: Any) -> list[str]:
    return input_problems(ListInput, raw_input)


MY_CASES_TOOL = Tool(
    MY_CASES_NAME, MY_CASES_DEFINITION, run_my_cases, describe_my_cases, check_my_cases
)
LIST_TOOL = Tool(LIST_NAME, LIST_DEFINITION, run_list, describe_list, check_list)
