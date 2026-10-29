"""The seeded cases' summaries (Task 28): the plumbing that puts trial 1's real summaries in.

Until the case-summary run has written them, each seeded case carries the placeholder. Once a
summary is recorded in `SEEDED_SUMMARIES`, it must pass the very checks every live summary passes,
against its own case's words, and name the model and the prompt version that wrote it.
"""

import json
from pathlib import Path

import pytest

from app.ai.case_summary import summary_problem
from app.modules.sandbox import seed_data
from app.modules.sandbox.seed import build_company
from app.modules.sandbox.seed_data import (
    CASES,
    SEEDED_SUMMARIES,
    SEEDED_SUMMARY_MODEL,
    SEEDED_SUMMARY_PLACEHOLDER,
    SEEDED_SUMMARY_PROMPT_VERSION,
)
from scripts import apply_seeded_summaries as apply
from tests.test_seed import ANCHOR, TENANT_ID

SOURCE = Path(seed_data.__file__)
CASE_TEXT = {case.key: case.text for case in CASES}

EM_DASH = chr(0x2014)


def test_every_recorded_seeded_summary_passes_the_live_checks_against_its_words() -> None:
    for key, summary in SEEDED_SUMMARIES.items():
        assert key in CASE_TEXT
        assert summary_problem(summary.text, CASE_TEXT[key]) is None, key
        assert summary.model not in {SEEDED_SUMMARY_MODEL, ""}
        assert summary.prompt_version not in {SEEDED_SUMMARY_PROMPT_VERSION, ""}
        assert summary.text != SEEDED_SUMMARY_PLACEHOLDER


def test_a_case_without_a_recorded_summary_keeps_the_placeholder() -> None:
    company = build_company(TENANT_ID, ANCHOR)

    for row, spec in zip(company.cases, CASES, strict=True):
        recorded = SEEDED_SUMMARIES.get(spec.key)
        if recorded is None:
            assert row.summary_text == SEEDED_SUMMARY_PLACEHOLDER
            assert row.summary_model == SEEDED_SUMMARY_MODEL
        else:
            assert row.summary_text == recorded.text
            assert (row.summary_model, row.summary_prompt_version) == (
                recorded.model,
                recorded.prompt_version,
            )


def write_run(path: Path, summaries: dict[str, dict[str, str]]) -> Path:
    path.write_text(json.dumps({"run": {}, "summaries": summaries}), encoding="utf-8")
    return path


GOOD = {
    "keisha-zhang": {
        "text": "The person says their last two paychecks were each about four hours short.",
        "model": "claude-opus-5-5",
        "promptVersion": "2026-11.1",
    },
    "chloe-foster": {
        "text": "The person says a regional visitor keeps commenting on their accent.",
        "model": "claude-opus-5-5",
        "promptVersion": "2026-11.1",
    },
}


def test_the_script_renders_the_summaries_as_a_block_the_seed_can_hold(tmp_path: Path) -> None:
    block = apply.render_block(apply.read_run(write_run(tmp_path / "run.json", GOOD)))

    namespace: dict[str, object] = {}
    exec(  # noqa: S102
        "from collections.abc import Mapping\n"
        "from app.modules.sandbox.seed_data import SeededSummary\n" + block,
        namespace,
    )
    recorded = namespace["SEEDED_SUMMARIES"]
    assert isinstance(recorded, dict)
    assert recorded["chloe-foster"] == seed_data.SeededSummary(
        GOOD["chloe-foster"]["text"], "claude-opus-5-5", "2026-11.1"
    )
    assert EM_DASH not in block


def test_the_script_rewrites_only_the_marked_block(tmp_path: Path) -> None:
    source = SOURCE.read_text(encoding="utf-8")
    copy = tmp_path / "seed_data.py"
    copy.write_text(source, encoding="utf-8")

    changed = apply.apply(write_run(tmp_path / "run.json", GOOD), copy)

    assert changed is True
    after = copy.read_text(encoding="utf-8")
    assert after.replace(apply.render_block(apply.read_run(tmp_path / "run.json")), "") != after
    head, _, rest = source.partition(apply.BEGIN)
    _, _, tail = rest.partition(apply.END)
    assert after.startswith(head)
    assert after.endswith(tail)


def test_the_script_refuses_a_summary_that_fails_the_checks(tmp_path: Path) -> None:
    bad = {"keisha-zhang": {**GOOD["keisha-zhang"], "text": "HR should investigate this."}}

    with pytest.raises(apply.ApplyError, match="keisha-zhang"):
        apply.read_run(write_run(tmp_path / "run.json", bad))


@pytest.mark.parametrize(
    "bad",
    [
        {"nobody": GOOD["keisha-zhang"]},
        {"keisha-zhang": {**GOOD["keisha-zhang"], "model": "seeded-placeholder"}},
        {"keisha-zhang": {**GOOD["keisha-zhang"], "promptVersion": ""}},
        {"keisha-zhang": {"text": "x"}},
    ],
)
def test_the_script_refuses_an_unknown_case_a_placeholder_model_or_a_missing_field(
    tmp_path: Path, bad: dict[str, dict[str, str]]
) -> None:
    with pytest.raises(apply.ApplyError):
        apply.read_run(write_run(tmp_path / "run.json", bad))


def test_the_script_names_the_block_by_its_markers_and_the_source_has_them_once() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert source.count(apply.BEGIN) == 1
    assert source.count(apply.END) == 1


@pytest.mark.parametrize(
    "text",
    [
        " leading space",
        "trailing space ",
        "two  spaces inside",
        "plain words " * 20,
        "x" * 200,
        "",
    ],
)
def test_the_pieces_join_back_to_exactly_the_text(text: str) -> None:
    assert "".join(apply._pieces(text)) == text
