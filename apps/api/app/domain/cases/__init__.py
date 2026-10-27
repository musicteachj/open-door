"""When HR replies to a case: the second business day after it was sent.

Pure, like everything under app.domain: no framework imports and no clock. The caller passes the
moment the case was sent, Denver HQ's time zone, and HQ's holidays, so the date is the same for
everyone and a test can work it out by hand.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.holidays import holidays_for

# Denver HQ: the one calendar and clock every reply-by date uses, wherever the sender is. The seed
# and the service both read these, so the code, the zone, and the closed days are written once.
HQ_LOCATION_CODE = "den"
HQ_TIMEZONE = "America/Denver"

REPLY_BUSINESS_DAYS = 2
# Monday is 0 and Friday is 4.
LAST_WEEKDAY = 4


def hq_closed_days(*years: int) -> frozenset[date]:
    """The days Denver HQ is closed in the given years, from the company calendar."""
    return frozenset(
        holiday.holiday_date for year in years for holiday in holidays_for(HQ_LOCATION_CODE, year)
    )


def is_business_day(day: date, holidays: frozenset[date]) -> bool:
    """Whether `day` is a weekday that is not in `holidays`."""
    return day.weekday() <= LAST_WEEKDAY and day not in holidays


def add_business_days(day: date, count: int, holidays: frozenset[date]) -> date:
    """The business day `count` business days after `day` (before it, for a negative count).

    `day` need not be a business day itself, and it never counts. Zero returns `day`.
    """
    step = timedelta(days=1 if count > 0 else -1)
    remaining = abs(count)
    while remaining:
        day += step
        if is_business_day(day, holidays):
            remaining -= 1
    return day


def reply_by(sent_at: datetime, tz: ZoneInfo, holidays: frozenset[date]) -> date:
    """The date HR replies by: the second business day after the day the case was sent.

    The sent day is the calendar day in `tz` (Denver HQ's), whatever the sender's own zone, so a
    case sent at 11 PM Thursday in Oakland, already Friday in Denver, counts from Friday. A business
    day is a weekday that is not in `holidays`. The sent day itself never counts, even when it is a
    business day, so Monday gives Wednesday. `holidays` must cover the days after the sent day too:
    the caller passes the sent year's and the next year's.
    """
    if sent_at.tzinfo is None or sent_at.utcoffset() is None:
        msg = "sent_at must be timezone-aware"
        raise ValueError(msg)
    day = sent_at.astimezone(tz).date()
    return add_business_days(day, REPLY_BUSINESS_DAYS, holidays)
