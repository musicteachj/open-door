"""The seed company, built in memory: the same fictional company in every sandbox."""

import hashlib
import re
from collections import Counter
from dataclasses import astuple, fields
from datetime import UTC, date, datetime, time, timedelta
from itertools import cycle, islice, pairwise
from typing import cast
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

# Importing the models puts every table on Base.metadata.
from app.db import models  # noqa: F401
from app.db.base import Base
from app.domain.cases import reply_by
from app.domain.holidays import holidays_for
from app.domain.timeoff.counting import count_days
from app.domain.timeoff.evaluate import NewRequest, evaluate
from app.domain.timeoff.model import (
    EmploymentType,
    LeaveType,
    Opening,
    Request,
    RequestStatus,
    Schedule,
    State,
)
from app.domain.timeoff.model import Person as EnginePerson
from app.domain.timeoff.pto import pto_balance
from app.domain.timeoff.sick import sick_years
from app.domain.timeoff.today import today_at
from app.modules.sandbox.seed import (
    ROW_TYPES,
    CaseEventRow,
    CaseRow,
    PersonRow,
    RequestRow,
    Row,
    SeedCompany,
    build_company,
)
from app.modules.sandbox.seed_data import (
    LOCATIONS,
    SEEDED_SUMMARY_MODEL,
    SEEDED_SUMMARY_PLACEHOLDER,
    TIME_OFF_STREAM,
)

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
        | {row.id for row in company.time_off_openings}
        | {row.id for row in company.time_off_requests}
    )


def test_every_row_gets_an_id_of_its_own(company: SeedCompany) -> None:
    # all_ids() returns a set, so a repeated ID would quietly shrink it. Two seats sharing a key
    # would give two people one ID, which only the database would otherwise catch.
    rows = (
        len(company.locations)
        + len(company.departments)
        + len(company.people)
        + len(company.holidays)
        + len(company.time_off_openings)
        + len(company.time_off_requests)
    )
    assert len(all_ids(company)) == rows


def test_the_same_tenant_and_anchor_date_build_an_equal_company(company: SeedCompany) -> None:
    assert build_company(TENANT_ID, ANCHOR) == company


def test_another_tenant_gets_the_same_people_under_new_ids(company: SeedCompany) -> None:
    other = build_company(OTHER_TENANT_ID, ANCHOR)

    def directory(seeded: SeedCompany) -> list[tuple[str, str, str]]:
        return [(full_name(person), person.title, person.work_email) for person in seeded.people]

    assert directory(other) == directory(company)
    assert all_ids(other).isdisjoint(all_ids(company))
    assert {person.tenant_id for person in other.people} == {OTHER_TENANT_ID}


def test_145_people_across_four_locations_with_25_in_atlanta(company: SeedCompany) -> None:
    head_count = Counter(location_code(company, person) for person in company.people)

    assert head_count == {"den": 40, "oak": 45, "aus": 35, "atl": 25}
    assert len(company.person_private) == 145


