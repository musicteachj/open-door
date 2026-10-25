"""A rule-based stand-in for Claude (ADR 0010). It makes no network call and needs no database.

The browser tests, the proxy check, and `make dev` run the real loop, tools, citation mapping, and
stream against this transport, so everything but the model's judgment is exercised for free.

Which scenario runs is picked by trigger phrases in the question (app/ai/scripted_scenarios.json,
which the browser tests import). A question with no trigger gets the default: search the handbook,
then write two sentences that quote the first result's first passage and cite it. When the search
also returns a state addendum ("CA-4.3"), that result is the one it quotes and cites.
"""

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Final

from app.ai.pricing import SCRIPTED_MODEL, IterationUsage, Usage
from app.ai.text import one_line
from app.ai.transport import (
    GUARD_NEW_MESSAGE_TAG,
    GUARD_TIMEOUT_SECONDS,
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
from app.domain.retrieval import MAX_QUERY_CHARACTERS

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
# The behaviors that call the time-off tools (the real engine, proposals, and cards run).
TIME_OFF_BEHAVIORS: Final = (
    "book_friday",
    "sick_tomorrow",
    "show_balance",
    "waiting_on_me",
    "approve_it",
    "deny_it",
    "cancel_mine",
)
MODEL_BEHAVIORS: Final = (
    "decline",
    "safety_refusal",
    "not_found",
    "long_answer",
    "silence",
    "mid_stream_error",
    "working_note",
    *TIME_OFF_BEHAVIORS,
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
# Written before the search by the working-note scenario. The turn takes it back and shows it as a
# status line, so the browser tests and Stage 6 can see a retraction.
WORKING_NOTE_TEXT: Final = "Let me look that up in the handbook first."
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
    """The search scenarios have two steps: the search, then the answer."""
    return bool(messages) and _holds_tool_results(messages[-1])


def _tool_rounds_this_turn(messages: Sequence[dict[str, Any]]) -> int:
    """How many tool rounds this turn has had so far: the assistant messages that called a tool
    after the question. The step a scenario is at. Earlier turns' rounds don't count."""
    rounds = 0
    for message in reversed(messages):
        if message.get("role") == "user" and not _holds_tool_results(message):
            break
        if message.get("role") == "assistant" and _has_tool_use(message):
            rounds += 1
    return rounds


def _has_tool_use(message: dict[str, Any]) -> bool:
    content = message.get("content")
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_use" for block in content
    )


def _tool_calls_so_far(messages: Sequence[dict[str, Any]]) -> int:
    return sum(
        1
        for message in messages
        if message.get("role") == "assistant" and isinstance(message.get("content"), list)
        for block in message["content"]
        if isinstance(block, dict) and block.get("type") == "tool_use"
    )


# A state addendum's section id is a two-letter state code, a dash, and the section number
# ("CA-4.3"), as the handbook validates it (app/domain/handbook/validate.py). A search result
# carries no kind field, only its deep link ("/handbook/CA-4.3?passage=p1"), so the id is read
# from that.
_ADDENDUM_SOURCE = re.compile(r"^/handbook/[A-Z]{2}-\d+(?:\.\d+)*(?:[?#]|$)")


def _is_addendum(result: dict[str, Any]) -> bool:
    return _ADDENDUM_SOURCE.match(str(result.get("source", ""))) is not None


def _chosen_search_result(
    messages: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], int] | None:
    """The result the scripted model cites, and its place among all the request's results.

    The first `search_result` of the latest tool result, unless the search also returned a state
    addendum: then the first addendum, so a person is cited their own state's rule. The API counts
    every `search_result` block in the request, in order, across messages and inside tool results,
    so the index is the count of everything before the last message plus the place in it.
    """
    results = list(iter_search_results(messages[-1].get("content", [])))
    if not results:
        return None
    before = sum(count_search_results(message.get("content", [])) for message in messages[:-1])
    position = next((i for i, result in enumerate(results) if _is_addendum(result)), 0)
    return results[position], before + position


