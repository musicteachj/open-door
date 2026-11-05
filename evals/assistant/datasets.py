"""The assistant eval's datasets: the red-team set, the Q&A set, the action set, and the smoke list.

Pure: reading and checking YAML, with no database and no network (it imports the turn's question
length limit, so the datasets and the turn can't disagree about it). The runner builds `EvalItem`s
from these (`item.id`, `item.asker`, and `item.prompt`). A bad file raises `DatasetError` listing
every problem, one per line, the way the retrieval eval does, and the runner exits 2.

Whether a Q&A item's `expect` sections exist in the handbook is checked by `check_sections`, which
takes the section IDs from the handbook files (a pure test) or from the database (the runner).
Which requests an action item names is checked by `check_requests`, against the eval sandbox's
company (the seed plus the harness's own requests).
"""

import hashlib
from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from app.ai.tools.timeoff import MAX_SICK_HOURS
from app.ai.turn import MAX_QUESTION_CHARACTERS
from app.domain.handbook.applicability import Asker
from app.modules.sandbox.seed import SeedCompany, build_company
from app.modules.sandbox.seed_data import LOCATIONS
from assistant.eval_sandbox import (
    CLONEABLE_PERSONAS,
    CloneSpec,
    NoSuchRequest,
    clone_person_id,
    request_id,
    template_person_id,
)

EVAL_DIR = Path(__file__).resolve().parent
REDTEAM_PATH = EVAL_DIR / "redteam.yaml"
QA_PATH = EVAL_DIR / "qa.yaml"
ACTIONS_PATH = EVAL_DIR / "actions.yaml"
SMOKE_PATH = EVAL_DIR / "smoke.yaml"
FAIRNESS_PATH = EVAL_DIR.parent / "fairness" / "groups.yaml"


def personas_of(company: SeedCompany) -> dict[str, Asker]:
    """Each persona as the handbook sees them (state, employment type, and office), read from the
    seed company itself. The datasets and the graders both use it, so there is one table, the
    seed's."""
    locations = {location.id: location for location in company.locations}
    return {
        p.persona_key: Asker(
            locations[p.location_id].state, p.employment_type, locations[p.location_id].code
        )
        for p in company.people
        if p.persona_key is not None
    }


def clone_askers(company: SeedCompany, clones: Collection[CloneSpec]) -> dict[str, Asker]:
    """Each fairness clone (by key) as the handbook sees them, read from the sandbox's company.
    A clone has no persona key, so `personas_of` does not find it."""
    locations = {location.id: location for location in company.locations}
    people = {person.id: person for person in company.people}
    found: dict[str, Asker] = {}
    for spec in clones:
        person = people[clone_person_id(company.tenant_id, spec.key)]
        place = locations[person.location_id]
        found[spec.key] = Asker(place.state, person.employment_type, place.code)
    return found


# The four people the demo talks about: Priya and Marcus (salaried, California), Dana (the HR
# administrator, salaried, Colorado), and Mateo (hourly, Texas). Who they are does not depend on a
# sandbox's IDs, so any tenant ID builds the same table.
PERSONAS: dict[str, Asker] = personas_of(build_company(UUID(int=1), date(2026, 10, 5)))
LOCATION_STATES = {spec.code: spec.state for spec in LOCATIONS}

GROUPS = ("private_details", "injection", "prompt_extraction", "routing", "actions", "cases")
ROUTES = ("crisis", "sensitive")
# What a red-team item may say about the cards the turn made: none at all, or one of this action.
PROPOSALS = ("none", "timeoff.request", "timeoff.decide", "timeoff.cancel")
ACTION_GROUPS = ("requests", "checks", "decisions", "cancels", "refused")
# The tools a "checks" item may expect: the ones that read and never propose.
CHECK_TOOLS = ("check_time_off", "get_time_off_balance", "list_time_off_requests")
LEAVE_TYPES = ("pto", "sick")
DECISIONS = ("approve", "deny")
KINDS = (
    "answerable",
    "unanswerable",
    "other_state",
    "employment_decision",
    "ai_identity",
    "tool_answer",
)


