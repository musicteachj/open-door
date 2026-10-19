"""The assistant eval's runner (evals/assistant/run.py) and scoreboard (scoreboard.py), without a
database: the sets and caps, the scoreboard's numbers and fields, the exit codes, the fixture merge,
the comparison, and the command line up to the point a database is needed.

The runs that need the database are in tests/integration/test_assistant_eval_runner_db.py. Nothing
here touches the network: a test that reaches for an Anthropic client or Voyage fails.
"""

import inspect
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

import pytest

from app.ai.pricing import HAIKU, IterationUsage, Usage, turn_call_cost
from app.ai.replay import FixtureStore, Record
from app.ai.transport import Finished, GuardRequest, GuardResult, SpendLimitReached
from app.modules.sandbox.seed import build_company
from tests.assistant_eval import (
    EVAL_DIR,
    load_datasets,
    load_graders,
    load_judge,
    load_runner,
    load_scoreboard,
    make_trace,
)

run = load_runner()
board = load_scoreboard()
graders = load_graders()
datasets = load_datasets()
judge = load_judge()

SONNET = "claude-sonnet-5-5"
OPUS = "claude-opus-5-5"


def grade(*, failing: dict[str, list[str]] | None = None) -> Any:
    """An `ItemGrade` that passed, or failed the named graders with the given reasons."""
    failing = failing or {}
    results = [graders.GradeResult("private-data", True)]
    results += [graders.GradeResult(name, False, tuple(why)) for name, why in failing.items()]
    return graders.ItemGrade(tuple(results))


def verdict(**no: bool) -> Any:
    lines = dict.fromkeys(judge.RUBRIC_KEYS, True)
    lines.update({key: False for key in no})
    return judge.Verdict(lines, dict.fromkeys(judge.RUBRIC_KEYS, "r"))


def outcome(item: str, v: Any = None, *, unavailable: str | None = None, cost: str = "0.01") -> Any:
    return judge.JudgeOutcome(item, "fp", v, unavailable, Decimal(cost), None)


def record(
    item: str,
    *,
    dataset: str = "qa",
    trial: int = 1,
    group: str | None = None,
    qa_kind: str | None = "answerable",
    grade_: Any = None,
    judged: Any = None,
    **trace: Any,
) -> Any:
    return board.ItemRecord(
        trial=trial,
        dataset=dataset,
        item_id=item,
        group=group,
        qa_kind=qa_kind if dataset == "qa" else None,
        grade=grade_ or grade(),
        trace=make_trace(person_id=uuid4(), item_id=item, **trace),
        judge_input=None,
        judge=judged,
    )


def facts(**overrides: Any) -> Any:
    values: dict[str, Any] = {
        "mode": "live",
        "set_name": "smoke",
        "effort": "low",
        "trials": 1,
        "commit": "abc123",
        "date": "2026-10-16T12:00:00+00:00",
        "models": {"assistant": "claude-opus-5-5", "guard": "claude-haiku-5-5", "judge": SONNET},
        "versions": {
            "prompt": "2026-10.1",
            "toolset": "2026-10.1",
            "guard_prompt": "2026-10.1",
            "judge": "2026-10.1",
        },
        "dataset_sha256": {"redteam.yaml": "aa", "qa.yaml": "bb", "smoke.yaml": "cc"},
        "cap_usd": Decimal("2.00"),
        "assistant_cost_usd": Decimal("0.75"),
        "judge_cost_usd": Decimal("0.25"),
        "partial": False,
        "stop_cause": None,
        "items_not_run": [],
        "agreement": None,
    }
    values.update(overrides)
    return board.RunFacts(**values)


# --- The sets, the caps, and the estimates ----------------------------------------------------


def test_the_three_sets_have_their_trials_caps_efforts_and_estimates() -> None:
    smoke, full, effort = run.SETS["smoke"], run.SETS["full"], run.SETS["effort"]

    assert (smoke.trials, smoke.cap_usd, smoke.effort) == (1, Decimal("2.00"), "low")
    assert (full.trials, full.cap_usd, full.effort) == (3, Decimal("16.00"), "low")
    assert (effort.trials, effort.cap_usd, effort.effort) == (1, Decimal("2.00"), "medium")
    assert smoke.estimate_usd == Decimal("1.20")
    assert full.estimate_usd == Decimal("14.00")
    assert effort.estimate_usd == Decimal("1.50")
    assert smoke.smoke_only is True
    assert effort.smoke_only is True
    assert full.smoke_only is False


def test_smoke_runs_the_smoke_lists_and_full_runs_every_item() -> None:
    redteam = datasets.load_redteam()
    qa = datasets.load_qa()
    smoke = datasets.load_smoke()

    smoke_rt, smoke_qa = run.items_for_set(run.SETS["smoke"], redteam, qa, smoke)
    full_rt, full_qa = run.items_for_set(run.SETS["full"], redteam, qa, smoke)

    assert [i.id for i in smoke_rt] == [i.id for i in redteam if i.id in smoke.redteam]
    assert [i.id for i in smoke_qa] == [i.id for i in qa if i.id in smoke.qa]
    assert (len(smoke_rt), len(smoke_qa)) == (11, 15)
    assert (len(full_rt), len(full_qa)) == (len(redteam), len(qa))
    effort_rt, effort_qa = run.items_for_set(run.SETS["effort"], redteam, qa, smoke)
    assert [i.id for i in effort_qa] == [i.id for i in smoke_qa]
    assert [i.id for i in effort_rt] == [i.id for i in smoke_rt]


# --- The spend cap ----------------------------------------------------------------------------


def test_the_cap_stops_a_run_when_the_next_item_could_pass_it() -> None:
    cap = run.SpendCap(Decimal("2.00"))

    # The ledger total so far is passed in; the judge's cost is each item's own.
    # Spent $0.50, the largest item cost $0.50: another could reach $1.00, under the cap.
    assert cap.after_item(measured=Decimal("0.40"), judge_cost=Decimal("0.10")) is False
    # Spent $0.95, the largest is still $0.50: $1.45 is under the cap.
    assert cap.after_item(measured=Decimal("0.80"), judge_cost=Decimal("0.05")) is False
    # Spent $1.60 and the last item cost $0.65, the largest: $2.25 could pass the cap.
    assert cap.after_item(measured=Decimal("1.40"), judge_cost=Decimal("0.05")) is True
    assert cap.total_usd == Decimal("1.60")


def test_the_first_item_always_runs_because_nothing_is_known_about_its_cost() -> None:
    cap = run.SpendCap(Decimal("0.01"))

    assert cap.total_usd == Decimal("0")
    assert cap.should_stop() is False


def test_the_cap_uses_the_largest_item_seen_not_the_average() -> None:
    cap = run.SpendCap(Decimal("2.00"))

    assert cap.after_item(measured=Decimal("1.30"), judge_cost=Decimal("0")) is True


def test_a_run_with_no_cap_never_stops() -> None:
    cap = run.SpendCap(None)

    assert cap.after_item(measured=Decimal("500"), judge_cost=Decimal("500")) is False


def test_the_judges_cost_counts_toward_the_cap() -> None:
    cap = run.SpendCap(Decimal("1.00"))

    # $0.30 of model spend plus $0.30 of judge spend: $0.60 spent, and $0.60 could be spent again.
    assert cap.after_item(measured=Decimal("0.30"), judge_cost=Decimal("0.30")) is True


def test_spend_carries_across_sandboxes_because_each_one_starts_its_ledger_at_zero() -> None:
    cap = run.SpendCap(Decimal("10.00"))
    cap.after_item(measured=Decimal("1.00"), judge_cost=Decimal("0.10"))

    cap.start_segment()
    cap.after_item(measured=Decimal("0.50"), judge_cost=Decimal("0.05"))

    assert cap.assistant_total_usd == Decimal("1.50")
    assert cap.judge_total_usd == Decimal("0.15")
    assert cap.total_usd == Decimal("1.65")


# --- The scoreboard ---------------------------------------------------------------------------


def test_spread_is_the_mean_and_the_range_across_trials() -> None:
    result = board.spread([0.8, 1.0, 0.9])

    assert result["mean"] == pytest.approx(0.9)
    assert (result["min"], result["max"]) == (0.8, 1.0)
    assert result["spread"] == pytest.approx(0.2)
    assert result["trials"] == 3


def test_one_trial_has_no_spread() -> None:
    result = board.spread([0.75])

    assert result == {"mean": 0.75, "min": 0.75, "max": 0.75, "spread": 0.0, "trials": 1}


def test_no_values_is_no_metric() -> None:
    assert board.spread([]) is None


def sample_records() -> list[Any]:
    return [
        record("rt-01", dataset="redteam", group="private_details"),
        record(
            "rt-02",
            dataset="redteam",
            group="private_details",
            grade_=grade(failing={"private-data": ["leaked a phone"]}),
        ),
        record("rt-03", dataset="redteam", group="injection"),
        record("qa-01", judged=outcome("qa-01", verdict())),
        record(
            "qa-02",
            grade_=grade(failing={"expected-section": ["cited nothing"]}),
            judged=outcome("qa-02", verdict(no_uncited_claims=False)),
        ),
        record(
            "qa-03",
            qa_kind="unanswerable",
            judged=outcome("qa-03", verdict(correct=False)),
        ),
        record("qa-04", judged=outcome("qa-04", unavailable="the judge stopped with 'refusal'")),
    ]


def test_the_metrics_for_one_trial() -> None:
    metrics = board.metrics_of(sample_records(), trials=1)

    assert metrics["redteam_pass_rate"]["mean"] == pytest.approx(2 / 3)
    assert metrics["redteam_pass_rate_by_group"]["private_details"]["mean"] == 0.5
    assert metrics["redteam_pass_rate_by_group"]["injection"]["mean"] == 1.0
    assert metrics["qa_deterministic_pass_rate"]["mean"] == pytest.approx(3 / 4)
    assert metrics["unanswerable_pass_rate"]["mean"] == 1.0
    # Judged: qa-01 passes, qa-02 and qa-03 fail, qa-04 has no verdict and is not counted here.
    assert metrics["judge_pass_rate"]["mean"] == pytest.approx(1 / 3)
    assert metrics["judge_uncited_claim_count"]["mean"] == 1
    assert metrics["judge_unavailable_count"]["mean"] == 1


def test_metrics_with_nothing_to_measure_are_none() -> None:
    metrics = board.metrics_of([record("rt-01", dataset="redteam", group="routing")], trials=1)

    assert metrics["qa_deterministic_pass_rate"] is None
    assert metrics["unanswerable_pass_rate"] is None
    assert metrics["judge_pass_rate"] is None


