"""Time off over HTTP: balances, requests, the date picker's marks, the form's check, and the
Approvals page's queue.

Every route needs a session, and a route that writes also needs the CSRF header (both are the
session dependency's job). Errors are problem details. The service does the work and the policy
layer decides who may act; this module maps a refusal to a status:

| Refusal code                                                          | Status |
|-----------------------------------------------------------------------|--------|
| `not-found` (can't read it, or there is none)                         | 404    |
| `not-allowed` (can read it, may not do this to it)                    | 403    |
| `status-changed`, `already-started` (with the request's current status) | 409    |
| the engine's codes (`not-enough`, `overlaps`, ...)                    | 422    |

It doesn't use `authorize()`: that answers 403 where a request someone can't read must look the
same as one that doesn't exist, a 404. The code is the problem's `type`, and its `detail` is the
fixed sentence from `texts.py`.

"Now" is the server's clock, passed into the service. Today is always the date at the request
person's location, never the sandbox's anchor date.
"""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.deps import Now
from app.api.problems import problem_responses
from app.core.problems import ProblemError
from app.domain.timeoff.evaluate import NewRequest, request_bounds
from app.domain.timeoff.labels import label
from app.domain.timeoff.today import today_at
from app.modules.identity.deps import SignedIn, SignedInDep
from app.modules.identity.security_log import SecurityEvent, log_security_event
from app.modules.timeoff import queries, service
from app.modules.timeoff.coverage import CoverageEntry, CoverageRequest, team_coverage
from app.modules.timeoff.schemas import (
    BalancesOut,
    CalendarOut,
    CheckOut,
    DecisionBody,
    EarliestStart,
    HolidayOut,
    NameOut,
    PossibleRequest,
    RequestList,
    RequestOut,
    SummaryOut,
)
from app.modules.timeoff.service import Refused
from app.modules.timeoff.texts import refusal_text
from app.policy import Action, can

router = APIRouter(prefix="/time-off", tags=["time-off"])

MAX_ROWS = 200
DEFAULT_DAYS_BACK = 30
DEFAULT_DAYS_AHEAD = 120

_STATUS_FOR_CODE = {
    "not-found": status.HTTP_404_NOT_FOUND,
    "not-allowed": status.HTTP_403_FORBIDDEN,
    "status-changed": status.HTTP_409_CONFLICT,
    "already-started": status.HTTP_409_CONFLICT,
}
_NOT_ALLOWED_REASON = {"decision": "timeoff.decide", "cancel": "timeoff.cancel"}

READ_ERRORS = problem_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_422_UNPROCESSABLE_CONTENT,
)
ONE_ERRORS = problem_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_422_UNPROCESSABLE_CONTENT,
)
WRITE_ERRORS = problem_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_409_CONFLICT,
    status.HTTP_422_UNPROCESSABLE_CONTENT,
)
CHECK_ERRORS = problem_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN,
    status.HTTP_422_UNPROCESSABLE_CONTENT,
)


def _not_found() -> ProblemError:
    """The 404 for a request or person the actor can't read, or that doesn't exist."""
    return ProblemError(status.HTTP_404_NOT_FOUND, "not-found", refusal_text("not-found"))


async def _refusal(
    signed_in: SignedIn,
    request: Request,
    refused: Refused,
    request_id: UUID | None,
    operation: str,
) -> ProblemError:
    """The problem for a refusal: its status, its code as the `type`, and its fixed sentence."""
    code = refused.code
    status_code = _STATUS_FOR_CODE.get(code, status.HTTP_422_UNPROCESSABLE_CONTENT)
    extra: dict[str, object] = {}
    if status_code == status.HTTP_409_CONFLICT and request_id is not None:
        # Read in the same transaction, which still holds the person's lock, so it is the status
        # the refusal was decided on.
        stored = await queries.load_stored_request(
            signed_in.db, signed_in.actor.tenant_id, request_id
        )
        if stored is not None:
            extra["currentStatus"] = stored.status
    if code == "not-allowed":
        log_security_event(
            SecurityEvent.AUTHZ_DENIED,
            request,
            _NOT_ALLOWED_REASON.get(operation, "timeoff.request"),
            tenant_id=signed_in.actor.tenant_id,
            actor_id=signed_in.actor.person_id,
            target_id=request_id,
        )
    return ProblemError(status_code, code, refusal_text(code), extra)


async def _one(
    signed_in: SignedIn, request_id: UUID, stored: queries.StoredRequest | None = None
) -> queries.RequestRow:
    """The request as the actor sees it. A caller that has just read the stored request passes it,
    so it is read once."""
    if stored is None:
        stored = await queries.load_stored_request(
            signed_in.db, signed_in.actor.tenant_id, request_id
        )
    rows = await queries.load_request_rows(
        signed_in.db,
        signed_in.actor.tenant_id,
        person_ids=[stored.person_id] if stored else [],
        request_id=request_id,
    )
    if not rows:
        raise _not_found()
    return rows[0]


