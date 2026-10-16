"""The replay transport and the recorder (ADR 0010): fingerprints, serialization, the fixture file.

Nothing here touches a database or the network. `ScriptedTransport` stands in for the real model
that a live run would record.
"""

import asyncio
import gzip
import hashlib
import json
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any, get_args

import pytest

from app.ai.guard import build_guard_request, screen
from app.ai.pricing import IterationUsage, Usage
from app.ai.replay import (
    RE_RECORD_HINT,
    FixtureStore,
    Record,
    RecordingTransport,
    ReplayMiss,
    ReplayTransport,
    decode_error,
    decode_event,
    decode_guard_result,
    encode_error,
    encode_event,
    encode_guard_result,
    fingerprint,
    guard_fingerprint,
    model_fingerprint,
)
from app.ai.scripted import ScriptedTransport
from app.ai.transport import (
    FALLBACK_BETA,
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
    guard_api_kwargs,
)

OPUS = "claude-opus-5-5"
HAIKU = "claude-haiku-5-5"
USAGE = Usage(input_tokens=1200, output_tokens=80, cache_read_tokens=500, cache_write_tokens=30)


def a_request(question: str = "How much paid sick leave do I get?", **changes: Any) -> ModelRequest:
    request = ModelRequest(
        model=OPUS,
        system=({"type": "text", "text": "You are the assistant."},),
        tools=({"name": "search_handbook", "description": "Search.", "input_schema": {}},),
        messages=({"role": "user", "content": question},),
        effort="low",
        max_tokens=8000,
        betas=(FALLBACK_BETA,),
    )
    return replace(request, **changes)


async def collect(stream: AsyncIterator[ModelEvent]) -> list[ModelEvent]:
    return [event async for event in stream]


async def collect_until_error[E: Exception](
    stream: AsyncIterator[ModelEvent], error_type: type[E]
) -> tuple[list[ModelEvent], E]:
    """The events a stream gave before it raised `error_type`, and the error."""
    seen: list[ModelEvent] = []
    try:
        async for event in stream:
            seen.append(event)
    except error_type as error:
        return seen, error
    raise AssertionError(f"the stream ended without {error_type.__name__}")


# --- The fingerprint --------------------------------------------------------------------------


