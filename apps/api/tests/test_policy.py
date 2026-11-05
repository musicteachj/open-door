"""The permission matrix, as plain values: no database and no HTTP."""

from collections.abc import MutableMapping
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app import policy
from app.policy import Action, Actor, CaseResource, PersonResource, TimeOffRequestResource, can

TENANT_ID = uuid4()
EMPLOYEE_ID, COLLEAGUE_ID, MANAGER_ID, REPORT_ID, HR_ID, SKIP_ID = (uuid4() for _ in range(6))
TODAY = date(2026, 10, 21)

EMPLOYEE = Actor(
    EMPLOYEE_ID, TENANT_ID, is_hr_admin=False, report_ids=frozenset(), direct_report_ids=frozenset()
)
# The manager manages REPORT_ID directly. SKIP is the manager's own manager: REPORT_ID is two
# levels below them, a report but not a direct one.
MANAGER = Actor(
    MANAGER_ID,
    TENANT_ID,
    is_hr_admin=False,
    report_ids=frozenset({REPORT_ID}),
    direct_report_ids=frozenset({REPORT_ID}),
)
SKIP = Actor(
    SKIP_ID,
    TENANT_ID,
    is_hr_admin=False,
    report_ids=frozenset({MANAGER_ID, REPORT_ID}),
    direct_report_ids=frozenset({MANAGER_ID}),
)
HR = Actor(
    HR_ID, TENANT_ID, is_hr_admin=True, report_ids=frozenset(), direct_report_ids=frozenset()
)

# The spec's matrix: the actor, the target, and what each action allows.
TARGETS: dict[str, tuple[Actor, UUID]] = {
    "self": (EMPLOYEE, EMPLOYEE_ID),
    "another employee": (EMPLOYEE, COLLEAGUE_ID),
    "manager, for a report": (MANAGER, REPORT_ID),
    "manager two levels up": (SKIP, REPORT_ID),
    "manager, for their own manager": (MANAGER, SKIP_ID),
    "HR, for anyone": (HR, COLLEAGUE_ID),
    # HR's own record: for a case, HR's own case, which appears in their queue with no actions.
    "HR, for their own": (HR, HR_ID),
}
MATRIX: dict[Action, dict[str, bool]] = {
    Action.DIRECTORY_READ: {
        "self": True,
        "another employee": True,
        "manager, for a report": True,
        "manager two levels up": True,
        "manager, for their own manager": True,
        "HR, for anyone": True,
        "HR, for their own": True,
    },
    Action.PERSON_PRIVATE_READ: {
        "self": True,
        "another employee": False,
        "manager, for a report": False,
        "manager two levels up": False,
        "manager, for their own manager": False,
        "HR, for anyone": True,
        "HR, for their own": True,
    },
    Action.TIMEOFF_READ: {
        "self": True,
        "another employee": False,
        "manager, for a report": True,
        "manager two levels up": True,
        "manager, for their own manager": False,
        "HR, for anyone": True,
        "HR, for their own": True,
    },
    Action.TIMEOFF_REQUEST: {
        "self": True,
        "another employee": False,
        "manager, for a report": False,
        "manager two levels up": False,
        "manager, for their own manager": False,
        "HR, for anyone": False,
        "HR, for their own": True,
    },
    # The request is a pending PTO request of the target, starting after today.
    Action.TIMEOFF_DECIDE: {
        "self": False,
        "another employee": False,
        "manager, for a report": True,
        "manager two levels up": False,
        "manager, for their own manager": False,
        "HR, for anyone": False,
        "HR, for their own": False,
    },
    # The request is the target's own pending request: only the person cancels it.
    Action.TIMEOFF_CANCEL: {
        "self": True,
        "another employee": False,
        "manager, for a report": False,
        "manager two levels up": False,
        "manager, for their own manager": False,
        "HR, for anyone": False,
        "HR, for their own": True,
    },
    # Cases (Phase 6). Only the person who opened a case and HR read its status. HR alone lists the
    # queue, and reads a summary or the words, and changes the status, on a case that isn't theirs.
    # A manager gets nothing: a report's case is not theirs to see.
    Action.CASE_OPEN: {
        "self": True,
        "another employee": False,
        "manager, for a report": False,
        "manager two levels up": False,
        "manager, for their own manager": False,
        "HR, for anyone": False,
        "HR, for their own": True,
    },
    Action.CASE_READ_STATUS: {
        "self": True,
        "another employee": False,
        "manager, for a report": False,
        "manager two levels up": False,
        "manager, for their own manager": False,
        "HR, for anyone": True,
        "HR, for their own": True,
    },
    Action.CASE_LIST: {
        "self": False,
        "another employee": False,
        "manager, for a report": False,
        "manager two levels up": False,
        "manager, for their own manager": False,
        "HR, for anyone": True,
        "HR, for their own": True,
    },
    Action.CASE_READ_SUMMARY: {
        "self": False,
        "another employee": False,
        "manager, for a report": False,
        "manager two levels up": False,
        "manager, for their own manager": False,
        "HR, for anyone": True,
        "HR, for their own": False,
    },
    Action.CASE_READ_TEXT: {
        "self": False,
        "another employee": False,
        "manager, for a report": False,
        "manager two levels up": False,
        "manager, for their own manager": False,
        "HR, for anyone": True,
        "HR, for their own": False,
    },
    # The case is one whose words this actor has read.
    Action.CASE_UPDATE_STATUS: {
        "self": False,
        "another employee": False,
        "manager, for a report": False,
        "manager two levels up": False,
        "manager, for their own manager": False,
        "HR, for anyone": True,
        "HR, for their own": False,
    },
    # The AI Ops console is HR's, like the case queue. "HR, for their own" is True because the
    # route passes the HR person's own PersonResource (unlike the case reads, which compare a case's
    # owner with the actor).
    Action.CONSOLE_READ: {
        "self": False,
        "another employee": False,
        "manager, for a report": False,
        "manager two levels up": False,
        "manager, for their own manager": False,
        "HR, for anyone": True,
        "HR, for their own": True,
    },
}


