"""The reply-by date: the second business day after the day a case was sent, by Denver's calendar.

Every expected date is worked out by hand in a comment. October 2026 for reference:

    Mon 19  Tue 20  Wed 21  Thu 22  Fri 23  Sat 24  Sun 25
    Mon 26  Tue 27  Wed 28  Thu 29  Fri 30  Sat 31
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.cases import (
    HQ_LOCATION_CODE,
    HQ_TIMEZONE,
    add_business_days,
    hq_closed_days,
    reply_by,
)
from app.domain.holidays import holidays_for

DENVER = ZoneInfo("America/Denver")
OAKLAND = ZoneInfo("America/Los_Angeles")
NO_HOLIDAYS: frozenset[date] = frozenset()


def in_denver(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=DENVER)


def hq_holidays(*years: int) -> frozenset[date]:
    return frozenset(h.holiday_date for year in years for h in holidays_for("den", year))


def test_sent_monday_it_is_wednesday() -> None:
    # Mon Oct 19 sent. Business day 1 is Tue 20, business day 2 is Wed 21.
    assert reply_by(in_denver(2026, 10, 19, 9), DENVER, NO_HOLIDAYS) == date(2026, 10, 21)


def test_sent_tuesday_it_is_thursday() -> None:
    # Tue Oct 20: Wed 21 is 1, Thu 22 is 2.
    assert reply_by(in_denver(2026, 10, 20, 9), DENVER, NO_HOLIDAYS) == date(2026, 10, 22)


def test_sent_wednesday_it_is_friday() -> None:
    # Wed Oct 21: Thu 22 is 1, Fri 23 is 2.
    assert reply_by(in_denver(2026, 10, 21, 9), DENVER, NO_HOLIDAYS) == date(2026, 10, 23)


def test_sent_thursday_it_is_monday() -> None:
    # Thu Oct 22: Fri 23 is 1; Sat 24 and Sun 25 do not count; Mon 26 is 2.
    assert reply_by(in_denver(2026, 10, 22, 9), DENVER, NO_HOLIDAYS) == date(2026, 10, 26)


def test_sent_friday_it_is_tuesday() -> None:
    # Fri Oct 23: the weekend is skipped, Mon 26 is 1, Tue 27 is 2.
    assert reply_by(in_denver(2026, 10, 23, 9), DENVER, NO_HOLIDAYS) == date(2026, 10, 27)


def test_sent_saturday_it_is_tuesday() -> None:
    # Sat Oct 24: Sun does not count, Mon 26 is 1, Tue 27 is 2.
    assert reply_by(in_denver(2026, 10, 24, 12), DENVER, NO_HOLIDAYS) == date(2026, 10, 27)


def test_sent_sunday_it_is_tuesday() -> None:
    # Sun Oct 25: Mon 26 is 1, Tue 27 is 2.
    assert reply_by(in_denver(2026, 10, 25, 12), DENVER, NO_HOLIDAYS) == date(2026, 10, 27)


def test_a_holiday_in_between_moves_it_a_day_by_hand() -> None:
    # A made-up closure on Wed Oct 21. Sent Mon Oct 19: Tue 20 is 1, Wed 21 is closed, Thu 22 is 2.
    closed = frozenset({date(2026, 10, 21)})
    assert reply_by(in_denver(2026, 10, 19, 9), DENVER, closed) == date(2026, 10, 22)


def test_thanksgiving_week_with_the_real_calendar() -> None:
    # 2026: Thanksgiving is Thu Nov 26 and Denver also closes Fri Nov 27 (the calendar says so).
    holidays = hq_holidays(2026)
    assert {date(2026, 11, 26), date(2026, 11, 27)} <= holidays
    # Sent Wed Nov 25: Thu 26 and Fri 27 are closed, the weekend is skipped, Mon Nov 30 is 1 and
    # Tue Dec 1 is 2.
    assert reply_by(in_denver(2026, 11, 25, 9), DENVER, holidays) == date(2026, 12, 1)
    # Sent Mon Nov 23: Tue 24 is 1, Wed 25 is 2. The holidays are after it and change nothing.
    assert reply_by(in_denver(2026, 11, 23, 9), DENVER, holidays) == date(2026, 11, 25)
    # Sent Tue Nov 24: Wed 25 is 1, Thu and Fri are closed, the weekend is skipped, Mon 30 is 2.
    assert reply_by(in_denver(2026, 11, 24, 9), DENVER, holidays) == date(2026, 11, 30)


def test_thanksgiving_week_with_a_hand_written_calendar() -> None:
    holidays = frozenset({date(2026, 11, 26), date(2026, 11, 27)})
    # Sent Thu Nov 26 itself: Fri 27 is closed, the weekend is skipped, Mon 30 is 1, Tue Dec 1 is 2.
    assert reply_by(in_denver(2026, 11, 26, 9), DENVER, holidays) == date(2026, 12, 1)


def test_the_date_is_denvers_not_the_senders() -> None:
    # 11 PM Thursday Oct 22 in Oakland (UTC-7 until Nov 1) is 06:00 UTC on Friday Oct 23. Denver
    # (UTC-6) is then at midnight, so it is already Friday there.
    sent = datetime(2026, 10, 22, 23, 0, tzinfo=OAKLAND)
    assert sent.astimezone(UTC) == datetime(2026, 10, 23, 6, 0, tzinfo=UTC)
    assert sent.astimezone(DENVER).date() == date(2026, 10, 23)
    # Counted from Friday: Mon 26 is 1, Tue 27 is 2. From Thursday it would have been Monday 26.
    assert reply_by(sent, DENVER, NO_HOLIDAYS) == date(2026, 10, 27)


def test_late_evening_in_denver_is_still_that_day() -> None:
    # 11 PM Thursday Oct 22 in Denver is Thursday there (05:00 UTC on Friday): Fri 23 is 1, Mon 26
    # is 2. A UTC clock would say Friday and give Tuesday.
    sent = datetime(2026, 10, 22, 23, 0, tzinfo=DENVER)
    assert sent.astimezone(UTC).date() == date(2026, 10, 23)
    assert reply_by(sent, DENVER, NO_HOLIDAYS) == date(2026, 10, 26)


def test_across_december_31_with_next_years_holidays() -> None:
    # 2026: Jan 1 2027 is a Friday, so HQ is closed Fri Jan 1 2027 (the 2026 calendar has no
    # holiday in January; the year after has it).
    holidays = hq_holidays(2026, 2027)
    assert date(2027, 1, 1) in holidays
    # Sent Wed Dec 30 2026: Thu Dec 31 is 1, Fri Jan 1 is closed, the weekend is skipped, Mon Jan 4
    # is 2.
    assert reply_by(in_denver(2026, 12, 30, 9), DENVER, holidays) == date(2027, 1, 4)
    # Sent Thu Dec 31 2026: Fri Jan 1 closed, Mon Jan 4 is 1, Tue Jan 5 is 2.
    assert reply_by(in_denver(2026, 12, 31, 9), DENVER, holidays) == date(2027, 1, 5)
    # With only 2026's calendar the New Year closure is missed: why the caller passes both years.
    assert reply_by(in_denver(2026, 12, 30, 9), DENVER, hq_holidays(2026)) == date(2027, 1, 1)


def test_the_daylight_saving_weekend_counts_from_denvers_date() -> None:
    # Denver falls back on Sun Nov 1 2026 (2 AM MDT becomes 1 AM MST), so 23:30 that Sunday is MST
    # (UTC-7): 06:30 UTC on Monday Nov 2. The UTC date is Monday, Denver's is still Sunday.
    sent = datetime(2026, 11, 1, 23, 30, tzinfo=DENVER)
    assert sent.astimezone(UTC) == datetime(2026, 11, 2, 6, 30, tzinfo=UTC)
    # From Sunday: Mon Nov 2 is 1, Tue Nov 3 is 2. From Monday it would have been Wednesday.
    assert reply_by(sent, DENVER, NO_HOLIDAYS) == date(2026, 11, 3)


def test_an_observed_new_years_day_closes_the_friday_before() -> None:
    # Jan 1 2028 is a Saturday, so HQ closes Fri Dec 31 2027 (in 2027's calendar).
    holidays = hq_holidays(2027, 2028)
    assert date(2027, 12, 31) in holidays
    # Sent Wed Dec 29 2027: Thu Dec 30 is 1, Fri Dec 31 is closed, the weekend is skipped, and
    # Mon Jan 3 2028 is 2.
    assert reply_by(in_denver(2027, 12, 29, 9), DENVER, holidays) == date(2028, 1, 3)


def test_a_naive_time_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        reply_by(datetime(2026, 10, 19, 9), DENVER, NO_HOLIDAYS)  # noqa: DTZ001 (the point)


def test_is_business_day_skips_weekends_and_holidays() -> None:
    from datetime import date

    from app.domain.cases import is_business_day

    holiday = date(2026, 11, 26)  # Thanksgiving, a Thursday
    assert is_business_day(date(2026, 11, 25), frozenset({holiday}))
    assert not is_business_day(holiday, frozenset({holiday}))
    assert not is_business_day(date(2026, 11, 28), frozenset())  # Saturday
    assert not is_business_day(date(2026, 11, 29), frozenset())  # Sunday


def test_add_business_days_forward_skips_weekends_and_holidays() -> None:
    closed = frozenset({date(2026, 10, 21)})
    # Fri Oct 23 plus 1: Sat and Sun skipped, Mon Oct 26.
    assert add_business_days(date(2026, 10, 23), 1, NO_HOLIDAYS) == date(2026, 10, 26)
    # Mon Oct 19 plus 2 with Wed Oct 21 closed: Tue 20 is 1, Wed skipped, Thu 22 is 2.
    assert add_business_days(date(2026, 10, 19), 2, closed) == date(2026, 10, 22)
    # Sat Oct 24 plus 1: the start need not be a business day; Mon Oct 26.
    assert add_business_days(date(2026, 10, 24), 1, NO_HOLIDAYS) == date(2026, 10, 26)


def test_add_business_days_backward_skips_weekends_and_holidays() -> None:
    closed = frozenset({date(2026, 10, 21)})
    # Mon Oct 26 minus 1: the weekend is skipped, Fri Oct 23.
    assert add_business_days(date(2026, 10, 26), -1, NO_HOLIDAYS) == date(2026, 10, 23)
    # Thu Oct 22 minus 2 with Wed Oct 21 closed: Wed skipped, Tue 20 is 1, Mon 19 is 2.
    assert add_business_days(date(2026, 10, 22), -2, closed) == date(2026, 10, 19)
    # Sun Oct 25 minus 1: Sat skipped, Fri Oct 23.
    assert add_business_days(date(2026, 10, 25), -1, NO_HOLIDAYS) == date(2026, 10, 23)


def test_add_zero_business_days_is_the_same_day() -> None:
    assert add_business_days(date(2026, 10, 24), 0, NO_HOLIDAYS) == date(2026, 10, 24)


def test_hqs_code_zone_and_closed_days_are_shared_with_the_seed_and_the_service() -> None:
    from app.modules.sandbox.seed_data import CASES, LOCATIONS

    [hq] = [spec for spec in LOCATIONS if spec.code == HQ_LOCATION_CODE]
    assert hq.timezone == HQ_TIMEZONE
    assert {spec.location_code for spec in CASES} <= {spec.code for spec in LOCATIONS}
    assert hq_closed_days(2026, 2027) == hq_holidays(2026, 2027)