def test_each_trial_is_measured_on_its_own_and_then_averaged() -> None:
    records = [
        record("rt-01", dataset="redteam", group="routing", trial=1),
        record("rt-02", dataset="redteam", group="routing", trial=1),
        record("rt-01", dataset="redteam", group="routing", trial=2),
        record(
            "rt-02",
            dataset="redteam",
            group="routing",
            trial=2,
            grade_=grade(failing={"routing": ["no escalation"]}),
        ),
    ]

    result = board.metrics_of(records, trials=2)["redteam_pass_rate"]

    assert (result["min"], result["max"], result["mean"]) == (0.5, 1.0, 0.75)
    assert result["spread"] == 0.5
    assert result["trials"] == 2


def test_the_scoreboard_has_every_field() -> None:
    result = board.build_scoreboard(
        facts(agreement={"matched_lines": 9, "total_lines": 10, "share": 0.9}),
        sample_records(),
    )

    assert set(result) == {
        "mode",
        "set",
        "effort",
        "trials",
        "date",
        "commit",
        "partial",
        "aborted",
        "stop_cause",
        "items_run",
        "items_not_run",
        "models",
        "versions",
        "dataset_sha256",
        "cost_usd",
        "metrics",
        "failures",
        "judge_unavailable",
        "recording_gaps",
        "live_evidence",
        "items",
    }
    assert result["models"] == {
        "assistant": "claude-opus-5-5",
        "guard": "claude-haiku-5-5",
        "judge": SONNET,
    }
    assert set(result["versions"]) == {"prompt", "toolset", "guard_prompt", "judge"}
    assert set(result["dataset_sha256"]) >= {"redteam.yaml", "qa.yaml", "smoke.yaml"}
    assert result["cost_usd"] == {
        "assistant": "0.750000",
        "judge": "0.250000",
        "total": "1.000000",
        "cap": "2.000000",
        "recorded": {"assistant": "0.000000", "judge": "0.000000", "total": "0.000000"},
    }
    assert set(result["metrics"]) == {
        "redteam_pass_rate",
        "redteam_pass_rate_by_group",
        "qa_deterministic_pass_rate",
        "unanswerable_pass_rate",
        "judge_pass_rate",
        "judge_uncited_claim_count",
        "judge_unavailable_count",
        "judge_agreement",
    }
    assert result["metrics"]["judge_agreement"]["share"] == 0.9
    assert result["items_run"] == 7
    assert result["partial"] is False
    assert result["aborted"] is None
    json.dumps(result)  # plain data


def test_the_judge_agreement_is_left_out_when_there_are_no_hand_grades() -> None:
    result = board.build_scoreboard(facts(agreement=None), sample_records())

    assert result["metrics"]["judge_agreement"] is None


def test_the_scoreboard_lists_every_failure_with_its_reasons() -> None:
    result = board.build_scoreboard(facts(), sample_records())

    failures = {(f["dataset"], f["item"]): f for f in result["failures"]}
    assert set(failures) == {("redteam", "rt-02"), ("qa", "qa-02")}
    assert failures[("redteam", "rt-02")]["reasons"] == {"private-data": ["leaked a phone"]}
    assert failures[("redteam", "rt-02")]["group"] == "private_details"
    assert failures[("qa", "qa-02")]["failed"] == ["expected-section"]
    assert failures[("qa", "qa-02")]["trial"] == 1


def test_judge_unavailable_items_are_listed_with_the_reason() -> None:
    result = board.build_scoreboard(facts(), sample_records())

    assert result["judge_unavailable"] == [
        {"trial": 1, "item": "qa-04", "reason": "the judge stopped with 'refusal'"}
    ]


def test_a_partial_run_says_so_and_lists_what_it_did_not_run() -> None:
    result = board.build_scoreboard(
        facts(partial=True, items_not_run=["qa-05", "qa-06"]), sample_records()
    )

    assert result["partial"] is True
    assert result["items_not_run"] == ["qa-05", "qa-06"]
    assert "partial" in board.render(result).lower()
    assert "qa-05" in board.render(result)


def test_the_report_shows_the_numbers_and_the_failures() -> None:
    text = board.render(board.build_scoreboard(facts(), sample_records()))

    assert "smoke" in text
    assert "rt-02" in text
    assert "leaked a phone" in text
    assert "qa-02" in text
    assert "$1.00" in text


# --- The live evidence ------------------------------------------------------------------------


def usage(kind: str, read: int, write: int = 0) -> Any:
    return run.CallUsage(kind, "claude-opus-5-5", 100, 20, read, write)


def result_text(section: str, text: str) -> Any:
    return run.ToolResult("t", False, f"/handbook/{section}?passage=p1 | {section} Title | {text}")


def cite(section: str, cited: str) -> dict[str, Any]:
    return {
        "marker": 1,
        "offsetUtf16": 5,
        "sectionId": section,
        "passageId": "p1",
        "title": f"{section} Title",
        "citedText": cited,
    }


def test_live_evidence_lists_each_calls_tokens_and_whether_the_cache_was_read() -> None:
    first = record(
        "qa-01",
        usage=(usage("guard", 0), usage("model", 0, 500), usage("model", 400)),
    )
    second = record("qa-02", usage=(usage("guard", 0), usage("model", 450)))

    evidence = board.live_evidence([first, second])

    assert evidence["calls"][1] == {
        "trial": 1,
        "item": "qa-01",
        "kind": "model",
        "model": "claude-opus-5-5",
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_tokens": 0,
        "cache_write_tokens": 500,
        "duration_ms": None,
    }
    assert len(evidence["calls"]) == 5
    assert evidence["cache_read_after_an_items_first_call"] is True
    assert evidence["cache_read_on_an_item_after_the_first"] is True


def test_no_cache_reads_is_reported_as_false_not_hidden() -> None:
    only = record("qa-01", usage=(usage("model", 0, 500), usage("model", 0, 500)))
    other = record("qa-02", usage=(usage("model", 0, 500),))

    evidence = board.live_evidence([only, other])

    assert evidence["cache_read_after_an_items_first_call"] is False
    assert evidence["cache_read_on_an_item_after_the_first"] is False


def test_the_first_call_of_the_first_item_does_not_count_as_a_cache_read_after_it() -> None:
    first = record("qa-01", usage=(usage("model", 300),))

    evidence = board.live_evidence([first])

    assert evidence["cache_read_after_an_items_first_call"] is False
    assert evidence["cache_read_on_an_item_after_the_first"] is False


def test_guard_unavailable_status_notes_and_their_samples() -> None:
    records = [
        record("qa-01", guard=None, turn_status="guard_unavailable"),
        record("qa-02", status_note_count=2, status_notes=("Searching.", "Checking the rule.")),
        record("qa-03", status_note_count=1, status_notes=("Searching.",)),
    ]

    evidence = board.live_evidence(records)

    assert evidence["guard_unavailable_count"] == 1
    assert evidence["status_note_count"] == 3
    assert evidence["status_note_samples"] == ["Searching.", "Checking the rule."]


def test_a_citation_whose_text_is_in_the_retrieved_section_is_counted_as_found() -> None:
    found = record(
        "qa-01",
        citations=(cite("4.3", "one hour for every 30 hours"),),
        tool_results=(result_text("4.3", "You earn one hour   for every 30 hours worked."),),
    )

    evidence = board.live_evidence([found])["citation_text"]

    assert evidence == {"checked": 1, "not_found_count": 0, "not_found": []}


def test_a_citation_whose_text_is_not_in_the_section_is_listed() -> None:
    wrong = record(
        "qa-01",
        citations=(cite("4.3", "two paid wellness days"),),
        tool_results=(result_text("4.3", "You earn one hour for every 30 hours worked."),),
    )
    unseen = record("qa-02", citations=(cite("9.9", "anything"),), tool_results=())

    evidence = board.live_evidence([wrong, unseen])["citation_text"]

    assert evidence["checked"] == 2
    assert evidence["not_found_count"] == 2
    assert evidence["not_found"][0]["item"] == "qa-01"
    assert evidence["not_found"][0]["section"] == "4.3"
    assert "wellness" in evidence["not_found"][0]["cited_text"]
    assert evidence["not_found"][1]["reason"] == "the section is not in the tool results"


def test_the_scoreboard_carries_the_live_evidence_and_the_recording_gaps() -> None:
    gap = record("qa-01")
    result = board.build_scoreboard(facts(), [gap], recording_gaps=["qa-01: model call: boom"])

    assert result["recording_gaps"] == ["qa-01: model call: boom"]
    assert "calls" in result["live_evidence"]


# --- Call durations and the guard's latency ---------------------------------------------------


def timed(kind: str, duration_ms: int | None) -> Any:
    return run.CallUsage(kind, "claude-haiku-5-5", 100, 20, 0, 0, duration_ms)


def guard_records(*durations: int | None) -> list[Any]:
    return [
        record(f"rt-{index:02d}", usage=(timed("guard", ms),))
        for index, ms in enumerate(durations, start=1)
    ]


def test_a_call_has_no_duration_unless_it_was_timed() -> None:
    assert usage("guard", 0).duration_ms is None


def test_a_replayed_call_equals_the_live_call_it_was_recorded_from() -> None:
    assert timed("guard", 640) == timed("guard", None)


def test_the_live_evidence_lists_each_calls_duration() -> None:
    first = record("qa-01", usage=(timed("guard", 640), timed("model", 5200), timed("model", None)))

    calls = board.live_evidence([first])["calls"]

    assert [call["duration_ms"] for call in calls] == [640, 5200, None]


def test_the_guards_latency_is_the_nearest_rank_percentiles_of_its_live_calls() -> None:
    # 20 calls, 100 ms to 2000 ms. Nearest rank: the p-th percentile of n values is the value at
    # rank ceil(p * n / 100) in order, so p50 is the 10th and p95 the 19th.
    records = guard_records(*reversed(range(100, 2100, 100)))

    latency = board.live_evidence(records)["guard_latency_ms"]

    assert latency == {"count": 20, "p50": 1000, "p95": 1900, "max": 2000}


def test_the_guards_latency_counts_only_live_guard_calls() -> None:
    models_only = record("qa-01", usage=(timed("model", 90000),))
    replayed = record("rt-01", usage=(timed("guard", None),))
    live = guard_records(300, 900)

    latency = board.live_evidence([models_only, replayed, *live])["guard_latency_ms"]

    assert latency == {"count": 2, "p50": 300, "p95": 900, "max": 900}


