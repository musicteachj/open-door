"""What every tool shares: the context it runs in, the outcome it returns, and input checking.

Kept apart from the registry so the tools can import it without importing the registry back.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.conversations import SourceEntry
from app.ai.embeddings import Embedder
from app.ai.proposals import ProposalOut
from app.ai.text import one_line
from app.db.tenancy import TenantContext
from app.domain.handbook.applicability import Asker
from app.policy import Actor

# A trace summary holds this many characters of a question at most.
SUMMARY_QUERY_CHARACTERS = 60


@dataclass(frozen=True)
class ToolContext:
    """Who the tool acts for and what it reads with. Every field comes from the server session,
    never from the model's input (invariant 1)."""

    engine: AsyncEngine
    tenant_ctx: TenantContext
    actor: Actor
    asker: Asker
    version_id: UUID  # the handbook version the sandbox is pinned to
    embedder: Embedder | None  # None means full-text search only
    # The turn's own instant, the one the per-turn context used: "today" in a tool comes from it,
    # never from a clock.
    now: datetime
    # The turn and its conversation, which a proposal is stored under.
    conversation_id: UUID
    turn_id: UUID


@dataclass(frozen=True)
class ToolOutcome:
    """What a tool gives back: the blocks of the `tool_result`, whether it failed, a short summary
    of the input for the trace, and one source per `search_result` block, in order."""

    content: list[dict[str, Any]]
    is_error: bool = False
    summary: str = ""
    sources: list[SourceEntry] = field(default_factory=list)
    # The card a proposal tool stored, for the turn to send to the browser. Never part of `content`.
    proposal: ProposalOut | None = None


@dataclass(frozen=True)
class Tool:
    """One tool: what the model is sent, how it runs, and how its call is summarized.

    `describe` and `run` must share one parse of the input, so the summary on `tool.started` can't
    drift from the one on `tool.finished`."""

    name: str
    definition: dict[str, Any]
    run: Callable[[dict[str, Any], ToolContext], Awaitable[ToolOutcome]]
    describe: Callable[[Any], str]
    # The problems with a raw input, from the tool's own input model, or none. No database needed:
    # the eval graders use it to check each call against the tool that was called.
    check: Callable[[Any], list[str]]
    # A proposal tool stores a card for a person to confirm. The turn makes at most one card per
    # model response, so it needs to know which tools these are.
    proposes: bool = False


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def json_block(data: object) -> dict[str, Any]:
    """A compact JSON text block: how a tool hands the model structured data."""
    return text_block(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def failure(message: str, summary: str = "") -> ToolOutcome:
    """A tool error the model can act on. Never holds a stack trace or SQL."""
    return ToolOutcome([text_block(message)], is_error=True, summary=summary)


def shortened(text: str, limit: int = SUMMARY_QUERY_CHARACTERS) -> str:
    line = one_line(text)
    return line if len(line) <= limit else line[: limit - 1] + "…"


class ToolInput(BaseModel):
    """Base for a tool's input: no extra keys, and no coercing ("3" is not a string query)."""

    model_config = {"extra": "forbid", "strict": True}


def describe_problem(error: ValidationError) -> str:
    """A validation error as plain words. Pydantic's own text repeats the input value, which could
    be a person's question, so only the field and the reason are used."""
    parts = []
    for item in error.errors(include_input=False, include_url=False):
        field_name = ".".join(str(part) for part in item["loc"]) or "input"
        if item["type"] == "extra_forbidden":
            parts.append(f"'{field_name}' is not an input of this tool")
        elif item["type"] == "missing":
            parts.append(f"'{field_name}' is required")
        else:
            parts.append(f"'{field_name}' is not valid: {item['msg']}")
    return "; ".join(parts)


def validation_problems(error: ValidationError) -> list[str]:
    """A validation error as one plain sentence per field, for a grader to read."""
    return [
        f"'{'.'.join(str(part) for part in item['loc']) or 'input'}' is not valid: {item['msg']}"
        for item in error.errors(include_input=False, include_url=False)
    ]


def input_problems(model: type[BaseModel], raw_input: Any) -> list[str]:
    """What is wrong with `raw_input` for the input model, one sentence per field; empty when it is
    valid. The check a grader runs before a tool does."""
    try:
        model.model_validate(raw_input)
    except ValidationError as error:
        return validation_problems(error)
    return []
