"""The seed company, built in memory: the same fictional company in every sandbox."""

import re
from collections import Counter
from dataclasses import fields
from datetime import date, timedelta
from uuid import UUID

import pytest

# Importing the models puts every table on Base.metadata.
from app.db import models  # noqa: F401
from app.db.base import Base
from app.domain.holidays import holidays_for
from app.modules.sandbox.seed import ROW_TYPES, PersonRow, Row, SeedCompany, build_company

TENANT_ID = UUID("0b6f3f9e-5d0c-4c1e-9a43-6b1f0d3c2a71")
OTHER_TENANT_ID = UUID("d2a4c6e8-1f3b-4d5a-8c7e-9b0a1c2d3e4f")
ANCHOR = date(2026, 10, 5)

# Phones in 555-0100 to 555-0199 are reserved for fiction, so none of them can ring a real person.
FICTIONAL_PHONE = re.compile(r"[0-9]{3}-555-01[0-9]{2}")
WORK_EMAIL = re.compile(r"[a-z]+\.[a-z]+@juniperrow\.example")


@pytest.fixture(scope="module")
def company() -> SeedCompany:
    return build_company(TENANT_ID, ANCHOR)


def full_name(person: PersonRow) -> str:
    return f"{person.given_name} {person.family_name}"


def named(company: SeedCompany, name: str) -> PersonRow:
    return next(person for person in company.people if full_name(person) == name)


def location_code(company: SeedCompany, person: PersonRow) -> str:
    return next(row.code for row in company.locations if row.id == person.location_id)


def reports_of(company: SeedCompany, manager: PersonRow) -> set[str]:
    return {full_name(person) for person in company.people if person.manager_id == manager.id}


def all_reports_of(company: SeedCompany, manager: PersonRow) -> set[str]:
    """Direct and indirect reports, as the recursive query on manager_id will find them."""
    found: set[UUID] = set()
    level = {manager.id}
    while level:
        level = {person.id for person in company.people if person.manager_id in level} - found
        found |= level
    return {full_name(person) for person in company.people if person.id in found}


def years_between(earlier: date, later: date) -> int:
    return later.year - earlier.year - ((later.month, later.day) < (earlier.month, earlier.day))


def all_ids(company: SeedCompany) -> set[UUID]:
    return (
        {row.id for row in company.locations}
        | {row.id for row in company.departments}
        | {row.id for row in company.people}
        | {row.id for row in company.holidays}
    )


def test_every_row_gets_an_id_of_its_own(company: SeedCompany) -> None:
    # all_ids() returns a set, so a repeated ID would quietly shrink it. Two seats sharing a key
    # would give two people one ID, which only the database would otherwise catch.
    rows = len(company.locations) + len(company.departments) + len(company.people)
    assert len(all_ids(company)) == rows + len(company.holidays)


def test_the_same_tenant_and_anchor_date_build_an_equal_company(company: SeedCompany) -> None:
    assert build_company(TENANT_ID, ANCHOR) == company


def test_another_tenant_gets_the_same_people_under_new_ids(company: SeedCompany) -> None:
    other = build_company(OTHER_TENANT_ID, ANCHOR)

    def directory(seeded: SeedCompany) -> list[tuple[str, str, str]]:
        return [(full_name(person), person.title, person.work_email) for person in seeded.people]

    assert directory(other) == directory(company)
    assert all_ids(other).isdisjoint(all_ids(company))
    assert {person.tenant_id for person in other.people} == {OTHER_TENANT_ID}


def test_120_people_40_in_denver_45_in_oakland_and_35_in_austin(company: SeedCompany) -> None:
    head_count = Counter(location_code(company, person) for person in company.people)

    assert head_count == {"den": 40, "oak": 45, "aus": 35}
    assert len(company.person_private) == 120


def test_eight_departments_and_three_locations_each_with_people(company: SeedCompany) -> None:
    assert len(company.departments) == 8
    assert {row.id for row in company.departments} == {p.department_id for p in company.people}
    assert [(row.code, row.state, row.timezone) for row in company.locations] == [
        ("den", "CO", "America/Denver"),
        ("oak", "CA", "America/Los_Angeles"),
        ("aus", "TX", "America/Chicago"),
    ]


def test_the_four_personas(company: SeedCompany) -> None:
    personas = {person.persona_key: person for person in company.people if person.persona_key}
    priya, mateo, marcus, dana = (personas[key] for key in ("priya", "mateo", "marcus", "dana"))

    assert set(personas) == {"priya", "mateo", "marcus", "dana"}
    assert (full_name(priya), location_code(company, priya)) == ("Priya Raman", "oak")
    assert (priya.employment_type, priya.manager_id) == ("salaried", marcus.id)
    assert (full_name(mateo), location_code(company, mateo)) == ("Mateo Alvarez", "aus")
    assert mateo.employment_type == "hourly"
    assert (full_name(marcus), location_code(company, marcus)) == ("Marcus Bell", "oak")
    assert (full_name(dana), location_code(company, dana)) == ("Dana Whitfield", "den")
    assert (dana.title, dana.is_hr_admin) == ("HR Business Partner", True)