def test_eight_departments_and_four_locations_each_with_people(company: SeedCompany) -> None:
    assert len(company.departments) == 8
    assert {row.id for row in company.departments} == {p.department_id for p in company.people}
    assert [(row.code, row.state, row.timezone) for row in company.locations] == [
        ("den", "CO", "America/Denver"),
        ("oak", "CA", "America/Los_Angeles"),
        ("aus", "TX", "America/Chicago"),
        ("atl", "GA", "America/New_York"),
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


def seeded_holiday_years(anchor: date) -> range:
    """The years the seed stores holidays for: the year before the anchor through two after."""
    return range(anchor.year - 1, anchor.year + 3)


def test_holidays_are_the_company_calendar_from_the_year_before_the_anchor_to_two_after(
    company: SeedCompany,
) -> None:
    expected_count = 0
    for location in company.locations:
        seeded = {
            (row.holiday_date, row.name)
            for row in company.holidays
            if row.location_id == location.id
        }
        expected = {
            (holiday.holiday_date, holiday.name)
            for year in seeded_holiday_years(ANCHOR)
            for holiday in holidays_for(location.code, year)
        }
        assert seeded == expected
        expected_count += len(expected)
    assert seeded_holiday_years(ANCHOR) == range(2025, 2029)
    assert len(company.holidays) == expected_count


@pytest.mark.parametrize("anchor", [date(2026, 12, 31), date(2027, 1, 1), date(2026, 6, 15)])
def test_the_seeded_years_always_cover_what_the_engine_can_be_asked_for(
    anchor: date,
) -> None:
    """A sandbox lives 24 hours, so a person's today can be a day or two past the anchor, or a day
    before it. The engine refuses an end date after December 31 of the next year, so the holidays
    must reach that year. Created at any UTC time of the anchor date, at any instant within 25
    hours after, in every seeded time zone."""
    company = build_company(TENANT_ID, anchor)
    years = seeded_holiday_years(anchor)
    assert {row.holiday_date.year for row in company.holidays} == set(years)
    for location in company.locations:
        for hour in range(24):
            created = datetime(anchor.year, anchor.month, anchor.day, hour, 30, tzinfo=UTC)
            for later in range(26):
                today = today_at(location.timezone, created + timedelta(hours=later))
                assert today.year + 1 in years
                assert today.year in years


def test_new_years_crossing_is_covered_from_both_sides() -> None:
    # Anchor December 31, created at 23:00 UTC: 25 hours on it is January 1 or 2, so the engine's
    # last day is December 31 of anchor year + 2, and the holidays reach into that year.
    december = build_company(TENANT_ID, date(2026, 12, 31))
    created = datetime(2026, 12, 31, 23, 0, tzinfo=UTC)
    latest = max(
        today_at(location.timezone, created + timedelta(hours=25))
        for location in december.locations
    )
    assert latest.year == 2027
    assert any(row.holiday_date.year == 2028 for row in december.holidays)
    # Anchor January 1, created at 03:00 UTC: it is still December 31 in the Americas, and that
    # year's closures are seeded.
    january = build_company(TENANT_ID, date(2027, 1, 1))
    earliest = today_at("America/Los_Angeles", datetime(2027, 1, 1, 3, 0, tzinfo=UTC))
    assert earliest == date(2026, 12, 31)
    assert any(row.holiday_date.year == 2026 for row in january.holidays)


@pytest.mark.parametrize(("table_name", "row_type"), ROW_TYPES.items())
def test_each_row_type_has_exactly_its_tables_columns(table_name: str, row_type: type[Row]) -> None:
    # insert_company writes each field to the column of the same name.
    columns = set(Base.metadata.tables[table_name].columns.keys())

    assert {field.name for field in fields(row_type)} == columns


def test_the_people_who_existed_before_the_atlanta_store_are_unchanged(
    company: SeedCompany,
) -> None:
    """Golden values taken from the seed as it was before Atlanta, with 120 people.

    Names, phones, and addresses come from shuffles and draws whose results depend on the order
    and size of every list. A new location or longer name list must not move any of them.
    """
    private = {row.person_id: row for row in company.person_private}
    first_120 = [
        (
            person.given_name,
            person.family_name,
            private[person.id].phone,
            private[person.id].home_address,
        )
        for person in company.people[:120]
    ]

    mid_oakland, last_austin = company.people[74], company.people[119]
    assert (mid_oakland.title, mid_oakland.hire_date, first_120[74]) == (
        "Cashier",
        date(2024, 7, 24),
        ("Mina", "Abbott", "510-555-0153", "6039 Bluebell Lane, Oakland, CA 94606"),
    )
    assert (last_austin.title, last_austin.hire_date, first_120[119]) == (
        "Forklift Operator",
        date(2021, 6, 21),
        ("Fatima", "Kim", "512-555-0169", "5695 Linden Avenue, Austin, TX 78745"),
    )
    assert (
        hashlib.sha256(repr(first_120).encode()).hexdigest()
        == "0f412651d5b0a6acaf6a886f8d5cf0eacb10c6c4fdb4bc0f5c2f5b4de3e4d521"
    )


# ---- Time off: schedules, openings, history, and the one pending request (Phase 5) ----

MONDAY_TO_FRIDAY = {1, 2, 3, 4, 5}
SUNDAY_TO_THURSDAY = {1, 2, 3, 4, 7}
TUESDAY_TO_SATURDAY = {2, 3, 4, 5, 6}
WEDNESDAY_TO_SUNDAY = {3, 4, 5, 6, 7}
# The stores' rotation, in the order the spec gives it, handed out by seat order.
STORE_ROTATION = [
    TUESDAY_TO_SATURDAY,
    SUNDAY_TO_THURSDAY,
    WEDNESDAY_TO_SUNDAY,
    MONDAY_TO_FRIDAY,
]
# Handbook 4.1, worked by hand: 10 hours a month for salaried staff and 8 for hourly, with a
# ceiling of 1.5 times the year's amount (180 and 144 hours).
CEILING_MINUTES = {"salaried": 10_800, "hourly": 8_640}
MONTHLY_MINUTES = {"salaried": 600, "hourly": 480}


def schedule_of(person: PersonRow) -> set[int]:
    return set(person.scheduled_weekdays)


def test_every_person_has_a_schedule_per_the_patterns(company: SeedCompany) -> None:
    store_staff: dict[str, list[PersonRow]] = {"oak": [], "atl": []}
    for person in company.people:
        code = location_code(company, person)
        assert person.scheduled_weekdays == tuple(sorted(set(person.scheduled_weekdays)))
        if code == "den":
            assert schedule_of(person) == MONDAY_TO_FRIDAY, full_name(person)
        elif code in store_staff:
            # The store managers, Priya, and Leo are written out; everyone else rotates.
            if person.title == "Store Manager" or person.persona_key == "priya":
                assert schedule_of(person) == MONDAY_TO_FRIDAY, full_name(person)
            elif full_name(person) == "Leo Nakamura":
                assert schedule_of(person) == WEDNESDAY_TO_SUNDAY
            else:
                store_staff[code].append(person)
    for staff in store_staff.values():
        rotation = list(islice(cycle(STORE_ROTATION), len(staff)))
        assert [schedule_of(person) for person in staff] == rotation
    assert (len(store_staff["oak"]), len(store_staff["atl"])) == (42, 24)

    nights = next(person for person in company.people if person.title == "Shift Supervisor, Nights")
    night_side = {nights.id} | {
        person.id
        for person in company.people
        if full_name(person) in all_reports_of(company, nights)
    }
    austin = [p for p in company.people if location_code(company, p) == "aus"]
    assert len(night_side) == 1 + 12 + 2
    for person in austin:
        expected = SUNDAY_TO_THURSDAY if person.id in night_side else MONDAY_TO_FRIDAY
        assert schedule_of(person) == expected, full_name(person)


def test_the_personas_schedules_are_exact(company: SeedCompany) -> None:
    for name in ("Priya Raman", "Marcus Bell", "Dana Whitfield", "Mateo Alvarez"):
        assert named(company, name).scheduled_weekdays == (1, 2, 3, 4, 5), name
    # Leo is a store associate, so his seat is written out rather than left to the rotation.
    assert named(company, "Leo Nakamura").scheduled_weekdays == (3, 4, 5, 6, 7)


def location_state(company: SeedCompany, person: PersonRow) -> str:
    return next(row.state for row in company.locations if row.id == person.location_id)


def holidays_at(company: SeedCompany, location_id: UUID) -> dict[date, str]:
    return {
        row.holiday_date: row.name for row in company.holidays if row.location_id == location_id
    }


def facts_of(
    company: SeedCompany, person: PersonRow
) -> tuple[EnginePerson, Opening, tuple[Request, ...]]:
    """The engine's view of a seeded person: who, their opening, and every stored request."""
    opening_row = next(row for row in company.time_off_openings if row.person_id == person.id)
    requests = tuple(
        Request(
            str(row.id),
            cast(LeaveType, row.type),
            row.start_date,
            row.end_date,
            row.partial_minutes,
            cast(RequestStatus, row.status),
        )
        for row in company.time_off_requests
        if row.person_id == person.id
    )
    engine_person = EnginePerson(
        cast(EmploymentType, person.employment_type),
        cast(State, location_state(company, person)),
        person.hire_date,
        Schedule(frozenset(person.scheduled_weekdays)),
    )
    return engine_person, Opening(opening_row.as_of, opening_row.amount_minutes), requests


def week_before_the_anchors_week(anchor: date) -> date:
    """The Monday of the week before the one that holds the anchor date."""
    return anchor - timedelta(days=anchor.weekday() + 7)


def leos_last_week_pto(company: SeedCompany) -> RequestRow:
    leo = named(company, "Leo Nakamura")
    monday = week_before_the_anchors_week(company.anchor_date)
    return next(
        row
        for row in company.time_off_requests
        if row.person_id == leo.id and row.start_date == monday + timedelta(days=2)
    )


def assert_the_time_off_seed_is_sound(company: SeedCompany) -> None:
    """Every rule the history, the openings, and the pending request must keep, for any anchor."""
    anchor = company.anchor_date
    january_1 = date(anchor.year, 1, 1)
    day_before = anchor - timedelta(days=1)
    people = {person.id: person for person in company.people}
    openings = {row.person_id: row for row in company.time_off_openings}
    last_week = leos_last_week_pto(company)
    assert last_week.person_id == named(company, "Leo Nakamura").id
    assert set(openings) == set(people)
    assert len(company.time_off_openings) == len(people)
    assert [row for row in company.time_off_requests if row.status == "pending"] != []
    assert all(row.person_id in people for row in company.time_off_requests)

    for person in company.people:
        who = full_name(person)
        engine_person, opening, requests = facts_of(company, person)
        holidays = holidays_at(company, person.location_id)
        # An opening is as of January 1 of the anchor year, or the hire date if that is later,
        # and below the ceiling, so a month's earning is never cut short on its first day.
        assert opening.as_of == max(january_1, person.hire_date), who
        assert 0 <= opening.amount_minutes < CEILING_MINUTES[person.employment_type], who
        if person.hire_date >= january_1:
            assert opening.amount_minutes == 0, who
        else:
            assert opening.amount_minutes % 60 == 0, who

        mine = sorted(
            (row for row in company.time_off_requests if row.person_id == person.id),
            key=lambda row: row.start_date,
        )
        for earlier, later in pairwise(mine):
            assert earlier.end_date < later.start_date, f"{who}'s requests overlap"
        for row in mine:
            counted = count_days(engine_person, row.start_date, row.end_date, holidays).counted
            assert len(counted) >= 1, who
            assert row.amount_minutes == (row.partial_minutes or 480 * len(counted)), who
            assert (row.created_via, row.proposal_id) == ("ui", None)
            assert (row.decision_note, row.canceled_at) == (None, None)
            if row.status != "pending":
                assert row.end_date <= day_before, who
            if row != last_week:
                assert row.start_date >= opening.as_of, who
            start_of_day = datetime.combine(row.start_date, datetime.min.time(), tzinfo=UTC)
            assert row.created_at < start_of_day or row.status == "recorded"
            match (row.type, row.status):
                case ("pto", "approved"):
                    assert row.decided_by == person.manager_id is not None, who
                    assert row.decided_at is not None
                    assert row.created_at < row.decided_at < start_of_day, who
                case ("sick", "recorded"):
                    assert (row.decided_by, row.decided_at) == (None, None)
                case ("pto", "pending"):
                    assert (row.decided_by, row.decided_at) == (None, None)
                case _:
                    pytest.fail(f"{who} has a {row.type} request that is {row.status}")
        # What is left to use is never negative, for PTO or for any sick year, on the anchor or
        # the day before it (a person's today in the Americas, early in the UTC day). Earning only
        # grows with today, so the day before is the strictest: a month-end anchor must not rely
        # on that day's earning.
        for today in (anchor, day_before):
            assert (
                pto_balance(engine_person, opening, requests, holidays, today).available_minutes
                >= 0
            ), f"{who} on {today}"
            assert all(
                year.available_minutes >= 0
                for year in sick_years(engine_person, requests, holidays, today)
            ), f"{who} on {today}"
        if person.manager_id is None:
            assert all(row.status != "approved" for row in mine), "the CEO has no one to decide"


def test_every_person_has_one_opening_below_their_ceiling(company: SeedCompany) -> None:
    assert_the_time_off_seed_is_sound(company)
    january_1 = date(ANCHOR.year, 1, 1)
    openings = {row.person_id: row for row in company.time_off_openings}
    hired_this_year = [p for p in company.people if p.hire_date >= january_1]
    assert hired_this_year, "the anchor year has hires, so the zero opening is exercised"
    for person in company.people:
        opening = openings[person.id]
        assert opening.as_of == max(january_1, person.hire_date)
        assert (opening.amount_minutes == 0) == (person in hired_this_year)


def test_an_opening_is_the_balance_at_the_start_of_its_day() -> None:
    """A hire on a month-end opens at 0 and earns that day (the engine adds the day's earning), so
    on its own day the balance is exactly that month's rate: the earning is counted once, never
    already inside the opening."""
    seen_month_end_hires = 0
    for offset in range(0, 366, 3):
        company = build_company(TENANT_ID, date(2026, 1, 1) + timedelta(days=offset))
        for person in company.people:
            engine_person, opening, requests = facts_of(company, person)
            if person.hire_date.year != company.anchor_date.year:
                continue
            rate = MONTHLY_MINUTES[person.employment_type]
            month_end = opening.as_of.month != (opening.as_of + timedelta(days=1)).month
            holidays = holidays_at(company, person.location_id)
            on_its_day = pto_balance(engine_person, opening, requests, holidays, opening.as_of)
            # Hired this year: nothing to start from, so the day's own earning is all there is.
            assert opening.amount_minutes == 0
            assert on_its_day.earned_minutes == (rate if month_end else 0)
            seen_month_end_hires += month_end
    assert seen_month_end_hires > 0, "some hire date fell on a month-end, so the pin was exercised"


def test_leo_has_approved_pto_wednesday_to_friday_of_the_week_before_the_anchors_week(
    company: SeedCompany,
) -> None:
    leo = named(company, "Leo Nakamura")
    row = leos_last_week_pto(company)

    # The anchor is Monday, 2026-10-05, so the week before is Monday, September 28.
    assert (row.start_date, row.end_date) == (date(2026, 9, 30), date(2026, 10, 2))
    assert (row.person_id, row.type, row.status) == (leo.id, "pto", "approved")
    # Wednesday, Thursday, and Friday are all on Leo's Wednesday-to-Sunday week, and none is a
    # holiday: three days of 8 hours.
    assert row.amount_minutes == 3 * 480
    assert row.decided_by == leo.manager_id == named(company, "Marcus Bell").id
    assert row.partial_minutes is None


@pytest.mark.parametrize("anchor", [date(2026, 10, 7), date(2026, 10, 11), date(2026, 5, 29)])
def test_leos_last_week_follows_the_anchor(anchor: date) -> None:
    company = build_company(TENANT_ID, anchor)
    row = leos_last_week_pto(company)
    monday = week_before_the_anchors_week(anchor)

    assert (row.start_date, row.end_date) == (
        monday + timedelta(days=2),
        monday + timedelta(days=4),
    )
    assert row.amount_minutes == 3 * 480  # no holiday in these weeks


def test_marcuss_queue_holds_one_pending_request_from_zara_about_three_weeks_out(
    company: SeedCompany,
) -> None:
    marcus, zara = named(company, "Marcus Bell"), named(company, "Zara Bautista")
    pending = [row for row in company.time_off_requests if row.status == "pending"]

    assert len(pending) == 1
    (row,) = pending
    assert (row.person_id, zara.manager_id, zara.title) == (
        zara.id,
        marcus.id,
        "Department Lead, Apparel",
    )
    assert row.type == "pto"
    # Zara works Tuesday to Saturday: two scheduled days in a row, three weeks after the anchor.
    assert timedelta(days=21) <= row.start_date - ANCHOR <= timedelta(days=28)
    assert row.end_date == row.start_date + timedelta(days=1)
    assert (row.decided_by, row.decided_at, row.decision_note, row.canceled_at) == (
        None,
        None,
        None,
        None,
    )
    assert row.partial_minutes is None
    assert row.amount_minutes == 2 * 480
    # The engine finds nothing wrong with it, today, from the rest of Zara's requests.
    engine_person, opening, requests = facts_of(company, zara)
    others = tuple(request for request in requests if request.id != str(row.id))
    result = evaluate(
        engine_person,
        opening,
        others,
        holidays_at(company, zara.location_id),
        NewRequest("pto", row.start_date, row.end_date, None),
        ANCHOR,
    )
    assert (result.ok, result.problems, result.amount_minutes) == (True, (), 960)


def test_nothing_overlaps_and_everything_fits_the_balances(company: SeedCompany) -> None:
    assert_the_time_off_seed_is_sound(company)
    approved = [row for row in company.time_off_requests if row.status == "approved"]
    recorded = [row for row in company.time_off_requests if row.status == "recorded"]
    with_pto = {row.person_id for row in approved}
    # Modest, but there: most people have some history, and the sick days are the odd one.
    assert len(with_pto) >= 100
    assert 200 <= len(approved) <= 600
    assert 20 <= len(recorded) <= 200


@pytest.mark.parametrize(
    "anchor",
    [
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 8),
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2028, 2, 29),
        date(2026, 6, 30),
        date(2026, 9, 30),
        date(2026, 10, 5),
        date(2026, 10, 22),
        date(2026, 12, 31),
        date(2027, 12, 31),
    ],
)
def test_other_anchors_build_a_sound_company(anchor: date) -> None:
    assert_the_time_off_seed_is_sound(build_company(TENANT_ID, anchor))


