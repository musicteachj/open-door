"""A card says what it is (`kind`), so the web app can narrow the union without guessing."""

from typing import Any, get_args

import pytest
from pydantic import TypeAdapter, ValidationError

from app.ai.proposal_cards import CARD_TYPES, Card
from app.main import create_app

FIGURE = {"Minutes": 480, "Label": "8 hours (1 day)"}


def pair(key: str, figure: dict[str, Any] | None = FIGURE) -> dict[str, Any]:
    if figure is None:
        return {f"{key}Minutes": None, f"{key}Label": None}
    return {f"{key}{name}": value for name, value in figure.items()}


BASE = {"type": "pto", "startDate": "2026-11-09", "endDate": "2026-11-09", "partialMinutes": None}
CARDS: dict[str, dict[str, Any]] = {
    "request": {
        **BASE,
        "countedDays": [],
        "skippedDays": [],
        **pair("amount"),
        **pair("availableBefore"),
        **pair("availableAfter"),
        "warnings": [],
        "approver": None,
        "rules": [],
    },
    "decide": {
        **BASE,
        "requester": {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "A B",
            "title": "Designer",
        },
        **pair("amount"),
        **pair("availableAfter", None),
        "coverage": [],
        "decision": "approve",
        "rules": [],
    },
    "cancel": {
        **BASE,
        "status": "pending",
        **pair("amount"),
        **pair("returns", None),
        **pair("availableAfter", None),
        "rules": [],
    },
}


def test_each_card_model_has_its_own_kind() -> None:
    kinds = {
        name: get_args(model.model_fields["kind"].annotation) for name, model in CARD_TYPES.items()
    }
    assert kinds == {
        "timeoff.request": ("request",),
        "timeoff.decide": ("decide",),
        "timeoff.cancel": ("cancel",),
    }


@pytest.mark.parametrize("action", ["timeoff.request", "timeoff.decide", "timeoff.cancel"])
def test_a_stored_card_needs_its_own_kind(action: str) -> None:
    kind = action.split(".")[1]
    model = CARD_TYPES[action]
    good = model.model_validate({**CARDS[kind], "kind": kind})
    assert good.model_dump(mode="json", by_alias=True)["kind"] == kind
    with pytest.raises(ValidationError):
        model.model_validate(CARDS[kind])
    other = "cancel" if kind != "cancel" else "request"
    with pytest.raises(ValidationError):
        model.model_validate({**CARDS[kind], "kind": other})


def test_the_union_picks_a_card_by_its_kind() -> None:
    adapter: TypeAdapter[Any] = TypeAdapter(Card)
    for kind in CARDS:
        assert adapter.validate_python({**CARDS[kind], "kind": kind}).kind == kind


def test_the_openapi_schema_gives_the_card_a_discriminator_with_three_mappings() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    ref = schemas["ProposalOut"]["properties"]["card"]["$ref"]
    card = schemas[ref.rsplit("/", 1)[-1]]
    assert card["discriminator"]["propertyName"] == "kind"
    mapping = card["discriminator"]["mapping"]
    assert {k: v.rsplit("/", 1)[-1] for k, v in mapping.items()} == {
        "request": "RequestCard",
        "decide": "DecideCard",
        "cancel": "CancelCard",
    }
