"""The scoreboard generator (ADR 0017): committed run boards in, README section and JSON out.

Run it from apps/api (`make scoreboard`):

    uv run python ../../evals/scoreboard_gen.py [--check]

It reads every board in `evals/scoreboards/` and writes two things:

- the README's scoreboard, between `<!-- scoreboard:start -->` and `<!-- scoreboard:end -->`;
- `apps/web/src/generated/scoreboard.json`, which the AI Ops console bundles:
  `{"schema": 1, "sets": [SetRow], "history": [HistoryRow]}`.

`--check` writes nothing and exits 1 when either file differs from what the boards give, so CI
holds the boards and the published figures together (like the API client's drift check).

The generator is pure. It reads boards and the pinned assistant model, and nothing else: no
database, no network. The pinned model is read from the app's code (`CURRENT_PINS.model`).

A row is one set's newest board. The assistant sets (policy Q&A, answer quality, red team,
actions, and later fairness) read the newest `full` board on the pinned model, so a run on another
model never replaces the figures the app ships with. Escalation, case summary, and retrieval read
their own newest board. A set with no board yet is "Not run yet". The `effort` board is the
effort comparison, not a scoreboard row.
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

EVALS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVALS_ROOT.parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

from assistant import boards as run_boards  # noqa: E402

BOARDS_DIR = run_boards.SCOREBOARDS_DIR
README_PATH = REPO_ROOT / "README.md"
JSON_PATH = REPO_ROOT / "apps" / "web" / "src" / "generated" / "scoreboard.json"
START_MARKER = "<!-- scoreboard:start -->"
END_MARKER = "<!-- scoreboard:end -->"
SCHEMA = 1

NOT_RUN = "Not run yet"
NO_TRIALS = "No trials: retrieval is exact."
GROUPS_ACROSS_TRIALS = "Groups are judged across all trials."
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
NUMBER_WORDS = {
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
}
SMALL_SET_NOTE = (
    "The sets are small ({items}), so a single item can move a figure by more than a point."
)
REPLAY_NOTE = (
    "These figures come from recorded eval runs. CI replays the recordings on every change, so it"
    " checks the app's handling, not the model."
)
TRIALS_NOTE = "Three trials per set unless noted."


class ScoreboardError(Exception):
    """The generator can't do its job: broken markers, or a board it can't read."""


def pinned_model() -> str:
    """The assistant model the app ships with."""
    from app.ai.conversations import CURRENT_PINS

    return CURRENT_PINS.model


def _read_board(path: Path) -> dict[str, Any]:
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ScoreboardError(f"{path.name}: can't read the board ({error})") from error
    if not isinstance(board, dict):
        raise ScoreboardError(f"{path.name}: a board is a JSON object")
    for field in ("stamp", "set", "facts", "metrics"):
        if field not in board:
            raise ScoreboardError(f"{path.name}: the board has no {field!r}")
    if board.get("schema") != run_boards.SCHEMA:
        raise ScoreboardError(f"{path.name}: unknown schema {board.get('schema')}")
    if not isinstance(board["facts"], dict) or not isinstance(board["metrics"], dict):
        raise ScoreboardError(f"{path.name}: 'facts' and 'metrics' are objects")
    return board


def load_boards(boards_dir: Path = BOARDS_DIR) -> list[dict[str, Any]]:
    """Every board in the folder, oldest first (by stamp, then set). A board that can't be read
    is an error naming its file."""
    found = [_read_board(path) for path in sorted(boards_dir.glob("*.json"))]
    return sorted(found, key=lambda b: (b["stamp"], b["set"]))


def _shown(board: Mapping[str, Any]) -> bool:
    """Whether a board may be a scoreboard row or a history line. A partial run (a cap or an error
    stopped it) isn't comparable, and a tuning-half escalation run isn't the held-out figure."""
    facts = board["facts"]
    if facts.get("partial"):
        return False
    return not (board["set"] == "escalation" and facts.get("scoredHalf") == "tuning")


# --- Formatting -------------------------------------------------------------------------------


def pct(value: float, *, places: int = 0) -> str:
    """A rate as a percentage, rounded half up."""
    scaled = Decimal(str(value)) * 100
    return f"{scaled.quantize(Decimal(1).scaleb(-places), rounding='ROUND_HALF_UP'):f}%"


def _stamp_date(stamp: str) -> str:
    return f"{MONTHS[int(stamp[4:6]) - 1]} {int(stamp[6:8])}, {stamp[:4]}"


def _stamp_moment(stamp: str) -> str:
    return f"{_stamp_date(stamp)}, {stamp[9:11]}:{stamp[11:13]} UTC"


def _count(value: float, items: int | None) -> str:
    """'22 of 22' when the figure is a whole count of a known number of items, else a percentage."""
    if items:
        whole = value * items
        if abs(whole - round(whole)) < 1e-6:
            return f"{round(whole)} of {items}"
    return pct(value)


def _metric(board: Mapping[str, Any] | None, name: str) -> Mapping[str, Any] | None:
    if board is None:
        return None
    found = board["metrics"].get(name)
    return found if found and found.get("mean") is not None else None


def _figure(label: str, value: float, display: str) -> dict[str, Any]:
    return {"label": label, "value": value, "display": display}


# --- The rows ---------------------------------------------------------------------------------


def _not_run(key: str, name: str) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "detail": None,
        "notRun": True,
        "headline": None,
        "lowest": None,
        "also": [],
        "facts": None,
    }


def _row(
    key: str,
    name: str,
    detail: str,
    board: Mapping[str, Any],
    headline: dict[str, Any],
    lowest: dict[str, Any],
    also: Sequence[str],
) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "detail": detail,
        "notRun": False,
        "headline": headline,
        "lowest": lowest,
        "also": list(also),
        "facts": {**board["facts"], "stamp": board["stamp"], "set": board["set"]},
    }


def _lowest(metric: Mapping[str, Any], text: str | None = None) -> dict[str, Any]:
    low = metric.get("min")
    if text is not None:
        return {"value": None, "display": text}
    return {"value": low, "display": "-" if low is None else pct(low)}


def _newest(
    boards: Sequence[Mapping[str, Any]],
    set_name: str,
    model: str | None,
    *,
    has: str | None = None,
) -> Any:
    """The newest board of the set on the model; with `has`, the newest that has that metric."""
    matching = [
        b
        for b in boards
        if _shown(b)
        and b["set"] == set_name
        and (model is None or b["facts"].get("model") == model)
        and (has is None or _metric(b, has) is not None)
    ]
    return matching[-1] if matching else None


def _group_names(metrics: Mapping[str, Any], prefix: str) -> list[tuple[str, Mapping[str, Any]]]:
    return [
        (name[len(prefix) :].replace("_", " "), value)
        for name, value in sorted(metrics.items())
        if name.startswith(prefix)
    ]


def _retrieval_row(board: Mapping[str, Any] | None) -> dict[str, Any]:
    hit = _metric(board, "hit_rate_at_5")
    if board is None or hit is None:
        return _not_run("retrieval", "Retrieval")
    negatives = _metric(board, "negatives_passing")
    also = []
    if negatives is not None:
        also.append(
            "Every negative passed."
            if negatives["mean"] == 1.0
            else f"Negative cases passing {pct(negatives['mean'])}"
        )
    version = board["facts"].get("handbookVersion")
    return _row(
        "retrieval",
        "Retrieval",
        f"Handbook {version}" if version else _stamp_date(board["stamp"]),
        board,
        _figure("Hit rate at 5", hit["mean"], pct(hit["mean"])),
        _lowest(hit, NO_TRIALS),
        also,
    )


def _qa_row(board: Mapping[str, Any] | None) -> dict[str, Any]:
    qa = _metric(board, "qa_deterministic_pass_rate")
    if board is None or qa is None:
        return _not_run("qa", "Policy Q&A")
    unanswerable = _metric(board, "unanswerable_pass_rate")
    also = []
    if unanswerable is not None:
        also.append(
            f"Unanswerable {pct(unanswerable['mean'])}, lowest {pct(unanswerable['min'])}"
            if unanswerable.get("min") is not None
            else f"Unanswerable {pct(unanswerable['mean'])}"
        )
    return _row(
        "qa",
        "Policy Q&A",
        f"Full run, {_stamp_date(board['stamp'])}",
        board,
        _figure("Program checks", qa["mean"], pct(qa["mean"])),
        _lowest(qa),
        also,
    )


def _uncited_text(mean: float) -> str:
    """The uncited claims per trial: a whole number as it is, else one decimal, and never a
    nonzero mean shown as 0."""
    if abs(mean - round(mean)) < 1e-6:
        count = round(mean)
        return f"{count} uncited claim{'' if count == 1 else 's'}"
    text = f"{mean:.1f}"
    if float(text) == 0:
        text = f"{mean:.2f}"
    return f"{text} uncited claims"


def _quality_row(board: Mapping[str, Any] | None) -> dict[str, Any]:
    judge = _metric(board, "judge_pass_rate")
    if board is None or judge is None:
        return _not_run("quality", "Answer quality")
    also = [f"Target {pct(run_boards.JUDGE_PASS_TARGET)}"]
    agreement_status = None
    uncited = _metric(board, "judge_uncited_claim_count")
    if uncited is not None:
        also.append(_uncited_text(uncited["mean"]))
    agreement = _metric(board, "judge_agreement")
    if agreement is not None:
        agreement_status = agreement.get("status")
        note = {
            "not_accepted": f" (below the {pct(run_boards.MIN_AGREEMENT)} bar)",
            "incomplete": " (incomplete: some hand-graded answers were not judged)",
        }.get(agreement_status or "", "")
        also.append(
            f"Judge agreement with the hand grades {pct(agreement['mean'], places=1)}{note}"
        )
    row = _row(
        "quality",
        "Answer quality",
        _stamp_date(board["stamp"]),
        board,
        _figure("Judge pass rate", judge["mean"], pct(judge["mean"])),
        _lowest(judge),
        also,
    )
    row["agreementStatus"] = agreement_status
    return row


def _redteam_row(board: Mapping[str, Any] | None) -> dict[str, Any]:
    red = _metric(board, "redteam_pass_rate")
    if board is None or red is None:
        return _not_run("redteam", "Red team")
    groups = _group_names(board["metrics"], "redteam_pass_rate_by_group.")
    also = []
    if groups:
        names = ", ".join(name for name, _ in groups)
        if all(value["mean"] == 1.0 for _, value in groups):
            word = NUMBER_WORDS.get(len(groups), str(len(groups)))
            also.append(f"All {word} groups at 100%: {names}.")
        else:
            also.append("By group: " + ", ".join(f"{n} {pct(v['mean'])}" for n, v in groups) + ".")
    every_trial = red.get("min") == 1.0
    return _row(
        "redteam",
        "Red team",
        _stamp_date(board["stamp"]),
        board,
        _figure("In every trial" if every_trial else "Pass rate", red["mean"], pct(red["mean"])),
        _lowest(red),
        also,
    )


def _actions_row(board: Mapping[str, Any] | None) -> dict[str, Any]:
    actions = _metric(board, "action_pass_rate")
    if board is None or actions is None:
        return _not_run("actions", "Actions")
    numbers = _metric(board, "action_numbers_match_rate")
    also = [f"Numbers match the engine {pct(numbers['mean'])}"] if numbers is not None else []
    return _row(
        "actions",
        "Actions",
        _stamp_date(board["stamp"]),
        board,
        _figure("Pass rate", actions["mean"], pct(actions["mean"])),
        _lowest(actions),
        also,
    )


# The order the attributes are listed in (evals/fairness/groups.yaml).
ATTRIBUTE_ORDER = ("name", "parent", "religion", "age", "origin", "spouse")


def _plural_of(count: float, word: str) -> str:
    whole = round(count)
    return f"{whole} {word}{'' if whole == 1 else 's'}"


def _fairness_row(board: Mapping[str, Any] | None) -> dict[str, Any]:
    groups = _metric(board, "fairness_groups_consistent")
    if board is None or groups is None:
        return _not_run("fairness", "Fairness")
    also = []
    assumptions = _metric(board, "fairness_identity_assumptions")
    if assumptions is not None:
        worst = assumptions.get("max")
        worst = assumptions["mean"] if worst is None else worst
        also.append(
            "No identity assumption in any trial"
            if worst == 0
            else f"{_plural_of(worst, 'identity assumption')} in the worst trial"
        )
    equivalence = _metric(board, "fairness_judge_equivalence")
    if equivalence is not None:
        text = f"Judge equivalence {pct(equivalence['mean'])}"
        if equivalence.get("min") is not None:
            text += f" (lowest trial {pct(equivalence['min'])})"
        also.append(text)
    unavailable = _metric(board, "fairness_judge_unavailable")
    if unavailable is not None:
        most = unavailable.get("max")
        most = unavailable["mean"] if most is None else most
        if most:
            also.append(f"Up to {_plural_of(most, 'comparison')} unavailable in a trial")
    by_attribute = {
        name: value
        for name, value in _group_names(board["metrics"], "fairness_consistent_by_group.")
        if value and value.get("mean") is not None
    }
    ordered = [a for a in ATTRIBUTE_ORDER if a in by_attribute] + sorted(
        a for a in by_attribute if a not in ATTRIBUTE_ORDER
    )
    if ordered:
        also.append(
            "Groups consistent by attribute: "
            + ", ".join(f"{a} {pct(by_attribute[a]['mean'])}" for a in ordered)
            + "."
        )
    regraded = board["facts"].get("fairnessRegraded")
    if regraded:
        # The run's traces and pairwise verdicts are the recorded ones; the checks are newer.
        day = regraded["date"]
        also.append(f"Graded again from the saved run on {day}; no new model calls")
    return _row(
        "fairness",
        "Fairness",
        _stamp_date(board["stamp"]),
        board,
        _figure(
            "Groups consistent", groups["mean"], _count(groups["mean"], groups.get("itemsPerTrial"))
        ),
        _lowest(groups, GROUPS_ACROSS_TRIALS),
        also,
    )


def _escalation_row(board: Mapping[str, Any] | None) -> dict[str, Any]:
    crisis = _metric(board, "crisis_recall")
    if board is None or crisis is None:
        return _not_run("escalation", "Escalation")
    also = []
    sensitive = _metric(board, "sensitive_recall")
    if sensitive is not None:
        also.append(f"Sensitive recall {pct(sensitive['mean'])}")
    ordinary = _metric(board, "ordinary_no_offer")
    if ordinary is not None:
        also.append(f"Ordinary questions offered no case {pct(ordinary['mean'])}")
    return _row(
        "escalation",
        "Escalation",
        _stamp_date(board["stamp"]),
        board,
        _figure("Crisis recall", crisis["mean"], pct(crisis["mean"])),
        _lowest(crisis),
        also,
    )


def _judge_text(judge: Mapping[str, Any]) -> str:
    """'By the judge: N of M' (M the summaries judged), plus '(K not judged)' when some weren't."""
    text = f"By the judge: {_count(judge['mean'], judge.get('itemsPerTrial'))}"
    missing = judge.get("notJudgedPerTrial") or 0
    return f"{text} ({missing} not judged)" if missing else text


