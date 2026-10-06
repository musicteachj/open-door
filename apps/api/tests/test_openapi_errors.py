"""The OpenAPI schema describes the errors the API really sends: problem details, not FastAPI's."""

import json
from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.problems import document_problems_as_problem_json
from app.api.v1.router import api_router
from app.modules.identity.deps import signed_in

PROBLEM_REF = "#/components/schemas/Problem"
HTTP_METHODS = {"get", "put", "post", "patch", "delete"}


def _routes(router: Any) -> Iterator[APIRoute]:
    """Every route under a router. FastAPI 0.142 nests included routers instead of flattening."""
    for route in router.routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _routes(original)
        elif isinstance(route, APIRoute):
            yield route


def _operation_id(route: APIRoute) -> str:
    assert route.operation_id is not None
    return route.operation_id


def _calls(dependant: Dependant) -> Iterator[Any]:
    for dependency in dependant.dependencies:
        yield dependency.call
        yield from _calls(dependency)


def _operations(app: FastAPI) -> dict[str, dict[str, Any]]:
    schema = app.openapi()
    return {
        operation["operationId"]: operation
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method in HTTP_METHODS
    }


def _declared(operation: dict[str, Any]) -> dict[str, Any]:
    responses: dict[str, Any] = operation["responses"]
    return responses


def test_the_walk_finds_every_operation_in_the_schema(app: FastAPI) -> None:
    walked = {_operation_id(route) for route in _routes(api_router)}

    assert walked == set(_operations(app))
    assert len(walked) >= 9


def test_nothing_references_fastapis_default_validation_error(app: FastAPI) -> None:
    text = json.dumps(app.openapi())

    assert "HTTPValidationError" not in text
    assert "ValidationError" not in text


def test_problem_is_filed_under_problem_json_never_plain_json(app: FastAPI) -> None:
    problem_responses = [
        (operation_id, status, response)
        for operation_id, operation in _operations(app).items()
        for status, response in _declared(operation).items()
        if "content" in response and PROBLEM_REF in json.dumps(response["content"])
    ]

    assert problem_responses
    for operation_id, status, response in problem_responses:
        assert list(response["content"]) == ["application/problem+json"], (operation_id, status)
        assert response["content"]["application/problem+json"]["schema"] == {"$ref": PROBLEM_REF}


def test_every_operation_with_input_declares_a_422_problem(app: FastAPI) -> None:
    operations = _operations(app)
    with_input = [
        operation_id
        for operation_id, operation in operations.items()
        if operation.get("parameters") or "requestBody" in operation
    ]

    assert with_input
    for operation_id in with_input:
        content = _declared(operations[operation_id]).get("422", {}).get("content", {})
        assert content == {"application/problem+json": {"schema": {"$ref": PROBLEM_REF}}}, (
            operation_id
        )


def test_every_signed_in_operation_declares_a_401(app: FastAPI) -> None:
    operations = _operations(app)
    signed_in_ids = [
        _operation_id(route)
        for route in _routes(api_router)
        if signed_in in _calls(route.dependant)
    ]

    assert len(signed_in_ids) >= 7
    for operation_id in signed_in_ids:
        assert "401" in _declared(operations[operation_id]), operation_id


def test_every_operation_that_changes_state_declares_a_403(app: FastAPI) -> None:
    changes = [
        _operation_id(route)
        for route in _routes(api_router)
        if not (route.methods or set()) <= {"GET", "HEAD"}
    ]
    operations = _operations(app)

    assert changes
    for operation_id in changes:
        assert "403" in _declared(operations[operation_id]), operation_id


def test_every_operation_with_a_path_parameter_declares_a_404(app: FastAPI) -> None:
    operations = _operations(app)
    looked_up = [
        _operation_id(route) for route in _routes(api_router) if route.dependant.path_params
    ]

    assert looked_up
    for operation_id in looked_up:
        assert "404" in _declared(operations[operation_id]), operation_id


def test_the_schema_is_stable_across_calls(app: FastAPI) -> None:
    assert app.openapi() == app.openapi()


def test_a_real_error_matches_the_problem_model(client: TestClient) -> None:
    from app.api.problems import Problem

    unauthorized = client.get("/api/v1/me")
    missing = client.get("/api/v1/no-such-route")

    for response, status in ((unauthorized, 401), (missing, 404)):
        assert response.status_code == status
        problem = Problem.model_validate(response.json())
        assert problem.status == status
        assert problem.request_id == response.headers["x-request-id"]
        assert set(response.json()) == set(problem.model_dump(by_alias=True, exclude_none=True))


def _refs(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from _refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item)


def test_a_route_that_forgets_to_declare_its_422_still_gets_a_problem_not_a_dangling_ref() -> None:
    forgetful = FastAPI()

    @forgetful.get("/things")
    def things(limit: int) -> dict[str, int]:
        return {"limit": limit}

    document_problems_as_problem_json(forgetful)
    schema = forgetful.openapi()

    content = schema["paths"]["/things"]["get"]["responses"]["422"]["content"]
    assert list(content) == ["application/problem+json"]
    assert content["application/problem+json"]["schema"] == {"$ref": PROBLEM_REF}
    components = schema["components"]["schemas"]
    for ref in _refs(schema):
        assert ref.startswith("#/components/schemas/"), ref
        assert ref.removeprefix("#/components/schemas/") in components, ref
