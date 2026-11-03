"""The judge spot check (`run.py --rejudge`, Phase 7, stage 4): both runs' answers on the pairs the
two judges split, judged again by another judge model. Tiny synthetic run and traces files and a
fake judge caller. No database and no network."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.ai.pricing import Usage
from tests.assistant_eval import load_judge, load_runner
from tests.test_assistant_eval_runner import Boom, raising_env

run = load_runner()
judge = load_judge()

OPUS = "claude-opus-5-5"
LINES = list(judge.RUBRIC_KEYS)


def verdict(**no: bool) -> dict[str, Any]:
    lines = {key: key not in no for key in LINES}
    return {"passed": all(lines.values()), "lines": lines, "reasons": {k: "r" for k in LINES}}


def judge_input(arm: str, item: str) -> dict[str, Any]:
    return {
        "asker": "Ana",
        "location_asked": None,
        "today": "2026-10-15",
        "question": f"question {item}",
        "reference": "reference",
        "answer": f"{arm} answer to {item}",
        "tool_facts": [],
        "passages": [],
    }


# (trial, item, baseline judge verdict, current judge verdict)
ROWS = [
    (1, "qa-01", verdict(), verdict()),  # same: not picked
    (1, "qa-02", verdict(), verdict(correct=False)),  # pass -> fail: picked
    (2, "qa-02", verdict(correct=False), verdict(correct=False)),  # same failure: not picked
    (1, "qa-03", verdict(correct=False), verdict(faithful=False)),  # a different line: picked
]


def write_run(
    path: Path, arm: str, verdicts: list[dict[str, Any]], judge_version: str | None = None
) -> Path:
    items = [
        {"trial": t, "item": i, "dataset": "qa", "deterministic_passed": True, "judge": v}
        for (t, i, *_), v in zip(ROWS, verdicts, strict=True)
    ]
    document = {
        "commit": "abc",
        "models": {"assistant": arm},
        "versions": {"judge": judge_version or judge.judge_version()},
        "metrics": {},
        "items": items,
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    traces = [
        {"item_id": i, "trial": t, "dataset": "qa", "judge_input": judge_input(arm, i)}
        for t, i, *_ in ROWS
    ]
    path.with_name(path.stem + "-traces.json").write_text(
        json.dumps({"run": {}, "traces": traces}), encoding="utf-8"
    )
    return path


class Opus:
    """A judge caller: fails `correct` on any current-arm answer, passes the rest, and records the
    model each request named."""

    def __init__(self) -> None:
        self.models: list[str] = []
        self.answers: list[str] = []

    async def __call__(self, kwargs: dict[str, Any]) -> Any:
        self.models.append(kwargs["model"])
        content = kwargs["messages"][0]["content"]
        self.answers.append(content)
        fails = "current answer" in content
        lines = {key: {"verdict": not (fails and key == "correct"), "reason": "r"} for key in LINES}
        return judge.JudgeResponse("end_turn", json.dumps(lines), Usage(1500, 300, 0, 0), OPUS)


class Untouched:
    """The assistant transport: any use of it fails the test."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the assistant transport was used ({name})")


def files(tmp_path: Path) -> tuple[Path, Path]:
    base = write_run(tmp_path / "20261103T000000Z-full.json", "baseline", [r[2] for r in ROWS])
    cur = write_run(tmp_path / "20261104T000000Z-full.json", "current", [r[3] for r in ROWS])
    return base, cur


def spot_env(tmp_path: Path, settings: Any, caller: Any) -> Any:
    return raising_env(
        tmp_path,
        settings=settings,
        transport_factory=lambda _settings: Untouched(),
        judge_caller_factory=lambda _transport: caller,
        paths=run.EvalPaths(hand_grades=tmp_path / "hand-grades.yaml"),
    )


def args(base: Path, cur: Path, fixtures: Path, *extra: str) -> list[str]:
    return [
        "--rejudge", str(base), str(cur), "--judge-model", OPUS,
        "--fixtures-dir", str(fixtures), *extra,
    ]  # fmt: skip


