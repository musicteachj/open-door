"""The assistant eval's judge: a model that answers six yes or no questions about each Q&A answer.

The deterministic graders (graders.py) cover what a program can check. The judge covers the rest:
is the answer correct as the reference has it, faithful to the passages it cites, free of uncited
policy claims, clear about whose policy it states, free of employment decisions, and honest about
being an AI. An item passes only if every line is yes. The rubric is `judge.md`, versioned on its
first line (`JUDGE_VERSION`), like a prompt: changing it invalidates the recorded judge calls.

**The request** (`judge_api_kwargs`, pure) is one Messages API call: `claude-sonnet-5-5`, effort
`medium`, and a strict JSON schema. It sends no sampling parameters (non-default values are a 400
on Sonnet 5.5), no `thinking` (omitting it runs adaptive thinking, and `disabled` is a 400), and no
`fallbacks`: a fallback would grade with a different model and break the agreement measurement
against the owner's hand grades. Structured outputs and citations can't be combined, but the judge
sends no documents, so that never arises.

**The schema form** is nested: one object for each rubric line, `{"<key>": {"verdict": boolean,
"reason": string}}`, all required, nothing else. A reason beside every verdict keeps the judge's
explanation with the line it explains, and the owner reads those next to the hand grades.

**The answer** is read strictly (`parse_response`). The text comes from the text blocks by type,
never by position, because a response can begin with thinking blocks. A stop reason other than
`end_turn` (a refusal, `max_tokens`) means there is no usable verdict, and so does a wrong shape or
a wrong key. The item is then "judge unavailable": counted and reported, never a pass.

**Recording.** The `Judge` answers from a `FixtureStore` of kind "judge" first, keyed by
`fingerprint("judge", judge_api_kwargs(...))`, and calls its caller only for a request not recorded
(no caller means replay, and a miss raises `ReplayMiss`). What is recorded is the raw response, so a
change to how it is parsed needs no re-recording. A refusal or a cutoff is model behavior and is
recorded. A transient failure (a dropped connection, a timeout, a 429 or 5xx) says nothing about
the judge and is never recorded. A refused request (a 4xx) stops the run: retrying a bad key for
every item only repeats it.

Pure apart from the SDK client the live caller wraps. Run from apps/api.
"""

import copy
import json
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any, NamedTuple

from anthropic import (
    APIConnectionError,
    APIError,
    APIStatusError,
    AsyncAnthropic,
    BadRequestError,
    Timeout,
)

from app.ai.anthropic_transport import is_spend_limit, usage_from_sdk
from app.ai.pricing import Usage, cost_usd, is_priced
from app.ai.replay import (
    RE_RECORD_HINT,
    FixtureStore,
    Record,
    ReplayMiss,
    decode_usage,
    encode_usage,
    fingerprint,
)
from app.modules.sandbox.seed import SeedCompany

EVAL_DIR = Path(__file__).resolve().parent
JUDGE_MD_PATH = EVAL_DIR / "judge.md"

JUDGE_MODEL = "claude-sonnet-5-5"
JUDGE_EFFORT = "medium"
# Room for adaptive thinking and the twelve fields of the answer.
JUDGE_MAX_TOKENS = 8000

# The rubric's six lines, in the order the schema and the reports use. `judge.md` describes each.
RUBRIC_KEYS = (
    "correct",
    "faithful",
    "no_uncited_claims",
    "says_whose_policy",
    "no_employment_decision",
    "says_ai_if_asked",
)
UNCITED_KEY = "no_uncited_claims"
# Between the different words cited for one marker.
CITED_TEXT_JOINER = " ... "
# Rough size of a token in characters, for the input half of a judge reservation.
CHARACTERS_PER_TOKEN = 3


def _line_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"verdict": {"type": "boolean"}, "reason": {"type": "string"}},
        "required": ["verdict", "reason"],
        "additionalProperties": False,
    }


# Every object is closed and every property required. No length or range keywords: the API does not
# support them.
VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {key: _line_schema() for key in RUBRIC_KEYS},
    "required": list(RUBRIC_KEYS),
    "additionalProperties": False,
}

