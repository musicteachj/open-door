import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import get_engine


def request_for(app: FastAPI) -> Request:
    return Request({"type": "http", "app": app})


def test_get_engine_returns_the_engine_the_lifespan_created(
    app: FastAPI, client: TestClient
) -> None:
    engine = get_engine(request_for(app))

    assert isinstance(engine, AsyncEngine)
    assert engine is app.state.engine


def test_a_missing_engine_is_a_clear_error_not_an_attribute_error(app: FastAPI) -> None:
    # No TestClient, so the lifespan never ran and never created the engine.
    with pytest.raises(RuntimeError, match="lifespan"):
        get_engine(request_for(app))
