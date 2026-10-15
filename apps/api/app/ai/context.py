"""The per-turn context: a system message with who is asking and today's date where they work.

It is a pure function of its inputs, so the evals can pin "today" and keep request fingerprints
stable. The date is the location's local date, never the sandbox's anchor date (which only moves
the seed data), so "next Friday" means the Friday the person means.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from app.ai.text import one_line
from app.modules.people.schemas import Me

Role = Literal["employee", "manager", "hr"]

# Fixed English names, so the text doesn't change with the server's locale.
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_ROLE_LABELS: dict[Role, str] = {"employee": "employee", "manager": "manager", "hr": "HR"}


@dataclass(frozen=True)
class ActorView:
    """What the model is told about the asker, from the server session and never from input."""

    given_name: str
    role: Role
    location_name: str
    state: str
    location_code: str
    timezone: str
    employment_type: str


def role_of(me: Me) -> Role:
    """The one rule for a person's role: HR over manager over employee."""
    return "hr" if me.is_hr_admin else "manager" if me.is_manager else "employee"


def actor_view(me: Me) -> ActorView:
    """The view of the signed-in person. `Me` already carries the location and its timezone."""
    role = role_of(me)
    return ActorView(
        given_name=me.given_name,
        role=role,
        location_name=me.location.name,
        state=me.location.state,
        location_code=me.location.code,
        timezone=me.location.timezone,
        employment_type=me.employment_type,
    )


def turn_context(
    actor_view: ActorView,
    *,
    now: datetime,
    handbook_label: str,
    operator_notes: Sequence[str],
) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        msg = "`now` must be timezone-aware"
        raise ValueError(msg)
    local = now.astimezone(ZoneInfo(actor_view.timezone))
    lines = [
        "Context for this turn.",
        f"Asker: {one_line(actor_view.given_name)}, role {_ROLE_LABELS[actor_view.role]}, "
        f"{actor_view.employment_type} employee.",
        f"Location: {one_line(actor_view.location_name)} "
        f"({actor_view.state}, code {actor_view.location_code}).",
        f"Today: {_WEEKDAYS[local.weekday()]}, {local.date().isoformat()} ({actor_view.timezone}).",
        f"Handbook version: {handbook_label}.",
    ]
    if operator_notes:
        lines.append("Operator notes:")
        lines.extend(f"- {one_line(note)}" for note in operator_notes)
    return "\n".join(lines)