def test_no_location_draws_from_the_time_off_stream() -> None:
    """A location's phones and addresses must not share a stream with the time-off history, or
    opening one would reshuffle the other."""
    assert TIME_OFF_STREAM == 2, "changing it reshuffles all seeded history"
    assert all(spec.seed_stream != TIME_OFF_STREAM for spec in LOCATIONS)


def test_every_fifth_anchor_for_three_years_builds_a_sound_company() -> None:
    # Five is coprime to seven, so every weekday and every part of the year takes a turn as the
    # anchor.
    day = date(2026, 1, 1)
    while day <= date(2028, 12, 31):
        assert_the_time_off_seed_is_sound(build_company(TENANT_ID, day))
        day += timedelta(days=5)


def test_history_is_the_same_for_every_tenant_apart_from_its_ids(company: SeedCompany) -> None:
    other = build_company(OTHER_TENANT_ID, ANCHOR)

    def shape(seeded: SeedCompany) -> list[tuple[object, ...]]:
        return [
            (row.type, row.start_date, row.end_date, row.partial_minutes, row.amount_minutes)
            for row in seeded.time_off_requests
        ]

    assert shape(other) == shape(company)
    assert [row.amount_minutes for row in other.time_off_openings] == [
        row.amount_minutes for row in company.time_off_openings
    ]


