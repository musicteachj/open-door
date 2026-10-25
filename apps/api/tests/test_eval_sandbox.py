"""The requests the eval harness adds to its sandbox after the seed (evals/assistant/
eval_sandbox.py): an upcoming Friday of Priya's to cancel and a pending request of hers for Marcus
to decide. Pure: the rows are built in memory from the seed company and the engine."""

from dataclasses import replace
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID, uuid5

import pytest

from app.domain.timeoff.model import Opening, Person, Request, Schedule
from app.domain.timeoff.pto import pto_balance
from app.modules.sandbox.seed import SeedCompany, build_company
from tests.assistant_eval import load_eval_module, load_runner

run = load_runner()
sandbox = load_eval_module("eval_sandbox.py")

TENANT = run.TENANT_ID
TODAY = run.NOW.date()


def company() -> SeedCompany:
    return build_company(TENANT, run.ANCHOR_DATE)


def priya_of(c: SeedCompany) -> Any:
    return next(p for p in c.people if p.persona_key == "priya")


def test_the_eval_sandbox_counts_back_from_the_date_of_every_turn() -> None:
    # The seed's "last week" is then the questions' last week.
    assert run.ANCHOR_DATE == run.NOW.date() == date(2026, 10, 15)


def test_the_cancel_day_is_an_approved_friday_and_the_pending_request_is_monday_to_wednesday() -> (
    None
):
    cancel, pending = sandbox.eval_requests(company())

    assert (cancel.start_date, cancel.end_date) == (date(2026, 10, 30), date(2026, 10, 30))
    assert cancel.start_date.strftime("%A") == "Friday"
    assert (cancel.type, cancel.status, cancel.amount_minutes) == ("pto", "approved", 480)
    assert (pending.start_date, pending.end_date) == (date(2026, 11, 16), date(2026, 11, 18))
    assert (pending.start_date.strftime("%A"), pending.end_date.strftime("%A")) == (
        "Monday",
        "Wednesday",
    )
    assert (pending.type, pending.status, pending.amount_minutes) == ("pto", "pending", 1440)


def test_both_belong_to_priya_and_the_approved_one_was_decided_by_her_manager() -> None:
    c = company()
    priya = priya_of(c)

    cancel, pending = sandbox.eval_requests(c)

    assert cancel.person_id == pending.person_id == priya.id
    assert cancel.decided_by == priya.manager_id
    assert cancel.decided_at is not None
    assert pending.decided_by is None
    assert pending.decided_at is None
    assert (
        cancel.created_at
        < cancel.decided_at
        < datetime.combine(cancel.start_date, time(), tzinfo=UTC)
    )


def test_the_ids_are_derived_from_the_sandbox_id_with_labels_the_seed_never_uses() -> None:
    cancel, pending = sandbox.eval_requests(company())

    assert cancel.id == uuid5(TENANT, "timeoff:priya:eval-cancel-friday")
    assert pending.id == uuid5(TENANT, "timeoff:priya:eval-pending-november")
    seeded = {row.id for row in company().time_off_requests}
    assert cancel.id not in seeded
    assert pending.id not in seeded


def test_the_same_sandbox_gets_the_same_ids_and_another_sandbox_gets_others() -> None:
    first = [r.id for r in sandbox.eval_requests(company())]
    again = [r.id for r in sandbox.eval_requests(company())]
    other = [r.id for r in sandbox.eval_requests(build_company(UUID(int=7), run.ANCHOR_DATE))]

    assert first == again
    assert set(first).isdisjoint(other)


def test_neither_day_is_a_holiday_and_both_are_days_priya_works() -> None:
    c = company()
    priya = priya_of(c)
    holidays = {h.holiday_date for h in c.holidays if h.location_id == priya.location_id}

    for row in sandbox.eval_requests(c):
        days = [
            date.fromordinal(n)
            for n in range(row.start_date.toordinal(), row.end_date.toordinal() + 1)
        ]
        assert all(d.isoweekday() in priya.scheduled_weekdays for d in days)
        assert holidays.isdisjoint(days)


def test_they_overlap_none_of_her_seeded_requests() -> None:
    c = company()
    priya = priya_of(c)
    mine = [r for r in c.time_off_requests if r.person_id == priya.id]

    for row in sandbox.eval_requests(c):
        assert not any(r.start_date <= row.end_date and row.start_date <= r.end_date for r in mine)


def test_the_balance_with_both_stays_inside_what_she_has_available() -> None:
    c = with_requests()
    priya = priya_of(c)
    location = next(loc for loc in c.locations if loc.id == priya.location_id)
    person = Person(
        priya.employment_type,
        location.state,  # type: ignore[arg-type]
        priya.hire_date,
        Schedule(frozenset(priya.scheduled_weekdays)),
    )
    opening = next(o for o in c.time_off_openings if o.person_id == priya.id)
    requests = [
        Request(str(r.id), r.type, r.start_date, r.end_date, r.partial_minutes, r.status)  # type: ignore[arg-type]
        for r in c.time_off_requests
        if r.person_id == priya.id
    ]
    holidays = {h.holiday_date: h.name for h in c.holidays if h.location_id == priya.location_id}

    balance = pto_balance(
        person, Opening(opening.as_of, opening.amount_minutes), requests, holidays, TODAY
    )

    # 174 hours available in the seed alone; 8 booked and 24 pending leave 142.
    assert balance.booked_minutes == 8 * 60
    assert balance.pending_minutes == 24 * 60
    assert balance.available_minutes == 142 * 60


def with_requests() -> SeedCompany:
    combined: SeedCompany = sandbox.with_eval_requests(company())
    return combined


