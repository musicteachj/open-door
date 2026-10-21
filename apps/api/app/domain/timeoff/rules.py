"""The one table of rules the engine cites.

A rule is a handbook section ID plus the name of the rule it backs. The engine names sections by
ID only; the service resolves titles and deep links from the pinned handbook. Every section ID
here is one of 3.1, 4.1, 4.2, 4.3, CA-4.3, or CO-4.3, and a test enforces that.
"""

from dataclasses import dataclass
from types import MappingProxyType

from app.domain.timeoff.model import State


@dataclass(frozen=True, slots=True)
class Rule:
    section_id: str  # "4.1"
    rule: str  # "pto-earning"


def _table(*rules: Rule) -> "MappingProxyType[str, Rule]":
    return MappingProxyType({rule.rule: rule for rule in rules})


RULES = _table(
    Rule("3.1", "scheduled-days"),  # each scheduled day is 8 hours; only scheduled days count
    Rule("4.2", "holidays-not-charged"),  # a company holiday is never charged
    Rule("4.1", "pto-earning"),  # earned on the last day of each month worked
    Rule("4.1", "pto-ceiling"),  # earning stops at 1.5 times the yearly amount
    Rule("4.1", "pto-available"),  # only earned PTO, less pending and booked, can be requested
    Rule("4.1", "pto-increments"),  # full days or half days
    Rule("4.1", "pto-notice"),  # two weeks where you can, for more than three days
    Rule("4.3", "sick-increments"),  # whole hours up to a day, or whole scheduled days
    Rule("4.3", "sick-window"),  # record up to 30 days after the day out
)

_SICK_GRANT_SECTION: dict[State, str] = {
    "TX": "4.3",
    "GA": "4.3",
    "CA": "CA-4.3",
    "CO": "CO-4.3",
}


def sick_grant_rule(state: State) -> Rule:
    """The section that backs a state's yearly sick grant."""
    return Rule(_SICK_GRANT_SECTION[state], "sick-grant")
