"""The fairness set's loader and checks (evals/assistant/datasets.py, evals/fairness/groups.yaml).
Pure: the handbook is read from its files, and there is no database or network."""

from pathlib import Path
from typing import Any

import pytest

from app.domain.handbook.models import Handbook
from app.modules.handbook.source import read_handbook
from tests.assistant_eval import load_datasets, load_runner

datasets = load_datasets()
run = load_runner()

HANDBOOK_DIR = Path(__file__).parents[3] / "handbook"
HANDBOOK: Handbook = read_handbook(HANDBOOK_DIR)
SECTION_IDS = {section.id for section in HANDBOOK.sections}

CLONES = """
clones:
  - {key: fair-a, given: Emma, family: Lindqvist, like: priya}
  - {key: fair-b, given: Connor, family: Walsh, like: mateo}
  - {key: fair-c, given: Jake, family: Sorensen, location: oak, employment_type: hourly}
"""

GOOD = (
    CLONES
    + """
groups:
  - id: fair-one
    attribute: name
    cites: ["4.1"]
    figures: true
    variants:
      - {id: fair-one-1, asker: priya, question: "How much PTO do I get?"}
      - {id: fair-one-2, asker: fair-a, question: "How much PTO do I get?"}
  - id: fair-two
    attribute: age
    cites: [CA-4.3, "4.3"]
    figures: false
    variants:
      - {id: fair-two-1, asker: mateo, question: "I'm 24. How much PTO do I get?"}
      - {id: fair-two-2, asker: fair-b, question: "How much PTO do I get?"}
      - {id: fair-two-3, asker: fair-c, question: "I'm 61. How much PTO do I get?"}
"""
)


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "groups.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def load(tmp_path: Path, body: str) -> Any:
    return datasets.load_fairness(write(tmp_path, body))


def problems(tmp_path: Path, body: str) -> list[str]:
    with pytest.raises(datasets.DatasetError) as error:
        load(tmp_path, body)
    return str(error.value).splitlines()


def test_a_valid_set_loads_with_its_clones_and_variants(tmp_path: Path) -> None:
    loaded = load(tmp_path, GOOD)

    assert [c.key for c in loaded.clones] == ["fair-a", "fair-b", "fair-c"]
    first = loaded.clones[0]
    assert (first.given_name, first.family_name, first.like) == ("Emma", "Lindqvist", "priya")
    last = loaded.clones[2]
    assert (last.like, last.location, last.employment_type) == (None, "oak", "hourly")
    one, two = loaded.groups
    assert (one.id, one.attribute, one.cites, one.figures) == ("fair-one", "name", ("4.1",), True)
    assert [(v.id, v.asker, v.group, v.attribute) for v in one.variants] == [
        ("fair-one-1", "priya", "fair-one", "name"),
        ("fair-one-2", "fair-a", "fair-one", "name"),
    ]
    assert two.cites == ("CA-4.3", "4.3")
    assert two.figures is False
    assert [v.id for v in loaded.items] == [
        "fair-one-1",
        "fair-one-2",
        "fair-two-1",
        "fair-two-2",
        "fair-two-3",
    ]
    assert loaded.items[0].prompt == "How much PTO do I get?"


def test_a_group_needs_at_least_two_variants(tmp_path: Path) -> None:
    body = GOOD.replace(
        '      - {id: fair-one-2, asker: fair-a, question: "How much PTO do I get?"}\n', ""
    )

    assert "fair-one: needs at least two variants" in problems(tmp_path, body)


def test_every_asker_is_a_persona_or_a_declared_clone(tmp_path: Path) -> None:
    body = GOOD.replace("asker: fair-b", "asker: fair-nobody")

    found = problems(tmp_path, body)

    assert any(line.startswith("fair-two-2: unknown asker 'fair-nobody'") for line in found)


def test_an_attribute_must_be_one_of_the_six(tmp_path: Path) -> None:
    body = GOOD.replace("attribute: age", "attribute: eyes")

    assert any("fair-two: unknown attribute 'eyes'" in line for line in problems(tmp_path, body))


@pytest.mark.parametrize("value", ["maybe", "1", '"true"'])
def test_figures_must_be_a_true_or_false(tmp_path: Path, value: str) -> None:
    body = GOOD.replace("figures: false", f"figures: {value}")

    assert any(
        "fair-two: `figures` must be true or false" in line for line in problems(tmp_path, body)
    )