# --- Reading the per-turn context, and the time-off tools' results ------------------------------

_TODAY_LINE = re.compile(r"^Today: [A-Za-z]+, (\d{4}-\d{2}-\d{2}) \(", flags=re.MULTILINE)
_WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_FRIDAY = 4


def today_from_context(messages: Sequence[dict[str, Any]]) -> date | None:
    """Today's date from the last `system` message (the per-turn context), never from a clock:
    the line "Today: Thursday, 2026-10-15 (America/Los_Angeles)." Returns None if it isn't there or
    isn't a real date."""
    for message in reversed(messages):
        if message.get("role") != "system":
            continue
        match = _TODAY_LINE.search(_text_of(message.get("content")))
        if match is None:
            return None
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None
    return None


def next_friday(today: date) -> date:
    """ "Next Friday" for the scripted model: the Friday of the following week, with weeks running
    Monday to Sunday. So on any day of one week it is the Friday after that week's own Friday, and
    on the coming Monday it moves a week on."""
    next_monday = today + timedelta(days=7 - today.weekday())
    return next_monday + timedelta(days=_FRIDAY)


def _day_name(day: date) -> str:
    return f"{_WEEKDAY_NAMES[day.weekday()]}, {_MONTH_NAMES[day.month - 1]} {day.day}"


def _days_name(first: date, last: date) -> str:
    return _day_name(first) if first == last else f"{_day_name(first)} to {_day_name(last)}"


