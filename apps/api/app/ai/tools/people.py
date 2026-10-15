"""`get_my_profile` and `find_people`: the two tools that read people.

Neither takes a person from the model. `get_my_profile` reads the session's own person, under the
database rule that limits private details to that person and HR. `find_people` returns directory
cards only, each one checked by the policy layer.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError, field_validator
from sqlalchemy import select

from app.ai.context import role_of
from app.ai.text import error_name
from app.ai.tools.base import (
    Tool,
    ToolContext,
    ToolInput,
    ToolOutcome,
    describe_problem,
    failure,
    shortened,
    text_block,
)
from app.db.models import Tenant
from app.db.tenancy import tenant_session
from app.modules.audit.service import record_event
from app.modules.handbook.search import clean_query
from app.modules.people.queries import (
    DirectoryFilters,
    get_me,
    get_private_details,
    list_directory,
)
from app.modules.people.schemas import DirectoryCard
from app.policy import Action, PersonResource, can

logger = logging.getLogger(__name__)

PROFILE_NAME = "get_my_profile"
# What the tool reports for its call, started or finished, failed or not.
PROFILE_SUMMARY = "own profile"
FIND_NAME = "find_people"
MAX_PEOPLE = 10
MAX_PEOPLE_QUERY_CHARACTERS = 100

PROFILE_DEFINITION: dict[str, Any] = {
    "name": PROFILE_NAME,
    "description": (
        "Get the signed-in person's own profile: name, title, department, manager, location, work "
        "email, employment type (salaried or hourly), and role, plus their own private details "
        "(personal email, phone, home address, date of birth). It always returns the person who "
        "is asking and takes no input. Use it only when they ask about their own details."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
}

FIND_DEFINITION: dict[str, Any] = {
    "name": FIND_NAME,
    "description": (
        f"Find people in the company directory. Returns up to {MAX_PEOPLE} cards with name, title, "
        "department, manager, location, and work email, and never anything private. 'scope' is "
        "'everyone' for the whole company or 'my_team' for the asker's own direct and indirect "
        "reports (someone with no reports gets none). 'query' is optional text to match against "
        f"a name, title, or work email, up to {MAX_PEOPLE_QUERY_CHARACTERS} characters. The result "
        'says "truncated": true when more people matched than the 10 returned, so narrow the '
        "query to see the rest."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    f"Optional. Part of a name, title, or work email, up to "
                    f"{MAX_PEOPLE_QUERY_CHARACTERS} characters."
                ),
            },
            "scope": {"type": "string", "enum": ["everyone", "my_team"]},
        },
        "required": ["scope"],
        "additionalProperties": False,
    },
}


def _json_block(data: object) -> dict[str, Any]:
    return text_block(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def _card(card: DirectoryCard) -> dict[str, Any]:
    """A directory card in the tool's form. It has no IDs: nothing names a person to act as."""
    manager = card.manager
    return {
        "name": f"{card.given_name} {card.family_name}",
        "title": card.title,
        "department": card.department.name,
        "manager": None if manager is None else f"{manager.given_name} {manager.family_name}",
        "location": {
            "code": card.location.code,
            "name": card.location.name,
            "state": card.location.state,
        },
        "workEmail": card.work_email,
    }


class NoInput(ToolInput):
    pass


class FindInput(ToolInput):
    query: str | None = None
    scope: Literal["everyone", "my_team"]

    @field_validator("query")
    @classmethod
    def _query_fits(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value.strip()) > MAX_PEOPLE_QUERY_CHARACTERS:
            msg = f"use at most {MAX_PEOPLE_QUERY_CHARACTERS} characters"
            raise ValueError(msg)
        try:
            # The handbook search's own cleaning: control, format, and surrogate characters go.
            return clean_query(value)
        except ValueError:
            msg = "is empty. Leave 'query' out to list everyone in the scope"
            raise ValueError(msg) from None


