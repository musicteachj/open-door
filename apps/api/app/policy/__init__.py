"""Who may do what: one pure function that every route asks before it reads or acts.

Pure, like app.domain: no framework or database imports, which import-linter enforces (see
`[tool.importlinter]` in pyproject.toml). Deny by default: an action without a rule is refused.

Tenant scope isn't a rule here. Row-level security already keeps every target inside the actor's
tenant, so a person from another tenant never reaches this function.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID


def _require(value: object, expected: type, name: str) -> None:
    """Raise a TypeError unless `value` really is an `expected`, so a look-alike can't pass."""
    if not isinstance(value, expected):
        raise TypeError(f"{name} must be a {expected.__name__}, not {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class Actor:
    """The signed-in person. Every field comes from the server session and the database."""

    person_id: UUID
    tenant_id: UUID
    is_hr_admin: bool
    # Direct and indirect reports, computed fresh for every request and never cached.
    report_ids: frozenset[UUID]
    # The people who report straight to this person: a subset of `report_ids`. Deciding a request
    # needs the direct manager, so a manager two levels up reads a request but doesn't decide it.
    direct_report_ids: frozenset[UUID]

    def __post_init__(self) -> None:
        # Python doesn't check annotations at runtime. A truthy string in `is_hr_admin`, for
        # example "false", would read as an HR administrator, so a wrong type fails loudly here.
        _require(self.person_id, UUID, "person_id")
        _require(self.tenant_id, UUID, "tenant_id")
        _require(self.is_hr_admin, bool, "is_hr_admin")
        _require(self.report_ids, frozenset, "report_ids")
        _require(self.direct_report_ids, frozenset, "direct_report_ids")
        if not self.direct_report_ids <= self.report_ids:
            msg = "direct_report_ids must be a subset of report_ids"
            raise ValueError(msg)

    @property
    def is_manager(self) -> bool:
        """Being a manager is derived from having reports, never stored."""
        return bool(self.report_ids)


class Action(StrEnum):
    DIRECTORY_READ = "directory.read"
    PERSON_PRIVATE_READ = "person_private.read"
    TIMEOFF_READ = "timeoff.read"
    TIMEOFF_REQUEST = "timeoff.request"
    TIMEOFF_DECIDE = "timeoff.decide"
    TIMEOFF_CANCEL = "timeoff.cancel"
    CASE_OPEN = "case.open"
    CASE_READ_STATUS = "case.read_status"
    CASE_LIST = "case.list"
    CASE_READ_SUMMARY = "case.read_summary"
    CASE_READ_TEXT = "case.read_text"
    CASE_UPDATE_STATUS = "case.update_status"


@dataclass(frozen=True, slots=True)
class PersonResource:
    """The person an action is aimed at."""

    person_id: UUID

    def __post_init__(self) -> None:
        _require(self.person_id, UUID, "person_id")


@dataclass(frozen=True, slots=True)
class TimeOffRequestResource:
    """A time-off request, as far as a permission needs it: whose it is, what kind, where it
    stands, and its first day. The decide and cancel rules read all four."""

    person_id: UUID
    type: str  # "pto" or "sick"; an unknown value simply matches no rule
    status: str
    start_date: date

    def __post_init__(self) -> None:
        _require(self.person_id, UUID, "person_id")
        _require(self.type, str, "type")
        _require(self.status, str, "status")
        _require_date(self.start_date, "start_date")


@dataclass(frozen=True, slots=True)
class CaseResource:
    """A case, as far as a permission needs it: who opened it, where it stands, and whether this
    actor has read its words (the caller looks up the actor's own `text_read` event)."""

    person_id: UUID
    status: str
    words_read_by_actor: bool

    def __post_init__(self) -> None:
        _require(self.person_id, UUID, "person_id")
        _require(self.status, str, "status")
        _require(self.words_read_by_actor, bool, "words_read_by_actor")


def _require_date(value: object, name: str) -> None:
    """A calendar date. A datetime is a date too, but comparing the two raises, so it is refused."""
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError(f"{name} must be a date, not {type(value).__name__}")


type Resource = PersonResource | TimeOffRequestResource | CaseResource
# A rule gets the actor, the resource, and today's date at the person's location (None when the
# caller has none). It must return exactly True to grant.
type Rule = Callable[[Actor, Resource, date | None], bool]


def _anyone_in_the_company(actor: Actor, target: Resource, today: date | None) -> bool:
    return isinstance(target, PersonResource)


def _themselves_or_hr(actor: Actor, target: Resource, today: date | None) -> bool:
    if not isinstance(target, PersonResource):
        return False
    # A manager gets nothing extra: their reports' private details are not theirs to read.
    return target.person_id == actor.person_id or actor.is_hr_admin


def _timeoff_read(actor: Actor, target: Resource, today: date | None) -> bool:
    # A person, or one of their requests: either way it is the person that counts.
    if not isinstance(target, PersonResource | TimeOffRequestResource):
        return False
    return (
        target.person_id == actor.person_id
        or target.person_id in actor.report_ids
        or actor.is_hr_admin
    )


def _timeoff_request(actor: Actor, target: Resource, today: date | None) -> bool:
    return isinstance(target, PersonResource) and target.person_id == actor.person_id


def _timeoff_decide(actor: Actor, target: Resource, today: date | None) -> bool:
    # Only the direct manager, never on one's own request. HR and managers further up read, and
    # don't decide. Sick time is recorded, never decided.
    return (
        isinstance(target, TimeOffRequestResource)
        and target.person_id != actor.person_id
        and target.person_id in actor.direct_report_ids
        and target.type == "pto"
        and target.status == "pending"
    )


def _timeoff_cancel(actor: Actor, target: Resource, today: date | None) -> bool:
    if (
        not isinstance(target, TimeOffRequestResource)
        or today is None
        or target.person_id != actor.person_id
    ):
        return False
    if target.status == "pending":
        return True
    # Approved or recorded: only before its first day, so the day before yes, on it no.
    return target.status in {"approved", "recorded"} and today < target.start_date


def _case_open(actor: Actor, target: Resource, today: date | None) -> bool:
    # Anyone opens a case, for themselves. HR is no exception, and no one opens one for another.
    return isinstance(target, PersonResource) and target.person_id == actor.person_id


def _case_read_status(actor: Actor, target: Resource, today: date | None) -> bool:
    # The person who opened it, or HR. A manager gets nothing: a report's case is not theirs.
    return isinstance(target, CaseResource) and (
        target.person_id == actor.person_id or actor.is_hr_admin
    )


def _case_list(actor: Actor, target: Resource, today: date | None) -> bool:
    # The queue is HR's. It has no case of its own to name, so it takes the actor as a person.
    return isinstance(target, PersonResource) and actor.is_hr_admin


def _case_hr_not_own(actor: Actor, target: Resource, today: date | None) -> bool:
    # HR reads the summary and the words of anyone's case but their own.
    return (
        isinstance(target, CaseResource)
        and actor.is_hr_admin
        and target.person_id != actor.person_id
    )


def _case_update_status(actor: Actor, target: Resource, today: date | None) -> bool:
    # HR, never on their own case, and only after reading its words: a status never moves on the
    # AI's summary alone.
    # The isinstance is for mypy's narrowing: `_case_hr_not_own` has already refused any other type.
    return _case_hr_not_own(actor, target, today) and (
        isinstance(target, CaseResource) and target.words_read_by_actor
    )


RULES: Mapping[Action, Rule] = MappingProxyType(
    {
        Action.DIRECTORY_READ: _anyone_in_the_company,
        Action.PERSON_PRIVATE_READ: _themselves_or_hr,
        Action.TIMEOFF_READ: _timeoff_read,
        Action.TIMEOFF_REQUEST: _timeoff_request,
        Action.TIMEOFF_DECIDE: _timeoff_decide,
        Action.TIMEOFF_CANCEL: _timeoff_cancel,
        Action.CASE_OPEN: _case_open,
        Action.CASE_READ_STATUS: _case_read_status,
        Action.CASE_LIST: _case_list,
        Action.CASE_READ_SUMMARY: _case_hr_not_own,
        Action.CASE_READ_TEXT: _case_hr_not_own,
        Action.CASE_UPDATE_STATUS: _case_update_status,
    }
)


def can(actor: Actor, action: Action, target: Resource, *, today: date | None = None) -> bool:
    """Whether `actor` may perform `action` on `target`. An action without a rule is denied.

    `today` is the date at the request person's location, which only the cancel rule reads. It is
    a plain date, never a datetime. Always a real bool: only a rule that returns exactly True
    grants access.
    """
    if today is not None:
        _require_date(today, "today")
    rule = RULES.get(action)
    return rule is not None and rule(actor, target, today) is True