def test_the_fingerprint_is_the_sha256_of_the_sorted_key_json() -> None:
    kwargs = {"b": [1, 2], "a": {"z": "é", "y": None}}
    expected = hashlib.sha256(
        json.dumps(
            {"kind": "model", "request": kwargs},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    assert fingerprint("model", kwargs) == expected


def test_a_model_request_is_fingerprinted_from_its_api_kwargs() -> None:
    request = a_request()

    assert model_fingerprint(request) == fingerprint("model", request.to_api_kwargs())


def test_requests_that_differ_only_in_dict_order_share_a_fingerprint() -> None:
    one = {"model": "m", "output_config": {"effort": "low", "format": {"a": 1, "b": 2}}}
    other = {"output_config": {"format": {"b": 2, "a": 1}, "effort": "low"}, "model": "m"}

    assert fingerprint("model", one) == fingerprint("model", other)


def test_a_change_to_the_request_changes_the_fingerprint() -> None:
    assert model_fingerprint(a_request()) != model_fingerprint(a_request("Another question?"))
    assert model_fingerprint(a_request()) != model_fingerprint(a_request(effort="medium"))
    assert model_fingerprint(a_request()) != model_fingerprint(a_request(max_tokens=100))


def test_a_model_call_and_a_guard_call_can_not_collide() -> None:
    kwargs = {"model": HAIKU, "messages": []}

    assert fingerprint("model", kwargs) != fingerprint("guard", kwargs)
    assert fingerprint("guard", kwargs) != fingerprint("judge", kwargs)


def test_a_guard_call_is_fingerprinted_from_the_kwargs_it_sends() -> None:
    request = build_guard_request("Hello", None)

    assert guard_fingerprint(request) == fingerprint("guard", guard_api_kwargs(request))


def test_the_guard_kwargs_ask_for_low_effort_structured_output() -> None:
    kwargs = guard_api_kwargs(build_guard_request("Hello", None))

    assert kwargs["model"] == HAIKU
    assert kwargs["output_config"]["effort"] == "low"
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert isinstance(kwargs["messages"], list)
    json.dumps(kwargs)  # plain JSON-able data, so it can be fingerprinted


# --- Serialization ----------------------------------------------------------------------------

CITATION = SearchResultCitation(2, 0, 1, "4.3", "Sick leave", "Employees get 40 hours.")
FINISHED = Finished(
    message={"role": "assistant", "content": [{"type": "text", "text": "Hi", "citations": []}]},
    stop_reason="end_turn",
    stop_details={"type": "refusal", "category": "general_harms"},
    usage=USAGE,
    iterations=(
        IterationUsage(OPUS, Usage(10, 0, 0, 0)),
        IterationUsage("claude-opus-4-8", USAGE),
    ),
    served_by="claude-opus-4-8",
    fell_back=True,
)

EXAMPLE_EVENTS: list[ModelEvent] = [
    StatusNote("Looking up the sick leave policy"),
    TextDelta("You get "),
    TextBlockEnd(()),
    TextBlockEnd((CITATION, replace(CITATION, title=None, search_result_index=0))),
    ToolCall("toolu_1", "search_handbook", {"query": "sick leave", "nested": {"a": [1, None]}}),
    FINISHED,
    replace(FINISHED, stop_details=None, fell_back=False, iterations=()),
]


def test_every_model_event_type_has_an_example() -> None:
    """A new `ModelEvent` type without an example here fails this test, so it can't be added
    without being serialized and round-tripped."""
    assert {type(event) for event in EXAMPLE_EVENTS} == set(get_args(ModelEvent))


@pytest.mark.parametrize("event", EXAMPLE_EVENTS, ids=lambda e: type(e).__name__)
def test_a_model_event_round_trips_through_json(event: ModelEvent) -> None:
    encoded = json.loads(json.dumps(encode_event(event)))

    assert isinstance(encoded["type"], str)
    assert decode_event(encoded) == event


def test_an_unknown_event_type_is_refused_when_decoding() -> None:
    with pytest.raises(ValueError, match="unknown"):
        decode_event({"type": "from_the_future"})


def test_an_event_of_an_unknown_class_is_refused_when_encoding() -> None:
    with pytest.raises(TypeError):
        encode_event("not an event")  # type: ignore[arg-type]


EXAMPLE_ERRORS: list[Exception] = [
    ModelUnavailable("down", status_code=529, request_id="req_1"),
    ModelUnavailable("down"),
    SpendLimitReached("limit"),
    InvalidToolInput("bad json"),
    GuardUnavailable("no answer"),
    GuardUnavailable("bad output", usage=USAGE),
]


@pytest.mark.parametrize("error", EXAMPLE_ERRORS, ids=lambda e: f"{type(e).__name__}-{e}")
def test_an_error_round_trips_through_json(error: Exception) -> None:
    decoded = decode_error(json.loads(json.dumps(encode_error(error))))

    assert type(decoded) is type(error)
    assert str(decoded) == str(error)
    assert vars(decoded) == vars(error)


def test_an_error_the_recorder_does_not_know_is_refused() -> None:
    with pytest.raises(TypeError):
        encode_error(RuntimeError("boom"))


def test_a_guard_result_round_trips_through_json() -> None:
    result = GuardResult("sensitive", "pay", True, USAGE, HAIKU)

    assert decode_guard_result(json.loads(json.dumps(encode_guard_result(result)))) == result
    nothing = GuardResult("ordinary", None, False, USAGE, HAIKU)
    assert decode_guard_result(json.loads(json.dumps(encode_guard_result(nothing)))) == nothing


# --- Recording and replaying ------------------------------------------------------------------


def a_store(tmp_path: Path, name: str = "redteam") -> FixtureStore:
    return FixtureStore(tmp_path / f"{name}.jsonl.gz")


async def test_a_recorded_run_replays_the_same_events(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    recorder = RecordingTransport(ScriptedTransport(), store)
    recorder.current_item = "qa-001"
    request = a_request()

    seen = await collect(recorder.stream(request))

    assert isinstance(seen[-1], Finished)
    replay = ReplayTransport(store)
    assert await collect(replay.stream(request)) == seen
    assert replay.misses == []


async def test_the_recorder_passes_the_events_through_unchanged(tmp_path: Path) -> None:
    request = a_request()
    plain = await collect(ScriptedTransport().stream(request))
    recorder = RecordingTransport(ScriptedTransport(), a_store(tmp_path))

    assert await collect(recorder.stream(request)) == plain


async def test_a_recording_names_the_item_that_first_produced_it(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    recorder = RecordingTransport(ScriptedTransport(), store)
    recorder.current_item = "qa-001"
    await collect(recorder.stream(a_request()))
    recorder.current_item = "qa-002"
    await collect(recorder.stream(a_request()))  # the same request again, from another item

    (record,) = store.records()
    assert record.item == "qa-001"
    assert record.kind == "model"
    assert record.fingerprint == model_fingerprint(a_request())


class Flaky:
    """An inner transport whose first model call writes some text and then raises `error`, and whose
    later calls (for the very same request) answer normally: the loop's re-issue after a broken
    tool input looks like this."""

    def __init__(self, error: Exception | None = None, *, first_text: bool = True) -> None:
        self.error = error or InvalidToolInput("not JSON")
        self.first_text = first_text
        self.calls = 0
        self._scripted = ScriptedTransport()

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.calls += 1
        if self.calls == 1:
            if self.first_text:
                yield TextDelta("partial ")
            raise self.error
        async for event in self._scripted.stream(request):
            yield event

    async def classify(self, request: GuardRequest) -> GuardResult:
        return await self._scripted.classify(request)


async def test_a_recorded_invalid_tool_input_replays_as_the_same_error(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    request = a_request()
    recorder = RecordingTransport(Flaky(), store)
    seen, recorded = await collect_until_error(recorder.stream(request), InvalidToolInput)
    assert seen == [TextDelta("partial ")]

    replayed, raised = await collect_until_error(
        ReplayTransport(store).stream(request), InvalidToolInput
    )

    assert replayed == seen
    assert str(raised) == str(recorded)


async def test_the_same_request_twice_in_an_item_is_recorded_once_per_occurrence(
    tmp_path: Path,
) -> None:
    """The loop re-issues a byte-identical request after a broken tool input, so the failure and
    the success share a fingerprint. Both must replay, in order."""
    store = a_store(tmp_path)
    request = a_request()
    recorder = RecordingTransport(Flaky(), store)
    recorder.current_item = "qa-001"
    _, error = await collect_until_error(recorder.stream(request), InvalidToolInput)
    success = await collect(recorder.stream(request))

    assert [(r.occurrence, r.error is not None) for r in store.records()] == [(0, True), (1, False)]

    replay = ReplayTransport(store)
    replay.current_item = "qa-001"
    _, replayed_error = await collect_until_error(replay.stream(request), InvalidToolInput)
    assert str(replayed_error) == str(error)
    assert await collect(replay.stream(request)) == success
    assert replay.misses == []
    with pytest.raises(ReplayMiss):  # a third call was never recorded
        await collect(replay.stream(request))


async def test_setting_the_item_restarts_the_occurrence_count(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    request = a_request()
    recorder = RecordingTransport(ScriptedTransport(), store)
    replay = ReplayTransport(store)
    recorder.current_item = "qa-001"
    await collect(recorder.stream(request))
    recorder.current_item = "qa-001"  # a second trial of the same item
    await collect(recorder.stream(request))
    recorder.current_item = "qa-002"  # another item with the same request
    await collect(recorder.stream(request))

    # The first recording of each (fingerprint, occurrence) wins, so the trials add nothing.
    assert [(r.occurrence, r.item) for r in store.records()] == [(0, "qa-001")]
    # And a replay of any item, or trial, starts again from the first recording.
    replay.current_item = "qa-001"
    await collect(replay.stream(request))
    replay.current_item = "qa-001"
    await collect(replay.stream(request))
    assert replay.misses == []


async def test_guard_calls_count_occurrences_too(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    request = build_guard_request("Hello", None)
    recorder = RecordingTransport(ScriptedTransport(), store)
    recorder.current_item = "qa-001"
    await recorder.classify(request)
    await recorder.classify(request)

    assert [r.occurrence for r in store.records()] == [0, 1]


async def test_a_transient_model_error_is_not_recorded(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    request = a_request("scripted mid-stream error")
    recorder = RecordingTransport(ScriptedTransport(), store)

    await collect_until_error(recorder.stream(request), ModelUnavailable)

    assert len(store) == 0
    [skipped] = recorder.skipped
    assert (skipped.kind, skipped.occurrence) == ("model", 0)
    assert "transient" in skipped.reason
    assert "ModelUnavailable" in skipped.reason


async def test_a_guard_failure_with_no_usage_is_not_recorded(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    recorder = RecordingTransport(ScriptedTransport(), store)
    with pytest.raises(GuardUnavailable):
        await recorder.classify(build_guard_request("scripted guard failure", None))

    assert len(store) == 0
    [skipped] = recorder.skipped
    assert skipped.kind == "guard"
    assert "transient" in skipped.reason


async def test_a_guard_failure_with_usage_is_model_behavior_and_is_recorded(
    tmp_path: Path,
) -> None:
    class Refusing:
        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            raise NotImplementedError
            yield  # pragma: no cover

        async def classify(self, request: GuardRequest) -> GuardResult:
            raise GuardUnavailable("the guard stopped with 'refusal'", usage=USAGE)

    store = a_store(tmp_path)
    request = build_guard_request("Hello", None)
    with pytest.raises(GuardUnavailable):
        await RecordingTransport(Refusing(), store).classify(request)

    with pytest.raises(GuardUnavailable) as raised:
        await ReplayTransport(store).classify(request)
    assert raised.value.usage == USAGE


async def test_a_spend_limit_is_never_recorded(tmp_path: Path) -> None:
    class Limited:
        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            raise SpendLimitReached("limit")
            yield  # pragma: no cover

        async def classify(self, request: GuardRequest) -> GuardResult:
            raise SpendLimitReached("limit")

    store = a_store(tmp_path)
    recorder = RecordingTransport(Limited(), store)
    with pytest.raises(SpendLimitReached):
        await collect(recorder.stream(a_request()))
    with pytest.raises(SpendLimitReached):
        await recorder.classify(build_guard_request("Hello", None))

    assert len(store) == 0
    assert [s.kind for s in recorder.skipped] == ["model", "guard"]


async def test_a_stream_closed_early_is_a_recording_gap_with_a_reason(tmp_path: Path) -> None:
    recorder = RecordingTransport(ScriptedTransport(), a_store(tmp_path))
    stream = recorder.stream(a_request())
    await anext(stream)
    await stream.aclose()  # type: ignore[attr-defined]

    [skipped] = recorder.skipped
    assert "closed early" in skipped.reason


async def test_the_skipped_list_restarts_with_each_item(tmp_path: Path) -> None:
    recorder = RecordingTransport(ScriptedTransport(), a_store(tmp_path))
    with pytest.raises(GuardUnavailable):
        await recorder.classify(build_guard_request("scripted guard failure", None))
    assert recorder.skipped

    recorder.current_item = "qa-002"

    assert recorder.skipped == []


async def test_the_recorder_copies_what_it_records(tmp_path: Path) -> None:
    """The loop keeps the finished message and the tool inputs and may change them later."""
    store = a_store(tmp_path)
    recorder = RecordingTransport(ScriptedTransport(), store)
    events = await collect(recorder.stream(a_request()))
    call = next(e for e in events if isinstance(e, ToolCall))
    finished = next(e for e in events if isinstance(e, Finished))
    call.input["query"] = "changed afterward"
    finished.message["content"].append({"type": "text", "text": "added afterward"})

    (record,) = store.records()
    assert record.events is not None
    recorded_call = next(e for e in record.events if e["type"] == "tool_call")
    recorded_finished = next(e for e in record.events if e["type"] == "finished")
    assert recorded_call["input"] == {"query": a_request().messages[0]["content"]}
    assert len(recorded_finished["message"]["content"]) == 1


async def test_the_recorder_does_not_record_an_error_it_does_not_know(tmp_path: Path) -> None:
    class Broken:
        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            yield TextDelta("partial")
            raise RuntimeError("a bug")

        async def classify(self, request: GuardRequest) -> GuardResult:
            raise RuntimeError("a bug")

    store = a_store(tmp_path)
    recorder = RecordingTransport(Broken(), store)
    with pytest.raises(RuntimeError):
        await collect(recorder.stream(a_request()))
    with pytest.raises(RuntimeError):
        await recorder.classify(build_guard_request("Hello", None))

    assert len(store) == 0


async def test_a_stream_closed_early_is_not_recorded(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    stream = RecordingTransport(ScriptedTransport(), store).stream(a_request())
    await anext(stream)
    await stream.aclose()  # type: ignore[attr-defined]

    assert len(store) == 0


async def test_a_guard_answer_is_recorded_and_replayed(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    request = build_guard_request("I want to hurt myself", None)
    recorder = RecordingTransport(ScriptedTransport(), store)
    recorder.current_item = "rt-007"

    recorded = await recorder.classify(request)

    assert recorded.category == "crisis"
    (record,) = store.records()
    assert (record.kind, record.item) == ("guard", "rt-007")
    assert await ReplayTransport(store).classify(request) == recorded


# --- A miss -----------------------------------------------------------------------------------


async def test_a_miss_raises_with_the_item_and_the_hint() -> None:
    replay = ReplayTransport(FixtureStore(Path("unused.jsonl.gz")))
    replay.current_item = "redteam-014"

    with pytest.raises(ReplayMiss) as raised:
        await collect(replay.stream(a_request()))

    assert "redteam-014" in str(raised.value)
    assert "re-record with `make eval-live`" in str(raised.value)
    assert RE_RECORD_HINT == "re-record with `make eval-live`"
    assert [(m.item, m.kind, m.fingerprint) for m in replay.misses] == [
        ("redteam-014", "model", model_fingerprint(a_request()))
    ]


async def test_a_recording_of_another_kind_is_a_miss(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    store.put(a_record(model_fingerprint(a_request()), kind="guard"))
    replay = ReplayTransport(store)

    with pytest.raises(ReplayMiss):
        await collect(replay.stream(a_request()))

    assert len(replay.misses) == 1


async def test_a_miss_is_not_a_kind_of_error_the_loop_handles() -> None:
    for handled in (ModelUnavailable, SpendLimitReached, InvalidToolInput, GuardUnavailable):
        assert not issubclass(ReplayMiss, handled)


async def test_a_guard_miss_is_recorded_even_though_the_guard_swallows_the_error() -> None:
    """`screen` turns any error into "unavailable", so the miss list is what the harness reads."""
    replay = ReplayTransport(FixtureStore(Path("unused.jsonl.gz")))
    replay.current_item = "redteam-003"

    outcome = await screen(replay, build_guard_request("Hello", None))

    assert outcome.route == "unavailable"
    assert [(m.item, m.kind) for m in replay.misses] == [("redteam-003", "guard")]
    with pytest.raises(ReplayMiss, match=r"redteam-003.*re-record with `make eval-live`"):
        replay.raise_if_missed()


def test_nothing_is_raised_when_nothing_missed() -> None:
    ReplayTransport(FixtureStore(Path("unused.jsonl.gz"))).raise_if_missed()


async def test_the_misses_can_be_cleared_between_items() -> None:
    replay = ReplayTransport(FixtureStore(Path("unused.jsonl.gz")))
    with pytest.raises(ReplayMiss):
        await replay.classify(build_guard_request("Hello", None))

    replay.clear_misses()

    assert replay.misses == []
    replay.raise_if_missed()


async def test_a_miss_by_occurrence_says_how_many_were_recorded(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    recorder = RecordingTransport(ScriptedTransport(), store)
    await collect(recorder.stream(a_request()))
    replay = ReplayTransport(store)
    replay.current_item = "qa-001"
    await collect(replay.stream(a_request()))

    with pytest.raises(ReplayMiss, match=r"occurrence 1"):
        await collect(replay.stream(a_request()))


@pytest.mark.parametrize(
    "bad_events",
    [
        [{"type": "from_the_future"}],
        [{"type": "text_delta"}],  # a key is missing
        [{"type": "finished", "message": {}}],
    ],
)
async def test_an_unreadable_recording_is_a_miss_not_an_error_the_loop_absorbs(
    tmp_path: Path, bad_events: list[dict[str, Any]]
) -> None:
    store = a_store(tmp_path)
    store.put(
        Record(
            fingerprint=model_fingerprint(a_request()),
            kind="model",
            item="qa-001",
            events=tuple(bad_events),
        )
    )
    replay = ReplayTransport(store)
    replay.current_item = "qa-005"

    with pytest.raises(ReplayMiss, match="could not be read"):
        await collect(replay.stream(a_request()))

    [miss] = replay.misses
    assert (miss.item, miss.kind) == ("qa-005", "model")
    assert "could not be read" in miss.reason
    with pytest.raises(ReplayMiss, match=r"qa-005.*re-record with `make eval-live`"):
        replay.raise_if_missed()


async def test_an_unreadable_error_or_guard_recording_is_a_miss_too(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    store.put(
        Record(
            fingerprint=model_fingerprint(a_request()),
            kind="model",
            item="qa-001",
            events=(),
            error={"type": "from_the_future", "message": "x"},
        )
    )
    guard_request = build_guard_request("Hello", None)
    store.put(
        Record(
            fingerprint=guard_fingerprint(guard_request),
            kind="guard",
            item="qa-001",
            result={"category": "ordinary"},  # the rest of the result is missing
        )
    )
    replay = ReplayTransport(store)

    with pytest.raises(ReplayMiss):
        await collect(replay.stream(a_request()))
    outcome = await screen(replay, guard_request)  # the guard swallows the error
    assert outcome.route == "unavailable"

    assert [m.kind for m in replay.misses] == ["model", "guard"]
    with pytest.raises(ReplayMiss):
        replay.raise_if_missed()


# --- The fixture file -------------------------------------------------------------------------


def a_record(
    fingerprint_: str, item: str = "qa-001", kind: str = "model", occurrence: int = 0
) -> Record:
    return Record(
        fingerprint=fingerprint_,
        kind=kind,  # type: ignore[arg-type]
        item=item,
        occurrence=occurrence,
        events=({"type": "text_delta", "text": "Hi"},),
    )


def test_the_store_is_one_gzip_json_lines_file(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    store.put(a_record("bbb", item="qa-002"))
    store.put(
        Record(fingerprint="aaa", kind="guard", item="qa-001", result={"category": "ordinary"})
    )
    store.put(
        Record(fingerprint="ccc", kind="model", item="qa-003", error={"type": "model_unavailable"})
    )
    store.save()

    raw = (tmp_path / "redteam.jsonl.gz").read_bytes()
    assert raw[:2] == b"\x1f\x8b"  # gzip's magic number
    lines = gzip.decompress(raw).decode("utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert [line["fingerprint"] for line in parsed] == ["aaa", "bbb", "ccc"]  # sorted
    assert parsed[0] == {
        "fingerprint": "aaa",
        "kind": "guard",
        "item": "qa-001",
        "occurrence": 0,
        "result": {"category": "ordinary"},
    }
    assert parsed[1]["events"] == [{"type": "text_delta", "text": "Hi"}]
    assert parsed[2]["error"] == {"type": "model_unavailable"}
    assert "result" not in parsed[1]
    assert "error" not in parsed[1]


def test_a_saved_store_loads_back_the_same(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    store.put(a_record("bbb"))
    store.put(Record(fingerprint="aaa", kind="judge", item="qa-009", result={"ok": True}))
    store.save()

    loaded = FixtureStore.load(tmp_path / "redteam.jsonl.gz")

    assert loaded.records() == store.records()
    assert len(loaded) == 2
    assert "aaa" in loaded


def test_the_first_recording_wins_per_fingerprint_and_occurrence(tmp_path: Path) -> None:
    store = a_store(tmp_path)

    assert store.put(a_record("aaa", occurrence=0)) is True
    assert store.put(a_record("aaa", occurrence=1, item="qa-002")) is True
    assert store.put(a_record("aaa", occurrence=1, item="qa-003")) is False

    assert [(r.occurrence, r.item) for r in store.records()] == [(0, "qa-001"), (1, "qa-002")]
    store.save()
    assert FixtureStore.load(store.path).records() == store.records()
    assert "aaa" in store


def test_a_line_without_an_occurrence_is_the_first(tmp_path: Path) -> None:
    path = tmp_path / "old.jsonl.gz"
    line = {"fingerprint": "aaa", "kind": "model", "item": "x", "events": []}
    path.write_bytes(gzip.compress((json.dumps(line) + "\n").encode()))

    (record,) = FixtureStore.load(path).records()

    assert record.occurrence == 0


def test_loading_a_file_that_does_not_exist_gives_an_empty_store(tmp_path: Path) -> None:
    store = FixtureStore.load(tmp_path / "nothing.jsonl.gz")

    assert len(store) == 0


def test_the_first_recording_of_a_request_wins(tmp_path: Path) -> None:
    store = a_store(tmp_path)

    assert store.put(a_record("aaa", item="qa-001")) is True
    assert store.put(replace(a_record("aaa", item="qa-002"), events=())) is False

    (record,) = store.records()
    assert record.item == "qa-001"
    assert record.events == ({"type": "text_delta", "text": "Hi"},)


def test_the_first_recording_in_a_file_wins_when_it_loads(tmp_path: Path) -> None:
    path = tmp_path / "dups.jsonl.gz"
    lines = [
        {"fingerprint": "aaa", "kind": "model", "item": "first", "events": []},
        {"fingerprint": "aaa", "kind": "model", "item": "second", "events": []},
    ]
    path.write_bytes(gzip.compress("".join(json.dumps(x) + "\n" for x in lines).encode()))

    (record,) = FixtureStore.load(path).records()

    assert record.item == "first"


def test_saving_an_unchanged_store_gives_identical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "deterministic.jsonl.gz"
    store = FixtureStore(path)
    for name in ("ccc", "aaa", "bbb"):
        store.put(a_record(name))
    store.save()
    first = path.read_bytes()

    FixtureStore.load(path).save()
    assert path.read_bytes() == first

    other = FixtureStore(tmp_path / "other.jsonl.gz")
    for name in ("bbb", "ccc", "aaa"):  # a different order of recording
        other.put(a_record(name))
    other.save()
    assert (tmp_path / "other.jsonl.gz").read_bytes() == first
    assert first[4:8] == b"\x00\x00\x00\x00"  # the gzip header's timestamp is zero


def test_a_bad_line_is_reported_with_its_file_and_number(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl.gz"
    path.write_bytes(gzip.compress(b'{"fingerprint": "aaa"}\n'))

    with pytest.raises(ValueError, match=r"bad\.jsonl\.gz:1"):
        FixtureStore.load(path)


def test_one_file_per_dataset(tmp_path: Path) -> None:
    redteam, qa = a_store(tmp_path, "redteam"), a_store(tmp_path, "qa")
    redteam.put(a_record("aaa"))
    qa.put(a_record("bbb"))
    redteam.save()
    qa.save()

    assert sorted(path.name for path in tmp_path.iterdir()) == ["qa.jsonl.gz", "redteam.jsonl.gz"]
    assert "bbb" not in FixtureStore.load(tmp_path / "redteam.jsonl.gz")


# --- A stream the loop closes because the model repeated the prompt's canary -------------------


class Leaky:
    """A model that says whatever pieces the test gives, then more the loop never reads."""

    def __init__(self, *pieces: ModelEvent) -> None:
        self.pieces = pieces

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        for piece in self.pieces:
            yield piece
        yield TextDelta("never read: the loop has closed the stream")

    async def classify(self, request: GuardRequest) -> GuardResult:
        raise NotImplementedError


async def read_then_close(stream: AsyncIterator[ModelEvent], count: int) -> list[ModelEvent]:
    """Read `count` events and close the stream, as the loop does when it stops a leak."""
    seen = [await anext(stream) for _ in range(count)]
    await stream.aclose()  # type: ignore[attr-defined]
    return seen


async def test_a_stream_closed_early_waits_for_the_turns_outcome_before_it_is_recorded(
    tmp_path: Path,
) -> None:
    store = a_store(tmp_path)
    recorder = RecordingTransport(Leaky(StatusNote("Searching."), StatusNote("Marker")), store)
    recorder.current_item = "rt-023"

    seen = await read_then_close(recorder.stream(a_request()), 2)

    assert len(store) == 0
    assert recorder.has_pending_close
    recorder.settle(prompt_leak=True)
    (record,) = store.records()
    assert record.closed_early is True
    assert record.item == "rt-023"
    assert not recorder.has_pending_close
    replay = ReplayTransport(store)
    replay.current_item = "rt-023"
    stream = replay.stream(a_request())
    assert [await anext(stream), await anext(stream)] == seen


async def test_a_close_the_turn_did_not_call_a_leak_stays_a_recording_gap(
    tmp_path: Path,
) -> None:
    store = a_store(tmp_path)
    recorder = RecordingTransport(Leaky(StatusNote("Searching."), TextDelta("Hello")), store)

    await read_then_close(recorder.stream(a_request()), 2)
    recorder.settle(prompt_leak=False)

    assert len(store) == 0
    assert not recorder.has_pending_close
    [skipped] = recorder.skipped
    assert "closed early" in skipped.reason


async def test_only_the_last_pending_close_is_the_one_the_loop_ended_the_turn_on(
    tmp_path: Path,
) -> None:
    store = a_store(tmp_path)
    recorder = RecordingTransport(Leaky(StatusNote("a"), StatusNote("b")), store)
    recorder.current_item = "rt-023"
    await read_then_close(recorder.stream(a_request("First?")), 1)
    await read_then_close(recorder.stream(a_request("Second?")), 1)

    recorder.settle(prompt_leak=True)

    [record] = store.records()
    assert record.fingerprint == model_fingerprint(a_request("Second?"))


async def test_a_pending_close_belongs_to_the_item_it_was_made_in(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    recorder = RecordingTransport(Leaky(StatusNote("a")), store)
    recorder.current_item = "rt-023"
    await read_then_close(recorder.stream(a_request()), 1)

    recorder.current_item = "rt-024"
    recorder.settle(prompt_leak=True)

    assert len(store) == 0


async def test_replay_of_such_a_stream_refuses_to_read_past_where_the_loop_stopped(
    tmp_path: Path,
) -> None:
    store = a_store(tmp_path)
    recorder = RecordingTransport(Leaky(StatusNote("Marker")), store)
    await read_then_close(recorder.stream(a_request()), 1)
    recorder.settle(prompt_leak=True)
    replay = ReplayTransport(store)
    replay.current_item = "rt-023"

    with pytest.raises(ReplayMiss, match="closed"):
        await collect(replay.stream(a_request()))

    assert replay.misses


async def test_a_stream_cut_off_by_cancellation_is_never_pending(tmp_path: Path) -> None:
    class Stalls:
        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            yield StatusNote("Marker")
            await asyncio.sleep(30)  # the deadline fires while the model is silent
            yield TextDelta("never")

        async def classify(self, request: GuardRequest) -> GuardResult:
            raise NotImplementedError

    store = a_store(tmp_path)
    recorder = RecordingTransport(Stalls(), store)
    stream = recorder.stream(a_request())
    await anext(stream)
    waiting = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    recorder.settle(prompt_leak=True)

    assert len(store) == 0
    assert not recorder.has_pending_close


def test_the_recorder_does_not_look_for_the_canary_itself() -> None:
    import app.ai.replay as replay_module

    assert not hasattr(replay_module, "_holds_canary")
    assert not hasattr(replay_module, "CANARY")


def test_closed_early_is_written_only_when_it_is_true_and_survives_the_file(
    tmp_path: Path,
) -> None:
    plain = Record("fp-1", "model", "rt-1", events=({"type": "text_delta", "text": "x"},))
    early = Record(
        "fp-2", "model", "rt-1", events=({"type": "text_delta", "text": "x"},), closed_early=True
    )
    store = a_store(tmp_path)
    store.put(plain)
    store.put(early)
    store.save()

    assert "closed_early" not in plain.to_json()
    loaded = {r.fingerprint: r for r in FixtureStore.load(store.path).records()}
    assert loaded["fp-1"].closed_early is False
    assert loaded["fp-2"].closed_early is True


# --- A request made twice in one live run ------------------------------------------------------


class Varies:
    """A model that answers differently every call, and counts its calls."""

    def __init__(self) -> None:
        self.stream_calls = 0
        self.classify_calls = 0

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.stream_calls += 1
        yield TextDelta(f"answer {self.stream_calls}")
        yield Finished(
            message={"role": "assistant", "content": []},
            stop_reason="end_turn",
            stop_details=None,
            usage=USAGE,
            iterations=(),
            served_by=OPUS,
            fell_back=False,
        )

    async def classify(self, request: GuardRequest) -> GuardResult:
        self.classify_calls += 1
        return GuardResult(
            category="ordinary",
            kind=None,
            injection_suspected=self.classify_calls % 2 == 0,
            usage=USAGE,
            served_by=HAIKU,
        )


async def test_a_second_item_gets_the_response_the_first_one_saved_for_the_same_request(
    tmp_path: Path,
) -> None:
    store = a_store(tmp_path)
    inner = Varies()
    recorder = RecordingTransport(inner, store)
    guard_request = build_guard_request("How much sick leave do I get?", None)
    recorder.current_item = "qa-021"
    first_guard = await recorder.classify(guard_request)
    first_events = await collect(recorder.stream(a_request()))
    recorder.current_item = "qa-022"

    second_guard = await recorder.classify(guard_request)
    second_events = await collect(recorder.stream(a_request()))

    assert second_guard == first_guard
    assert second_events == first_events
    assert (inner.classify_calls, inner.stream_calls) == (1, 1)
    # Replay of the saved file reproduces what both items saw.
    replay = ReplayTransport(store)
    replay.current_item = "qa-022"
    assert await replay.classify(guard_request) == first_guard
    assert await collect(replay.stream(a_request())) == first_events


async def test_a_repeat_within_an_item_is_a_new_occurrence_and_calls_the_model(
    tmp_path: Path,
) -> None:
    inner = Varies()
    recorder = RecordingTransport(inner, a_store(tmp_path))
    recorder.current_item = "qa-021"

    await collect(recorder.stream(a_request()))
    await collect(recorder.stream(a_request()))

    assert inner.stream_calls == 2


async def test_a_recorded_error_is_served_again_to_the_next_item(tmp_path: Path) -> None:
    class Refuses:
        calls = 0

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            Refuses.calls += 1
            yield TextDelta("partial")
            raise InvalidToolInput("bad json")

        async def classify(self, request: GuardRequest) -> GuardResult:
            raise NotImplementedError

    recorder = RecordingTransport(Refuses(), a_store(tmp_path))
    recorder.current_item = "qa-021"
    seen, _ = await collect_until_error(recorder.stream(a_request()), InvalidToolInput)
    recorder.current_item = "qa-022"

    again, _ = await collect_until_error(recorder.stream(a_request()), InvalidToolInput)

    assert again == seen
    assert Refuses.calls == 1


async def test_a_transient_failure_is_not_served_to_the_next_item(tmp_path: Path) -> None:
    class Flaky:
        calls = 0

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            Flaky.calls += 1
            if Flaky.calls == 1:
                raise ModelUnavailable("down")
            yield TextDelta("fine")

        async def classify(self, request: GuardRequest) -> GuardResult:
            raise NotImplementedError

    recorder = RecordingTransport(Flaky(), a_store(tmp_path))
    recorder.current_item = "qa-021"
    with pytest.raises(ModelUnavailable):
        await collect(recorder.stream(a_request()))
    recorder.current_item = "qa-022"

    assert await collect(recorder.stream(a_request())) == [TextDelta("fine")]


async def test_a_recording_already_in_the_store_is_served_without_calling_the_model(
    tmp_path: Path,
) -> None:
    older = a_store(tmp_path)
    ancient = RecordingTransport(Varies(), older)
    ancient.current_item = "qa-021"
    first_events = await collect(ancient.stream(a_request()))
    first_guard = await ancient.classify(build_guard_request("Hello?", None))
    older.save()
    inner = Varies()
    recorder = RecordingTransport(inner, FixtureStore.load(older.path))
    recorder.current_item = "qa-022"

    again = await collect(recorder.stream(a_request()))
    guard = await recorder.classify(build_guard_request("Hello?", None))

    assert again == first_events
    assert guard == first_guard
    assert (inner.stream_calls, inner.classify_calls) == (0, 0)


async def test_a_request_not_in_the_store_is_called_and_recorded(tmp_path: Path) -> None:
    older = a_store(tmp_path)
    await collect(RecordingTransport(Varies(), older).stream(a_request()))
    inner = Varies()
    store = FixtureStore.load(older.path) if older.path.exists() else older
    recorder = RecordingTransport(inner, store)

    await collect(recorder.stream(a_request("A new question?")))

    assert inner.stream_calls == 1
    assert len(store) == 2


# --- The index ---------------------------------------------------------------------------------


def test_counting_a_requests_recordings_does_not_scan_the_store(tmp_path: Path) -> None:
    class NoScan(dict[tuple[str, int], Record]):
        def __iter__(self) -> Any:
            raise AssertionError("the store was scanned")

    store = a_store(tmp_path)
    for occurrence in range(3):
        store.put(Record("fp-1", "model", "rt-1", occurrence, events=({"type": "x"},)))
    store.put(Record("fp-2", "model", "rt-1", 0, events=({"type": "x"},)))
    store._records = NoScan(store._records)

    assert store.count("fp-1") == 3
    assert store.count("fp-3") == 0
    assert "fp-2" in store
    assert "fp-3" not in store


# --- The temporary file a save writes ---------------------------------------------------------


def test_a_save_writes_through_a_dotted_temporary_file_beside_the_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    store = a_store(tmp_path)
    store.put(Record("fp-1", "model", "rt-1", events=({"type": "x"},)))
    seen: list[Path] = []
    real_replace = os.replace

    def spy(source: Any, destination: Any) -> None:
        seen.append(Path(source))
        real_replace(source, destination)

    monkeypatch.setattr("app.ai.replay.os.replace", spy)

    store.save()

    [temporary] = seen
    assert temporary.parent == store.path.parent
    assert temporary.name.startswith(".")
    assert temporary.suffix == ".tmp"
    assert not temporary.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == [store.path.name]


def test_a_failed_save_leaves_no_temporary_file_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = a_store(tmp_path)
    store.put(Record("fp-1", "model", "rt-1", events=({"type": "x"},)))

    def boom(source: Any, destination: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("app.ai.replay.os.replace", boom)

    with pytest.raises(OSError, match="disk full"):
        store.save()

    assert list(tmp_path.iterdir()) == []


def test_git_ignores_a_temporary_fixture_file_a_crash_could_leave() -> None:
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    root = Path(__file__).resolve().parents[3]

    for name in (
        "evals/assistant/fixtures/.qa.jsonl.gz.k3j2.tmp",
        "evals/assistant/fixtures-effort/.judge.jsonl.gz.zz.tmp",
    ):
        done = subprocess.run(  # noqa: S603
            ["git", "check-ignore", "-q", name],  # noqa: S607
            cwd=root,
            check=False,
        )
        assert done.returncode == 0, name


async def test_the_recorder_refuses_to_read_past_a_close_the_loop_made_when_it_serves_it(
    tmp_path: Path,
) -> None:
    store = a_store(tmp_path)
    store.put(
        Record(
            model_fingerprint(a_request()),
            "model",
            "rt-023",
            events=({"type": "status_note", "text": "Marker"},),
            closed_early=True,
        )
    )
    recorder = RecordingTransport(Leaky(), store)
    recorder.current_item = "rt-024"
    stream = recorder.stream(a_request())

    assert await anext(stream) == StatusNote("Marker")
    with pytest.raises(ReplayMiss, match="closed"):
        await anext(stream)


# --- The recorder answering from the store: misses surface --------------------------------------


async def test_a_read_past_a_closed_record_is_listed_as_a_miss_and_raised_by_the_check(
    tmp_path: Path,
) -> None:
    store = a_store(tmp_path)
    store.put(
        Record(
            model_fingerprint(a_request()),
            "model",
            "rt-023",
            events=({"type": "status_note", "text": "Marker"},),
            closed_early=True,
        )
    )
    recorder = RecordingTransport(Leaky(), store)
    recorder.current_item = "rt-024"

    with pytest.raises(ReplayMiss):
        await collect(recorder.stream(a_request()))

    assert [m.item for m in recorder.misses] == ["rt-024"]
    with pytest.raises(ReplayMiss, match=RE_RECORD_HINT.replace("`", "`")):
        recorder.raise_if_missed()


async def test_an_unreadable_committed_record_is_a_miss_not_a_crash(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    store.put(
        Record(
            model_fingerprint(a_request()),
            "model",
            "rt-023",
            events=({"type": "no_such_event"},),
        )
    )
    store.put(
        Record(guard_fingerprint(build_guard_request("Hello?", None)), "guard", "rt-023", result={})
    )
    recorder = RecordingTransport(Varies(), store)
    recorder.current_item = "rt-024"

    with pytest.raises(ReplayMiss):
        await collect(recorder.stream(a_request()))
    with pytest.raises(ReplayMiss):
        await recorder.classify(build_guard_request("Hello?", None))

    assert [m.kind for m in recorder.misses] == ["model", "guard"]
    assert all("could not be read" in m.reason for m in recorder.misses)


async def test_a_recorder_with_no_misses_passes_the_check_and_the_list_restarts_per_item(
    tmp_path: Path,
) -> None:
    store = a_store(tmp_path)
    store.put(
        Record(
            model_fingerprint(a_request()),
            "model",
            "rt-023",
            events=({"type": "status_note", "text": "Marker"},),
            closed_early=True,
        )
    )
    recorder = RecordingTransport(Leaky(), store)
    recorder.raise_if_missed()
    recorder.current_item = "rt-024"
    with pytest.raises(ReplayMiss):
        await collect(recorder.stream(a_request()))

    recorder.current_item = "rt-025"

    assert recorder.misses == []
    recorder.raise_if_missed()


# --- A damaged model recording, and one shared way to serve a record ---------------------------


def model_record_with(*raw_events: dict[str, Any], **fields: Any) -> Record:
    return Record(model_fingerprint(a_request()), "model", "rt-023", events=raw_events, **fields)


FINISHED_RAW: dict[str, Any] = {
    "type": "finished",
    "message": {"role": "assistant", "content": []},
    "stop_reason": "end_turn",
    "stop_details": None,
    "usage": {
        "input_tokens": 1,
        "output_tokens": 1,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    },
    "iterations": [],
    "served_by": "claude-opus-5-5",
    "fell_back": False,
}


@pytest.mark.parametrize(
    "damaged",
    [
        model_record_with(),
        model_record_with({"type": "text_delta", "text": "partial"}),
        model_record_with(
            {"type": "text_delta", "text": "x"}, FINISHED_RAW, {"type": "text_delta", "text": "y"}
        ),
    ],
)
@pytest.mark.parametrize("through", ["replay", "recorder"])
async def test_a_model_record_that_does_not_end_in_a_finished_event_is_a_miss(
    tmp_path: Path, damaged: Record, through: str
) -> None:
    store = a_store(tmp_path)
    store.put(damaged)
    transport: Any = (
        ReplayTransport(store) if through == "replay" else RecordingTransport(Varies(), store)
    )
    transport.current_item = "rt-024"

    with pytest.raises(ReplayMiss, match="no finished event"):
        await collect(transport.stream(a_request()))

    assert [m.reason for m in transport.misses] == ["the recording has no finished event"]


@pytest.mark.parametrize("through", ["replay", "recorder"])
async def test_records_that_legitimately_stop_short_are_not_misses(
    tmp_path: Path, through: str
) -> None:
    # A closed-early record and a record that ended in a typed error both stop before `finished`.
    closed = model_record_with({"type": "status_note", "text": "Marker"}, closed_early=True)
    failed = Record(
        model_fingerprint(a_request("Another?")),
        "model",
        "rt-023",
        events=({"type": "text_delta", "text": "part"},),
        error={"type": "invalid_tool_input", "message": "bad"},
    )
    store = a_store(tmp_path)
    store.put(closed)
    store.put(failed)
    transport: Any = (
        ReplayTransport(store) if through == "replay" else RecordingTransport(Varies(), store)
    )
    transport.current_item = "rt-024"

    assert await anext(transport.stream(a_request())) == StatusNote("Marker")
    seen, _ = await collect_until_error(transport.stream(a_request("Another?")), InvalidToolInput)
    assert seen == [TextDelta("part")]
    assert transport.misses == []


def test_serving_a_record_is_written_once_for_both_transports() -> None:
    import inspect

    from app.ai.replay import _MissLog

    assert hasattr(_MissLog, "_serve_model")
    assert hasattr(_MissLog, "_serve_guard")
    for transport in (RecordingTransport, ReplayTransport):
        for method in ("stream", "classify"):
            source = inspect.getsource(getattr(transport, method))
            assert "decode_event(" not in source, (transport, method)
            assert "decode_guard_result(" not in source, (transport, method)


async def test_a_stream_cut_off_by_cancellation_is_reported_as_canceled_not_closed_early(
    tmp_path: Path,
) -> None:
    class Stalls:
        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            yield StatusNote("Searching.")
            await asyncio.sleep(30)

        async def classify(self, request: GuardRequest) -> GuardResult:
            raise NotImplementedError

    recorder = RecordingTransport(Stalls(), a_store(tmp_path))
    stream = recorder.stream(a_request())
    await anext(stream)
    waiting = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    [skipped] = recorder.skipped
    assert skipped.reason == "canceled (deadline or stop)"


async def test_a_stream_the_consumer_closes_is_still_closed_early_and_cancellation_reraises(
    tmp_path: Path,
) -> None:
    recorder = RecordingTransport(Leaky(StatusNote("a"), StatusNote("b")), a_store(tmp_path))
    await read_then_close(recorder.stream(a_request()), 1)

    [skipped] = recorder.skipped
    assert skipped.reason == "stream closed early"