# What a fairness group varies: who asks (name), or the cue in the question.
ATTRIBUTES = ("name", "parent", "religion", "age", "origin", "spouse")

SMOKE_QA_COUNT = 23
SMOKE_REDTEAM_COUNT = 13
SMOKE_ACTION_COUNT = 6


class DatasetError(Exception):
    """A dataset is invalid. The message lists every problem, one per line."""


@dataclass(frozen=True, slots=True)
class RedTeamItem:
    id: str
    asker: str
    group: str
    message: str
    route: str | None
    # "none": no card may exist after the turn. An action ("timeoff.request"): a card of that
    # action must. None: the item says nothing about cards (it is graded for no write only).
    proposal: str | None = None
    # With an action in `proposal`: no card plus a clarifying question also passes.
    clarify: bool = False

    @property
    def prompt(self) -> str:
        """The words the asker types."""
        return self.message


@dataclass(frozen=True, slots=True)
class QaItem:
    id: str
    asker: str
    kind: str
    question: str
    reference: str
    expect: tuple[str, ...]
    location_code: str | None

    @property
    def prompt(self) -> str:
        """The words the asker types."""
        return self.question


@dataclass(frozen=True, slots=True)
class Reading:
    """One right way to read a request: the type, the dates, and how much of the day."""

    type: str
    start: date
    end: date
    half_day: bool = False
    hours: int | None = None


@dataclass(frozen=True, slots=True)
class RequestRef:
    """A time-off request named the way a person would: whose it is and when it starts. The
    graders resolve it to the request's ID in the eval sandbox."""

    person: str
    start: date


@dataclass(frozen=True, slots=True)
class ActionItem:
    id: str
    asker: str
    group: str
    message: str
    # requests, and optionally checks: the right readings (any one will do).
    readings: tuple[Reading, ...] = ()
    # requests, decisions, refused: a clarifying question is also a right answer.
    clarify: bool = False
    # checks: the tools, any one of which the turn must have called.
    tools: tuple[str, ...] = ()
    # decisions, cancels: the request, and for a decision what to do with it.
    request: RequestRef | None = None
    decision: str | None = None
    # refused: phrases, any one of which the answer must contain (lowercase).
    reason: tuple[str, ...] = ()

    @property
    def prompt(self) -> str:
        """The words the asker types."""
        return self.message


@dataclass(frozen=True, slots=True)
class FairnessItem:
    """One variant of a fairness group: who asks, and the exact words. `asker` is a persona or the
    key of a clone (see eval_sandbox.py)."""

    id: str
    group: str
    attribute: str
    asker: str
    question: str

    @property
    def prompt(self) -> str:
        """The words the asker types."""
        return self.question


@dataclass(frozen=True, slots=True)
class FairnessGroup:
    """The same question asked several ways. Every variant must get the same outcome, the same
    safety-check category, the `cites` sections cited, and, with `figures`, the same figures."""

    id: str
    attribute: str
    cites: tuple[str, ...]
    figures: bool
    variants: tuple[FairnessItem, ...]


@dataclass(frozen=True, slots=True)
class FairnessSet:
    clones: tuple[CloneSpec, ...]
    groups: tuple[FairnessGroup, ...]

    @property
    def items(self) -> tuple[FairnessItem, ...]:
        """Every variant of every group, in the file's order."""
        return tuple(item for group in self.groups for item in group.variants)


@dataclass(frozen=True, slots=True)
class SmokeSet:
    qa: tuple[str, ...]
    redteam: tuple[str, ...]
    actions: tuple[str, ...] = ()


def asker_for(persona: str, location_code: str | None = None) -> Asker:
    """The persona as the handbook sees them, or, with a location, as a person of the same
    employment type working there (the question "what does California say?")."""
    asker = PERSONAS[persona]
    if location_code is None:
        return asker
    return Asker(LOCATION_STATES[location_code], asker.employment_type, location_code)


def dataset_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- Reading ---------------------------------------------------------------------------------


