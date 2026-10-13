"""Who a section applies to, and how its audience reads in plain words.

A section applies to a person when each of its `applies_to` lists is empty or contains theirs: the
state of their location, their employment type, and their location's code. Applicability decides
relevance, not permission: the whole handbook is readable by everyone. Stage 3's SQL filter must
agree with `applies`, and a test compares them.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.handbook.models import Audience

STATE_NAMES = {"CA": "California", "CO": "Colorado", "GA": "Georgia", "TX": "Texas"}


@dataclass(frozen=True, slots=True)
class Asker:
    """What decides which sections apply to someone. It comes from the server session, never from
    input: see app.modules.handbook.asker."""

    state: str
    employment_type: str
    location_code: str


def applies(audience: Audience, asker: Asker) -> bool:
    return (
        (not audience.states or asker.state in audience.states)
        and (not audience.employment_types or asker.employment_type in audience.employment_types)
        and (not audience.locations or asker.location_code in audience.locations)
    )


def audience_label(audience: Audience, location_names: Mapping[str, str]) -> str:
    """The audience in words: "Everyone", "California employees", "Hourly staff in California",
    "Denver HQ". Locations alone stand as their own names; otherwise they follow with "at"."""
    states = [STATE_NAMES.get(state, state) for state in audience.states]
    types = [kind.capitalize() for kind in audience.employment_types]
    locations = [location_names.get(code, code) for code in audience.locations]

    if not (states or types or locations):
        return "Everyone"
    if locations and not (states or types):
        return _join(locations)

    if types:
        label = f"{_join(types, lower_after_first=True)} staff"
        if states:
            label += f" in {_join(states)}"
    elif states:
        label = f"{_join(states)} employees"
    else:
        label = "Employees"
    if locations:
        label += f" at {_join(locations)}"
    return label


def _join(items: Sequence[str], *, lower_after_first: bool = False) -> str:
    if lower_after_first:
        items = [items[0], *(item.lower() for item in items[1:])]
    if len(items) <= 2:
        return " and ".join(items)
    return f"{', '.join(items[:-1])}, and {items[-1]}"
