"""What the case service takes and returns. Plain dataclasses: the routes (Stage 3) map them to
their JSON, and none of them is ever sent to a model.

Units and zones: `sent_at` and the other `*_at` values are UTC instants; `reply_by` and the dates
beside it are calendar dates in Denver HQ's zone.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Final, Literal
from uuid import UUID

CATEGORIES: Final = (
    "harassment_discrimination",
    "safety",
    "medical_accommodation",
    "pay",
    "other",
)
type Category = Literal[
    "harassment_discrimination", "safety", "medical_accommodation", "pay", "other"
]
type Status = Literal["new", "in_review", "closed"]
type Screening = Literal["ordinary", "sensitive", "crisis", "unscreened"]
type QueueFilter = Literal["open", "new", "in_review", "closed"]
type SummaryFailure = Literal[
    "transport", "refusal", "timeout", "budget", "checks", "crisis", "unscreened"
]


@dataclass(frozen=True, slots=True)
class OpenCase:
    submission_id: UUID
    category: str
    text: str = field(repr=False)
    turn_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CaseStatusView:
    """What the person who opened a case sees of it: no words, no screening."""

    id: UUID
    category: str
    status: str
    sent_at: datetime
    reply_by: date
    status_changed_at: datetime


@dataclass(frozen=True, slots=True)
class CaseOpened:
    case: CaseStatusView
    # False when the submission (or its turn) already had a case: nothing new is scheduled.
    created: bool
    screening: str
    # The fixed crisis text, for a crisis verdict only. The route sends it after the sent state.
    crisis_text: str | None
    # Whether the background summary should run now: a new case the guard did not call a crisis
    # and did screen.
    summary_due: bool


@dataclass(frozen=True, slots=True)
class QueueItem:
    id: UUID
    category: str
    person_id: UUID
    given_name: str
    family_name: str
    title: str
    location_name: str
    sent_at: datetime
    reply_by: date
    status: str
    status_changed_at: datetime
    # The safety check's fact, shown under the category. None on HR's own case, which hides it as
    # the opener's view does.
    crisis: bool | None
    # HR's own case: listed with no actions.
    is_own: bool


@dataclass(frozen=True, slots=True)
class QueuePage:
    items: tuple[QueueItem, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class Counts:
    new: int
    reply_due: int


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    kind: str
    occurred_at: datetime
    actor_person_id: UUID | None
    actor_given_name: str | None
    actor_family_name: str | None
    from_status: str | None
    to_status: str | None


@dataclass(frozen=True, slots=True)
class SummaryState:
    status: Literal["none", "written", "failed"]
    reason: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CaseDetail:
    """The metadata HR's detail page shows. No words and no summary text. For HR's own case the
    person, the summary, and the timeline are left out."""

    id: UUID
    category: str
    status: str
    sent_at: datetime
    reply_by: date
    status_changed_at: datetime
    # None on HR's own case.
    screening: str | None
    is_own: bool
    person_id: UUID
    given_name: str | None
    family_name: str | None
    title: str | None
    department_name: str | None
    location_name: str | None
    work_email: str | None
    summary: SummaryState | None
    timeline: tuple[TimelineEntry, ...] | None


@dataclass(frozen=True, slots=True)
class SummaryRead:
    status: Literal["none", "written", "failed"]
    text: str | None = field(default=None, repr=False)
    reason: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SummaryWritten:
    text: str = field(repr=False)
    model: str
    prompt_version: str


@dataclass(frozen=True, slots=True)
class SummaryFailed:
    reason: SummaryFailure


type SummaryResult = SummaryWritten | SummaryFailed
