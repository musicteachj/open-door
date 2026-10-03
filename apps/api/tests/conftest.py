from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

# Unit tests never reach a database: port 1 refuses instantly.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://opendoor:opendoor@127.0.0.1:1/opendoor"


@pytest.fixture
def settings() -> Settings:
    # Pin every field, so a developer's exported environment variables can't change test behavior.
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=UNREACHABLE_DATABASE_URL,
        migration_database_url=None,
        cleanup_database_url=None,
        app_origin="http://localhost:5173",
        log_level="INFO",
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
