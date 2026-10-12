"""The validated handbook: its sections, and who each applies to."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.domain.handbook.blocks import Block
from app.domain.handbook.source import SourceFile

EMPLOYMENT_TYPES = ("salaried", "hourly")


@dataclass(frozen=True, slots=True)
class Audience:
    """Who a section applies to. An empty list doesn't restrict."""

    states: tuple[str, ...] = ()
    employment_types: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()

    def to_json(self) -> dict[str, list[str]]:
        """The value for a section's `audience` column."""
        return {
            "states": list(self.states),
            "employmentTypes": list(self.employment_types),
            "locations": list(self.locations),
        }


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    title: str
    kind: Literal["company", "addendum"]
    # A company section has a chapter; an addendum has a state.
    chapter: int | None
    addendum_state: str | None
    # The chapter's name or the addendum's name, for the chunks' embedded text.
    group_name: str
    supplements: str | None
    updated: date
    audience: Audience
    sources: tuple[str, ...]
    blocks: tuple[Block, ...]
    path: str


@dataclass(frozen=True)
class Handbook:
    """A valid handbook. `sections` are in the handbook's order: company sections by number, then
    each state's addendum. `files` are the sources it was built from, for the content hash."""

    version: str
    title: str
    chapters: Mapping[int, str]
    addenda: Mapping[str, str]
    locations: Mapping[str, str]
    sections: tuple[Section, ...]
    files: tuple[SourceFile, ...]

    @property
    def updated_on(self) -> date:
        """The latest section's date: the "Handbook updated" figure."""
        return max(section.updated for section in self.sections)
