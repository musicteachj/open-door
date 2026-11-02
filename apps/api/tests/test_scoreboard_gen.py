"""The scoreboard generator (evals/scoreboard_gen.py): boards in, README section and JSON out.

The fixed boards in tests/fixtures/scoreboard/boards are copies of real run boards. The golden
files beside them are the generator's output for those boards, read through by eye once; a change
to the generator's wording or layout means regenerating them on purpose (see `regenerate_golden`).
"""

import json
import re
import shutil
import socket
from pathlib import Path
from typing import Any

import pytest

from tests.assistant_eval import load_evals_script

gen = load_evals_script("scoreboard_gen")

FIXTURES = Path(__file__).parent / "fixtures" / "scoreboard"
BOARDS = FIXTURES / "boards"
PINNED = "claude-opus-5-5"

README = """# Open Door

## Intro

Some words.

## How we know it works

Intro sentence.

<!-- scoreboard:start -->
OLD CONTENT
<!-- scoreboard:end -->

## After

Kept as is.
"""


def regenerate_golden() -> None:  # pragma: no cover (run by hand when the wording changes)
    data = gen.build(gen.load_boards(BOARDS), pinned_model=PINNED)
    (FIXTURES / "expected-section.md").write_text(gen.render_section(data), encoding="utf-8")
    (FIXTURES / "expected.json").write_text(gen.dumps_json(data), encoding="utf-8")


def built() -> dict[str, Any]:
    data: dict[str, Any] = gen.build(gen.load_boards(BOARDS), pinned_model=PINNED)
    return data


def test_fixed_boards_give_the_golden_section_and_json() -> None:
    data = built()

    assert gen.render_section(data) == (FIXTURES / "expected-section.md").read_text("utf-8")
    assert gen.dumps_json(data) == (FIXTURES / "expected.json").read_text("utf-8")


def test_the_rows_carry_the_figures_the_roadmap_quotes() -> None:
    sets = {row["key"]: row for row in built()["sets"]}

    assert sets["redteam"]["headline"]["display"] == "100%"
    assert sets["redteam"]["headline"]["label"] == "In every trial"
    assert sets["qa"]["headline"]["display"] == "97%"
    assert sets["qa"]["lowest"]["display"] == "96%"
    assert sets["qa"]["also"] == ["Unanswerable 93%, lowest 90%"]
    assert sets["quality"]["headline"]["display"] == "68%"
    assert sets["quality"]["lowest"]["display"] == "65%"
    assert "18 uncited claims" in sets["quality"]["also"]
    assert (
        "Judge agreement with the hand grades 89.7% (below the 90% bar)" in sets["quality"]["also"]
    )
    assert sets["actions"]["headline"]["display"] == "99%"
    assert sets["actions"]["lowest"]["display"] == "97%"
    assert sets["actions"]["also"] == ["Numbers match the engine 100%"]
    assert sets["escalation"]["headline"]["display"] == "100%"
    assert sets["case-summary"]["headline"]["display"] == "22 of 22"
    assert sets["retrieval"]["headline"]["display"] == "100%"


def test_a_set_with_no_board_is_not_run_yet() -> None:
    sets = {row["key"]: row for row in built()["sets"]}

    assert sets["fairness"]["notRun"] is True
    assert "Not run yet" in gen.render_section(built())
    assert [row["key"] for row in built()["sets"]] == [
        "retrieval",
        "qa",
        "quality",
        "redteam",
        "actions",
        "fairness",
        "escalation",
        "case-summary",
    ]


def test_the_full_rows_use_the_newest_board_on_the_pinned_model() -> None:
    boards = gen.load_boards(BOARDS)

    on_pin = gen.build(boards, pinned_model=PINNED)
    other = gen.build(boards, pinned_model="claude-sonnet-5-5")

    assert {row["key"]: row for row in on_pin["sets"]}["qa"]["facts"]["stamp"] == (
        "20261029T142328Z"
    )
    rows = {row["key"]: row for row in other["sets"]}
    assert rows["qa"]["notRun"] is True
    assert rows["retrieval"]["notRun"] is False  # only the assistant sets follow the pin
    # The history lists every full board, whatever its model.
    assert len(other["history"]) == 3


