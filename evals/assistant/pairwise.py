"""The fairness set's pairwise judge: two answers in, two verdicts out.

Each variant of a fairness group is compared with the group's first variant, in the same trial. The
judge says whether the two answers give the same substance (the same rules, figures, and advice for
the same situation) and whether either draws anything from who the asker is (name, religion, age,
origin, gender, or parent role) that the question and the handbook do not support. The rubric is
`evals/fairness/judge.md`, versioned on its first line (`FAIRNESS_JUDGE_VERSION`), like a prompt:
changing it invalidates the recorded calls.

It follows the main judge (judge.py) in everything that is not about the rubric: the same model
(`JUDGE_MODEL`, Sonnet 5.5) at the same effort, a closed JSON schema, no sampling parameters, no
`thinking`, no fallbacks, and the same untrusted-text rules (the questions and answers are escaped
and sit inside tags; the rubric tells the judge never to follow them). It reuses the main judge's
response type, caller, and errors, so the live call, the cost, and the failure handling are one
code path.

**The answer** is read strictly (`parse_response`): a stop other than `end_turn`, text that is not
JSON, or JSON that is not exactly the schema is "judge unavailable", counted and reported, never a
pass. **Recording** is the main judge's: the raw response is recorded in its own fixture file
(`judge-fairness.jsonl.gz`) by `fingerprint("judge", pairwise_api_kwargs(...))`; a refusal or a
cutoff is recorded; a transient failure never is; a fatal one stops the run.

Pure apart from the SDK client the live caller wraps. Run from apps/api.
"""

import copy
import json
import re
from dataclasses import dataclass, replace
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

from app.ai.pricing import Usage, cost_usd, is_priced
from app.ai.replay import RE_RECORD_HINT, FixtureStore, Record, ReplayMiss, fingerprint
from assistant.judge import (
    JUDGE_EFFORT,
    JUDGE_MAX_TOKENS,
    JUDGE_MODEL,
    JudgeCaller,
    JudgeResponse,
    JudgeTransient,
    JudgeUnavailable,
    Passage,
    Prepared,
    _attribute,
    _escape,
    build_input,
)
from assistant.judge import reservation_usd as reservation_usd  # the same rule: re-exported

FAIRNESS_JUDGE_MD_PATH = Path(__file__).resolve().parent.parent / "fairness" / "judge.md"

PAIRWISE_KEYS = ("sameSubstance", "identityAssumption", "reason")

# Closed, every property required, no length or range keywords (the API does not support them).
PAIRWISE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sameSubstance": {"type": "boolean"},
        "identityAssumption": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": list(PAIRWISE_KEYS),
    "additionalProperties": False,
}

_VERSION_LINE = re.compile(r"FAIRNESS_JUDGE_VERSION: (\S+)")


# --- The rubric -------------------------------------------------------------------------------


def pairwise_version(text: str | None = None) -> str:
    """The `FAIRNESS_JUDGE_VERSION` on the first line of the rubric (or of `text`)."""
    source = pairwise_system() if text is None else text
    match = _VERSION_LINE.fullmatch(source.splitlines()[0] if source else "")
    if match is None:
        raise ValueError(
            "the fairness judge.md must start with a line like `FAIRNESS_JUDGE_VERSION: 2026-11.1`"
        )
    return match.group(1)


@cache
def pairwise_system() -> str:
    """The pairwise judge's system prompt: fairness/judge.md as written, version line included, so
    that a new version always invalidates the recordings."""
    return FAIRNESS_JUDGE_MD_PATH.read_text(encoding="utf-8")


# --- What the judge reads ---------------------------------------------------------------------


@dataclass(frozen=True)
class PairSide:
    """One asker's side: who they are, what they asked, the answer with `[n]` markers where it
    cites, and the passages it cites."""

    asker: str
    question: str
    answer: str
    passages: tuple[Passage, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "asker": self.asker,
            "question": self.question,
            "answer": self.answer,
            "passages": [p.to_json() for p in self.passages],
        }


@dataclass(frozen=True)
class PairInput:
    """Everything the judge is given about one comparison: the group, what varies in it
    (`attribute`), the group's first variant, and the variant compared with it."""

    group: str
    attribute: str
    first: PairSide
    second: PairSide

    def to_json(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "attribute": self.attribute,
            "first": self.first.to_json(),
            "second": self.second.to_json(),
        }


def side_of(trace: Any, *, asker: str) -> PairSide:
    """A side built from a traced turn: the main judge's reading of the answer and its citations,
    so a marker and a passage mean the same to both judges."""
    built = build_input(trace, asker=asker, reference="", location_asked=None)
    return PairSide(asker, built.question, built.answer, built.passages)


def _side_message(tag: str, side: PairSide) -> list[str]:
    parts = [
        f"<{tag}>",
        f"<asker>{_escape(side.asker)}</asker>",
        f"<question>{_escape(side.question)}</question>",
        f"<answer>{_escape(side.answer)}</answer>",
    ]
    if not side.passages:
        parts.append("<cited_passages>The answer cites nothing.</cited_passages>")
    else:
        parts.append("<cited_passages>")
        for passage in side.passages:
            parts.append(
                f'<passage marker="{passage.marker}" section="{_attribute(passage.section_id)}"'
                f' title="{_attribute(passage.title)}">'
            )
            parts.append(f"<cited_text>{_escape(passage.cited_text)}</cited_text>")
            if passage.section_text is not None:
                parts.append(f"<section_text>{_escape(passage.section_text)}</section_text>")
            parts.append("</passage>")
        parts.append("</cited_passages>")
    parts.append(f"</{tag}>")
    return parts


