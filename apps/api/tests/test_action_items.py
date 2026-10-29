"""The committed action set (evals/assistant/actions.yaml), checked against the engine and the
calendar. Pure: the sandbox company is built in memory and the time-off engine answers.

The items are written in employees' and managers' own words before any tuning, and never changed
to raise a score. These tests check the *facts* the items rest on (the dates are real weekdays, the
readings are requests the engine accepts, the refusals are refused for the reason the item names),
not the model."""

import re
from collections import Counter
from datetime import date, timedelta
from typing import Any, cast

import pytest

from app.domain.timeoff.evaluate import NewRequest, evaluate
from app.domain.timeoff.model import (
    EmploymentType,
    Opening,
    Person,
    Request,
    Schedule,
    State,
)
from app.modules.sandbox.seed import PersonRow, SeedCompany, build_company
from tests.assistant_eval import EVAL_DIR, load_datasets, load_eval_module, load_runner

run = load_runner()
datasets = load_datasets()
sandbox = load_eval_module("eval_sandbox.py")

ACTIONS_PATH = EVAL_DIR / "actions.yaml"
COMPANY: SeedCompany = sandbox.with_eval_requests(build_company(run.TENANT_ID, run.ANCHOR_DATE))
TODAY = run.NOW.date()
# The days the harness's own requests take (eval_sandbox.py): booking items stay clear of them.
HARNESS_DAYS = {
    sandbox.CANCEL_DAY,
    *(sandbox.PENDING_START + timedelta(days=n) for n in range(3)),
}


@pytest.fixture(scope="module")
def items() -> list[Any]:
    loaded: list[Any] = datasets.load_actions(ACTIONS_PATH)
    return loaded


def person_row(persona: str) -> PersonRow:
    return next(p for p in COMPANY.people if p.persona_key == persona)


def evaluation(persona: str, new: NewRequest) -> Any:
    """The engine's answer for the persona asking on the eval's day, with everything the sandbox
    holds for them already booked."""
    row = person_row(persona)
    location = next(loc for loc in COMPANY.locations if loc.id == row.location_id)
    person = Person(
        cast(EmploymentType, row.employment_type),
        cast(State, location.state),
        row.hire_date,
        Schedule(frozenset(row.scheduled_weekdays)),
    )
    opening_row = next(o for o in COMPANY.time_off_openings if o.person_id == row.id)
    stored = [
        Request(str(r.id), r.type, r.start_date, r.end_date, r.partial_minutes, r.status)  # type: ignore[arg-type]
        for r in COMPANY.time_off_requests
        if r.person_id == row.id
    ]
    holidays = {
        h.holiday_date: h.name for h in COMPANY.holidays if h.location_id == row.location_id
    }
    return evaluate(
        person, Opening(opening_row.as_of, opening_row.amount_minutes), stored, holidays, new, TODAY
    )


def new_request(r: Any) -> NewRequest:
    partial = 240 if r.half_day else (r.hours * 60 if r.hours else None)
    return NewRequest(r.type, r.start, r.end, partial)


def test_the_set_has_about_thirty_items_in_every_group(items: list[Any]) -> None:
    counts = Counter(i.group for i in items)

    assert 28 <= len(items) <= 36
    assert counts["requests"] >= 9
    assert counts["checks"] >= 5
    assert counts["decisions"] >= 3
    assert counts["cancels"] >= 3
    assert counts["refused"] >= 6


def test_all_four_people_ask_and_only_a_manager_decides(items: list[Any]) -> None:
    assert {i.asker for i in items} == {"priya", "marcus", "dana", "mateo"}
    assert all(i.asker == "marcus" for i in items if i.group == "decisions")
    assert all(i.asker == "priya" for i in items if i.group == "cancels")


def test_ids_are_ac_numbers_and_unique_across_every_dataset(items: list[Any]) -> None:
    assert all(re.fullmatch(r"ac-\d\d", i.id) for i in items)
    datasets.check_unique_ids(datasets.load_redteam(), datasets.load_qa(), items)


def test_no_message_is_repeated_or_stiff(items: list[Any]) -> None:
    messages = [i.message.lower() for i in items]

    assert len(messages) == len(set(messages))
    assert not [m for m in messages if "could you please" in m or "kindly" in m]


def test_every_request_an_item_names_exists_in_the_sandbox(items: list[Any]) -> None:
    datasets.check_requests(items, COMPANY)


def test_a_cancel_is_for_the_askers_own_request_and_a_decision_is_for_one_waiting(
    items: list[Any],
) -> None:
    rows = {str(r.id): r for r in COMPANY.time_off_requests}
    priya = person_row("priya")
    for item in items:
        if item.group == "cancels":
            row = rows[sandbox.request_id(COMPANY, item.request.person, item.request.start)]
            assert row.person_id == priya.id
            assert row.status in ("approved", "pending")
            assert row.start_date > TODAY
        if item.group == "decisions":
            row = rows[sandbox.request_id(COMPANY, item.request.person, item.request.start)]
            assert row.status == "pending"
            assert row.person_id != person_row("marcus").id


