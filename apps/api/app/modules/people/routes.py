"""The directory, and a person's private details.

Each route asks the policy layer before it reads, so a refusal never depends on whether the person
exists. Row-level security then keeps every query inside the actor's tenant, so a person from
another sandbox is simply not found: a 404, the same as an ID that doesn't exist.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import AfterValidator, StringConstraints

from app.api.problems import problem_responses
from app.modules.audit.service import record_event
from app.modules.identity.deps import AuditedReadDep, SignedInDep, authorize
from app.modules.people.queries import (
    DirectoryCursor,
    DirectoryFilters,
    directory_facets,
    get_card,
    get_private_details,
    list_directory,
)
from app.modules.people.schemas import (
    DirectoryCard,
    DirectoryFacets,
    DirectoryPage,
    PrivateDetails,
)
from app.policy import Action, PersonResource, can

router = APIRouter(prefix="/people", tags=["people"])


def _no_nul(value: str | None) -> str | None:
    # Postgres text can't hold NUL, so it would be a 500 at the query. Refuse it as a 422, as the
    # cursor does.
    if value is not None and "\x00" in value:
        raise ValueError("The search can't contain a NUL character.")
    return value


NOT_FOUND = "No such person in this company."

# A directory read needs a session (401) and is checked for input (422). A read of one person can
# also be refused by the policy (403) or find no one (404).
LIST_ERRORS = problem_responses(status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_CONTENT)
PERSON_ERRORS = problem_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_422_UNPROCESSABLE_CONTENT,
)


def directory_filters(
    signed_in: SignedInDep,
    # Trimmed before the length check, so spaces around a 100-character search are fine. Blank
    # means no search.
    q: Annotated[
        str | None,
        Query(),
        StringConstraints(strip_whitespace=True, max_length=100),
        AfterValidator(_no_nul),
    ] = None,
    location_id: Annotated[UUID | None, Query(alias="locationId")] = None,
    department_id: Annotated[UUID | None, Query(alias="departmentId")] = None,
    team: Annotated[Literal["mine"] | None, Query()] = None,
) -> DirectoryFilters:
    """The directory's filters, from the query string. Shared by the list and its counts.

    `team=mine` is the actor's own reports, as the server loaded them for this request. For
    someone with no reports it matches no one, and it is never an error.
    """
    return DirectoryFilters(
        q=q or None,
        location_id=location_id,
        department_id=department_id,
        team=signed_in.actor.report_ids if team == "mine" else None,
    )


DirectoryFiltersDep = Annotated[DirectoryFilters, Depends(directory_filters)]


@router.get(
    "",
    operation_id="listPeople",
    summary="The company directory, a page at a time",
    response_model=DirectoryPage,
    responses=LIST_ERRORS,
)
async def list_people(
    signed_in: SignedInDep,
    filters: DirectoryFiltersDep,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DirectoryPage:
    try:
        after = None if cursor is None else DirectoryCursor.decode(cursor)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The cursor is not one this API issued."
        ) from None
    page = await list_directory(signed_in.db, limit=limit, after=after, filters=filters)
    actor = signed_in.actor
    return DirectoryPage(
        items=[
            card
            for card in page.cards
            if can(actor, Action.DIRECTORY_READ, PersonResource(card.id))
        ],
        next_cursor=None if page.next_cursor is None else page.next_cursor.encode(),
    )


# Declared before "/{person_id}", or "facets" would be read as a person ID.
@router.get(
    "/facets",
    operation_id="getDirectoryFacets",
    summary="The directory's counts: the header's, and each filter option's",
    response_model=DirectoryFacets,
    responses=LIST_ERRORS,
)
async def get_directory_facets(
    signed_in: SignedInDep, filters: DirectoryFiltersDep
) -> DirectoryFacets:
    # These counts skip the per-row can() check that the list makes. That is safe while
    # DIRECTORY_READ allows everyone in the tenant. The backlog item "Keep the directory cursor
    # and the facet counts from naming a hidden person" (docs/BACKLOG.md) covers the phase that
    # first restricts it.
    return await directory_facets(
        signed_in.db, filters=filters, team_ids=signed_in.actor.report_ids
    )


@router.get(
    "/{person_id}",
    operation_id="getPerson",
    summary="One person's directory card",
    response_model=DirectoryCard,
    responses=PERSON_ERRORS,
)
async def get_person(person_id: UUID, signed_in: SignedInDep, request: Request) -> DirectoryCard:
    authorize(request, signed_in, Action.DIRECTORY_READ, PersonResource(person_id))
    card = await get_card(signed_in.db, person_id)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return card


@router.get(
    "/{person_id}/private",
    operation_id="getPersonPrivate",
    summary="One person's private details, for that person and for HR. Each read is audited.",
    response_model=PrivateDetails,
    responses=PERSON_ERRORS,
    dependencies=[AuditedReadDep],
)
async def get_person_private(
    person_id: UUID, signed_in: SignedInDep, request: Request
) -> PrivateDetails:
    authorize(request, signed_in, Action.PERSON_PRIVATE_READ, PersonResource(person_id))
    details = await get_private_details(signed_in.db, person_id)
    if details is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    await record_event(
        signed_in.db,
        tenant_id=signed_in.actor.tenant_id,
        actor_id=signed_in.actor.person_id,
        action="person_private.read",
        target_type="person",
        target_id=person_id,
        # The names of the fields returned, never their values.
        after={"fields": sorted(details.model_dump(by_alias=True))},
    )
    return details
