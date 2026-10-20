"""`search_handbook`: the assistant's only way to learn what the handbook says.

Each hit becomes one `search_result` block with citations on, so the model's answer can cite the
exact passages. The matching `SourceEntry` is kept beside it (the conversation stores them), which
is how a citation's index later finds its passage.
"""

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.ai.conversations import SourceEntry
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
from app.db.tenancy import tenant_session
from app.domain.retrieval import MAX_QUERY_CHARACTERS
from app.modules.handbook.search import (
    Hit,
    clean_query,
    embed_query,
    search_handbook,
)

logger = logging.getLogger(__name__)

NAME = "search_handbook"
MAX_HITS = 5
# The handbook's own codes for the four offices, in the order the error message lists them.
LOCATION_CODES = ("den", "oak", "aus", "atl")
NO_HITS = "No handbook passages matched."

DEFINITION: dict[str, Any] = {
    "name": NAME,
    "description": (
        "Search the company handbook for passages that answer a policy question. Returns up to "
        f"{MAX_HITS} passages as sources you can cite, best match first. By default it searches "
        "the policies that apply to the person asking. To answer for another office, pass its "
        "location code (den, oak, aus, or atl): that returns the policies for that office with "
        "the asker's own employment type. The query is a plain-language question or key words, "
        f"1 to {MAX_QUERY_CHARACTERS} characters. Search again with different words if the first "
        "search finds nothing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": f"What to look up, 1 to {MAX_QUERY_CHARACTERS} characters.",
            },
            "location": {
                "type": "string",
                "enum": list(LOCATION_CODES),
                "description": "Optional. An office's code, to get that office's policies.",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


class SearchInput(ToolInput):
    query: str
    # A plain string here, so an unknown code gets the helpful message below, not a schema error.
    location: str | None = None


def _title(hit: Hit) -> str:
    title = f"{hit.section_id} {hit.title}"
    return f"{title} · {hit.group_name}" if hit.group_name else title


def _block(hit: Hit) -> dict[str, Any]:
    return {
        "type": "search_result",
        "source": hit.deep_link,
        "title": _title(hit),
        "content": [text_block(passage) for passage in hit.passages],
        "citations": {"enabled": True},
    }


def _entry(hit: Hit) -> SourceEntry:
    return SourceEntry(
        section_id=hit.section_id,
        passage_ids=hit.passage_ids,
        title=hit.title,
        group_name=hit.group_name,
        audience_label=hit.audience_label,
        last_updated=hit.last_updated,
        deep_link=hit.deep_link,
    )


def summary_of(question: str, location: str | None) -> str:
    """The trace summary of a search: the cleaned question and the location asked for."""
    summary = f"query={shortened(question)!r}"
    if location is not None:
        summary += f", location={shortened(location, 10)}"
    return summary


@dataclass(frozen=True)
class _Parsed:
    question: str
    location: str | None
    summary: str


def _parse(raw_input: Any) -> _Parsed | ToolOutcome:
    """Check the input, once, for both `describe` and `run`. A failure is the outcome `run` returns,
    and its `summary` is what `describe` reports: empty where the failure has none."""
    try:
        arguments = SearchInput.model_validate(raw_input)
    except ValidationError as error:
        return failure(describe_problem(error))
    try:
        # Measured after cleaning, as `find_people` does, so padding that cleans away doesn't
        # reject a valid query.
        question = clean_query(arguments.query, max_characters=None)
    except ValueError:
        return failure("'query' is empty. Say what to look up.")
    if len(question) > MAX_QUERY_CHARACTERS:
        return failure(f"'query' is too long: use at most {MAX_QUERY_CHARACTERS} characters.")
    summary = summary_of(question, arguments.location)
    location = arguments.location
    if location is not None and location not in LOCATION_CODES:
        return failure(
            f"Unknown location {shortened(location, 20)!r}. "
            f"Use one of: {', '.join(LOCATION_CODES)}.",
            summary,
        )
    return _Parsed(question, location, summary)


def describe(raw_input: Any) -> str:
    """The summary `run` will give, for the `tool.started` event."""
    parsed = _parse(raw_input)
    return parsed.summary


async def run(raw_input: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    parsed = _parse(raw_input)
    if isinstance(parsed, ToolOutcome):
        return parsed
    question, location, summary = parsed.question, parsed.location, parsed.summary
    try:
        # Embedded first: a slow Voyage call never holds a transaction or a connection.
        vector = None if ctx.embedder is None else await embed_query(ctx.embedder, question)
        async with tenant_session(ctx.engine, ctx.tenant_ctx) as db:
            result = await search_handbook(
                db,
                version_id=ctx.version_id,
                asker=ctx.asker,
                query=question,
                query_vector=vector,
                location_code=location,
                limit=MAX_HITS,
            )
    except Exception as error:
        logger.warning("search_handbook failed: %s", error_name(error))
        return failure(
            "The handbook search failed. Try again, or say you couldn't look it up.", summary
        )
    if not result.hits:
        return ToolOutcome([text_block(NO_HITS)], summary=summary)
    return ToolOutcome(
        [_block(hit) for hit in result.hits],
        summary=summary,
        sources=[_entry(hit) for hit in result.hits],
    )


TOOL = Tool(NAME, DEFINITION, run, describe)