def test_the_people_and_their_private_details_are_unchanged_by_time_off(
    company: SeedCompany,
) -> None:
    """Golden hashes of every row the seed built before Phase 5, for this tenant and anchor. The
    time-off draws use a stream of their own, so none of these moves: a change to a name, a hire
    date, an ID, a phone, or an address (or to the years before 2027's holidays) fails here."""

    def digest(rows: list[tuple[object, ...]]) -> str:
        return hashlib.sha256(repr(rows).encode()).hexdigest()

    people = [
        tuple(
            getattr(row, field.name)
            for field in fields(PersonRow)
            if field.name != "scheduled_weekdays"
        )
        for row in company.people
    ]
    holidays_before = [
        astuple(row)
        for row in company.holidays
        if row.holiday_date.year in (ANCHOR.year, ANCHOR.year + 1)
    ]
    assert digest(people) == "553c3e432ebcd33cf628c71f713161ff3d96c35fcb6c1a705c01243006d5d509"
    assert (
        digest([astuple(row) for row in company.person_private])
        == "08ca2a0e42792b6c8c6646dbb17e21d4cd9dc4f407090c7bbd0642a0ca55fbda"
    )
    assert (
        digest([astuple(row) for row in company.locations])
        == "247d547f1a94b833025d22b10e93f5d2d3ba72339a6ff8644da2fafe0e003897"
    )
    assert (
        digest([astuple(row) for row in company.departments])
        == "483c69fa71b6be8e1ff0a2bf1e057a075add0a014c09926c9eedd72cc6be03c6"
    )
    assert (
        digest(holidays_before)
        == "dcb5672e08a04aa609bb410d2ce1ab415fcf74ebb8f2776982a3c86701b837b6"
    )