def _read_list(path: Path, key: str, *, allow_empty: bool = False) -> list[Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DatasetError(f"{path.name}: can't be read: {error}") from error
    items = data.get(key) if isinstance(data, dict) else None
    if not isinstance(items, list) or not (items or allow_empty):
        raise DatasetError(f"{path.name}: expected a non-empty `{key}:` list")
    return items


def _text(value: Any) -> str | None:
    """The trimmed text, or None when it is not a usable string."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


class _Problems:
    """Collects what is wrong with a dataset, and the IDs seen so far."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.seen: set[str] = set()

    def add(self, where: str, message: str) -> None:
        self.lines.append(f"{where}: {message}")

    def name(self, item: dict[str, Any], index: int) -> str:
        raw = item.get("id")
        where = raw if isinstance(raw, str) and raw else f"item {index}"
        if not isinstance(raw, str) or not raw:
            self.add(where, "needs an id")
        elif raw in self.seen:
            self.add(where, "duplicate id")
        else:
            self.seen.add(raw)
        return where

    def persona(self, item: dict[str, Any], where: str) -> str | None:
        persona = item.get("asker")
        if isinstance(persona, str) and persona in PERSONAS:
            return str(persona)
        self.add(where, f"unknown asker {persona!r} (known: {', '.join(PERSONAS)})")
        return None

    def words(self, item: dict[str, Any], key: str, where: str) -> str | None:
        words = _text(item.get(key))
        if words is None:
            self.add(where, f"needs a {key}")
        elif len(words) > MAX_QUESTION_CHARACTERS:
            self.add(where, f"the {key} is over {MAX_QUESTION_CHARACTERS} characters")
        return words

    def raise_if_any(self) -> None:
        if self.lines:
            raise DatasetError("\n".join(self.lines))


def load_redteam(path: Path = REDTEAM_PATH) -> list[RedTeamItem]:
    """The red-team items in `path`. Raises `DatasetError` listing every problem."""
    problems = _Problems()
    items: list[RedTeamItem] = []
    for index, raw in enumerate(_read_list(path, "items"), start=1):
        if not isinstance(raw, dict):
            problems.add(f"item {index}", "must be a mapping")
            continue
        where = problems.name(raw, index)
        asker = problems.persona(raw, where)
        message = problems.words(raw, "message", where)
        group = raw.get("group")
        route = raw.get("route")
        proposal = raw.get("proposal")
        clarify = raw.get("clarify", False)
        valid = True
        if not isinstance(clarify, bool):
            problems.add(where, "`clarify` must be true or false")
            valid = False
        elif clarify and (proposal is None or proposal == "none"):
            problems.add(where, "`clarify` needs a `proposal` that names an action")
            valid = False
        if proposal is not None and proposal not in PROPOSALS:
            problems.add(where, f"unknown proposal {proposal!r} (known: {', '.join(PROPOSALS)})")
            valid = False
        if group not in GROUPS:
            problems.add(where, f"unknown group {group!r} (known: {', '.join(GROUPS)})")
            valid = False
        elif group != "routing" and route is not None:
            problems.add(where, "only a routing item has a route")
            valid = False
        elif group == "routing" and route is None:
            problems.add(where, "a routing item needs a route")
            valid = False
        elif group == "routing" and route not in ROUTES:
            problems.add(where, f"unknown route {route!r} (known: {', '.join(ROUTES)})")
            valid = False
        if asker is not None and message is not None and valid:
            items.append(
                RedTeamItem(where, asker, str(group), message, route, proposal, clarify is True)
            )
    problems.raise_if_any()
    return items


def _section_ids(value: Any, where: str, problems: _Problems) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        problems.add(where, "`expect` must be a list of section IDs written as strings")
        return ()
    return tuple(value)


def load_qa(path: Path = QA_PATH) -> list[QaItem]:
    """The Q&A items in `path`. Raises `DatasetError` listing every problem."""
    problems = _Problems()
    items: list[QaItem] = []
    for index, raw in enumerate(_read_list(path, "questions"), start=1):
        if not isinstance(raw, dict):
            problems.add(f"item {index}", "must be a mapping")
            continue
        before = len(problems.lines)
        where = problems.name(raw, index)
        asker = problems.persona(raw, where)
        question = problems.words(raw, "question", where)
        reference = _text(raw.get("reference"))
        if reference is None:
            problems.add(where, "needs a reference answer")
        kind = raw.get("kind")
        if kind not in KINDS:
            problems.add(where, f"unknown kind {kind!r} (known: {', '.join(KINDS)})")
        expect = _section_ids(raw.get("expect"), where, problems)
        if kind == "unanswerable" and expect:
            problems.add(where, "an unanswerable item has no `expect` sections")
        if kind in ("answerable", "other_state") and not expect:
            problems.add(where, f"a {kind} item needs `expect` sections")
        location_code = raw.get("location_code")
        if location_code is not None and not (
            isinstance(location_code, str) and location_code in LOCATION_STATES
        ):
            problems.add(where, f"unknown location_code {location_code!r}")
            location_code = None
        if kind == "other_state" and location_code is None:
            problems.add(where, "an other_state item needs a location_code")
        if (
            asker is not None
            and question is not None
            and reference is not None
            and len(problems.lines) == before
        ):
            items.append(
                QaItem(where, asker, str(kind), question, reference, expect, location_code)
            )
    problems.raise_if_any()
    return items


# --- The action set ---------------------------------------------------------------------------

# The keys each group takes, besides `id`, `asker`, `group`, and `message`.
_ACTION_KEYS: dict[str, tuple[str, ...]] = {
    "requests": ("readings", "clarify"),
    "checks": ("tools", "readings"),
    "decisions": ("request", "decision", "clarify"),
    "cancels": ("request",),
    "refused": ("reason", "clarify"),
}
_ALL_ACTION_KEYS = ("readings", "clarify", "tools", "request", "decision", "reason")


def _as_date(value: Any) -> date | None:
    """A date written YYYY-MM-DD (a quoted string, or the date YAML itself read), or None."""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _reading(raw: Any, where: str, problems: _Problems) -> Reading | None:
    if not isinstance(raw, dict):
        problems.add(where, "a reading must be a mapping")
        return None
    before = len(problems.lines)
    kind = raw.get("type")
    if kind not in LEAVE_TYPES:
        problems.add(where, f"unknown reading type {kind!r} (known: {', '.join(LEAVE_TYPES)})")
    days: dict[str, date | None] = {}
    for key in ("start", "end"):
        days[key] = _as_date(raw.get(key))
        if days[key] is None:
            problems.add(where, f"a reading's `{key}` must be a date written YYYY-MM-DD")
    start, end = days["start"], days["end"]
    if start is not None and end is not None and end < start:
        problems.add(where, "a reading can't end before it starts")
    half_day = raw.get("half_day", False)
    hours = raw.get("hours")
    if not isinstance(half_day, bool):
        problems.add(where, "`half_day` must be true or false")
    if hours is not None and not (
        isinstance(hours, int) and not isinstance(hours, bool) and 1 <= hours <= MAX_SICK_HOURS
    ):
        problems.add(where, f"`hours` must be a whole number from 1 to {MAX_SICK_HOURS}")
    if hours is not None and half_day is True:
        problems.add(where, "a reading takes `half_day` or `hours`, not both")
    if hours is not None and kind == "pto":
        problems.add(where, "`hours` is for sick time only")
    if len(problems.lines) > before or start is None or end is None:
        return None
    return Reading(str(kind), start, end, half_day, hours)


def _request_ref(raw: Any, where: str, problems: _Problems) -> RequestRef | None:
    person = _text(raw.get("person")) if isinstance(raw, dict) else None
    start = _as_date(raw.get("start")) if isinstance(raw, dict) else None
    if person is None or start is None:
        problems.add(where, "`request` needs a `person` and a `start` (YYYY-MM-DD)")
        return None
    return RequestRef(person, start)


def load_actions(path: Path = ACTIONS_PATH) -> list[ActionItem]:
    """The action items in `path`. Raises `DatasetError` listing every problem. A file may hold no
    items (a test's tiny set); the committed one holds about thirty."""
    problems = _Problems()
    items: list[ActionItem] = []
    for index, raw in enumerate(_read_list(path, "items", allow_empty=True), start=1):
        if not isinstance(raw, dict):
            problems.add(f"item {index}", "must be a mapping")
            continue
        before = len(problems.lines)
        where = problems.name(raw, index)
        asker = problems.persona(raw, where)
        message = problems.words(raw, "message", where)
        group = raw.get("group")
        if group not in ACTION_GROUPS:
            problems.add(where, f"unknown group {group!r} (known: {', '.join(ACTION_GROUPS)})")
            continue
        for key in _ALL_ACTION_KEYS:
            if key in raw and key not in _ACTION_KEYS[group]:
                problems.add(where, f"a {group} item has no `{key}`")
        readings = _readings(raw, where, problems, group)
        tools = _tools(raw, where, problems, group)
        request = None
        if group in ("decisions", "cancels"):
            request = _request_ref(raw.get("request"), where, problems)
        decision = raw.get("decision")
        if group == "decisions" and decision is None:
            problems.add(where, "a decisions item needs a `decision`")
        elif group == "decisions" and decision not in DECISIONS:
            problems.add(where, f"unknown decision {decision!r} (known: {', '.join(DECISIONS)})")
        clarify = raw.get("clarify", False)
        if not isinstance(clarify, bool):
            problems.add(where, "`clarify` must be true or false")
        reason = _reasons(raw, where, problems, group)
        if (
            asker is not None
            and message is not None
            and isinstance(clarify, bool)
            and len(problems.lines) == before
        ):
            items.append(
                ActionItem(
                    where,
                    asker,
                    str(group),
                    message,
                    readings,
                    clarify,
                    tools,
                    request,
                    None if decision is None else str(decision),
                    reason,
                )
            )
    problems.raise_if_any()
    return items


def _readings(
    raw: dict[str, Any], where: str, problems: _Problems, group: str
) -> tuple[Reading, ...]:
    listed = raw.get("readings")
    if group not in ("requests", "checks"):
        return ()
    if group == "requests" and not listed:
        problems.add(where, "a requests item needs `readings`")
        return ()
    if listed is None:
        return ()
    if not isinstance(listed, list):
        problems.add(where, "`readings` must be a list")
        return ()
    found = [_reading(entry, where, problems) for entry in listed]
    return tuple(r for r in found if r is not None)


def _tools(raw: dict[str, Any], where: str, problems: _Problems, group: str) -> tuple[str, ...]:
    if group != "checks":
        return ()
    listed = raw.get("tools")
    if not isinstance(listed, list) or not listed:
        problems.add(where, "a checks item needs `tools`")
        return ()
    for name in listed:
        if name not in CHECK_TOOLS:
            problems.add(where, f"unknown tool {name!r} (known: {', '.join(CHECK_TOOLS)})")
    return tuple(str(name) for name in listed)


def _reasons(raw: dict[str, Any], where: str, problems: _Problems, group: str) -> tuple[str, ...]:
    if group != "refused":
        return ()
    listed = raw.get("reason")
    if (
        not isinstance(listed, list)
        or not listed
        or not all(isinstance(r, str) and r.strip() for r in listed)
    ):
        problems.add(where, "a refused item needs `reason`, a list of phrases")
        return ()
    # Answers are compared after `_plain`, so the phrases are normalized the same way. Imported
    # here because graders imports this module.
    from assistant.graders import _plain

    return tuple(_plain(r) for r in listed)


# --- The fairness set -------------------------------------------------------------------------


def _clones(raw_clones: Any, problems: _Problems) -> list[CloneSpec]:
    if raw_clones is None:
        return []
    if not isinstance(raw_clones, list):
        problems.add("clones", "must be a list")
        return []
    clones: list[CloneSpec] = []
    keys: set[str] = set()
    for index, raw in enumerate(raw_clones, start=1):
        if not isinstance(raw, dict):
            problems.add(f"clone {index}", "must be a mapping")
            continue
        key = _text(raw.get("key"))
        where = key or f"clone {index}"
        if key is None:
            problems.add(where, "needs a key")
        elif key in PERSONAS:
            problems.add(key, "a clone's key can't be a persona")
        elif key in keys:
            problems.add(key, "duplicate clone key")
        else:
            keys.add(key)
        given, family = _text(raw.get("given")), _text(raw.get("family"))
        if given is None or family is None:
            problems.add(where, "needs a `given` and a `family` name")
        like = raw.get("like")
        location, employment_type = raw.get("location"), raw.get("employment_type")
        ok = True
        if like is not None:
            if like not in CLONEABLE_PERSONAS:
                problems.add(
                    where, f"can't be like {like!r} (an employee: {', '.join(CLONEABLE_PERSONAS)})"
                )
                ok = False
            if location is not None or employment_type is not None:
                problems.add(where, "takes `like`, or `location` and `employment_type`, not both")
                ok = False
        elif location is None or employment_type is None:
            problems.add(where, "needs `like`, or a `location` and an `employment_type`")
            ok = False
        if ok and key and given and family:
            spec = CloneSpec(
                key,
                given,
                family,
                None if like is None else str(like),
                None if location is None else str(location),
                None if employment_type is None else str(employment_type),
            )
            if like is None:
                try:
                    template_person_id(UUID(int=1), spec)
                except ValueError as error:
                    problems.add(where, str(error).split(": ", 1)[-1])
                    continue
            clones.append(spec)
    return clones


def _variants(
    group: dict[str, Any], where: str, attribute: str, askers: Collection[str], problems: _Problems
) -> tuple[FairnessItem, ...]:
    raw_variants = group.get("variants")
    if not isinstance(raw_variants, list) or len(raw_variants) < 2:
        problems.add(where, "needs at least two variants")
        return ()
    found: list[FairnessItem] = []
    for index, raw in enumerate(raw_variants, start=1):
        if not isinstance(raw, dict):
            problems.add(f"{where} variant {index}", "must be a mapping")
            continue
        before = len(problems.lines)
        name = problems.name(raw, index)
        asker = raw.get("asker")
        if not (isinstance(asker, str) and asker in askers):
            problems.add(name, f"unknown asker {asker!r} (known: {', '.join(sorted(askers))})")
        question = problems.words(raw, "question", name)
        if len(problems.lines) == before and question is not None:
            found.append(FairnessItem(name, where, attribute, str(asker), question))
    return tuple(found)


def _group(
    raw: dict[str, Any], index: int, askers: Collection[str], problems: _Problems
) -> FairnessGroup | None:
    before = len(problems.lines)
    where = problems.name(raw, index)
    attribute = raw.get("attribute")
    if attribute not in ATTRIBUTES:
        problems.add(where, f"unknown attribute {attribute!r} (known: {', '.join(ATTRIBUTES)})")
    cites = raw.get("cites")
    if not isinstance(cites, list) or not cites or not all(isinstance(c, str) and c for c in cites):
        problems.add(where, "needs `cites`, a list of section IDs written as strings")
    figures = raw.get("figures")
    if not isinstance(figures, bool):
        problems.add(where, "`figures` must be true or false")
    variants = _variants(raw, where, str(attribute), askers, problems)
    if len(problems.lines) > before:
        return None
    return FairnessGroup(
        where,
        str(attribute),
        tuple(str(c) for c in (cites if isinstance(cites, list) else [])),
        figures is True,
        variants,
    )


def load_fairness(path: Path = FAIRNESS_PATH) -> FairnessSet:
    """The fairness clones and groups in `path`. Raises `DatasetError` listing every problem."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DatasetError(f"{path.name}: can't be read: {error}") from error
    if not isinstance(data, dict):
        raise DatasetError(f"{path.name}: expected `clones:` and `groups:`")
    problems = _Problems()
    clones = _clones(data.get("clones"), problems)
    askers = {*PERSONAS, *(clone.key for clone in clones)}
    groups: list[FairnessGroup] = []
    raw_groups = data.get("groups")
    if not isinstance(raw_groups, list) or not raw_groups:
        raise DatasetError(f"{path.name}: expected a non-empty `groups:` list")
    for index, raw in enumerate(raw_groups, start=1):
        if not isinstance(raw, dict):
            problems.add(f"group {index}", "must be a mapping")
            continue
        group = _group(raw, index, askers, problems)
        if group is not None:
            groups.append(group)
    asked = {item.asker for group in groups for item in group.variants}
    problems.lines.extend(
        f"{clone.key}: no variant is asked by this clone"
        for clone in clones
        if clone.key not in asked
    )
    problems.raise_if_any()
    return FairnessSet(tuple(clones), tuple(groups))


def load_smoke(path: Path = SMOKE_PATH) -> SmokeSet:
    """The smoke list: Q&A, red-team, and action IDs. `actions` may be left out. Raises
    `DatasetError` on a malformed file."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DatasetError(f"{path.name}: can't be read: {error}") from error
    problems = _Problems()
    lists: dict[str, tuple[str, ...]] = {}
    for key in ("qa", "redteam", "actions"):
        ids = data.get(key) if isinstance(data, dict) else None
        if ids is None and key == "actions" and isinstance(data, dict):
            lists[key] = ()
            continue
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            problems.add(path.name, f"`{key}` must be a list of item IDs")
            continue
        lists[key] = tuple(ids)
    problems.raise_if_any()
    return SmokeSet(lists["qa"], lists["redteam"], lists["actions"])


# --- Checks across files ---------------------------------------------------------------------


def check_unique_ids(
    redteam: Sequence[RedTeamItem],
    qa: Sequence[QaItem],
    actions: Sequence[ActionItem] = (),
    *,
    fairness: Sequence[FairnessItem] = (),
) -> None:
    """Every ID is used once across the datasets, so a trace can be found by its ID alone."""
    counts = Counter(
        [item.id for item in redteam]
        + [item.id for item in qa]
        + [item.id for item in actions]
        + [item.id for item in fairness]
    )
    duplicated = sorted(item_id for item_id, count in counts.items() if count > 1)
    if duplicated:
        raise DatasetError(
            "\n".join(f"{i}: used more than once across the datasets" for i in duplicated)
        )


def check_requests(actions: Sequence[ActionItem], company: SeedCompany) -> None:
    """Every request an action item names exists in `company`: the eval sandbox's, the seed plus
    the harness's own requests (see eval_sandbox.py)."""
    lines: list[str] = []
    for item in actions:
        if item.request is None:
            continue
        try:
            request_id(company, item.request.person, item.request.start)
        except NoSuchRequest as error:
            lines.append(f"{item.id}: {error}")
    if lines:
        raise DatasetError("\n".join(lines))


def check_sections(qa: Sequence[QaItem], section_ids: Collection[str]) -> None:
    """Every `expect` section exists. `section_ids` come from the handbook files or the database."""
    lines = [
        f"{item.id}: no section {section} in the handbook"
        for item in qa
        for section in item.expect
        if section not in section_ids
    ]
    if lines:
        raise DatasetError("\n".join(lines))


def check_fairness_sections(groups: Sequence[FairnessGroup], section_ids: Collection[str]) -> None:
    """Every section a fairness group cites exists. `section_ids` come from the handbook files or
    the database."""
    lines = [
        f"{group.id}: no section {section} in the handbook"
        for group in groups
        for section in group.cites
        if section not in section_ids
    ]
    if lines:
        raise DatasetError("\n".join(lines))


def check_smoke(
    smoke: SmokeSet,
    redteam: Sequence[RedTeamItem],
    qa: Sequence[QaItem],
    actions: Sequence[ActionItem] = (),
) -> None:
    """The smoke list names `SMOKE_QA_COUNT` Q&A items, `SMOKE_REDTEAM_COUNT` red-team items, and
    `SMOKE_ACTION_COUNT` action items, each once, each existing."""
    lines: list[str] = []
    for name, ids, known, count in (
        ("qa", smoke.qa, {i.id for i in qa}, SMOKE_QA_COUNT),
        ("redteam", smoke.redteam, {i.id for i in redteam}, SMOKE_REDTEAM_COUNT),
        ("actions", smoke.actions, {i.id for i in actions}, SMOKE_ACTION_COUNT),
    ):
        if len(ids) != count:
            lines.append(f"smoke {name}: needs exactly {count} IDs, has {len(ids)}")
        lines.extend(
            f"smoke {name}: {i} is listed more than once" for i, n in Counter(ids).items() if n > 1
        )
        lines.extend(
            f"smoke {name}: {i} is not in the {name} dataset" for i in ids if i not in known
        )
    if lines:
        raise DatasetError("\n".join(lines))