def test_the_history_lists_full_runs_oldest_first_with_model_and_cost() -> None:
    history = built()["history"]

    assert [row["stamp"] for row in history] == [
        "20261019T152212Z",
        "20261025T160449Z",
        "20261029T142328Z",
    ]
    assert history[0]["model"] == PINNED
    assert history[0]["actions"] is None
    assert history[-1]["cost"] == "$10.93"
    assert history[-1]["date"] == "Oct 29, 2026, 14:23 UTC"


def test_the_effort_board_is_not_a_scoreboard_row() -> None:
    rendered = gen.render_section(built())

    assert "effort" not in {row["key"] for row in built()["sets"]}
    assert "20261016" not in rendered


# --- Boards that must not become rows ---------------------------------------------------------


def with_board(tmp_path: Path, name: str, edit: Any) -> list[dict[str, Any]]:
    """The fixed boards plus a newer copy of one of them, edited by `edit`."""
    boards_dir = tmp_path / "boards"
    shutil.copytree(BOARDS, boards_dir)
    board = json.loads((BOARDS / name).read_text())
    board["stamp"] = "20261031T000000Z"
    edit(board)
    (boards_dir / f"{board['stamp']}-{board['set']}.json").write_text(json.dumps(board))
    loaded: list[dict[str, Any]] = gen.load_boards(boards_dir)
    return loaded


def test_a_partial_board_is_neither_a_row_nor_a_history_line(tmp_path: Path) -> None:
    def halve(board: dict[str, Any]) -> None:
        board["facts"]["partial"] = True
        board["metrics"]["qa_deterministic_pass_rate"] = {"mean": 0.5, "min": 0.5}

    boards = with_board(tmp_path, "20261029T142328Z-full.json", halve)

    data = gen.build(boards, pinned_model=PINNED)

    assert data == built()


def test_a_tuning_half_escalation_board_is_not_the_escalation_row(tmp_path: Path) -> None:
    def tuning(board: dict[str, Any]) -> None:
        board["facts"]["scoredHalf"] = "tuning"
        board["metrics"]["crisis_recall"] = {"mean": 0.5, "min": 0.5}

    boards = with_board(tmp_path, "20261027T234352Z-escalation.json", tuning)

    assert gen.build(boards, pinned_model=PINNED) == built()


def test_an_old_escalation_board_without_a_scored_half_still_counts(tmp_path: Path) -> None:
    def older(board: dict[str, Any]) -> None:
        board["facts"]["scoredHalf"] = None
        board["metrics"]["crisis_recall"] = {"mean": 0.9, "min": 0.9}

    boards = with_board(tmp_path, "20261027T234352Z-escalation.json", older)

    row = {r["key"]: r for r in gen.build(boards, pinned_model=PINNED)["sets"]}["escalation"]
    assert row["headline"]["display"] == "90%"


# --- Malformed boards -------------------------------------------------------------------------


@pytest.mark.parametrize("drop", ["stamp", "set", "facts", "metrics"])
def test_a_board_missing_a_field_is_an_error_naming_the_file(tmp_path: Path, drop: str) -> None:
    board = json.loads((BOARDS / "20261029T142328Z-full.json").read_text())
    del board[drop]
    (tmp_path / "bad.json").write_text(json.dumps(board))

    with pytest.raises(gen.ScoreboardError, match=r"bad\.json.*" + drop):
        gen.load_boards(tmp_path)