async def _managed_view(
    signed_in: SignedIn, rows: Sequence[queries.RequestRow], now: datetime
) -> list[RequestOut]:
    """Each row as the actor's page shows it. A direct manager's view of a request also carries
    the person's available PTO and team coverage; nobody else's does."""
    actor = signed_in.actor
    # Only a direct manager's view needs the person's facts, and both the coverage and the balance
    # use them, so each person's are read once here.
    facts = {
        person_id: await queries.load_facts(signed_in.db, actor.tenant_id, person_id)
        for person_id in dict.fromkeys(
            row.person_id for row in rows if row.person_id in actor.direct_report_ids
        )
    }
    coverage = await team_coverage(
        signed_in.db,
        actor,
        [CoverageRequest(row.id, row.person_id, row.start_date, row.end_date) for row in rows],
        facts=facts,
    )
    available: dict[UUID, int | None] = {}
    out: list[RequestOut] = []
    for row in rows:
        entries: tuple[CoverageEntry, ...] | None = coverage.get(row.id)
        after = None
        # Only a request still waiting is already subtracted from what is available, so "after"
        # means nothing for a decided or canceled one.
        if entries is not None and row.type == "pto" and row.status == "pending":
            if row.person_id not in available:
                available[row.person_id] = await service.pto_available_minutes(
                    signed_in.db, actor, row.person_id, now, facts=facts.get(row.person_id)
                )
            after = available[row.person_id]
        out.append(RequestOut.of(row, available_after_minutes=after, coverage=entries))
    return out


def _window(first: date | None, last: date | None, today: date) -> tuple[date, date]:
    start = first if first is not None else today - timedelta(days=DEFAULT_DAYS_BACK)
    end = last if last is not None else today + timedelta(days=DEFAULT_DAYS_AHEAD)
    if end < start:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The window can't end before it starts."
        )
    return start, end


@router.get(
    "/balances",
    operation_id="getTimeOffBalances",
    summary="PTO and sick balances for yourself or a person you may read",
    response_model=BalancesOut,
    responses=ONE_ERRORS,
)
async def get_balances(
    signed_in: SignedInDep,
    request: Request,
    now: Now,
    person: Annotated[UUID | None, Query()] = None,
) -> BalancesOut:
    actor = signed_in.actor
    result = await service.balances(signed_in.db, actor, person or actor.person_id, now)
    if isinstance(result, Refused):
        raise await _refusal(signed_in, request, result, None, "balances")
    return BalancesOut.of(result)


@router.get(
    "/requests",
    operation_id="listTimeOffRequests",
    summary="Time-off requests: your own, everyone below you, or what waits for your decision",
    response_model=RequestList,
    responses=READ_ERRORS,
)
async def list_requests(
    signed_in: SignedInDep,
    now: Now,
    scope: Annotated[Literal["mine", "team", "waiting"], Query()] = "mine",
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
) -> RequestList:
    actor = signed_in.actor
    zone = await queries.timezone_of(signed_in.db, actor.tenant_id, actor.person_id)
    if zone is None:
        raise _not_found()
    first, last = _window(from_date, to_date, today_at(zone, now))
    people = {
        "mine": frozenset({actor.person_id}),
        "team": actor.report_ids,
        "waiting": actor.direct_report_ids,
    }[scope]
    rows = (
        await queries.load_request_rows(
            signed_in.db,
            actor.tenant_id,
            person_ids=people,
            # What waits for a decision is shown whenever its days fall: it still needs deciding.
            overlapping=None if scope == "waiting" else (first, last),
            pending_pto_only=scope == "waiting",
            limit=MAX_ROWS,
        )
        if people
        else []
    )
    # The people were chosen by the policy's own sets; asking it for each row is a second guard.
    readable = [
        row for row in rows if can(actor, Action.TIMEOFF_READ, service.request_resource(row))
    ]
    items = (
        await _managed_view(signed_in, readable, now)
        if scope == "waiting"
        else [RequestOut.of(row) for row in readable]
    )
    return RequestList(items=items, from_date=first, to_date=last)


@router.get(
    "/requests/{request_id}",
    operation_id="getTimeOffRequest",
    summary="One request, for a person who may read it",
    response_model=RequestOut,
    responses=ONE_ERRORS,
)
async def get_request(request_id: UUID, signed_in: SignedInDep, now: Now) -> RequestOut:
    actor = signed_in.actor
    stored = await queries.load_stored_request(signed_in.db, actor.tenant_id, request_id)
    if stored is None or not can(actor, Action.TIMEOFF_READ, service.request_resource(stored)):
        raise _not_found()
    row = await _one(signed_in, request_id, stored)
    [view] = await _managed_view(signed_in, [row], now)
    return view