def test_with_eval_requests_appends_them_and_changes_nothing_else() -> None:
    base = company()

    both = sandbox.with_eval_requests(base)

    assert len(both.time_off_requests) == len(base.time_off_requests) + 2
    assert both.time_off_requests[: len(base.time_off_requests)] == base.time_off_requests
    assert both.people == base.people
    assert both.time_off_openings == base.time_off_openings


def test_the_demo_seed_has_neither_request() -> None:
    seeded = [(r.start_date, r.end_date) for r in company().time_off_requests]

    assert (date(2026, 10, 30), date(2026, 10, 30)) not in seeded
    assert (date(2026, 11, 16), date(2026, 11, 18)) not in seeded


def test_a_request_is_found_by_the_persons_name_and_first_day() -> None:
    c = with_requests()

    assert sandbox.request_id(c, "Priya Raman", date(2026, 10, 30)) == str(
        uuid5(TENANT, "timeoff:priya:eval-cancel-friday")
    )
    zara = next(
        r
        for r in c.time_off_requests
        if r.status == "pending" and r.start_date == date(2026, 11, 5)
    )
    assert sandbox.request_id(c, "Zara Bautista", date(2026, 11, 5)) == str(zara.id)


def test_a_request_that_does_not_exist_is_an_error_naming_who_and_when() -> None:
    with pytest.raises(sandbox.NoSuchRequest, match=r"Priya Raman.*2026-12-01"):
        sandbox.request_id(with_requests(), "Priya Raman", date(2026, 12, 1))
    with pytest.raises(sandbox.NoSuchRequest, match=r"Nobody Here"):
        sandbox.request_id(with_requests(), "Nobody Here", date(2026, 10, 30))


def test_a_day_the_engine_would_not_charge_is_refused_when_the_rows_are_built() -> None:
    with pytest.raises(ValueError, match="doesn't fit"):
        sandbox.build_request(
            company(), "priya", "eval-weekend", date(2026, 10, 31), date(2026, 10, 31), "approved"
        )


def test_a_request_that_overlaps_one_of_hers_is_refused_when_the_rows_are_built() -> None:
    # Her seeded PTO on Tuesday, September 8 and Wednesday, September 9.
    with pytest.raises(ValueError, match="overlaps one of her requests"):
        sandbox.build_request(
            company(), "priya", "eval-clash", date(2026, 9, 9), date(2026, 9, 10), "approved"
        )


def test_a_request_the_balance_cannot_afford_is_refused_when_the_rows_are_built() -> None:
    # November 2 to December 2 is 22 charged days (Thanksgiving is closed): 176 hours, and she has
    # 174 available.
    with pytest.raises(ValueError, match="takes PTO below zero"):
        sandbox.build_request(
            company(), "priya", "eval-too-long", date(2026, 11, 2), date(2026, 12, 2), "pending"
        )


def test_building_the_pair_in_order_changes_nothing_about_either_row() -> None:
    c = company()

    cancel, pending = sandbox.eval_requests(c)

    # Each row equals the one built against the seed company alone, as before.
    assert cancel == sandbox.build_request(
        c, "priya", sandbox.CANCEL_LABEL, sandbox.CANCEL_DAY, sandbox.CANCEL_DAY, "approved"
    )
    assert pending == sandbox.build_request(
        c, "priya", sandbox.PENDING_LABEL, sandbox.PENDING_START, sandbox.PENDING_END, "pending"
    )
    assert [(r.start_date, r.end_date, r.amount_minutes, r.status) for r in (cancel, pending)] == [
        (date(2026, 10, 30), date(2026, 10, 30), 480, "approved"),
        (date(2026, 11, 16), date(2026, 11, 18), 1440, "pending"),
    ]


def test_a_balance_that_fits_each_request_but_not_both_is_refused() -> None:
    c = company()
    priya = priya_of(c)
    # 174 hours are available in the seed. An approved December booking of 18 days (144 hours)
    # leaves 30: 8 fits, 24 fits, 32 does not.
    template = next(r for r in c.time_off_requests if r.person_id == priya.id and r.type == "pto")
    filler = replace(
        template,
        id=uuid5(TENANT, "test:filler"),
        start_date=date(2026, 12, 1),
        end_date=date(2026, 12, 24),
        partial_minutes=None,
        amount_minutes=144 * 60,
        status="approved",
    )
    small = replace(c, time_off_requests=(*c.time_off_requests, filler))
    sandbox.build_request(
        small, "priya", sandbox.CANCEL_LABEL, sandbox.CANCEL_DAY, sandbox.CANCEL_DAY, "approved"
    )
    sandbox.build_request(
        small, "priya", sandbox.PENDING_LABEL, sandbox.PENDING_START, sandbox.PENDING_END, "pending"
    )

    with pytest.raises(ValueError, match="takes PTO below zero"):
        sandbox.eval_requests(small)


def test_the_persona_argument_decides_the_id_and_priyas_ids_are_unchanged() -> None:
    c = company()
    args = (sandbox.CANCEL_LABEL, sandbox.CANCEL_DAY, sandbox.CANCEL_DAY, "approved")

    mine = sandbox.build_request(c, "priya", *args)
    marcus = sandbox.build_request(c, "marcus", *args)

    assert mine.id == uuid5(TENANT, "timeoff:priya:eval-cancel-friday")
    assert marcus.id == uuid5(TENANT, "timeoff:marcus:eval-cancel-friday")
    assert marcus.id != mine.id
    pair = sandbox.eval_requests(c)
    assert [r.id for r in pair] == [
        uuid5(TENANT, "timeoff:priya:eval-cancel-friday"),
        uuid5(TENANT, "timeoff:priya:eval-pending-november"),
    ]