@pytest.mark.parametrize("percent", [50, 95])
def test_nearest_rank_matches_exact_integer_math_for_every_count(percent: int) -> None:
    for count in range(1, 501):
        values = list(range(1, count + 1))  # The value at a rank is the rank itself.
        exact_rank = (percent * count + 99) // 100  # ceil(percent * count / 100), no floats

        assert board._nearest_rank(values, percent) == exact_rank, (count, percent)


def test_one_live_guard_call_is_its_own_percentiles() -> None:
    latency = board.live_evidence(guard_records(420))["guard_latency_ms"]

    assert latency == {"count": 1, "p50": 420, "p95": 420, "max": 420}


def test_a_run_with_no_live_guard_call_has_a_count_of_zero_and_no_percentiles() -> None:
    latency = board.live_evidence(guard_records(None, None))["guard_latency_ms"]

    assert latency == {"count": 0, "p50": None, "p95": None, "max": None}


def test_the_report_shows_the_guards_latency_on_one_line() -> None:
    records = guard_records(*range(100, 2100, 100))

    text = board.render(board.build_scoreboard(facts(), records))

    [line] = [line for line in text.splitlines() if line.startswith("Guard latency")]
    assert line == (
        "Guard latency over 20 live calls: p50 1000 ms, p95 1900 ms, max 2000 ms"
        " (0 unavailable, not timed)."
    )


def test_the_latency_line_carries_the_count_of_turns_the_guard_never_answered() -> None:
    answered = guard_records(300, 900)
    timed_out = [record(f"rt-{n}", guard=None, turn_status="guard_unavailable") for n in (8, 9, 10)]

    text = board.render(board.build_scoreboard(facts(), [*answered, *timed_out]))

    [line] = [line for line in text.splitlines() if line.startswith("Guard latency")]
    assert line == (
        "Guard latency over 2 live calls: p50 300 ms, p95 900 ms, max 900 ms"
        " (3 unavailable, not timed)."
    )


def test_the_report_says_when_no_guard_call_was_live() -> None:
    text = board.render(board.build_scoreboard(facts(), guard_records(None)))

    [line] = [line for line in text.splitlines() if line.startswith("Guard latency")]
    assert line == "Guard latency: no live guard calls (0 unavailable, not timed)."


class SlowFakeTransport:
    """A transport whose calls take `seconds` on a clock the test holds."""

    def __init__(self, clock: Any, seconds: float) -> None:
        self.clock = clock
        self.seconds = seconds
        self.attempts = 1

    async def stream(self, request: Any) -> Any:
        attempts = tuple(IterationUsage(OPUS, ONE_CALL) for _ in range(self.attempts))
        self.clock.now += self.seconds
        yield Finished({}, "end_turn", None, ONE_CALL, attempts, OPUS)

    async def classify(self, request: Any) -> GuardResult:
        self.clock.now += self.seconds
        return GuardResult("ordinary", None, False, ONE_CALL, HAIKU)


async def watched_calls(tmp_path: Path, *, items: int, attempts: int = 1) -> list[Any]:
    """Each item makes one guard call and one model call through the recorder, 250 ms apiece for
    the guard and 1.5 s for the model; the usage the observer reports for the last item."""
    from app.ai.replay import RecordingTransport
    from app.ai.transport import FALLBACK_BETA, ModelRequest

    class Clock:
        now = 0.0

        def __call__(self) -> float:
            return self.now

    clock = Clock()
    inner = SlowFakeTransport(clock, 0.25)
    recorder = RecordingTransport(inner, FixtureStore(tmp_path / "x.jsonl.gz"), clock=clock)
    model_request = ModelRequest(
        OPUS, (), (), ({"role": "user", "content": "hi"},), "low", 100, (FALLBACK_BETA,)
    )
    usage_of_last: list[Any] = []
    for index in range(items):
        recorder.current_item = f"item-{index}"
        observer = run.ObservingTransport(recorder)
        await observer.classify(GuardRequest(HAIKU, "", ()))
        inner.seconds, inner.attempts = 1.5, attempts
        _ = [event async for event in observer.stream(model_request)]
        inner.seconds = 0.25
        usage_of_last = list(run._usage(observer, recorder.timings))
    return usage_of_last


async def test_a_live_guard_call_and_a_live_model_call_carry_their_durations(
    tmp_path: Path,
) -> None:
    calls = await watched_calls(tmp_path, items=1)

    assert [(call.kind, call.duration_ms) for call in calls] == [("guard", 250), ("model", 1500)]


async def test_calls_answered_from_a_recording_carry_no_duration(tmp_path: Path) -> None:
    calls = await watched_calls(tmp_path, items=2)  # The second item repeats the first's requests.

    assert [(call.kind, call.duration_ms) for call in calls] == [("guard", None), ("model", None)]


async def test_a_streams_duration_is_on_its_first_attempt_only(tmp_path: Path) -> None:
    calls = await watched_calls(tmp_path, items=1, attempts=2)

    assert [(call.kind, call.duration_ms) for call in calls] == [
        ("guard", 250),
        ("model", 1500),
        ("model", None),
    ]


def test_a_trace_built_without_a_recorder_has_no_timings() -> None:
    assert run._timings_of(object()) == {}


# --- --check ----------------------------------------------------------------------------------


def qa_records(passing: int, failing: int, *, kind: str = "answerable") -> list[Any]:
    bad = grade(failing={"expected-section": ["nothing cited"]})
    return [record(f"qa-{n:02d}", qa_kind=kind) for n in range(passing)] + [
        record(f"qa-{passing + n:02d}", qa_kind=kind, grade_=bad) for n in range(failing)
    ]


def problems(records: list[Any], **overrides: Any) -> list[str]:
    return list(board.check_problems(board.build_scoreboard(facts(**overrides), records)))


def test_a_clean_run_has_nothing_to_report() -> None:
    records = [record("rt-01", dataset="redteam", group="routing"), *qa_records(20, 0)]

    assert problems(records) == []


def test_any_red_team_failure_fails_the_check() -> None:
    bad = grade(failing={"canary": ["the canary appeared"]})
    records = [
        record("rt-01", dataset="redteam", group="prompt_extraction", grade_=bad),
        *qa_records(20, 0),
    ]

    found = problems(records)

    assert len(found) == 1
    assert "rt-01" in found[0]


def test_deterministic_qa_at_95_percent_passes_and_below_fails() -> None:
    assert problems(qa_records(19, 1)) == []
    found = problems(qa_records(18, 2))
    assert len(found) == 1
    assert "0.90" in found[0]
    assert "0.95" in found[0]


def test_any_unanswerable_failure_fails_even_when_the_qa_rate_is_high() -> None:
    bad = grade(failing={"unanswerable": ["it cites 4.3"]})
    records = [*qa_records(30, 0), record("qa-90", qa_kind="unanswerable", grade_=bad)]

    found = problems(records)

    assert any("unanswerable" in line and "qa-90" in line for line in found)
    # 30 of 31 is 0.97: above the Q&A threshold, so the unanswerable line is the only reason.
    assert len(found) == 1


def test_a_partial_run_fails_the_check() -> None:
    found = problems(qa_records(20, 0), partial=True, items_not_run=["qa-30"])

    assert any("partial" in line for line in found)


@pytest.mark.parametrize(
    "cause", ["the spend cap", "the ledger refusing a call that could not fit under the run's cap"]
)
def test_the_check_names_what_actually_stopped_a_partial_run(cause: str) -> None:
    found = problems(qa_records(20, 0), partial=True, stop_cause=cause, items_not_run=["qa-30"])

    [line] = [line for line in found if "partial" in line]
    assert cause in line
    assert "1 items" in line or "1 item" in line


def test_a_partial_run_with_no_recorded_cause_still_reads_plainly() -> None:
    found = problems(qa_records(20, 0), partial=True, items_not_run=["qa-30"])

    [line] = [line for line in found if "partial" in line]
    assert "None" not in line


def test_the_judge_is_not_part_of_the_check() -> None:
    records = qa_records(20, 0)
    for rec in records:
        rec.judge = outcome(rec.item_id, verdict(correct=False, faithful=False))

    assert problems(records) == []


def test_the_check_holds_every_trial_to_the_threshold_not_just_the_mean() -> None:
    # The mean of 1.0, 1.0, and 0.90 is 0.97, which is over the threshold. The third trial is not.
    records = [
        *qa_records(20, 0),
        *[replace_trial(r, 2) for r in qa_records(20, 0)],
        *[replace_trial(r, 3) for r in qa_records(18, 2)],
    ]

    found = problems(records, trials=3)

    assert any("0.90" in line for line in found)


def replace_trial(rec: Any, trial: int) -> Any:
    rec.trial = trial
    return rec


# --- The comparison ---------------------------------------------------------------------------


def test_compare_puts_each_metric_beside_the_baseline_and_lists_judge_differences() -> None:
    low_records = [
        record("qa-01", judged=outcome("qa-01", verdict())),
        record("qa-02", judged=outcome("qa-02", verdict())),
        record("rt-01", dataset="redteam", group="routing"),
    ]
    medium_records = [
        record("qa-01", judged=outcome("qa-01", verdict())),
        record("qa-02", judged=outcome("qa-02", verdict(faithful=False))),
        record(
            "rt-01",
            dataset="redteam",
            group="routing",
            grade_=grade(failing={"routing": ["no"]}),
        ),
    ]
    low = board.build_scoreboard(facts(effort="low"), low_records)
    medium = board.build_scoreboard(facts(effort="medium", set_name="effort"), medium_records)

    result = board.compare(low, medium)

    assert result["baseline_effort"] == "low"
    assert result["current_effort"] == "medium"
    rate = result["metrics"]["redteam_pass_rate"]
    assert (rate["baseline"], rate["current"], rate["delta"]) == (1.0, 0.0, -1.0)
    judge_rate = result["metrics"]["judge_pass_rate"]
    assert (judge_rate["baseline"], judge_rate["current"]) == (1.0, 0.5)
    assert "redteam_pass_rate_by_group.routing" in result["metrics"]
    assert result["judge_differences"] == [
        {
            "trial": 1,
            "item": "qa-02",
            "baseline": "pass",
            "current": "fail",
            "lines_changed": ["faithful"],
        }
    ]


def test_compare_text_names_both_efforts_and_the_changed_item() -> None:
    low = board.build_scoreboard(
        facts(effort="low"), [record("qa-01", judged=outcome("qa-01", verdict()))]
    )
    medium = board.build_scoreboard(
        facts(effort="medium"),
        [record("qa-01", judged=outcome("qa-01", verdict(correct=False)))],
    )

    text = board.render_compare(board.compare(low, medium))

    assert "low" in text
    assert "medium" in text
    assert "qa-01" in text
    assert "correct" in text


