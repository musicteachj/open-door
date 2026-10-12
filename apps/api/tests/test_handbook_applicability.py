"""Who a handbook section applies to, and how an audience reads in plain words."""

from itertools import product
from pathlib import Path

import pytest

from app.domain.handbook.applicability import Asker, applies, audience_label
from app.domain.handbook.models import Audience, Handbook
from app.modules.handbook.source import read_handbook
from app.modules.sandbox.seed_data import LOCATIONS, ORG

REAL_HANDBOOK = Path(__file__).parents[3] / "handbook"
LOCATION_NAMES = {"den": "Denver HQ", "oak": "Oakland store", "aus": "Austin warehouse"}

OAKLAND_HOURLY = Asker("CA", "hourly", "oak")


# applies


@pytest.mark.parametrize(
    ("restrict_states", "restrict_types", "restrict_locations"),
    list(product([False, True], repeat=3)),
)
def test_each_list_is_empty_or_must_contain_the_askers_value(
    restrict_states: bool, restrict_types: bool, restrict_locations: bool
) -> None:
    asker = Asker("CA", "hourly", "oak")
    # For each list: a value that matches the asker, and one that doesn't.
    states = [("CA",), ("CO",)] if restrict_states else [()]
    types = [("hourly",), ("salaried",)] if restrict_types else [()]
    locations = [("oak",), ("den",)] if restrict_locations else [()]

    for index, (s, t, loc) in enumerate(product(states, types, locations)):
        audience = Audience(s, t, loc)
        # The first combination (index 0) uses the matching value for every restricted list.
        assert applies(audience, asker) is (index == 0)


def test_an_empty_audience_applies_to_everyone() -> None:
    assert applies(Audience(), Asker("TX", "salaried", "aus"))


def test_a_list_may_name_several_values() -> None:
    audience = Audience(states=("CA", "CO"))

    assert applies(audience, Asker("CO", "hourly", "den"))
    assert not applies(audience, Asker("TX", "hourly", "aus"))


def test_an_asker_is_immutable() -> None:
    with pytest.raises(AttributeError):
        OAKLAND_HOURLY.state = "TX"  # type: ignore[misc]


# audience_label


@pytest.mark.parametrize(
    ("audience", "label"),
    [
        (Audience(), "Everyone"),
        (Audience(states=("CA",)), "California employees"),
        (Audience(employment_types=("hourly",)), "Hourly staff"),
        (Audience(states=("CA",), employment_types=("hourly",)), "Hourly staff in California"),
        (Audience(locations=("den",)), "Denver HQ"),
        (Audience(employment_types=("salaried",)), "Salaried staff"),
        (Audience(states=("CA", "TX")), "California and Texas employees"),
        (Audience(states=("CA", "CO", "TX")), "California, Colorado, and Texas employees"),
        (Audience(locations=("den", "oak")), "Denver HQ and Oakland store"),
        (
            Audience(employment_types=("hourly",), locations=("oak",)),
            "Hourly staff at Oakland store",
        ),
        (Audience(states=("CO",), locations=("den",)), "Colorado employees at Denver HQ"),
        (
            Audience(states=("TX",), employment_types=("salaried",), locations=("aus",)),
            "Salaried staff in Texas at Austin warehouse",
        ),
    ],
)
def test_audience_labels(audience: Audience, label: str) -> None:
    assert audience_label(audience, LOCATION_NAMES) == label


def test_a_state_or_location_without_a_known_name_falls_back_to_its_code() -> None:
    assert audience_label(Audience(states=("NY",)), {}) == "NY employees"
    assert audience_label(Audience(locations=("nyc",)), {}) == "nyc"


# The real handbook, for every seed persona. Stage 3's SQL filter must agree with these.


@pytest.fixture(scope="module")
def handbook() -> Handbook:
    return read_handbook(REAL_HANDBOOK)


def seed_askers() -> dict[str, Asker]:
    """Each persona as the handbook sees them, from the seed's own org chart."""
    state_of = {spec.code: spec.state for spec in LOCATIONS}
    askers = {}
    for (_department, location), positions in ORG.items():
        for position in positions:
            if position.person and position.person.persona_key:
                askers[position.person.persona_key] = Asker(
                    state_of[location], position.employment_type, location
                )
    return askers