async def test_it_picks_only_the_pairs_the_judges_split_and_judges_both_arms_with_the_named_model(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)
    caller = Opus()

    code = await run.run_cli(
        args(base, cur, tmp_path / "f", "--mode", "live", "--yes"),
        env=spot_env(tmp_path, settings, caller),
    )

    out = capsys.readouterr().out
    assert code == 0
    # Two pairs, both arms each: four calls, every one on the named model.
    assert caller.models == [OPUS] * 4
    assert any("baseline answer to qa-02" in a for a in caller.answers)
    assert any("current answer to qa-03" in a for a in caller.answers)
    assert not any("qa-01" in a for a in caller.answers)
    assert "2 pairs" in out
    assert out.count("2 of 2 re-judged (0 not judged)") == 2
    assert "qa-02 (trial 1)" in out
    assert "qa-03 (trial 1)" in out
    # qa-02: baseline pass -> pass under Opus; current fail -> fail under Opus.
    assert "baseline: judge pass, Opus 5.5 judge pass" in out
    assert "current: judge fail, Opus 5.5 judge fail" in out
    assert f"pass share under {OPUS}" in out
    assert (tmp_path / "f" / run.SPOT_CHECK_FIXTURE).exists()


async def test_a_second_run_reads_the_recordings_and_calls_nothing(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)
    await run.run_cli(
        args(base, cur, tmp_path / "f", "--mode", "live", "--yes"),
        env=spot_env(tmp_path, settings, Opus()),
    )
    capsys.readouterr()

    code = await run.run_cli(
        args(base, cur, tmp_path / "f", "--mode", "offline"),
        env=spot_env(tmp_path, settings, Boom()),
    )

    assert code == 0
    assert "2 pairs" in capsys.readouterr().out


async def test_the_default_judge_s_recordings_never_answer_the_named_judge(
    tmp_path: Path,
) -> None:
    default = judge.judge_api_kwargs(judge.JudgeInput.from_json(judge_input("x", "qa-01")))
    named = judge.judge_api_kwargs(
        judge.JudgeInput.from_json(judge_input("x", "qa-01")), model=OPUS
    )

    assert default["model"] == judge.JUDGE_MODEL
    assert named["model"] == OPUS
    assert judge.fingerprint("judge", default) != judge.fingerprint("judge", named)
    assert judge.reservation_usd(named) > judge.reservation_usd(default)