# --- The seeded cases (Phase 6) ---

DENVER = ZoneInfo("America/Denver")


def denver_holidays(year: int) -> frozenset[date]:
    return frozenset(
        holiday.holiday_date
        for years in (year - 1, year, year + 1)
        for holiday in holidays_for("den", years)
    )


def business_days_between(earlier: date, later: date, closed: frozenset[date]) -> int:
    """How many business days after `earlier` is `later` (counting `later`, never `earlier`)."""
    days = (earlier + timedelta(days=n) for n in range(1, (later - earlier).days + 1))
    return sum(1 for day in days if day.weekday() < 5 and day not in closed)


def case_of(company: SeedCompany, given_name: str) -> CaseRow:
    person = next(p for p in company.people if p.given_name == given_name)
    return next(case for case in company.cases if case.person_id == person.id)


def test_the_four_seeded_cases_are_from_the_specs_people(company: SeedCompany) -> None:
    people = {person.id: person for person in company.people}
    locations = {location.id: location.code for location in company.locations}

    seen = [
        (
            f"{people[case.person_id].given_name} {people[case.person_id].family_name}",
            people[case.person_id].title,
            locations[people[case.person_id].location_id],
            case.category,
            case.status,
        )
        for case in company.cases
    ]

    assert seen == [
        ("Keisha Zhang", "Warehouse Associate", "aus", "pay", "new"),
        ("Chloe Foster", "Shift Lead, Opening", "atl", "harassment_discrimination", "new"),
        ("Aaliyah Edwards", "Cashier", "oak", "safety", "in_review"),
        ("Lucia Gutierrez", "Graphic Designer", "den", "medical_accommodation", "closed"),
    ]
    # None of them is a persona, so none can be the visitor.
    assert all(people[case.person_id].persona_key is None for case in company.cases)


