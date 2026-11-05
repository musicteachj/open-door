"""The per-turn context: a system message with who is asking and today's date where they work.

It is a pure function of its inputs, so the evals can pin "today" and keep request fingerprints
stable. The date is the location's local date, never the sandbox's anchor date (which only moves
the seed data), so "next Friday" means the Friday the person means.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from app.ai.text import one_line
from app.domain.cases import CATEGORY_LABELS
from app.domain.timeoff.today import today_at
from app.modules.cases.texts import WEEKDAYS, reply_by_label
from app.modules.people.schemas import Me

Role = Literal["employee", "manager", "hr"]

ROLE_LABELS: dict[Role, str] = {"employee": "employee", "manager": "manager", "hr": "HR"}


@dataclass(frozen=True)
class ActorView:
    """What the model is told about the asker, from the server session and never from input."""

    given_name: str
    role: Role
    location_name: str
    # The location's city. Not in the model's context text: the console labels the asker with it.
    city: str
    state: str
    location_code: str
    timezone: str
    employment_type: str


def role_for(*, is_hr_admin: bool, is_manager: bool) -> Role:
    """The one rule for a person's role: HR over manager over employee."""
    return "hr" if is_hr_admin else "manager" if is_manager else "employee"


def role_of(me: Me) -> Role:
    return role_for(is_hr_admin=me.is_hr_admin, is_manager=me.is_manager)


def actor_view(me: Me) -> ActorView:
    """The view of the signed-in person. `Me` already carries the location and its timezone."""
    role = role_of(me)
    return ActorView(
        given_name=me.given_name,
        role=role,
        location_name=me.location.name,
        city=me.location.city,
        state=me.location.state,
        location_code=me.location.code,
        timezone=me.location.timezone,
        employment_type=me.employment_type,
    )


def case_opened_sentence(category: str, reply_by: date) -> str:
    """The sentence (lowercase first word, to follow the "Since the last message:" prefix) for a
    case the person opened from this conversation since the last turn
    (spec, "What the model learns afterward"). Made from the stored category and the reply-by date
    only, worded here: nothing the person wrote ever reaches it, and an unknown category reads as
    "something else"."""
    label = CATEGORY_LABELS.get(category, "something else")
    day = reply_by_label(reply_by)
    return f"the person opened a confidential case with HR ({label}). HR replies by {day}."


def turn_context(
    actor_view: ActorView,
    *,
    now: datetime,
    handbook_label: str,
    operator_notes: Sequence[str],
    outcomes: Sequence[str] = (),
) -> str:
    """The context text. `outcomes` is what happened to the person's cards since the last turn,
    already worded from structured data (`proposals.unreported_outcomes`); each goes on its own
    line."""
    # The engine's own "today", so the model's date and the engine's can't drift apart. It also
    # refuses a naive `now`.
    local = today_at(actor_view.timezone, now)
    lines = [
        "Context for this turn.",
        f"Asker: {one_line(actor_view.given_name)}, role {ROLE_LABELS[actor_view.role]}, "
        f"{actor_view.employment_type} employee.",
        f"Location: {one_line(actor_view.location_name)} "
        f"({actor_view.state}, code {actor_view.location_code}).",
        f"Today: {WEEKDAYS[local.weekday()]}, {local.isoformat()} ({actor_view.timezone}).",
        f"Handbook version: {handbook_label}.",
    ]
    lines.extend(one_line(outcome) for outcome in outcomes)
    if operator_notes:
        lines.append("Operator notes:")
        lines.extend(f"- {one_line(note)}" for note in operator_notes)
    return "\n".join(lines)
