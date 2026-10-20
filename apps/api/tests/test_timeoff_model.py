"""The time-off types and the rule table. Every expected value was worked out by hand."""

from datetime import date

import pytest

from app.domain.timeoff.evaluate import NewRequest
from app.domain.timeoff.model import (
    DAY_MINUTES,
    HALF_DAY_MINUTES,
    Opening,
    Person,
    Request,
    Schedule,
)
from app.domain.timeoff.rules import RULES, Rule, sick_grant_rule

ALLOWED_SECTIONS = {"3.1", "4.1", "4.2", "4.3", "CA-4.3", "CO-4.3"}


def test_a_day_is_eight_hours_and_a_half_day_is_four() -> None:
    assert DAY_MINUTES == 8 * 60
    assert HALF_DAY_MINUTES == 4 * 60


def test_a_schedule_refuses_no_days() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Schedule(weekdays=frozenset())


@pytest.mark.parametrize("weekday", [0, 8, -1])
def test_a_schedule_refuses_a_weekday_outside_one_to_seven(weekday: int) -> None:
    with pytest.raises(ValueError, match="ISO 1 to 7"):
        Schedule(weekdays=frozenset({1, weekday}))


def test_a_schedule_accepts_the_ends_of_the_range() -> None:
    assert Schedule(weekdays=frozenset({1, 7})).weekdays == {1, 7}


def test_a_request_refuses_an_end_before_its_start() -> None:
    with pytest.raises(ValueError, match="before it starts"):
        Request(
            id="r1",
            type="pto",
            start=date(2026, 10, 20),
            end=date(2026, 10, 19),
            partial_minutes=None,
            status="pending",
        )


def test_a_one_day_request_is_allowed() -> None:
    day = date(2026, 10, 20)
    request = Request(
        id="r1", type="sick", start=day, end=day, partial_minutes=120, status="recorded"
    )
    assert request.start == request.end


def test_an_opening_refuses_a_negative_amount() -> None:
    with pytest.raises(ValueError, match="negative"):
        Opening(as_of=date(2026, 1, 1), amount_minutes=-1)


def test_an_opening_of_zero_is_allowed() -> None:
    assert Opening(as_of=date(2026, 1, 1), amount_minutes=0).amount_minutes == 0


def test_every_rule_names_one_of_the_six_sections() -> None:
    assert RULES  # the table is not empty
    for rule in RULES.values():
        assert rule.section_id in ALLOWED_SECTIONS


def test_the_table_is_keyed_by_the_rule_name() -> None:
    for name, rule in RULES.items():
        assert rule.rule == name


def test_the_spec_rules_are_in_their_sections() -> None:
    # Spec "Every result cites its rule".
    assert RULES["scheduled-days"] == Rule("3.1", "scheduled-days")
    assert RULES["holidays-not-charged"] == Rule("4.2", "holidays-not-charged")
    assert RULES["pto-earning"] == Rule("4.1", "pto-earning")
    assert RULES["pto-ceiling"] == Rule("4.1", "pto-ceiling")
    assert RULES["pto-available"] == Rule("4.1", "pto-available")


@pytest.mark.parametrize(
    ("state", "section"),
    [("TX", "4.3"), ("GA", "4.3"), ("CA", "CA-4.3"), ("CO", "CO-4.3")],
)
def test_the_sick_grant_rule_follows_the_state(state: str, section: str) -> None:
    assert sick_grant_rule(state) == Rule(section, "sick-grant")  # type: ignore[arg-type]


def _request(kind: str, start: date, end: date, partial: int | None) -> Request:
    return Request("r", kind, start, end, partial, "pending")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kind", "end", "partial"),
    [
        ("pto", date(2026, 10, 20), 480),  # PTO partial must be 240
        ("pto", date(2026, 10, 20), 120),
        ("sick", date(2026, 10, 20), 0),  # under 60
        ("sick", date(2026, 10, 20), 30),
        ("sick", date(2026, 10, 20), 90),  # not whole hours
        ("sick", date(2026, 10, 20), 900),  # over a day
        ("pto", date(2026, 10, 21), 240),  # a partial on a two-day range
        ("sick", date(2026, 10, 21), 120),
    ],
)
def test_a_request_refuses_a_partial_the_rules_do_not_allow(
    kind: str, end: date, partial: int
) -> None:
    with pytest.raises(ValueError, match="partial"):
        _request(kind, date(2026, 10, 20), end, partial)


@pytest.mark.parametrize(
    ("kind", "partial"), [("pto", 240), ("sick", 180), ("sick", 60), ("sick", 480)]
)
def test_a_request_accepts_a_partial_the_rules_allow(kind: str, partial: int) -> None:
    day = date(2026, 10, 20)
    assert _request(kind, day, day, partial).partial_minutes == partial


def test_a_schedule_built_from_a_plain_set_is_frozen_in() -> None:
    days = {1, 2, 3}
    schedule = Schedule(weekdays=days)  # type: ignore[arg-type]
    days.add(7)
    assert schedule.weekdays == frozenset({1, 2, 3})
    assert isinstance(schedule.weekdays, frozenset)
    person = Person("salaried", "TX", date(2020, 1, 6), schedule)
    assert isinstance(hash(person), int)


def test_a_stored_request_may_span_31_days_but_not_32() -> None:
    # Oct 1 to Oct 31 2026 is 31 days; Oct 1 to Nov 1 is 32.
    assert _request("pto", date(2026, 10, 1), date(2026, 10, 31), None).end == date(2026, 10, 31)
    with pytest.raises(ValueError, match="31"):
        _request("pto", date(2026, 10, 1), date(2026, 11, 1), None)


@pytest.mark.parametrize("kind", ["PTO", "vacation", ""])
def test_a_request_refuses_an_unknown_type(kind: str) -> None:
    day = date(2026, 10, 20)
    with pytest.raises(ValueError, match="type"):
        _request(kind, day, day, None)


@pytest.mark.parametrize("status", ["Approved", "done", ""])
def test_a_request_refuses_an_unknown_status(status: str) -> None:
    day = date(2026, 10, 20)
    with pytest.raises(ValueError, match="status"):
        Request("r", "pto", day, day, None, status)  # type: ignore[arg-type]


@pytest.mark.parametrize("kind", ["PTO", "vacation"])
def test_a_new_request_refuses_an_unknown_type(kind: str) -> None:
    day = date(2026, 10, 20)
    with pytest.raises(ValueError, match="type"):
        NewRequest(kind, day, day, None)  # type: ignore[arg-type]


@pytest.mark.parametrize("employment_type", ["part-time", "Salaried", ""])
def test_a_person_refuses_an_unknown_employment_type(employment_type: str) -> None:
    schedule = Schedule(weekdays=frozenset({1}))
    with pytest.raises(ValueError, match="employment type"):
        Person(employment_type, "TX", date(2020, 1, 6), schedule)  # type: ignore[arg-type]


@pytest.mark.parametrize("state", ["NY", "tx", ""])
def test_a_person_refuses_an_unknown_state(state: str) -> None:
    schedule = Schedule(weekdays=frozenset({1}))
    with pytest.raises(ValueError, match="state"):
        Person("salaried", state, date(2020, 1, 6), schedule)  # type: ignore[arg-type]
