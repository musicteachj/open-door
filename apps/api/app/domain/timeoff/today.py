"""Today's date at a location. The engine never reads the clock: the caller passes `now`."""

from datetime import date, datetime
from zoneinfo import ZoneInfo


def today_at(timezone: str, now: datetime) -> date:
    """The calendar date at `timezone` when it is `now`.

    A naive `now` is refused with ValueError. An unknown zone raises
    `zoneinfo.ZoneInfoNotFoundError`, and a malformed key (empty, absolute, or containing `..`)
    raises ValueError from `ZoneInfo`.

    This is never the sandbox's anchor date: late in the evening in Oakland it is already
    tomorrow in UTC, and the person's today is still the local date.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        msg = "`now` must be timezone-aware"
        raise ValueError(msg)
    return now.astimezone(ZoneInfo(timezone)).date()