async def run_profile(raw_input: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    try:
        NoInput.model_validate(raw_input)
    except ValidationError as error:
        return failure(describe_problem(error), PROFILE_SUMMARY)
    actor = ctx.actor
    try:
        async with tenant_session(ctx.engine, ctx.tenant_ctx) as db:
            expires_at = await db.scalar(select(Tenant.expires_at))
            if expires_at is None:
                return failure("Your profile couldn't be read.", PROFILE_SUMMARY)
            me = await get_me(db, actor, expires_at)
            details = None
            # The database decides too; this asks the policy layer first, like the people route.
            if can(actor, Action.PERSON_PRIVATE_READ, PersonResource(actor.person_id)):
                details = await get_private_details(db, actor.person_id)
            if details is not None:
                await record_event(
                    db,
                    tenant_id=actor.tenant_id,
                    actor_id=actor.person_id,
                    action="person_private.read",
                    target_type="person",
                    target_id=actor.person_id,
                    # The names of the fields returned, never their values.
                    after={"fields": sorted(details.model_dump(by_alias=True))},
                    via="assistant",
                )
    except Exception as error:
        logger.warning("get_my_profile failed: %s", error_name(error))
        return failure(
            "Your profile couldn't be read. Try again, or say you couldn't look it up.",
            PROFILE_SUMMARY,
        )
    role = role_of(me)
    profile: dict[str, Any] = {
        "givenName": me.given_name,
        "familyName": me.family_name,
        **{key: value for key, value in _card(me).items() if key != "name"},
        "employmentType": me.employment_type,
        "role": role,
        "privateDetails": None
        if details is None
        else {
            "personalEmail": details.personal_email,
            "phone": details.phone,
            "homeAddress": details.home_address,
            "dateOfBirth": details.date_of_birth.isoformat(),
        },
    }
    return ToolOutcome([_json_block(profile)], summary=PROFILE_SUMMARY)


def summary_of(scope: str, query: str | None) -> str:
    summary = f"scope={scope}"
    if query:
        summary += f", query={shortened(query, 40)!r}"
    return summary


@dataclass(frozen=True)
class _ParsedFind:
    scope: str
    query: str | None
    summary: str


def _parse_find(raw_input: Any) -> _ParsedFind | ToolOutcome:
    """Check the input, once, for both `describe_find` and `run_find`."""
    try:
        arguments = FindInput.model_validate(raw_input)
    except ValidationError as error:
        return failure(describe_problem(error))
    return _ParsedFind(
        arguments.scope, arguments.query, summary_of(arguments.scope, arguments.query)
    )


def describe_find(raw_input: Any) -> str:
    """The summary `run_find` will give, for the `tool.started` event."""
    return _parse_find(raw_input).summary


async def run_find(raw_input: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    parsed = _parse_find(raw_input)
    if isinstance(parsed, ToolOutcome):
        return parsed
    arguments = parsed
    summary = parsed.summary
    actor = ctx.actor
    filters = DirectoryFilters(
        q=arguments.query,
        # The actor's own reports, as the server loaded them for this session.
        team=actor.report_ids if arguments.scope == "my_team" else None,
    )
    try:
        async with tenant_session(ctx.engine, ctx.tenant_ctx) as db:
            page = await list_directory(db, limit=MAX_PEOPLE, after=None, filters=filters)
    except Exception as error:
        logger.warning("find_people failed: %s", error_name(error))
        return failure(
            "The directory search failed. Try again, or say you couldn't look it up.", summary
        )
    visible = [
        card for card in page.cards if can(actor, Action.DIRECTORY_READ, PersonResource(card.id))
    ]
    # `truncated` is the cursor only. Saying more when the policy removed a card would hint that
    # someone is hidden. If the policy can hide cards, filter in SQL before the limit instead.
    truncated = page.next_cursor is not None
    return ToolOutcome(
        [_json_block({"people": [_card(card) for card in visible], "truncated": truncated})],
        summary=summary,
    )


def describe_profile(raw_input: Any) -> str:
    return PROFILE_SUMMARY


PROFILE_TOOL = Tool(PROFILE_NAME, PROFILE_DEFINITION, run_profile, describe_profile)
FIND_TOOL = Tool(FIND_NAME, FIND_DEFINITION, run_find, describe_find)
