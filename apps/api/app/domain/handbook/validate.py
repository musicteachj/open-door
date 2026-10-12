"""Check the handbook's sources against every rule and build the validated handbook.

Every error is collected and reported together, each with its file and line, so one run shows
everything to fix.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime

from app.domain.handbook.blocks import Block, Passage
from app.domain.handbook.errors import HandbookError, HandbookInvalid
from app.domain.handbook.models import EMPLOYMENT_TYPES, Audience, Handbook, Section
from app.domain.handbook.parse import LinkRef, parse_body
from app.domain.handbook.source import SourceFile

__all__ = ["HandbookError", "HandbookInvalid", "load_handbook"]

type Fail = Callable[[str, str], None]

_FIELDS = {"id", "title", "updated", "applies_to", "supplements", "sources"}
_REQUIRED = ("id", "title", "updated")
_AUDIENCE_KEYS = ("states", "employment_types", "locations")
_NUMBER = r"\d+\.\d+"
_COMPANY_ID = re.compile(_NUMBER)
_ADDENDUM_ID = re.compile(rf"([A-Z]{{2}})-({_NUMBER})")
_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_ADDENDUM_PATH = re.compile(r"addenda/([a-z]{2})/([^/]+)\.md")
_COMPANY_PATH = re.compile(r"sections/([^/]+)\.md")


def load_handbook(config: SourceFile, files: Sequence[SourceFile]) -> Handbook:
    """Validate `config` (handbook.yaml) and the section `files`; raise HandbookInvalid if any
    rule is broken, listing every error."""
    errors: list[HandbookError] = []
    settings = _Config.read(config, errors)

    drafts: list[_Draft] = []
    for file in files:
        draft = _Draft.read(file, settings, errors)
        if draft is not None:
            drafts.append(draft)

    _check_unique_ids(drafts, errors)
    ids = {draft.id for draft in drafts}
    company_ids = {draft.id for draft in drafts if draft.kind == "company"}
    links: list[LinkRef] = []
    for draft in drafts:
        links.extend(draft.links)
        if draft.supplements is not None and draft.supplements not in company_ids:
            what = "isn't a section" if draft.supplements not in ids else "isn't a company section"
            errors.append(
                HandbookError(
                    draft.path,
                    draft.line("supplements"),
                    f"supplements {draft.supplements!r} {what}: name a company section that exists",
                )
            )
    for link in links:
        if link.target not in ids:
            errors.append(
                HandbookError(link.path, link.line, f"link to {link.target!r}: no such section")
            )

    if errors:
        raise HandbookInvalid(errors)

    sections = tuple(sorted((d.section(settings) for d in drafts), key=_order(settings)))
    return Handbook(
        version=settings.version,
        title=settings.title,
        chapters=settings.chapters,
        addenda=settings.addenda,
        locations=settings.locations,
        sections=sections,
        files=(config, *files),
    )


def _order(settings: "_Config") -> Callable[[Section], tuple[int, int, int, int]]:
    states = list(settings.addenda)

    def key(section: Section) -> tuple[int, int, int, int]:
        number = tuple(int(part) for part in section.id.split("-")[-1].split("."))
        if section.addendum_state is None:
            return (0, 0, number[0], number[1])
        return (1, states.index(section.addendum_state), number[0], number[1])

    return key


class _Config:
    """handbook.yaml, checked."""

    def __init__(
        self,
        version: str,
        title: str,
        chapters: Mapping[int, str],
        addenda: Mapping[str, str],
        locations: Mapping[str, str],
    ) -> None:
        self.version = version
        self.title = title
        self.chapters = chapters
        self.addenda = addenda
        self.locations = locations

    @classmethod
    def read(cls, file: SourceFile, errors: list[HandbookError]) -> "_Config":
        def fail(key: str, message: str) -> None:
            # An entry's line if the key is nested (`chapters.four`), else its parent's, else 1.
            fallback = file.field_lines.get(key.split(".")[0], 1)
            errors.append(HandbookError(file.path, file.field_lines.get(key, fallback), message))

        def text(key: str) -> str:
            value = file.data.get(key)
            if not isinstance(value, str) or not value.strip():
                fail(key, f"`{key}` must be a non-empty string")
                return ""
            return value

        def names(key: str) -> dict[object, str]:
            value = file.data.get(key)
            if not isinstance(value, Mapping) or not value:
                fail(key, f"`{key}` must be a non-empty mapping")
                return {}
            result: dict[object, str] = {}
            for name, label in value.items():
                if not isinstance(label, str) or not label.strip():
                    fail(f"{key}.{name}", f"`{key}` entry {name!r} needs a name")
                else:
                    result[name] = label
            return result

        version = text("version")
        title = text("title")
        chapters: dict[int, str] = {}
        for number, name in names("chapters").items():
            if isinstance(number, int) and not isinstance(number, bool):
                chapters[number] = name
            else:
                fail(f"chapters.{number}", f"chapter key {number!r} must be a whole number")
        addenda: dict[str, str] = {}
        for state, name in names("addenda").items():
            if isinstance(state, str) and re.fullmatch(r"[A-Z]{2}", state):
                addenda[state] = name
            else:
                fail(f"addenda.{state}", f"addendum key {state!r} must be a two-letter state code")
        locations: dict[str, str] = {}
        for code, name in names("locations").items():
            if isinstance(code, str) and re.fullmatch(r"[a-z]+", code):
                locations[code] = name
            else:
                fail(f"locations.{code}", f"location code {code!r} must be lowercase letters")
        return cls(version, title, chapters, addenda, locations)


class _Draft:
    """One section file after checking, before the links across files are resolved."""

    def __init__(self, file: SourceFile) -> None:
        self.file = file
        self.path = file.path
        self.id = ""
        self.title = ""
        self.kind: str = "company"
        self.chapter: int | None = None
        self.state: str | None = None
        self.updated = date.min
        self.audience = Audience()
        self.sources: tuple[str, ...] = ()
        self.supplements: str | None = None
        self.blocks: tuple[Block, ...] = ()
        self.links: tuple[LinkRef, ...] = ()

    def line(self, key: str) -> int:
        return self.file.field_lines.get(key, 1)

    @classmethod
    def read(
        cls, file: SourceFile, settings: _Config, errors: list[HandbookError]
    ) -> "_Draft | None":
        draft = cls(file)
        problems: list[HandbookError] = []

        def fail(key: str, message: str) -> None:
            problems.append(HandbookError(file.path, draft.line(key), message))

        data = file.data
        for key in data:
            if key not in _FIELDS:
                fail(key, f"unknown front matter field `{key}`")
        for key in _REQUIRED:
            if key not in data:
                fail(key, f"missing front matter field `{key}`")

        draft._identity(settings, fail)
        draft._title_and_date(fail)
        draft._audience(settings, fail)
        draft._supplements_and_sources(fail)

        parsed = parse_body(file.path, file.body, file.body_line_offset)
        problems.extend(parsed.errors)
        if not parsed.errors and not any(isinstance(b, Passage) for b in parsed.blocks):
            # Retrieval searches passages, so a section without one could never be found.
            line = file.body_line_offset + 1
            problems.append(
                HandbookError(file.path, line, "a section needs at least one paragraph or list")
            )
        draft.blocks = parsed.blocks
        draft.links = parsed.links

        errors.extend(problems)
        return draft if draft.id else None

    def _identity(self, settings: _Config, fail: Fail) -> None:
        value = self.file.data.get("id")
        if "id" not in self.file.data:
            return
        if not isinstance(value, str):
            fail("id", f"`id` must be a quoted string (a bare {value!r} would lose digits in YAML)")
            return
        company = _COMPANY_ID.fullmatch(value)
        addendum = _ADDENDUM_ID.fullmatch(value)
        folder = _ADDENDUM_PATH.fullmatch(self.path)
        if company and (path := _COMPANY_PATH.fullmatch(self.path)):
            self.kind = "company"
            self.chapter = int(value.split(".")[0])
            if self.chapter not in settings.chapters:
                fail("id", f"chapter {self.chapter} isn't in handbook.yaml's chapters")
            stem = path.group(1)
        elif addendum and folder:
            self.kind = "addendum"
            self.state = addendum.group(1)
            if self.state not in settings.addenda:
                fail("id", f"state {self.state} isn't in handbook.yaml's addenda")
            if folder.group(1) != self.state.lower():
                fail("id", f"ID {value!r} doesn't belong in the folder addenda/{folder.group(1)}/")
            stem = folder.group(2)
        else:
            fail(
                "id",
                f"ID {value!r} doesn't fit where the file is: a company section is `4.3` under "
                "sections/, an addendum is `CA-4.3` under addenda/ca/",
            )
            return
        self.id = value
        if not re.fullmatch(re.escape(value) + "-" + _SLUG, stem):
            fail("id", f"ID {value!r} doesn't match the file name: expected `{value}-<slug>.md`")

    def _title_and_date(self, fail: Fail) -> None:
        data = self.file.data
        if "title" in data:
            title = data["title"]
            if isinstance(title, str) and title.strip():
                self.title = title
            else:
                fail("title", "`title` must be a non-empty string")
        if "updated" in data:
            updated = data["updated"]
            if isinstance(updated, date) and not isinstance(updated, datetime):
                self.updated = updated
            else:
                fail("updated", f"`updated` must be a date like 2026-09-12, not {updated!r}")

    def _audience(self, settings: _Config, fail: Fail) -> None:
        applies_to = self.file.data.get("applies_to")
        if applies_to is None:
            if self.state is not None:
                # Without the field, nothing would limit the addendum to its state.
                fail(
                    "applies_to" if "applies_to" in self.file.field_lines else "id",
                    "an addendum applies to its own state: "
                    f"`applies_to.states` must be [{self.state}]",
                )
            return
        if not isinstance(applies_to, Mapping):
            fail("applies_to", "`applies_to` must be a mapping of lists")
            return
        allowed = {
            "states": set(settings.addenda),
            "employment_types": set(EMPLOYMENT_TYPES),
            "locations": set(settings.locations),
        }
        singular = {
            "states": "state",
            "employment_types": "employment type",
            "locations": "location",
        }
        lists: dict[str, tuple[str, ...]] = {}
        all_valid = True
        for key, value in applies_to.items():
            if key not in _AUDIENCE_KEYS:
                fail("applies_to", f"unknown `applies_to` field `{key}`")
                continue
            where = f"applies_to.{key}"
            if value is None:
                value = []
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                fail(where, f"`{where}` must be a list of strings")
                continue
            for item in value:
                if item not in allowed[key]:
                    all_valid = False
                    options = ", ".join(sorted(allowed[key]))
                    fail(where, f"unknown {singular[key]} {item!r}: expected one of {options}")
            lists[key] = tuple(value)
        self.audience = Audience(
            lists.get("states", ()),
            lists.get("employment_types", ()),
            lists.get("locations", ()),
        )
        if all_valid and self.state is not None and self.audience.states != (self.state,):
            fail(
                "applies_to.states"
                if "applies_to.states" in self.file.field_lines
                else "applies_to",
                f"an addendum applies to its own state: `applies_to.states` must be [{self.state}]",
            )

    def _supplements_and_sources(self, fail: Fail) -> None:
        data = self.file.data
        if "supplements" in data:
            value = data["supplements"]
            if not isinstance(value, str):
                fail("supplements", '`supplements` must be a quoted string like "4.3"')
            elif self.kind == "company":
                fail("supplements", "only an addendum has `supplements`")
            else:
                self.supplements = value
        elif self.kind == "addendum" and self.id:
            fail("id", "an addendum needs `supplements`: the company section it adds to")
        if "sources" in data:
            sources = data["sources"]
            if isinstance(sources, list) and all(isinstance(s, str) for s in sources):
                self.sources = tuple(sources)
            else:
                fail("sources", "`sources` must be a list of strings")

    def section(self, settings: _Config) -> Section:
        group = (
            settings.chapters[self.chapter]
            if self.chapter is not None
            else settings.addenda[self.state or ""]
        )
        return Section(
            id=self.id,
            title=self.title,
            kind="addendum" if self.state else "company",
            chapter=self.chapter,
            addendum_state=self.state,
            group_name=group,
            supplements=self.supplements,
            updated=self.updated,
            audience=self.audience,
            sources=self.sources,
            blocks=self.blocks,
            path=self.path,
        )


def _check_unique_ids(drafts: list[_Draft], errors: list[HandbookError]) -> None:
    first: dict[str, _Draft] = {}
    for draft in drafts:
        if draft.id in first:
            errors.append(
                HandbookError(
                    draft.path,
                    draft.line("id"),
                    f"duplicate ID {draft.id!r}: {first[draft.id].path} already has it",
                )
            )
        else:
            first[draft.id] = draft
