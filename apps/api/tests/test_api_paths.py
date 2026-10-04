import pytest
from starlette.types import Scope

from app.core.api_paths import is_api_request, route_path


def http_scope(path: str, root_path: str = "") -> Scope:
    return {"type": "http", "path": path, "root_path": root_path}


@pytest.mark.parametrize(
    ("root_path", "path", "is_api"),
    [
        pytest.param("", "/api/v1/me", True, id="no root path"),
        pytest.param("/od", "/od/api/v1/me", True, id="under a root path"),
        pytest.param("/od", "/odapi/x", False, id="a path that only starts like the root path"),
        pytest.param("/od", "/od", False, id="the root path itself"),
        # Starlette routes the raw path when it lacks the root path.
        pytest.param("/od", "/api/v1/me", True, id="the root path absent from the path"),
        pytest.param("", "/docs", False, id="outside the API"),
    ],
)
def test_a_request_is_an_api_request_when_the_router_matches_it_under_api(
    root_path: str, path: str, is_api: bool
) -> None:
    assert is_api_request(http_scope(path, root_path)) is is_api


@pytest.mark.parametrize(
    ("root_path", "path", "routed"),
    [
        pytest.param("", "/api/v1/me", "/api/v1/me", id="no root path"),
        pytest.param("/od", "/od/api/v1/me", "/api/v1/me", id="the root path is stripped"),
        pytest.param(
            "/od", "/odx/api", "/odx/api", id="a path that only starts like the root path"
        ),
        pytest.param("/od", "/od", "/od", id="the root path itself"),
        pytest.param("/od", "/api/v1/me", "/api/v1/me", id="the root path absent from the path"),
    ],
)
def test_the_route_path_is_the_path_without_the_root_path(
    root_path: str, path: str, routed: str
) -> None:
    assert route_path(http_scope(path, root_path)) == routed
