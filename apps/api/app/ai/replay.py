"""Recorded replay for the offline evals (ADR 0010): the fixture file, the recorder, and the replay.

A live eval run wraps the real transport in `RecordingTransport`, which writes every request it
sees, with the response, into a `FixtureStore`. CI then runs the same items against
`ReplayTransport`, which looks each request up and returns what was recorded. No model is called, so
the graders, the loop, the tools, and the plumbing are tested on real output for free.

**The fingerprint.** There is no seed, and these models take no sampling settings, so the same
request does not give the same answer twice: replay must return a recording, never regenerate. A
recording is found by `fingerprint(kind, kwargs)`, the SHA-256 of the JSON of
`{"kind": kind, "request": kwargs}` with sorted keys, compact separators, and no ASCII escaping. The
kwargs are everything that affects a response and nothing else: `ModelRequest.to_api_kwargs()` for
the assistant model, `guard_api_kwargs()` for the guard. The `kind` is part of what is hashed so a
model call and a guard call (or a judge call) can never share a fingerprint, whatever they hold.

**The fixture file.** One gzip-compressed JSON Lines file per dataset, for example
`fixtures/redteam.jsonl.gz`, and a separate `judge.jsonl.gz` for the judge's calls, so a change to
the grader replays without the model. A line is `{"fingerprint", "kind", "item", ...}` plus
`"events"` (a model call, possibly with an `"error"` at the end of a stream that failed),
`"result"` (a guard or judge answer), or `"error"`. `item` is the eval item that first produced the
request. The first recording of a fingerprint wins, so a later trial of the same item never
replaces it. Saving sorts by fingerprint and writes a zero gzip timestamp, so an unchanged store
saves to identical bytes and the file diffs cleanly.

**A stream the loop closes on a canary.** When the model repeats the prompt's canary, the turn loop
stops reading, closes the stream, and ends in `prompt-leak`. That is model behavior, so it is
recorded: the events seen up to the close, marked `closed_early`, and replay gives the same events
and the same turn. The recorder does not look for the canary itself (the loop's rule spans calls,
and a copy of it could drift). It keeps a stream closed early, with no error, as a pending record,
and the harness, which knows how the turn ended, calls `settle`: after a `prompt-leak` the item's
last pending record is committed, and otherwise the pending ones are dropped and stay recording
gaps (a deadline, a cancel, the person leaving).

**A request made twice in one live run** (the guard sees only the question, so two items asking the
same thing share a request) is answered the second time from what the first time recorded, not by
a second call. Every item then runs on exactly the response that is saved. The same holds for a
recording that was in the store before the run: a live run starts from the committed files, so an
unchanged request gets its recording back and costs nothing, and only a new fingerprint is called.

**A miss** raises `ReplayMiss`. The loop and the guard would treat an unexpected error from the
transport as the model being unavailable (and the guard swallows every error, failing closed), which
would show up as a wrong answer instead of a missing recording. So the transport also lists each
miss in `misses` (a recording that can't be read is a miss too), and the eval harness calls
`raise_if_missed` after every item: the failure names the item and says to re-record.

This module imports no SDK (import-linter enforces it): the typed errors it records are
`app.ai.transport`'s.
"""

import copy
import dataclasses
import gzip
import hashlib
import json
import os
import tempfile
import time
from collections import Counter
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple, Self, get_args

from app.ai.case_summary import (
    Summarizer,
    SummaryAnswer,
    SummaryRefused,
    SummaryRequest,
    SummaryUnavailable,
    summary_api_kwargs,
)
from app.ai.pricing import IterationUsage, Usage
from app.ai.transport import (
    Finished,
    GuardRequest,
    GuardResult,
    GuardUnavailable,
    InvalidToolInput,
    ModelEvent,
    ModelRequest,
    ModelUnavailable,
    SearchResultCitation,
    SpendLimitReached,
    StatusNote,
    TextBlockEnd,
    TextDelta,
    ToolCall,
    Transport,
    guard_api_kwargs,
)