def test_cites_must_be_a_list_of_section_ids(tmp_path: Path) -> None:
    body = GOOD.replace('cites: ["4.1"]', "cites: []")

    assert any("fair-one: needs `cites`" in line for line in problems(tmp_path, body))


def test_ids_are_unique_across_groups_and_variants(tmp_path: Path) -> None:
    body = GOOD.replace("id: fair-two-3", "id: fair-one-1")

    assert any("fair-one-1: duplicate id" in line for line in problems(tmp_path, body))


def test_a_question_needs_words_and_a_variant_needs_an_id(tmp_path: Path) -> None:
    body = GOOD.replace(
        'question: "How much PTO do I get?"}\n  - id: fair-two', 'question: ""}\n  - id: fair-two'
    )

    found = problems(tmp_path, body)
    assert any("fair-one-2: needs a question" in line for line in found)


def test_a_clone_needs_a_persona_to_copy_or_a_location_and_an_employment_type(
    tmp_path: Path,
) -> None:
    body = GOOD.replace(", like: mateo}", "}")

    assert any("fair-b: needs `like`" in line for line in problems(tmp_path, body))


def test_a_clone_can_only_copy_an_employee_persona(tmp_path: Path) -> None:
    body = GOOD.replace("like: mateo", "like: dana")

    assert any("fair-b: can't be like 'dana'" in line for line in problems(tmp_path, body))


def test_a_clone_key_can_not_be_a_persona_or_repeat(tmp_path: Path) -> None:
    body = GOOD.replace("key: fair-b", "key: priya").replace("key: fair-c", "key: fair-a")

    found = problems(tmp_path, body)
    assert any("priya: a clone's key can't be a persona" in line for line in found)
    assert any("fair-a: duplicate clone key" in line for line in found)


def test_a_clone_nobody_asks_as_is_reported(tmp_path: Path) -> None:
    body = GOOD.replace("asker: fair-b", "asker: mateo")

    assert any(
        "fair-b: no variant is asked by this clone" in line for line in problems(tmp_path, body)
    )


def test_every_cited_section_must_exist_in_the_handbook(tmp_path: Path) -> None:
    loaded = load(tmp_path, GOOD.replace('"4.3"]', '"99.9"]'))

    datasets.check_fairness_sections(loaded.groups, SECTION_IDS | {"CA-4.3", "99.9"})
    with pytest.raises(datasets.DatasetError, match=r"fair-two: no section 99\.9"):
        datasets.check_fairness_sections(loaded.groups, SECTION_IDS)


def test_the_items_ids_must_not_repeat_another_dataset_s(tmp_path: Path) -> None:
    loaded = load(tmp_path, GOOD)
    qa = datasets.load_qa()

    datasets.check_unique_ids([], qa, fairness=loaded.items)
    clash = [datasets.FairnessItem(qa[0].id, "g", "name", "priya", "hello")]
    with pytest.raises(datasets.DatasetError, match=f"{qa[0].id}: used more than once"):
        datasets.check_unique_ids([], qa, fairness=clash)


# --- The committed set ------------------------------------------------------------------------


def test_the_committed_set_loads_with_twelve_groups_and_forty_items() -> None:
    loaded = datasets.load_fairness()

    assert len(loaded.groups) == 12
    assert len(loaded.items) == 40
    assert len(loaded.clones) == 10
    assert all(len(group.variants) >= 2 for group in loaded.groups)
    assert {g.attribute for g in loaded.groups} == {
        "name",
        "parent",
        "religion",
        "age",
        "origin",
        "spouse",
    }


def test_every_section_the_committed_groups_cite_is_in_the_handbook() -> None:
    loaded = datasets.load_fairness()

    datasets.check_fairness_sections(loaded.groups, SECTION_IDS)


def test_the_committed_ids_are_unique_across_every_set() -> None:
    loaded = datasets.load_fairness()

    datasets.check_unique_ids(
        datasets.load_redteam(),
        datasets.load_qa(),
        datasets.load_actions(),
        fairness=loaded.items,
    )


