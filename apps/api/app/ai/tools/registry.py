"""The tool registry: the definitions the model is sent, and the one way a tool is run.

It knows nothing of the transport, so a later adapter (an MCP server, say) can wrap it. Tool inputs
stream to us before the API validates them, so every input is checked here, against our own limits,
before any tool runs; a bad one comes back as an error result the model can read and correct.
"""

import logging
from typing import Any

from app.ai.tools import cases, handbook, people, timeoff
from app.ai.tools.base import Tool, ToolContext, ToolOutcome, failure

__all__ = [
    "TOOL_DEFINITIONS",
    "ToolContext",
    "ToolOutcome",
    "describe_call",
    "input_problems",
    "proposes",
    "run_tool",
]

logger = logging.getLogger(__name__)

# The order is fixed: it is part of the cached prompt prefix, and the toolset version covers it.
_TOOLS: tuple[Tool, ...] = (
    handbook.TOOL,
    people.PROFILE_TOOL,
    people.FIND_TOOL,
    *timeoff.TOOLS,
    cases.MY_CASES_TOOL,
    cases.LIST_TOOL,
)
_BY_NAME: dict[str, Tool] = {tool.name: tool for tool in _TOOLS}
TOOL_DEFINITIONS: list[dict[str, Any]] = [tool.definition for tool in _TOOLS]


def describe_call(name: str, raw_input: Any) -> str:
    """The summary a tool will report for this input, so `tool.started` and `tool.finished` agree.
    Empty when the input is too malformed to summarize."""
    tool = _BY_NAME.get(name)
    return "" if tool is None else tool.describe(raw_input)


def proposes(name: str) -> bool:
    """Whether the named tool stores a card for a person to confirm. False for an unknown name."""
    tool = _BY_NAME.get(name)
    return tool is not None and tool.proposes


def input_problems(name: str, raw_input: Any) -> list[str] | None:
    """The problems with a raw input, checked by the named tool's own input model: an empty list
    for a good one, and None when there is no such tool. Touches nothing but the input."""
    tool = _BY_NAME.get(name)
    return None if tool is None else tool.check(raw_input)


async def run_tool(name: str, raw_input: Any, ctx: ToolContext) -> ToolOutcome:
    """Run the named tool for the session in `ctx`. Never raises for a bad name or input."""
    tool = _BY_NAME.get(name)
    if tool is None:
        return failure(f"Unknown tool {name[:40]!r}. Use one of: {', '.join(_BY_NAME)}.")
    if not isinstance(raw_input, dict):
        return failure("The tool input must be an object.")
    return await tool.run(raw_input, ctx)