def test_the_cases_ids_come_from_the_sandbox_id(company: SeedCompany) -> None:
    other = build_company(OTHER_TENANT_ID, ANCHOR)

    for case in company.cases:
        assert case.tenant_id == TENANT_ID
        assert case.id.version == 5
    assert {case.id for case in company.cases}.isdisjoint(case.id for case in other.cases)
    ids = [
        value
        for case in company.cases
        for value in (case.id, case.submission_id, case.summary_id, *(e.id for e in case.events))
    ]
    assert len(ids) == len(set(ids))


def recorded_case_ids(company: SeedCompany) -> set[UUID]:
    return {c.id for c in company.cases if c.summary_text != SEEDED_SUMMARY_PLACEHOLDER}


def test_build_company_holds_the_words_and_the_placeholder_in_plaintext(
    company: SeedCompany,
) -> None:
    assert build_company(TENANT_ID, ANCHOR) == company
    assert all(case.text and "\u2014" not in case.text for case in company.cases)
    # A case with no recorded real summary carries the placeholder (tests/test_seeded_summaries.py
    # checks the recorded ones).
    plain = [c for c in company.cases if c.id not in recorded_case_ids(company)]
    assert {case.summary_text for case in plain} <= {SEEDED_SUMMARY_PLACEHOLDER}
    assert {case.summary_model for case in plain} <= {SEEDED_SUMMARY_MODEL}


