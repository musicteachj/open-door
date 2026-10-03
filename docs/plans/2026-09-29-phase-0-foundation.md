# Phase 0: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. **Project rule:** never commit, push, or open a PR without
> the owner's explicit OK for that action (see `CLAUDE.md`). Every "Propose the commit" step stops
> and waits.

**Goal:** A working skeleton of Open Door. A FastAPI backend with a health check, a React web app
that shows the API's status, a development Postgres, database migrations, and CI that runs every
check on every push and pull request.

**Architecture:** Two apps in one repository. `apps/api` is a FastAPI service managed by `uv`, with
settings validated at startup, request IDs on every response, errors in RFC 9457 problem-details
format, and Alembic migrations against Postgres with pgvector. `apps/web` is a Vite + React +
TypeScript app with Tailwind v4. It calls the API through a client that Orval generates from the
API's OpenAPI schema. A root `Makefile` runs everything, and GitHub Actions runs the same checks.

**Tech stack:**
- **API:** Python 3.13, uv 0.12, FastAPI 0.142, Starlette 1.7, SQLAlchemy 2.1 (async), asyncpg,
  Alembic 1.20, pydantic-settings; checked with pytest 9, ruff, mypy (strict) and import-linter.
- **Web:** Node 24, Vite 8, React 19, TypeScript 6, Tailwind CSS 4, TanStack Query 5, Orval 8,
  Vitest 5, Testing Library, oxlint and Prettier.
- **Database:** Postgres 17 with pgvector, in Docker Compose.
- **CI:** GitHub Actions.

**Spec:** [`../specs/2026-09-29-open-door-design.md`](../specs/2026-09-29-open-door-design.md) ·
**Roadmap:** [`../ROADMAP.md`](../ROADMAP.md)

---

## Decisions made while planning

Every command and code block below was run in a throwaway copy on 2026-09-29, and everything
passed. That covered 15 API tests, 4 web tests, ruff, strict mypy, import-linter, oxlint, Prettier,
the TypeScript build, and the OpenAPI and client drift checks. The exceptions are the steps that
need a running Postgres (migrations and the integration tests). Docker wasn't running, so those
are checked first when this plan is executed.

- **The Vite template now ships oxlint, not ESLint, and we keep it.** It is much faster, and it has
  the React, TypeScript, and accessibility (`jsx-a11y`) rules built in. The accessibility rules
  were confirmed to catch a missing `alt` attribute. The spec's CI table said "eslint"; this
  supersedes it.
- **TypeScript 6, not 7.** TypeScript 7 (the new native compiler) is the newest release, but the
  Vite template pins 6, and the surrounding tooling expects it.
- **`httpx2`, not `httpx`, for the API's test client.** Starlette 1.7 warns that `httpx` is
  deprecated for its test client, and the Anthropic SDK 1.x uses `httpx2` too.
- **Python 3.13.** uv downloads it automatically from `.python-version`. The system Python on this
  machine is 3.9, which is too old.
- **The API is an installable package (`app`)**, so pytest, Alembic, import-linter, and scripts all
  import it without `PYTHONPATH` tricks. `app/__init__.py` must exist before the first `uv add`, or
  the build fails.
- **The app starts through a factory** (`uvicorn --factory app.main:create_app`). No module-level
  app object means tests and the OpenAPI export can build the app with their own settings.
- **Request IDs use plain ASGI middleware**, which never buffers a streamed response. That matters
  in Phase 4, when the assistant streams its answers.
- **Orval's fetch client does not throw on a 503.** It returns `{ data, status }`, so the web app
  reads the API's own status from `data.data.status`.
- **Drift checks compare a fresh regeneration with the working tree, not with git.** A developer who
  regenerates the schema and the client before committing still passes `make check`, and CI (where
  the working tree is the commit) catches anything stale.
- **The development Postgres listens on port 5433**, not 5432, so it can't collide with a Postgres
  that is already installed.
- **No `docs/DESIGN.md` stub.** The dated design spec already fills that role.
- **One pull request per stage.** That follows the `CLAUDE.md` rule (a PR at each stage boundary),
  and it keeps each review small.

---

## Prerequisites (owner)

- [ ] **Install uv** (the Python package and project manager): `brew install uv`, then confirm with
      `uv --version` (0.12 or later).
- [ ] **Start Docker Desktop**, then confirm with `docker info --format '{{.ServerVersion}}'`, which
      should print a version rather than an error.
- Node 24 and npm 11 are already installed (`node -v` prints `v24.x`).

---

## File map

```
open-door/
├── .editorconfig                       Stage 1  editor defaults for every file type
├── .nvmrc                              Stage 1  Node 24, read by CI and nvm
├── .gitignore                          Stage 1  (modified) adds *.local and *.log
├── compose.yaml                        Stage 1  development Postgres 17 + pgvector on 127.0.0.1:5433
├── Makefile                            Stage 1, replaced in Stages 2 and 3
├── .pre-commit-config.yaml             Stage 3  ruff, gitleaks, and web lint and format hooks
├── _typos.toml                         Stage 3  spelling rules for the docs check (US English)
├── .github/
│   ├── dependabot.yml                  Stage 3  weekly grouped updates, targeting dev
│   └── workflows/
│       ├── ci.yml                      Stage 3  api and web jobs (filtered), docs and workflows
│       ├── security.yml                Stage 3  gitleaks, pip-audit, npm audit, weekly
│       └── changelog.yml               Stage 3  code changes need a CHANGELOG entry
├── apps/api/
│   ├── pyproject.toml                  project, dependencies, tool configuration
│   ├── uv.lock                         generated by uv
│   ├── .python-version                 3.13
│   ├── .env.example                    the committed list of environment variables
│   ├── alembic.ini                     generated by `alembic init`, then edited
│   ├── app/
│   │   ├── __init__.py                 package marker and __version__
│   │   ├── main.py                     create_app(): the application factory
│   │   ├── core/config.py              Settings, validated at startup
│   │   ├── core/request_id.py          X-Request-ID middleware and context variable
│   │   ├── core/logging.py             JSON log formatter
│   │   ├── core/problems.py            RFC 9457 problem-details error handlers
│   │   ├── db/engine.py                async engine factory and ping()
│   │   ├── db/base.py                  declarative Base with a naming convention
│   │   ├── api/v1/router.py            mounts every v1 route under /api/v1
│   │   ├── api/v1/health.py            GET /api/v1/health
│   │   └── domain/…                    pure-logic packages (import-linter enforced)
│   ├── migrations/                     Alembic: env.py, script.py.mako, versions/0001_enable_pgvector.py
│   ├── scripts/export_openapi.py       writes apps/web/openapi.json; --check mode for CI
│   └── tests/                          unit tests plus tests/integration (needs Postgres)
└── apps/web/
    ├── openapi.json                    generated by the API; the client's source
    ├── orval.config.ts                 client generation settings
    ├── scripts/check-api-client.mjs    fails if the generated client is stale
    ├── vite.config.ts                  React, Tailwind, the /api proxy, and Vitest
    ├── .oxlintrc.json / .prettierrc.json / .prettierignore
    └── src/
        ├── main.tsx                    React root with TanStack Query
        ├── App.tsx                     product name and API status
        ├── App.test.tsx
        ├── index.css                   Tailwind entry point
        ├── test/setup.ts               jest-dom matchers and cleanup
        └── api/generated.ts            generated by Orval: never edit by hand
```

---

# Stage 1: API foundation

**Branch:** `feat/phase-0-api-foundation`, off `dev`. It already exists and holds this plan.
**Ends with:** the API answering `/api/v1/health` against a real Postgres, with every check passing
through `make check-api`.

### Task 1: Repository-level files

**Files:**
- Create: `.editorconfig`, `.nvmrc`, `compose.yaml`
- Modify: `.gitignore` (append two lines)

- [ ] **Step 1: Create `.editorconfig`**

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 2

[*.py]
indent_size = 4

[*.toml]
indent_size = 4

[Makefile]
indent_style = tab

[*.md]
trim_trailing_whitespace = false
```

- [ ] **Step 2: Create `.nvmrc`**

```
24
```

- [ ] **Step 3: Create `compose.yaml`**

```yaml
# The development database only. It binds to 127.0.0.1, so nothing outside this machine can reach
# it, and its password is a throwaway used nowhere else. Port 5433 avoids colliding with a Postgres
# that may already be installed on 5432.
# A fixed project name, so every checkout (including git worktrees) shares one database.
name: open-door
services:
  db:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: opendoor
      POSTGRES_PASSWORD: opendoor
      POSTGRES_DB: opendoor
    ports:
      - "127.0.0.1:5433:5432"
    volumes:
      - db-data:/var/lib/postgresql/data
    # Probe over TCP: on a fresh volume, Postgres first runs a socket-only setup server, which
    # would pass a socket probe before the real server is up.
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U opendoor -d opendoor"]
      interval: 2s
      timeout: 5s
      retries: 30

volumes:
  db-data:
```

- [ ] **Step 4: Append to `.gitignore`** (at the end of the "OS and editors" block)

```
*.local
*.log
```

- [ ] **Step 5: Start the database and confirm it is healthy**

Run: `docker compose up --detach --wait db && docker compose ps`
Expected: the `db` service shows `healthy`.

### Task 2: The API project and its dependencies

**Files:**
- Create: `apps/api/.python-version`, `apps/api/pyproject.toml`, `apps/api/app/__init__.py`,
  `apps/api/.env.example`
- Create (empty package markers): `apps/api/app/api/__init__.py`, `apps/api/app/api/v1/__init__.py`,
  `apps/api/app/core/__init__.py`, `apps/api/app/db/__init__.py`, `apps/api/tests/__init__.py`,
  `apps/api/tests/integration/__init__.py`
- Create: `apps/api/app/domain/__init__.py`, `apps/api/app/domain/timeoff/__init__.py`
- Generated: `apps/api/uv.lock`

- [ ] **Step 1: Create `apps/api/.python-version`**

```
3.13
```

- [ ] **Step 2: Create `apps/api/pyproject.toml`**

```toml
[project]
name = "open-door-api"
version = "0.0.0"
description = "The Open Door API: FastAPI, Postgres, and the assistant."
requires-python = ">=3.13"
dependencies = []

