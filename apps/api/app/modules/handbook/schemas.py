"""What the handbook API shows. Every field is public to everyone in the sandbox: the handbook is
company-public, and `applies_to_me` says relevance, not permission."""

from datetime import date
from typing import Literal

from app.api.schemas import CamelModel


class AudienceOut(CamelModel):
    states: list[str]
    employment_types: list[str]
    locations: list[str]


class SectionSummary(CamelModel):
    """A section as the list, the search results, and the section and passage headers show it."""

    # The section key: "4.3" or "CA-4.3".
    id: str
    title: str
    kind: Literal["company", "addendum"]
    # A company section's chapter number; null for an addendum.
    chapter: int | None
    # An addendum's state code; null for a company section.
    addendum_state: str | None
    # The chapter's name or the addendum's ("Time off", "California addendum").
    group_name: str
    audience: AudienceOut
    # "Everyone", "California employees", "Hourly staff in California", "Denver HQ".
    audience_label: str
    # Worked out on the server from the signed-in person's location and employment type.
    applies_to_me: bool
    last_updated: date


class VersionInfo(CamelModel):
    label: str
    title: str
    # The latest section's date: the "Handbook updated" figure.
    updated_on: date


class HandbookOverview(CamelModel):
    version: VersionInfo
    # Chapter number (as text) to name, and state code to addendum name.
    chapters: dict[str, str]
    addenda: dict[str, str]
    # In the handbook's order: company sections by number, then each state's addendum.
    sections: list[SectionSummary]


class Inline(CamelModel):
    text: str
    bold: bool
    italic: bool
    # Set when the run is inside a link to another section of this handbook.
    link_section_id: str | None


class HeadingBlock(CamelModel):
    type: Literal["heading"]
    level: Literal[2, 3]
    text: str


class ParagraphPassage(CamelModel):
    type: Literal["passage"]
    id: str
    kind: Literal["paragraph"]
    inlines: list[Inline]


class ListPassage(CamelModel):
    type: Literal["passage"]
    id: str
    kind: Literal["list"]
    ordered: bool
    items: list[list[Inline]]


class SectionLink(CamelModel):
    """A neighbor in the handbook's order."""

    id: str
    title: str


class SectionRef(CamelModel):
    """A related section: the one an addendum supplements, or an addendum that supplements one."""

    id: str
    title: str
    group_name: str
    audience_label: str
    applies_to_me: bool


class SectionDetail(SectionSummary):
    blocks: list[HeadingBlock | ParagraphPassage | ListPassage]
    sources: list[str]
    # The company section this addendum supplements; null for a company section.
    supplements: SectionRef | None
    # The addenda that supplement this company section; empty for an addendum.
    supplemented_by: list[SectionRef]
    previous: SectionLink | None
    next: SectionLink | None


class PassageView(CamelModel):
    """What the passage panel shows."""

    section: SectionSummary
    passage: ParagraphPassage | ListPassage
    # The passages immediately before and after, skipping headings; null at the section's ends.
    previous: ParagraphPassage | ListPassage | None
    next: ParagraphPassage | ListPassage | None


class Segment(CamelModel):
    text: str
    # True for a word the search matched, so the browser can emphasize it without any HTML.
    match: bool


class SearchResultOut(CamelModel):
    section: SectionSummary
    # The passage the excerpt comes from, for a deep link: the first passage of the best chunk
    # that contains a matched word.
    passage_id: str
    excerpt: list[Segment]


class SearchResults(CamelModel):
    results: list[SearchResultOut]
