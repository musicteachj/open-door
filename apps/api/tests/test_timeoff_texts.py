"""The fixed refusal texts: one plain, figure-free sentence per code the service can return."""

import ast
import re
from pathlib import Path

import pytest

from app.modules.timeoff import service
from app.modules.timeoff.texts import REFUSAL_TEXTS, refusal_text

SERVICE_SOURCE = Path(service.__file__).read_text()
EM_DASH = chr(0x2014)
THIRD_PARTY_PRONOUNS = re.compile(r"\b(he|she|him|her|his|hers|they|them|their|theirs)\b", re.I)


def codes_the_service_refuses_with() -> set[str]:
    """Every string the service passes to `Refused(...)`, found in its source: through the module's
    own constants for the service's codes. A code taken from the engine's answer (an expression, not
    a name) is covered by `PROBLEM_CODES`, which `test_the_service_lists_every_code` checks."""
    tree = ast.parse(SERVICE_SOURCE)
    constants = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Refused"
            and node.args
        ):
            first = node.args[0]
            if isinstance(first, ast.Name) and first.id in constants:
                found.add(constants[first.id])
            elif isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.add(first.value)
    return found


def test_every_code_the_service_can_return_has_a_text() -> None:
    assert set(service.REFUSAL_CODES) == set(REFUSAL_TEXTS)
    assert len(set(service.REFUSAL_CODES)) == len(service.REFUSAL_CODES)


def test_the_service_lists_every_code_it_refuses_with() -> None:
    found = codes_the_service_refuses_with()

    # The service's own five, plus overlaps from the database's constraint.
    assert found == {
        "not-found",
        "not-allowed",
        "status-changed",
        "already-started",
        "no-approver",
        "overlaps",
    }
    assert found <= set(service.REFUSAL_CODES)


@pytest.mark.parametrize("code", sorted(REFUSAL_TEXTS))
def test_a_text_is_one_plain_sentence_without_figures(code: str) -> None:
    text = REFUSAL_TEXTS[code]

    assert text == refusal_text(code)
    assert text[0].isupper()
    assert text.endswith(".")
    assert not re.search(r"[.!?]\s", text), "one sentence only"
    assert not re.search(r"\d", text), "no figures"
    assert EM_DASH not in text
    assert not THIRD_PARTY_PRONOUNS.search(text)


def test_an_unknown_code_has_no_text() -> None:
    with pytest.raises(KeyError):
        refusal_text("made-up")


def test_the_out_of_range_text_covers_every_case_the_bounds_refuse() -> None:
    text = REFUSAL_TEXTS["out-of-range"].lower()

    # A past start (PTO), too far back (sick time), before the balance began or the hire date,
    # and an end after next year.
    for part in ("past", "sick", "too far back", "balance", "hire date", "next year"):
        assert part in text, part


def test_the_context_line_has_a_reason_for_exactly_the_codes_the_service_can_refuse_with() -> None:
    from app.ai import proposals

    assert set(proposals._FAILURE_REASONS) == set(service.REFUSAL_CODES)
