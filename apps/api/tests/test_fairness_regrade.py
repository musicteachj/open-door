"""Grading a finished run's fairness results again from its saved traces
(`run.py --regrade-fairness`): free, replay only, and nothing else in the run changes."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.ai.pricing import Usage
from app.ai.replay import FixtureStore, Record, fingerprint
from tests.assistant_eval import (
    load_boards,
    load_datasets,
    load_eval_module,
    load_evals_script,
    load_fairness_module,
    load_graders,
    load_pairwise,
    load_runner,
    load_scoreboard,
)

run = load_runner()
boards = load_boards()
scoreboard = load_scoreboard()
pairwise = load_pairwise()
datasets = load_datasets()
graders = load_graders()
regrade = load_eval_module("regrade.py")
fairness_graders = load_fairness_module("graders")

GROUP = "fair-sick-oakland"
STAMP = "20261103T140018Z"
SEARCH = "/handbook/CA-4.3 | CA-4.3 Sick leave | You receive at least 40 hours of sick leave."
CITED = (
    {
        "sectionId": "CA-4.3",
        "marker": 1,
        "offsetUtf16": 20,
        "citedText": "40 hours of sick leave",
        "title": "Sick",
    },
)


def fairness() -> Any:
    return datasets.load_fairness()


def variant_of(item_id: str) -> Any:
    return next(v for g in fairness().groups for v in g.variants if v.id == item_id)


def trace_dict(item_id: str, trial: int, answer: str, **overrides: Any) -> dict[str, Any]:
    variant = variant_of(item_id)
    trace: dict[str, Any] = scoreboard.trace_json(
        run.ItemTrace(
            item_id=item_id,
            persona=variant.asker,
            question=variant.question,
            person_id=uuid4(),
            answer_text=answer,
            citations=CITED,
            tool_uses=(run.ToolUse("u1", "search_handbook", {"query": "sick"}),),
            tool_results=(
                run.ToolResult("u1", False, SEARCH, (run.SearchResult("/h", "T", ("p",)),)),
            ),
            guard=run.GuardVerdict("ordinary", None, False),
            main_model_called=True,
            model_call_count=1,
            escalations=(),
            error_codes=(),
            status_note_count=0,
            status_notes=(),
            retracted_texts=(),
            usage=(),
            turn_status="completed",
            turn_error_code=None,
            cost_usd=Decimal("0.01"),
        )
    )
    trace.update(trial=trial, dataset="fairness", group=GROUP, qa_kind=None)
    trace.update(overrides)
    return trace


def spread(value: float) -> dict[str, Any]:
    return {"mean": value, "min": value, "max": value, "spread": 0.0, "trials": 1}


def ids() -> list[str]:
    return [
        v.id for v in fairness().groups[[g.id for g in fairness().groups].index(GROUP)].variants
    ]


def make_files(
    tmp_path: Path, answers: dict[str, str], *, record_verdicts: bool = True
) -> tuple[Path, Path, Path]:
    """A run file, its traces, and the pairwise recordings for one trial of one group. The run
    file carries a stale result: the group splits, and an unrelated Q&A figure that must stay."""
    traces = [
        trace_dict(i, 1, answers.get(i, "You get 40 hours of sick leave a year.")) for i in ids()
    ]
    run_doc = {
        "mode": "live",
        "set": "full",
        "trials": 1,
        "date": "2026-11-03T14:00:18+00:00",
        "commit": "abc",
        "cost_usd": {"total": "9.99"},
        "metrics": {
            "qa_deterministic_pass_rate": {"mean": 0.97},
            "fairness_groups_consistent": {**spread(0.0), "groups": 1},
            "fairness_consistent_by_group": {"name": spread(0.0)},
            "fairness_identity_assumptions": spread(0.0),
            "fairness_judge_equivalence": spread(0.5),
            "fairness_equivalence_by_group": {"name": spread(1.0)},
            "fairness_judge_unavailable": spread(0.0),
        },
        "failures": [
            {"trial": 1, "dataset": "qa", "item": "qa-1", "failed": ["x"], "reasons": {}},
            {
                "trial": 1,
                "dataset": "fairness",
                "item": ids()[1],
                "group": GROUP,
                "failed": ["same-figures"],
                "reasons": {"same-figures": ["old"]},
            },
        ],
        "fairness": {
            "groups": [
                {
                    "group": GROUP,
                    "attribute": "name",
                    "trials_graded": 1,
                    "trials_differing": 1,
                    "split": True,
                }
            ],
            "pairs": [],
        },
        "items": [
            {"trial": 1, "item": "qa-1", "dataset": "qa", "deterministic_passed": False},
            *[
                {
                    "trial": 1,
                    "item": i,
                    "dataset": "fairness",
                    "deterministic_passed": i != ids()[1],
                }
                for i in ids()
            ],
        ],
    }
    run_path = tmp_path / f"{STAMP}-full.json"
    run_path.write_text(json.dumps(run_doc), encoding="utf-8")
    saved = {"run": {"date": run_doc["date"], "commit": "abc"}, "traces": traces}
    (tmp_path / f"{STAMP}-full-traces.json").write_text(json.dumps(saved), encoding="utf-8")
    store = FixtureStore(tmp_path / run.PAIRWISE_FIXTURE)
    if record_verdicts:
        record_pairs(store, saved)
    store.save()
    return run_path, tmp_path / f"{STAMP}-full-traces.json", store.path


def record_pairs(store: Any, saved: dict[str, Any]) -> None:
    """Record a verdict for each comparison, by building the pairs as the command does."""
    by_id = {t["item_id"]: run.trace_from_json(t) for t in saved["traces"]}
    company = run.eval_sandbox.with_eval_clones(
        run.eval_sandbox.with_eval_requests(run.build_company(run.TENANT_ID, run.ANCHOR_DATE)),
        fairness().clones,
    )
    group = next(g for g in fairness().groups if g.id == GROUP)
    system = pairwise.pairwise_system()
    first = pairwise.side_of(
        by_id[group.variants[0].id], asker=run.fairness_asker_line(company, group.variants[0].asker)
    )
    for variant in group.variants[1:]:
        pair = pairwise.PairInput(
            group.id,
            group.attribute,
            first,
            pairwise.side_of(
                by_id[variant.id], asker=run.fairness_asker_line(company, variant.asker)
            ),
        )
        kwargs = pairwise.pairwise_api_kwargs(pair, system=system)
        key = fingerprint("judge", kwargs)
        text = json.dumps(
            {"sameSubstance": True, "identityAssumption": False, "reason": "the same rules"}
        )
        response = run.judge.JudgeResponse(
            "end_turn", text, Usage(10, 5, 0, 0), run.judge.JUDGE_MODEL
        )
        store.put(Record(key, "judge", variant.id, 0, result=response.to_json()))


def regrade_args(run_path: Path, tmp_path: Path) -> list[str]:
    return [
        "--regrade-fairness",
        str(run_path),
        "--fixtures-dir",
        str(tmp_path),
        "--boards-dir",
        str(tmp_path / "boards"),
    ]


async def test_regrading_replaces_only_the_fairness_results(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_path, _, _ = make_files(tmp_path, {})
    before = json.loads(run_path.read_text())

    code = await run.run_cli(regrade_args(run_path, tmp_path), env=run.RunEnv())

    assert code == 0
    after = json.loads(run_path.read_text())
    # What was not fairness is untouched.
    for key in ("mode", "set", "trials", "date", "commit", "cost_usd"):
        assert after[key] == before[key]
    assert after["metrics"]["qa_deterministic_pass_rate"] == {"mean": 0.97}
    assert [f for f in after["failures"] if f["dataset"] == "qa"] == [before["failures"][0]]
    assert after["items"][0] == before["items"][0]
    # The stale split is gone: every variant answered the same.
    assert [f for f in after["failures"] if f["dataset"] == "fairness"] == []
    assert after["fairness"]["groups"][0]["split"] is False
    assert after["metrics"]["fairness_groups_consistent"]["mean"] == 1.0
    assert all(i["deterministic_passed"] for i in after["items"] if i["dataset"] == "fairness")
    # The verdicts come from the recordings (the stub's stale 50% is replaced).
    assert after["metrics"]["fairness_judge_equivalence"]["mean"] == 1.0
    assert [p["sameSubstance"] for p in after["fairness"]["pairs"]] == [True] * (len(ids()) - 1)
    assert after["fairness_regraded"]["date"]
    assert set(after["fairness_regraded"]["sha256"]) == {"graders.py", "groups.yaml"}
    out = capsys.readouterr().out
    assert "Before:" in out
    assert "After:" in out


async def test_regrading_rewrites_the_board_in_place_with_the_fact(tmp_path: Path) -> None:
    run_path, _, _ = make_files(tmp_path, {})

    await run.run_cli(regrade_args(run_path, tmp_path), env=run.RunEnv())

    board = json.loads((tmp_path / "boards" / f"{STAMP}-full.json").read_text())
    assert board["stamp"] == STAMP
    assert board["facts"]["fairnessRegraded"]["date"]
    assert sorted(p.name for p in (tmp_path / "boards").iterdir()) == [f"{STAMP}-full.json"]
    assert (tmp_path / f"{STAMP}-full-board.json").exists()


async def test_a_missing_pairwise_verdict_stops_the_regrade_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_path, _, _ = make_files(tmp_path, {}, record_verdicts=False)
    before = run_path.read_text()

    code = await run.run_cli(regrade_args(run_path, tmp_path), env=run.RunEnv())

    assert code == 2
    assert run_path.read_text() == before
    assert "pairwise verdicts are in neither" in capsys.readouterr().err
    assert not (tmp_path / "boards").exists()


async def test_a_verdict_not_recorded_is_read_from_the_run_files_own_pairs(
    tmp_path: Path,
) -> None:
    run_path, _, _ = make_files(tmp_path, {}, record_verdicts=False)
    doc = json.loads(run_path.read_text())
    doc["fairness"]["pairs"] = [
        {
            "trial": 1,
            "item": i,
            "group": GROUP,
            "attribute": "name",
            "sameSubstance": False,
            "identityAssumption": True,
            "reason": "from the run",
        }
        for i in ids()[1:]
    ]
    run_path.write_text(json.dumps(doc))

    code = await run.run_cli(regrade_args(run_path, tmp_path), env=run.RunEnv())

    after = json.loads(run_path.read_text())
    assert code == 0
    assert after["metrics"]["fairness_judge_equivalence"]["mean"] == 0.0
    assert after["metrics"]["fairness_identity_assumptions"]["max"] == len(ids()) - 1


async def test_a_traces_file_from_another_run_is_refused(tmp_path: Path) -> None:
    run_path, traces_path, _ = make_files(tmp_path, {})
    saved = json.loads(traces_path.read_text())
    saved["run"]["commit"] = "other"
    traces_path.write_text(json.dumps(saved))

    code = await run.run_cli(regrade_args(run_path, tmp_path), env=run.RunEnv())

    assert code == 2


async def test_a_real_difference_still_splits_the_group(tmp_path: Path) -> None:
    run_path, _, _ = make_files(tmp_path, {ids()[1]: "You get 24 hours of sick leave a year."})

    await run.run_cli(regrade_args(run_path, tmp_path), env=run.RunEnv())

    after = json.loads(run_path.read_text())
    assert after["fairness"]["groups"][0]["split"] is True
    assert any(f["item"] == ids()[1] for f in after["failures"])


def test_an_older_board_has_no_regrade_fact() -> None:
    made = boards.board_of({"set": "full", "mode": "live", "trials": 3}, stamp=STAMP)

    assert made["facts"]["fairnessRegraded"] is None


def test_the_scoreboard_row_says_when_the_fairness_was_graded_again() -> None:
    gen = load_evals_script("scoreboard_gen")
    metrics = {
        "fairness_groups_consistent": {"mean": 1.0, "min": 1.0},
        "fairness_judge_equivalence": {"mean": 0.9, "min": 0.9},
    }
    plain = {"stamp": STAMP, "set": "full", "facts": {}, "metrics": metrics}
    again = {**plain, "facts": {"fairnessRegraded": {"date": "2026-11-04", "sha256": {}}}}

    assert not any("again" in line for line in gen._fairness_row(plain)["also"])
    assert any(
        "again" in line and "2026-11-04" in line for line in gen._fairness_row(again)["also"]
    )


def regrade_with(saved: dict[str, Any], tmp_path: Path) -> Any:
    run_doc: dict[str, Any] = {"date": "d", "commit": "c", "failures": [], "fairness": None}
    saved["run"] = {"date": "d", "commit": "c"}
    return run.regraded_fairness_records(
        run_doc,
        saved,
        fairness(),
        pairwise_store=FixtureStore(tmp_path / run.PAIRWISE_FIXTURE),
        pairwise_system="s",
    )


@pytest.mark.parametrize("field", ["question", "persona"])
def test_a_trace_that_asked_something_else_than_the_groups_file_stops_the_regrade(
    tmp_path: Path, field: str
) -> None:
    traces = [trace_dict(i, 1, "You get 40 hours.") for i in ids()]
    traces[1][field] = "someone else" if field == "persona" else "A different question?"

    with pytest.raises(run.EvalFailure, match=rf"{ids()[1]}.*groups.yaml now has"):
        regrade_with({"traces": traces}, tmp_path)


def test_a_variant_not_regraded_keeps_its_failure_and_its_grade() -> None:
    # A partial run: only the first two variants' group ran in full, so only they are regraded.
    # The others keep what the run file said, a private-data failure included.
    regraded_ids = ids()[:2]
    kept_failing, kept_passing = ids()[2], ids()[3]
    stale = {
        "trial": 1,
        "dataset": "fairness",
        "item": kept_failing,
        "group": "fair-other",
        "failed": ["no-private-data"],
        "reasons": {"no-private-data": ["leaked"]},
    }
    stale_regraded = {**stale, "item": regraded_ids[1], "failed": ["same-figures"]}
    run_doc = {
        "metrics": {},
        "failures": [stale, stale_regraded],
        "items": [
            {
                "trial": 1,
                "item": kept_failing,
                "dataset": "fairness",
                "deterministic_passed": False,
            },
            {"trial": 1, "item": kept_passing, "dataset": "fairness", "deterministic_passed": True},
            {
                "trial": 1,
                "item": regraded_ids[1],
                "dataset": "fairness",
                "deterministic_passed": False,
            },
        ],
        "trials": 1,
    }
    records = [
        scoreboard.ItemRecord(
            1,
            "fairness",
            item_id,
            GROUP,
            None,
            graders.ItemGrade((graders.GradeResult("answer-checks", True),)),
            None,
        )
        for item_id in regraded_ids
    ]

    document = regrade.regraded_document(run_doc, records, today="2026-11-04", sha256={})

    assert document["failures"] == [stale]
    passed = {i["item"]: i["deterministic_passed"] for i in document["items"]}
    assert passed == {kept_failing: False, kept_passing: True, regraded_ids[1]: True}
    assert scoreboard.fairness_problems(document) == [
        f"fairness: {kept_failing} failed no-private-data"
    ]
