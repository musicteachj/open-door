"""The eval runner's --model option: a run of another model records apart from the committed
fixtures, is boarded with that model, and is compared with another run fact by fact (Phase 7,
stage 2). No database and no network."""

import argparse
import dataclasses
import json
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.ai.conversations import CURRENT_PINS
from tests.assistant_eval import load_boards, load_runner, load_scoreboard
from tests.test_assistant_eval_runner import raising_env

run = load_runner()
boards = load_boards()
scoreboard = load_scoreboard()

SONNET_55 = "claude-sonnet-5-5"


def test_a_set_defaults_to_the_apps_pinned_model() -> None:
    for config in run.SETS.values():
        assert config.model == CURRENT_PINS.model


def test_model_is_an_option_and_defaults_to_none() -> None:
    parser = run.build_parser()

    assert parser.parse_args(["--set", "full"]).model is None
    assert parser.parse_args(["--set", "full", "--model", SONNET_55]).model == SONNET_55


def test_another_model_records_into_its_own_folder_unless_one_is_named() -> None:
    env = run.RunEnv()
    parser = run.build_parser()

    other = parser.parse_args(["--set", "full", "--model", SONNET_55])
    same = parser.parse_args(["--set", "full", "--model", CURRENT_PINS.model])
    other_effort = parser.parse_args(["--set", "effort", "--model", SONNET_55])
    named = parser.parse_args(
        ["--set", "full", "--model", SONNET_55, "--fixtures-dir", "elsewhere"]
    )

    assert run.resolve_fixtures_dir(other, env) == run.MODEL_FIXTURES_DIR
    assert run.MODEL_FIXTURES_DIR.name == "fixtures-sonnet"
    assert run.resolve_fixtures_dir(other_effort, env) == run.MODEL_FIXTURES_DIR
    assert run.resolve_fixtures_dir(same, env) == run.FIXTURES_DIR
    assert run.resolve_fixtures_dir(named, env) == Path("elsewhere")


@pytest.mark.parametrize("name", ["full", "smoke", "case-summary"])
async def test_another_model_is_refused_the_committed_fixtures_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    committed = tmp_path / "committed"
    committed.mkdir()
    env = raising_env(tmp_path, committed_fixtures_dir=committed)

    code = await run.run_cli(
        [
            "--mode", "live", "--set", name, "--yes", "--model", SONNET_55,
            "--fixtures-dir", str(committed),
        ],
        env=env,
    )  # fmt: skip

    assert code == 2
    err = capsys.readouterr().err
    assert "committed" in err
    assert "--model" in err
    assert not os.listdir(committed)


