"""Run boards: the small, committed summary of one live eval run (ADR 0017).

A run file in the git-ignored `runs/` folder holds every trace. A board keeps only what the
scoreboard needs: the run's facts, its metrics (the mean over trials and the lowest trial), the
IDs of the items that failed, and the cost. It holds no answer text, no reasons, no traces and no
per-item detail, so it is safe to commit and to read in review.

Four kinds of run file exist, each with its own shape, and `board_of` has one adapter for each:
the assistant sets (smoke, full, effort), the escalation set, the case-summary set, and the
retrieval eval. All of them produce the one schema documented in `board_of`. An older file that
lacks a fact gives `null` for it, never an error.

This module is pure: it imports nothing from the app and makes no call.
"""

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = 1
# The share of the hand-graded lines the judge must match to be accepted (run.py reads it too).
MIN_AGREEMENT = 0.90
# The share of answers the judge should pass, shown beside the judge pass rate on the scoreboard.
JUDGE_PASS_TARGET = 0.85
SCOREBOARDS_DIR = Path(__file__).resolve().parent.parent / "scoreboards"
BOARD_SUFFIX = "-board"
STAMP_PATTERN = re.compile(r"^(\d{8}T\d{6}Z)-")
RETRIEVAL_DATASET_NAME = "dataset.yaml"


def stamp_of(path: Path) -> str | None:
    """The `YYYYMMDDTHHMMSSZ` a run file's name starts with, or None for any other name."""
    found = STAMP_PATTERN.match(path.name)
    return found.group(1) if found else None


def stamp_of_date(iso: str) -> str:
    """The stamp for an ISO timestamp, for a run that has no run file (the retrieval eval)."""
    return datetime.fromisoformat(iso).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _pair(mean: float | None, low: float | None, **extra: Any) -> dict[str, Any]:
    return {"mean": mean, "min": low, **extra}


# Metrics where a higher number is worse, so the board keeps the worst trial (the highest) as `max`.
WORST_IS_HIGH = ("fairness_identity_assumptions", "fairness_judge_unavailable")


def _spread(value: Mapping[str, Any] | None, name: str = "") -> dict[str, Any] | None:
    """A metric's mean and lowest trial (and, for a count where more is worse, its highest); None
    for a metric with no data (null on the board)."""
    if value is None:
        return None
    if name in WORST_IS_HIGH:
        return _pair(value.get("mean"), value.get("min"), max=value.get("max"))
    if name == "fairness_groups_consistent":
        return _pair(value.get("mean"), value.get("min"), itemsPerTrial=value.get("groups"))
    return _pair(value.get("mean"), value.get("min"))


def _unique(ids: Sequence[str | None]) -> list[str]:
    seen: dict[str, None] = {}
    for item in ids:
        if item:
            seen.setdefault(item, None)
    return list(seen)


def _day(iso: str | None) -> str | None:
    return None if not iso else iso[:10]


def _money(document: Mapping[str, Any]) -> dict[str, Any] | None:
    cost = document.get("cost_usd")
    if cost is None:
        return None
    if isinstance(cost, Mapping):
        return {"total": cost.get("total"), "cap": cost.get("cap")}
    return {"total": cost, "cap": document.get("cap_usd")}


def _facts(
    document: Mapping[str, Any],
    *,
    model: str | None,
    trials: int | None,
    live: bool,
    **more: Any,
) -> dict[str, Any]:
    models = document.get("models")
    facts: dict[str, Any] = {
        "model": model,
        "models": dict(models) if isinstance(models, Mapping) else None,
        "effort": document.get("effort"),
        "promptVersion": None,
        "toolsetVersion": None,
        "guardPromptVersion": None,
        "judgeVersion": None,
        "datasetSha256": None,
        "commit": document.get("commit"),
        "trials": trials,
        "date": _day(document.get("date")),
        "live": live,
        "partial": bool(document.get("partial", False)),
    }
    facts.update(more)
    return facts


def _dataset_hashes(document: Mapping[str, Any]) -> dict[str, str] | None:
    hashes = document.get("dataset_sha256")
    return dict(hashes) if isinstance(hashes, Mapping) else None


# --- One adapter for each shape of run file ---------------------------------------------------


