"""Re-grade a finished run's fairness results from its saved traces, without a model call.

The fairness graders (evals/fairness/graders.py) compare the variants of a group, and they can
change after a paid run recorded its traces. This module puts the new fairness results into the
old run file: the fairness metrics, the fairness section, the fairness lines of the failure list,
and the fairness items' grades. Everything else in the run file (the other sets' results, the
costs, the commit, the date) stays as it was, and the run file says it was re-graded and with
which grader files (`fairness_regraded`).

Pure: records in, a run file's data out. run.py builds the records from the saved traces and the
recorded pairwise verdicts (`regrade_fairness_command`).
"""

from collections.abc import Mapping, Sequence
from typing import Any

from assistant import scoreboard

RUN_KEY = "fairness_regraded"


def regraded_document(
    run: Mapping[str, Any],
    records: Sequence[scoreboard.ItemRecord],
    *,
    today: str,
    sha256: Mapping[str, str],
) -> dict[str, Any]:
    """The run file with its fairness results replaced by those of `records` (the fairness items,
    graded again). `today` is a date and `sha256` the hash of each fairness grader file used."""
    document = dict(run)
    fresh = scoreboard.fairness_metrics(records)
    metrics = {k: v for k, v in run["metrics"].items() if not k.startswith("fairness_")}
    metrics.update(fresh)
    document["metrics"] = metrics
    document["fairness"] = scoreboard.fairness_section(records)
    # A variant whose group did not run in full is not in `records`: its failures and its grade
    # stay as the run file had them.
    regraded = {(r.trial, r.item_id) for r in records}
    document["failures"] = [
        f
        for f in run["failures"]
        if f.get("dataset") != "fairness" or (f["trial"], f["item"]) not in regraded
    ] + scoreboard.failures_of(records)
    passed = {(r.trial, r.item_id): r.grade.passed for r in records}
    document["items"] = [
        {**item, "deterministic_passed": passed[(item["trial"], item["item"])]}
        if item["dataset"] == "fairness" and (item["trial"], item["item"]) in passed
        else item
        for item in run["items"]
    ]
    document[RUN_KEY] = {"date": today, "sha256": dict(sha256)}
    return document