def user_message(pair: PairInput) -> str:
    """The user turn: what varied, then each side in its own tag. The questions and answers are
    untrusted and the cited text is what the model claimed to quote, so all are escaped."""
    parts = [f"<varied>{_escape(pair.attribute)}</varied>"]
    parts += _side_message("first", pair.first)
    parts += _side_message("second", pair.second)
    return "\n".join(parts)


def pairwise_api_kwargs(pair: PairInput, *, system: str | None = None) -> dict[str, Any]:
    """The keyword arguments for the pairwise judge's `client.messages.create`, as plain JSON-able
    data. Pure: the live caller sends exactly this and the recorder fingerprints exactly this."""
    return {
        "model": JUDGE_MODEL,
        "max_tokens": JUDGE_MAX_TOKENS,
        "output_config": {
            "effort": JUDGE_EFFORT,
            "format": {"type": "json_schema", "schema": copy.deepcopy(PAIRWISE_SCHEMA)},
        },
        "system": pairwise_system() if system is None else system,
        "messages": [{"role": "user", "content": user_message(pair)}],
    }


# --- Reading the answer -----------------------------------------------------------------------


@dataclass(frozen=True)
class PairVerdict:
    """The judge's two yes or no answers and its reason."""

    same_substance: bool
    identity_assumption: bool
    reason: str

    def to_json(self) -> dict[str, Any]:
        return {
            "sameSubstance": self.same_substance,
            "identityAssumption": self.identity_assumption,
            "reason": self.reason,
        }


def parse_response(response: JudgeResponse) -> PairVerdict:
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
    if not isinstance(data, dict) or set(data) != set(PAIRWISE_KEYS):
        raise JudgeUnavailable(
            "the judge's answer did not have exactly sameSubstance, identityAssumption, and reason"
        )
    same, assumed, reason = data["sameSubstance"], data["identityAssumption"], data["reason"]
    if not (isinstance(same, bool) and isinstance(assumed, bool) and isinstance(reason, str)):
        raise JudgeUnavailable("the judge's answer had a wrong type")
    return PairVerdict(same, assumed, reason)


# --- The judge --------------------------------------------------------------------------------


@dataclass(frozen=True)
class PairOutcome:
    """One comparison's result: a verdict, or why there is none, and what the call cost."""

    item_id: str
    fingerprint: str
    verdict: PairVerdict | None
    unavailable: str | None
    cost_usd: Decimal
    usage: Usage | None
    # Whether this outcome came from a call made now, as opposed to a recording.
    called: bool = True

    def to_json(self) -> dict[str, Any]:
        if self.verdict is not None:
            return self.verdict.to_json()
        return {"unavailable": self.unavailable}


def _outcome(item_id: str, key: str, response: JudgeResponse) -> PairOutcome:
    model = response.served_by if is_priced(response.served_by) else JUDGE_MODEL
    cost = cost_usd(model, response.usage)
    try:
        return PairOutcome(item_id, key, parse_response(response), None, cost, response.usage)
    except JudgeUnavailable as error:
        return PairOutcome(item_id, key, None, str(error), cost, response.usage)


class PairwiseJudge:
    """Judges comparisons from recordings first, and from the API for a request not recorded.

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

    def prepare(self, pair: PairInput) -> Prepared:
        """The request for this comparison and its fingerprint."""
        kwargs = pairwise_api_kwargs(pair, system=self.system)
        return Prepared(kwargs, fingerprint("judge", kwargs))

    def _lookup(self, key: str) -> tuple[JudgeResponse | None, bool]:
        """The recorded response for this request, and whether a record is there but damaged."""
        record = self.store.get(key, 0)
        if record is None or record.kind != "judge" or record.result is None:
            return None, False
        try:
            return JudgeResponse.from_json(record.result), False
        except (KeyError, TypeError, ValueError):
            return None, True

    def recorded(self, pair: PairInput, prepared: Prepared | None = None) -> PairOutcome | None:
        """The recorded outcome for this comparison, or None. Never calls."""
        key = (prepared or self.prepare(pair)).key
        response, _ = self._lookup(key)
        return None if response is None else _outcome("", key, response)

    async def judge(
        self, item_id: str, pair: PairInput, prepared: Prepared | None = None
    ) -> PairOutcome:
        request = prepared or self.prepare(pair)
        key = request.key
        response, damaged = self._lookup(key)
        if response is not None:
            return replace(_outcome(item_id, key, response), called=False)
        if self.caller is None:
            what = "could not be read" if damaged else "is missing"
            raise ReplayMiss(
                f"item {item_id}: the recording for the pairwise judge's request {what}"
                f" (fingerprint {key[:12]}): {RE_RECORD_HINT}"
            )
        try:
            fresh = await self.caller(request.kwargs)
        except JudgeTransient as error:
            # Says nothing about the judge, so it is never recorded.
            return PairOutcome(item_id, key, None, str(error), Decimal(0), None)
        if self.record:
            self.store.put(
                Record(key, "judge", item_id, 0, result=fresh.to_json()), replace=damaged
            )
        return _outcome(item_id, key, fresh)
