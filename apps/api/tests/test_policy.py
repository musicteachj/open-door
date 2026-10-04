"""The permission matrix, as plain values: no database and no HTTP."""

from collections.abc import MutableMapping
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app import policy
from app.policy import Action, Actor, PersonResource, can

TENANT_ID = uuid4()
EMPLOYEE_ID, COLLEAGUE_ID, MANAGER_ID, REPORT_ID, HR_ID = (uuid4() for _ in range(5))

EMPLOYEE = Actor(EMPLOYEE_ID, TENANT_ID, is_hr_admin=False, report_ids=frozenset())
MANAGER = Actor(MANAGER_ID, TENANT_ID, is_hr_admin=False, report_ids=frozenset({REPORT_ID}))
HR = Actor(HR_ID, TENANT_ID, is_hr_admin=True, report_ids=frozenset())

# The spec's matrix: the actor, the target, and what each action allows.
TARGETS: dict[str, tuple[Actor, UUID]] = {
    "self": (EMPLOYEE, EMPLOYEE_ID),
    "another employee": (EMPLOYEE, COLLEAGUE_ID),
    "manager, for a report": (MANAGER, REPORT_ID),
    "HR, for anyone": (HR, COLLEAGUE_ID),
}
MATRIX: dict[Action, dict[str, bool]] = {
    Action.DIRECTORY_READ: {
        "self": True,
        "another employee": True,
        "manager, for a report": True,
        "HR, for anyone": True,
    },
    Action.PERSON_PRIVATE_READ: {
        "self": True,
        "another employee": False,
        "manager, for a report": False,
        "HR, for anyone": True,
    },
}
CASES = [
    (action, relationship, allowed)
    for action, row in MATRIX.items()
    for relationship, allowed in row.items()
]


@pytest.mark.parametrize(("action", "relationship", "allowed"), CASES)
def test_the_permission_matrix(action: Action, relationship: str, allowed: bool) -> None:
    actor, target_id = TARGETS[relationship]

    assert can(actor, action, PersonResource(target_id)) is allowed


def test_the_matrix_covers_every_action_and_every_relationship() -> None:
    # A new action fails here until its row is added to the matrix.
    assert set(MATRIX) == set(Action)
    assert all(set(row) == set(TARGETS) for row in MATRIX.values())


def test_an_action_without_a_rule_is_denied_even_for_hr() -> None:
    unknown = cast(Action, "payroll.read")

    assert can(HR, unknown, PersonResource(HR_ID)) is False


def test_being_a_manager_comes_from_having_reports() -> None:
    assert (EMPLOYEE.is_manager, MANAGER.is_manager, HR.is_manager) == (False, True, False)


@pytest.mark.parametrize(("action", "relationship", "allowed"), CASES)
def test_can_returns_exactly_true_or_false(
    action: Action, relationship: str, allowed: bool
) -> None:
    actor, target_id = TARGETS[relationship]

    result = can(actor, action, PersonResource(target_id))

    if allowed:
        assert result is True
    else:
        assert result is False


@pytest.mark.parametrize("returned", ["false", "yes", 1, 0, None, [], [1]])
def test_a_rule_that_returns_anything_but_true_denies(
    monkeypatch: pytest.MonkeyPatch, returned: object
) -> None:
    # A truthy non-bool, such as the string "false", must never read as permission.
    monkeypatch.setattr(policy, "RULES", {Action.DIRECTORY_READ: lambda actor, target: returned})

    assert can(EMPLOYEE, Action.DIRECTORY_READ, PersonResource(EMPLOYEE_ID)) is False


VALID_ACTOR: dict[str, Any] = {
    "person_id": EMPLOYEE_ID,
    "tenant_id": TENANT_ID,
    "is_hr_admin": False,
    "report_ids": frozenset[UUID](),
}


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("is_hr_admin", "false"),
        ("is_hr_admin", 1),
        ("is_hr_admin", None),
        ("report_ids", {REPORT_ID}),
        ("report_ids", [REPORT_ID]),
        ("report_ids", None),
        ("person_id", str(EMPLOYEE_ID)),
        ("person_id", None),
        ("tenant_id", str(TENANT_ID)),
        ("tenant_id", 7),
    ],
)
def test_an_actor_refuses_a_field_of_the_wrong_type(field: str, bad_value: object) -> None:
    with pytest.raises(TypeError, match=field):
        Actor(**{**VALID_ACTOR, field: bad_value})


def test_a_string_for_is_hr_admin_cannot_grant_access() -> None:
    # The proven exploit: "false" is truthy, so an unchecked Actor read as an HR administrator.
    with pytest.raises(TypeError, match="is_hr_admin"):
        Actor(EMPLOYEE_ID, TENANT_ID, is_hr_admin=cast(bool, "false"), report_ids=frozenset())


@pytest.mark.parametrize("bad_value", [str(EMPLOYEE_ID), None, 7])
def test_a_person_resource_refuses_an_id_that_is_not_a_uuid(bad_value: object) -> None:
    with pytest.raises(TypeError, match="person_id"):
        PersonResource(cast(UUID, bad_value))


def test_the_rules_cannot_be_modified() -> None:
    rules = cast(MutableMapping[Action, object], policy.RULES)

    with pytest.raises(TypeError):
        rules[Action.PERSON_PRIVATE_READ] = lambda actor, target: True
    with pytest.raises(TypeError):
        del rules[Action.PERSON_PRIVATE_READ]
