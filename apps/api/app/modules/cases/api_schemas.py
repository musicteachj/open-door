"""What the case routes take and send, in JSON (camelCase).

The service's dataclasses (`schemas.py`) map onto these by attribute. A case's words and summary
text appear only in `CaseTextOut` and `CaseSummaryOut`, which two audited reads send.
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.api.schemas import CamelModel
from app.modules.cases.schemas import Category, Status

# Like the assistant's question limit: far above the 4,000 the service allows.
MAX_BODY_CHARACTERS = 20_000


class OpenCaseBody(CamelModel):
    submission_id: UUID
    category: Category
    # Far above the service's limit, so its "too long" problem answers; this bounds the body.
    text: str = Field(repr=False, max_length=MAX_BODY_CHARACTERS)
    turn_id: UUID | None = None


class StatusBody(CamelModel):
    to: Status


class CaseStatusOut(CamelModel):
    """What the person who opened a case sees: no words, no screening label."""

    id: UUID
    category: Category
    status: Status
    sent_at: datetime
    reply_by: date
    status_changed_at: datetime


class CaseSentOut(CamelModel):
    case: CaseStatusOut
    # False when the submission already had a case: the same case comes back.
    created: bool
    # The fixed crisis text, for a crisis verdict only.
    crisis_text: str | None


class CaseListOut(CamelModel):
    items: list[CaseStatusOut]


class CaseTextsOut(CamelModel):
    """The form's fixed bullets, with today's reply-by date filled in."""

    bullets: list[str]
    reply_by: date


class CountsOut(CamelModel):
    new: int
    reply_due: int


class QueueItemOut(CamelModel):
    id: UUID
    category: Category
    person_id: UUID
    given_name: str
    family_name: str
    title: str
    location_name: str
    sent_at: datetime
    reply_by: date
    status: Status
    status_changed_at: datetime
    # The safety check's fact. Null on HR's own case.
    crisis: bool | None
    is_own: bool


class QueuePageOut(CamelModel):
    items: list[QueueItemOut]
    next_cursor: str | None


class TimelineEntryOut(CamelModel):
    kind: str
    occurred_at: datetime
    actor_person_id: UUID | None
    actor_given_name: str | None
    actor_family_name: str | None
    from_status: Status | None
    to_status: Status | None


class SummaryStateOut(CamelModel):
    status: Literal["none", "written", "failed"]
    reason: str | None = None
    created_at: datetime | None = None


class SummaryRetryOut(CamelModel):
    """The retry's answer: the summary is being written.

    Refused with a 409 when the newest summary was written or is a crisis note, or when the case
    is under 2 minutes old with no summary.
    """

    status: Literal["writing"]


class CaseDetailOut(CamelModel):
    """The detail page's metadata. No words and no summary text."""

    id: UUID
    category: Category
    status: Status
    sent_at: datetime
    reply_by: date
    status_changed_at: datetime
    screening: str | None
    is_own: bool
    person_id: UUID
    given_name: str | None
    family_name: str | None
    title: str | None
    department_name: str | None
    location_name: str | None
    work_email: str | None
    summary: SummaryStateOut | None
    timeline: list[TimelineEntryOut] | None


class CaseSummaryOut(CamelModel):
    status: Literal["none", "written", "failed"]
    text: str | None = Field(default=None, repr=False)
    reason: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    created_at: datetime | None = None


class CaseTextOut(CamelModel):
    text: str = Field(repr=False)