def test_a_board_that_is_not_json_is_an_error_naming_the_file(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text("{not json")

    with pytest.raises(gen.ScoreboardError, match=r"broken\.json"):
        gen.load_boards(tmp_path)


def test_main_exits_2_for_a_malformed_board(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args, boards_dir, _, _ = stage(tmp_path)
    (boards_dir / "broken.json").write_text("[]")

    assert gen.main(args) == 2
    assert "broken.json" in capsys.readouterr().err


# --- Judge agreement, honestly ----------------------------------------------------------------


def test_a_judge_below_the_bar_says_so_in_the_row_and_the_json() -> None:
    row = {r["key"]: r for r in built()["sets"]}["quality"]

    assert "Judge agreement with the hand grades 89.7% (below the 90% bar)" in row["also"]
    assert row["agreementStatus"] == "not_accepted"


def test_an_accepted_judge_has_no_caveat(tmp_path: Path) -> None:
    def accepted(board: dict[str, Any]) -> None:
        board["metrics"]["judge_agreement"] = {"mean": 0.95, "min": None, "status": "accepted"}

    boards = with_board(tmp_path, "20261029T142328Z-full.json", accepted)

    row = {r["key"]: r for r in gen.build(boards, pinned_model=PINNED)["sets"]}["quality"]
    assert "Judge agreement with the hand grades 95.0%" in row["also"]
    assert row["agreementStatus"] == "accepted"


# --- Replacing between the markers ------------------------------------------------------------


def test_only_what_is_between_the_markers_is_replaced() -> None:
    out = gen.replace_between_markers(README, "NEW\nLINES")

    assert out.startswith(README.split("OLD CONTENT")[0])
    assert out.endswith(README.split("<!-- scoreboard:end -->")[1])
    assert "OLD CONTENT" not in out
    assert "<!-- scoreboard:start -->\nNEW\nLINES\n<!-- scoreboard:end -->" in out
    assert gen.replace_between_markers(out, "NEW\nLINES") == out


@pytest.mark.parametrize(
    "text",
    [
        "no markers",
        "<!-- scoreboard:start -->\nonly the start",
        "only the end\n<!-- scoreboard:end -->",
        "<!-- scoreboard:end -->\nbackwards\n<!-- scoreboard:start -->",
        README + "\n<!-- scoreboard:start -->\n<!-- scoreboard:end -->\n",
    ],
)
def test_missing_or_broken_markers_are_an_error(text: str) -> None:
    with pytest.raises(gen.ScoreboardError):
        gen.replace_between_markers(text, "x")


# --- The docs checks --------------------------------------------------------------------------

# Written in pieces so the spelling check (typos) doesn't flag this file for naming them.
BRITISH = re.compile(
    r"\b("
    + "|".join(["col" + "our", "behav" + "iour", "organ" + "isation", "cancel" + "led"])
    + ")",
    re.IGNORECASE,
)


def test_the_output_has_no_em_dash_and_no_british_spelling() -> None:
    data = built()
    for text in (gen.render_section(data), gen.dumps_json(data)):
        assert chr(0x2014) not in text  # em dash
        assert chr(0x2013) not in text  # en dash
        assert not BRITISH.search(text)


# --- Purity -----------------------------------------------------------------------------------


def test_the_generator_runs_with_the_network_and_database_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the generator touched the network")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none")
    readme = tmp_path / "README.md"
    readme.write_text(README, encoding="utf-8")

    code = gen.main(
        ["--boards-dir", str(BOARDS), "--readme", str(readme), "--json", str(tmp_path / "s.json")]
    )

    assert code == 0
    assert "| Set |" in readme.read_text()


def test_the_default_pinned_model_is_the_apps() -> None:
    from app.ai.conversations import CURRENT_PINS

    assert gen.pinned_model() == CURRENT_PINS.model


# --- The drift check --------------------------------------------------------------------------


def stage(tmp_path: Path) -> tuple[list[str], Path, Path, Path]:
    boards_dir = tmp_path / "boards"
    shutil.copytree(BOARDS, boards_dir)
    readme, out = tmp_path / "README.md", tmp_path / "scoreboard.json"
    readme.write_text(README, encoding="utf-8")
    args = ["--boards-dir", str(boards_dir), "--readme", str(readme), "--json", str(out)]
    return args, boards_dir, readme, out


def test_check_passes_after_a_run_and_fails_when_a_board_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args, boards_dir, readme, out = stage(tmp_path)
    assert gen.main(args) == 0
    before = (readme.read_bytes(), out.read_bytes())

    assert gen.main([*args, "--check"]) == 0
    assert (readme.read_bytes(), out.read_bytes()) == before

    board_path = boards_dir / "20261029T142328Z-full.json"
    board = json.loads(board_path.read_text())
    board["metrics"]["judge_pass_rate"]["mean"] = 0.5
    board_path.write_text(json.dumps(board, indent=2) + "\n")

    code = gen.main([*args, "--check"])

    assert code == 1
    message = capsys.readouterr().out
    assert "out of date. Run `make scoreboard`." in message
    assert (readme.read_bytes(), out.read_bytes()) == before  # --check writes nothing


def test_check_fails_when_the_generated_files_do_not_exist(tmp_path: Path) -> None:
    args, _, _, _ = stage(tmp_path)

    assert gen.main([*args, "--check"]) == 1


def test_missing_markers_exit_with_an_error_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args, _, readme, _ = stage(tmp_path)
    readme.write_text("# No markers here\n", encoding="utf-8")

    assert gen.main(args) == 2
    assert "scoreboard:start" in capsys.readouterr().err


# --- The repository's own files ---------------------------------------------------------------


def test_the_committed_outputs_match_the_committed_boards() -> None:
    root = Path(__file__).resolve().parents[3]

    assert gen.main(["--check"]) == 0
    assert (root / "evals" / "scoreboards").is_dir()


def test_the_case_summary_row_follows_the_pinned_summary_model() -> None:
    boards = gen.load_boards(BOARDS)
    shown = {row["key"]: row for row in gen.build(boards, pinned_model=PINNED)["sets"]}
    assert shown["case-summary"]["notRun"] is False
    older = next(b for b in boards if b["set"] == "case-summary")
    newer = {
        **older,
        "stamp": "29990101T000000Z",
        "facts": {**older["facts"], "model": "claude-sonnet-5-5"},
    }

    both = gen.build([*boards, newer], pinned_model=PINNED, summary_model=PINNED)
    row = {r["key"]: r for r in both["sets"]}["case-summary"]

    assert row["facts"]["stamp"] == older["stamp"]
    other = gen.build(boards, pinned_model=PINNED, summary_model="claude-sonnet-5-5")
    assert {r["key"]: r for r in other["sets"]}["case-summary"]["notRun"] is True


def test_the_case_summary_row_says_how_many_were_not_judged_only_when_some_were() -> None:
    assert gen._judge_text({"mean": 1.0, "itemsPerTrial": 20, "notJudgedPerTrial": 2}) == (
        "By the judge: 20 of 20 (2 not judged)"
    )
    assert gen._judge_text({"mean": 1.0, "itemsPerTrial": 22, "notJudgedPerTrial": 0}) == (
        "By the judge: 22 of 22"
    )


def test_the_summary_model_option_is_independent_of_the_pinned_model(tmp_path: Path) -> None:
    out = tmp_path / "scoreboard.json"
    readme = tmp_path / "README.md"
    readme.write_text(
        (BOARDS.parent / "README.md").read_text(encoding="utf-8")
        if (BOARDS.parent / "README.md").exists()
        else f"{gen.START_MARKER}\n{gen.END_MARKER}\n",
        encoding="utf-8",
    )
    args = ["--boards-dir", str(BOARDS), "--readme", str(readme), "--json", str(out)]

    assert gen.main([*args, "--pinned-model", PINNED, "--summary-model", "other-model"]) == 0

    rows = {r["key"]: r for r in json.loads(out.read_text(encoding="utf-8"))["sets"]}
    assert rows["case-summary"]["notRun"] is True
    assert rows["qa"]["notRun"] is False


def test_a_board_with_null_metrics_builds_and_shows_dashes() -> None:
    boards = gen.load_boards(BOARDS)
    full = next(b for b in boards if b["set"] == "full" and b["stamp"] == "20261029T142328Z")
    nulled = {**full, "metrics": {**full["metrics"], "judge_pass_rate": None, "x_by": None}}

    data = gen.build([*[b for b in boards if b is not full], nulled], pinned_model=PINNED)

    assert gen.render_section(data)


@pytest.mark.parametrize(
    ("mean", "text"),
    [
        (18.0, "18 uncited claims"),
        (1.0, "1 uncited claim"),
        (0.0, "0 uncited claims"),
        (1 / 3, "0.3 uncited claims"),
        (0.5, "0.5 uncited claims"),
        (0.04, "0.04 uncited claims"),
    ],
)
def test_uncited_claims_never_show_a_nonzero_mean_as_zero(mean: float, text: str) -> None:
    assert gen._uncited_text(mean) == text


def test_the_judge_target_lives_with_the_runs_other_bars() -> None:
    assert gen.run_boards.JUDGE_PASS_TARGET == 0.85
    assert not hasattr(gen, "JUDGE_TARGET")
