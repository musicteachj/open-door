"""What the API shows of a person. Each tier is its own model, so a field can't leak between them.

- `DirectoryCard` is what anyone in the company may see.
- `Me` adds what only the signed-in person sees about themselves.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from app.api.schemas import CamelModel

type PersonaKey = Literal["priya", "mateo", "marcus", "dana"]


class DepartmentRef(CamelModel):
    id: UUID
    name: str


class LocationRef(CamelModel):
    id: UUID
    name: str
    state: str


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


class Me(DirectoryCard):
    """The signed-in person's own card, with the fields only they see."""

    employment_type: Literal["salaried", "hourly"]
    is_manager: bool
    is_hr_admin: bool
    persona_key: PersonaKey
    tenant_expires_at: datetime