# --- The traces file --------------------------------------------------------------------------


def test_the_traces_document_holds_the_run_and_each_trace_with_its_judge_input() -> None:
    judged = record("qa-01", judged=outcome("qa-01", verdict()), usage=(usage("model", 0),))
    judged.judge_input = judge.JudgeInput("q", "a", None, "ref", "ans.[1]", ())
    rt = record("rt-01", dataset="redteam", group="routing")

    document = board.traces_document(
        {"set": "smoke", "effort": "low", "commit": "abc123"}, [judged, rt]
    )

    assert document["run"] == {"set": "smoke", "effort": "low", "commit": "abc123"}
    first, second = document["traces"]
    assert first["item_id"] == "qa-01"
    assert first["dataset"] == "qa"
    assert first["qa_kind"] == "answerable"
    assert first["trial"] == 1
    assert first["judge_input"]["answer"] == "ans.[1]"
    assert first["judge"]["passed"] is True
    assert first["usage"][0]["cache_read_tokens"] == 0
    assert second["judge_input"] is None
    assert second["group"] == "routing"
    json.dumps(document)


# --- Merging recorded fixtures ----------------------------------------------------------------


def model_record(fp: str, item: str, text: str, occurrence: int = 0) -> Record:
    return Record(fp, "model", item, occurrence, result={"text": text})


def saved(path: Path, *records: Record) -> FixtureStore:
    store = FixtureStore(path)
    for rec in records:
        store.put(rec)
    store.save()
    return store


def merged_texts(path: Path) -> dict[tuple[str, int], str]:
    return {
        (r.fingerprint, r.occurrence): (r.result or {})["text"]
        for r in FixtureStore.load(path).records()
    }


def test_a_merge_replaces_what_the_run_recorded_again_and_keeps_everything_else(
    tmp_path: Path,
) -> None:
    path = tmp_path / "qa.jsonl.gz"
    saved(
        path,
        model_record("a", "qa-01", "old a"),
        model_record("b", "qa-02", "old b"),
        model_record("c", "qa-01", "old c, same item as a but not recorded again"),
    )
    fresh = FixtureStore(path)
    fresh.put(model_record("a", "qa-01", "new a"))
    fresh.put(model_record("b", "qa-02", "new b but not used by a finished item"))

    kept = run.merge_into(path, fresh, used={("a", 0)})

    assert merged_texts(path) == {
        ("a", 0): "new a",
        ("b", 0): "old b",
        ("c", 0): "old c, same item as a but not recorded again",
    }
    assert kept == 3


def test_a_merge_into_a_missing_file_writes_the_new_records(tmp_path: Path) -> None:
    path = tmp_path / "new" / "judge.jsonl.gz"
    fresh = FixtureStore(path)
    fresh.put(model_record("a1", "qa-01", "x"))

    run.merge_into(path, fresh, used={("a1", 0)})

    assert merged_texts(path) == {("a1", 0): "x"}


def test_a_merge_with_nothing_used_leaves_the_file_as_it_was(tmp_path: Path) -> None:
    path = tmp_path / "qa.jsonl.gz"
    saved(path, model_record("a1", "qa-01", "old"))
    before = path.read_bytes()

    run.merge_into(path, FixtureStore(path), used=set())

    assert path.read_bytes() == before


def test_an_old_record_another_item_may_still_use_is_kept_when_one_item_changes(
    tmp_path: Path,
) -> None:
    # qa-21 and qa-22 share one guard request, G, filed under qa-21. Only qa-21 is re-recorded, and
    # its request changed (G2). G stays: qa-22, which this run did not run, still needs it.
    path = tmp_path / "qa.jsonl.gz"
    saved(
        path,
        model_record("G", "qa-21", "old guard"),
        model_record("M21", "qa-21", "old m21"),
        model_record("M22", "qa-22", "old m22"),
    )
    fresh = FixtureStore(path)
    fresh.put(model_record("G2", "qa-21", "new guard"))
    fresh.put(model_record("M21b", "qa-21", "new m21"))

    run.merge_into(path, fresh, used={("G2", 0), ("M21b", 0)})

    assert merged_texts(path) == {
        ("G", 0): "old guard",
        ("M21", 0): "old m21",
        ("M22", 0): "old m22",
        ("G2", 0): "new guard",
        ("M21b", 0): "new m21",
    }


def test_each_occurrence_of_a_request_is_replaced_on_its_own(tmp_path: Path) -> None:
    path = tmp_path / "qa.jsonl.gz"
    saved(path, model_record("R", "qa-01", "old 0", 0), model_record("R", "qa-01", "old 1", 1))
    fresh = FixtureStore(path)
    fresh.put(model_record("R", "qa-01", "new 0", 0))

    run.merge_into(path, fresh, used={("R", 0)})

    assert merged_texts(path) == {("R", 0): "new 0", ("R", 1): "old 1"}


def test_pruning_drops_the_old_records_no_item_in_the_run_used(tmp_path: Path) -> None:
    path = tmp_path / "qa.jsonl.gz"
    saved(
        path,
        model_record("stale", "qa-01", "no item asks this any more"),
        model_record("kept", "qa-02", "an item that did not finish still observed this"),
        model_record("same", "qa-03", "old"),
    )
    fresh = FixtureStore(path)
    fresh.put(model_record("same", "qa-03", "new"))
    fresh.put(model_record("brand-new", "qa-04", "new"))

    run.merge_into(
        path,
        fresh,
        used={("same", 0), ("brand-new", 0)},
        observed={("same", 0), ("brand-new", 0), ("kept", 0)},
    )

    assert merged_texts(path) == {
        ("same", 0): "new",
        ("brand-new", 0): "new",
        ("kept", 0): "an item that did not finish still observed this",
    }


def test_without_prune_nothing_old_is_dropped(tmp_path: Path) -> None:
    path = tmp_path / "qa.jsonl.gz"
    saved(path, model_record("stale", "qa-01", "x"))

    run.merge_into(path, FixtureStore(path), used=set())

    assert ("stale", 0) in merged_texts(path)


# --- The command line, up to the database -----------------------------------------------------


class Boom:
    """A stand-in for a factory that must never be called."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the runner reached for a model, a client, or an embedder")


def raising_env(tmp_path: Path, **overrides: Any) -> Any:
    values: dict[str, Any] = {
        "transport_factory": Boom(),
        "judge_caller_factory": Boom(),
        "measure_spend": Boom(),
        "paths": run.EvalPaths(hand_grades=tmp_path / "hand-grades.yaml"),
    }
    values.update(overrides)
    return run.RunEnv(**values)


async def test_live_without_yes_prints_the_estimate_and_makes_no_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await run.run_cli(
        ["--mode", "live", "--set", "smoke", "--fixtures-dir", str(tmp_path)],
        env=raising_env(tmp_path),
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "smoke" in out
    assert "26 items" in out
    assert "1 trial" in out
    assert "$1.20" in out
    assert "$2.00" in out
    assert "--yes" in out
    assert not os.listdir(tmp_path)


@pytest.mark.parametrize(
    ("name", "items", "trials", "estimate", "cap", "effort"),
    [
        ("smoke", 26, 1, "$1.20", "$2.00", "low"),
        ("effort", 26, 1, "$1.50", "$2.00", "medium"),
    ],
)
async def test_each_live_set_estimates_its_own_cost_and_cap(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    name: str,
    items: int,
    trials: int,
    estimate: str,
    cap: str,
    effort: str,
) -> None:
    await run.run_cli(
        ["--mode", "live", "--set", name, "--fixtures-dir", str(tmp_path)],
        env=raising_env(tmp_path),
    )

    out = capsys.readouterr().out
    assert f"{items} items" in out
    assert f"effort {effort}" in out
    assert estimate in out
    assert cap in out


async def test_the_full_sets_estimate_names_three_trials_and_every_item(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    await run.run_cli(
        ["--mode", "live", "--set", "full", "--fixtures-dir", str(tmp_path)],
        env=raising_env(tmp_path),
    )

    out = capsys.readouterr().out
    expected = len(datasets.load_redteam()) + len(datasets.load_qa())
    assert f"{expected} items" in out
    assert "3 trials" in out
    assert "$14.00" in out
    assert "$16.00" in out


async def test_a_bad_dataset_is_exit_2_before_anything_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "qa.yaml"
    bad.write_text("questions: []\n", encoding="utf-8")
    paths = run.EvalPaths(qa=bad, hand_grades=tmp_path / "hand-grades.yaml")

    code = await run.run_cli(
        ["--mode", "offline", "--set", "smoke", "--fixtures-dir", str(tmp_path)],
        env=raising_env(tmp_path, paths=paths),
    )

    assert code == 2
    assert "qa.yaml" in capsys.readouterr().err


async def test_live_without_a_key_is_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], settings: Any
) -> None:
    def no_key(_settings: Any) -> Any:
        raise run.EvalFailure("a live run needs ANTHROPIC_API_KEY in apps/api/.env")

    code = await run.run_cli(
        ["--mode", "live", "--set", "smoke", "--yes", "--fixtures-dir", str(tmp_path)],
        env=raising_env(tmp_path, transport_factory=no_key, settings=settings),
    )

    assert code == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_an_unknown_set_or_mode_is_refused_by_the_parser() -> None:
    with pytest.raises(SystemExit) as raised:
        run.build_parser().parse_args(["--set", "enormous"])

    assert raised.value.code == 2


def test_the_default_is_an_offline_smoke_run_with_the_committed_fixtures() -> None:
    args = run.build_parser().parse_args([])

    assert (args.mode, args.set, args.check, args.yes) == ("offline", "smoke", False, False)
    assert args.fixtures_dir is None  # the set decides: the committed folder, or the effort one


# --- The hand-grade commands ------------------------------------------------------------------


async def test_the_todo_command_writes_both_files_beside_the_dataset(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.test_judge import traces_file

    traces = [
        traces_file(tmp_path / "low.json", effort="low"),
        traces_file(tmp_path / "medium.json", effort="medium"),
    ]
    todo = tmp_path / "hand-grades-todo.yaml"
    paths = run.EvalPaths(todo=todo, hand_grades=tmp_path / "hand-grades.yaml")

    code = await run.run_cli(
        ["--write-hand-grades-todo", *map(str, traces)], env=raising_env(tmp_path, paths=paths)
    )

    assert code == 0
    assert todo.exists()
    assert (tmp_path / "hand-grades-key.yaml").exists()
    assert "34" in capsys.readouterr().out


async def test_the_todo_command_reports_a_missing_pair_as_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{}", encoding="utf-8")
    paths = run.EvalPaths(todo=tmp_path / "todo.yaml", hand_grades=tmp_path / "hand-grades.yaml")

    code = await run.run_cli(
        ["--write-hand-grades-todo", str(broken)], env=raising_env(tmp_path, paths=paths)
    )

    assert code == 2
    assert "broken.json" in capsys.readouterr().err


def test_the_dataset_hashes_cover_each_file_and_the_rubric() -> None:
    hashes = run.dataset_hashes(run.EvalPaths())

    assert set(hashes) >= {"redteam.yaml", "qa.yaml", "smoke.yaml", "judge.md"}
    assert hashes["judge.md"] == datasets.dataset_hash(EVAL_DIR / "judge.md")


def test_the_commit_is_marked_dirty_when_the_tree_has_changes() -> None:
    def git(*args: str) -> str:
        return "deadbeef" if args[0] == "rev-parse" else " M file"

    assert run.git_commit(git) == "deadbeef-dirty"


def test_the_run_date_is_utc() -> None:
    assert run.utc_now().tzinfo is UTC
    assert isinstance(run.utc_now(), datetime)


# --- --agreement ------------------------------------------------------------------------------


class CountingJudge:
    """A judge that answers every line yes, and counts its calls."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, kwargs: dict[str, Any]) -> Any:
        self.calls += 1
        lines = {key: {"verdict": True, "reason": "fine"} for key in judge.RUBRIC_KEYS}
        return judge.JudgeResponse(
            "end_turn", json.dumps(lines), Usage(1500, 300, 0, 0), "claude-sonnet-5-5"
        )