_VERSION_LINE = re.compile(r"JUDGE_VERSION: (\S+)")


class JudgeUnavailable(Exception):  # noqa: N818
    """The judge gave no usable verdict for this item. The message says why."""


class JudgeTransient(Exception):  # noqa: N818
    """The call failed in a way that says nothing about the judge (a dropped connection, a timeout,
    a 429 or 5xx). The item is unavailable and the failure is never recorded."""


class JudgeFatal(Exception):  # noqa: N818
    """The API refused the request (a bad key, a rejected request). Retrying for each item only
    repeats it, so the run stops."""


CONSOLE_LIMIT_MESSAGE = (
    "The Anthropic Console's spend limit was reached; raise it in the Console"
    " (Settings, Billing) or wait for next month"
)


class ConsoleSpendLimit(JudgeFatal):
    """The Anthropic Console's own spend limit was reached. It is not the run's cap: no setting here
    can lift it, so the run stops. The judge and the answers' model report it the same way."""

    def __init__(self) -> None:
        super().__init__(CONSOLE_LIMIT_MESSAGE)


# --- The rubric -------------------------------------------------------------------------------


def judge_version(text: str | None = None) -> str:
    """The `JUDGE_VERSION` on the first line of judge.md (or of `text`)."""
    source = judge_system() if text is None else text
    match = _VERSION_LINE.fullmatch(source.splitlines()[0] if source else "")
    if match is None:
        raise ValueError("judge.md must start with a line like `JUDGE_VERSION: 2026-10.1`")
    return match.group(1)


@cache
def judge_system() -> str:
    """The judge's system prompt: judge.md as written, version line included, so that a new version
    always invalidates the recordings."""
    return JUDGE_MD_PATH.read_text(encoding="utf-8")


# --- What the judge reads ---------------------------------------------------------------------


@dataclass(frozen=True)
class Passage:
    """One cited passage: what the answer says it quoted, and what the handbook says."""

    marker: int
    section_id: str
    title: str
    cited_text: str
    # The text of the section as the assistant retrieved it. None when the tool results hold no
    # such section: a citation to something the assistant never saw.
    section_text: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "marker": self.marker,
            "section": self.section_id,
            "title": self.title,
            "cited_text": self.cited_text,
            "section_text": self.section_text,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "Passage":
        section_text = data["section_text"]
        return cls(
            marker=int(data["marker"]),
            section_id=str(data["section"]),
            title=str(data["title"]),
            cited_text=str(data["cited_text"]),
            section_text=None if section_text is None else str(section_text),
        )