RE_RECORD_HINT = "re-record with `make eval-live`"
UNNAMED_ITEM = "(no eval item)"

Kind = Literal["model", "guard", "judge", "summary"]
_KINDS: tuple[str, ...] = get_args(Kind)

# --- Fingerprints -----------------------------------------------------------------------------


def fingerprint(kind: Kind, kwargs: Mapping[str, Any]) -> str:
    """The SHA-256 (hex) of the request's JSON with sorted keys, tagged with what kind of call it
    is. Two requests that differ only in dict order share one; a model call and a guard call never
    do."""
    text = json.dumps(
        {"kind": kind, "request": kwargs},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def model_fingerprint(request: ModelRequest) -> str:
    return fingerprint("model", request.to_api_kwargs())


def guard_fingerprint(request: GuardRequest) -> str:
    return fingerprint("guard", guard_api_kwargs(request))


def summary_fingerprint(request: SummaryRequest) -> str:
    return fingerprint("summary", summary_api_kwargs(request))


# --- Serialization ----------------------------------------------------------------------------


def encode_usage(usage: Usage) -> dict[str, Any]:
    return dataclasses.asdict(usage)


def decode_usage(data: Mapping[str, Any]) -> Usage:
    return Usage(
        input_tokens=data["input_tokens"],
        output_tokens=data["output_tokens"],
        cache_read_tokens=data["cache_read_tokens"],
        cache_write_tokens=data["cache_write_tokens"],
    )


def _encode_citation(citation: SearchResultCitation) -> dict[str, Any]:
    return dataclasses.asdict(citation)


def _decode_citation(data: Mapping[str, Any]) -> SearchResultCitation:
    return SearchResultCitation(
        search_result_index=data["search_result_index"],
        start_block_index=data["start_block_index"],
        end_block_index=data["end_block_index"],
        source=data["source"],
        title=data["title"],
        cited_text=data["cited_text"],
    )


def _encode_finished(event: Finished) -> dict[str, Any]:
    # Copies: the loop keeps the message and may change it after the recorder has seen it.
    return {
        "message": copy.deepcopy(event.message),
        "stop_reason": event.stop_reason,
        "stop_details": copy.deepcopy(event.stop_details),
        "usage": encode_usage(event.usage),
        "iterations": [
            {"model": item.model, "usage": encode_usage(item.usage)} for item in event.iterations
        ],
        "served_by": event.served_by,
        "fell_back": event.fell_back,
    }


def _decode_finished(data: Mapping[str, Any]) -> Finished:
    # Deep copies, so replaying the same recording twice never hands two runs one shared dict.
    return Finished(
        message=copy.deepcopy(data["message"]),
        stop_reason=data["stop_reason"],
        stop_details=copy.deepcopy(data["stop_details"]),
        usage=decode_usage(data["usage"]),
        iterations=tuple(
            IterationUsage(item["model"], decode_usage(item["usage"]))
            for item in data["iterations"]
        ),
        served_by=data["served_by"],
        fell_back=data["fell_back"],
    )


# One row per `ModelEvent` type: its tag, how it is written, how it is read back.
_EVENT_CODECS: dict[type, tuple[str, Callable[[Any], dict[str, Any]], Callable[[Any], Any]]] = {
    StatusNote: (
        "status_note",
        lambda e: {"text": e.text},
        lambda d: StatusNote(d["text"]),
    ),
    TextDelta: (
        "text_delta",
        lambda e: {"text": e.text},
        lambda d: TextDelta(d["text"]),
    ),
    TextBlockEnd: (
        "text_block_end",
        lambda e: {"citations": [_encode_citation(c) for c in e.citations]},
        lambda d: TextBlockEnd(tuple(_decode_citation(c) for c in d["citations"])),
    ),
    ToolCall: (
        "tool_call",
        lambda e: {"id": e.id, "name": e.name, "input": copy.deepcopy(e.input)},
        lambda d: ToolCall(d["id"], d["name"], copy.deepcopy(d["input"])),
    ),
    Finished: ("finished", _encode_finished, _decode_finished),
}
_DECODERS = {tag: decode for tag, _, decode in _EVENT_CODECS.values()}

# A new `ModelEvent` type that is not written here would be recorded wrongly or not at all. Fail at
# import instead.
if set(_EVENT_CODECS) != set(get_args(ModelEvent)):
    raise RuntimeError("app.ai.replay does not serialize every ModelEvent type")


def encode_event(event: ModelEvent) -> dict[str, Any]:
    codec = _EVENT_CODECS.get(type(event))
    if codec is None:
        raise TypeError(f"cannot record an event of type {type(event).__name__}")
    tag, encode, _ = codec
    return {"type": tag, **encode(event)}


def decode_event(data: Mapping[str, Any]) -> ModelEvent:
    decode = _DECODERS.get(data.get("type", ""))
    if decode is None:
        raise ValueError(f"unknown event type {data.get('type')!r} in a recording")
    event: ModelEvent = decode(data)
    return event


def encode_guard_result(result: GuardResult) -> dict[str, Any]:
    return {
        "category": result.category,
        "kind": result.kind,
        "injection_suspected": result.injection_suspected,
        "usage": encode_usage(result.usage),
        "served_by": result.served_by,
    }


def decode_guard_result(data: Mapping[str, Any]) -> GuardResult:
    return GuardResult(
        category=data["category"],
        kind=data["kind"],
        injection_suspected=data["injection_suspected"],
        usage=decode_usage(data["usage"]),
        served_by=data["served_by"],
    )


def encode_summary_answer(answer: SummaryAnswer) -> dict[str, Any]:
    return {
        "text": answer.text,
        "model": answer.model,
        "prompt_version": answer.prompt_version,
        "usage": encode_usage(answer.usage),
    }


def decode_summary_answer(data: Mapping[str, Any]) -> SummaryAnswer:
    return SummaryAnswer(
        text=data["text"],
        model=data["model"],
        prompt_version=data["prompt_version"],
        usage=decode_usage(data["usage"]),
    )


# The errors a stream or the guard can raise that the loop handles by type. Anything else is a bug
# and is never recorded.
SUMMARY_ERRORS = (SummaryUnavailable, SummaryRefused)
RECORDED_ERRORS = (
    ModelUnavailable,
    SpendLimitReached,
    InvalidToolInput,
    GuardUnavailable,
    *SUMMARY_ERRORS,
)


def is_transient(error: Exception) -> bool:
    """A failure that says nothing about how the model behaves, so it is never recorded: it would
    replay an outage forever. `InvalidToolInput` and a guard failure that carries usage (the model
    did answer, unusably) are model behavior."""
    if isinstance(error, GuardUnavailable | SummaryUnavailable | SummaryRefused):
        return error.usage is None
    return isinstance(error, ModelUnavailable | SpendLimitReached)


def encode_error(error: Exception) -> dict[str, Any]:
    message = str(error)
    if isinstance(error, ModelUnavailable):
        return {
            "type": "model_unavailable",
            "message": message,
            "status_code": error.status_code,
            "request_id": error.request_id,
        }
    if isinstance(error, SpendLimitReached):
        return {"type": "spend_limit_reached", "message": message}
    if isinstance(error, InvalidToolInput):
        return {"type": "invalid_tool_input", "message": message}
    if isinstance(error, GuardUnavailable):
        return {
            "type": "guard_unavailable",
            "message": message,
            "usage": None if error.usage is None else encode_usage(error.usage),
        }
    if isinstance(error, SummaryUnavailable | SummaryRefused):
        usage = error.usage
        return {
            "type": "summary_unavailable"
            if isinstance(error, SummaryUnavailable)
            else "summary_refused",
            "message": message,
            "usage": None if usage is None else encode_usage(usage),
        }
    raise TypeError(f"cannot record an error of type {type(error).__name__}")


def decode_error(data: Mapping[str, Any]) -> Exception:
    kind = data.get("type")
    if kind == "model_unavailable":
        return ModelUnavailable(
            data["message"], status_code=data["status_code"], request_id=data["request_id"]
        )
    if kind == "spend_limit_reached":
        return SpendLimitReached(data["message"])
    if kind == "invalid_tool_input":
        return InvalidToolInput(data["message"])
    if kind == "guard_unavailable":
        usage = data["usage"]
        return GuardUnavailable(
            data["message"], usage=None if usage is None else decode_usage(usage)
        )
    if kind in {"summary_unavailable", "summary_refused"}:
        usage = data["usage"]
        decoded = None if usage is None else decode_usage(usage)
        summary_error = SummaryUnavailable if kind == "summary_unavailable" else SummaryRefused
        return summary_error(data["message"], usage=decoded)
    raise ValueError(f"unknown error type {kind!r} in a recording")


# --- The fixture file -------------------------------------------------------------------------


@dataclass(frozen=True)
class Record:
    """One recorded call, already in its JSON form. Only the keys that are set are written."""

    fingerprint: str
    kind: Kind
    # The eval item that first produced this request.
    item: str
    # Which call of this fingerprint within an item run: 0 for the first, 1 for a re-issue.
    occurrence: int = 0
    events: tuple[dict[str, Any], ...] | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    # The loop closed the stream after these events, because the model repeated the prompt's
    # canary. The recording ends there; replay yields the events and no more.
    closed_early: bool = False

    def to_json(self) -> dict[str, Any]:
        line: dict[str, Any] = {
            "fingerprint": self.fingerprint,
            "kind": self.kind,
            "item": self.item,
            "occurrence": self.occurrence,
        }
        if self.events is not None:
            line["events"] = list(self.events)
        if self.result is not None:
            line["result"] = self.result
        if self.error is not None:
            line["error"] = self.error
        if self.closed_early:
            line["closed_early"] = True
        return line

    @classmethod
    def from_json(cls, data: Any) -> Self:
        if not isinstance(data, dict):
            raise ValueError("not an object")
        fingerprint_, kind, item = data.get("fingerprint"), data.get("kind"), data.get("item")
        if not isinstance(fingerprint_, str) or not fingerprint_:
            raise ValueError("no fingerprint")
        if kind not in _KINDS:
            raise ValueError(f"unknown kind {kind!r}")
        if not isinstance(item, str):
            raise ValueError("no item")
        occurrence = data.get("occurrence", 0)
        if isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence < 0:
            raise ValueError("occurrence must be a whole number from 0")
        events, result, error = data.get("events"), data.get("result"), data.get("error")
        if events is not None and not (
            isinstance(events, list) and all(isinstance(e, dict) for e in events)
        ):
            raise ValueError("events must be a list of objects")
        if result is not None and not isinstance(result, dict):
            raise ValueError("result must be an object")
        if error is not None and not isinstance(error, dict):
            raise ValueError("error must be an object")
        if events is None and result is None and error is None:
            raise ValueError("no events, result, or error")
        closed_early = data.get("closed_early", False)
        if not isinstance(closed_early, bool):
            raise ValueError("closed_early must be true or false")
        return cls(
            fingerprint=fingerprint_,
            kind=kind,
            item=item,
            occurrence=occurrence,
            events=None if events is None else tuple(events),
            result=result,
            error=error,
            closed_early=closed_early,
        )


class FixtureStore:
    """The recordings of one dataset, in memory and as one gzip JSON Lines file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._records: dict[tuple[str, int], Record] = {}
        # How many occurrences of each fingerprint are recorded, kept up to date by `put`.
        self._counts: Counter[str] = Counter()

    @classmethod
    def load(cls, path: Path) -> Self:
        """The store in `path`, or an empty one when the file doesn't exist yet. The first line for
        a fingerprint and occurrence wins. A bad line is a `ValueError` naming the file and line."""
        store = cls(path)
        if not path.exists():
            return store
        text = gzip.decompress(path.read_bytes()).decode("utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = Record.from_json(json.loads(line))
            except ValueError as error:
                raise ValueError(f"{path}:{number}: not a valid recording ({error})") from None
            store.put(record)
        return store

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, key: str) -> bool:
        """Whether any call of this fingerprint is recorded."""
        return self._counts[key] > 0

    def count(self, key: str) -> int:
        """How many calls of this fingerprint are recorded (its occurrences)."""
        return self._counts[key]

    def get(self, key: str, occurrence: int = 0) -> Record | None:
        return self._records.get((key, occurrence))

    def records(self) -> list[Record]:
        """Every recording, sorted by fingerprint and occurrence (the order they are saved in)."""
        return [self._records[key] for key in sorted(self._records)]

    def put(self, record: Record, *, replace: bool = False) -> bool:
        """Add a recording. The first one for a fingerprint and occurrence wins: False means this
        one was ignored. With `replace`, it takes the place of what is there (a damaged record
        being recorded again)."""
        key = (record.fingerprint, record.occurrence)
        if key in self._records:
            if not replace:
                return False
            self._records[key] = record
            return True
        self._records[key] = record
        self._counts[record.fingerprint] += 1
        return True

    def save(self) -> None:
        """Write the file, sorted and with a zero timestamp, so an unchanged store gives the same
        bytes. It goes to a temporary file first, so a crash can't leave half a fixture."""
        lines = "".join(
            json.dumps(record.to_json(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
            for record in self.records()
        )
        data = gzip.compress(lines.encode("utf-8"), compresslevel=9, mtime=0)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # A dotted `.tmp` file in the same folder, which .gitignore covers: a crash between the
        # write and the replace must not leave something `git add` would pick up.
        handle, name = tempfile.mkstemp(
            dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
        )
        temporary = Path(name)
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(data)
            os.replace(temporary, self.path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise


# --- The recorder -----------------------------------------------------------------------------


class Skipped(NamedTuple):
    """A call the recorder saw but wrote no record for, and why."""

    item: str
    kind: Kind
    fingerprint: str
    occurrence: int
    reason: str


class _PerItem:
    """Counts each fingerprint's calls within one item run. Setting the item starts the count over,
    so every item and every trial of it numbers its calls from 0."""

    def __init__(self) -> None:
        self._item = UNNAMED_ITEM
        self._calls: Counter[str] = Counter()

    @property
    def current_item(self) -> str:
        return self._item

    @current_item.setter
    def current_item(self, item: str) -> None:
        self._item = item
        self._calls.clear()
        self._item_changed()

    def _item_changed(self) -> None:
        """For a subclass that keeps more per item."""

    def _next_occurrence(self, key: str) -> int:
        occurrence = self._calls[key]
        self._calls[key] += 1
        return occurrence


class ReplayMiss(Exception):  # noqa: N818
    """A request with no (readable) recording. It is deliberately none of the errors the loop
    handles."""


class Miss(NamedTuple):
    item: str
    kind: Kind
    fingerprint: str
    reason: str


class _MissLog(_PerItem):
    """What a transport that answers from recordings does when it can't: it raises `ReplayMiss` and
    also lists the miss, because the guard and the loop absorb unexpected errors. The harness calls
    `raise_if_missed` after every item."""

    def __init__(self) -> None:
        super().__init__()
        self.misses: list[Miss] = []

    def _unreadable(self, kind: Kind, key: str, cause: Exception) -> ReplayMiss:
        reason = f"the recording for this {kind} request could not be read ({type(cause).__name__})"
        return self._miss(kind, key, reason)

    def _miss(self, kind: Kind, key: str, reason: str) -> ReplayMiss:
        self.misses.append(Miss(self.current_item, kind, key, reason))
        return ReplayMiss(
            f"item {self.current_item}: {reason} (fingerprint {key[:12]}): {RE_RECORD_HINT}"
        )

    async def _serve_model(self, record: Record, key: str) -> AsyncIterator[ModelEvent]:
        """The events of a recorded model call, then its recorded end. One path for the replay and
        for a recorder answering from the store, so they can't drift.

        The whole record is read before the first event is handed out, so a bad one fails the call
        before the loop has seen part of it. A record that is not a finished call is a miss: one
        with no events, or whose events do not end with `finished`, unless it ended in a typed
        error or the loop closed it at a prompt leak. After a closed record's events, the loop must
        not read on."""
        try:
            events = [decode_event(raw) for raw in record.events or ()]
            error = None if record.error is None else decode_error(record.error)
        except (ValueError, KeyError, TypeError) as cause:
            raise self._unreadable("model", key, cause) from None
        ends_finished = bool(events) and isinstance(events[-1], Finished)
        if not (record.closed_early or error is not None or ends_finished):
            raise self._miss("model", key, "the recording has no finished event")
        for event in events:
            yield event
        if record.closed_early:
            # The loop stopped reading here when it was recorded. Reading on means it behaves
            # differently now, and the recording can't say what the model would have sent next.
            raise self._miss(
                "model",
                key,
                "the recording was closed by the loop at a prompt leak, but the loop read on",
            )
        if error is not None:
            raise error

    def _serve_guard(self, record: Record, key: str) -> GuardResult:
        """A recorded guard call's answer, or its recorded error. See `_serve_model`."""
        try:
            if record.error is not None:
                error = decode_error(record.error)
            elif record.result is None:
                raise ValueError("no guard answer")
            else:
                return decode_guard_result(record.result)
        except (ValueError, KeyError, TypeError) as cause:
            raise self._unreadable("guard", key, cause) from None
        raise error

    def _serve_summary(self, record: Record, key: str) -> SummaryAnswer:
        """A recorded summary call's answer, or its recorded error. See `_serve_model`."""
        try:
            if record.error is not None:
                error = decode_error(record.error)
            elif record.result is None:
                raise ValueError("no summary answer")
            else:
                return decode_summary_answer(record.result)
        except (ValueError, KeyError, TypeError) as cause:
            raise self._unreadable("summary", key, cause) from None
        raise error

    def clear_misses(self) -> None:
        self.misses.clear()

    def raise_if_missed(self) -> None:
        """Raise `ReplayMiss` naming each item that missed, and why, if any did."""
        if not self.misses:
            return
        found = "; ".join(f"{m.item} ({m.kind}: {m.reason})" for m in self.misses)
        raise ReplayMiss(
            f"{len(self.misses)} request(s) failed to replay: {found}: {RE_RECORD_HINT}"
        )


class _Recorder(_MissLog):
    """What a recorder keeps beside the real thing it wraps: the store, the clock, the calls it did
    not record (`skipped`), and the time of each live call (`timings`)."""

    def __init__(
        self,
        inner: Any,
        store: FixtureStore,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self.inner = inner
        self.store = store
        self._clock = clock
        self.skipped: list[Skipped] = []
        # (kind, fingerprint, occurrence) -> milliseconds, for the live calls of the current item.
        self.timings: dict[tuple[Kind, str, int], int] = {}

    def _item_changed(self) -> None:
        self.skipped = []
        self.misses = []
        self.timings = {}

    def _timed(self, kind: Kind, key: str, occurrence: int, started: float) -> None:
        self.timings[(kind, key, occurrence)] = round((self._clock() - started) * 1000)

    def _own(self, key: str, occurrence: int, kind: Kind) -> Record | None:
        """The recording already in the store for this call, if there is one."""
        record = self.store.get(key, occurrence)
        return record if record is not None and record.kind == kind else None

    def _skip(self, key: str, kind: Kind, occurrence: int, reason: str) -> None:
        self.skipped.append(Skipped(self.current_item, kind, key, occurrence, reason))

    def _put(self, record: Record) -> None:
        self.store.put(record)

    def _record(
        self,
        key: str,
        kind: Kind,
        occurrence: int,
        *,
        events: tuple[dict[str, Any], ...] | None = None,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        self._put(
            Record(
                fingerprint=key,
                kind=kind,
                item=self.current_item,
                occurrence=occurrence,
                events=events,
                result=result,
                error=error,
            )
        )


class RecordingTransport(_Recorder):
    """Wraps a real transport for a live eval run: everything passes through unchanged, and each
    request is recorded with its response, or with the typed error that ended it. A request that
    is already in the store, whether this run recorded it (a later item asking the same) or it was
    there before the run (a committed recording), is answered from that recording and the real
    transport is not called. A run that wants every request called live again gives it an empty
    store.

    Each call it makes live (the real transport answered) is timed with a monotonic clock, in
    `timings`, until the next item is set: a model call from the call to the end of its stream, a
    guard call from the call to its answer. A call answered from a recording has no entry, and nor
    does a call that ended in an error, since no usage is reported for it.

    Set `current_item` to the eval item being run before each item. A call that ends without a
    record (a transient failure, an untyped error, or a stream closed early) is listed in `skipped`
    with the reason, until the next item is set. Call `settle` after each item (see the module's
    note on a stream the loop closes on a canary)."""

    def __init__(
        self,
        inner: Transport,
        store: FixtureStore,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(inner, store, clock=clock)
        self.inner: Transport = inner
        # Streams the consumer closed early with no error, awaiting the turn's outcome.
        self._pending: list[Record] = []

    def _item_changed(self) -> None:
        super()._item_changed()
        self._pending = []

    @property
    def has_pending_close(self) -> bool:
        return bool(self._pending)

    def settle(self, *, prompt_leak: bool) -> None:
        """The item's turn is over. If it ended in `prompt-leak`, the loop closed its last pending
        stream on purpose: record that stream as it was seen. Otherwise a stream closed early says
        nothing about the model and stays a gap. Either way nothing is pending afterward."""
        pending, self._pending = self._pending, []
        if prompt_leak and pending:
            self._put(pending[-1])

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        key = model_fingerprint(request)
        occurrence = self._next_occurrence(key)
        recorded = self._own(key, occurrence, "model")
        if recorded is not None:
            async for event in self._serve_model(recorded, key):
                yield event
            return
        captured: list[dict[str, Any]] = []
        started = self._clock()
        events = self.inner.stream(request)
        # Replaced when the call ends in a way that was recorded. GeneratorExit and cancellation
        # are not Exceptions, so a stream closed early falls through to this reason.
        unrecorded: str | None = "stream closed early"
        try:
            async for event in events:
                captured.append(encode_event(event))
                yield event
            self._timed("model", key, occurrence, started)
            self._record(key, "model", occurrence, events=tuple(captured))
            unrecorded = None
        except GeneratorExit:
            # The consumer closed the stream between two events. Whether that was the loop stopping
            # a canary leak is decided by how the turn ends (`settle`), so it waits as pending.
            self._pending.append(
                Record(
                    key,
                    "model",
                    self.current_item,
                    occurrence,
                    events=tuple(captured),
                    closed_early=True,
                )
            )
            raise
        except RECORDED_ERRORS as error:
            if is_transient(error):
                unrecorded = f"transient error ({type(error).__name__}), not recorded"
            else:
                self._record(
                    key,
                    "model",
                    occurrence,
                    events=tuple(captured),
                    error=encode_error(error),
                )
                unrecorded = None
            raise
        except Exception as error:
            unrecorded = f"ended by {type(error).__name__}, not recorded"
            raise
        except BaseException:
            # A cancel or a deadline cut the call off. Only the reason is set here.
            unrecorded = "canceled (deadline or stop)"
            raise
        finally:
            if unrecorded is not None:
                self._skip(key, "model", occurrence, unrecorded)
            # The loop closes the stream it was handed, which is this one, so close the real one
            # too. Transports hand back an async generator, which has `aclose`.
            close = getattr(events, "aclose", None)
            if close is not None:
                await close()

    async def classify(self, request: GuardRequest) -> GuardResult:
        key = guard_fingerprint(request)
        occurrence = self._next_occurrence(key)
        recorded = self._own(key, occurrence, "guard")
        if recorded is not None:
            return self._serve_guard(recorded, key)
        started = self._clock()
        try:
            result = await self.inner.classify(request)
        except RECORDED_ERRORS as error:
            if is_transient(error):
                reason = f"transient error ({type(error).__name__}), not recorded"
                self._skip(key, "guard", occurrence, reason)
            else:
                self._record(key, "guard", occurrence, error=encode_error(error))
            raise
        except BaseException as error:
            reason = f"ended by {type(error).__name__}, not recorded"
            self._skip(key, "guard", occurrence, reason)
            raise
        self._timed("guard", key, occurrence, started)
        self._record(key, "guard", occurrence, result=encode_guard_result(result))
        return result


class RecordingSummarizer(_Recorder):
    """Wraps the real summarizer for a live eval run, like `RecordingTransport`: a request already
    in the store is answered from it, a new one is called and recorded with its answer or the typed
    summary error that ended it. A failure that reports no usage, a timeout, or an error the
    recorder does not know says nothing about the model and is listed in `skipped`, not recorded."""

    def __init__(
        self,
        inner: Summarizer,
        store: FixtureStore,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(inner, store, clock=clock)
        self.inner: Summarizer = inner
        # How many requests went to the real summarizer (not answered from a recording).
        self.live_calls = 0

    async def summarize(self, request: SummaryRequest) -> SummaryAnswer:
        key = summary_fingerprint(request)
        occurrence = self._next_occurrence(key)
        recorded = self._own(key, occurrence, "summary")
        if recorded is not None:
            return self._serve_summary(recorded, key)
        started = self._clock()
        self.live_calls += 1
        try:
            answer = await self.inner.summarize(request)
        except SUMMARY_ERRORS as error:
            if error.usage is None:
                reason = f"transient error ({type(error).__name__}), not recorded"
                self._skip(key, "summary", occurrence, reason)
            else:
                self._record(key, "summary", occurrence, error=encode_error(error))
            raise
        except BaseException as error:
            reason = f"ended by {type(error).__name__}, not recorded"
            self._skip(key, "summary", occurrence, reason)
            raise
        self._timed("summary", key, occurrence, started)
        self._record(key, "summary", occurrence, result=encode_summary_answer(answer))
        return answer


# --- The replay -------------------------------------------------------------------------------


class ReplayTransport(_MissLog):
    """Answers from a `FixtureStore` and never calls a model. A request that wasn't recorded, or
    whose recording can't be read, raises `ReplayMiss` and is also added to `misses`, because the
    guard and the loop absorb unexpected errors: the harness calls `raise_if_missed` after every
    item."""

    def __init__(self, store: FixtureStore) -> None:
        super().__init__()
        self.store = store

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        key = model_fingerprint(request)
        record = self._find(key, "model")
        async for event in self._serve_model(record, key):
            yield event

    async def classify(self, request: GuardRequest) -> GuardResult:
        key = guard_fingerprint(request)
        return self._serve_guard(self._find(key, "guard"), key)

    def _find(self, key: str, kind: Kind) -> Record:
        occurrence = self._next_occurrence(key)
        record = self.store.get(key, occurrence)
        if record is not None and record.kind == kind:
            return record
        recorded = self.store.count(key)
        if recorded == 0:
            reason = f"no recording for this {kind} request"
        else:
            reason = (
                f"no recording for occurrence {occurrence} of this {kind} request"
                f" ({recorded} recorded)"
            )
        raise self._miss(kind, key, reason)


class ReplaySummarizer(_MissLog):
    """Answers the case summary from a `FixtureStore` and never calls a model, like
    `ReplayTransport`. A request with no recording is a `ReplayMiss`."""

    def __init__(self, store: FixtureStore) -> None:
        super().__init__()
        self.store = store

    async def summarize(self, request: SummaryRequest) -> SummaryAnswer:
        key = summary_fingerprint(request)
        occurrence = self._next_occurrence(key)
        record = self.store.get(key, occurrence)
        if record is None or record.kind != "summary":
            raise self._miss("summary", key, "no recording for this summary request")
        return self._serve_summary(record, key)