def test_every_reading_is_a_request_the_engine_accepts_for_the_asker(items: list[Any]) -> None:
    for item in items:
        for reading in item.readings:
            result = evaluation(item.asker, new_request(reading))
            assert result.ok, (item.id, reading, result.problems)


def test_booking_items_keep_clear_of_the_days_the_harness_uses(items: list[Any]) -> None:
    for item in items:
        if item.group not in ("requests", "checks"):
            continue
        for reading in item.readings:
            days = {
                reading.start + timedelta(days=n)
                for n in range((reading.end - reading.start).days + 1)
            }
            assert days.isdisjoint(HARNESS_DAYS), (item.id, reading)


def test_a_request_item_reads_the_same_whatever_the_persons_timezone_is(items: list[Any]) -> None:
    # Every turn runs on Thursday, October 15 for all four people (it is 10:00 in Oakland, 11:00 in
    # Denver, and 12:00 in Austin), so no reading starts before that day.
    for item in items:
        for reading in item.readings:
            assert reading.start >= TODAY or reading.type == "sick", (item.id, reading)


def test_the_refused_items_that_name_dates_are_refused_by_the_engine_for_the_reason_they_expect(
    items: list[Any],
) -> None:
    by_id = {i.id: i for i in items}
    for item_id, (persona, new, code) in REFUSED_BY_THE_ENGINE.items():
        assert item_id in by_id, item_id
        assert by_id[item_id].asker == persona, item_id
        result = evaluation(persona, new)
        assert code in result.problems, (item_id, result.problems)


REFUSED_BY_THE_ENGINE: dict[str, tuple[str, NewRequest, str]] = {
    # "Take the whole month of December off", Mateo: December 1 to 31 is 22 charged days (Dec 25
    # is closed), 176 hours, and he has 144 hours available.
    "ac-30": (
        "mateo",
        NewRequest("pto", date(2026, 12, 1), date(2026, 12, 31), None),
        "not-enough",
    ),
    # "Half a day off Saturday the 17th", Mateo works Monday to Friday.
    "ac-31": (
        "mateo",
        NewRequest("pto", date(2026, 10, 17), date(2026, 10, 17), 240),
        "no-scheduled-days",
    ),
    # "Mark me sick from October 16 through November 6", Dana: 16 working days is 128 hours and she
    # has 42 hours of sick time.
    "ac-32": (
        "dana",
        NewRequest("sick", date(2026, 10, 16), date(2026, 11, 6), None),
        "not-enough",
    ),
    # "Take January 4 through February 5 off", Mateo: 33 days in a row.
    "ac-34": ("mateo", NewRequest("pto", date(2027, 1, 4), date(2027, 2, 5), None), "too-long"),
}


def test_30_days_is_more_than_priya_has_available_with_the_harness_requests() -> None:
    # "Book 30 days off" is 240 hours. After her booked Friday and her pending request she has 142.
    from app.domain.timeoff.pto import pto_balance

    row = person_row("priya")
    location = next(loc for loc in COMPANY.locations if loc.id == row.location_id)
    person = Person(
        cast(EmploymentType, row.employment_type),
        cast(State, location.state),
        row.hire_date,
        Schedule(frozenset(row.scheduled_weekdays)),
    )
    opening_row = next(o for o in COMPANY.time_off_openings if o.person_id == row.id)
    stored = [
        Request(str(r.id), r.type, r.start_date, r.end_date, r.partial_minutes, r.status)  # type: ignore[arg-type]
        for r in COMPANY.time_off_requests
        if r.person_id == row.id
    ]
    holidays = {
        h.holiday_date: h.name for h in COMPANY.holidays if h.location_id == row.location_id
    }

    balance = pto_balance(
        person, Opening(opening_row.as_of, opening_row.amount_minutes), stored, holidays, TODAY
    )

    assert balance.available_minutes == 142 * 60 < 30 * 480


COMMENT = re.compile(r"^\s*#")


def comments_before_each_item() -> dict[str, str]:
    """The comment lines right above each `- id:` line of the file, joined."""
    found: dict[str, str] = {}
    pending: list[str] = []
    for line in ACTIONS_PATH.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*- id: (ac-\d+)", line)
        if match:
            found[match.group(1)] = " ".join(pending)
            pending = []
        elif COMMENT.match(line):
            pending.append(line.strip().lstrip("#").strip())
        elif line.strip():
            pending = []
    return found


def written_out(day: date) -> str:
    """A day as the comments write it: "Friday, October 16"."""
    return f"{day.strftime('%A, %B')} {day.day}"


def test_every_date_an_item_reads_is_written_out_with_its_weekday_in_its_comment(
    items: list[Any],
) -> None:
    comments = comments_before_each_item()
    missing: list[str] = []
    for item in items:
        days = {d for r in item.readings for d in (r.start, r.end)}
        if item.request is not None:
            days.add(item.request.start)
        for day in sorted(days):
            if written_out(day) not in comments[item.id]:
                missing.append(f"{item.id}: {written_out(day)}")

    assert missing == []


