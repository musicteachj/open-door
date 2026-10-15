"""A rule-based stand-in for Claude (ADR 0010). It makes no network call and needs no database.

The browser tests, the proxy check, and `make dev` run the real loop, tools, citation mapping, and
stream against this transport, so everything but the model's judgment is exercised for free.

Which scenario runs is picked by trigger phrases in the question (app/ai/scripted_scenarios.json,
which the browser tests import). A question with no trigger gets the default: search the handbook,
then write two sentences that quote the first passage and cite it.
"""

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app.ai.pricing import SCRIPTED_MODEL, IterationUsage, Usage
from app.ai.text import one_line
from app.ai.transport import (
    GUARD_NEW_MESSAGE_TAG,
    Finished,
    GuardCategory,
    GuardKind,
    GuardRequest,
    GuardResult,
    GuardUnavailable,
    ModelEvent,
    ModelRequest,
    ModelUnavailable,
    SearchResultCitation,
    StatusNote,
    TextBlockEnd,
    TextDelta,
    ToolCall,
    count_search_results,
    iter_search_results,
)

SCENARIOS_PATH: Final = Path(__file__).with_name("scripted_scenarios.json")

# What each behavior in the scenario file does. The first group changes how the guard answers; the
# second changes how the model does. A question can trigger one of each.
GUARD_BEHAVIORS: Final = (
    "guard_crisis",
    "guard_sensitive",
    "guard_injection",
    "slow_guard",
    "guard_failure",
)
MODEL_BEHAVIORS: Final = (
    "decline",
    "safety_refusal",
    "not_found",
    "long_answer",
    "silence",
    "mid_stream_error",
)
BEHAVIORS: Final = GUARD_BEHAVIORS + MODEL_BEHAVIORS

# Fixed figures, priced at $0, so what a turn "costs" never varies.
MODEL_USAGE: Final = Usage(
    input_tokens=1200, output_tokens=80, cache_read_tokens=0, cache_write_tokens=0
)
GUARD_USAGE: Final = Usage(
    input_tokens=300, output_tokens=20, cache_read_tokens=0, cache_write_tokens=0
)

SEARCH_NOTE: Final = "Searching the handbook…"
NOT_FOUND_TEXT: Final = (
    "I couldn't find that in the handbook. I can put you in touch with HR, who can help directly."
)
DECLINE_TEXT: Final = (
    "I can't share another employee's private details, like a home address. If you need to reach"
    " someone for work, the people directory lists their work contact details."
)
MID_STREAM_TEXT: Final = "Let me check the handbook for that. "
# The long answer cites the passage this many times, once per block.
LONG_ANSWER_BLOCKS: Final = 12
EXCERPT_LIMIT_CHARACTERS: Final = 240


@dataclass(frozen=True)
class Scenario:
    id: str
    trigger: str
    behavior: str
    note: str


_SCENARIO_KEYS = ("id", "trigger", "behavior", "note")


def _scenario(position: int, entry: Any) -> Scenario:
    """One entry of the scenario file, or a ValueError that says which entry and which key."""
    if not isinstance(entry, dict):
        raise ValueError(f"scenario {position} is not an object")
    name = entry.get("id", position)
    for key in _SCENARIO_KEYS:
        if key not in entry:
            raise ValueError(f"scenario {name!r} is missing the key {key!r}")
        if not isinstance(entry[key], str) or not entry[key]:
            raise ValueError(f"scenario {name!r} needs {key!r} to be a non-empty string")
    for key in entry:
        if key not in _SCENARIO_KEYS:
            raise ValueError(f"scenario {name!r} has the unknown key {key!r}")
    return Scenario(**entry)


def load_scenarios(path: Path = SCENARIOS_PATH) -> tuple[Scenario, ...]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    scenarios = tuple(_scenario(position, entry) for position, entry in enumerate(entries))
    for scenario in scenarios:
        if scenario.behavior not in BEHAVIORS:
            raise ValueError(
                f"scenario {scenario.id!r} has the behavior {scenario.behavior!r}, which the"
                f" scripted model does not implement"
            )
    return scenarios


def _normalize(text: str) -> str:
    """Lower case, with curly apostrophes made straight, so a trigger matches how people type."""
    return text.lower().replace("’", "'").replace("‘", "'")  # noqa: RUF001


def _first_match(
    text: str, scenarios: Sequence[Scenario], behaviors: Sequence[str]
) -> Scenario | None:
    haystack = _normalize(text)
    for scenario in scenarios:
        if scenario.behavior in behaviors and _normalize(scenario.trigger) in haystack:
            return scenario
    return None