async def test_the_escalation_set_refuses_a_model(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await run.run_cli(
        [
            "--mode",
            "live",
            "--set",
            "escalation",
            "--model",
            SONNET_55,
            "--fixtures-dir",
            str(tmp_path),
        ],
        env=raising_env(tmp_path),
    )

    assert code == 2
    assert "guard" in capsys.readouterr().err


def board_args(tmp_path: Path, model: str | None, fixtures: Path) -> tuple[Any, Any]:
    args = argparse.Namespace(
        json=tmp_path / "runs" / "20261101T120000Z-full.json",
        boards_dir=tmp_path / "scoreboards",
        fixtures_dir=fixtures,
        set="full",
        model=model,
    )
    env = SimpleNamespace(
        committed_fixtures_dir=tmp_path / "fixtures",
        effort_fixtures_dir=tmp_path / "effort",
        model_fixtures_dir=tmp_path / "sonnet",
    )
    return args, env


def test_a_run_of_another_model_is_boarded_with_that_model_from_its_own_folder(
    tmp_path: Path,
) -> None:
    from tests.test_eval_boards import full_run

    args, env = board_args(tmp_path, SONNET_55, tmp_path / "sonnet")
    document = full_run(models={"assistant": SONNET_55, "guard": "claude-haiku-5-5", "judge": "j"})

    run._write_board(args, env, document)

    written = json.loads((args.boards_dir / "20261101T120000Z-full.json").read_text("utf-8"))
    assert written["facts"]["model"] == SONNET_55


def test_a_run_of_another_model_in_a_scratch_folder_is_not_boarded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.test_eval_boards import full_run

    args, env = board_args(tmp_path, SONNET_55, tmp_path / "scratch")

    run._write_board(args, env, full_run())

    assert "scratch" in capsys.readouterr().out
    assert not args.boards_dir.exists()


def test_the_default_model_is_still_boarded_from_the_committed_folder_only(
    tmp_path: Path,
) -> None:
    from tests.test_eval_boards import full_run

    args, env = board_args(tmp_path, None, tmp_path / "sonnet")

    run._write_board(args, env, full_run())

    assert not args.boards_dir.exists()


def test_the_estimate_names_a_model_that_is_not_the_default() -> None:
    config = run.SETS["full"]

    assert SONNET_55 not in run.estimate_text(config, 10)
    other = dataclasses.replace(config, model=SONNET_55)
    assert SONNET_55 in run.estimate_text(other, 10)


def test_the_gitignore_and_makefile_know_the_model_folder() -> None:
    root = Path(__file__).resolve().parents[3]

    assert "evals/assistant/fixtures-sonnet/" in (root / ".gitignore").read_text("utf-8")
    makefile = (root / "Makefile").read_text("utf-8")
    assert "--model $(MODEL)" in makefile
    assert "fixtures-sonnet" in makefile


# --- The comparison ---------------------------------------------------------------------------


def two_boards(**second: Any) -> tuple[Any, Any]:
    from tests.test_assistant_eval_runner import facts, outcome, record, verdict

    records = [record("qa-01", judged=outcome("qa-01", verdict()))]
    first = scoreboard.build_scoreboard(facts(), records)
    other = scoreboard.build_scoreboard(facts(**second), records)
    return first, other


def test_compare_reports_every_fact_that_differs() -> None:
    from tests.test_assistant_eval_runner import facts

    opus, sonnet = two_boards(
        effort="medium",
        trials=3,
        models={**facts().models, "assistant": SONNET_55},
        versions={**facts().versions, "prompt": "2026-11.1"},
        dataset_sha256={"redteam.yaml": "aa", "qa.yaml": "XX", "smoke.yaml": "cc"},
    )

    result = scoreboard.compare(opus, sonnet)

    differing = {row["fact"]: (row["baseline"], row["current"]) for row in result["facts"]}
    assert differing == {
        "models.assistant": ("claude-opus-5-5", SONNET_55),
        "effort": ("low", "medium"),
        "trials": (1, 3),
        "versions.prompt": ("2026-10.1", "2026-11.1"),
        "dataset_sha256.qa.yaml": ("bb", "XX"),
    }
    text = scoreboard.render_compare(result)
    for needle in (SONNET_55, "claude-opus-5-5", "effort", "versions.prompt", "qa.yaml"):
        assert needle in text


def test_compare_of_two_runs_with_the_same_facts_lists_none() -> None:
    first, second = two_boards()

    result = scoreboard.compare(first, second)

    assert result["facts"] == []
    assert "same facts" in scoreboard.render_compare(result).lower()


def test_compare_reads_a_run_that_lacks_a_fact_as_null() -> None:
    first, second = two_boards()
    del first["effort"]
    del first["versions"]

    result = scoreboard.compare(first, second)

    differing = {row["fact"]: row["baseline"] for row in result["facts"]}
    assert differing["effort"] is None
    assert differing["versions.prompt"] is None


def test_compare_still_gives_metric_deltas_and_judge_differences() -> None:
    from tests.test_assistant_eval_runner import facts, outcome, record, verdict

    a = scoreboard.build_scoreboard(facts(), [record("qa-01", judged=outcome("qa-01", verdict()))])
    b = scoreboard.build_scoreboard(
        facts(models={**facts().models, "assistant": SONNET_55}),
        [record("qa-01", judged=outcome("qa-01", verdict(correct=False)))],
    )

    result = scoreboard.compare(a, b)

    assert result["metrics"]["judge_pass_rate"]["delta"] == -1.0
    assert [d["item"] for d in result["judge_differences"]] == ["qa-01"]


def test_a_baseline_without_an_effort_is_accepted(tmp_path: Path) -> None:
    first, _ = two_boards()
    del first["effort"]
    path = tmp_path / "base.json"
    path.write_text(json.dumps(first), encoding="utf-8")

    assert run._read_baseline(path)["commit"] == "abc123"


@pytest.mark.parametrize(
    ("name", "default"), [("full", CURRENT_PINS.model), ("case-summary", run.SUMMARY_MODEL)]
)
async def test_the_default_model_with_the_other_model_folder_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, default: str
) -> None:
    folder = tmp_path / "sonnet"
    env = raising_env(tmp_path, model_fixtures_dir=folder)

    code = await run.run_cli(
        [
            "--mode",
            "live",
            "--set",
            name,
            "--yes",
            "--model",
            default,
            "--fixtures-dir",
            str(folder),
        ],
        env=env,
    )

    assert code == 2
    assert "leave MODEL" in capsys.readouterr().err
    assert not folder.exists()