def anchors() -> list[date]:
    # Every weekday of a week (October 5, 2026 is a Monday), the Monday after Thanksgiving (the
    # Friday between is an HQ holiday), the Friday after Thanksgiving itself, Christmas week, and
    # New Year's Day.
    week = [date(2026, 10, 5) + timedelta(days=n) for n in range(7)]
    return [
        *week,
        date(2026, 11, 26),
        date(2026, 11, 27),
        date(2026, 11, 30),
        date(2026, 12, 25),
        date(2027, 1, 1),
        date(2027, 1, 4),
    ]


@pytest.mark.parametrize("anchor", anchors())
def test_the_cases_are_sent_in_business_days_before_the_anchor(anchor: date) -> None:
    company = build_company(TENANT_ID, anchor)
    closed = denver_holidays(anchor.year)
    # The anchor's own day, or the last business day before it when it is a closed day.
    today = anchor
    while today.weekday() >= 5 or today in closed:
        today -= timedelta(days=1)

    sent = {
        given: case_of(company, given).created_at.astimezone(DENVER).date()
        for given in ("Keisha", "Chloe", "Aaliyah", "Lucia")
    }

    assert {given: business_days_between(day, today, closed) for given, day in sent.items()} == {
        "Keisha": 1,
        "Chloe": 2,
        "Aaliyah": 6,
        "Lucia": 15,
    }
    assert all(day.weekday() < 5 and day not in closed for day in sent.values())