def _case_summary_row(board: Mapping[str, Any] | None) -> dict[str, Any]:
    checks = _metric(board, "passed_every_check")
    if board is None or checks is None:
        return _not_run("case-summary", "Case summary")
    items = checks.get("itemsPerTrial")
    low = checks.get("min")
    judge = _metric(board, "passed_by_judge")
    return _row(
        "case-summary",
        "Case summary",
        _stamp_date(board["stamp"]),
        board,
        _figure("Passed every check", checks["mean"], _count(checks["mean"], items)),
        {"value": low, "display": "-" if low is None else _count(low, items)},
        [_judge_text(judge)] if judge else [],
    )


def _history_row(board: Mapping[str, Any]) -> dict[str, Any]:
    def figure(name: str) -> str | None:
        metric = _metric(board, name)
        return None if metric is None else pct(metric["mean"])

    cost = board.get("costUsd")
    return {
        "stamp": board["stamp"],
        "date": _stamp_moment(board["stamp"]),
        "model": board["facts"].get("model"),
        "qa": figure("qa_deterministic_pass_rate"),
        "unanswerable": figure("unanswerable_pass_rate"),
        "redteam": figure("redteam_pass_rate"),
        "actions": figure("action_pass_rate"),
        "judge": figure("judge_pass_rate"),
        "cost": f"${Decimal(cost['total']):.2f}" if cost and cost.get("total") else None,
    }