# --- Reading the request ----------------------------------------------------------------------


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _holds_tool_results(message: dict[str, Any]) -> bool:
    content = message.get("content")
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content
    )


def _question(messages: Sequence[dict[str, Any]]) -> str:
    """The text of the latest user message that isn't a tool result."""
    for message in reversed(messages):
        if message.get("role") == "user" and not _holds_tool_results(message):
            return _text_of(message.get("content"))
    return ""


def _is_second_call(messages: Sequence[dict[str, Any]]) -> bool:
    return bool(messages) and _holds_tool_results(messages[-1])


def _tool_calls_so_far(messages: Sequence[dict[str, Any]]) -> int:
    return sum(
        1
        for message in messages
        if message.get("role") == "assistant" and isinstance(message.get("content"), list)
        for block in message["content"]
        if isinstance(block, dict) and block.get("type") == "tool_use"
    )


def _first_search_result(message: dict[str, Any]) -> dict[str, Any] | None:
    """The first `search_result` block in a message, including inside its tool results."""
    return next(iter_search_results(message.get("content", [])), None)


def _index_of_first_result(messages: Sequence[dict[str, Any]]) -> int:
    """Where the first result of the latest tool result sits among all the request's results.

    The API counts every `search_result` block in the request, in order, across messages and inside
    tool results. Everything before the last message comes first, so that count is the index.
    """
    return sum(count_search_results(message.get("content", [])) for message in messages[:-1])


# --- Writing the answer -----------------------------------------------------------------------


def _sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+", one_line(text)) if part]


def _excerpt(text: str) -> str:
    if len(text) <= EXCERPT_LIMIT_CHARACTERS:
        return text
    return text[: EXCERPT_LIMIT_CHARACTERS - 1].rsplit(" ", 1)[0] + "…"


def _chunks(text: str) -> list[str]:
    """The text in word-sized pieces that join back into exactly the text."""
    return re.findall(r"\S+\s*|\s+", text)


def _passage(result: dict[str, Any]) -> str:
    """The text of a search result's first block, the one the scripted model cites."""
    content = result.get("content")
    return _text_of(content[0:1]) if isinstance(content, list) else ""


def _two_sentences(result: dict[str, Any]) -> list[str]:
    title = str(result.get("title") or "the handbook")
    sentences = _sentences(_passage(result)) or ["The handbook covers this."]
    first = f"According to {title}, {_excerpt(sentences[0])}"
    second = (
        f" It also says: {_excerpt(sentences[1])}"
        if len(sentences) > 1
        else f" That comes from {title}."
    )
    return [first, second]


def _long_answer(result: dict[str, Any]) -> list[str]:
    title = str(result.get("title") or "the handbook")
    sentences = _sentences(_passage(result)) or ["The handbook covers this."]
    return [
        f"{'' if i == 0 else ' '}{title}, point {i + 1}: {_excerpt(sentences[i % len(sentences)])}"
        for i in range(LONG_ANSWER_BLOCKS)
    ]


def _citation_for(result: dict[str, Any], index: int) -> SearchResultCitation:
    return SearchResultCitation(
        search_result_index=index,
        start_block_index=0,
        end_block_index=1,  # exclusive: block 0 only
        source=str(result["source"]),
        title=result.get("title"),
        cited_text=_passage(result),
    )


def _citation_json(citation: SearchResultCitation) -> dict[str, Any]:
    shape: dict[str, Any] = {
        "type": "search_result_location",
        "cited_text": citation.cited_text,
        "search_result_index": citation.search_result_index,
        "start_block_index": citation.start_block_index,
        "end_block_index": citation.end_block_index,
        "source": citation.source,
    }
    if citation.title is not None:
        shape["title"] = citation.title
    return shape


def _finished(
    content: list[dict[str, Any]], stop_reason: str, stop_details: dict[str, Any] | None = None
) -> Finished:
    return Finished(
        message={"role": "assistant", "content": content},
        stop_reason=stop_reason,
        stop_details=stop_details,
        usage=MODEL_USAGE,
        iterations=(IterationUsage(SCRIPTED_MODEL, MODEL_USAGE),),
        served_by=SCRIPTED_MODEL,
    )