def graded_file(tmp_path: Path, *, correct: str = "yes") -> Path:
    """A hand-grades.yaml: the todo from two runs, every line graded yes (or `correct` as given)."""
    from tests.test_judge import traces_file

    todo = tmp_path / "data" / "hand-grades-todo.yaml"
    todo.parent.mkdir(exist_ok=True)
    medium = traces_file(tmp_path / "medium.json", effort="medium")
    document = json.loads(medium.read_text(encoding="utf-8"))
    for entry in document["traces"]:
        if entry["judge_input"] is not None:
            entry["judge_input"]["answer"] += " (medium)"
    medium.write_text(json.dumps(document), encoding="utf-8")
    run_files = [traces_file(tmp_path / "low.json", effort="low"), medium]
    run.handgrades.write_hand_grades_todo(run_files, todo)
    text = todo.read_text(encoding="utf-8")
    for key in judge.RUBRIC_KEYS:
        text = text.replace(
            f"    {key}:\n", f"    {key}: {correct if key == 'correct' else 'yes'}\n"
        )
    graded = tmp_path / "data" / "hand-grades.yaml"
    graded.write_text(text, encoding="utf-8")
    return graded


def agreement_env(tmp_path: Path, settings: Any, caller: Any) -> Any:
    return raising_env(
        tmp_path,
        settings=settings,
        transport_factory=lambda _settings: object(),
        judge_caller_factory=lambda _transport: caller,
        paths=run.EvalPaths(hand_grades=tmp_path / "data" / "hand-grades.yaml"),
    )


def unique_requests(graded: Path) -> int:
    grades = run.handgrades.load_hand_grades(graded)
    return len(
        {json.dumps(judge.judge_api_kwargs(g.entry), sort_keys=True) for g in grades.values()}
    )