[build-system]
requires = ["uv_build>=0.12,<0.13"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "app"
module-root = ""
```

- [ ] **Step 3: Create `apps/api/app/__init__.py`.** This must exist before the first `uv add`,
      because uv builds the package to install it.

```python
"""The Open Door API."""

from importlib.metadata import version

# The single source of truth is `version` in pyproject.toml; uv sync always installs the package.
__version__ = version("open-door-api")
```

- [ ] **Step 4: Create the empty package markers**

Run: `cd apps/api && mkdir -p app/api/v1 app/core app/db app/domain/timeoff tests/integration scripts && touch app/api/__init__.py app/api/v1/__init__.py app/core/__init__.py app/db/__init__.py tests/__init__.py tests/integration/__init__.py`

- [ ] **Step 5: Create `apps/api/app/domain/__init__.py`**

```python
"""Pure domain logic. Nothing under this package may import a framework.

import-linter enforces the rule (see `[tool.importlinter]` in pyproject.toml), so the time-off
engine and anything like it stays testable with plain values and runs anywhere.
"""
```

- [ ] **Step 6: Create `apps/api/app/domain/timeoff/__init__.py`**

```python
"""The time-off engine. It arrives in Phase 5."""
```

- [ ] **Step 7: Add the dependencies**

Run: `cd apps/api && uv add fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic pydantic-settings && uv add --dev pytest pytest-asyncio httpx2 ruff mypy import-linter`
Expected: uv downloads Python 3.13 if needed, then writes `uv.lock` and the dependency lists into
`pyproject.toml`.

- [ ] **Step 8: Confirm the package imports**

Run: `cd apps/api && uv run python -c "import app, fastapi, sqlalchemy; print(app.__version__, fastapi.__version__, sqlalchemy.__version__)"`
Expected: `0.0.0 0.142.0 2.1.1` (or newer patch versions).

- [ ] **Step 9: Create `apps/api/.env.example`, then copy it to `.env`**

```
# Copy to apps/api/.env for local development: cp .env.example .env
# This file is committed. Real secrets never go in it.
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://opendoor:opendoor@127.0.0.1:5433/opendoor
LOG_LEVEL=INFO
```

Run: `cd apps/api && cp .env.example .env`
(`.env` is git-ignored.)

### Task 3: Tool configuration

**Files:**
- Modify: `apps/api/pyproject.toml` (append to the end)

- [ ] **Step 1: Append the tool configuration to `apps/api/pyproject.toml`**

```toml

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "UP", "B", "SIM", "ASYNC", "DTZ", "S", "PT", "RUF"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]

[tool.mypy]
strict = true
plugins = ["pydantic.mypy"]
files = ["app", "tests", "scripts", "migrations"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = "-ra --strict-markers"
# A deprecation warning fails the run, so upgrades surface breakage early.
filterwarnings = ["error"]
markers = ["integration: needs the development Postgres running (make db)"]

[tool.importlinter]
root_package = "app"
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Domain code imports no framework"
type = "forbidden"
source_modules = ["app.domain"]
# Every framework and I/O dependency the domain must never touch. Add each new one here.
forbidden_modules = [
    "fastapi",
    "starlette",
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "uvicorn",
    "httpx",
    "httpx2",
    "pydantic",
    "pydantic_settings",
    "anthropic",
    "app.api",
    "app.core",
    "app.db",
]
```

- [ ] **Step 2: Confirm the import rule holds**

Run: `cd apps/api && uv run lint-imports`
Expected: `Domain code imports no framework KEPT` and `Contracts: 1 kept, 0 broken.`

### Task 4: Settings, validated at startup

**Files:**
- Create: `apps/api/app/core/config.py`
- Test: `apps/api/tests/test_config.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_config.py`

```python
import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_a_missing_database_url_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_the_database_url_must_use_the_asyncpg_driver() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg"):
        Settings(_env_file=None, database_url="postgresql://opendoor:opendoor@localhost/opendoor")


def test_defaults_apply_when_only_the_database_url_is_set() -> None:
    settings = Settings(
        _env_file=None, database_url="postgresql+asyncpg://opendoor:opendoor@localhost/opendoor"
    )
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_config.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'app.core.config'`.

- [ ] **Step 3: Write `apps/api/app/core/config.py`**

```python
"""Application settings, read from the environment and validated once at startup."""

from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every setting the API reads. A missing or malformed value stops the process at boot."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: PostgresDsn
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def require_asyncpg_driver(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+asyncpg":
            msg = "DATABASE_URL must use the postgresql+asyncpg:// scheme"
            raise ValueError(msg)
        return value


@lru_cache
def get_settings() -> Settings:
    """Read settings once per process."""
    return Settings()
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/test_config.py -q`
Expected: `3 passed`.

### Task 5: Request IDs

**Files:**
- Create: `apps/api/app/core/request_id.py`
- Test: `apps/api/tests/test_request_id.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_request_id.py`

```python
import re
from collections.abc import Iterator

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.request_id import RequestIdMiddleware, request_id_var

GENERATED_ID = re.compile(r"[0-9a-f]{32}")


async def echo_request_id(request: Request) -> PlainTextResponse:
    """Report the ID the way the rest of the app sees it: the context variable and request state."""
    return PlainTextResponse(f"{request_id_var.get()}|{request.state.request_id}")


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = Starlette(routes=[Route("/", echo_request_id)])
    app.add_middleware(RequestIdMiddleware)
    with TestClient(app) as test_client:
        yield test_client


def test_every_response_carries_a_generated_request_id(client: TestClient) -> None:
    response = client.get("/")

    request_id = response.headers["X-Request-ID"]
    assert GENERATED_ID.fullmatch(request_id)
    assert response.text == f"{request_id}|{request_id}"


def test_a_well_formed_incoming_request_id_is_reused(client: TestClient) -> None:
    response = client.get("/", headers={"X-Request-ID": "trace-42.a_b"})

    assert response.headers["X-Request-ID"] == "trace-42.a_b"
    assert response.text == "trace-42.a_b|trace-42.a_b"


def test_a_malformed_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/", headers={"X-Request-ID": "not allowed; x=1"})

    assert GENERATED_ID.fullmatch(response.headers["X-Request-ID"])


def test_the_request_id_does_not_leak_past_the_request(client: TestClient) -> None:
    client.get("/")

    assert request_id_var.get() is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_request_id.py -q`
Expected: collection error, `No module named 'app.core.request_id'`.

- [ ] **Step 3: Write `apps/api/app/core/request_id.py`**

```python
"""Give every request an ID, echo it to the client, and make it available to logs and errors."""

import re
import uuid
from contextvars import ContextVar

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdMiddleware:
    """Pure ASGI middleware, so it never buffers a streamed response.

    A well-formed incoming X-Request-ID is reused, which lets a caller correlate its own logs with
    ours. Anything else is replaced with a fresh ID, so a client cannot inject arbitrary text into
    the logs.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        if incoming is not None and _VALID_REQUEST_ID.fullmatch(incoming):
            request_id = incoming
        else:
            request_id = uuid.uuid4().hex

        # Error handlers run outside this middleware, after the context variable is reset, so
        # the ID also goes on the request state where they can read it.
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/test_request_id.py -q`
Expected: `4 passed`.

### Task 6: JSON logs

**Files:**
- Create: `apps/api/app/core/logging.py`
- Test: `apps/api/tests/test_logging.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_logging.py`

```python
import json
import logging

from app.core.logging import JsonFormatter
from app.core.request_id import request_id_var


def make_record(message: str) -> logging.LogRecord:
    return logging.LogRecord("app.test", logging.INFO, __file__, 1, message, None, None)


def test_a_log_line_is_one_json_object() -> None:
    line = JsonFormatter().format(make_record("hello"))

    entry = json.loads(line)
    assert entry["level"] == "INFO"
    assert entry["logger"] == "app.test"
    assert entry["message"] == "hello"
    assert "requestId" not in entry


def test_a_log_line_inside_a_request_carries_its_id() -> None:
    token = request_id_var.set("trace-42")
    try:
        entry = json.loads(JsonFormatter().format(make_record("hello")))
    finally:
        request_id_var.reset(token)

    assert entry["requestId"] == "trace-42"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_logging.py -q`
Expected: collection error, `No module named 'app.core.logging'`.

- [ ] **Step 3: Write `apps/api/app/core/logging.py`**

```python
"""Structured JSON logs, one object per line, each carrying the request ID when there is one."""

import json
import logging
from datetime import UTC, datetime

from app.core.request_id import request_id_var


class JsonFormatter(logging.Formatter):
    """Format a log record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or request_id_var.get()
        if request_id is not None:
            entry["requestId"] = request_id
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging(level: str) -> None:
    """Send every log record, including uvicorn's, through the JSON formatter."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/test_logging.py -q`
Expected: `2 passed`.

### Task 7: Errors as problem details

**Files:**
- Create: `apps/api/app/core/problems.py`
- Test: `apps/api/tests/test_problems.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_problems.py`

```python
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.problems import install_problem_handlers
from app.core.request_id import RequestIdMiddleware


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_problem_handlers(app)

    @app.get("/items")
    async def list_items(limit: int) -> dict[str, int]:
        return {"limit": limit}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("database password is hunter2")

    # The unhandled-error test needs the 500 response, not the exception re-raised.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_an_unknown_route_returns_problem_details(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "instance": "/does-not-exist",
        "requestId": response.headers["X-Request-ID"],
    }


def test_invalid_input_returns_problem_details_listing_each_error(client: TestClient) -> None:
    response = client.get("/items", params={"limit": "many"})

    body = response.json()
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert body["detail"] == "The request did not pass validation."
    assert body["errors"][0]["loc"] == ["query", "limit"]


def test_an_unhandled_error_hides_its_cause_and_keeps_the_request_id(client: TestClient) -> None:
    response = client.get("/boom")

    body = response.json()
    assert response.status_code == 500
    assert body["detail"] == "Something went wrong."
    assert "hunter2" not in response.text
    assert body["requestId"] == response.headers["X-Request-ID"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_problems.py -q`
Expected: collection error, `No module named 'app.core.problems'`.

- [ ] **Step 3: Write `apps/api/app/core/problems.py`**

```python
"""Errors as RFC 9457 problem details (`application/problem+json`), each carrying the request ID."""

import logging
from http import HTTPStatus
from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_id import REQUEST_ID_HEADER

PROBLEM_JSON = "application/problem+json"

logger = logging.getLogger(__name__)


def problem_response(
    request: Request,
    status_code: int,
    detail: str | None = None,
    extra: dict[str, object] | None = None,
) -> JSONResponse:
    """Build a problem-details response. `type` stays `about:blank` until we define our own."""
    request_id = getattr(request.state, "request_id", None)
    body: dict[str, object] = {
        "type": "about:blank",
        "title": HTTPStatus(status_code).phrase,
        "status": status_code,
        "instance": request.url.path,
    }
    if detail is not None:
        body["detail"] = detail
    if request_id is not None:
        body["requestId"] = request_id
    if extra:
        body.update(extra)
    headers = {REQUEST_ID_HEADER: request_id} if request_id is not None else None
    return JSONResponse(body, status_code=status_code, media_type=PROBLEM_JSON, headers=headers)


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, exc)
    phrase = HTTPStatus(exc.status_code).phrase
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail != phrase else None
    return problem_response(request, exc.status_code, detail)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, exc)
    errors = [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return problem_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "The request did not pass validation.",
        {"errors": errors},
    )


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.error("Unhandled error", exc_info=exc, extra={"request_id": request_id})
    return problem_response(request, status.HTTP_500_INTERNAL_SERVER_ERROR, "Something went wrong.")


def install_problem_handlers(app: FastAPI) -> None:
    """Route every error the API can produce through problem details."""
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/test_problems.py -q`
Expected: `3 passed`.

### Task 8: The database engine and ping

**Files:**
- Create: `apps/api/app/db/engine.py`, `apps/api/app/db/base.py`
- Test: `apps/api/tests/test_engine.py`

- [ ] **Step 1: Write the failing test** in `apps/api/tests/test_engine.py`

```python
from app.db.engine import create_engine, ping


async def test_ping_reports_an_unreachable_database_as_down() -> None:
    # Port 1 refuses connections at once, so this needs no running database.
    engine = create_engine("postgresql+asyncpg://nobody:nothing@127.0.0.1:1/nowhere")
    try:
        assert await ping(engine) is False
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd apps/api && uv run pytest tests/test_engine.py -q`
Expected: collection error, `No module named 'app.db.engine'`.

- [ ] **Step 3: Write `apps/api/app/db/engine.py`**

```python
"""The async database engine, and a cheap check that the database answers."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_engine(database_url: str) -> AsyncEngine:
    """Create the engine. Connections open lazily, so this never touches the database."""
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        # asyncpg's connect timeout, in seconds: a dead database fails fast instead of hanging.
        connect_args={"timeout": 5},
    )


async def ping(engine: AsyncEngine) -> bool:
    """Return True if the database answers `SELECT 1`, False if it can't be reached."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (OSError, TimeoutError, SQLAlchemyError):
        return False
    return True
```

- [ ] **Step 4: Write `apps/api/app/db/base.py`**

```python
"""The declarative base every table inherits from."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Named constraints make migrations reviewable and let Alembic drop them by name later.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

- [ ] **Step 5: Run it and watch it pass**

Run: `cd apps/api && uv run pytest tests/test_engine.py -q`
Expected: `1 passed`.

### Task 9: The health endpoint and the application factory

**Files:**
- Create: `apps/api/app/api/v1/health.py`, `apps/api/app/api/v1/router.py`, `apps/api/app/main.py`
- Create: `apps/api/tests/conftest.py`
- Test: `apps/api/tests/test_health.py`

- [ ] **Step 1: Write `apps/api/tests/conftest.py`**

```python
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

# Unit tests never open a connection; port 1 refuses instantly if one slips through.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://opendoor:opendoor@127.0.0.1:1/opendoor"


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, app_env="test", database_url=UNREACHABLE_DATABASE_URL)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
```

- [ ] **Step 2: Write the failing tests** in `apps/api/tests/test_health.py`

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import __version__
from app.api.v1.health import DatabasePing, get_database_ping


def database_answers(answer: bool) -> DatabasePing:
    async def check() -> bool:
        return answer

    return check


def test_health_is_ok_when_the_database_answers(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_database_ping] = lambda: database_answers(True)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "version": __version__}