class ScriptedTransport:
    """`silence_seconds` and `slow_guard_seconds` are what the silence and slow-guard scenarios
    wait; tests shorten them. `delta_delay_seconds` paces the text, for watching it stream."""

    def __init__(
        self,
        *,
        silence_seconds: float = 45,
        slow_guard_seconds: float = 6,
        delta_delay_seconds: float = 0,
        scenarios: Sequence[Scenario] | None = None,
    ) -> None:
        self.silence_seconds = silence_seconds
        self.slow_guard_seconds = slow_guard_seconds
        self.delta_delay_seconds = delta_delay_seconds
        self._scenarios = tuple(scenarios) if scenarios is not None else load_scenarios()

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        messages = request.messages
        question = _question(messages)
        scenario = _first_match(question, self._scenarios, MODEL_BEHAVIORS)
        behavior = scenario.behavior if scenario else "default"

        if _is_second_call(messages):
            async for event in self._second_call(messages, behavior):
                yield event
            return

        if behavior == "decline":
            async for event in self._say([(DECLINE_TEXT, None)]):
                yield event
            return
        if behavior == "safety_refusal":
            yield _finished(
                [],
                "refusal",
                stop_details={
                    "type": "refusal",
                    "category": "general_harms",
                    "explanation": "Scripted safety refusal.",
                },
            )
            return
        if behavior == "mid_stream_error":
            async for event in self._say([(MID_STREAM_TEXT, None)], finish=False):
                yield event
            raise ModelUnavailable("scripted mid-stream error", status_code=529)
        if behavior == "silence":
            await asyncio.sleep(self.silence_seconds)

        # The default, not_found, long_answer, and silence all begin by searching.
        digest = hashlib.sha256(f"{question}|{_tool_calls_so_far(messages)}".encode()).hexdigest()
        call = ToolCall(f"toolu_scripted_{digest[:12]}", "search_handbook", {"query": question})
        yield StatusNote(SEARCH_NOTE)
        yield call
        yield _finished(
            [{"type": "tool_use", "id": call.id, "name": call.name, "input": call.input}],
            "tool_use",
        )

    async def _second_call(
        self, messages: Sequence[dict[str, Any]], behavior: str
    ) -> AsyncIterator[ModelEvent]:
        result = _first_search_result(messages[-1])
        if result is None or behavior == "not_found":
            async for event in self._say([(NOT_FOUND_TEXT, None)]):
                yield event
            return
        citation = _citation_for(result, _index_of_first_result(messages))
        texts = _long_answer(result) if behavior == "long_answer" else _two_sentences(result)
        async for event in self._say([(text, citation) for text in texts]):
            yield event

    async def _say(
        self, blocks: list[tuple[str, SearchResultCitation | None]], *, finish: bool = True
    ) -> AsyncIterator[ModelEvent]:
        """Stream text blocks, each ended with its citations, then finish the message."""
        content: list[dict[str, Any]] = []
        for text, citation in blocks:
            for chunk in _chunks(text):
                if self.delta_delay_seconds:
                    await asyncio.sleep(self.delta_delay_seconds)
                yield TextDelta(chunk)
            yield TextBlockEnd((citation,) if citation else ())
            block: dict[str, Any] = {"type": "text", "text": text}
            if citation:
                block["citations"] = [_citation_json(citation)]
            content.append(block)
        if finish:
            yield _finished(content, "end_turn")

    def _triggered(self, text: str, behavior: str) -> bool:
        return _first_match(text, self._scenarios, (behavior,)) is not None

    async def classify(self, request: GuardRequest) -> GuardResult:
        text = _guard_text(request.messages)
        if self._triggered(text, "slow_guard"):
            # It does not enforce the 4-second limit itself: the caller's timeout is what is tested.
            await asyncio.sleep(self.slow_guard_seconds)
        if self._triggered(text, "guard_failure"):
            raise GuardUnavailable("scripted guard failure")
        category: GuardCategory = "ordinary"
        kind: GuardKind | None = None
        if self._triggered(text, "guard_crisis"):
            category, kind = "crisis", "self_harm"
        elif self._triggered(text, "guard_sensitive"):
            category, kind = "sensitive", "harassment_discrimination"
        return GuardResult(
            category=category,
            kind=kind,
            injection_suspected=self._triggered(text, "guard_injection"),
            usage=GUARD_USAGE,
            served_by=SCRIPTED_MODEL,
        )


def _guard_text(messages: Sequence[dict[str, Any]]) -> str:
    """The person's new message, from the last user message the guard was sent."""
    for message in reversed(messages):
        if message.get("role") == "user":
            text = _text_of(message.get("content"))
            tag = GUARD_NEW_MESSAGE_TAG
            # From the first opening tag to the LAST closing one, so a message that contains a
            # closing tag of its own can't hide the rest of itself from the stand-in.
            match = re.search(rf"<{tag}>(.*)</{tag}>", text, flags=re.DOTALL)
            return match.group(1) if match else text
    return ""