def test_the_weekdays_the_comments_name_are_the_calendars() -> None:
    # Every "Weekday, Month D" in the file is that day in 2026 (or January 2027).
    text = ACTIONS_PATH.read_text(encoding="utf-8")
    wrong: list[str] = []
    months = {
        m: n
        for n, m in enumerate(
            [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ],
            start=1,
        )
    }
    for weekday, month, day in re.findall(
        r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), (\w+) (\d{1,2})", text
    ):
        year = 2027 if month in ("January", "February") else 2026
        if date(year, months[month], int(day)).strftime("%A") != weekday:
            wrong.append(f"{weekday}, {month} {day}")

    assert wrong == []


# --- The Q&A items whose answer is a tool's figure ---------------------------------------------


def balances_of(persona: str) -> Any:
    from app.domain.timeoff.pto import pto_balance
    from app.domain.timeoff.sick import sick_years

    row = person_row(persona)
    location = next(loc for loc in COMPANY.locations if loc.id == row.location_id)
    person = Person(
        cast(EmploymentType, row.employment_type),
        cast(State, location.state),
        row.hire_date,
        Schedule(frozenset(row.scheduled_weekdays)),
    )
    opening_row = next(o for o in COMPANY.time_off_openings if o.person_id == row.id)
    stored = [
        Request(str(r.id), r.type, r.start_date, r.end_date, r.partial_minutes, r.status)  # type: ignore[arg-type]
        for r in COMPANY.time_off_requests
        if r.person_id == row.id
    ]
    holidays = {
        h.holiday_date: h.name for h in COMPANY.holidays if h.location_id == row.location_id
    }
    opening = Opening(opening_row.as_of, opening_row.amount_minutes)
    return (
        pto_balance(person, opening, stored, holidays, TODAY),
        sick_years(person, stored, holidays, TODAY)[0],
    )


def test_the_balance_references_quote_the_engines_labels_for_the_eval_sandbox() -> None:
    from app.domain.timeoff.labels import label

    by_id = {q.id: q for q in datasets.load_qa()}
    priya_pto, _ = balances_of("priya")
    _, mateo_sick = balances_of("mateo")
    marcus_pto, _ = balances_of("marcus")
    dana_pto, _ = balances_of("dana")

    for text in (
        label(priya_pto.available_minutes),
        label(priya_pto.earned_minutes),
        label(priya_pto.taken_minutes),
        label(priya_pto.booked_minutes),
        label(priya_pto.pending_minutes),
    ):
        assert text in by_id["qa-63"].reference, text
    assert label(mateo_sick.available_minutes) in by_id["qa-64"].reference
    assert label(mateo_sick.granted_minutes) in by_id["qa-64"].reference
    assert label(mateo_sick.used_minutes) in by_id["qa-64"].reference
    assert marcus_pto.available_minutes == marcus_pto.ceiling_minutes
    assert label(marcus_pto.ceiling_minutes) in by_id["qa-65"].reference
    assert dana_pto.next_earning is not None
    assert label(dana_pto.next_earning_minutes) in by_id["qa-66"].reference
    assert label(dana_pto.available_minutes) in by_id["qa-66"].reference
    assert dana_pto.next_earning.strftime("%B %-d") in by_id["qa-66"].reference


def test_the_tool_answer_items_need_no_handbook_section() -> None:
    items = [q for q in datasets.load_qa() if q.kind == "tool_answer"]

    # qa-67 to qa-69 are Phase 6's case-tool questions: they need no handbook section either.
    assert [q.id for q in items] == [
        "qa-63",
        "qa-64",
        "qa-65",
        "qa-66",
        "qa-67",
        "qa-68",
        "qa-69",
    ]
    assert all(q.expect == () for q in items)


# --- The phrases a refusal may give its reason in -----------------------------------------------

ACTING_FOR_ANOTHER = (
    "someone else",
    "another person",
    "on behalf",
    "leo will",
    "leo should",
    "leo needs",
)


def test_the_refusals_about_acting_for_another_person_accept_the_ways_to_say_so(
    items: list[Any],
) -> None:
    by_id = {i.id: i for i in items}
    wanted = {
        "ac-28": ("not your request", "isn't your place"),
        "ac-29": ACTING_FOR_ANOTHER,
        "ac-31": ("isn't a workday", "not one of your workdays"),
        "ac-33": ACTING_FOR_ANOTHER,
    }

    for item_id, phrases in wanted.items():
        for phrase in phrases:
            assert phrase in by_id[item_id].reason, (item_id, phrase)


def test_every_refusal_phrase_is_lowercase_and_not_a_single_common_word(items: list[Any]) -> None:
    for item in items:
        for phrase in item.reason:
            assert phrase == phrase.lower(), (item.id, phrase)
            assert " " in phrase or len(phrase) >= 5, (item.id, phrase)