async def test_live_without_yes_prints_the_count_and_an_estimate_and_calls_nothing(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)

    code = await run.run_cli(
        args(base, cur, tmp_path / "f", "--mode", "live"),
        env=spot_env(tmp_path, settings, Boom()),
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "2 pairs" in out
    assert "4 judge calls" in out
    assert "Nothing was called" in out
    assert "$" in out
    assert not (tmp_path / "f" / run.SPOT_CHECK_FIXTURE).exists()


async def test_offline_with_a_missing_recording_exits_2(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)

    code = await run.run_cli(
        args(base, cur, tmp_path / "f", "--mode", "offline"),
        env=spot_env(tmp_path, settings, Boom()),
    )

    assert code == 2
    assert "missing" in capsys.readouterr().err


async def test_it_stops_before_a_call_that_could_pass_the_cap_and_keeps_what_it_judged(
    tmp_path: Path,
    settings: Any,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, cur = files(tmp_path)
    caller = Opus()
    one_call = judge.reservation_usd(
        judge.judge_api_kwargs(judge.JudgeInput.from_json(judge_input("x", "qa-02")), model=OPUS)
    )
    # The cap fits one call's reservation and the cost of the first call, but not a second.
    monkeypatch.setattr(run, "SPOT_CHECK_CAP_USD", one_call + Decimal("0.001"))

    code = await run.run_cli(
        args(base, cur, tmp_path / "f", "--mode", "live", "--yes"),
        env=spot_env(tmp_path, settings, caller),
    )

    assert code == 2
    assert len(caller.models) == 1
    captured = capsys.readouterr()
    assert "cap" in captured.err
    assert "Summary over 2 pairs" in captured.out
    assert "not judged" in captured.out
    assert len(run.FixtureStore.load(tmp_path / "f" / run.SPOT_CHECK_FIXTURE)) == 1


async def test_it_needs_a_judge_model(tmp_path: Path, settings: Any) -> None:
    base, cur = files(tmp_path)

    code = await run.run_cli(
        ["--rejudge", str(base), str(cur), "--fixtures-dir", str(tmp_path / "f")],
        env=spot_env(tmp_path, settings, Boom()),
    )

    assert code == 2


async def test_an_arm_with_no_judge_input_is_skipped_and_counted_not_fatal(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)
    traces = cur.with_name(cur.stem + "-traces.json")
    document = json.loads(traces.read_text(encoding="utf-8"))
    for entry in document["traces"]:
        if entry["item_id"] == "qa-02":
            entry["judge_input"] = None
    traces.write_text(json.dumps(document), encoding="utf-8")
    caller = Opus()

    code = await run.run_cli(
        args(base, cur, tmp_path / "f", "--mode", "live", "--yes"),
        env=spot_env(tmp_path, settings, caller),
    )

    out = capsys.readouterr().out
    assert code == 0
    assert len(caller.models) == 3
    assert "no answer to judge" in out
    assert "1 answer had no answer to judge" in out
    assert "baseline: 2 of 2 re-judged (0 not judged)" in out
    assert "current: 1 of 2 re-judged (1 not judged)" in out


async def test_a_pair_with_no_trace_entry_at_all_is_still_refused(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)
    traces = cur.with_name(cur.stem + "-traces.json")
    document = json.loads(traces.read_text(encoding="utf-8"))
    document["traces"] = document["traces"][:1]
    traces.write_text(json.dumps(document), encoding="utf-8")

    code = await run.run_cli(
        args(base, cur, tmp_path / "f", "--mode", "live"), env=spot_env(tmp_path, settings, Boom())
    )

    assert code == 2
    assert "no trace" in capsys.readouterr().err


async def test_live_refuses_the_committed_fixtures_folder(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)
    committed = tmp_path / "committed"
    committed.mkdir()
    env = spot_env(tmp_path, settings, Boom())
    env.committed_fixtures_dir = committed

    code = await run.run_cli(args(base, cur, committed, "--mode", "live", "--yes"), env=env)

    assert code == 2
    assert "committed" in capsys.readouterr().err
    assert not list(committed.iterdir())


async def test_a_run_judged_under_another_rubric_version_is_refused(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, _ = files(tmp_path)
    old = write_run(
        tmp_path / "20261102T000000Z-full.json", "current", [r[3] for r in ROWS], "1999-01.1"
    )

    code = await run.run_cli(
        args(base, old, tmp_path / "f", "--mode", "live"), env=spot_env(tmp_path, settings, Boom())
    )

    assert code == 2
    assert "rubric" in capsys.readouterr().err


async def test_judge_model_without_rejudge_is_refused(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await run.run_cli(
        ["--judge-model", OPUS, "--fixtures-dir", str(tmp_path)],
        env=spot_env(tmp_path, settings, Boom()),
    )

    assert code == 2
    assert "--judge-model" in capsys.readouterr().err


async def test_compare_case_summary_needs_compare_and_a_readable_file_up_front(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, _ = files(tmp_path)
    env = spot_env(tmp_path, settings, Boom())

    alone = await run.run_cli(
        ["--compare-case-summary", str(base), "--fixtures-dir", str(tmp_path)], env=env
    )
    bad_path = await run.run_cli(
        [
            "--compare", str(base), "--compare-case-summary", str(tmp_path / "nope.json"),
            "--fixtures-dir", str(tmp_path),
        ],
        env=env,
    )  # fmt: skip

    assert (alone, bad_path) == (2, 2)
    assert "nope.json" in capsys.readouterr().err


async def test_the_spot_check_refuses_a_scripted_unpriced_or_same_judge(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)

    for model, needle in (
        ("scripted", "scripted"),
        ("claude-unknown-9-9", "no pinned price"),
        (judge.JUDGE_MODEL, "independent"),
    ):
        code = await run.run_cli(
            ["--rejudge", str(base), str(cur), "--judge-model", model,
             "--fixtures-dir", str(tmp_path / "f")],
            env=spot_env(tmp_path, settings, Boom()),
        )  # fmt: skip
        assert code == 2, model
        assert needle in capsys.readouterr().err, model


async def test_a_traces_file_that_is_not_json_gets_an_error_that_says_so(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)
    cur.with_name(cur.stem + "-traces.json").write_text("[1, 2]", encoding="utf-8")

    code = await run.run_cli(
        args(base, cur, tmp_path / "f", "--mode", "live"), env=spot_env(tmp_path, settings, Boom())
    )

    assert code == 2
    err = capsys.readouterr().err
    assert "traces" in err
    assert "is not a scoreboard" not in err


async def test_the_spot_check_is_independent_of_the_judge_each_run_recorded(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)

    def set_judges(baseline_judge: str, current_judge: str) -> None:
        for path, name in ((base, baseline_judge), (cur, current_judge)):
            document = json.loads(path.read_text(encoding="utf-8"))
            document["models"]["judge"] = name
            path.write_text(json.dumps(document), encoding="utf-8")

    for judges, needle in (
        (("claude-sonnet-5-5", "claude-haiku-5-5"), "differ"),
        ((OPUS, OPUS), "independent"),
    ):
        set_judges(*judges)
        code = await run.run_cli(
            args(base, cur, tmp_path / "f", "--mode", "live"),
            env=spot_env(tmp_path, settings, Boom()),
        )
        assert code == 2, judges
        assert needle in capsys.readouterr().err, judges


async def test_the_dry_run_says_when_the_estimate_is_over_the_cap_and_how_many_calls_fit(
    tmp_path: Path,
    settings: Any,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, cur = files(tmp_path)
    one_call = judge.reservation_usd(
        judge.judge_api_kwargs(judge.JudgeInput.from_json(judge_input("x", "qa-02")), model=OPUS)
    )
    monkeypatch.setattr(run, "SPOT_CHECK_CAP_USD", one_call * Decimal("2.05"))

    code = await run.run_cli(
        args(base, cur, tmp_path / "f", "--mode", "live"), env=spot_env(tmp_path, settings, Boom())
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "over the cap" in out
    assert "about 2 of 4" in out


async def test_rejudge_rejects_flags_that_would_do_nothing(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)

    for extra in (["--set", "full"], ["--model", "claude-sonnet-5-5"], ["--compare", str(base)],
                  ["--compare-case-summary", str(base)]):  # fmt: skip
        code = await run.run_cli(
            [*args(base, cur, tmp_path / "f", "--mode", "live"), *extra],
            env=spot_env(tmp_path, settings, Boom()),
        )
        assert code == 2, extra
        assert extra[0] in capsys.readouterr().err, extra
    # --set smoke is the default, but passing it is still passing it.
    code = await run.run_cli(
        [*args(base, cur, tmp_path / "f", "--mode", "live"), "--set=smoke"],
        env=spot_env(tmp_path, settings, Boom()),
    )
    assert code == 2


async def test_the_comparison_files_are_checked_for_shape_before_anything_is_spent(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, _ = files(tmp_path)
    env = spot_env(tmp_path, settings, Boom())
    zero = tmp_path / "zero.json"
    zero.write_text(
        json.dumps({"metrics": {"passed_every_check": {"mean": 1.0, "itemsPerTrial": 0}}}),
        encoding="utf-8",
    )
    traces = base.with_name(base.stem + "-traces.json")

    for extra, bad_traces, needle in (
        (["--compare", str(base), "--compare-case-summary", str(zero)], [], "zero.json"),
        (["--compare", str(base)], "nope", "traces"),
    ):
        traces.write_text(json.dumps({"traces": bad_traces}), encoding="utf-8")
        code = await run.run_cli([*extra, "--fixtures-dir", str(tmp_path)], env=env)
        assert code == 2, extra
        assert needle in capsys.readouterr().err, extra


def test_wrong_typed_fields_in_the_comparison_files_are_eval_failures_not_crashes(
    tmp_path: Path,
) -> None:
    good = {"commit": "abc", "metrics": {}, "items": []}
    wrong: list[tuple[str, Any]] = [("live_evidence", []), ("models", [])]
    for field, value in wrong:
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps({**good, field: value}), encoding="utf-8")
        with pytest.raises(run.EvalFailure):
            run._read_baseline(path)
    with pytest.raises(run.EvalFailure):
        run.check_case_summary_file({"metrics": []}, tmp_path / "c.json")
    with pytest.raises(run.EvalFailure):
        run.check_case_summary_file({"metrics": {"passed_every_check": []}}, tmp_path / "c.json")


def test_a_traces_file_needs_an_int_trial_and_a_text_item_id_in_every_entry(
    tmp_path: Path,
) -> None:
    for entry in ({"trial": "1", "item_id": "a"}, {"trial": 1, "item_id": 5}, {"item_id": "a"}):
        with pytest.raises(run.EvalFailure):
            run.check_traces_file({"traces": [entry]}, tmp_path / "t.json")
    run.check_traces_file({"traces": [{"trial": 1, "item_id": "a"}]}, tmp_path / "t.json")


def test_a_failed_decision_keeps_the_metric_comparison_in_the_run_file_and_reports_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from types import SimpleNamespace

    scoreboard = run.scoreboard

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise KeyError("rule")

    monkeypatch.setattr(scoreboard, "decision_rule", boom)
    baseline = {"commit": "a", "metrics": {}, "items": [], "models": {"assistant": OPUS}}
    board: dict[str, Any] = {
        "commit": "b",
        "metrics": {},
        "items": [],
        "models": {"assistant": "x"},
    }
    out = tmp_path / "run.json"
    args = SimpleNamespace(baseline_traces=None, case_summary_run=None, json=out)

    ok = run._report_comparison_safely(args, baseline, board, [])

    assert ok is False
    assert "comparison failed" in capsys.readouterr().err
    assert "compare" in json.loads(out.read_text(encoding="utf-8"))


class Refusing:
    """A judge caller whose every answer is a refusal (no verdict)."""

    async def __call__(self, kwargs: dict[str, Any]) -> Any:
        return judge.JudgeResponse("refusal", "", Usage(1500, 0, 0, 0), OPUS)


async def test_an_unavailable_verdict_is_named_and_left_out_of_the_shares(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)

    code = await run.run_cli(
        args(base, cur, tmp_path / "f", "--mode", "live", "--yes"),
        env=spot_env(tmp_path, settings, Refusing()),
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "4 answers had no verdict and are left out of the shares" in out
    assert "0 of 2 re-judged (2 not judged)" in out


async def test_rejudge_refuses_every_flag_that_belongs_to_another_command(
    tmp_path: Path, settings: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    base, cur = files(tmp_path)

    for extra in (
        ["--agreement"], ["--fresh"], ["--prune"], ["--check"], ["--json", "x.json"],
        ["--traces", "x.json"], ["--regrade-fairness", "x.json"],
        ["--write-hand-grades-todo", "x.json"],
    ):  # fmt: skip
        code = await run.run_cli(
            [*args(base, cur, tmp_path / "f", "--mode", "live"), *extra],
            env=spot_env(tmp_path, settings, Boom()),
        )
        assert code == 2, extra
        assert extra[0] in capsys.readouterr().err, extra
