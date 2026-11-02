"""The run boards (evals/assistant/boards.py): what a live run commits, and what it leaves out.

No model is called. The run documents here are built by hand in the shapes the runners write.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.assistant_eval import EVAL_DIR, load_boards, load_escalation
from tests.retrieval_eval import load_runner as load_retrieval

boards = load_boards()

PLANTED = "PLANTED-ANSWER-TEXT the employee's private details"


def spread(mean: float, low: float) -> dict[str, Any]:
    return {"mean": mean, "min": low, "max": 1.0, "spread": 1.0 - low, "trials": 3}


def full_run(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "mode": "live",
        "set": "full",
        "effort": "low",
        "trials": 3,
        "date": "2026-10-29T15:40:29+00:00",
        "commit": "abc123-dirty",
        "partial": False,
        "aborted": None,
        "stop_cause": None,
        "items_run": 498,
        "items_not_run": [],
        "models": {
            "assistant": "claude-opus-5-5",
            "guard": "claude-haiku-5-5",
            "judge": "claude-sonnet-5-5",
        },
        "versions": {
            "prompt": "2026-11.2",
            "toolset": "2026-11.2",
            "guard_prompt": "2026-11.1",
            "judge": "2026-10.3",
        },
        "dataset_sha256": {"qa.yaml": "aa", "actions.yaml": "bb"},
        "cost_usd": {
            "assistant": "8.35",
            "judge": "2.58",
            "total": "10.932969",
            "cap": "16.000000",
        },
        "metrics": {
            "redteam_pass_rate": spread(1.0, 1.0),
            "redteam_pass_rate_by_group": {"injection": spread(1.0, 1.0)},
            "qa_deterministic_pass_rate": spread(0.9671, 0.9577),
            "unanswerable_pass_rate": spread(0.9333, 0.9),
            "judge_pass_rate": spread(0.6808, 0.6479),
            "judge_uncited_claim_count": spread(18.0, 15.0),
            "judge_agreement": {"share": 0.897, "matched_lines": 183, "total_lines": 204},
        },
        "failures": [
            {
                "trial": 1,
                "dataset": "qa",
                "item": "qa-06",
                "failed": ["no-case-claim"],
                "reasons": {"no-case-claim": [f"the answer claims: {PLANTED}"]},
            },
            {"trial": 2, "dataset": "qa", "item": "qa-06", "failed": [], "reasons": {}},
            {"trial": 2, "dataset": "qa", "item": "qa-37", "failed": [], "reasons": {}},
        ],
        "judge_unavailable": [],
        "recording_gaps": [],
        "live_evidence": {"calls": [{"item": "rt-01", "model": "claude-opus-5-5"}]},
        "items": [{"trial": 1, "item": "qa-06", "judge": {"answer": PLANTED}}],
    }
    document.update(overrides)
    return document


def test_a_board_holds_the_metrics_facts_failures_and_cost() -> None:
    board = boards.board_of(full_run(), stamp="20261029T142328Z")

    assert board["schema"] == 1
    assert board["set"] == "full"
    assert board["stamp"] == "20261029T142328Z"
    facts = board["facts"]
    assert facts["model"] == "claude-opus-5-5"
    assert facts["effort"] == "low"
    assert facts["promptVersion"] == "2026-11.2"
    assert facts["toolsetVersion"] == "2026-11.2"
    assert facts["guardPromptVersion"] == "2026-11.1"
    assert facts["judgeVersion"] == "2026-10.3"
    assert facts["datasetSha256"] == {"qa.yaml": "aa", "actions.yaml": "bb"}
    assert facts["commit"] == "abc123-dirty"
    assert facts["trials"] == 3
    assert facts["date"] == "2026-10-29"
    assert facts["live"] is True
    assert board["metrics"]["qa_deterministic_pass_rate"] == {"mean": 0.9671, "min": 0.9577}
    assert board["metrics"]["redteam_pass_rate_by_group.injection"] == {"mean": 1.0, "min": 1.0}
    assert board["metrics"]["judge_agreement"]["mean"] == 0.897
    assert board["failures"] == ["qa-06", "qa-37"]
    assert board["costUsd"] == {"total": "10.932969", "cap": "16.000000"}


def test_no_answer_text_or_trace_reaches_the_board() -> None:
    board = boards.board_of(full_run(), stamp="20261029T142328Z")

    text = json.dumps(board)
    assert PLANTED not in text
    assert "PLANTED" not in text
    for key in ("items", "live_evidence", "reasons", "reason"):
        assert f'"{key}"' not in text


def test_an_older_run_missing_facts_gives_null_not_an_error() -> None:
    old = full_run()
    for key in ("stop_cause", "cost_usd", "items_run"):
        del old[key]
    del old["versions"]["judge"]
    del old["versions"]["guard_prompt"]
    del old["dataset_sha256"]

    board = boards.board_of(old, stamp="20261019T152212Z")

    assert board["facts"]["judgeVersion"] is None
    assert board["facts"]["guardPromptVersion"] is None
    assert board["facts"]["datasetSha256"] is None
    assert board["costUsd"] is None


def escalation_run(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "mode": "live",
        "set": "escalation",
        "trials": 3,
        "commit": "abc-dirty",
        "date": "2026-10-27T23:49:09+00:00",
        "half_run": "both",
        "scored_half": "held_out",
        "models": {"guard": "claude-haiku-5-5"},
        "guard_prompt": "2026-11.1",
        "dataset_sha256": {"messages.yaml": "cc"},
        "cap_usd": "0.50",
        "cost_usd": "0.051754",
        "metrics": {
            "calls": 147,
            "crisis_recall_by_trial": [1.0, 1.0, 0.9],
            "sensitive_recall": 1.0,
            "ordinary_no_offer": 1.0,
        },
        "misses": [{"item": "esc-04", "trial": 3, "label": "crisis"}],
        "gaps": [],
    }
    document.update(overrides)
    return document


def test_escalation_uses_the_same_schema_with_its_own_metrics() -> None:
    board = boards.board_of(escalation_run(), stamp="20261027T234352Z")

    assert board["set"] == "escalation"
    assert board["facts"]["model"] == "claude-haiku-5-5"
    assert board["facts"]["guardPromptVersion"] == "2026-11.1"
    assert board["facts"]["effort"] is None
    assert board["facts"]["promptVersion"] is None
    assert board["metrics"]["crisis_recall"] == {
        "mean": pytest.approx(0.9666, abs=1e-3),
        "min": 0.9,
    }
    # An older file has no per-trial lists, so a mean of 1.0 means every trial was 1.0.
    assert board["metrics"]["sensitive_recall"] == {"mean": 1.0, "min": 1.0}
    assert board["failures"] == ["esc-04"]
    assert board["costUsd"] == {"total": "0.051754", "cap": "0.50"}


def test_escalation_minimum_is_unknown_when_an_older_file_missed_something() -> None:
    run = escalation_run()
    run["metrics"]["sensitive_recall"] = 0.95

    board = boards.board_of(run, stamp="20261027T234352Z")

    assert board["metrics"]["sensitive_recall"] == {"mean": 0.95, "min": None}


def test_escalation_new_runs_record_per_trial_values_for_every_figure() -> None:
    esc = load_escalation()
    calls = [
        esc.Call(
            trial=trial,
            item_id=f"e-{trial}-{n}",
            half="held_out",
            label=label,
            expected_kind=None,
            route="resource",
            category=None,
            kind=None,
            shown=None,
            offers_case=label == "sensitive",
            unavailable=False,
            gap=False,
            latency_ms=10,
        )
        for trial in (1, 2)
        for n, label in enumerate(("crisis", "sensitive", "ordinary"))
    ]
    metrics = esc.half_metrics(calls)
    assert len(metrics["sensitive_recall_by_trial"]) == 2
    assert len(metrics["ordinary_no_offer_by_trial"]) == 2


def case_summary_run() -> dict[str, Any]:
    lines = {"faithful": 22, "neutral": 22, "no_recommendation": 22, "keeps_uncertainty": 22}
    return {
        "mode": "live",
        "set": "case-summary",
        "trials": 3,
        "commit": "e33-dirty",
        "date": "2026-10-30T21:37:55+00:00",
        "models": {"summary": "claude-opus-5-5", "judge": "claude-sonnet-5-5"},
        "summary_prompt": "2026-11.2",
        "judge_version": "2026-11.1",
        "dataset_sha256": {"narratives.yaml": "dd"},
        "cap_usd": "3.00",
        "cost_usd": "0.516096",
        "by_trial": [
            {"trial": 1, "items": 22, "program_passed": 22, "judge_lines": lines, "judged": 22},
            {"trial": 2, "items": 22, "program_passed": 21, "judge_lines": lines, "judged": 22},
        ],
        "failures": [{"item": "cs-05", "trial": 2, "error": None, "problems": [PLANTED]}],
        "judge_not_passed": [{"item": "cs-09", "trial": 1, "failed": ["neutral"]}],
        "gaps": [],
    }


def test_case_summary_board_counts_summaries_passing_every_check_and_the_judge() -> None:
    board = boards.board_of(case_summary_run(), stamp="20261030T213352Z")

    assert board["set"] == "case-summary"
    assert board["facts"]["model"] == "claude-opus-5-5"
    assert board["facts"]["promptVersion"] == "2026-11.2"
    assert board["facts"]["judgeVersion"] == "2026-11.1"
    assert board["facts"]["guardPromptVersion"] is None
    checks = board["metrics"]["passed_every_check"]
    assert checks["min"] == pytest.approx(21 / 22)
    assert checks["mean"] == pytest.approx((1 + 21 / 22) / 2)
    assert checks["itemsPerTrial"] == 22
    judge = board["metrics"]["passed_by_judge"]
    assert judge["min"] == pytest.approx(21 / 22)
    assert board["failures"] == ["cs-05", "cs-09"]
    assert PLANTED not in json.dumps(board)


def retrieval_run() -> dict[str, Any]:
    return {
        "model": "voyage-3",
        "dimensions": 1024,
        "datasetSha256": "ee",
        "commit": "f00-dirty",
        "date": "2026-11-01T12:00:00+00:00",
        "handbookVersion": "2026.11.1",
        "overall": {"questions": 50, "hits": 50, "hitRateAt5": 1.0, "meanReciprocalRank": 0.9},
        "perAsker": {},
        "misses": [{"id": "r-04", "question": PLANTED, "returned": ["1.1"]}],
        "negatives": [{"id": "n-1", "passed": True}, {"id": "n-2", "passed": False}],
        "fulltextFallbacks": [],
        "passed": False,
    }


def test_retrieval_board_has_one_trial_and_no_cost() -> None:
    board = boards.board_of(retrieval_run(), stamp="20261101T120000Z")

    assert board["set"] == "retrieval"
    assert board["facts"]["trials"] == 1
    assert board["facts"]["model"] == "voyage-3"
    assert board["facts"]["handbookVersion"] == "2026.11.1"
    assert board["facts"]["datasetSha256"] == {"dataset.yaml": "ee"}
    assert board["metrics"]["hit_rate_at_5"] == {"mean": 1.0, "min": 1.0}
    assert board["metrics"]["negatives_passing"] == {"mean": 0.5, "min": 0.5}
    assert board["failures"] == ["r-04", "n-2"]
    assert board["costUsd"] is None
    assert PLANTED not in json.dumps(board)


# --- Writing ----------------------------------------------------------------------------------


def test_write_boards_names_the_board_after_the_run_file_and_writes_it_twice(
    tmp_path: Path,
) -> None:
    runs, out = tmp_path / "runs", tmp_path / "scoreboards"
    runs.mkdir()
    run_file = runs / "20261029T142328Z-full.json"

    written = boards.write_boards(run_file, full_run(), out)

    assert written == out / "20261029T142328Z-full.json"
    beside = runs / "20261029T142328Z-full-board.json"
    assert json.loads(written.read_text()) == json.loads(beside.read_text())
    assert json.loads(written.read_text())["stamp"] == "20261029T142328Z"


def test_smoke_and_replay_runs_get_no_board(tmp_path: Path) -> None:
    run_file = tmp_path / "20261029T142328Z-smoke.json"

    assert boards.write_boards(run_file, full_run(set="smoke"), tmp_path / "out") is None
    assert boards.write_boards(run_file, full_run(mode="offline"), tmp_path / "out") is None
    assert not (tmp_path / "out").exists()


def test_a_run_file_without_a_stamp_gets_no_board(tmp_path: Path) -> None:
    assert boards.write_boards(tmp_path / "board.json", full_run(), tmp_path / "out") is None


async def test_a_live_escalation_run_writes_its_board_and_a_scratch_run_does_not(
    tmp_path: Path,
) -> None:
    from tests.test_escalation_eval import FakeGuard, answer_by_label, esc, make_env, run

    items = esc.load_messages()
    out = tmp_path / "scoreboards"

    async def live(*extra: str) -> int:
        code: int = await run.run_cli(
            ["--mode", "live", "--set", "escalation", "--yes",
             "--fixtures-dir", str(tmp_path / "f"),
             "--json", str(tmp_path / "runs" / "20261101T010203Z-escalation.json"),
             "--boards-dir", str(out), *extra],
            env=make_env(tmp_path / "f", FakeGuard(answer_by_label(items))),
        )  # fmt: skip
        return code

    assert await live() == 0
    board = json.loads((out / "20261101T010203Z-escalation.json").read_text())
    assert board["set"] == "escalation"
    assert "sensitive_recall" in board["metrics"]


async def test_a_replay_writes_no_board(tmp_path: Path) -> None:
    from tests.test_escalation_eval import FakeGuard, answer_by_label, esc, make_env, run

    items = esc.load_messages()
    env = make_env(tmp_path, FakeGuard(answer_by_label(items)))
    await run.run_cli(
        ["--mode", "live", "--set", "escalation", "--yes", "--fixtures-dir", str(tmp_path)],
        env=env,
    )
    out = tmp_path / "scoreboards"

    code = await run.run_cli(
        ["--mode", "offline", "--set", "escalation", "--check", "--fixtures-dir", str(tmp_path),
         "--json", str(tmp_path / "20261101T010203Z-escalation.json"), "--boards-dir", str(out)],
        env=make_env(tmp_path),
    )  # fmt: skip

    assert code == 0
    assert not out.exists()


def test_the_retrieval_run_names_its_board_after_its_own_date(tmp_path: Path) -> None:
    retrieval = load_retrieval()
    out = tmp_path / "scoreboards"

    assert not hasattr(retrieval, "board_stamp")
    path = retrieval.write_board(retrieval_run(), out)

    assert path == out / "20261101T120000Z-retrieval.json"
    assert json.loads(path.read_text())["set"] == "retrieval"


# --- The Makefile -----------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
def test_make_passes_a_scratch_fixtures_folder_through_and_no_flag_to_skip_the_board() -> None:
    def dry(*variables: str) -> str:
        return subprocess.run(  # noqa: S603
            ["make", "-n", "eval-live", *variables],  # noqa: S607
            cwd=EVAL_DIR.parents[1],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    scratch = dry("SET=escalation", "HALF=tuning", "FIXTURES_DIR=/tmp/scratch")
    assert "--no-board" not in dry("SET=full")
    assert "--no-board" not in scratch
    assert "--fixtures-dir /tmp/scratch" in scratch


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
def test_make_eval_retrieval_writes_a_board_only_with_write() -> None:
    def dry(*variables: str) -> str:
        return subprocess.run(  # noqa: S603
            ["make", "-n", "eval-retrieval", *variables],  # noqa: S607
            cwd=EVAL_DIR.parents[1],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    assert "--write-board" not in dry()
    assert "--write-board" in dry("WRITE=1")


def test_the_gitignore_names_the_committed_scoreboards_folder() -> None:
    text = (EVAL_DIR.parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert "evals/scoreboards/" in text


# --- The backfill -----------------------------------------------------------------------------


def test_the_backfill_of_a_run_file_equals_the_live_writers_board(tmp_path: Path) -> None:
    from tests.assistant_eval import load_evals_script

    backfill = load_evals_script("backfill_boards")
    runs = tmp_path / "runs"
    runs.mkdir()
    run_file = runs / "20261029T142328Z-full.json"
    run_file.write_text(json.dumps(full_run()), encoding="utf-8")
    live_dir, backfill_dir = tmp_path / "live", tmp_path / "backfill"

    boards.write_boards(run_file, full_run(), live_dir)
    code = backfill.main([str(run_file), "--boards-dir", str(backfill_dir)])

    name = "20261029T142328Z-full.json"
    assert code == 0
    assert (backfill_dir / name).read_text() == (live_dir / name).read_text()
    # The backfill only reads the run folder: the one extra file is the live writer's copy.
    assert {p.name for p in runs.iterdir()} == {name, "20261029T142328Z-full-board.json"}


def test_the_backfill_refuses_a_smoke_run_and_a_file_with_no_stamp(tmp_path: Path) -> None:
    from tests.assistant_eval import load_evals_script

    backfill = load_evals_script("backfill_boards")
    smoke = tmp_path / "20261029T142328Z-smoke.json"
    smoke.write_text(json.dumps(full_run(set="smoke")), encoding="utf-8")
    plain = tmp_path / "board.json"
    plain.write_text(json.dumps(full_run()), encoding="utf-8")

    assert backfill.main([str(smoke), "--boards-dir", str(tmp_path / "out")]) == 2
    assert backfill.main([str(plain), "--boards-dir", str(tmp_path / "out")]) == 2
    assert not (tmp_path / "out").exists()


def runner_args(tmp_path: Path, name: str, **overrides: Any) -> Any:
    import argparse
    from types import SimpleNamespace

    default = tmp_path / "fixtures"
    args = argparse.Namespace(
        json=tmp_path / "runs" / name,
        boards_dir=tmp_path / "scoreboards",
        fixtures_dir=default,
        set="full",
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    env = SimpleNamespace(committed_fixtures_dir=default, effort_fixtures_dir=tmp_path / "effort")
    return args, env


def test_the_assistant_runner_boards_a_full_run(tmp_path: Path) -> None:
    from tests.assistant_eval import load_runner

    args, env = runner_args(tmp_path, "20261029T142328Z-full.json")

    load_runner()._write_board(args, env, full_run())

    assert [p.name for p in args.boards_dir.iterdir()] == ["20261029T142328Z-full.json"]


@pytest.mark.parametrize(
    ("name", "overrides", "document", "reason"),
    [
        ("20261029T142328Z-smoke.json", {}, {"set": "smoke"}, "smoke"),
        ("20261029T142328Z-full.json", {}, {"mode": "offline"}, "replay"),
        ("board.json", {}, {}, "stamp"),
        ("20261029T142328Z-full.json", {"fixtures_dir": Path("/scratch")}, {}, "scratch"),
        ("20261029T142328Z-effort.json", {"set": "effort"}, {"set": "effort"}, "scratch"),
        ("20261029T142328Z-escalation.json", {}, {"scored_half": "tuning"}, "tuning"),
    ],
)  # fmt: skip
def test_every_skipped_board_says_why(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    name: str,
    overrides: dict[str, Any],
    document: dict[str, Any],
    reason: str,
) -> None:
    from tests.assistant_eval import load_runner

    args, env = runner_args(tmp_path, name, **overrides)

    load_runner()._write_board(args, env, full_run(**document))

    out = capsys.readouterr().out
    assert out.startswith("No board: ")
    assert out.count("No board:") == 1
    assert reason in out
    assert not args.boards_dir.exists()


def test_the_effort_set_is_boarded_in_its_own_fixtures_folder(tmp_path: Path) -> None:
    from tests.assistant_eval import load_runner

    args, env = runner_args(tmp_path, "20261029T142328Z-effort.json", set="effort")
    args.fixtures_dir = env.effort_fixtures_dir

    load_runner()._write_board(args, env, full_run(set="effort"))

    assert (args.boards_dir / "20261029T142328Z-effort.json").exists()


def test_a_partial_run_is_boarded_but_says_it_will_not_be_shown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.assistant_eval import load_runner

    args, env = runner_args(tmp_path, "20261029T142328Z-full.json")

    load_runner()._write_board(args, env, full_run(partial=True))

    assert (args.boards_dir / "20261029T142328Z-full.json").exists()
    out = capsys.readouterr().out
    assert "partial" in out
    assert "won't be shown" in out


def test_the_judge_agreement_status_is_carried_into_the_board() -> None:
    run = full_run()
    run["metrics"]["judge_agreement"]["status"] = "not_accepted"

    board = boards.board_of(run, stamp="20261029T142328Z")

    assert board["metrics"]["judge_agreement"]["status"] == "not_accepted"


def test_the_agreement_bar_has_one_home() -> None:
    from tests.assistant_eval import load_runner

    runner = load_runner()
    assert runner.MIN_AGREEMENT == boards.MIN_AGREEMENT == 0.90
    # The runner takes the bar from the board module instead of repeating the number.
    assert "MIN_AGREEMENT = boards.MIN_AGREEMENT" in Path(str(runner.__file__)).read_text("utf-8")


def test_a_summary_the_judge_never_saw_is_not_a_judge_failure() -> None:
    run = case_summary_run()
    run["by_trial"] = [
        {"trial": 1, "items": 22, "program_passed": 22, "judge_lines": {}, "judged": 20},
    ]
    run["judge_not_passed"] = []

    judge = boards.board_of(run, stamp="20261030T213352Z")["metrics"]["passed_by_judge"]

    assert judge["mean"] == 1.0
    assert judge["itemsPerTrial"] == 20
    assert judge["notJudgedPerTrial"] == 2


def test_a_stamp_for_a_non_utc_date_is_converted_to_utc() -> None:
    assert boards.stamp_of_date("2026-11-01T23:30:00-05:00") == "20261102T043000Z"


def test_write_boards_names_a_run_with_no_run_file_by_its_stamp_and_set(tmp_path: Path) -> None:
    target = boards.write_boards(None, retrieval_run(), tmp_path / "out", stamp="20261101T120000Z")

    assert target == tmp_path / "out" / "20261101T120000Z-retrieval.json"
    assert json.loads(target.read_text(encoding="utf-8"))["stamp"] == "20261101T120000Z"
    assert [p.name for p in (tmp_path / "out").iterdir()] == [target.name]
    with pytest.raises(ValueError, match="stamp"):
        boards.write_boards(None, retrieval_run(), tmp_path / "out")


def test_a_metric_with_no_data_is_null_on_the_board_and_a_dash_on_the_scoreboard() -> None:
    run = full_run(
        partial=True,
        metrics={
            "action_pass_rate": None,
            "judge_pass_rate": None,
            "redteam_pass_rate": {"mean": 1.0, "min": 1.0},
            "redteam_pass_rate_by_group": {"routing": None, "other": {"mean": 1.0, "min": 1.0}},
        },
    )

    board = boards.board_of(run, stamp="20261029T142328Z")

    assert board["metrics"]["action_pass_rate"] is None
    assert board["metrics"]["judge_pass_rate"] is None
    assert board["metrics"]["redteam_pass_rate_by_group.routing"] is None
    assert board["metrics"]["redteam_pass_rate"] == {"mean": 1.0, "min": 1.0}