def test_health_is_degraded_when_the_database_is_down(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_database_ping] = lambda: database_answers(False)

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "database": "unavailable",
        "version": __version__,
    }


def test_the_app_serves_problem_details_and_request_ids(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["requestId"] == response.headers["X-Request-ID"]
```

- [ ] **Step 3: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_health.py -q`
Expected: collection error, `No module named 'app.main'` (conftest imports it).

- [ ] **Step 4: Write `apps/api/app/api/v1/health.py`**

```python
"""GET /api/v1/health: is the API up, and can it reach its database?"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from app import __version__
from app.db.engine import ping

router = APIRouter(tags=["health"])

DatabasePing = Callable[[], Awaitable[bool]]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    version: str


def get_database_ping(request: Request) -> DatabasePing:
    """The database check, as a dependency so tests can replace it."""
    engine = request.app.state.engine

    async def check() -> bool:
        return await ping(engine)

    return check


@router.get(
    "/health",
    operation_id="getHealth",
    summary="Report whether the API and its database are up",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def get_health(
    response: Response,
    database_ping: Annotated[DatabasePing, Depends(get_database_ping)],
) -> HealthResponse:
    if await database_ping():
        return HealthResponse(status="ok", database="ok", version=__version__)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="degraded", database="unavailable", version=__version__)
```

- [ ] **Step 5: Write `apps/api/app/api/v1/router.py`**

```python
"""Every version 1 endpoint, mounted under /api/v1."""

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
```

- [ ] **Step 6: Write `apps/api/app/main.py`**

```python
"""The application factory. Run it with `uvicorn --factory app.main:create_app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.problems import install_problem_handlers
from app.core.request_id import RequestIdMiddleware
from app.db.engine import create_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Settings are validated here, so a bad environment fails at boot."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = create_engine(str(settings.database_url))
        try:
            yield
        finally:
            await app.state.engine.dispose()

    app = FastAPI(title="Open Door API", version=__version__, lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    install_problem_handlers(app)
    app.include_router(api_router)
    return app
```

- [ ] **Step 7: Run every unit test and watch them pass**

Run: `cd apps/api && uv run pytest -q`
Expected: `32 passed`.

### Task 10: Migrations

**Files:**
- Generated then edited: `apps/api/alembic.ini`, `apps/api/migrations/env.py`,
  `apps/api/migrations/script.py.mako`
- Create: `apps/api/migrations/versions/0001_enable_pgvector.py`
- Delete: `apps/api/migrations/README`

- [ ] **Step 1: Generate the async Alembic scaffold**

Run: `cd apps/api && uv run alembic init -t async migrations && rm migrations/README`
Expected: `alembic.ini` and `migrations/` are created.

- [ ] **Step 2: In `apps/api/alembic.ini`, replace the line** `sqlalchemy.url = driver://user:pass@localhost/dbname` **with:**

```ini
# The URL comes from DATABASE_URL through app.core.config; see migrations/env.py.
```

- [ ] **Step 3: Replace `apps/api/migrations/env.py`**

```python
"""Alembic's entry point. The database URL comes from the app's settings, never from alembic.ini."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def database_url() -> str:
    return str(get_settings().database_url)


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 4: Replace `apps/api/migrations/script.py.mako`**, so new migrations pass ruff and
      strict mypy out of the box

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}
revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 5: Create `apps/api/migrations/versions/0001_enable_pgvector.py`**

```python
"""Enable the pgvector extension, which stores the handbook's embeddings.

Revision ID: 0001
Revises:
Create Date: 2026-09-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
```

- [ ] **Step 6: Preview the SQL without touching the database**

Run: `cd apps/api && uv run alembic upgrade head --sql`
Expected: output includes `CREATE EXTENSION IF NOT EXISTS vector;` and the `alembic_version` insert.

- [ ] **Step 7: Apply it, then confirm the models and migrations agree** (needs `docker compose up
      --wait db`)

Run: `cd apps/api && uv run alembic upgrade head && uv run alembic check`
Expected: `Running upgrade  -> 0001`, then `No new upgrade operations detected.`

### Task 11: Integration tests against the real database

**Files:**
- Test: `apps/api/tests/integration/test_database.py`

- [ ] **Step 1: Write the tests** in `apps/api/tests/integration/test_database.py`

```python
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.engine import create_engine, ping

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    # Reads DATABASE_URL from the environment (CI) or apps/api/.env (local development).
    engine = create_engine(str(Settings().database_url))
    yield engine
    await engine.dispose()


async def test_the_development_database_answers(engine: AsyncEngine) -> None:
    assert await ping(engine) is True


async def test_migrations_have_enabled_pgvector(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        assert result.scalar_one_or_none() == "vector"
```

- [ ] **Step 2: Run them against the running, migrated database**

Run: `cd apps/api && uv run pytest tests/integration -q`
Expected: `2 passed`. If Postgres is down, `test_the_development_database_answers` fails. That's
intended: integration tests should say loudly that the database is missing, not skip quietly.

- [ ] **Step 3: Run the whole suite**

Run: `cd apps/api && uv run pytest -q`
Expected: `34 passed`.

### Task 12: The OpenAPI export

**Files:**
- Create: `apps/api/scripts/export_openapi.py`
- Generated: `apps/web/openapi.json`

- [ ] **Step 1: Write `apps/api/scripts/export_openapi.py`**

```python
"""Write the API's OpenAPI schema to apps/web/openapi.json, the source of the web app's client.

`--check` writes nothing. It fails if the committed schema differs from what the API produces now,
which is how CI keeps the schema, and so the generated client, in step with the API.
"""

import json
import sys
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT = REPO_ROOT / "apps" / "web" / "openapi.json"

# Building the schema never connects to the database, so any well-formed URL will do.
SCHEMA_ONLY_DATABASE_URL = "postgresql+asyncpg://schema:schema@localhost/schema"


def render_schema() -> str:
    app = create_app(Settings(_env_file=None, database_url=SCHEMA_ONLY_DATABASE_URL))
    return json.dumps(app.openapi(), indent=2) + "\n"


def main(argv: list[str]) -> int:
    schema = render_schema()
    relative = OUTPUT.relative_to(REPO_ROOT)
    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != schema:
            print(f"{relative} is out of date. Run `make openapi` and commit the result.")
            return 1
        print(f"{relative} is up to date.")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(schema, encoding="utf-8")
    print(f"Wrote {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 2: Export the schema, then confirm the check passes**

Run: `cd apps/api && uv run python scripts/export_openapi.py && uv run python scripts/export_openapi.py --check`
Expected: `Wrote apps/web/openapi.json`, then `apps/web/openapi.json is up to date.`

### Task 13: The Stage 1 Makefile

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Create `Makefile`.** Recipe lines start with a **tab**, not spaces.

```make
# Open Door developer commands. Run `make` to list them.
# Written for GNU Make 3.81, the version macOS ships: each recipe line runs in its own shell, so
# every line that needs a directory starts with `cd`.

API := apps/api

.DEFAULT_GOAL := help
.PHONY: help db db-stop migrate dev-api openapi check-api

help: ## List the available commands
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-12s %s\n", $$1, $$2}'

db: ## Start the development Postgres in Docker and wait until it's ready
	docker compose up --detach --wait db

db-stop: ## Stop the development Postgres (its data is kept)
	docker compose stop db

migrate: ## Apply database migrations
	cd $(API) && uv run alembic upgrade head

dev-api: ## Run the API on http://localhost:8000 with auto-reload
	cd $(API) && uv run uvicorn --factory app.main:create_app --reload --port 8000

openapi: ## Regenerate apps/web/openapi.json from the API
	cd $(API) && uv run python scripts/export_openapi.py

check-api: ## Lint, type-check, migrate, and test the API; confirm the schema is current
	cd $(API) && uv run ruff check .
	cd $(API) && uv run ruff format --check .
	cd $(API) && uv run mypy
	cd $(API) && uv run lint-imports
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run alembic check
	cd $(API) && uv run pytest
	cd $(API) && uv run python scripts/export_openapi.py --check
```

- [ ] **Step 2: Run the full API check**

Run: `make db && make check-api`
Expected: every step passes. That means ruff clean, formatting clean, `Success: no issues found`,
the import contract KEPT, the migration applied, `No new upgrade operations detected`, `34 passed`,
and `apps/web/openapi.json is up to date.`

- [ ] **Step 3: Smoke-test the running API**

Run: `make dev-api` in one terminal, then `curl -i http://localhost:8000/api/v1/health` in
another.
Expected: `HTTP/1.1 200 OK`, an `x-request-id` header, and
`{"status":"ok","database":"ok","version":"0.0.0"}`. The API's terminal shows JSON log lines.
Then run `make db-stop`, re-run the curl, and expect `503` with
`{"status":"degraded","database":"unavailable",...}`. Run `make db` again, and stop the API.

### Task 14: Close Stage 1

**Files:**
- Modify: `CHANGELOG.md`, `docs/ROADMAP.md`

- [ ] **Step 1: Add to `CHANGELOG.md` under `## [Unreleased]` → `### Added`**

```markdown
- **The API foundation** (Phase 0, stage 1). A FastAPI backend with a health check at
  `/api/v1/health`, which says whether the API can reach its database. Settings are checked at
  startup, so a missing or malformed value stops the server instead of failing later. Every
  response carries a request ID. Errors come back in the standard problem-details format without
  leaking internal details, and logs are one JSON object per line. There is a development Postgres
  with pgvector in Docker, the first database migration, and a `Makefile` for the everyday commands.
```

- [ ] **Step 2: Update the status table in `docs/ROADMAP.md`.** Replace the Planning row and the
      Phase 0 row with:

```markdown
| Planning (repo, spec, roadmap, design brief) | Done | `docs/initial-planning` | [#1](https://github.com/musicteachj/open-door/pull/1) | [initial plan](plans/2026-09-29-open-door-initial-plan.md) | 2026-09-29 |
| 0 Foundation | In progress: stage 1 of 3 (API foundation) | `feat/phase-0-api-foundation` | — | [phase 0 plan](plans/2026-09-29-phase-0-foundation.md) | 2026-09-29 |
```

- [ ] **Step 3: Run `/code-review medium`** on the uncommitted diff, and fix anything real it
      finds. Re-run `make check-api` after any fix.

- [ ] **Step 4: Propose the commit, and wait for the owner's OK.** Message:

```
Set up the API with a health check, request IDs, and clear errors

Adds the backend that everything else builds on. The API checks its
settings when it starts, so a missing or malformed value stops it
straight away instead of failing later. Every response carries a
request ID, which also appears in the logs, and errors come back in a
standard format that never leaks internal details.

It also adds a development database in Docker, the first migration,
which turns on the vector extension for handbook search, and a Makefile
for the everyday commands. The Phase 0 plan comes with it.
```

- [ ] **Step 5: With the owner's OK, push and open the PR into `dev`.** Title: "Set up the API with
      a health check, request IDs, and clear errors". Body:

```markdown
## What this does
Adds the Open Door API: a health check that reports whether the database is reachable, settings
checked at startup, a request ID on every response, errors in a standard format, and JSON logs. It
also adds a development database in Docker and the first database migration.

## Why
Everything in later phases (permissions, the handbook, the assistant) plugs into this. Getting the
basics right now means every future endpoint gets request IDs, safe errors, and structured logs
for free.

## How it was checked
`make check-api` passes: linting, formatting, strict type checks, the rule that keeps domain code
free of framework imports, migrations applied and matching the code, and 34 tests (2 against the
real database). I also started the API and confirmed the health check says "ok" with the database
up, and "degraded" with it stopped.

## What to look at
How errors are shaped (`app/core/problems.py`) and the health check's behavior when the database is
down.
```

---

# Stage 2: Web foundation

**Branch:** `feat/phase-0-web-foundation`, off `dev` after Stage 1's PR merges.
**Ends with:** the web app showing "Open Door" and the API's live status, every web check passing,
and `make dev` running both apps together.

### Task 15: Scaffold the web app

**Files:**
- Create: `apps/web/*`, from the Vite `react-ts` template
- Delete: the template's `README.md`, `.gitignore`, `public/`, `src/assets/`, `src/App.css`
- Modify: `apps/web/index.html`

- [ ] **Step 1: Scaffold in a temporary folder, then copy in.** `apps/web` already holds
      `openapi.json`, and the template refuses a non-empty folder.

Run: `rm -rf /tmp/open-door-web && npm create vite@latest /tmp/open-door-web -- --template react-ts --no-interactive && cp -R /tmp/open-door-web/. apps/web/ && rm -rf /tmp/open-door-web`

- [ ] **Step 2: Remove what the template brings that we don't use**

Run: `cd apps/web && rm -rf README.md .gitignore public src/assets src/App.css`

- [ ] **Step 3: Replace `apps/web/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Open Door</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Rename the package**

Run: `cd apps/web && npm pkg set name=open-door-web`

### Task 16: Web dependencies

**Files:**
- Modify: `apps/web/package.json`; generated: `apps/web/package-lock.json`

- [ ] **Step 1: Install**

Run: `cd apps/web && npm install && npm install @tanstack/react-query && npm install -D tailwindcss @tailwindcss/vite vitest jsdom @testing-library/react @testing-library/jest-dom prettier prettier-plugin-tailwindcss orval`
Expected: no peer-dependency errors.

- [ ] **Step 2: Set the scripts**

Run: `cd apps/web && npm pkg set scripts.typecheck="tsc -b" scripts.lint="oxlint --deny-warnings" scripts.format="prettier --write ." scripts.format:check="prettier --check ." scripts.test="vitest run" scripts.generate:api="orval --config orval.config.ts && prettier --write src/api" scripts.check:api-client="node scripts/check-api-client.mjs"`

Expected: `npm pkg get scripts` shows `dev`, `build`, `preview`, `typecheck`, `lint`, `format`,
`format:check`, `test`, `generate:api`, and `check:api-client`.

### Task 17: Web configuration

**Files:**
- Modify: `apps/web/vite.config.ts`, `apps/web/tsconfig.app.json`, `apps/web/.oxlintrc.json`,
  `apps/web/src/index.css`
- Create: `apps/web/.prettierrc.json`, `apps/web/.prettierignore`, `apps/web/orval.config.ts`,
  `apps/web/src/test/setup.ts`, `apps/web/scripts/check-api-client.mjs`

- [ ] **Step 1: Replace `apps/web/vite.config.ts`**

```ts
/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dev server forwards /api to the FastAPI server, so the browser talks to one origin
// in development exactly as it will in production.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
  },
})
```

- [ ] **Step 2: Turn on strict mode in `apps/web/tsconfig.app.json`.** Add `"strict": true,` on
      the line after `"noEmit": true,`. The file becomes:

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "target": "es2023",
    "lib": ["ES2023", "DOM"],
    "module": "esnext",
    "types": ["vite/client"],
    "allowArbitraryExtensions": true,
    "skipLibCheck": true,

    /* Bundler mode */
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "jsx": "react-jsx",

    /* Linting */
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "erasableSyntaxOnly": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Replace `apps/web/.oxlintrc.json`**, adding the accessibility and Vitest rules

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc", "jsx-a11y", "vitest"],
  "categories": { "correctness": "error" },
  "ignorePatterns": ["src/api/generated.ts"],
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

- [ ] **Step 4: Create `apps/web/.prettierrc.json`**

```json
{
  "semi": false,
  "singleQuote": true,
  "printWidth": 100,
  "plugins": ["prettier-plugin-tailwindcss"],
  "tailwindStylesheet": "./src/index.css"
}
```

- [ ] **Step 5: Create `apps/web/.prettierignore`.** `openapi.json` belongs to the API's exporter,
      which formats it itself.

```
openapi.json
package-lock.json
dist
coverage
```

- [ ] **Step 6: Replace `apps/web/src/index.css`**

```css
@import 'tailwindcss';
```

- [ ] **Step 7: Create `apps/web/src/test/setup.ts`**

```ts
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
})
```

- [ ] **Step 8: Create `apps/web/orval.config.ts`**

```ts
import { defineConfig } from 'orval'

export default defineConfig({
  openDoor: {
    input: './openapi.json',
    output: {
      target: './src/api/generated.ts',
      client: 'react-query',
      httpClient: 'fetch',
      mode: 'single',
      clean: true,
    },
  },
})
```

- [ ] **Step 9: Create `apps/web/scripts/check-api-client.mjs`**

```js
// Regenerates the API client from openapi.json and fails if that changed anything, which means
// the committed client was stale. The regenerated file is left in place, ready to review and commit.
import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'

const client = 'src/api/generated.ts'
const before = readFileSync(client, 'utf8')
execSync('npm run generate:api', { stdio: 'inherit' })
const after = readFileSync(client, 'utf8')

if (before !== after) {
  console.error(`${client} was out of date with openapi.json and has been regenerated. Commit it.`)
  process.exit(1)
}
console.log(`${client} is up to date with openapi.json.`)
```

### Task 18: Generate the API client

**Files:**
- Generated: `apps/web/src/api/generated.ts`

- [ ] **Step 1: Generate**

Run: `cd apps/web && npm run generate:api`
Expected: Orval reports success, and `src/api/generated.ts` exports `useGetHealth`, `getHealth`,
and the `HealthResponse` type.

### Task 19: The home page, test first

**Files:**
- Modify: `apps/web/src/App.tsx`, `apps/web/src/main.tsx`
- Test: `apps/web/src/App.test.tsx`

- [ ] **Step 1: Write the failing tests** in `apps/web/src/App.test.tsx`

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

function stubHealth(body: unknown, status: number) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  )
}

describe('App', () => {
  it('shows the product name', () => {
    stubHealth({ status: 'ok', database: 'ok', version: '0.0.0' }, 200)
    renderApp()
    expect(screen.getByRole('heading', { name: 'Open Door' })).toBeInTheDocument()
  })

  it('reports a healthy API', async () => {
    stubHealth({ status: 'ok', database: 'ok', version: '0.0.0' }, 200)
    renderApp()
    expect(await screen.findByText('API: ok')).toBeInTheDocument()
  })

  it('reports a degraded API when the database is down', async () => {
    stubHealth({ status: 'degraded', database: 'unavailable', version: '0.0.0' }, 503)
    renderApp()
    expect(await screen.findByText('API: degraded')).toBeInTheDocument()
  })

  it('reports an unreachable API when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )
    renderApp()
    expect(await screen.findByText('API: unreachable')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/web && npm test`
Expected: failures. The template's `App` has no "Open Door" heading and no API status.

- [ ] **Step 3: Replace `apps/web/src/App.tsx`**

```tsx
import { useGetHealth } from './api/generated'

export default function App() {
  const health = useGetHealth()

  let apiStatus = 'checking'
  if (health.isError) apiStatus = 'unreachable'
  else if (health.data) apiStatus = health.data.data.status

  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="text-3xl font-semibold">Open Door</h1>
      <p className="mt-2">Your open-door policy, now always open.</p>
      <output className="mt-6 block">API: {apiStatus}</output>
    </main>
  )
}
```

- [ ] **Step 4: Replace `apps/web/src/main.tsx`**

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
```

- [ ] **Step 5: Run them and watch them pass**

Run: `cd apps/web && npm test`
Expected: `Tests  4 passed (4)`.

### Task 20: Every web check

- [ ] **Step 1: Format everything once, then run each check**

Run: `cd apps/web && npm run format && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build && npm run check:api-client`
Expected: oxlint reports no warnings or errors, `All matched files use Prettier code style!`, the
type check is silent, 4 tests pass, the build writes `dist/`, and
`src/api/generated.ts is up to date with openapi.json.`

### Task 21: The full Makefile

**Files:**
- Modify: `Makefile` (replace the whole file)

- [ ] **Step 1: Replace `Makefile`** (tabs in recipes)

```make
# Open Door developer commands. Run `make` to list them.
# Written for GNU Make 3.81, the version macOS ships: each recipe line runs in its own shell, so
# every line that needs a directory starts with `cd`.

API := apps/api
WEB := apps/web

.DEFAULT_GOAL := help
.PHONY: help setup db db-stop migrate dev dev-api dev-web openapi check check-api check-web

help: ## List the available commands
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-12s %s\n", $$1, $$2}'

setup: ## Install API and web dependencies; create apps/api/.env if it's missing
	cd $(API) && uv sync
	cd $(WEB) && npm ci
	@test -f $(API)/.env || (cp $(API)/.env.example $(API)/.env && echo "Created $(API)/.env")

db: ## Start the development Postgres in Docker and wait until it's ready
	docker compose up --detach --wait db

db-stop: ## Stop the development Postgres (its data is kept)
	docker compose stop db

migrate: ## Apply database migrations
	cd $(API) && uv run alembic upgrade head

dev: db migrate ## Start Postgres, migrate, then run the API (:8000) and the web app (:5173)
	$(MAKE) -j2 dev-api dev-web

dev-api: ## Run only the API, with auto-reload
	cd $(API) && uv run uvicorn --factory app.main:create_app --reload --port 8000

dev-web: ## Run only the web app
	cd $(WEB) && npm run dev

openapi: ## Regenerate the OpenAPI schema and the web app's API client
	cd $(API) && uv run python scripts/export_openapi.py
	cd $(WEB) && npm run generate:api

check: check-api check-web ## Run everything CI runs (start Postgres first with `make db`)

check-api: ## Lint, type-check, migrate, and test the API; confirm the schema is current
	cd $(API) && uv run ruff check .
	cd $(API) && uv run ruff format --check .
	cd $(API) && uv run mypy
	cd $(API) && uv run lint-imports
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run alembic check
	cd $(API) && uv run pytest
	cd $(API) && uv run python scripts/export_openapi.py --check

check-web: ## Lint, format-check, type-check, test, and build the web app; confirm the client
	cd $(WEB) && npm run lint
	cd $(WEB) && npm run format:check
	cd $(WEB) && npm run typecheck
	cd $(WEB) && npm test
	cd $(WEB) && npm run build
	cd $(WEB) && npm run check:api-client
```

- [ ] **Step 2: Run everything**

Run: `make db && make check`
Expected: both the API and web checks pass.

- [ ] **Step 3: Smoke-test both apps together**

Run: `make dev`, then in another terminal `curl -i http://localhost:5173/api/v1/health`.
Expected: `200`, an `x-request-id` header, and the healthy JSON, proxied through Vite to the API.
Open `http://localhost:5173`: the page shows "Open Door" and "API: ok". Press Ctrl-C to stop both.

### Task 22: Close Stage 2

**Files:**
- Modify: `CHANGELOG.md`, `docs/ROADMAP.md`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: Add to `CHANGELOG.md` under `## [Unreleased]` → `### Added`**

```markdown
- **The web app foundation** (Phase 0, stage 2). A React app that shows the product name and
  whether the API is reachable. It talks to the API through a client generated from the API's own
  schema, so the two can't silently drift apart. `make dev` runs the API and the web app together,
  and `make check` runs every check CI will run.
```

- [ ] **Step 2: Update the Phase 0 row in `docs/ROADMAP.md`**

```markdown
| 0 Foundation | In progress: stage 2 of 3 (web foundation) | `feat/phase-0-web-foundation` | [#<stage 1 PR>](https://github.com/musicteachj/open-door/pull/<stage 1 PR>) | [phase 0 plan](plans/2026-09-29-phase-0-foundation.md) | <today> |
```

Use the real Stage 1 PR number and today's date.

- [ ] **Step 3: Add a "Run it locally" section to `README.md`**, after the "Stack" section

````markdown
## Run it locally

You need Node 24, [uv](https://docs.astral.sh/uv/), and Docker Desktop.

```
make setup   # install dependencies and create apps/api/.env
make dev     # start Postgres, migrate, and run the API (:8000) and web app (:5173)
make check   # run everything CI runs
```

`make` on its own lists every command.
````

- [ ] **Step 4: Add a "Commands" section to `CLAUDE.md`**, after "Architecture (summary; the detail
      is in the spec)"

````markdown
---

## Commands

Prerequisites: Node 24, uv, and Docker Desktop running.

```
make setup      install dependencies; create apps/api/.env from .env.example
make db         start the development Postgres (127.0.0.1:5433)
make dev        Postgres, migrations, API (:8000) and web app (:5173) together
make check      everything CI runs; needs `make db` first
make openapi    after changing an API route: regenerate the schema and the web client
```

Run a single API test: `cd apps/api && uv run pytest tests/test_health.py -q`. Run a single web
test: `cd apps/web && npx vitest run src/App.test.tsx`.
````

- [ ] **Step 5: Run `/code-review medium`** on the whole branch against `dev`, committed and
      uncommitted work together, and fix anything real it finds. Re-run `make check`.

- [ ] **Step 6: Propose the commit, and wait for the owner's OK.** Message:

```
Set up the web app and show whether the API is up

Adds the React web app. For now it shows the product name and a live
status line saying whether the API and its database are reachable.

The app talks to the API through a client generated from the API's own
schema, and a check fails if the two ever fall out of step. `make dev`
now runs the API and the web app together, and `make check` runs every
check that CI will run.
```

- [ ] **Step 7: With the owner's OK, push and open the PR into `dev`.** Title: "Set up the web app
      and show whether the API is up". Body:

```markdown
## What this does
Adds the web app: a page showing the product name and whether the API is reachable, connected
through a client generated from the API's schema. `make dev` runs both apps, and `make check` runs
every check.

## Why
Later phases build every screen on this setup: styling, testing, linting, and the generated API
client. The real design arrives in Phase 2 from Claude Design.

## How it was checked
`make check` passes for both apps: 4 web tests, linting (including accessibility rules), formatting,
type checks, a production build, and a check that the generated client matches the API. I ran
`make dev` and confirmed the page shows "API: ok" through the development proxy.

## What to look at
How the page reads the API's status (`apps/web/src/App.tsx`), and the drift check that keeps the
client in step with the API.
```

---

# Stage 3: CI and guardrails

**Branch:** `chore/phase-0-ci`, off `dev` after Stage 2's PR merges.
**Ends with:** GitHub running every check on every push and pull request, and the PR for this stage
green.

### Task 23: The CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
# Every action is pinned to a full commit SHA, with its version in a comment. Dependabot updates
# both, and `make check-workflows` (zizmor) fails on an action pinned only to a tag.
name: CI

on:
  # dev is where work lands; main is the release branch. A push to either must be checked.
  push:
    branches: [main, dev]
  # No branch filter: every pull request is checked, including feature -> dev.
  pull_request:
  workflow_dispatch:

# A newer push to the same branch or pull request makes an older run pointless.
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  changes:
    name: Detect what changed
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
      pull-requests: read
    outputs:
      api: ${{ steps.filter.outputs.api }}
      web: ${{ steps.filter.outputs.web }}
    steps:
      # Every other checkout drops its credentials. This one keeps them, because on a push
      # paths-filter fetches the previous commit with them. The job runs no repository code.
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: true
      # Docs-only changes skip the heavy jobs. That saves private-repo Actions minutes.
      - uses: dorny/paths-filter@ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d # v4.0.3
        id: filter
        with:
          filters: |
            api:
              - 'apps/api/**'
              - 'apps/web/openapi.json'
              - 'evals/**'
              - 'handbook/**'
              - 'compose.yaml'
              - '.github/workflows/ci.yml'
            web:
              - 'apps/web/**'
              - '.nvmrc'
              - '.github/workflows/ci.yml'

  api:
    name: API
    needs: changes
    if: needs.changes.outputs.api == 'true' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    defaults:
      run:
        working-directory: apps/api
    services:
      # The same image and credentials as compose.yaml, so CI tests what developers run.
      postgres:
        image: pgvector/pgvector:pg17
        env:
          POSTGRES_USER: opendoor
          POSTGRES_PASSWORD: opendoor
          POSTGRES_DB: opendoor
        ports:
          - 5433:5432
        options: >-
          --health-cmd "pg_isready -h 127.0.0.1 -U opendoor -d opendoor"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      APP_ENV: test
      DATABASE_URL: postgresql+asyncpg://opendoor:opendoor@127.0.0.1:5433/opendoor
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
        with:
          enable-cache: true
          cache-dependency-glob: apps/api/uv.lock
      # --locked fails if uv.lock is out of date with pyproject.toml instead of quietly updating it.
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy
      - name: Domain code imports no framework
        run: uv run lint-imports
      - run: uv run alembic upgrade head
      - name: Models and migrations agree
        run: uv run alembic check
      - run: uv run pytest
      - name: The committed OpenAPI schema matches the API
        run: uv run python scripts/export_openapi.py --check

  web:
    name: Web
    needs: changes
    if: needs.changes.outputs.web == 'true' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version-file: .nvmrc
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run format:check
      - run: npm run typecheck
      - run: npm test
      - run: npm run build
      - name: The committed API client matches openapi.json
        run: npm run check:api-client
```

### Task 24: The security workflow

**Files:**
- Create: `.github/workflows/security.yml`

- [ ] **Step 1: Create `.github/workflows/security.yml`**

```yaml
name: Security

on:
  push:
    branches: [main, dev]
  pull_request:
  # Weekly, so a newly published vulnerability in an unchanged dependency still surfaces.
  schedule:
    - cron: '0 13 * * 1'
  workflow_dispatch:

concurrency:
  group: security-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  secrets:
    name: Leaked secrets (gitleaks)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
          fetch-depth: 0 # scan the whole history, not just the latest commit
      - name: Install gitleaks
        env:
          GITLEAKS_VERSION: 8.30.1
        run: |
          curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" | tar -xz gitleaks
      - name: Scan every commit
        run: ./gitleaks git --redact --verbose --exit-code 1

  python-dependencies:
    name: Vulnerable Python dependencies (pip-audit)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    defaults:
      run:
        working-directory: apps/api
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
        with:
          enable-cache: true
          cache-dependency-glob: apps/api/uv.lock
      - run: uv sync --locked
      # --skip-editable skips the API itself, which isn't a published package.
      - run: uv run --with pip-audit pip-audit --skip-editable

  web-dependencies:
    name: Vulnerable web dependencies (npm audit)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version-file: .nvmrc
      # npm audit reads package-lock.json, so no install is needed.
      - run: npm audit --audit-level=high
```

### Task 25: The changelog check

**Files:**
- Create: `.github/workflows/changelog.yml`

- [ ] **Step 1: Create `.github/workflows/changelog.yml`**

```yaml
name: Changelog

on:
  # Label events are included so adding or removing skip-changelog re-runs the check.
  pull_request:
    types: [opened, synchronize, reopened, labeled, unlabeled]

permissions:
  contents: read

jobs:
  changelog:
    name: Changelog updated
    if: ${{ !contains(github.event.pull_request.labels.*.name, 'skip-changelog') }}
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
          fetch-depth: 0
      - name: Code changes need a CHANGELOG.md entry
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
        run: |
          changed=$(git diff --name-only "$BASE_SHA...$HEAD_SHA")
          if echo "$changed" | grep -qE '^(apps|evals|handbook)/'; then
            if ! echo "$changed" | grep -qx 'CHANGELOG.md'; then
              echo "::error::This pull request changes code but not CHANGELOG.md. Add an entry, or apply the skip-changelog label if it's a pure chore."
              exit 1
            fi
          fi
          echo "Changelog check passed."
```

- [ ] **Step 2: With the owner's OK, create the two labels the workflows and Dependabot use**

Run: `gh label create skip-changelog --repo musicteachj/open-door --color BFD4F2 --description "No changelog entry needed (pure chore)" && gh label create dependencies --repo musicteachj/open-door --color 0366D6 --description "Dependency updates"`
Expected: both labels are created.

### Task 26: Dependabot

**Files:**
- Create: `.github/dependabot.yml`

- [ ] **Step 1: Create `.github/dependabot.yml`**

```yaml
# Weekly, grouped dependency updates, opened against dev like every other change. They carry
# skip-changelog: a version bump is a chore, and the lockfile diff is its own record.
# The 7-day cooldown waits for a release to age before proposing it, so a compromised release has
# time to be caught first. Security updates skip the wait.
version: 2
updates:
  - package-ecosystem: uv
    directory: /apps/api
    target-branch: dev
    schedule:
      interval: weekly
      day: monday
    cooldown:
      default-days: 7
    groups:
      python:
        patterns: ['*']
    labels: [dependencies, skip-changelog]

  - package-ecosystem: npm
    directory: /apps/web
    target-branch: dev
    schedule:
      interval: weekly
      day: monday
    cooldown:
      default-days: 7
    groups:
      web:
        patterns: ['*']
    labels: [dependencies, skip-changelog]

  - package-ecosystem: github-actions
    directory: /
    target-branch: dev
    schedule:
      interval: weekly
      day: monday
    cooldown:
      default-days: 7
    groups:
      actions:
        patterns: ['*']
    labels: [dependencies, skip-changelog]
```

### Task 27: Pre-commit hooks and the security command

**Files:**
- Create: `.pre-commit-config.yaml`
- Modify: `Makefile` (the `setup` target and a new `audit` target)

- [ ] **Step 1: Create `.pre-commit-config.yaml`**

```yaml
# Fast checks before each commit. CI runs the full set, so these are a head start, not the gate.
# Install once with `make setup`; run by hand with `uvx pre-commit run --all-files`.
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.16.9
    hooks:
      - id: ruff-check
        args: [--fix]
        files: ^apps/api/
      - id: ruff-format
        files: ^apps/api/

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1
    hooks:
      - id: gitleaks

  - repo: local
    hooks:
      - id: web-lint
        name: web lint (oxlint)
        entry: npm --prefix apps/web run lint
        language: system
        files: ^apps/web/
        pass_filenames: false
      - id: web-format
        name: web format check (prettier)
        entry: npm --prefix apps/web run format:check
        language: system
        files: ^apps/web/
        pass_filenames: false
```

- [ ] **Step 2: In `Makefile`, replace the `setup` target and add `audit` to `.PHONY`**

```make
.PHONY: help setup db db-stop migrate dev dev-api dev-web openapi check check-api check-web audit
```

```make
setup: ## Install dependencies and git hooks; create apps/api/.env if it's missing
	cd $(API) && uv sync
	cd $(WEB) && npm ci
	uvx pre-commit install
	@test -f $(API)/.env || (cp $(API)/.env.example $(API)/.env && echo "Created $(API)/.env")
```

- [ ] **Step 3: Append the `audit` target to `Makefile`**

```make

audit: ## Scan for leaked secrets and vulnerable dependencies (what the Security workflow runs)
	uvx pre-commit run gitleaks --all-files
	cd $(API) && uv run --with pip-audit pip-audit --skip-editable
	cd $(WEB) && npm audit --audit-level=high
```

- [ ] **Step 4: Install the hooks and run them on everything**

Run: `uvx pre-commit install && uvx pre-commit run --all-files`
Expected: every hook passes. The first run downloads the hook environments; pre-commit fetches a
Go toolchain for gitleaks if the machine has none. If gitleaks flags the throwaway development
password in `compose.yaml` or `apps/api/.env.example`, add each finding's `Fingerprint` line (from
`uvx pre-commit run gitleaks --all-files --verbose`) to a new `.gitleaksignore` file, with a
comment above it saying it's the local-only development password. Then re-run.

- [ ] **Step 5: Run the security command**

Run: `make audit`
Expected: gitleaks finds no leaks, and neither `pip-audit` nor `npm audit` reports a high-severity
vulnerability. If one does, update that dependency (`uv add <pkg>@latest` or `npm install
<pkg>@latest`), re-run `make check`, and mention it in the changelog entry.

### Task 28: Docs and workflow checks

`CLAUDE.md` promises that docs-only pull requests get automated spelling, link, and placeholder
checks. This task adds them, plus linting for the workflows themselves. CI calls the same `make`
targets developers run, so the tool versions are pinned in one place.

**Files:**
- Create: `_typos.toml`
- Modify: `Makefile` (adds the tool versions and two targets, adds both to `check`, and widens the
  help column), `.github/workflows/ci.yml` (adds two jobs)
- Fix: the spelling findings the first run turns up

<!-- spellchecker:off -->

- [ ] **Step 1: Create `_typos.toml`** at the repository root

```toml
# Spelling checks for `make check-docs` and CI. US English, as CLAUDE.md requires: "colour" fails.
[default]
locale = "en-us"
# Markdown between `spellchecker:off` and `spellchecker:on` HTML comments is skipped, for text
# that quotes a misspelling on purpose.
extend-ignore-re = ['(?s)<!--\s*spellchecker:off\s*-->.*?<!--\s*spellchecker:on\s*-->']

[default.extend-words]
# axe is the accessibility checker (axe-core), not a misspelling of "ax".
axe = "axe"
# The US locale accepts both spellings. CLAUDE.md asks for one L.
cancelled = "canceled"
cancelling = "canceling"

[files]
extend-exclude = [
    # Generated files: their spelling comes from their source.
    "uv.lock",
    "package-lock.json",
    "apps/web/openapi.json",
    "apps/web/src/api/generated.ts",
    # Frozen by project rule, so a finding there could never be fixed.
    "docs/plans/2026-09-29-open-door-initial-plan.md",
]
```

<!-- spellchecker:on -->

- [ ] **Step 2: Update `Makefile`.** Recipe lines start with a tab.

After `WEB := apps/web`, add:

```make

# The docs and workflow linters. Dependabot can't see these versions, so bump them by hand.
TYPOS := typos@1.50.3
LYCHEE := lycheeverse/lychee:0.24.2
ACTIONLINT := rhysd/actionlint:1.7.12
ZIZMOR := zizmor@1.30.1
```

Then make three edits:
- Replace the `.PHONY` line with
  `.PHONY: help setup db db-stop migrate dev dev-api dev-web openapi check check-api check-web check-docs check-workflows audit`.
- Replace the `check` line with
  ``check: check-api check-web check-docs check-workflows ## Run everything CI runs (start Postgres first with `make db`)``.
- In `help`, change `%-12s` to `%-16s`, so `check-workflows` fits its column.

Append:

```make

check-docs: ## Check spelling (American English), links between files, and leftover placeholders
	uvx $(TYPOS)
	docker run --rm -v "$(CURDIR):/input:ro" -w /input $(LYCHEE) --offline --no-progress --include-fragments './**/*.md'
	@if git grep --untracked -n -I -w -E 'T[O]DO|TB[D]|FIXM[E]|XX[X]|[Ll]orem [i]psum' -- '*.md'; then echo "Finish or remove the placeholders above."; exit 1; fi

check-workflows: ## Check the GitHub Actions workflows for mistakes (actionlint) and security (zizmor)
	docker run --rm -v "$(CURDIR):/repo:ro" -w /repo $(ACTIONLINT) -no-color
	uvx $(ZIZMOR) .
```

How the checks behave:
- `lychee --offline` checks only links inside the repository, including `#heading` anchors. A slow
  or missing external site can't fail it. It skips git-ignored paths such as `.venv` and
  `node_modules`.
- The placeholder pattern is written as `T[O]DO` and so on, so this plan, which documents the
  check, doesn't match it. `-w` (whole words) is used instead of `\b`, which macOS git's regex
  doesn't support.
- The actionlint image includes shellcheck, so the shell in every `run:` block is checked too.
- Markdown that quotes a misspelling on purpose, as this task does, goes between
  `<!-- spellchecker:off -->` and `<!-- spellchecker:on -->` comments. They don't show when the
  markdown is rendered.

- [ ] **Step 3: Append the two jobs to `.github/workflows/ci.yml`**

```yaml

  # Both are cheap, so they run on every pull request, docs-only ones included.
  docs:
    name: Docs
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
      - name: Spelling in American English, links between files, and leftover placeholders
        run: make check-docs

  workflows:
    name: Workflows
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
      - name: Workflow mistakes (actionlint) and security problems (zizmor)
        # The token lets zizmor confirm that each pinned commit really belongs to its action.
        env:
          GH_TOKEN: ${{ github.token }}
        run: make check-workflows
```

<!-- spellchecker:off -->

- [ ] **Step 4: Run the docs check and fix what it finds**

Run: `make check-docs`
Expected:
- On 2026-10-03, `typos` reported exactly one finding: "cancelling" in the `ping` docstring in
  `apps/api/app/db/engine.py`. Change it to "canceling", and fix anything written since.
- Then the re-run passes: `typos` is silent, lychee reports `0 Errors`, and no placeholder is
  printed.

- [ ] **Step 5: Run the workflow check**

Run: `make check-workflows`
Expected: actionlint prints nothing, and zizmor ends with `No findings to report`. zizmor's online
checks run only when a token is set. To match CI, run `GH_TOKEN=$(gh auth token) make
check-workflows`.

- [ ] **Step 6: Prove both checks can fail, then undo**

Make each of these changes, run the check, and expect a failure:
- Add a scratch `zz.md` containing "colour" and a to-do marker. Expect `make check-docs` to fail.
- Change one `uses:` line in `ci.yml` to `actions/checkout@v7`. Expect `make check-workflows` to
  fail with `unpinned-uses`.

Then delete `zz.md`, restore the `uses:` line, and re-run `make check`.

<!-- spellchecker:on -->

### Task 29: Close Stage 3 and Phase 0

**Files:**
- Modify: `CHANGELOG.md`, `docs/ROADMAP.md`, `CLAUDE.md`

- [ ] **Step 1: Add to `CHANGELOG.md` under `## [Unreleased]` → `### Added`**

```markdown
- **Automatic checks on every push and pull request** (Phase 0, stage 3). GitHub now runs the API
  and web checks, but only for the parts that changed. It scans for leaked secrets and vulnerable
  dependencies, weekly as well, and requires a changelog entry when code changes. Dependabot opens
  grouped weekly update pull requests against `dev`, and pre-commit hooks catch the quick problems
  before a commit is made. `make audit` runs the security scans locally.

  Every pull request, docs-only ones included, also gets two quick checks. The docs check covers
  spelling in American English, links between files, and leftover placeholders. The workflow
  check looks for mistakes and security problems in the workflows themselves. Every action is
  pinned to an exact commit, and Dependabot waits 7 days before proposing a new release.
```

- [ ] **Step 2: Add `make audit` to the Commands block in `CLAUDE.md`**, after the `make openapi`
      line

```
make audit      scan for leaked secrets and vulnerable dependencies
```

- [ ] **Step 3: Update the Phase 0 row in `docs/ROADMAP.md`**, using the real PR numbers and today's
      date

```markdown
| 0 Foundation | Done | `chore/phase-0-ci` | [#<stage 1>](https://github.com/musicteachj/open-door/pull/<stage 1>), [#<stage 2>](https://github.com/musicteachj/open-door/pull/<stage 2>), [#<stage 3>](https://github.com/musicteachj/open-door/pull/<stage 3>) | [phase 0 plan](plans/2026-09-29-phase-0-foundation.md) | <today> |
```

- [ ] **Step 4: Run `/code-review medium`** on the whole branch against `dev`, committed and
      uncommitted work together (the workflows count as code), and fix anything real it finds.
      Re-run `make check`.

- [ ] **Step 5: Propose the commit, and wait for the owner's OK.** Message:

```
Run the checks automatically on every push and pull request

GitHub now runs the API and web checks whenever those parts change, and
scans for leaked secrets and vulnerable dependencies on every push and
once a week. A pull request that changes code needs a changelog entry,
unless it's labeled as a pure chore.

Every pull request also gets a docs check (spelling in American
English, links between files, leftover placeholders) and a check of
the workflows themselves. Actions are pinned to exact commits, so a
moved tag can't change what runs.

Dependabot opens grouped weekly updates against dev once a release is
a week old, and pre-commit hooks catch quick problems before a commit
is made.
```

- [ ] **Step 6: With the owner's OK, push and open the PR into `dev`.** Title: "Run the checks
      automatically on every push and pull request". Body:

```markdown
## What this does
Adds GitHub Actions workflows for the API and web checks (run only when those parts change),
security scans (leaked secrets and vulnerable dependencies, also weekly), and a changelog
requirement for code changes. Every pull request, docs-only ones included, gets a docs check
(spelling in American English, links between files, leftover placeholders) and a check of the
workflows themselves. It also adds Dependabot and pre-commit hooks.

## Why
So nothing reaches `dev` or `main` without passing the same checks developers run locally, and so
new vulnerabilities in dependencies surface on their own.

## How it was checked
`make check`, `make audit`, and the pre-commit hooks pass locally. This pull request's own checks
are the real test: the CI, Security, and Changelog workflows should all be green below.

## What to look at
Which paths trigger which jobs (`ci.yml`, the `changes` job), the one checkout that keeps its
credentials and why, and the `skip-changelog` label on Dependabot's pull requests.
```

- [ ] **Step 7: Confirm the pull request's checks are green**

Run: `gh pr checks <stage 3 PR number> --repo musicteachj/open-door --watch`
Expected: CI (Detect what changed, API, Web, Docs, Workflows), Security (all three jobs), and
Changelog all pass. This PR changes both apps' tooling, so both the API and Web jobs run.

---

## Phase 0 is done when

- CI is green on the stage 3 pull request, with the API and web jobs both running.
- `make setup && make dev` on a fresh clone brings up a page that says "API: ok".
- `make check` and `make audit` pass locally.
- The roadmap shows Phase 0 as done, and the changelog has an entry for each stage.

## Self-review against the spec

- **Covered by this plan:**
  - Environment config validated at boot (Task 4, and `create_app` in Task 9).
  - `/health` (Task 9).
  - Request IDs and JSON logs (Tasks 5 and 6).
  - RFC 9457 errors (Task 7).
  - `/api/v1` prefix (Task 9).
  - Postgres 17 with pgvector (Tasks 1 and 10).
  - Alembic plus drift check (Task 10 and CI).
  - The import-linter engine boundary (Task 3).
  - Orval-generated client plus drift check (Tasks 12, 17, 18, and CI).
  - TanStack Query (Task 19).
  - Tailwind v4 (Task 17).
  - The accessibility lint rules (Task 17).
  - CI jobs `api`, `web`, `security`, `changelog` (Tasks 23 to 25).
  - Dependabot (Task 26).
  - Pre-commit (Task 27).
  - The docs checks `CLAUDE.md` promises (spelling, links, placeholders), workflow linting, and
    actions pinned to commits (Task 28, added 2026-10-03).
  - `make dev` and `make check` (Task 21).
- **Deliberately later:**
  - Database roles and row-level security (Phase 1).
  - Sessions and CSRF (Phase 1).
  - The design system, React Router, and Zustand (Phases 2 and 4).
  - `evals-offline` and `e2e` CI jobs (Phases 2 and 3).
  - Seeding in `make dev` (Phase 1).
- **Changed from the spec:** oxlint instead of ESLint (see "Decisions made while planning").

## Changes made during execution

- Tasks 1 to 3: review changes are already reflected in their code blocks above.
  - The import-linter `forbidden_modules` list also blocks alembic, uvicorn, httpx, httpx2, and
    anthropic.
  - Ruff's `DTZ` rules flag naive dates and times.
  - `compose.yaml` has a fixed project name (`open-door`), and its health check probes over TCP
    (`pg_isready -h 127.0.0.1`), which the CI `--health-cmd` mirrors.
  - `app/__init__.py` reads `__version__` from the installed package metadata, so
    `pyproject.toml` is the single source of truth.
  - `.editorconfig` indents TOML with 4 spaces.
- Task 4, config tests: an autouse fixture clears `APP_ENV`, `DATABASE_URL`, and `LOG_LEVEL` first,
  because CI sets `APP_ENV`.
- Task 4, config: `hide_input_in_errors=True` and `Field(repr=False)` keep the database password
  out of startup errors and `repr`, with two new tests.
- Task 5, request ID: the middleware adds the `headers` key when a response start lacks one, since
  the ASGI spec makes it optional.
- Task 5, request ID tests: the leak test now calls the middleware directly, because TestClient
  runs the app in another thread's context and the old test could not fail. New tests cover an
  over-long incoming ID, a streamed response, and a response start without headers.
- Task 6, logging: `configure_logging` replaces only its own handler, so it is safe to call
  repeatedly and leaves other handlers attached. The uvicorn loggers defer to the root level.
- Task 6, logging tests: new tests cover idempotence, uvicorn levels, an explicit `request_id` on
  a record, and exception output.
- Task 7, problems: `HTTPException.headers` (`Allow`, `WWW-Authenticate`, `Retry-After`) are kept.
  A non-standard status code gets the title "Error" instead of a crash, and an empty detail is
  left out of the body. A comment explains the duplicate uvicorn log line.
- Task 7, problems tests: new tests cover the 405 `Allow` header, a custom detail, status 499, the
  500 log carrying its request ID, and rejected input not being echoed.
- Task 8, engine: `ping` time-limits connecting and the query (5 seconds by default). When it
  fails, it logs a warning with the type of the driver's error, so a wrong password, a database
  that is still starting, and a missing database can be told apart. A test covers a connection
  that opens but never answers.
- Task 8, base: the naming convention puts all of a constraint's columns in its name
  (`column_0_N`), so composite constraints stay distinct, and index names read
  `ix_<table>_<columns>`. The new `apps/api/tests/test_base.py` covers it.
- Task 9, health: a new test calls `/api/v1/health` with no dependency override, so it exercises
  the real wiring (lifespan, `app.state.engine`, `get_database_ping`, `ping`) and expects a 503.
  The `settings` fixture also pins `log_level`, so an exported `LOG_LEVEL` can't change test
  behavior. `create_app` checks `if settings is None` instead of `settings or get_settings()`.
- Test counts in later steps: 28 unit tests after Task 8, 32 after Task 9, and 34 after Task 11.
- Tasks 1–9 were committed as a checkpoint (`840f583`) before Task 10. The rest of Stage 1 goes in
  a second commit on the same branch, and the Stage 1 changelog entry was edited in place rather
  than added again.
- Task 10, `alembic.ini`: ruff post-write hooks (`ruff check --fix`, then `ruff format`) run on
  every generated migration. Without them, the typed template's `repr()` emits single quotes and
  always imports `sa` and `op`, so a fresh migration failed `ruff format --check` and F401 until it
  was fixed by hand. It was verified with a throwaway revision, which was then deleted.
- Tasks 10–11: until Task 12 adds a file to `scripts/`, a bare `uv run mypy` stops with "no .py
  files in directory 'scripts'". The interim checks ran `mypy app tests migrations`.
- Task 12, the OpenAPI export:
  - It parses its arguments with `argparse`, so a misspelled flag exits 2 instead of silently
    rewriting the file.
  - It pins every `Settings` field, so an exported `LOG_LEVEL` or `APP_ENV` can't change or break
    the export.
  - The docstring now says the check compares the file on disk, which is the design.

- **Stage 3 additions (owner-approved, 2026-10-03, before Stage 3 started).**
  - **New Task 28, docs and workflow checks.** It adds `make check-docs` and `make check-workflows`,
    which CI runs as the Docs and Workflows jobs:
    - spelling in American English, with `typos`
    - links between files, with `lychee --offline`
    - leftover placeholders, with `git grep`
    - workflow mistakes and security problems, with actionlint and zizmor

    "Close Stage 3" is now Task 29.
  - **Tasks 23–26 were hardened, all checked against zizmor 1.30.1:**
    - Every action is pinned to a full commit SHA, with its version in a comment.
    - Every checkout sets `persist-credentials: false`, except the `changes` job. There, on a
      push, paths-filter fetches history with those credentials.
    - Dependabot waits 7 days (`cooldown`) before proposing a release.
  - **Code review scope.** The Stage 2 and 3 close-out steps review the whole branch against
    `dev`, following the updated `CLAUDE.md` rule.
  - **How the new blocks were checked.** They were run in a scratch clone with the Stage 1 Makefile
    and the planned workflows. actionlint (including shellcheck) and zizmor (including its online
    checks) were clean. Each check was shown to fail on a seeded mistake.

For Tasks 4–12, the code in the repository is the source of truth; the code blocks above show the original plan.

**Review process from Task 10 on (owner-approved, 2026-09-30).** Tasks 1–9 each got an
implementer plus two reviewers (spec compliance, then code quality on the strongest model). That
caught real bugs but is expensive for pre-validated, mechanical work. For the rest of Phase 0,
each batch of tasks gets one implementer and one combined review (spec and quality together).
The two-stage review with the strongest model is reserved for logic that matters: permissions
(Phase 1), the assistant loop (Phase 4), and the time-off engine (Phase 5). `/code-review
medium` still runs before every pull request that changes code.

## Backlog

Deferred review findings now live in [`../BACKLOG.md`](../BACKLOG.md).