def pinned_summary_model() -> str:
    """The case summarizer's model the app ships with."""
    from app.ai.case_summary import SUMMARY_MODEL

    return SUMMARY_MODEL


def build(
    boards: Sequence[Mapping[str, Any]], *, pinned_model: str, summary_model: str | None = None
) -> dict[str, Any]:
    """The scoreboard data: one row per set, then the history of full runs. The assistant sets
    show the newest board on the pinned assistant model and the case-summary row the newest on the
    pinned summary model (default: the same), so a model-comparison run never replaces them."""
    full = _newest(boards, "full", pinned_model)
    sets = [
        _retrieval_row(_newest(boards, "retrieval", None)),
        _qa_row(full),
        _quality_row(full),
        _redteam_row(full),
        _actions_row(full),
        _fairness_row(_newest(boards, "full", pinned_model, has="fairness_groups_consistent")),
        _escalation_row(_newest(boards, "escalation", None)),
        _case_summary_row(_newest(boards, "case-summary", summary_model or pinned_model)),
    ]
    history = [_history_row(b) for b in boards if b["set"] == "full" and _shown(b)]
    return {"schema": SCHEMA, "sets": sets, "history": history}


def dumps_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, indent=2) + "\n"


# --- The README section -----------------------------------------------------------------------


def _models_line(data: Mapping[str, Any]) -> str | None:
    for row in data["sets"]:
        facts = row["facts"]
        if row["key"] == "qa" and facts and facts.get("models"):
            models = facts["models"]
            parts = [
                f"{label} `{models[key]}`"
                for label, key in (
                    ("Assistant", "assistant"),
                    ("safety check", "guard"),
                    ("judge", "judge"),
                )
                if models.get(key)
            ]
            return ", ".join(parts) + "."
    return None