def test_marcus_runs_the_oakland_store_directly_and_through_three_leads(
    company: SeedCompany,
) -> None:
    marcus = named(company, "Marcus Bell")
    his_manager = next(person for person in company.people if person.id == marcus.manager_id)
    direct = reports_of(company, marcus)
    leads = direct - {"Priya Raman", "Leo Nakamura"}
    oakland = {full_name(p) for p in company.people if location_code(company, p) == "oak"}

    assert marcus.title == "Store Manager"
    assert (his_manager.title, location_code(company, his_manager)) == (
        "Chief Operating Officer",
        "den",
    )
    assert {"Priya Raman", "Leo Nakamura"} < direct
    assert len(leads) == 3
    assert all(reports_of(company, named(company, lead)) for lead in leads)
    # Everyone else at the store reports to him, directly or through a lead.
    assert all_reports_of(company, marcus) == oakland - {"Marcus Bell"}
    assert (len(direct), len(all_reports_of(company, marcus))) == (5, 44)


def test_priya_and_leo_manage_no_one(company: SeedCompany) -> None:
    # The employee persona must never gain a manager's view of anyone.
    priya, leo = named(company, "Priya Raman"), named(company, "Leo Nakamura")

    assert reports_of(company, priya) == set()
    assert reports_of(company, leo) == set()
    assert (location_code(company, leo), leo.employment_type, leo.persona_key) == (
        "oak",
        "hourly",
        None,
    )


def test_dana_is_the_only_hr_admin(company: SeedCompany) -> None:
    hr_admins = [full_name(person) for person in company.people if person.is_hr_admin]

    assert hr_admins == ["Dana Whitfield"]


def test_everyone_but_the_ceo_reports_to_someone_in_the_company(company: SeedCompany) -> None:
    ids = {person.id for person in company.people}
    without_a_manager = [person.title for person in company.people if person.manager_id is None]

    assert without_a_manager == ["Chief Executive Officer"]
    assert {p.manager_id for p in company.people if p.manager_id is not None} <= ids


def test_every_reporting_line_reaches_the_ceo_without_a_cycle(company: SeedCompany) -> None:
    manager_of = {person.id: person.manager_id for person in company.people}

    for person in company.people:
        chain = [person.id]
        while (manager_id := manager_of[chain[-1]]) is not None:
            assert manager_id not in chain, f"{full_name(person)}'s reporting line loops"
            chain.append(manager_id)


def test_names_and_work_emails_are_unique(company: SeedCompany) -> None:
    given_names = [person.given_name for person in company.people]
    work_emails = [person.work_email for person in company.people]

    # Every first name is different, so "Leo" or "Priya" always means exactly one person.
    assert len(set(given_names)) == len(given_names)
    assert len(set(work_emails)) == len(work_emails)
    assert all(WORK_EMAIL.fullmatch(email) for email in work_emails)


def test_private_details_are_obviously_fictional(company: SeedCompany) -> None:
    people = {person.id: person for person in company.people}
    places = {row.id: f", {row.city}, {row.state} " for row in company.locations}

    assert {row.person_id for row in company.person_private} == set(people)
    for row in company.person_private:
        person = people[row.person_id]
        assert row.personal_email.endswith("@example.com")
        assert FICTIONAL_PHONE.fullmatch(row.phone)
        assert places[person.location_id] in row.home_address
        assert 21 <= years_between(row.date_of_birth, ANCHOR) <= 65
        assert years_between(row.date_of_birth, person.hire_date) >= 18
        assert person.hire_date < ANCHOR


def test_every_date_moves_with_the_anchor_date(company: SeedCompany) -> None:
    later = build_company(TENANT_ID, ANCHOR + timedelta(days=100))
    hundred_days = timedelta(days=100)

    for before, after in zip(company.people, later.people, strict=True):
        assert after.hire_date - before.hire_date == hundred_days
    for before_private, after_private in zip(
        company.person_private, later.person_private, strict=True
    ):
        assert after_private.date_of_birth - before_private.date_of_birth == hundred_days


def test_holidays_are_the_company_calendar_for_the_anchor_year_and_the_next(
    company: SeedCompany,
) -> None:
    for location in company.locations:
        seeded = {
            (row.holiday_date, row.name)
            for row in company.holidays
            if row.location_id == location.id
        }
        expected = {
            (holiday.holiday_date, holiday.name)
            for year in (2026, 2027)
            for holiday in holidays_for(location.code, year)
        }
        assert seeded == expected
    # Denver closes 7 days in 2026 and 8 in 2027; Oakland and Austin close 6 and 7.
    assert len(company.holidays) == 15 + 13 + 13


@pytest.mark.parametrize(("table_name", "row_type"), ROW_TYPES.items())
def test_each_row_type_has_exactly_its_tables_columns(table_name: str, row_type: type[Row]) -> None:
    # insert_company writes each field to the column of the same name.
    columns = set(Base.metadata.tables[table_name].columns.keys())

    assert {field.name for field in fields(row_type)} == columns
