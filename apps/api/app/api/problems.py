"""How the OpenAPI schema describes errors: the real problem-details body, not FastAPI's default.

`app/core/problems.py` sends every error as RFC 9457 problem details. `Problem` mirrors that body,
`problem_responses` declares it on a route, and `document_problems_as_problem_json` files it under
the right media type, so the generated web client's error types are the shapes the API sends.
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI

from app.api.schemas import CamelModel
from app.core.problems import PROBLEM_JSON

PROBLEM_SCHEMA = "Problem"
# FastAPI's own 422 body, which `Problem` replaces.
FASTAPI_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")


class FieldError(CamelModel):
    """One failed field on a 422: where it was, what was wrong, and the error's kind."""

    loc: list[str | int]
    msg: str
    type: str


class Problem(CamelModel):
    """The body of every error response. Only a 422 has `errors`."""

    type: str
    title: str
    status: int
    instance: str
    detail: str | None = None
    request_id: str | None = None
    errors: list[FieldError] | None = None


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """The `responses=` entries for these error statuses, each described as a `Problem`.

    The return type is wide because FastAPI's `responses` parameter is invariant.
    """
    return {
        status: {"model": Problem, "description": HTTPStatus(status).phrase} for status in statuses
    }


def _move_problems_to_problem_json(schema: dict[str, Any]) -> None:
    """Refile each `Problem` response as `application/problem+json`. Safe to run twice."""
    problem_ref = f"#/components/schemas/{PROBLEM_SCHEMA}"
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            for response in operation.get("responses", {}).values():
                content = response.get("content", {})
                json_content = content.get("application/json")
                if json_content is not None and json_content.get("schema") == {"$ref": problem_ref}:
                    del content["application/json"]
                    content[PROBLEM_JSON] = json_content
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    # FastAPI adds its own 422 to any route with input. A route that didn't declare it as a
    # `Problem` would keep a reference to a schema removed below, so every such 422 becomes one.
    default_422 = {"$ref": f"#/components/schemas/{FASTAPI_VALIDATION_SCHEMAS[0]}"}
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            response = operation.get("responses", {}).get("422")
            content = response.get("content", {}) if response else {}
            default = content.get("application/json")
            if default is not None and default.get("schema") == default_422:
                del content["application/json"]
                content[PROBLEM_JSON] = {"schema": {"$ref": problem_ref}}
                if PROBLEM_SCHEMA not in components:
                    definitions = Problem.model_json_schema(
                        ref_template="#/components/schemas/{model}"
                    )
                    components.update(definitions.pop("$defs", {}))
                    components[PROBLEM_SCHEMA] = definitions
    for name in FASTAPI_VALIDATION_SCHEMAS:
        components.pop(name, None)


def document_problems_as_problem_json(app: FastAPI) -> None:
    """Make the generated schema file `Problem` under `application/problem+json`.

    FastAPI files every response model as `application/json`, and it adds its own 422 body to
    any route with input. Every such route declares its 422 as a `Problem`, so the default
    schemas are dropped.
    """
    build = app.openapi

    def openapi() -> dict[str, Any]:
        schema = build()
        _move_problems_to_problem_json(schema)
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
