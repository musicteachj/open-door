"""Which requests are API requests, judged by the path the router matches."""

from starlette.types import Scope

API_PREFIX = "/api/"


def route_path(scope: Scope) -> str:
    """The path the router matches: the request's path without the app's root path.

    Behind `uvicorn --root-path`, `scope["path"]` keeps the prefix and the router strips it, so a
    check on the raw path would miss every API route. This mirrors Starlette's routing.
    """
    path: str = scope["path"]
    root_path: str = scope.get("root_path", "")
    if root_path and path.startswith(root_path + "/"):
        return path[len(root_path) :]
    return path


def is_api_request(scope: Scope) -> bool:
    return route_path(scope).startswith(API_PREFIX)