def visible(handbook: Handbook, asker: Asker) -> set[str]:
    return {s.id for s in handbook.sections if applies(s.audience, asker)}


def test_the_seed_personas_are_the_ones_the_tests_expect() -> None:
    assert seed_askers() == {
        "dana": Asker("CO", "salaried", "den"),
        "marcus": Asker("CA", "salaried", "oak"),
        "priya": Asker("CA", "salaried", "oak"),
        "mateo": Asker("TX", "hourly", "aus"),
    }


def test_the_handbooks_locations_and_states_match_the_seed(handbook: Handbook) -> None:
    assert dict(handbook.locations) == {spec.code: spec.name for spec in LOCATIONS}
    assert set(handbook.addenda) == {spec.state for spec in LOCATIONS}


def test_a_california_hourly_employee_sees_the_california_addendum_and_not_colorados(
    handbook: Handbook,
) -> None:
    ids = visible(handbook, OAKLAND_HOURLY)

    assert "CA-4.3" in ids
    assert "CO-4.3" not in ids
    assert "4.3" in ids


def test_a_texan_sees_no_california_or_colorado_addenda(handbook: Handbook) -> None:
    ids = visible(handbook, seed_askers()["mateo"])

    assert not {i for i in ids if i.startswith(("CA-", "CO-"))}
    assert {"TX-3.4", "TX-4.5"} <= ids


def test_a_coloradan_sees_only_colorados_addenda(handbook: Handbook) -> None:
    ids = visible(handbook, seed_askers()["dana"])

    assert {i for i in ids if "-" in i} == {i for i in ids if i.startswith("CO-")}
    assert "CO-4.3" in ids


def test_every_persona_sees_every_company_section_that_has_no_restriction(
    handbook: Handbook,
) -> None:
    unrestricted = {
        s.id for s in handbook.sections if s.audience == Audience() and s.kind == "company"
    }

    for asker in seed_askers().values():
        assert unrestricted <= visible(handbook, asker)


# Read by hand from each file's front matter, not computed with `applies`: the only restrictions
# in the handbook are the hourly-only 3.2 and 3.3 and their state addenda, and each addendum's own
# state.
SALARIED_COMPANY = {
    "1.1", "1.2", "2.1", "2.2", "2.3", "2.4", "3.1", "3.4", "4.1", "4.2", "4.3", "4.4", "4.5",
    "5.1", "5.2", "5.3", "6.1", "6.2", "7.1", "7.2",
}  # fmt: skip
HOURLY_COMPANY = SALARIED_COMPANY | {"3.2", "3.3"}
CA_SALARIED = {"CA-3.4", "CA-4.3", "CA-5.1"}
CA_HOURLY = CA_SALARIED | {"CA-3.2", "CA-3.3"}
CO_SALARIED = {"CO-3.4", "CO-4.3", "CO-5.1"}
TX_ALL = {"TX-3.4", "TX-4.5"}

EXPECTED_SECTIONS = {
    "dana": SALARIED_COMPANY | CO_SALARIED,
    "marcus": SALARIED_COMPANY | CA_SALARIED,
    "priya": SALARIED_COMPANY | CA_SALARIED,
    "mateo": HOURLY_COMPANY | TX_ALL,
}


@pytest.mark.parametrize("persona", sorted(EXPECTED_SECTIONS))
def test_each_seed_persona_sees_exactly_these_sections(handbook: Handbook, persona: str) -> None:
    assert visible(handbook, seed_askers()[persona]) == EXPECTED_SECTIONS[persona]


def test_a_california_hourly_employee_sees_exactly_these_sections(handbook: Handbook) -> None:
    assert visible(handbook, OAKLAND_HOURLY) == HOURLY_COMPANY | CA_HOURLY


def test_the_reference_sets_cover_every_section_in_the_handbook(handbook: Handbook) -> None:
    everything = {s.id for s in handbook.sections}

    assert everything == HOURLY_COMPANY | CA_HOURLY | CO_SALARIED | {"CO-3.2", "CO-3.3"} | TX_ALL