CASE_ACTIONS = (
    Action.CASE_OPEN,
    Action.CASE_READ_STATUS,
    Action.CASE_LIST,
    Action.CASE_READ_SUMMARY,
    Action.CASE_READ_TEXT,
    Action.CASE_UPDATE_STATUS,
)


def resource_for(
    action: Action, person_id: UUID
) -> PersonResource | TimeOffRequestResource | CaseResource:
    """The resource a matrix row asks about: a person, the person's pending PTO request, or the
    person's new case, whose words the actor has read."""
    if action in {Action.TIMEOFF_DECIDE, Action.TIMEOFF_CANCEL}:
        return pto_request(person_id)
    if action in CASE_ACTIONS and action not in {Action.CASE_OPEN, Action.CASE_LIST}:
        return CaseResource(person_id, "new", words_read_by_actor=True)
    return PersonResource(person_id)


def pto_request(
    person_id: UUID,
    *,
    type: str = "pto",
    status: str = "pending",
    start_date: date = TODAY + timedelta(days=10),
) -> TimeOffRequestResource:
    return TimeOffRequestResource(person_id, type, status, start_date)


CASES = [
    (action, relationship, allowed)
    for action, row in MATRIX.items()
    for relationship, allowed in row.items()
]


@pytest.mark.parametrize(("action", "relationship", "allowed"), CASES)
def test_the_permission_matrix(action: Action, relationship: str, allowed: bool) -> None:
    actor, target_id = TARGETS[relationship]

    assert can(actor, action, resource_for(action, target_id), today=TODAY) is allowed


def test_the_matrix_covers_every_action_and_every_relationship() -> None:
    # A new action fails here until its row is added to the matrix.
    assert set(MATRIX) == set(Action)
    assert all(set(row) == set(TARGETS) for row in MATRIX.values())


def test_an_action_without_a_rule_is_denied_even_for_hr() -> None:
    unknown = cast(Action, "payroll.read")

    assert can(HR, unknown, PersonResource(HR_ID)) is False


def test_being_a_manager_comes_from_having_reports() -> None:
    assert (EMPLOYEE.is_manager, MANAGER.is_manager, HR.is_manager) == (False, True, False)


def test_an_actor_needs_direct_report_ids() -> None:
    # Required, with no default: a construction site that forgets it fails loudly.
    with pytest.raises(TypeError, match="direct_report_ids"):
        Actor(  # type: ignore[call-arg]
            EMPLOYEE_ID, TENANT_ID, is_hr_admin=False, report_ids=frozenset()
        )


def test_direct_reports_must_be_among_all_reports() -> None:
    with pytest.raises(ValueError, match="direct_report_ids"):
        Actor(
            MANAGER_ID,
            TENANT_ID,
            is_hr_admin=False,
            report_ids=frozenset({REPORT_ID}),
            direct_report_ids=frozenset({REPORT_ID, COLLEAGUE_ID}),
        )


