"""Each tier of what the API shows about a person has exactly its own fields, in camelCase."""

from app.api.schemas import CamelModel
from app.modules.people.schemas import DepartmentRef, DirectoryCard, LocationRef, Me, PersonRef

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