def _iso(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


@dataclass(frozen=True)
class _ToolResult:
    """The latest tool result of the request: its JSON (None for an error or non-JSON text), whether
    the tool reported an error, and its text."""

    data: Any
    is_error: bool
    text: str


def _last_tool_result(messages: Sequence[dict[str, Any]]) -> _ToolResult:
    content = messages[-1].get("content") if messages else None
    blocks = [
        block
        for block in (content if isinstance(content, list) else [])
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    if not blocks:
        return _ToolResult(None, True, "")
    block = blocks[0]
    text = _text_of(block.get("content"))
    if block.get("is_error"):
        return _ToolResult(None, True, text)
    try:
        return _ToolResult(json.loads(text), False, text)
    except ValueError:
        return _ToolResult(None, False, text)


def _first_sentence(text: str) -> str:
    return (_sentences(text) or ["The tool gave no reason."])[0]


def _request_call(
    question: str, messages: Sequence[dict[str, Any]], day: date, kind: str
) -> ToolCall:
    return _tool_call(
        "propose_time_off_request",
        {
            "type": kind,
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "half_day": False,
            "hours": None,
        },
        question,
        messages,
    )


def _tool_call(
    name: str, arguments: dict[str, Any], question: str, messages: Sequence[dict[str, Any]]
) -> ToolCall:
    digest = hashlib.sha256(
        f"{question}|{name}|{_tool_calls_so_far(messages)}".encode()
    ).hexdigest()
    return ToolCall(f"toolu_scripted_{digest[:12]}", name, arguments)


def _listed(data: Any) -> list[dict[str, Any]]:
    requests = data.get("requests") if isinstance(data, dict) else None
    return [item for item in (requests or []) if isinstance(item, dict)]


def _can_still_be_canceled(item: dict[str, Any], today: date | None) -> bool:
    if item.get("status") not in ("pending", "approved"):
        return False
    start = _iso(item.get("startDate"))
    return start is not None and (today is None or start >= today)


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


def _query_of(question: str) -> str:
    """The question as a search query: the tool refuses more than `MAX_QUERY_CHARACTERS`, so a
    longer question is cut on a word boundary."""
    query = " ".join(question.split())
    if len(query) <= MAX_QUERY_CHARACTERS:
        return query
    cut = query[:MAX_QUERY_CHARACTERS]
    if not query[MAX_QUERY_CHARACTERS].isspace():
        space = cut.rfind(" ")
        if space > 0:
            cut = cut[:space]
    return cut.rstrip()


_TIME_OFF_LISTS = {
    "waiting_on_me": "waiting_for_me",
    "approve_it": "waiting_for_me",
    "deny_it": "waiting_for_me",
    "cancel_mine": "mine",
}
_DECISIONS = {"approve_it": "approve", "deny_it": "deny"}


def _time_off_first_call(
    behavior: str, question: str, messages: Sequence[dict[str, Any]], today: date | None
) -> ToolCall | None:
    """The first tool call of a time-off scenario, or None when it needs today's date and the
    context has none."""
    if behavior == "show_balance":
        return _tool_call("get_time_off_balance", {}, question, messages)
    if behavior in _TIME_OFF_LISTS:
        # The optional properties are left out: a strict tool can't get a null for them.
        arguments = {"scope": _TIME_OFF_LISTS[behavior]}
        return _tool_call("list_time_off_requests", arguments, question, messages)
    if today is None:
        return None
    if behavior == "book_friday":
        return _request_call(question, messages, next_friday(today), "pto")
    return _request_call(question, messages, today + timedelta(days=1), "sick")


def _time_off_next(
    behavior: str,
    question: str,
    messages: Sequence[dict[str, Any]],
    today: date | None,
    rounds: int,
    data: Any,
) -> ToolCall | str:
    """What follows a successful tool result: the next call, or the closing words."""
    if data is None:
        return "I couldn't read what the tool sent back."
    if behavior in ("book_friday", "sick_tomorrow"):
        return _request_words(behavior, today, data)
    if behavior == "show_balance":
        return _balance_words(data)
    if behavior == "waiting_on_me":
        return _waiting_words(data)
    if behavior in _DECISIONS:
        verb = _DECISIONS[behavior]
        if rounds == 1:
            waiting = _listed(data)
            if not waiting:
                return f"Nothing is waiting for your decision, so there is nothing to {verb}."
            arguments = {"request_id": str(waiting[0].get("id")), "decision": verb}
            return _tool_call("propose_time_off_decision", arguments, question, messages)
        return _decision_words(verb, data)
    # cancel_mine
    if rounds == 1:
        cancelable = [item for item in _listed(data) if _can_still_be_canceled(item, today)]
        if not cancelable:
            return "You have no requests that can be canceled."
        arguments = {"request_id": str(cancelable[0].get("id"))}
        return _tool_call("propose_cancel_time_off", arguments, question, messages)
    return _cancel_words(data)


def _request_words(behavior: str, today: date | None, data: Any) -> str:
    day = None
    if today is not None:
        day = next_friday(today) if behavior == "book_friday" else today + timedelta(days=1)
    amount = data.get("amount") if isinstance(data, dict) else None
    what = "book PTO" if behavior == "book_friday" else "record sick time"
    done = "booked" if behavior == "book_friday" else "recorded"
    when = "" if day is None else f" for {_day_name(day)}"
    figure = f": {amount}" if isinstance(amount, str) else ""
    return f"I've prepared a card to {what}{when}{figure}. Nothing is {done} until you confirm."


def _balance_words(data: Any) -> str:
    pto = data.get("pto") if isinstance(data, dict) else None
    available = pto.get("available") if isinstance(pto, dict) else None
    if not isinstance(available, str):
        return "I couldn't read your balance."
    sick = [year for year in (data.get("sick") or []) if isinstance(year, dict)]
    words = f"You have {available} of PTO available"
    if sick and isinstance(sick[0].get("available"), str):
        return f"{words}, and {sick[0]['available']} of sick time for {sick[0].get('year')}."
    return f"{words}."


def _listed_days(item: dict[str, Any]) -> str:
    first, last = _iso(item.get("startDate")), _iso(item.get("endDate"))
    return "" if first is None or last is None else _days_name(first, last)


def _waiting_words(data: Any) -> str:
    waiting = _listed(data)
    if not waiting:
        return "Nothing is waiting for your decision right now."
    first = waiting[0]
    amount = first.get("amount")
    figure = f" ({amount})" if isinstance(amount, str) else ""
    return (
        f"The first request waiting for you is from {first.get('person')}, "
        f"for {_listed_days(first)}{figure}."
    )


def _decision_words(verb: str, data: Any) -> str:
    card = data if isinstance(data, dict) else {}
    return (
        f"I've prepared a card to {verb} {card.get('person')}'s request for {_listed_days(card)}. "
        "Nothing is decided until you confirm."
    )


def _cancel_words(data: Any) -> str:
    card = data if isinstance(data, dict) else {}
    return (
        f"I've prepared a card to cancel your request for {_listed_days(card)}. "
        "Nothing is canceled until you confirm."
    )


class ScriptedTransport:
    """`silence_seconds` and `slow_guard_seconds` are what the silence and slow-guard scenarios
    wait (the slow guard waits 2 seconds past the guard's limit); tests shorten them.
    `delta_delay_seconds` paces the text, for watching it stream."""

    def __init__(
        self,
        *,
        silence_seconds: float = 45,
        slow_guard_seconds: float = GUARD_TIMEOUT_SECONDS + 2,
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

        rounds = _tool_rounds_this_turn(messages)
        if behavior in TIME_OFF_BEHAVIORS:
            async for event in self._time_off(behavior, question, messages, rounds):
                yield event
            return
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

        # The default, not_found, long_answer, silence, and working_note all begin by searching.
        digest = hashlib.sha256(f"{question}|{_tool_calls_so_far(messages)}".encode()).hexdigest()
        call = ToolCall(
            f"toolu_scripted_{digest[:12]}", "search_handbook", {"query": _query_of(question)}
        )
        content: list[dict[str, Any]] = []
        if behavior == "working_note":
            # Text before the search: the turn streams it, then takes it back at the tool call.
            async for event in self._say([(WORKING_NOTE_TEXT, None)], finish=False):
                yield event
            content.append({"type": "text", "text": WORKING_NOTE_TEXT})
        else:
            yield StatusNote(SEARCH_NOTE)
        yield call
        yield _finished(
            [
                *content,
                {"type": "tool_use", "id": call.id, "name": call.name, "input": call.input},
            ],
            "tool_use",
        )

    async def _time_off(
        self, behavior: str, question: str, messages: Sequence[dict[str, Any]], rounds: int
    ) -> AsyncIterator[ModelEvent]:
        """One step of a time-off scenario: `rounds` tool rounds so far this turn. Each step is a
        tool call or the closing words, which quote the tool's labels and never calculate."""
        today = today_from_context(messages)
        if rounds == 0:
            call = _time_off_first_call(behavior, question, messages, today)
        else:
            result = _last_tool_result(messages)
            if result.is_error:
                words = f"That didn't work: {_first_sentence(result.text)}"
                async for event in self._say([(words, None)]):
                    yield event
                return
            outcome = _time_off_next(behavior, question, messages, today, rounds, result.data)
            if isinstance(outcome, str):
                async for event in self._say([(outcome, None)]):
                    yield event
                return
            call = outcome
        if call is None:
            words = "I can't tell today's date, so I can't work out which day you mean."
            async for event in self._say([(words, None)]):
                yield event
            return
        yield call
        yield _finished(
            [{"type": "tool_use", "id": call.id, "name": call.name, "input": call.input}],
            "tool_use",
        )

    async def _second_call(
        self, messages: Sequence[dict[str, Any]], behavior: str
    ) -> AsyncIterator[ModelEvent]:
        chosen = _chosen_search_result(messages)
        if chosen is None or behavior == "not_found":
            async for event in self._say([(NOT_FOUND_TEXT, None)]):
                yield event
            return
        result, index = chosen
        citation = _citation_for(result, index)
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
            # It does not enforce the guard's time limit itself: the caller's timeout is what
            # is tested.
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