@pytest.mark.parametrize("name", ["full", "case-summary"])
async def test_a_model_with_no_pinned_price_is_refused_before_anything_starts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    code = await run.run_cli(
        ["--mode", "live", "--set", name, "--yes", "--model", "claude-nonsense-9"],
        env=raising_env(tmp_path, model_fixtures_dir=tmp_path / "sonnet"),
    )

    assert code == 2
    assert "no pinned price" in capsys.readouterr().err
    assert not (tmp_path / "sonnet").exists()


async def test_the_scripted_stand_in_is_refused_as_a_model(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await run.run_cli(
        ["--mode", "live", "--set", "full", "--yes", "--model", "scripted"],
        env=raising_env(tmp_path, model_fixtures_dir=tmp_path / "sonnet"),
    )

    assert code == 2
    assert "scripted" in capsys.readouterr().err


async def test_the_default_model_refusal_names_the_sets_own_default_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "sonnet"
    env = raising_env(
        tmp_path, model_fixtures_dir=folder, effort_fixtures_dir=tmp_path / "fixtures-effort"
    )

    code = await run.run_cli(
        ["--mode", "live", "--set", "effort", "--yes", "--model", CURRENT_PINS.model,
         "--fixtures-dir", str(folder)],
        env=env,
    )  # fmt: skip

    assert code == 2
    assert "fixtures-effort" in capsys.readouterr().err


# --- The Sonnet full run's own estimate and cap -----------------------------------------------


def test_the_sonnet_full_run_is_priced_for_sonnet_and_carries_the_13_dollar_cap() -> None:
    config = run.config_for_model(run.SETS["full"], SONNET_55)

    assert config.model == SONNET_55
    assert (config.estimate_usd, config.cap_usd) == (Decimal("9.60"), Decimal("13.00"))
    text = run.estimate_text(config, 10)
    assert "$9.60" in text
    assert "$13.00 cap" in text
    assert "priced for the default model" not in text
    # The spend cap the run builds is the config's.
    assert run.SpendCap(config.cap_usd).cap_usd == Decimal("13.00")


def test_other_models_and_sets_keep_the_default_prices_and_the_note() -> None:
    other_model = run.config_for_model(run.SETS["full"], "claude-haiku-5-5")
    smoke = run.config_for_model(run.SETS["smoke"], SONNET_55)

    assert (other_model.estimate_usd, other_model.cap_usd) == (Decimal("15.50"), Decimal("18.00"))
    assert "priced for the default model" in run.estimate_text(other_model, 10)
    assert smoke.estimate_usd == Decimal("1.00")
    assert "priced for the default model" in run.estimate_text(smoke, 10)


async def test_the_dry_run_of_a_sonnet_full_run_prints_its_own_figures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await run.run_cli(
        ["--mode", "live", "--set", "full", "--model", SONNET_55, "--fixtures-dir", str(tmp_path)],
        env=raising_env(tmp_path),
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "Estimated cost $9.60." in out
    assert "$13.00 cap" in out