def _assistant_board(
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    models = document.get("models") or {}
    versions = document.get("versions") or {}
    items_run = document.get("items_run")
    trials = document.get("trials")
    facts = _facts(
        document,
        model=models.get("assistant"),
        trials=trials,
        live=document.get("mode") == "live",
        itemsPerTrial=(items_run // trials if items_run and trials else None),
    )
    facts.update(
        promptVersion=versions.get("prompt"),
        toolsetVersion=versions.get("toolset"),
        guardPromptVersion=versions.get("guard_prompt"),
        judgeVersion=versions.get("judge"),
        datasetSha256=_dataset_hashes(document),
        # Set when the fairness results were graded again from the saved traces (run.py
        # --regrade-fairness): the date and the fairness grader files' hashes. None otherwise.
        fairnessRegraded=document.get("fairness_regraded"),
    )
    metrics: dict[str, Any] = {}
    for name, value in (document.get("metrics") or {}).items():
        if name == "judge_agreement":
            if isinstance(value, Mapping) and value.get("share") is not None:
                metrics[name] = _pair(
                    value["share"],
                    None,
                    status=value.get("status"),
                    matchedLines=value.get("matched_lines"),
                    totalLines=value.get("total_lines"),
                )
        elif name.endswith("_by_group"):
            for group, spread in (value or {}).items():
                metrics[f"{name}.{group}"] = _spread(spread)
        else:
            metrics[name] = _spread(value, name)
    failures = _unique([f.get("item") for f in document.get("failures") or []])
    return facts, metrics, failures


def _per_trial(mean: float | None, by_trial: Sequence[float] | None) -> dict[str, Any]:
    """A figure with its lowest trial. A file from before the per-trial lists were recorded has
    only the mean: a mean of 1.0 means every trial was 1.0, and any other mean hides the minimum."""
    if by_trial:
        return _pair(sum(by_trial) / len(by_trial), min(by_trial))
    return _pair(mean, 1.0 if mean == 1.0 else None)


def _escalation_board(
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    models = document.get("models") or {}
    facts = _facts(
        document,
        model=models.get("guard"),
        trials=document.get("trials"),
        live=document.get("mode") == "live",
        scoredHalf=document.get("scored_half"),
    )
    facts.update(
        guardPromptVersion=document.get("guard_prompt"),
        datasetSha256=_dataset_hashes(document),
    )
    m = document.get("metrics") or {}
    crisis = m.get("crisis_recall_by_trial") or []
    metrics = {
        "crisis_recall": _per_trial(None, crisis) if crisis else _pair(None, None),
        "sensitive_recall": _per_trial(
            m.get("sensitive_recall"), m.get("sensitive_recall_by_trial")
        ),
        "ordinary_no_offer": _per_trial(
            m.get("ordinary_no_offer"), m.get("ordinary_no_offer_by_trial")
        ),
    }
    failures = _unique([miss.get("item") for miss in document.get("misses") or []])
    return facts, metrics, failures


def _case_summary_board(
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    models = document.get("models") or {}
    facts = _facts(
        document,
        model=models.get("summary"),
        trials=document.get("trials"),
        live=document.get("mode") == "live",
    )
    facts.update(
        promptVersion=document.get("summary_prompt"),
        judgeVersion=document.get("judge_version"),
        datasetSha256=_dataset_hashes(document),
    )
    judge_misses: dict[int, set[str]] = {}
    for miss in document.get("judge_not_passed") or []:
        judge_misses.setdefault(miss["trial"], set()).add(miss["item"])
    program: list[float] = []
    judge: list[float] = []
    items_per_trial = 0
    judged_per_trial = 0
    not_judged_per_trial = 0
    for row in document.get("by_trial") or []:
        items = row["items"]
        if not items:
            continue
        items_per_trial = max(items_per_trial, items)
        program.append(row["program_passed"] / items)
        judged = row.get("judged", 0)
        not_judged_per_trial = max(not_judged_per_trial, items - judged)
        if not judged:
            continue
        # Out of the judged summaries: one the judge never saw is not a judge failure.
        judged_per_trial = max(judged_per_trial, judged)
        passed = judged - len(judge_misses.get(row["trial"], ()))
        judge.append(max(passed, 0) / judged)
    metrics: dict[str, Any] = {}
    if program:
        metrics["passed_every_check"] = _pair(
            sum(program) / len(program), min(program), itemsPerTrial=items_per_trial
        )
    if judge:
        metrics["passed_by_judge"] = _pair(
            sum(judge) / len(judge),
            min(judge),
            itemsPerTrial=judged_per_trial,
            notJudgedPerTrial=not_judged_per_trial,
        )
    failures = _unique(
        [f.get("item") for f in document.get("failures") or []]
        + [f.get("item") for f in document.get("judge_not_passed") or []]
    )
    return facts, metrics, failures


def _retrieval_board(
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    facts = _facts(document, model=document.get("model"), trials=1, live=True)
    facts.update(
        datasetSha256=(
            {RETRIEVAL_DATASET_NAME: document["datasetSha256"]}
            if document.get("datasetSha256")
            else None
        ),
        handbookVersion=document.get("handbookVersion"),
    )
    overall = document.get("overall") or {}
    hit_rate = overall.get("hitRateAt5")
    negatives = document.get("negatives") or []
    metrics: dict[str, Any] = {"hit_rate_at_5": _pair(hit_rate, hit_rate)}
    if negatives:
        share = sum(1 for n in negatives if n.get("passed")) / len(negatives)
        metrics["negatives_passing"] = _pair(share, share)
    mrr = overall.get("meanReciprocalRank")
    if mrr is not None:
        metrics["mean_reciprocal_rank"] = _pair(mrr, mrr)
    failures = _unique(
        [miss.get("id") for miss in document.get("misses") or []]
        + [n.get("id") for n in negatives if not n.get("passed")]
    )
    return facts, metrics, failures


def set_of(document: Mapping[str, Any]) -> str:
    if "overall" in document and "hitRateAt5" in (document["overall"] or {}):
        return "retrieval"
    return str(document.get("set", "unknown"))


def board_of(document: Mapping[str, Any], *, stamp: str) -> dict[str, Any]:
    """The board of one run file, in the one schema every set shares:

        {"schema": 1, "set": "full", "stamp": "20261029T142328Z",
         "facts": {"model", "models", "effort", "promptVersion", "toolsetVersion",
                   "guardPromptVersion", "judgeVersion", "datasetSha256", "commit", "trials",
                   "date", "live", "partial", ...},
         "metrics": {"<name>": {"mean": 0.97, "min": 0.96}, ...},
         "failures": ["qa-23", ...],
         "costUsd": {"total": "10.93", "cap": "16.00"} or null}

    `facts.model` is the model the set is about: the assistant for the assistant sets, the guard
    for escalation, the summarizer for case summary, the embedding model for retrieval.
    """
    name = set_of(document)
    adapter = {
        "retrieval": _retrieval_board,
        "escalation": _escalation_board,
        "case-summary": _case_summary_board,
    }.get(name, _assistant_board)
    facts, metrics, failures = adapter(document)
    return {
        "schema": SCHEMA,
        "set": name,
        "stamp": stamp,
        "facts": facts,
        "metrics": metrics,
        "failures": failures,
        "costUsd": None if name == "retrieval" else _money(document),
    }


# --- Writing ----------------------------------------------------------------------------------


def dumps(board: Mapping[str, Any]) -> str:
    return json.dumps(board, indent=2) + "\n"


def skip_reason(run_file: Path, document: Mapping[str, Any]) -> str | None:
    """Why this run gets no board, or None when it does."""
    if stamp_of(run_file) is None:
        return f"the run file's name ({run_file.name}) does not start with a stamp"
    if document.get("mode") != "live":
        return "a replay is not boarded"
    if document.get("set") == "smoke":
        return "a smoke run is for trying wording"
    if document.get("scored_half") == "tuning":
        return "the run scored the tuning half, not the held-out half"
    return None


def write_boards(
    run_file: Path | None,
    document: Mapping[str, Any],
    boards_dir: Path = SCOREBOARDS_DIR,
    *,
    beside: bool = True,
    stamp: str | None = None,
) -> Path | None:
    """Write a live run's board to `boards_dir/<run file stem>.json`, and, with `beside`, a copy
    named `<stem>-board.json` next to the run file. Returns the committed path, or None when the
    run gets no board (see `skip_reason`): a smoke run (it is for trying wording), a replay, or a
    run file whose name carries no stamp (nothing to name the board by). The backfill and the live
    runners both come through here, so a board is named and built the same way either way.

    A run with no run file (the retrieval eval) passes `run_file=None` and its own `stamp`; the
    board is then named `<stamp>-<set>.json`, with no copy beside anything."""
    if run_file is None:
        if stamp is None:
            raise ValueError("a run with no run file needs a stamp")
        stem = f"{stamp}-{set_of(document)}"
        beside = False
    else:
        reason = skip_reason(run_file, document)
        if reason is not None:
            return None
        stamp = stamp_of(run_file)
        stem = run_file.stem
    assert stamp is not None  # noqa: S101 (skip_reason checked it)
    text = dumps(board_of(document, stamp=stamp))
    boards_dir.mkdir(parents=True, exist_ok=True)
    target = boards_dir / f"{stem}.json"
    target.write_text(text, encoding="utf-8")
    if beside and run_file is not None:
        run_file.parent.mkdir(parents=True, exist_ok=True)
        run_file.with_name(f"{run_file.stem}{BOARD_SUFFIX}.json").write_text(text, encoding="utf-8")
    return target
