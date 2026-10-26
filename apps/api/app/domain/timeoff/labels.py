"""The one amount label the API and the tool results share, so the model never divides by 8.

Hours always: "1 hour", otherwise "N hours". Days follow in parentheses only when the amount is
at least a day (480 minutes) and a whole number of quarter days (a multiple of 120 minutes):
"8 hours (1 day)", "10 hours (1.25 days)", "90 hours (11.25 days)". Exactly 240 minutes reads
"4 hours (half a day)". Minutes that are not whole hours read "1 hour 30 minutes", and under an
hour "45 minutes"; nothing is rounded. A negative keeps its sign. All integer arithmetic.
"""

from app.domain.timeoff.model import DAY_MINUTES, HALF_DAY_MINUTES

_QUARTER_DAY_MINUTES = DAY_MINUTES // 4  # 120
_QUARTER_FRACTIONS = {0: "", 1: ".25", 2: ".5", 3: ".75"}


def hours_label(minutes: int) -> str:
    """The hours-only text ("8 hours", "1 hour 30 minutes"), with no days. Not negative."""
    hours, rest = divmod(minutes, 60)
    if rest:
        return _minutes_text(hours, rest)
    return f"{hours} hour" if hours == 1 else f"{hours} hours"


def label(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    amount = abs(minutes)
    text = hours_label(amount)
    if amount == HALF_DAY_MINUTES and minutes > 0:
        return f"{text} (half a day)"
    if amount >= DAY_MINUTES and amount % _QUARTER_DAY_MINUTES == 0:
        quarters = amount // _QUARTER_DAY_MINUTES
        whole, part = divmod(quarters, 4)
        days = f"{sign}{whole}{_QUARTER_FRACTIONS[part]}"
        unit = "day" if quarters == 4 else "days"
        return f"{sign}{text} ({days} {unit})"
    return f"{sign}{text}"


def _minutes_text(hours: int, rest: int) -> str:
    minutes = f"{rest} minute" if rest == 1 else f"{rest} minutes"
    if hours == 0:
        return minutes
    hour_text = f"{hours} hour" if hours == 1 else f"{hours} hours"
    return f"{hour_text} {minutes}"