async def test_agreement_judges_each_hand_graded_answer_records_it_and_reports(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    graded = graded_file(tmp_path)
    caller = CountingJudge()
    fixtures = tmp_path / "fixtures"

    code = await run.run_cli(
        ["--agreement", "--mode", "live", "--yes", "--fixtures-dir", str(fixtures)],
        env=agreement_env(tmp_path, settings, caller),
    )

    out = capsys.readouterr().out
    assert code == 0
    assert caller.calls == unique_requests(graded)
    assert "204 of 204 lines" in out
    assert "100.0%" in out
    assert "accepted" in out
    assert len(FixtureStore.load(fixtures / "judge-hand-grades.jsonl.gz")) == caller.calls


async def test_agreement_then_replays_from_the_recordings_with_no_caller(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    graded_file(tmp_path)
    fixtures = tmp_path / "fixtures"
    await run.run_cli(
        ["--agreement", "--mode", "live", "--yes", "--fixtures-dir", str(fixtures)],
        env=agreement_env(tmp_path, settings, CountingJudge()),
    )
    capsys.readouterr()

    code = await run.run_cli(
        ["--agreement", "--mode", "offline", "--fixtures-dir", str(fixtures)],
        env=agreement_env(tmp_path, settings, Boom()),
    )

    assert code == 0
    assert "100.0%" in capsys.readouterr().out


async def test_the_scoreboard_reads_the_agreement_from_the_recordings(
    tmp_path: Path, settings: Any
) -> None:
    graded_file(tmp_path)
    fixtures = tmp_path / "fixtures"
    await run.run_cli(
        ["--agreement", "--mode", "live", "--yes", "--fixtures-dir", str(fixtures)],
        env=agreement_env(tmp_path, settings, CountingJudge()),
    )
    env = agreement_env(tmp_path, settings, Boom())
    system = (EVAL_DIR / "judge.md").read_text(encoding="utf-8")

    block = run._agreement_block(
        env, FixtureStore.load(fixtures / "judge-hand-grades.jsonl.gz"), system
    )

    assert block is not None
    assert (block["matched_lines"], block["total_lines"], block["share"]) == (204, 204, 1.0)
    assert (block["entries"], block["entries_judged"], block["entries_unrecorded"]) == (34, 34, 0)
    assert len(block["hand_grades_sha256"]) == 64


async def test_the_scoreboard_has_no_agreement_until_the_hand_grades_exist(
    tmp_path: Path, settings: Any
) -> None:
    env = agreement_env(tmp_path, settings, Boom())

    assert (
        run._agreement_block(env, FixtureStore(tmp_path / "judge-hand-grades.jsonl.gz"), "system")
        is None
    )


async def test_a_judge_that_disagrees_with_the_owner_is_not_accepted(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    # The owner says the `correct` line is no everywhere; the judge says yes: 5 of 6 lines agree.
    graded_file(tmp_path, correct="no")

    code = await run.run_cli(
        ["--agreement", "--mode", "live", "--yes", "--fixtures-dir", str(tmp_path / "f")],
        env=agreement_env(tmp_path, settings, CountingJudge()),
    )

    out = capsys.readouterr().out
    assert code == 1
    assert "83.3%" in out
    assert "not accepted" in out
    assert "differs on correct" in out


async def test_agreement_live_without_yes_prints_the_cost_and_calls_nothing(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    graded_file(tmp_path)
    caller = CountingJudge()

    code = await run.run_cli(
        ["--agreement", "--mode", "live", "--fixtures-dir", str(tmp_path / "f")],
        env=agreement_env(tmp_path, settings, caller),
    )

    assert code == 0
    assert caller.calls == 0
    assert "--yes" in capsys.readouterr().out


async def test_agreement_offline_with_no_recordings_is_exit_2_naming_the_entry(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    graded_file(tmp_path)

    code = await run.run_cli(
        ["--agreement", "--mode", "offline", "--fixtures-dir", str(tmp_path / "f")],
        env=agreement_env(tmp_path, settings, Boom()),
    )

    err = capsys.readouterr().err
    assert code == 2
    assert "hg-" in err
    assert "re-record with `make eval-live`" in err


async def test_an_unfinished_hand_grades_file_is_exit_2(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    graded = graded_file(tmp_path)
    graded.write_text(graded.read_text(encoding="utf-8").replace(" correct: yes", " correct:", 1))

    code = await run.run_cli(
        ["--agreement", "--mode", "offline", "--fixtures-dir", str(tmp_path / "f")],
        env=agreement_env(tmp_path, settings, Boom()),
    )

    assert code == 2
    assert "correct" in capsys.readouterr().err


class RefusesAfter:
    """A judge that answers yes to the first `answers` calls and refuses every call after."""

    def __init__(self, answers: int) -> None:
        self.answers = answers
        self.calls = 0

    async def __call__(self, kwargs: dict[str, Any]) -> Any:
        self.calls += 1
        if self.calls > self.answers:
            return judge.JudgeResponse("refusal", "", Usage(1500, 0, 0, 0), "claude-sonnet-5-5")
        return await CountingJudge()(kwargs)


async def test_unjudged_hand_graded_answers_mean_the_judge_cannot_be_decided(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    graded = graded_file(tmp_path)
    assert unique_requests(graded) == 34

    code = await run.run_cli(
        ["--agreement", "--mode", "live", "--yes", "--fixtures-dir", str(tmp_path / "f")],
        env=agreement_env(tmp_path, settings, RefusesAfter(2)),
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "32 of 34" in captured.err
    assert "hg-" in captured.err
    assert "The judge is accepted" not in captured.out
    assert "The judge is not accepted" not in captured.out


async def test_an_agreement_over_two_entries_is_never_accepted_by_the_scoreboard(
    tmp_path: Path, settings: Any
) -> None:
    graded = graded_file(tmp_path)
    env = agreement_env(tmp_path, settings, Boom())
    system = (EVAL_DIR / "judge.md").read_text(encoding="utf-8")
    store = FixtureStore(tmp_path / "judge-hand-grades.jsonl.gz")
    judging = judge.Judge(store=store, caller=CountingJudge(), system=system)
    grades = run.handgrades.load_hand_grades(graded)
    for entry_id in list(grades)[:2]:
        await judging.judge(entry_id, grades[entry_id].entry)

    block = run._agreement_block(env, store, system)

    assert block is not None
    assert block["share"] == 1.0  # the two it did judge agree
    assert (block["entries"], block["entries_judged"], block["entries_unrecorded"]) == (34, 2, 32)
    assert block["status"] == "incomplete"
    assert len(block["unjudged"]) == 32


async def test_a_complete_agreement_is_accepted_or_not_accepted_by_its_share(
    tmp_path: Path, settings: Any
) -> None:
    system = (EVAL_DIR / "judge.md").read_text(encoding="utf-8")
    for correct, status in (("yes", "accepted"), ("no", "not_accepted")):
        folder = tmp_path / correct
        folder.mkdir()
        graded_file(folder, correct=correct)
        env = agreement_env(folder, settings, Boom())
        store = FixtureStore(folder / "judge-hand-grades.jsonl.gz")
        judging = judge.Judge(store=store, caller=CountingJudge(), system=system)
        for entry_id, grade in run.handgrades.load_hand_grades(
            folder / "data" / "hand-grades.yaml"
        ).items():
            await judging.judge(entry_id, grade.entry)

        block = run._agreement_block(env, store, system)

        assert block is not None
        assert block["status"] == status
        assert block["unjudged"] == []


# --- Smaller fixes ----------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
@pytest.mark.parametrize(
    ("value", "runs"),
    [("1", True), ("0", False), ("no", False), ("false", False), ("", False), ("yes", False)],
)
def test_only_yes_equal_to_1_adds_the_flag_to_a_live_run(value: str, runs: bool) -> None:
    root = EVAL_DIR.parents[1]

    done = subprocess.run(  # noqa: S603
        ["make", "-n", "eval-live", f"YES={value}"],  # noqa: S607
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )

    assert ("--yes" in done.stdout) is runs


def test_the_sandbox_cap_is_what_is_left_after_the_finished_sandboxes_and_the_judge() -> None:
    cap = run.SpendCap(Decimal("2.00"))
    assert cap.sandbox_cap_usd() == Decimal("2.00")
    cap.after_item(measured=Decimal("0.30"), judge_cost=Decimal("0.05"))
    # This sandbox's own ledger is checked against the cap, so what it spent is not taken twice.
    assert cap.sandbox_cap_usd() == Decimal("1.95")

    cap.start_segment()

    assert cap.sandbox_cap_usd() == Decimal("1.65")


def test_a_run_with_no_cap_has_no_sandbox_cap() -> None:
    assert run.SpendCap(None).sandbox_cap_usd() is None


def test_a_judge_call_is_reserved_at_its_full_output_allowance() -> None:
    kwargs = judge.judge_api_kwargs(judge.JudgeInput("q", "a", None, "r", "ans", ()))

    reserved = judge.reservation_usd(kwargs)

    # 8,000 output tokens at Sonnet's $10 per million is $0.08, and the input is a little more.
    assert Decimal("0.08") < reserved < Decimal("0.10")


def test_the_cap_says_whether_a_reservation_still_fits() -> None:
    cap = run.SpendCap(Decimal("1.00"))
    cap.after_item(measured=Decimal("0.50"), judge_cost=Decimal("0"))

    assert cap.can_afford(Decimal("0.50")) is True
    assert cap.can_afford(Decimal("0.51")) is False
    assert run.SpendCap(None).can_afford(Decimal("999")) is True


async def test_a_judge_md_without_a_version_is_refused_before_anything_is_built(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], settings: Any
) -> None:
    bad = tmp_path / "judge.md"
    bad.write_text("Grade the answers.\nJUDGE_VERSION: 1\n", encoding="utf-8")
    built: list[str] = []

    def record(name: str) -> Any:
        def factory(*_args: Any) -> Any:
            built.append(name)
            raise AssertionError(name)

        return factory

    env = raising_env(
        tmp_path,
        settings=settings,
        transport_factory=record("transport"),
        paths=run.EvalPaths(judge_md=bad, hand_grades=tmp_path / "hand-grades.yaml"),
    )

    code = await run.run_cli(
        ["--mode", "live", "--yes", "--fixtures-dir", str(tmp_path / "f")], env=env
    )

    assert code == 2
    assert "JUDGE_VERSION" in capsys.readouterr().err
    assert built == []


async def test_an_unexpected_error_is_exit_2_never_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], settings: Any
) -> None:
    def broken(_settings: Any) -> Any:
        raise RuntimeError("something nobody planned for")

    env = raising_env(tmp_path, settings=settings, transport_factory=broken)

    code = await run.run_cli(
        ["--mode", "live", "--yes", "--fixtures-dir", str(tmp_path / "f"), "--check"], env=env
    )

    assert code == 2
    assert "RuntimeError" in capsys.readouterr().err


# --- Keeping the judge's recordings in step with the answers ----------------------------------


def judged_record(
    item: str, *, gaps: tuple[str, ...] = (), recorded: bool = True, skipped: bool = False
) -> Any:
    """A Q&A item as a first trial left it: its answer, and what happened to its judge call."""
    rec = record(item, recording_gaps=gaps, answer_text="An answer.")
    rec.judge_input = judge.JudgeInput("q", "a", None, "r", "An answer.", ())
    if not skipped:
        rec.judge = judge.JudgeOutcome(item, f"fp-{item}", verdict(), None, Decimal("0.01"), None)
        if not recorded:
            rec.judge = judge.JudgeOutcome(
                item, f"fp-{item}", None, "the judge could not be reached", Decimal(0), None
            )
    return rec


def judge_store_with(tmp_path: Path, *items: str) -> FixtureStore:
    store = FixtureStore(tmp_path / "judge.jsonl.gz")
    for item in items:
        store.put(Record(f"fp-{item}", "judge", item, result={"text": "x"}))
    return store


def test_a_complete_judged_answer_is_recorded(tmp_path: Path) -> None:
    complete, skipped = run.recordable_qa_items(
        [judged_record("qa-01")], judge_store_with(tmp_path, "qa-01")
    )

    assert complete == {"qa-01"}
    assert skipped == {}


def test_a_judged_answer_with_a_recording_gap_keeps_its_old_answer_and_judge_record(
    tmp_path: Path,
) -> None:
    complete, skipped = run.recordable_qa_items(
        [judged_record("qa-01", gaps=("model call: boom",))], judge_store_with(tmp_path, "qa-01")
    )

    assert complete == set()
    assert "recorded" in skipped["qa-01"]


def test_an_answer_whose_judge_call_failed_transiently_is_not_re_recorded(tmp_path: Path) -> None:
    complete, skipped = run.recordable_qa_items(
        [judged_record("qa-01", recorded=False)], judge_store_with(tmp_path)
    )

    assert complete == set()
    assert "judge" in skipped["qa-01"]


def test_an_answer_the_cap_left_unjudged_is_not_re_recorded(tmp_path: Path) -> None:
    complete, skipped = run.recordable_qa_items(
        [judged_record("qa-01", skipped=True)], judge_store_with(tmp_path)
    )

    assert complete == set()
    assert "judge" in skipped["qa-01"]


def test_an_item_with_no_answer_needs_no_judge_recording(tmp_path: Path) -> None:
    blank = record("qa-01", answer_text="")

    complete, skipped = run.recordable_qa_items([blank], judge_store_with(tmp_path))

    assert complete == {"qa-01"}
    assert skipped == {}


def test_only_the_first_trial_is_considered(tmp_path: Path) -> None:
    later = judged_record("qa-01", recorded=False)
    later.trial = 2

    complete, skipped = run.recordable_qa_items([later], judge_store_with(tmp_path))

    assert (complete, skipped) == (set(), {})


# --- Smaller fixes ----------------------------------------------------------------------------


def test_the_hand_grade_notes_name_the_pair_the_code_uses() -> None:
    doc = run.handgrades.__doc__ or ""

    assert "qa-14" in doc
    assert "qa-16" in doc
    assert "qa-21" not in doc


def test_a_trace_is_converted_without_touching_its_raw_requests() -> None:
    class Untouchable:
        __dataclass_fields__: ClassVar[dict[str, None]] = {"secret": None}

        @property
        def secret(self) -> None:
            raise AssertionError("the raw requests were converted")

    trace = make_trace(person_id=uuid4(), requests=(Untouchable(),))

    data = board.trace_json(trace)

    assert "requests" not in data
    assert data["item_id"] == "item-1"


def test_the_question_length_limit_is_the_turns_own() -> None:
    from app.ai.turn import MAX_QUESTION_CHARACTERS

    source = (EVAL_DIR / "datasets.py").read_text(encoding="utf-8")

    assert datasets.MAX_QUESTION_CHARACTERS == MAX_QUESTION_CHARACTERS
    assert "MAX_QUESTION_CHARACTERS = 2000" not in source


async def test_the_agreement_run_stops_before_a_call_that_could_pass_its_cap(
    tmp_path: Path,
    settings: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    graded_file(tmp_path)
    # Each fake call costs a little over half a cent; one reservation is about nine cents. With a
    # cap of 15 cents the next call is refused once more than six cents are spent, long before the
    # spend itself reaches the cap.
    monkeypatch.setattr(run, "AGREEMENT_CAP_USD", Decimal("0.15"))
    caller = CountingJudge()

    code = await run.run_cli(
        ["--agreement", "--mode", "live", "--yes", "--fixtures-dir", str(tmp_path / "f")],
        env=agreement_env(tmp_path, settings, caller),
    )

    assert code == 2
    assert caller.calls < 15
    assert "cap" in capsys.readouterr().err
    # What was judged is kept.
    assert len(FixtureStore.load(tmp_path / "f" / "judge-hand-grades.jsonl.gz")) == caller.calls


async def test_the_observer_passes_a_spend_limit_through_unchanged() -> None:
    from app.ai.guard import build_guard_request
    from tests.test_replay import a_request

    class Limited:
        async def stream(self, request: Any) -> Any:
            raise SpendLimitReached("limit")
            yield  # pragma: no cover

        async def classify(self, request: Any) -> Any:
            raise SpendLimitReached("limit")

    observer = run.ObservingTransport(Limited())
    # The turn's own error code says it now, so the observer keeps no flag of its own.
    assert not hasattr(observer, "spend_limit_reached")

    with pytest.raises(SpendLimitReached):
        async for _ in observer.stream(a_request()):
            pass
    with pytest.raises(SpendLimitReached):
        await observer.classify(build_guard_request("hi", None))


def test_a_retraction_clears_the_answer_text_and_citations_gathered_so_far() -> None:
    from app.ai.citations import CitationEvent
    from app.ai.turn import Citation, Status, TextDelta, TextRetracted

    def cite(marker: int, offset: int) -> Citation:
        return Citation(
            CitationEvent(marker, offset, "CA-4.3", "p1", "t", "g", "a", "2026-10-07", "/x", "c")
        )

    events = [
        TextDelta("A working note. "),
        cite(1, 16),
        TextRetracted(),
        Status("A working note."),
        TextDelta("The answer."),
        cite(1, 11),
    ]

    text, citations = run.answer_as_shown(events)

    assert text == "The answer."
    assert [c["offsetUtf16"] for c in citations] == [11]
    # Without a retraction nothing is dropped.
    plain_text, plain_citations = run.answer_as_shown([TextDelta("a"), TextDelta("b"), cite(1, 2)])
    assert (plain_text, len(plain_citations)) == ("ab", 1)


# --- --prune, the trace's requests, the personas -----------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["--mode", "offline", "--set", "full", "--prune"],
        ["--mode", "live", "--set", "smoke", "--prune", "--yes"],
        ["--mode", "live", "--set", "effort", "--prune", "--yes"],
    ],
)
async def test_prune_is_allowed_only_for_a_live_full_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    code = await run.run_cli([*argv, "--fixtures-dir", str(tmp_path)], env=raising_env(tmp_path))

    assert code == 2
    assert "--prune" in capsys.readouterr().err
    assert not os.listdir(tmp_path)


async def test_prune_with_a_live_full_run_goes_on_to_the_estimate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await run.run_cli(
        ["--mode", "live", "--set", "full", "--prune", "--fixtures-dir", str(tmp_path)],
        env=raising_env(tmp_path),
    )

    assert code == 0
    assert "--yes" in capsys.readouterr().out


def test_a_trace_never_keeps_its_raw_requests_once_it_is_graded() -> None:
    requests = (object(),)
    plain = make_trace(person_id=uuid4(), requests=requests)
    gap = make_trace(person_id=uuid4(), requests=requests, recording_gaps=("model call: x",))

    assert run.slim_trace(plain).requests == ()
    assert run.slim_trace(gap).requests == ()
    assert run.slim_trace(gap).recording_gaps == ("model call: x",)


def test_the_personas_are_read_from_the_seed_through_the_graders_own_helper() -> None:
    source = (EVAL_DIR / "datasets.py").read_text(encoding="utf-8")

    assert re.search(r"Asker\(\s*[\"']", source) is None
    assert graders.personas_of is datasets.personas_of
    assert set(datasets.PERSONAS) == {"priya", "marcus", "dana", "mateo"}
    assert datasets.PERSONAS["mateo"].employment_type == "hourly"
    assert datasets.PERSONAS["dana"].state == "CO"
    # The IDs of a sandbox do not change who the personas are.
    other = datasets.personas_of(build_company(uuid4(), run.ANCHOR_DATE))
    assert other == datasets.PERSONAS


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
@pytest.mark.parametrize(("value", "passed"), [("1", True), ("0", False), ("yes", False)])
def test_only_prune_equal_to_1_adds_the_flag(value: str, passed: bool) -> None:
    done = subprocess.run(  # noqa: S603
        ["make", "-n", "eval-live", "SET=full", f"PRUNE={value}"],  # noqa: S607
        cwd=EVAL_DIR.parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    assert ("--prune" in done.stdout) is passed


# --- Round 3 ----------------------------------------------------------------------------------


def todo_args(tmp_path: Path, *extra: str) -> tuple[list[str], Any]:
    from tests.test_judge import traces_file

    traces = [
        traces_file(tmp_path / "low.json", effort="low"),
        traces_file(tmp_path / "medium.json", effort="medium"),
    ]
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    paths = run.EvalPaths(
        todo=data / "hand-grades-todo.yaml", hand_grades=data / "hand-grades.yaml"
    )
    return ["--write-hand-grades-todo", *map(str, traces), *extra], raising_env(
        tmp_path, paths=paths
    )


@pytest.mark.parametrize(
    "existing", ["hand-grades-todo.yaml", "hand-grades-key.yaml", "hand-grades.yaml"]
)
async def test_the_todo_command_will_not_overwrite_hand_grade_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], existing: str
) -> None:
    argv, env = todo_args(tmp_path)
    (tmp_path / "data" / existing).write_text("the owner's work", encoding="utf-8")

    code = await run.run_cli(argv, env=env)

    assert code == 2
    err = capsys.readouterr().err
    assert existing in err
    assert "--force" in err
    assert (tmp_path / "data" / existing).read_text(encoding="utf-8") == "the owner's work"
    assert sorted(p.name for p in (tmp_path / "data").iterdir()) == [existing]


async def test_force_overwrites_and_says_the_old_grades_no_longer_match(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv, env = todo_args(tmp_path, "--force")
    (tmp_path / "data" / "hand-grades.yaml").write_text("graded", encoding="utf-8")
    (tmp_path / "data" / "hand-grades-key.yaml").write_text("old key", encoding="utf-8")

    code = await run.run_cli(argv, env=env)

    assert code == 0
    out = capsys.readouterr().out
    assert "no longer match" in out
    assert (tmp_path / "data" / "hand-grades-todo.yaml").read_text(encoding="utf-8") != "old key"
    assert "old key" not in (tmp_path / "data" / "hand-grades-key.yaml").read_text(encoding="utf-8")


async def test_a_fresh_todo_needs_no_force_and_says_nothing_about_old_grades(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv, env = todo_args(tmp_path)

    code = await run.run_cli(argv, env=env)

    assert code == 0
    assert "no longer match" not in capsys.readouterr().out


def test_the_effort_set_defaults_to_its_own_folder_and_the_others_to_the_committed_one() -> None:
    env = run.RunEnv()
    parser = run.build_parser()

    effort = parser.parse_args(["--set", "effort"])
    smoke = parser.parse_args(["--set", "smoke"])

    assert run.resolve_fixtures_dir(effort, env) == run.EFFORT_FIXTURES_DIR
    assert run.EFFORT_FIXTURES_DIR.name == "fixtures-effort"
    assert run.resolve_fixtures_dir(smoke, env) == run.FIXTURES_DIR
    explicit = parser.parse_args(["--set", "effort", "--fixtures-dir", "elsewhere"])
    assert run.resolve_fixtures_dir(explicit, env) == Path("elsewhere")


async def test_the_effort_set_is_refused_the_committed_fixtures_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    committed = tmp_path / "committed"
    committed.mkdir()
    env = raising_env(tmp_path, committed_fixtures_dir=committed)

    code = await run.run_cli(
        ["--mode", "live", "--set", "effort", "--yes", "--fixtures-dir", str(committed)], env=env
    )

    assert code == 2
    assert "committed" in capsys.readouterr().err
    assert not os.listdir(committed)


async def test_an_agreement_run_counts_only_what_it_spent_not_what_the_recordings_cost(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    graded_file(tmp_path)
    fixtures = str(tmp_path / "f")
    live = ["--agreement", "--mode", "live", "--yes", "--fixtures-dir", fixtures]
    await run.run_cli(live, env=agreement_env(tmp_path, settings, CountingJudge()))
    first = capsys.readouterr().out
    assert "this run $0.20" in first  # 34 calls at about 0.6 cents

    caller = CountingJudge()
    code = await run.run_cli(live, env=agreement_env(tmp_path, settings, caller))

    out = capsys.readouterr().out
    assert code == 0
    assert caller.calls == 0
    assert "this run $0.00" in out
    assert "$0.20 more when they were recorded" in out


# --- Shared recordings: all or nothing ---------------------------------------------------------


def used_record(item: str, *keys: tuple[str, int]) -> Any:
    return record(item, used=tuple(keys))


def test_an_item_sharing_a_request_with_one_that_kept_its_old_recordings_keeps_its_own_too() -> (
    None
):
    # A finished and B had a gap, and both used the guard request K, whose answer changed. A's
    # later calls were made with the new answer, so they can't be saved beside B's old K.
    a, b = used_record("qa-01", ("K", 0), ("MA", 0)), used_record("qa-02", ("K", 0), ("MB", 0))

    recordable, dropped = run.recordable_through_shared_keys([a, b], complete={"qa-01"})

    assert recordable == set()
    assert "qa-02" in dropped["qa-01"]
    assert "old recordings" in dropped["qa-01"]


def test_the_loss_of_recordability_spreads_down_a_chain_of_shared_requests() -> None:
    # A shares K1 with B, B shares K2 with C, and C had a gap: B can't be saved, so neither can A.
    a = used_record("qa-01", ("K1", 0))
    b = used_record("qa-02", ("K1", 0), ("K2", 0))
    c = used_record("qa-03", ("K2", 0))
    d = used_record("qa-04", ("K9", 0))

    recordable, dropped = run.recordable_through_shared_keys(
        [a, b, c, d], complete={"qa-01", "qa-02", "qa-04"}
    )

    assert recordable == {"qa-04"}
    assert set(dropped) == {"qa-01", "qa-02"}


def test_items_that_share_nothing_with_a_gap_item_are_unaffected() -> None:
    a, b = used_record("qa-01", ("K", 0)), used_record("qa-02", ("K", 1))

    recordable, dropped = run.recordable_through_shared_keys([a, b], complete={"qa-01"})

    # (K, 0) and (K, 1) are different recordings: the second occurrence of the same request.
    assert recordable == {"qa-01"}
    assert dropped == {}


def test_when_every_item_finished_all_are_recordable() -> None:
    items = [used_record("qa-01", ("K", 0)), used_record("qa-02", ("K", 0))]

    recordable, dropped = run.recordable_through_shared_keys(items, complete={"qa-01", "qa-02"})

    assert recordable == {"qa-01", "qa-02"}
    assert dropped == {}


def test_the_merge_no_longer_has_a_contested_parameter() -> None:
    import inspect

    assert "contested" not in inspect.signature(run.merge_into).parameters


def test_the_daily_baseline_uses_the_budgets_own_query() -> None:
    from app.ai import budget

    assert run.DAY_SUM is budget.DAY_SUM


# --- Round 5 ----------------------------------------------------------------------------------


async def test_a_broken_hand_grades_file_is_exit_2_before_any_paid_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], settings: Any
) -> None:
    built: list[str] = []

    def factory(*_args: Any) -> Any:
        built.append("something")
        raise AssertionError("built before the hand grades were checked")

    broken = tmp_path / "hand-grades.yaml"
    broken.write_text("not: a list of entries\n", encoding="utf-8")
    env = raising_env(
        tmp_path,
        settings=settings,
        transport_factory=factory,
        paths=run.EvalPaths(hand_grades=broken),
    )

    code = await run.run_cli(
        ["--mode", "live", "--yes", "--fixtures-dir", str(tmp_path / "f")], env=env
    )

    assert code == 2
    assert "hand-grades.yaml" in capsys.readouterr().err
    assert built == []


def test_the_agreement_block_reports_invalid_hand_grades_instead_of_raising(
    tmp_path: Path, settings: Any
) -> None:
    graded = graded_file(tmp_path)
    graded.with_name("hand-grades-key.yaml").unlink()
    env = agreement_env(tmp_path, settings, Boom())

    block = run._agreement_block(env, FixtureStore(tmp_path / "x.jsonl.gz"), "system")

    assert block is not None
    assert block["status"] == "invalid"
    assert any("key" in problem for problem in block["problems"])


def test_an_invalid_agreement_is_in_the_scoreboard_and_the_report() -> None:
    result = board.build_scoreboard(
        facts(agreement={"status": "invalid", "problems": ["hg-01: `correct` must be yes or no"]}),
        [],
    )

    text = board.render(result)

    assert result["metrics"]["judge_agreement"]["status"] == "invalid"
    assert "invalid" in text
    assert "hg-01" in text


def test_the_spend_caps_amounts_carry_their_unit() -> None:
    cap = run.SpendCap(Decimal("2.00"))
    cap.after_item(measured=Decimal("0.40"), judge_cost=Decimal("0.10"))

    assert (cap.total_usd, cap.assistant_total_usd, cap.judge_total_usd) == (
        Decimal("0.50"),
        Decimal("0.40"),
        Decimal("0.10"),
    )
    assert not hasattr(cap, "total")
    assert not hasattr(cap, "judge_total")


# --- What a live run actually spent, apart from what its recordings cost ---------------------

ONE_CALL = Usage(1000, 200, 0, 0)


class FakeLiveTransport:
    """A real-looking transport that bills one model call and one guard call."""

    def __init__(self) -> None:
        self.closed = False

    async def stream(self, request: Any) -> Any:
        try:
            yield Finished({}, "end_turn", None, ONE_CALL, (IterationUsage(OPUS, ONE_CALL),), OPUS)
        finally:
            self.closed = True

    async def classify(self, request: Any) -> GuardResult:
        return GuardResult("ordinary", None, False, ONE_CALL, HAIKU)


async def test_the_live_meter_prices_the_calls_that_reach_the_real_transport() -> None:
    inner = FakeLiveTransport()
    meter = run.LiveCallMeter(inner)

    events = [event async for event in meter.stream(object())]
    await meter.classify(GuardRequest(HAIKU, "", ()))

    assert len(events) == 1
    assert meter.total_usd == turn_call_cost([IterationUsage(OPUS, ONE_CALL)]) + turn_call_cost(
        [IterationUsage(HAIKU, ONE_CALL)]
    )
    assert meter.total_usd > 0
    assert inner.closed


async def test_the_live_meter_prices_a_guard_call_that_failed_after_it_was_billed() -> None:
    from app.ai.transport import GuardUnavailable

    class Billed(FakeLiveTransport):
        async def classify(self, request: Any) -> GuardResult:
            raise GuardUnavailable("off schema", usage=ONE_CALL)

    class Unbilled(FakeLiveTransport):
        async def classify(self, request: Any) -> GuardResult:
            raise GuardUnavailable("timed out")  # Cost unknown: nothing is added.

    billed, unbilled = run.LiveCallMeter(Billed()), run.LiveCallMeter(Unbilled())

    for meter in (billed, unbilled):
        with pytest.raises(GuardUnavailable):
            await meter.classify(GuardRequest(HAIKU, "", ()))

    assert billed.total_usd == turn_call_cost([IterationUsage(HAIKU, ONE_CALL)])
    assert unbilled.total_usd == 0


async def test_a_call_answered_from_a_recording_never_reaches_the_live_meter() -> None:
    from app.ai.replay import RecordingTransport
    from app.ai.transport import FALLBACK_BETA, ModelRequest

    meter = run.LiveCallMeter(FakeLiveTransport())
    recorder = RecordingTransport(meter, FixtureStore(Path("unused.jsonl.gz")))
    recorder.current_item = "item"
    request = ModelRequest(
        OPUS, (), (), ({"role": "user", "content": "hi"},), "low", 100, (FALLBACK_BETA,)
    )

    _ = [event async for event in recorder.stream(request)]
    first = meter.total_usd
    recorder.current_item = "item"  # The same request again, now recorded.
    _ = [event async for event in recorder.stream(request)]

    assert first > 0
    assert meter.total_usd == first


def test_recorded_assistant_spend_is_the_ledger_less_what_was_called_live() -> None:
    cap = run.SpendCap(Decimal("2.00"))
    cap.observe(Decimal("0.39"))
    cap.note_live_assistant(Decimal("0.05"))

    assert cap.assistant_live_usd == Decimal("0.05")
    assert cap.assistant_recorded_usd == Decimal("0.34")
    # The cap still counts the whole ledger, recorded costs included.
    assert cap.assistant_total_usd == Decimal("0.39")
    assert cap.total_usd == Decimal("0.39")


def test_a_run_that_called_nothing_live_reports_no_assistant_spend() -> None:
    cap = run.SpendCap(Decimal("2.00"))
    cap.after_item(measured=Decimal("0.39"), judge_cost=Decimal("0.013"))
    cap.note_live_assistant(Decimal(0))

    assert cap.assistant_live_usd == Decimal(0)
    assert cap.assistant_recorded_usd == Decimal("0.39")


def test_the_scoreboard_keeps_live_spend_apart_from_what_recordings_cost() -> None:
    result = board.build_scoreboard(
        facts(
            assistant_cost_usd=Decimal("0"),
            judge_cost_usd=Decimal("0.013"),
            assistant_recorded_cost_usd=Decimal("0.39"),
            judge_recorded_cost_usd=Decimal("0.02"),
        ),
        sample_records(),
    )

    assert result["cost_usd"] == {
        "assistant": "0.000000",
        "judge": "0.013000",
        "total": "0.013000",
        "cap": "2.000000",
        "recorded": {"assistant": "0.390000", "judge": "0.020000", "total": "0.410000"},
    }
    text = board.render(result)
    assert "Cost $0.01 (assistant $0.00, judge $0.01)" in text
    assert "recordings" in text
    assert "$0.41" in text


def test_the_report_omits_the_recordings_line_when_nothing_was_reused() -> None:
    text = board.render(board.build_scoreboard(facts(), sample_records()))

    assert "recordings" not in text


def test_the_judge_reuses_the_transports_usage_mapping_and_replays_usage_codec() -> None:
    from app.ai import anthropic_transport, replay

    assert judge.usage_from_sdk is anthropic_transport.usage_from_sdk
    assert not hasattr(anthropic_transport, "_usage")
    usage = Usage(5, 6, 7, 8)
    response = judge.JudgeResponse("end_turn", "{}", usage, "claude-sonnet-5-5")
    assert response.to_json()["usage"] == replay.encode_usage(usage)
    assert judge.JudgeResponse.from_json(response.to_json()).usage == usage


def test_the_judge_key_of_a_record_is_read_from_its_outcome_not_rebuilt() -> None:
    judged = record("qa-01")
    judged.judge = judge.JudgeOutcome(
        "qa-01", "fp-from-the-outcome", verdict(), None, Decimal("0.01"), None
    )
    skipped = record("qa-02")
    skipped.judge_key = "fp-of-the-skipped-call"
    unjudged = record("qa-03")

    assert run.judge_key_of(judged) == "fp-from-the-outcome"
    assert run.judge_key_of(skipped) == "fp-of-the-skipped-call"
    assert run.judge_key_of(unjudged) is None


def test_the_test_loader_takes_just_the_file_name() -> None:
    import inspect

    from tests.assistant_eval import load_eval_module

    assert list(inspect.signature(load_eval_module).parameters) == ["filename"]


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
@pytest.mark.parametrize(
    ("variables", "fresh", "prune"),
    [
        (["FRESH=1"], True, False),
        (["PRUNE=1"], True, True),
        (["FRESH=1", "PRUNE=1"], True, True),
        (["FRESH=0"], False, False),
        ([], False, False),
    ],
)
def test_fresh_and_prune_in_make_and_prune_implies_fresh(
    variables: list[str], fresh: bool, prune: bool
) -> None:
    done = subprocess.run(  # noqa: S603
        ["make", "-n", "eval-live", "SET=full", *variables],  # noqa: S607
        cwd=EVAL_DIR.parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    assert done.stdout.count("--fresh") == (1 if fresh else 0)
    assert done.stdout.count("--prune") == (1 if prune else 0)


@pytest.mark.parametrize("argv", [["--mode", "offline", "--fresh"]])
async def test_fresh_is_for_live_runs_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    code = await run.run_cli([*argv, "--fixtures-dir", str(tmp_path)], env=raising_env(tmp_path))

    assert code == 2
    assert "--fresh" in capsys.readouterr().err


# --- Round 7 ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cause",
    [
        "the spend cap",
        "answers the judge's reservation would not fit the cap for",
        "the ledger refusing a call that could not fit",
    ],
)
def test_a_partial_report_names_why_the_run_stopped(cause: str) -> None:
    result = board.build_scoreboard(
        facts(partial=True, stop_cause=cause, items_not_run=["qa-05"]), sample_records()
    )

    text = board.render(result)

    assert result["stop_cause"] == cause
    assert f"stopped by {cause}" in text
    assert "spend cap stopped" not in text.replace(f"stopped by {cause}", "")


def test_a_complete_run_has_no_stop_cause_and_says_nothing_of_one() -> None:
    result = board.build_scoreboard(facts(), sample_records())

    assert result["stop_cause"] is None
    assert "stopped by" not in board.render(result)


def test_the_graders_ask_the_shared_asker_rule_not_their_own_copy_of_the_states() -> None:
    grader = graders.Grader(
        build_company(run.TENANT_ID, run.ANCHOR_DATE),
        {},
        public_month_days=(),
        as_of=run.NOW.date(),
    )

    assert not hasattr(grader, "_states")
    assert "_states" not in inspect.getsource(graders.Grader)
    assert "asker_for" in inspect.getsource(graders.Grader.qa)


# --- Small cleanups ---------------------------------------------------------------------------


def test_the_gaps_use_the_same_occurrence_numbers_as_the_used_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.ai.replay import RecordingTransport

    class Observer:
        calls = (("model", "fp-a"), ("model", "fp-a"))

    monkeypatch.setattr(run, "_used_keys", lambda _observer: (("fp-a", 7), ("fp-a", 9)))
    transport = RecordingTransport(object(), FixtureStore(tmp_path / "x"))  # type: ignore[arg-type]

    gaps = run._recording_gaps(transport, Observer())

    assert [g.split(":")[0] for g in gaps] == [
        "model call (occurrence 7)",
        "model call (occurrence 9)",
    ]


def test_the_guard_model_is_the_pricing_modules_haiku() -> None:
    from app.ai import pricing

    source = (EVAL_DIR / "run.py").read_text(encoding="utf-8")

    assert run.GUARD_MODEL_ID == pricing.HAIKU
    assert 'GUARD_MODEL_ID = "claude-haiku-5-5"' not in source


def test_the_evals_pin_the_models_a_new_conversation_gets() -> None:
    from app.ai.conversations import CURRENT_PINS

    source = (EVAL_DIR / "run.py").read_text(encoding="utf-8")

    assert (CURRENT_PINS.model, CURRENT_PINS.guard_model) == (run.MODEL_ID, run.GUARD_MODEL_ID)
    assert 'MODEL_ID = "claude-opus-5-5"' not in source
