"""Real 404 and 422 responses fit the `Problem` model the schema publishes."""

from uuid import uuid4

import pytest

from app.api.problems import Problem
from tests.integration.conftest import Browser

pytestmark = pytest.mark.integration


def test_a_missing_person_and_a_failed_validation_match_the_problem_model(
    browser: Browser,
) -> None:
    browser.start_sandbox()

    missing = browser.client.get(f"/api/v1/people/{uuid4()}")
    invalid = browser.client.get("/api/v1/people", params={"limit": 0})

    assert (missing.status_code, invalid.status_code) == (404, 422)
    for response in (missing, invalid):
        problem = Problem.model_validate(response.json())
        assert set(response.json()) == set(problem.model_dump(by_alias=True, exclude_none=True))
    assert Problem.model_validate(missing.json()).errors is None
    errors = Problem.model_validate(invalid.json()).errors
    assert errors is not None
    assert errors[0].loc == ["query", "limit"]
