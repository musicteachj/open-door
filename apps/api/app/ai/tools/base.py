"""What every tool shares: the context it runs in, the outcome it returns, and input checking.

Kept apart from the registry so the tools can import it without importing the registry back.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.ai.conversations import SourceEntry
from app.ai.embeddings import Embedder
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
    embedder: Embedder


@dataclass(frozen=True)
class ToolOutcome:
    """What a tool gives back: the blocks of the `tool_result`, whether it failed, a short summary
    of the input for the trace, and one source per `search_result` block, in order."""

    content: list[dict[str, Any]]
    is_error: bool = False
    summary: str = ""
    sources: list[SourceEntry] = field(default_factory=list)


@dataclass(frozen=True)
class Tool:
    """One tool: what the model is sent, how it runs, and how its call is summarized.

    `describe` and `run` must share one parse of the input, so the summary on `tool.started` can't
    drift from the one on `tool.finished`."""

    name: str
    definition: dict[str, Any]
    run: Callable[[dict[str, Any], ToolContext], Awaitable[ToolOutcome]]
    describe: Callable[[Any], str]


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


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