@pytest.mark.parametrize("anchor", anchors())
def test_chloes_reply_is_due_on_the_anchor_and_keishas_is_later(anchor: date) -> None:
    company = build_company(TENANT_ID, anchor)
    closed = denver_holidays(anchor.year)
    keisha, chloe = case_of(company, "Keisha"), case_of(company, "Chloe")
    is_business_day = anchor.weekday() < 5 and anchor not in closed

    if is_business_day:
        assert chloe.reply_by == anchor
    else:
        # A reply cannot fall on a closed day: it is due the last business day before it, which
        # is already due on the anchor.
        assert chloe.reply_by < anchor
        assert business_days_between(chloe.reply_by, anchor, closed) <= 1
    assert keisha.reply_by > chloe.reply_by
    assert chloe.status == keisha.status == "new"


def test_the_cases_use_the_replyby_rule_and_the_dates_stay_before_the_anchor() -> None:
    for anchor in anchors():
        company = build_company(TENANT_ID, anchor)
        closed = denver_holidays(anchor.year)
        for case in company.cases:
            assert case.reply_by == reply_by(case.created_at, DENVER, closed)
            assert all(
                case.created_at <= event.occurred_at < datetime.combine(anchor, time.min, UTC)
                for event in case.events
            )


def test_the_timelines_match_the_statuses_in_time_order(company: SeedCompany) -> None:
    dana = next(p.id for p in company.people if p.persona_key == "dana")

    timeline = {
        given: [
            (e.kind, e.from_status, e.to_status, e.actor_person_id)
            for e in case_of(company, given).events
        ]
        for given in ("Keisha", "Chloe", "Aaliyah", "Lucia")
    }

    for given in ("Keisha", "Chloe", "Aaliyah", "Lucia"):
        case = case_of(company, given)
        times = [event.occurred_at for event in case.events]
        assert times == sorted(times)
        assert times[0] == case.created_at
        assert case.events[0].kind == "opened"
        assert case.events[0].actor_person_id == case.person_id
        assert case.events[1].kind == "summary_written"
        assert case.events[1].actor_person_id is None
        changes = [e for e in case.events if e.kind == "status_changed"]
        assert case.status_changed_at == (changes[-1].occurred_at if changes else case.created_at)
        assert (changes[-1].to_status if changes else "new") == case.status
    assert [kind for kind, *_ in timeline["Keisha"]] == ["opened", "summary_written"]
    assert [kind for kind, *_ in timeline["Chloe"]] == ["opened", "summary_written"]
    assert timeline["Aaliyah"][2:] == [
        ("viewed", None, None, dana),
        ("text_read", None, None, dana),
        ("status_changed", "new", "in_review", dana),
    ]
    assert timeline["Lucia"][2:] == [
        ("viewed", None, None, dana),
        ("text_read", None, None, dana),
        ("status_changed", "new", "in_review", dana),
        ("status_changed", "in_review", "closed", dana),
    ]


def test_the_cases_sit_in_the_cases_table_apart_from_the_sealed_columns() -> None:
    plain = {field.name for field in fields(CaseRow)}
    sealed_or_elsewhere = {"text", "summary_id", "events"} | {
        name for name in plain if name.startswith("summary_")
    }
    columns = set(Base.metadata.tables["cases"].columns.keys())

    assert plain - sealed_or_elsewhere <= columns
    # What a seeded case leaves unset or seals on the way in.
    assert columns - (plain - sealed_or_elsewhere) == {
        "conversation_id",
        "turn_id",
        "key_id",
        "wrapped_key",
        "text_ciphertext",
    }
    event_columns = set(Base.metadata.tables["case_events"].columns.keys())
    assert {f.name for f in fields(CaseEventRow)} | {"tenant_id", "case_id"} == event_columns