@dataclass(frozen=True)
class JudgeInput:
    """Everything the judge is given about one answer."""

    question: str
    # The asker in one line: name, employment type, and office. Trusted.
    asker: str
    # Set when the question is about another office. Trusted.
    location_asked: str | None
    reference: str
    # The answer with a `[n]` marker where each citation sits.
    answer: str
    passages: tuple[Passage, ...] = field(default=())

    def to_json(self) -> dict[str, Any]:
        return {
            "asker": self.asker,
            "location_asked": self.location_asked,
            "question": self.question,
            "reference": self.reference,
            "answer": self.answer,
            "passages": [p.to_json() for p in self.passages],
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "JudgeInput":
        location = data["location_asked"]
        return cls(
            question=str(data["question"]),
            asker=str(data["asker"]),
            location_asked=None if location is None else str(location),
            reference=str(data["reference"]),
            answer=str(data["answer"]),
            passages=tuple(Passage.from_json(p) for p in data["passages"]),
        )


def _escape(text: str) -> str:
    """Untrusted text can't open or close a tag: angle brackets become entities."""
    return text.replace("<", "&lt;").replace(">", "&gt;")


def _attribute(text: str) -> str:
    return _escape(text).replace('"', "&quot;")


def user_message(judge_input: JudgeInput) -> str:
    """The user turn: each input in its own tag. The question and the answer are untrusted, and the
    cited text is what the model claimed to quote, so all three are escaped."""
    parts = [f"<asker>{_escape(judge_input.asker)}</asker>"]
    if judge_input.location_asked is not None:
        parts.append(f"<location_asked>{_escape(judge_input.location_asked)}</location_asked>")
    parts += [
        f"<question>{_escape(judge_input.question)}</question>",
        f"<reference_answer>{_escape(judge_input.reference)}</reference_answer>",
        f"<answer>{_escape(judge_input.answer)}</answer>",
    ]
    if not judge_input.passages:
        parts.append("<cited_passages>The answer cites nothing.</cited_passages>")
    else:
        parts.append("<cited_passages>")
        for passage in judge_input.passages:
            parts.append(
                f'<passage marker="{passage.marker}" section="{_attribute(passage.section_id)}"'
                f' title="{_attribute(passage.title)}">'
            )
            parts.append(f"<cited_text>{_escape(passage.cited_text)}</cited_text>")
            if passage.section_text is not None:
                parts.append(f"<section_text>{_escape(passage.section_text)}</section_text>")
            parts.append("</passage>")
        parts.append("</cited_passages>")
    return "\n".join(parts)


def judge_api_kwargs(judge_input: JudgeInput, *, system: str | None = None) -> dict[str, Any]:
    """The keyword arguments for the judge's `client.messages.create`, as plain JSON-able data.

    Pure. The live caller sends exactly this and the recorder fingerprints exactly this, so a
    recorded call is the call that was sent."""
    return {
        "model": JUDGE_MODEL,
        "max_tokens": JUDGE_MAX_TOKENS,
        "output_config": {
            "effort": JUDGE_EFFORT,
            "format": {"type": "json_schema", "schema": copy.deepcopy(VERDICT_SCHEMA)},
        },
        "system": judge_system() if system is None else system,
        "messages": [{"role": "user", "content": user_message(judge_input)}],
    }


def reservation_usd(kwargs: Mapping[str, Any]) -> Decimal:
    """The most a judge call could cost: its full output allowance (`max_tokens`) plus an estimate
    of its input. The runner checks that this fits under the spend cap before each judge call."""
    characters = len(json.dumps(kwargs))
    estimate = Usage(
        input_tokens=-(-characters // CHARACTERS_PER_TOKEN),
        output_tokens=int(kwargs["max_tokens"]),
        cache_read_tokens=0,
        cache_write_tokens=0,
    )
    return cost_usd(JUDGE_MODEL, estimate)


def asker_line(company: SeedCompany, persona: str) -> str:
    """The asker in one line for the judge: name, employment type, and office."""
    person = next(p for p in company.people if p.persona_key == persona)
    place = next(loc for loc in company.locations if loc.id == person.location_id)
    return (
        f"{person.given_name} {person.family_name}, {person.employment_type}, works at the"
        f" {place.name} in {place.city}, {place.state}"
    )


def location_line(company: SeedCompany, code: str | None) -> str | None:
    if code is None:
        return None
    place = next(loc for loc in company.locations if loc.code == code)
    return f"the {place.name} in {place.city}, {place.state}"


# --- Building the input from a trace ----------------------------------------------------------

_RESULT_START = re.compile(r"\n(?=/handbook/)")
_RESULT = re.compile(r"/handbook/(?P<section>[^?\s|]+)\?passage=[^\s|]*\s\|\s(?P<rest>.*)", re.S)


def section_texts(tool_results: Iterable[Any]) -> dict[str, str]:
    """The handbook's text for each section the tools returned, by section ID.

    A search result is written into the tool result as `source | title | passages`, one result to a
    block (see run.py `_result_text`). A section that came back twice (two searches) is kept once.
    """
    found: dict[str, list[str]] = {}
    for result in tool_results:
        for block in _RESULT_START.split("\n" + result.text)[1:]:
            match = _RESULT.fullmatch(block.strip())
            if match is None:
                continue
            _title, _, passages = match.group("rest").partition(" | ")
            texts = found.setdefault(match.group("section"), [])
            if passages not in texts:
                texts.append(passages)
    return {section: " ".join(texts) for section, texts in found.items()}


def annotate_answer(answer: str, citations: Iterable[Mapping[str, Any]]) -> str:
    """The answer with `[n]` after the text each citation covers.

    A citation's offset counts UTF-16 code units (a browser's string index), so an emoji counts two.
    Markers at one offset keep their order. An offset past the end puts the marker at the end."""
    units = answer.encode("utf-16-le")
    ordered = sorted(enumerate(citations), key=lambda pair: (int(pair[1]["offsetUtf16"]), pair[0]))
    pieces: list[str] = []
    cursor = 0
    for _, citation in ordered:
        end = min(int(citation["offsetUtf16"]) * 2, len(units))
        if end > cursor:
            pieces.append(units[cursor:end].decode("utf-16-le", errors="replace"))
            cursor = end
        pieces.append(f"[{citation['marker']}]")
    pieces.append(units[cursor:].decode("utf-16-le", errors="replace"))
    return "".join(pieces)


def build_input(
    trace: Any, *, asker: str, reference: str, location_asked: str | None
) -> JudgeInput:
    """The judge's input for one traced answer: the answer with its citation markers, and the
    passages it cites with the handbook's text for each section."""
    sections = section_texts(trace.tool_results)
    passages: dict[int, Passage] = {}
    # A marker can be cited more than once, each time for different words. The judge sees all of
    # them, each once, in the order they were cited.
    cited: dict[int, list[str]] = {}
    for citation in trace.citations:
        marker = int(citation["marker"])
        texts = cited.setdefault(marker, [])
        if str(citation["citedText"]) not in texts:
            texts.append(str(citation["citedText"]))
        if marker not in passages:
            section = str(citation["sectionId"])
            passages[marker] = Passage(
                marker=marker,
                section_id=section,
                title=str(citation["title"]),
                cited_text="",
                section_text=sections.get(section),
            )
    for marker, passage in passages.items():
        passages[marker] = replace(passage, cited_text=CITED_TEXT_JOINER.join(cited[marker]))
    return JudgeInput(
        question=trace.question,
        asker=asker,
        location_asked=location_asked,
        reference=reference,
        answer=annotate_answer(trace.answer_text, trace.citations),
        passages=tuple(passages[marker] for marker in sorted(passages)),
    )


# --- Reading the answer -----------------------------------------------------------------------


@dataclass(frozen=True)
class JudgeResponse:
    """What the API returned, reduced to what is kept: the stop reason, the answer text, the usage,
    and the model that served it. This is what a recording holds."""

    stop_reason: str | None
    text: str
    usage: Usage
    served_by: str
    stop_details: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "stop_reason": self.stop_reason,
            "text": self.text,
            "usage": encode_usage(self.usage),
            "served_by": self.served_by,
            "stop_details": self.stop_details,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "JudgeResponse":
        return cls(
            stop_reason=data["stop_reason"],
            text=str(data["text"]),
            usage=decode_usage(data["usage"]),
            served_by=str(data["served_by"]),
            stop_details=data.get("stop_details"),
        )


def response_from_sdk(response: Any) -> JudgeResponse:
    """Reduce an SDK `Message`. The answer is every text block, found by type: the response can
    begin with thinking blocks. `cache_*` counts can be None, which is zero."""
    details = getattr(response, "stop_details", None)
    return JudgeResponse(
        stop_reason=response.stop_reason,
        text="".join(block.text for block in response.content if block.type == "text"),
        usage=usage_from_sdk(response.usage),
        served_by=response.model,
        stop_details=None if details is None else details.model_dump(mode="json"),
    )


@dataclass(frozen=True)
class Verdict:
    """The judge's yes or no for each rubric line, with its reasons."""

    lines: dict[str, bool]
    reasons: dict[str, str]

    @property
    def passed(self) -> bool:
        """An item passes only if every line is yes."""
        return all(self.lines.values())

    @property
    def uncited(self) -> bool:
        """The answer makes a policy claim with no citation. Counted on its own."""
        return not self.lines[UNCITED_KEY]

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(key for key, verdict in self.lines.items() if not verdict)

    def to_json(self) -> dict[str, Any]:
        return {"passed": self.passed, "lines": dict(self.lines), "reasons": dict(self.reasons)}


def uncited_claim_count(verdicts: Iterable[Verdict | None]) -> int:
    """The number of answers the judge found a policy claim without a citation in."""
    return sum(1 for verdict in verdicts if verdict is not None and verdict.uncited)


def parse_response(response: JudgeResponse) -> Verdict:
    """The verdict in a response, strictly. Raises `JudgeUnavailable` for a stop other than
    `end_turn`, text that is not JSON, or JSON that is not exactly the schema."""
    if response.stop_reason != "end_turn":
        raise JudgeUnavailable(
            f"the judge stopped with {response.stop_reason!r}, so there is no verdict"
        )
    try:
        data = json.loads(response.text)
    except ValueError:
        raise JudgeUnavailable("the judge's answer was not JSON") from None
    if not isinstance(data, dict) or set(data) != set(RUBRIC_KEYS):
        raise JudgeUnavailable("the judge's answer did not have exactly the six rubric lines")
    lines: dict[str, bool] = {}
    reasons: dict[str, str] = {}
    for key in RUBRIC_KEYS:
        line = data[key]
        if not isinstance(line, dict) or set(line) != {"verdict", "reason"}:
            raise JudgeUnavailable(f"the judge's line {key!r} did not have a verdict and a reason")
        if not isinstance(line["verdict"], bool) or not isinstance(line["reason"], str):
            raise JudgeUnavailable(f"the judge's line {key!r} had a wrong type")
        lines[key] = line["verdict"]
        reasons[key] = line["reason"]
    return Verdict(lines, reasons)


# --- The live call ----------------------------------------------------------------------------

JudgeCaller = Callable[[dict[str, Any]], Awaitable[JudgeResponse]]

# A status that says "try again later" rather than "this request is wrong".
_TRANSIENT_STATUSES = frozenset({408, 409, 429})


# The judge's wait for a reply. The answers' client reads for 90 seconds between stream events; the
# judge is one non-streaming call that thinks first, so nothing arrives until it is done, and 90
# seconds could cut off a slow answer. It is not streamed because the verdict is one small JSON
# object recorded whole, and `with_options` keeps the client's retries (two) and its other waits.
JUDGE_CONNECT_TIMEOUT_SECONDS = 10
JUDGE_READ_TIMEOUT_SECONDS = 300
JUDGE_WRITE_TIMEOUT_SECONDS = 30
JUDGE_POOL_TIMEOUT_SECONDS = 10


def anthropic_caller(client: AsyncAnthropic) -> JudgeCaller:
    """The live caller: one non-streaming Messages call with the request exactly as built.

    Errors are told apart by their SDK types. A connection error or timeout, a 408, 409, 429, or 5xx
    is `JudgeTransient`. Any other status is `JudgeFatal`. The SDK has already retried (the client's
    `max_retries`)."""

    waiting = client.with_options(
        timeout=Timeout(
            connect=JUDGE_CONNECT_TIMEOUT_SECONDS,
            read=JUDGE_READ_TIMEOUT_SECONDS,
            write=JUDGE_WRITE_TIMEOUT_SECONDS,
            pool=JUDGE_POOL_TIMEOUT_SECONDS,
        )
    )

    async def call(kwargs: dict[str, Any]) -> JudgeResponse:
        try:
            response = await waiting.messages.create(**kwargs)
        except APIConnectionError as error:
            raise JudgeTransient(
                f"the judge could not be reached ({type(error).__name__})"
            ) from error
        except APIStatusError as error:
            if isinstance(error, BadRequestError) and is_spend_limit(error.body):
                raise ConsoleSpendLimit from error
            status = error.status_code
            if status in _TRANSIENT_STATUSES or status >= 500:
                raise JudgeTransient(f"the judge's call failed (status {status})") from error
            raise JudgeFatal(f"the judge's request was refused (status {status})") from error
        except APIError as error:
            raise JudgeTransient(f"the judge's call failed ({type(error).__name__})") from error
        try:
            return response_from_sdk(response)
        except (AttributeError, TypeError) as error:
            # A 200 that is not a message at all (an error page): the SDK hands back raw text.
            raise JudgeTransient("the judge's response could not be read") from error

    return call


# --- The judge --------------------------------------------------------------------------------


@dataclass(frozen=True)
class JudgeOutcome:
    """One item's result: a verdict, or why there is none, and what the call cost."""

    item_id: str
    fingerprint: str
    verdict: Verdict | None
    unavailable: str | None
    cost_usd: Decimal
    usage: Usage | None
    # Whether this outcome came from a call made now, as opposed to a recording. A recording's
    # `cost_usd` is what the call cost when it was made, not money spent now.
    called: bool = True

    def to_json(self) -> dict[str, Any]:
        if self.verdict is not None:
            return self.verdict.to_json()
        return {"unavailable": self.unavailable}


def _outcome(item_id: str, key: str, response: JudgeResponse) -> JudgeOutcome:
    model = response.served_by if is_priced(response.served_by) else JUDGE_MODEL
    cost = cost_usd(model, response.usage)
    try:
        return JudgeOutcome(item_id, key, parse_response(response), None, cost, response.usage)
    except JudgeUnavailable as error:
        return JudgeOutcome(item_id, key, None, str(error), cost, response.usage)


class Prepared(NamedTuple):
    """A judge request built from an input: the API's keyword arguments, and their fingerprint."""

    kwargs: dict[str, Any]
    key: str


class Judge:
    """Judges answers from recordings first, and from the API for a request not recorded.

    With a `caller`, a request with no recording is sent, and the response is recorded into
    `store` unless `record` is False (the extra trials of a full run). With no caller it is a
    replay: a request with no recording raises `ReplayMiss`."""

    def __init__(
        self,
        *,
        store: FixtureStore,
        caller: JudgeCaller | None,
        record: bool = True,
        system: str | None = None,
    ) -> None:
        self.store = store
        self.caller = caller
        self.record = record
        self.system = system

    def prepare(self, judge_input: JudgeInput) -> Prepared:
        """The request for this input and its fingerprint. Built once, then handed to `recorded`,
        `judge`, and `reservation_usd`, which would each build it again."""
        kwargs = judge_api_kwargs(judge_input, system=self.system)
        return Prepared(kwargs, fingerprint("judge", kwargs))

    def _lookup(self, key: str) -> tuple[JudgeResponse | None, bool]:
        """The recorded response for this request, and whether a record is there but damaged. One
        way to find and read it, for `recorded` and `judge`."""
        record = self.store.get(key, 0)
        if record is None or record.kind != "judge" or record.result is None:
            return None, False
        try:
            return JudgeResponse.from_json(record.result), False
        except (KeyError, TypeError, ValueError):
            return None, True

    def recorded(
        self, judge_input: JudgeInput, prepared: Prepared | None = None
    ) -> JudgeOutcome | None:
        """The recorded outcome for this input, or None (also when the record is damaged). Never
        calls."""
        key = (prepared or self.prepare(judge_input)).key
        response, _ = self._lookup(key)
        return None if response is None else _outcome("", key, response)

    async def judge(
        self, item_id: str, judge_input: JudgeInput, prepared: Prepared | None = None
    ) -> JudgeOutcome:
        request = prepared or self.prepare(judge_input)
        key = request.key
        response, damaged = self._lookup(key)
        if response is not None:
            return replace(_outcome(item_id, key, response), called=False)
        if self.caller is None:
            what = "could not be read" if damaged else "is missing"
            raise ReplayMiss(
                f"item {item_id}: the recording for the judge's request {what}"
                f" (fingerprint {key[:12]}): {RE_RECORD_HINT}"
            )
        # A damaged record in a live run is called again as if missing, and recorded over.
        try:
            fresh = await self.caller(request.kwargs)
        except JudgeTransient as error:
            # Says nothing about the judge, so it is never recorded.
            return JudgeOutcome(item_id, key, None, str(error), Decimal(0), None)
        if self.record:
            self.store.put(
                Record(key, "judge", item_id, 0, result=fresh.to_json()), replace=damaged
            )
        return _outcome(item_id, key, fresh)