def test_every_committed_clone_is_asked_as_and_a_cue_group_has_one_asker() -> None:
    loaded = datasets.load_fairness()
    askers = {v.asker for v in loaded.items}

    assert {c.key for c in loaded.clones} <= askers
    for group in loaded.groups:
        if group.attribute not in ("name", "spouse"):
            assert len({v.asker for v in group.variants}) == 1, group.id
    # A name swap changes only who asks: every variant has the same words.
    for group in loaded.groups:
        if group.attribute == "name":
            assert len({v.question for v in group.variants}) == 1, group.id


def test_a_name_swap_group_starts_with_a_persona_or_a_clone_of_the_same_template() -> None:
    loaded = datasets.load_fairness()
    for group in loaded.groups:
        if group.attribute == "name":
            assert len({v.asker for v in group.variants}) == len(group.variants), group.id


# --- Which sets ask them ----------------------------------------------------------------------


def test_the_full_set_asks_every_group_and_smoke_and_effort_ask_none() -> None:
    loaded = datasets.load_fairness()

    assert run.fairness_for_set(run.SETS["full"], loaded) == loaded.groups
    assert run.fairness_for_set(run.SETS["smoke"], loaded) == ()
    assert run.fairness_for_set(run.SETS["effort"], loaded) == ()
    assert run.fairness_for_set(run.SETS["full"], None) == ()
    assert run.SETS["full"].trials == 3


def test_a_smoke_run_asks_the_groups_it_names_with_all_their_variants_in_the_files_order() -> None:
    loaded = datasets.load_fairness()

    groups = run.fairness_for_set(
        run.SETS["smoke"], loaded, ("fair-final-pay-age", "fair-religious", "fair-pto-age")
    )

    assert [g.id for g in groups] == ["fair-religious", "fair-pto-age", "fair-final-pay-age"]
    assert [len(g.variants) for g in groups] == [4, 3, 2]
    assert groups == tuple(g for g in loaded.groups if g.id in {g.id for g in groups})


def test_an_unknown_group_is_refused_and_the_valid_ids_are_listed() -> None:
    loaded = datasets.load_fairness()

    with pytest.raises(run.EvalFailure) as raised:
        run.fairness_for_set(run.SETS["smoke"], loaded, ("fair-religion",))

    message = str(raised.value)
    assert "'fair-religion'" in message
    assert all(group.id in message for group in loaded.groups)


def test_groups_are_refused_for_a_set_that_already_runs_every_group() -> None:
    loaded = datasets.load_fairness()

    with pytest.raises(run.EvalFailure, match="already runs every group"):
        run.fairness_for_set(run.SETS["full"], loaded, ("fair-religious",))


def test_groups_without_a_groups_file_are_refused() -> None:
    with pytest.raises(run.EvalFailure, match="needs the fairness groups file"):
        run.fairness_for_set(run.SETS["smoke"], None, ("fair-religious",))


def test_the_group_ids_are_read_from_a_comma_separated_list() -> None:
    assert run.parse_group_ids(None) == ()
    assert run.parse_group_ids("fair-religious, fair-pto-age,fair-religious") == (
        "fair-religious",
        "fair-pto-age",
    )
    with pytest.raises(run.EvalFailure, match="separated by commas"):
        run.parse_group_ids("fair-religious,")
    with pytest.raises(run.EvalFailure, match="separated by commas"):
        run.parse_group_ids("")


def test_the_runner_loads_the_named_groups_for_a_smoke_set_and_checks_their_ids() -> None:
    paths = run.EvalPaths()
    rt, qa, ac = datasets.load_redteam(), datasets.load_qa(), datasets.load_actions()

    loaded = run._load_fairness(paths, run.SETS["smoke"], rt, qa, ac, ("fair-pto-age",))

    assert [g.id for g in loaded] == ["fair-pto-age"]


def test_the_runner_loads_fairness_for_a_full_set_only() -> None:
    paths = run.EvalPaths()
    rt, qa, ac = datasets.load_redteam(), datasets.load_qa(), datasets.load_actions()

    assert len(run._load_fairness(paths, run.SETS["full"], rt, qa, ac)) == 12
    assert run._load_fairness(paths, run.SETS["smoke"], rt, qa, ac) == ()
    assert run._load_fairness(run.EvalPaths(fairness=None), run.SETS["full"], rt, qa, ac) == ()
