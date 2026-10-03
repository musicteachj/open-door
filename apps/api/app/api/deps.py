"""Dependencies the routes share."""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine


def get_engine(request: Request) -> AsyncEngine:
    """The engine the app's lifespan created.

    Without the lifespan there is no engine, and the request fails with a 500 whose logged cause
    says so, instead of an AttributeError from deep inside a route.
    """
    engine = getattr(request.app.state, "engine", None)
    if not isinstance(engine, AsyncEngine):
        msg = "No database engine: build the app with create_app() and run its lifespan."
        raise RuntimeError(msg)
    return engine