def _set_cell(row: Mapping[str, Any]) -> str:
    return row["name"] if not row["detail"] else f"{row['name']} ({row['detail']})"


def render_section(data: Mapping[str, Any]) -> str:
    """The text between the README's markers, ending in a newline."""
    lines: list[str] = []
    models = _models_line(data)
    if models:
        lines += [models, ""]
    lines += [
        TRIALS_NOTE,
        "",
        "| Set | Result | Lowest trial | Other figures |",
        "|---|---|---|---|",
    ]
    for row in data["sets"]:
        if row["notRun"]:
            lines.append(f"| {row['name']} | {NOT_RUN} | - | - |")
            continue
        head = row["headline"]
        also = "<br>".join(row["also"]) if row["also"] else "-"
        lines.append(
            f"| {_set_cell(row)} | **{head['display']}** {head['label']}"
            f" | {row['lowest']['display']} | {also} |"
        )
    lines += [
        "",
        "### History of full runs",
        "",
        "| Date | Model | Q&A | Unanswerable | Red team | Actions | Judge | Cost |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for run in data["history"]:
        cells = [
            run["date"],
            f"`{run['model']}`" if run["model"] else "-",
            *(run[k] or "-" for k in ("qa", "unanswerable", "redteam", "actions", "judge", "cost")),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    joined = next((r for r in data["history"] if r["actions"]), None)
    if joined is not None and joined is not data["history"][0]:
        lines += ["", f"Actions joined the full set on {joined['date'].rsplit(',', 1)[0]}."]
    items = next(
        (
            row["facts"].get("itemsPerTrial")
            for row in data["sets"]
            if row["key"] == "qa" and row["facts"]
        ),
        None,
    )
    size = f"{items} items in the full set" if items else "a few hundred items"
    lines += ["", REPLAY_NOTE, "", SMALL_SET_NOTE.format(items=size)]
    return "\n".join(lines) + "\n"


def replace_between_markers(text: str, body: str) -> str:
    """`text` with what lies between the scoreboard markers replaced by `body`. Each marker must
    appear exactly once, the start before the end: a README without them is an error, never a
    silent skip."""
    if text.count(START_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise ScoreboardError(
            f"the README needs exactly one {START_MARKER} and one {END_MARKER} line"
        )
    start = text.index(START_MARKER) + len(START_MARKER)
    end = text.index(END_MARKER)
    if end < start:
        raise ScoreboardError(f"{START_MARKER} must come before {END_MARKER}")
    return text[:start] + "\n" + body.rstrip("\n") + "\n" + text[end:]


# --- The command ------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the README scoreboard and its JSON.")
    parser.add_argument("--check", action="store_true", help="write nothing; fail if out of date")
    parser.add_argument("--boards-dir", type=Path, default=BOARDS_DIR)
    parser.add_argument("--readme", type=Path, default=README_PATH)
    parser.add_argument("--json", type=Path, default=JSON_PATH, dest="json_path")
    parser.add_argument("--pinned-model", default=None, help="default: the app's CURRENT_PINS")
    parser.add_argument(
        "--summary-model", default=None, help="default: the case summarizer's SUMMARY_MODEL"
    )
    args = parser.parse_args(argv)

    try:
        model = args.pinned_model or pinned_model()
        data = build(
            load_boards(args.boards_dir),
            pinned_model=model,
            summary_model=args.summary_model or pinned_summary_model(),
        )
        readme = args.readme.read_text(encoding="utf-8")
        new_readme = replace_between_markers(readme, render_section(data))
    except ScoreboardError as error:
        print(str(error), file=sys.stderr)
        return 2
    new_json = dumps_json(data)

    def shown(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(REPO_ROOT))
        except ValueError:
            return str(path)

    if args.check:
        stale = []
        if new_readme != readme:
            stale.append(args.readme)
        current = args.json_path.read_text(encoding="utf-8") if args.json_path.exists() else ""
        if new_json != current:
            stale.append(args.json_path)
        for path in stale:
            print(f"{shown(path)} is out of date. Run `make scoreboard`.")
        if not stale:
            print("The scoreboard is up to date.")
        return 1 if stale else 0

    args.readme.write_text(new_readme, encoding="utf-8")
    args.json_path.parent.mkdir(parents=True, exist_ok=True)
    args.json_path.write_text(new_json, encoding="utf-8")
    print(f"Wrote {shown(args.readme)} and {shown(args.json_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
