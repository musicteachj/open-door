"""What the API shows of a person. Each tier is its own model, so a field can't leak between them.

- `DirectoryCard` is what anyone in the company may see.
- `Me` adds what only the signed-in person sees about themselves.
- `PrivateDetails` is visible only to the person themselves and to HR.
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from app.api.schemas import CamelModel

type PersonaKey = Literal["priya", "mateo", "marcus", "dana"]


class DepartmentRef(CamelModel):
    id: UUID
    name: str


class LocationRef(CamelModel):
    id: UUID
    # The handbook's name for the place ("oak", "den", "aus", "atl"), which its audiences use.
    code: str
    name: str
    state: str
    # An IANA zone, such as "America/Denver". Not personal: it describes the place, not the person.
    timezone: str


class PersonRef(CamelModel):
    id: UUID
    given_name: str
    family_name: str


class DirectoryCard(CamelModel):
    id: UUID
    given_name: str
    family_name: str
    title: str
    department: DepartmentRef
    location: LocationRef
    manager: PersonRef | None
    work_email: str


class DirectoryPage(CamelModel):
    items: list[DirectoryCard]
    # Pass it back as `cursor` for the next page. Null on the last page.
    next_cursor: str | None


class LocationCount(CamelModel):
    id: UUID
    name: str
    state: str
    count: int


class DepartmentCount(CamelModel):
    id: UUID
    name: str
    count: int


class DirectoryFacets(CamelModel):
    """The counts behind the directory's header and filter menus.

    An option's count is how many people the list would show if that option were chosen, with
    every other active filter kept. Every location and department is listed, even at zero.
    """

    # Everyone in the company, whatever the filters.
    total: int
    # The people the list shows with every current filter applied.
    matching: int
    # Each menu is sorted by name.
    locations: list[LocationCount]
    departments: list[DepartmentCount]
    # How many the list would show with the team filter on, and the other filters kept. Null for
    # someone with no reports, so the web app can hide the toggle.
    my_team: int | None


class Me(DirectoryCard):
    """The signed-in person's own card, with the fields only they see."""

    employment_type: Literal["salaried", "hourly"]
    is_manager: bool
    is_hr_admin: bool
    persona_key: PersonaKey
    tenant_expires_at: datetime


class PrivateDetails(CamelModel):
    personal_email: str
    phone: str
    home_address: str
    date_of_birth: date