@pytest.mark.parametrize(("action", "relationship", "allowed"), CASES)
def test_can_returns_exactly_true_or_false(
    action: Action, relationship: str, allowed: bool
) -> None:
    actor, target_id = TARGETS[relationship]

    result = can(actor, action, resource_for(action, target_id), today=TODAY)

    if allowed:
        assert result is True
    else:
        assert result is False


@pytest.mark.parametrize("returned", ["false", "yes", 1, 0, None, [], [1]])
def test_a_rule_that_returns_anything_but_true_denies(
    monkeypatch: pytest.MonkeyPatch, returned: object
) -> None:
    # A truthy non-bool, such as the string "false", must never read as permission.
    monkeypatch.setattr(
        policy, "RULES", {Action.DIRECTORY_READ: lambda actor, target, today: returned}
    )

    assert can(EMPLOYEE, Action.DIRECTORY_READ, PersonResource(EMPLOYEE_ID)) is False


VALID_ACTOR: dict[str, Any] = {
    "person_id": EMPLOYEE_ID,
    "tenant_id": TENANT_ID,
    "is_hr_admin": False,
    "report_ids": frozenset[UUID](),
    "direct_report_ids": frozenset[UUID](),
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
        ("direct_report_ids", {REPORT_ID}),
        ("direct_report_ids", [REPORT_ID]),
        ("direct_report_ids", None),
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
        Actor(
            EMPLOYEE_ID,
            TENANT_ID,
            is_hr_admin=cast(bool, "false"),
            report_ids=frozenset(),
            direct_report_ids=frozenset(),
        )


@pytest.mark.parametrize("bad_value", [str(EMPLOYEE_ID), None, 7])
def test_a_person_resource_refuses_an_id_that_is_not_a_uuid(bad_value: object) -> None:
    with pytest.raises(TypeError, match="person_id"):
        PersonResource(cast(UUID, bad_value))


def test_the_rules_cannot_be_modified() -> None:
    rules = cast(MutableMapping[Action, object], policy.RULES)

    with pytest.raises(TypeError):
        rules[Action.PERSON_PRIVATE_READ] = lambda actor, target, today: True
    with pytest.raises(TypeError):
        del rules[Action.PERSON_PRIVATE_READ]


# Time off: the cases the matrix can't say with one request shape.


def test_marcus_decides_priyas_pending_pto_but_priya_cannot_decide_her_own() -> None:
    assert can(MANAGER, Action.TIMEOFF_DECIDE, pto_request(REPORT_ID)) is True
    own = Actor(
        REPORT_ID,
        TENANT_ID,
        is_hr_admin=False,
        report_ids=frozenset({EMPLOYEE_ID}),
        direct_report_ids=frozenset({EMPLOYEE_ID}),
    )
    assert can(own, Action.TIMEOFF_DECIDE, pto_request(REPORT_ID)) is False


def test_the_skip_level_manager_and_hr_read_a_request_but_do_not_decide_it() -> None:
    request = pto_request(REPORT_ID)

    assert can(SKIP, Action.TIMEOFF_READ, request) is True
    assert can(HR, Action.TIMEOFF_READ, request) is True
    assert can(SKIP, Action.TIMEOFF_DECIDE, request) is False
    assert can(HR, Action.TIMEOFF_DECIDE, request) is False


def test_a_manager_cannot_decide_a_request_of_their_own() -> None:
    # Even if a bad org chart listed them among their own direct reports, the rule refuses.
    loop = Actor(
        MANAGER_ID,
        TENANT_ID,
        is_hr_admin=False,
        report_ids=frozenset({MANAGER_ID}),
        direct_report_ids=frozenset({MANAGER_ID}),
    )

    assert can(loop, Action.TIMEOFF_DECIDE, pto_request(MANAGER_ID)) is False


@pytest.mark.parametrize(
    ("type_", "status", "allowed"),
    [
        ("pto", "pending", True),
        ("pto", "approved", False),
        ("pto", "denied", False),
        ("pto", "canceled", False),
        ("pto", "recorded", False),
        ("sick", "recorded", False),
        ("sick", "pending", False),
        ("sick", "canceled", False),
        ("vacation", "pending", False),
        ("pto", "waiting", False),
    ],
)
def test_only_a_pending_pto_request_is_decided(type_: str, status: str, allowed: bool) -> None:
    request = pto_request(REPORT_ID, type=type_, status=status)

    assert can(MANAGER, Action.TIMEOFF_DECIDE, request) is allowed


@pytest.mark.parametrize(
    ("status", "start_offset_days", "allowed"),
    [
        ("pending", 10, True),
        ("pending", 0, True),
        ("pending", -3, True),
        ("approved", 1, True),  # the day before its first day
        ("approved", 0, False),  # on its first day
        ("approved", -1, False),
        ("recorded", 1, True),
        ("recorded", 0, False),
        ("denied", 10, False),
        ("canceled", 10, False),
    ],
)
def test_priya_cancels_until_the_day_before_an_approved_or_recorded_request(
    status: str, start_offset_days: int, allowed: bool
) -> None:
    request = pto_request(
        EMPLOYEE_ID,
        type="sick" if status == "recorded" else "pto",
        status=status,
        start_date=TODAY + timedelta(days=start_offset_days),
    )

    assert can(EMPLOYEE, Action.TIMEOFF_CANCEL, request, today=TODAY) is allowed


def test_a_cancel_without_today_is_denied() -> None:
    assert can(EMPLOYEE, Action.TIMEOFF_CANCEL, pto_request(EMPLOYEE_ID)) is False
    assert can(EMPLOYEE, Action.TIMEOFF_CANCEL, pto_request(EMPLOYEE_ID), today=None) is False


def test_today_must_be_a_date_not_a_datetime() -> None:
    with pytest.raises(TypeError, match="today"):
        can(
            EMPLOYEE,
            Action.TIMEOFF_CANCEL,
            pto_request(EMPLOYEE_ID),
            today=cast(date, datetime(2026, 10, 21, tzinfo=UTC)),
        )


@pytest.mark.parametrize(
    ("actor", "action"),
    [
        (EMPLOYEE, Action.TIMEOFF_DECIDE),
        (MANAGER, Action.TIMEOFF_DECIDE),
        (EMPLOYEE, Action.TIMEOFF_CANCEL),
    ],
)
def test_decide_and_cancel_deny_a_person_resource(actor: Actor, action: Action) -> None:
    # They need a request's type, status, and first date, which a person doesn't have.
    assert can(actor, action, PersonResource(actor.person_id), today=TODAY) is False
    assert can(actor, action, PersonResource(REPORT_ID), today=TODAY) is False


def test_a_request_resource_cannot_be_used_to_make_a_request() -> None:
    assert can(EMPLOYEE, Action.TIMEOFF_REQUEST, pto_request(EMPLOYEE_ID)) is False


def test_timeoff_read_accepts_a_person_or_a_request_and_uses_the_person() -> None:
    assert can(MANAGER, Action.TIMEOFF_READ, PersonResource(REPORT_ID)) is True
    assert can(MANAGER, Action.TIMEOFF_READ, pto_request(REPORT_ID)) is True
    assert can(EMPLOYEE, Action.TIMEOFF_READ, pto_request(COLLEAGUE_ID)) is False


@pytest.mark.parametrize("resource", [None, "a person", {"person_id": EMPLOYEE_ID}, object()])
@pytest.mark.parametrize(
    "action",
    [
        Action.TIMEOFF_READ,
        Action.TIMEOFF_REQUEST,
        Action.TIMEOFF_DECIDE,
        Action.TIMEOFF_CANCEL,
    ],
)
def test_a_wrong_resource_type_is_denied_even_for_hr(action: Action, resource: object) -> None:
    assert can(HR, action, cast(PersonResource, resource), today=TODAY) is False


@pytest.mark.parametrize(
    "bad",
    [
        {"person_id": str(EMPLOYEE_ID)},
        {"type": None},
        {"status": 3},
        {"start_date": "2026-10-21"},
        {"start_date": datetime(2026, 10, 21, tzinfo=UTC)},
    ],
)
def test_a_request_resource_refuses_a_field_of_the_wrong_type(bad: dict[str, object]) -> None:
    fields: dict[str, Any] = {
        "person_id": EMPLOYEE_ID,
        "type": "pto",
        "status": "pending",
        "start_date": TODAY,
    }

    with pytest.raises(TypeError, match=next(iter(bad))):
        TimeOffRequestResource(**{**fields, **bad})


# --- Cases ---


def a_case(person_id: UUID, *, status: str = "new", read: bool = True) -> CaseResource:
    return CaseResource(person_id, status, words_read_by_actor=read)


@pytest.mark.parametrize("action", CASE_ACTIONS)
@pytest.mark.parametrize("actor", [MANAGER, SKIP])
def test_a_manager_is_refused_every_case_action_on_a_reports_case(
    actor: Actor, action: Action
) -> None:
    # Direct and indirect, with the words read and not: a manager never sees a case.
    for read in (True, False):
        for status in ("new", "in_review", "closed"):
            assert can(actor, action, a_case(REPORT_ID, status=status, read=read)) is False
    assert can(actor, action, PersonResource(REPORT_ID)) is False


@pytest.mark.parametrize("status", ["new", "in_review", "closed"])
def test_the_person_reads_their_cases_status_and_nothing_else(status: str) -> None:
    own = a_case(EMPLOYEE_ID, status=status)

    assert can(EMPLOYEE, Action.CASE_READ_STATUS, own) is True
    for action in (Action.CASE_READ_SUMMARY, Action.CASE_READ_TEXT, Action.CASE_UPDATE_STATUS):
        assert can(EMPLOYEE, action, own) is False


def test_hr_changes_a_status_only_after_reading_the_words() -> None:
    assert can(HR, Action.CASE_UPDATE_STATUS, a_case(EMPLOYEE_ID, read=True)) is True
    assert can(HR, Action.CASE_UPDATE_STATUS, a_case(EMPLOYEE_ID, read=False)) is False
    # Reading the words themselves needs no earlier reading, or no one could start.
    assert can(HR, Action.CASE_READ_TEXT, a_case(EMPLOYEE_ID, read=False)) is True
    assert can(HR, Action.CASE_READ_SUMMARY, a_case(EMPLOYEE_ID, read=False)) is True


def test_hr_never_reads_or_decides_their_own_case_but_sees_its_status() -> None:
    own = a_case(HR_ID)

    assert can(HR, Action.CASE_READ_STATUS, own) is True
    for action in (Action.CASE_READ_SUMMARY, Action.CASE_READ_TEXT, Action.CASE_UPDATE_STATUS):
        assert can(HR, action, own) is False


def test_opening_a_case_is_only_for_oneself_and_takes_a_person() -> None:
    assert can(EMPLOYEE, Action.CASE_OPEN, PersonResource(EMPLOYEE_ID)) is True
    assert can(EMPLOYEE, Action.CASE_OPEN, PersonResource(COLLEAGUE_ID)) is False
    # HR opens their own case like anyone, and no one opens one for another person.
    assert can(HR, Action.CASE_OPEN, PersonResource(COLLEAGUE_ID)) is False
    assert can(EMPLOYEE, Action.CASE_OPEN, a_case(EMPLOYEE_ID)) is False


@pytest.mark.parametrize("action", CASE_ACTIONS)
@pytest.mark.parametrize("resource", [None, "a case", {"person_id": EMPLOYEE_ID}, object()])
def test_a_wrong_resource_type_is_denied_for_a_case_action_even_for_hr(
    action: Action, resource: object
) -> None:
    assert can(HR, action, cast(CaseResource, resource)) is False


@pytest.mark.parametrize("action", [Action.CASE_LIST, Action.CASE_OPEN])
def test_a_case_resource_cannot_stand_in_for_a_person(action: Action) -> None:
    assert can(HR, action, a_case(HR_ID)) is False


@pytest.mark.parametrize(
    "bad",
    [
        {"person_id": str(EMPLOYEE_ID)},
        {"status": None},
        {"status": 3},
        {"words_read_by_actor": "yes"},
        {"words_read_by_actor": 1},
        {"words_read_by_actor": None},
    ],
)
def test_a_case_resource_refuses_a_field_of_the_wrong_type(bad: dict[str, object]) -> None:
    fields: dict[str, Any] = {
        "person_id": EMPLOYEE_ID,
        "status": "new",
        "words_read_by_actor": True,
    }

    with pytest.raises(TypeError, match=next(iter(bad))):
        CaseResource(**{**fields, **bad})


def test_hr_who_is_not_flagged_hr_has_no_case_access() -> None:
    not_hr = Actor(
        HR_ID, TENANT_ID, is_hr_admin=False, report_ids=frozenset(), direct_report_ids=frozenset()
    )

    for action in (Action.CASE_READ_SUMMARY, Action.CASE_READ_TEXT, Action.CASE_UPDATE_STATUS):
        assert can(not_hr, action, a_case(EMPLOYEE_ID)) is False
    assert can(not_hr, Action.CASE_LIST, PersonResource(HR_ID)) is False
