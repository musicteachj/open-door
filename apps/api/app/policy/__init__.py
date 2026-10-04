"""Who may do what: one pure function that every route asks before it reads or acts.

Pure, like app.domain: no framework or database imports, which import-linter enforces (see
`[tool.importlinter]` in pyproject.toml). Deny by default: an action without a rule is refused.

Tenant scope isn't a rule here. Row-level security already keeps every target inside the actor's
tenant, so a person from another tenant never reaches this function.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID


def _require(value: object, expected: type, name: str) -> None:
    """Raise a TypeError unless `value` really is an `expected`, so a look-alike can't pass."""
    if not isinstance(value, expected):
        raise TypeError(f"{name} must be a {expected.__name__}, not {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class Actor:
    """The signed-in person. Every field comes from the server session and the database."""

    person_id: UUID
    tenant_id: UUID
    is_hr_admin: bool
    # Direct and indirect reports, computed fresh for every request and never cached.
    report_ids: frozenset[UUID]

    def __post_init__(self) -> None:
        # Python doesn't check annotations at runtime. A truthy string in `is_hr_admin`, for
        # example "false", would read as an HR administrator, so a wrong type fails loudly here.
        _require(self.person_id, UUID, "person_id")
        _require(self.tenant_id, UUID, "tenant_id")
        _require(self.is_hr_admin, bool, "is_hr_admin")
        _require(self.report_ids, frozenset, "report_ids")

    @property
    def is_manager(self) -> bool:
        """Being a manager is derived from having reports, never stored."""
        return bool(self.report_ids)


class Action(StrEnum):
    DIRECTORY_READ = "directory.read"
    PERSON_PRIVATE_READ = "person_private.read"


@dataclass(frozen=True, slots=True)
class PersonResource:
    """The person an action is aimed at."""

    person_id: UUID

    def __post_init__(self) -> None:
        _require(self.person_id, UUID, "person_id")


type Rule = Callable[[Actor, PersonResource], bool]


def _anyone_in_the_company(actor: Actor, target: PersonResource) -> bool:
    return True


def _themselves_or_hr(actor: Actor, target: PersonResource) -> bool:
    # A manager gets nothing extra: their reports' private details are not theirs to read.
    return target.person_id == actor.person_id or actor.is_hr_admin


RULES: Mapping[Action, Rule] = MappingProxyType(
    {
        Action.DIRECTORY_READ: _anyone_in_the_company,
        Action.PERSON_PRIVATE_READ: _themselves_or_hr,
    }
)


def can(actor: Actor, action: Action, target: PersonResource) -> bool:
    """Whether `actor` may perform `action` on `target`. An action without a rule is denied.

    Always a real bool: only a rule that returns exactly True grants access.
    """
    rule = RULES.get(action)
    return rule is not None and rule(actor, target) is True