@router.get(
    "/calendar",
    operation_id="getTimeOffCalendar",
    summary="The date picker's marks for you: your weekdays, holidays, and the earliest days",
    response_model=CalendarOut,
    responses=READ_ERRORS,
)
async def get_calendar(
    signed_in: SignedInDep,
    now: Now,
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
) -> CalendarOut:
    if to_date < from_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The window can't end before it starts."
        )
    actor = signed_in.actor
    facts = await queries.load_facts(signed_in.db, actor.tenant_id, actor.person_id)
    if facts is None:
        raise _not_found()
    bounds = request_bounds(facts.person, facts.opening, today_at(facts.timezone, now))
    return CalendarOut(
        scheduled_weekdays=sorted(facts.person.schedule.weekdays),
        holidays=[
            HolidayOut(day=day, name=name)
            for day, name in sorted(facts.holidays.items())
            if from_date <= day <= to_date
        ],
        earliest_start=EarliestStart(
            pto=bounds.earliest_pto_start, sick=bounds.earliest_sick_start
        ),
        latest_end=bounds.latest_end,
    )


@router.post(
    "/check",
    operation_id="checkTimeOffRequest",
    summary="What a possible request of yours would count, with nothing written",
    response_model=CheckOut,
    responses=CHECK_ERRORS,
)
async def check_request(body: PossibleRequest, signed_in: SignedInDep, now: Now) -> CheckOut:
    answer = await service.preview(signed_in.db, signed_in.actor, _new(body), now)
    return CheckOut.of(answer)


@router.post(
    "/requests",
    operation_id="createTimeOffRequest",
    summary="Make a time-off request of your own: PTO waits for a decision, sick time is recorded",
    status_code=status.HTTP_201_CREATED,
    response_model=RequestOut,
    responses=CHECK_ERRORS | problem_responses(status.HTTP_409_CONFLICT),
)
async def create_request(
    body: PossibleRequest, signed_in: SignedInDep, request: Request, now: Now
) -> RequestOut:
    result = await service.create(signed_in.db, signed_in.actor, _new(body), now, via="ui")
    if isinstance(result, Refused):
        raise await _refusal(signed_in, request, result, None, "create")
    return RequestOut.of(await _one(signed_in, result.request_id))


@router.post(
    "/requests/{request_id}/decision",
    operation_id="decideTimeOffRequest",
    summary="Approve or deny a PTO request as the person's direct manager",
    response_model=RequestOut,
    responses=WRITE_ERRORS,
)
async def decide_request(
    request_id: UUID, body: DecisionBody, signed_in: SignedInDep, request: Request, now: Now
) -> RequestOut:
    result = await service.decide(
        signed_in.db, signed_in.actor, request_id, body.decision, body.note, now, via="ui"
    )
    if isinstance(result, Refused):
        raise await _refusal(signed_in, request, result, request_id, "decision")
    return RequestOut.of(await _one(signed_in, request_id))


@router.post(
    "/requests/{request_id}/cancel",
    operation_id="cancelTimeOffRequest",
    summary="Cancel your own request",
    response_model=RequestOut,
    responses=WRITE_ERRORS,
)
async def cancel_request(
    request_id: UUID, signed_in: SignedInDep, request: Request, now: Now
) -> RequestOut:
    result = await service.cancel(signed_in.db, signed_in.actor, request_id, now, via="ui")
    if isinstance(result, Refused):
        raise await _refusal(signed_in, request, result, request_id, "cancel")
    return RequestOut.of(await _one(signed_in, request_id))


@router.get(
    "/summary",
    operation_id="getTimeOffSummary",
    summary="Your PTO available, your pending requests, your approver, and what waits for you",
    response_model=SummaryOut,
    responses=problem_responses(status.HTTP_401_UNAUTHORIZED, status.HTTP_404_NOT_FOUND),
)
async def get_summary(signed_in: SignedInDep, now: Now) -> SummaryOut:
    db, actor = signed_in.db, signed_in.actor
    available = await service.pto_available_minutes(db, actor, actor.person_id, now)
    if available is None:
        raise _not_found()
    manager = await queries.manager_name(db, actor.tenant_id, actor.person_id)
    waiting = (
        await queries.count_requests(
            db, actor.tenant_id, actor.direct_report_ids, status="pending", type_="pto"
        )
        if actor.direct_report_ids
        else None
    )
    return SummaryOut(
        pto_available_minutes=available,
        pto_available_label=label(available),
        pending_count=await queries.count_requests(
            db, actor.tenant_id, [actor.person_id], status="pending"
        ),
        approver=None if manager is None else NameOut(name=manager),
        waiting_count=waiting,
    )


def _new(body: PossibleRequest) -> NewRequest:
    return NewRequest(body.type, body.start_date, body.end_date, body.partial_minutes)
