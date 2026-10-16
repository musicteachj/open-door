"""The assistant eval's datasets: the red-team set, the Q&A set, and the smoke list.

Pure: reading and checking YAML, with no database and no network (it imports the turn's question
length limit, so the datasets and the turn can't disagree about it). The runner builds `EvalItem`s
from these (`item.id`, `item.asker`, and `item.prompt`). A bad file raises `DatasetError` listing
every problem, one per line, the way the retrieval eval does, and the runner exits 2.

Whether a Q&A item's `expect` sections exist in the handbook is checked by `check_sections`, which
takes the section IDs from the handbook files (a pure test) or from the database (the runner).
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

from app.ai.turn import MAX_QUESTION_CHARACTERS
from app.domain.handbook.applicability import Asker
from app.modules.sandbox.seed import SeedCompany, build_company
from app.modules.sandbox.seed_data import LOCATIONS

EVAL_DIR = Path(__file__).resolve().parent
REDTEAM_PATH = EVAL_DIR / "redteam.yaml"
QA_PATH = EVAL_DIR / "qa.yaml"
SMOKE_PATH = EVAL_DIR / "smoke.yaml"


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


# The four people the demo talks about: Priya and Marcus (salaried, California), Dana (the HR
# administrator, salaried, Colorado), and Mateo (hourly, Texas). Who they are does not depend on a
# sandbox's IDs, so any tenant ID builds the same table.
PERSONAS: dict[str, Asker] = personas_of(build_company(UUID(int=1), date(2026, 10, 5)))
LOCATION_STATES = {spec.code: spec.state for spec in LOCATIONS}

GROUPS = ("private_details", "injection", "prompt_extraction", "routing")
ROUTES = ("crisis", "sensitive")
KINDS = ("answerable", "unanswerable", "other_state", "employment_decision", "ai_identity")


SMOKE_QA_COUNT = 15
SMOKE_REDTEAM_COUNT = 10


class DatasetError(Exception):
    """A dataset is invalid. The message lists every problem, one per line."""


@dataclass(frozen=True, slots=True)
class RedTeamItem:
    id: str
    asker: str
    group: str
    message: str
    route: str | None

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
class SmokeSet:
    qa: tuple[str, ...]
    redteam: tuple[str, ...]


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


def _read_list(path: Path, key: str) -> list[Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DatasetError(f"{path.name}: can't be read: {error}") from error
    items = data.get(key) if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
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
        if persona in PERSONAS:
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
        valid = True
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
            items.append(RedTeamItem(where, asker, str(group), message, route))
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
        if location_code is not None and location_code not in LOCATION_STATES:
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


def load_smoke(path: Path = SMOKE_PATH) -> SmokeSet:
    """The smoke list: Q&A IDs and red-team IDs. Raises `DatasetError` on a malformed file."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DatasetError(f"{path.name}: can't be read: {error}") from error
    problems = _Problems()
    lists: dict[str, tuple[str, ...]] = {}
    for key in ("qa", "redteam"):
        ids = data.get(key) if isinstance(data, dict) else None
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            problems.add(path.name, f"`{key}` must be a list of item IDs")
            continue
        lists[key] = tuple(ids)
    problems.raise_if_any()
    return SmokeSet(lists["qa"], lists["redteam"])


# --- Checks across files ---------------------------------------------------------------------


def check_unique_ids(redteam: Sequence[RedTeamItem], qa: Sequence[QaItem]) -> None:
    """Every ID is used once across both datasets, so a trace can be found by its ID alone."""
    counts = Counter([item.id for item in redteam] + [item.id for item in qa])
    duplicated = sorted(item_id for item_id, count in counts.items() if count > 1)
    if duplicated:
        raise DatasetError(
            "\n".join(f"{i}: used more than once across the datasets" for i in duplicated)
        )


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


def check_smoke(smoke: SmokeSet, redteam: Sequence[RedTeamItem], qa: Sequence[QaItem]) -> None:
    """The smoke list names 15 Q&A items and 10 red-team items, each once, each existing."""
    lines: list[str] = []
    for name, ids, known, count in (
        ("qa", smoke.qa, {i.id for i in qa}, SMOKE_QA_COUNT),
        ("redteam", smoke.redteam, {i.id for i in redteam}, SMOKE_REDTEAM_COUNT),
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
