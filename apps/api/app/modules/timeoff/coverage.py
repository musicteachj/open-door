"""Team coverage: who else on a manager's team is off on the days a request would take.

For a request R by person P, whose direct manager M is the viewer, it lists M's OTHER direct
reports with approved or recorded time off (a request still waiting isn't time off, and a denied
or canceled one never was) on any of R's counted days: P's scheduled weekdays, less the company
holidays at P's location. A colleague's time off counts only on days that are also counted for them
(their own schedule and holidays). One entry per colleague, with the days they overlap and the type
of each.

It is context only: plain data that nothing ranks or recommends (invariant 5). It is shown on the
card and the page, never sent to the model and never written to an audit event. Only the person's
direct manager gets it, so a skip-level manager, HR, and the person see none.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.timeoff.counting import count_days
from app.modules.timeoff import queries
from app.policy import Actor


@dataclass(frozen=True, slots=True)
class CoverageRequest:
    """The part of a request coverage needs: whose it is, and its dates."""

    id: UUID
    person_id: UUID
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class CoverageDay:
    day: date
    type: str  # "pto" or "sick"
    # Null for a whole day; 240 for half a day of PTO, or whole hours of sick time.
    partial_minutes: int | None


@dataclass(frozen=True, slots=True)
class CoverageEntry:
    """One colleague, with each of the request's days they are off and what kind."""

    person_id: UUID
    person_name: str
    days: tuple[CoverageDay, ...]  # in date order, never empty


async def team_coverage(
    db: AsyncSession,
    actor: Actor,
    requests: Iterable[CoverageRequest],
    *,
    facts: Mapping[UUID, queries.PersonFacts | None] | None = None,
) -> dict[UUID, tuple[CoverageEntry, ...]]:
    """The coverage of each request whose person reports directly to the actor, by request ID.

    A request of anyone else is not in the answer at all (not an empty entry, which would read as
    "no one is off"). One query reads the colleagues' time off for every request together; the
    facts of each person (the requesters, and each colleague who has time off in range) are read
    once, one query per person, so a caller passes the few that wait, not a page.
    """
    mine = [request for request in requests if request.person_id in actor.direct_report_ids]
    if not mine:
        return {}
    off = await queries.load_time_off(
        db,
        actor.tenant_id,
        actor.direct_report_ids,
        min(request.start_date for request in mine),
        max(request.end_date for request in mine),
    )
    found: dict[UUID, tuple[CoverageEntry, ...]] = {}
    # A caller that has read the people's facts already passes them, so they are read once.
    known: dict[UUID, queries.PersonFacts | None] = dict(facts or {})
    # Each time-off row's own counted days, once: the days that row is time off for its person
    # (their schedule and holidays). None when their facts can't be read, which falls back to the
    # plain date range.
    theirs: list[set[date] | None] = []
    for time_off in off:
        if time_off.person_id not in known:
            known[time_off.person_id] = await queries.load_facts(
                db, actor.tenant_id, time_off.person_id
            )
        colleague = known[time_off.person_id]
        theirs.append(
            None
            if colleague is None
            else set(
                count_days(
                    colleague.person, time_off.start_date, time_off.end_date, colleague.holidays
                ).counted
            )
        )
    for request in mine:
        if request.person_id not in known:
            known[request.person_id] = await queries.load_facts(
                db, actor.tenant_id, request.person_id
            )
        person_facts = known[request.person_id]
        if person_facts is None:
            continue
        counted = count_days(
            person_facts.person, request.start_date, request.end_date, person_facts.holidays
        ).counted
        days_by_colleague: dict[tuple[UUID, str], dict[date, tuple[str, int | None]]] = {}
        for time_off, own_days in zip(off, theirs, strict=True):
            if time_off.person_id == request.person_id:
                continue
            days = days_by_colleague.setdefault((time_off.person_id, time_off.person_name), {})
            for day in counted:
                if (
                    day in own_days
                    if own_days is not None
                    else time_off.start_date <= day <= time_off.end_date
                ):
                    days[day] = (time_off.type, time_off.partial_minutes)
        found[request.id] = tuple(
            CoverageEntry(
                person_id,
                name,
                tuple(CoverageDay(day, *days[day]) for day in sorted(days)),
            )
            for (person_id, name), days in days_by_colleague.items()
            if days
        )
    return found
