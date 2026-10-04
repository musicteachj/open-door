"""Each tier of what the API shows about a person has exactly its own fields, in camelCase."""

import base64
import json
from uuid import uuid4

import pytest

from app.api.schemas import CamelModel
from app.modules.people.queries import DirectoryCursor
from app.modules.people.schemas import (
    DepartmentRef,
    DirectoryCard,
    LocationRef,
    Me,
    PersonRef,
    PrivateDetails,
)

CARD_FIELDS = {
    "id",
    "givenName",
    "familyName",
    "title",
    "department",
    "location",
    "manager",
    "workEmail",
}
ME_ONLY_FIELDS = {"employmentType", "isManager", "isHrAdmin", "personaKey", "tenantExpiresAt"}
PRIVATE_FIELDS = {"personalEmail", "phone", "homeAddress", "dateOfBirth"}
PERSON_REF_FIELDS = {"id", "givenName", "familyName"}
DEPARTMENT_REF_FIELDS = {"id", "name"}
LOCATION_REF_FIELDS = {"id", "name", "state"}


def json_fields(model: type[CamelModel]) -> set[str]:
    return set(model.model_json_schema(by_alias=True)["properties"])


def encoded(key: object) -> str:
    """A key encoded the way a real cursor is, so only its content is wrong."""
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode().rstrip("=")


def test_the_directory_card_has_none_of_the_me_only_or_private_fields() -> None:
    assert json_fields(DirectoryCard) == CARD_FIELDS
    assert json_fields(DirectoryCard).isdisjoint(ME_ONLY_FIELDS | PRIVATE_FIELDS)


def test_me_adds_only_the_me_only_fields() -> None:
    assert json_fields(Me) == CARD_FIELDS | ME_ONLY_FIELDS


def test_the_nested_references_have_exactly_their_own_fields() -> None:
    # A card embeds these, so a private field added to one would reach every directory page.
    assert json_fields(PersonRef) == PERSON_REF_FIELDS
    assert json_fields(DepartmentRef) == DEPARTMENT_REF_FIELDS
    assert json_fields(LocationRef) == LOCATION_REF_FIELDS
    for reference in (PersonRef, DepartmentRef, LocationRef):
        assert json_fields(reference).isdisjoint(ME_ONLY_FIELDS | PRIVATE_FIELDS)


def test_private_details_are_a_separate_model() -> None:
    assert json_fields(PrivateDetails) == PRIVATE_FIELDS
    assert not issubclass(PrivateDetails, DirectoryCard)


def test_a_directory_cursor_comes_back_as_it_went_out() -> None:
    cursor = DirectoryCursor("O'Brien", "Zoë", uuid4())

    assert DirectoryCursor.decode(cursor.encode()) == cursor


@pytest.mark.parametrize(
    "garbage",
    [
        "",
        "not-a-cursor",
        encoded([]),
        encoded(["Abbott", "Mina"]),
        encoded([1, 2, 3]),
        encoded(["Abbott", "Mina", 3]),
        encoded(["Abbott", "Mina", "not-a-uuid"]),
        encoded({"family": "Abbott", "given": "Mina", "id": "x"}),
    ],
)
def test_a_cursor_the_api_did_not_issue_is_refused(garbage: str) -> None:
    with pytest.raises(ValueError, match="Not a directory cursor"):
        DirectoryCursor.decode(garbage)


# Postgres text can't hold NUL, and a lone surrogate has no UTF-8 encoding. Either one decodes
# from JSON, but makes the directory query fail.
UNSTORABLE_NAMES = ["\x00", "Ab\x00bott", "\ud800", "Mi\udfffna"]


@pytest.mark.parametrize("name", UNSTORABLE_NAMES)
def test_a_cursor_with_a_name_postgres_cannot_hold_is_refused(name: str) -> None:
    for key in ([name, "Mina", str(uuid4())], ["Abbott", name, str(uuid4())]):
        with pytest.raises(ValueError, match="Not a directory cursor"):
            DirectoryCursor.decode(encoded(key))
