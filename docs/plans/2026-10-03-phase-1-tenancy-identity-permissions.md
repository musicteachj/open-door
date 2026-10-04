# Phase 1: Tenancy, Identity, and Permissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. **Project rule:** never commit, push, or open a PR without
> the owner's explicit OK for that action (see `CLAUDE.md`). Every "Propose the commit" step stops
> and waits.

**Goal:** Every visitor gets an isolated sandbox company and signs in as one of four personas
through a session cookie. They can read only what their role allows. The database enforces tenant
isolation, and one pure function decides who can see what.

**Architecture:** Postgres row-level security keeps sandbox companies apart. The API connects as
its own login, `od_app_login`, which owns nothing and can't bypass the policies. Each request runs
in one transaction, and a SQLAlchemy hook sets the tenant and person for it with
`set_config(…, true)`. Sessions are hashed tokens in `__Host-` cookies, and a same-origin check
plus a session-bound CSRF token guard every state-changing request. `app/policy/can()` is pure
Python, checked by import-linter, and a second database rule backs it for private details. A
deterministic generator seeds the same fictional company of 120 people into each sandbox.

**Tech stack:** Postgres 17 with row-level security, SQLAlchemy 2.1 (async, asyncpg), Alembic,
FastAPI, and pydantic, managed with uv. Tests run with pytest against the real database. The
regenerated web client uses Orval.

**Spec:** [`../specs/2026-10-03-phase-1-tenancy-identity-permissions.md`](../specs/2026-10-03-phase-1-tenancy-identity-permissions.md) ·
**Session lifetime:** [ADR 0007](../adr/0007-session-lifetime.md) ·
**Roadmap:** [`../ROADMAP.md`](../ROADMAP.md)

---

## Decisions made while planning

**Every code block and command below was run before it was written down.** The whole phase was
built in a scratch clone of `dev` on 2026-10-03, stage on top of stage, against a throwaway
Postgres 17 + pgvector container. Each stage's code blocks were copied from the files that passed,
and a script confirmed that every block matches them.

The full validation, at the end of Stage 4:
- 260 tests passed.
- ruff, strict mypy, and import-linter were clean.
- `alembic check` passed, and so did the migration round trip.
- `make check-web`, `make check-docs`, and `make check-workflows` passed.

The tests themselves were checked in two ways:
- **Every test-first failure was reproduced.** Each failure a step shows is the real one.
- **Every database guarantee fails without its rule.** For example, taking out `NULLIF`
  reproduces the `''::uuid` error, and removing the transaction hook fails 15 tests.

**Four stages, not the spec's three.** The third stage came to about 2,400 lines, so it is split
into sessions (Stage 3) and the directory API (Stage 4). Each stage is a pull request into `dev`:

| Stage | Branch | Tasks | Code + tests | Tests at the end |
|---|---|---|---|---|
| 1 Roles and tenancy | `feat/phase-1-tenancy` | 1–10 | about 2,000 (about 1,100 of them tests) | 81 |
| 2 The seed company | `feat/phase-1-seed` | 11–14 | about 1,000 | 112 |
| 3 Sessions and signing in | `feat/phase-1-sessions` | 15–22 | about 1,850, plus about 900 generated | 217 |
| 4 The directory API | `feat/phase-1-directory-api` | 23–27 | about 500, plus docs and about 750 generated | 260 |

Stages 1 and 3 are above the roughly 1,500-line PR guideline, mostly because of their tests. Each
stage's tests prove the code in the same PR, so the plan keeps them together.

**Other decisions that affect more than one stage:**
- **Marcus is the Oakland store manager,** as the initial plan and the design brief say. Priya,
  Leo, and three department leads report to him directly, and the leads manage the associates.
  The spec was corrected to match during planning.
- **The `__Host-` cookies were checked in a real browser on `http://localhost`.** In headless
  Chrome 154, sandbox creation, `/me`, and a persona switch returned 201, 200, and 200 through
  Vite's proxy. The page could read the CSRF cookie and could not see the session cookie.
- **Each stage's own "Decisions made while planning this stage" section has the details.**

## Prerequisites (owner)

- **Docker Desktop is running.** `make db` starts the development Postgres, and from Stage 1 on it
  also migrates and creates the login users.
- **Your `apps/api/.env` needs the new database URLs** before Stage 1's Task 6. Stage 1's "Before
  you start" note has the exact lines.
- **Each stage branches off `dev` after the previous stage's PR merges.**

## File map

```
open-door/
├── Makefile                                 Stage 1  db migrates and creates logins; bootstrap-db, migrations-roundtrip
├── .github/workflows/ci.yml                 Stage 1  owner migrates, round trip, logins, tests as the app; Stage 3 renames a step
├── README.md                                Stage 4  links the data inventory
├── CLAUDE.md                                Stages 1, 4  the three database URLs; a data-inventory rule
├── docs/
│   ├── DATA-INVENTORY.md                    Stage 4  what each column holds, why, who sees it, how long it's kept
│   └── BACKLOG.md                           Stages 1, 3, 4  closed Phase 1 items out; later-phase findings in
├── apps/api/
│   ├── .env.example                         Stage 1  DATABASE_URL (app login), MIGRATION_ and CLEANUP_DATABASE_URL, APP_ORIGIN
│   ├── pyproject.toml                       Stage 3  import-linter also covers app.policy
│   ├── migrations/
│   │   ├── env.py                           Stage 1  runs as MIGRATION_DATABASE_URL; imports the models
│   │   └── versions/
│   │       ├── 0002_app_schema_and_roles.py Stage 1  schema app, roles od_app and od_cleanup, context functions
│   │       └── 0003_tenant_tables.py        Stage 1  the eight tables, row-level security, policies, grants
│   ├── scripts/bootstrap_db_users.py        Stage 1  creates the login users from the URLs
│   ├── app/
│   │   ├── core/config.py                   Stage 1  the three database URLs and APP_ORIGIN
│   │   ├── core/logging.py                  Stage 3  structured fields for security events
│   │   ├── db/base.py                       Stage 1  type map: str to text, datetime to timestamptz
│   │   ├── db/models.py                     Stage 1  the eight ORM models
│   │   ├── db/tenancy.py                    Stage 1  TenantContext, tenant_session(), set_is_hr(), the after_begin hook
│   │   ├── api/deps.py                      Stage 1  get_engine()
│   │   ├── api/schemas.py                   Stage 3  the camelCase base model
│   │   ├── api/v1/router.py                 Stages 3, 4  mounts the new routers
│   │   ├── main.py                          Stage 3  the same-origin middleware
│   │   ├── domain/holidays.py               Stage 2  the company holiday calendar (pure)
│   │   ├── policy/__init__.py               Stage 3  Actor, Action, PersonResource, can() (pure)
│   │   └── modules/
│   │       ├── sandbox/                     Stages 2, 3  seed_data.py, seed.py; service.py, routes.py (POST /sandboxes)
│   │       ├── identity/                    Stage 3  tokens, cookies, sessions, actor, same_origin, security_log, deps, routes
│   │       ├── audit/service.py             Stage 3  record_event()
│   │       └── people/                      Stages 3, 4  schemas.py, queries.py; routes.py (the directory and private details)
│   └── tests/                               unit tests, plus tests/integration against the real database
└── apps/web/
    ├── openapi.json                         Stages 3, 4  regenerated
    └── src/api/generated.ts                 Stages 3, 4  regenerated
```

---

# Stage 1: Roles and tenancy

**Branch:** `feat/phase-1-tenancy`, off `dev`.
**Ends with:** Postgres keeping every sandbox company apart. The API connects as its own login,
which owns nothing and can't skip row-level security. The eight Phase 1 tables exist with their
policies and exact grants, `make db` creates the login users, CI proves that every migration
reverses, and `make check-api` passes with 81 tests, 33 of them against the real database.

> **Before you start: add three lines to `apps/api/.env`.** From Task 3 on, migrations connect
> through their own URL, as the database owner, and Task 1 adds the settings these lines fill in.
> Leave `DATABASE_URL` as it is for now. It still names the owner, and Task 6 moves it to the
> API's own login, once that login exists.
>
> ```
> MIGRATION_DATABASE_URL=postgresql+asyncpg://opendoor:opendoor@127.0.0.1:5433/opendoor
> CLEANUP_DATABASE_URL=postgresql+asyncpg://od_cleanup_login:od_cleanup_dev@127.0.0.1:5433/opendoor
> APP_ORIGIN=http://localhost:5173
> ```
>
> Then start the development database with `make db`. Until Task 8 changes it, that only starts
> Postgres.

## Decisions made while planning this stage

Every code block below is the exact final content of a file that was run in a scratch clone on
2026-10-03, and every "Expected" is the output it produced. That ran against Postgres 17.11 (the
pgvector image) with Python 3.13, SQLAlchemy 2.1.1, Alembic 1.20.0, asyncpg 0.31.0, and
pytest-asyncio 1.4.0. The scratch database listened on port 5434, and the commands here use 5433,
the development port.

- **Reversing migration 0002 keeps the two roles.** Roles belong to the whole Postgres server, not
  to one database. So `downgrade` revokes what this database granted them and drops the `app`
  schema and its functions, but leaves `od_app` and `od_cleanup` in place. Dropping them would
  also drop the login users' memberships, and could break another database on the same server.
  Upgrading again reuses them, which is why role creation sits in a `DO` block that skips a role
  that already exists.
- **`DATABASE_URL` moves to the API's login in Task 6, not at the start.** That login doesn't
  exist until the bootstrap script creates it, so Tasks 1–5 keep connecting as the owner.
- **The tenant factory fixture is `make_tenant`.** It creates a `SampleTenant` as the API's login,
  with a row in every table, a session and an audit event included, so the isolation and cleanup
  tests cover all eight tables. Every tenant it creates is deleted through the owner when the test
  session ends.
- **`Base` maps `str` to `text` and `datetime` to `timestamptz`.** A model then can't drift from
  its migration by forgetting a time zone.
- **A few constraints the spec doesn't list,** all scoped to a tenant:
  - A department's name is unique within its tenant.
  - `employment_type`, `persona_key`, and `via` are checked against their allowed values.
  - Both session hashes must be 32 bytes, the size of a SHA-256 digest.
  - `person_private`, `sessions`, and `audit_events` get an index that starts with `tenant_id`,
    so the foreign-key checks during a cascading delete stay inside one tenant.
- **`tenants.expires_at` has no default.** Stage 3 sets it when it creates a sandbox, from the one
  lifetime constant that also sets the cookies' `Max-Age`. `created_at` and `occurred_at` default
  to `now()`, and audit IDs to `gen_random_uuid()`.
- **The bootstrap script refuses three mistakes.** A login URL that names the migrator (as
  `DATABASE_URL` does before Task 6), a URL that names `od_app` or `od_cleanup` themselves, and
  the same user in both URLs. Each would let a login skip the rules, or hold both roles.
- **The bootstrap test uses an awkward user name and password,** with quotes, a semicolon, a SQL
  comment, a backslash, and the placeholders `:name`, `%s`, `$1`, and `?`. It runs the script
  twice, then logs in as the result, which proves both the quoting and the second run.
- **Each guarantee test was shown to fail.**
  - Without `NULLIF` in `app.current_tenant_id()`, the reused-connection tests fail with
    `invalid input syntax for type uuid: ""`, which is exactly the problem the spec describes.
  - Without the transaction hook, 15 tests fail.
  - A view without `security_invoker` fails the view guard.
- **Stage 1 is about 2,000 lines,** above the spec's estimate of 1,500. About 1,100 of them are
  the database tests the spec lists. The rest is code, migrations, and tooling.

### Task 1: Settings for the three database URLs and the app origin

**Files:**
- Modify: `apps/api/app/core/config.py`, `apps/api/tests/conftest.py`,
  `apps/api/scripts/export_openapi.py`, `apps/api/.env.example`
- Test: `apps/api/tests/test_config.py`

- [ ] **Step 1: Replace `apps/api/tests/test_config.py` with the new tests**

```python
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

APP_URL = "postgresql+asyncpg://od_app_login:od_app_dev@localhost/opendoor"
DATABASE_URL_FIELDS = ("database_url", "migration_database_url", "cleanup_database_url")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests read the real environment, and CI sets APP_ENV, so start each one clean."""
    for name in (
        "APP_ENV",
        "DATABASE_URL",
        "MIGRATION_DATABASE_URL",
        "CLEANUP_DATABASE_URL",
        "APP_ORIGIN",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_a_missing_database_url_stops_startup() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


@pytest.mark.parametrize("field", DATABASE_URL_FIELDS)
def test_every_database_url_must_use_the_asyncpg_driver(field: str) -> None:
    urls: dict[str, Any] = {
        "database_url": APP_URL,
        field: "postgresql://opendoor:opendoor@localhost/opendoor",
    }
    with pytest.raises(ValidationError, match=rf"{field.upper()} must use the postgresql\+asyncpg"):
        Settings(_env_file=None, **urls)


def test_defaults_apply_when_only_the_database_url_is_set() -> None:
    settings = Settings(_env_file=None, database_url=APP_URL)
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.migration_database_url is None
    assert settings.cleanup_database_url is None
    assert settings.app_origin == "http://localhost:5173"


@pytest.mark.parametrize("field", DATABASE_URL_FIELDS)
def test_a_malformed_database_url_does_not_leak_its_password(field: str) -> None:
    urls: dict[str, Any] = {"database_url": APP_URL, field: "postgresql://app:hunter2@db/app"}
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, **urls)

    assert "hunter2" not in str(excinfo.value)


def test_no_database_password_appears_in_the_settings_repr() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://app:hunter2@localhost/app",
        migration_database_url="postgresql+asyncpg://owner:swordfish@localhost/app",
        cleanup_database_url="postgresql+asyncpg://cleanup:letmein@localhost/app",
    )

    for password in ("hunter2", "swordfish", "letmein"):
        assert password not in repr(settings)


@pytest.mark.parametrize(
    "origin", ["http://localhost:5173", "https://opendoor.example.com", "http://127.0.0.1:8080"]
)
def test_the_app_origin_accepts_a_bare_origin(origin: str) -> None:
    assert Settings(_env_file=None, database_url=APP_URL, app_origin=origin).app_origin == origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173/",
        "http://localhost:5173/app",
        "http://localhost:5173?next=1",
        "localhost:5173",
        "ftp://localhost",
        "HTTP://LOCALHOST:5173",
        "http://user@localhost:5173",
    ],
)
def test_the_app_origin_must_be_scheme_host_and_port_only(origin: str) -> None:
    with pytest.raises(ValidationError, match="APP_ORIGIN must look like"):
        Settings(_env_file=None, database_url=APP_URL, app_origin=origin)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_config.py -q`
Expected: `15 failed, 4 passed`. `Settings` ignores fields it doesn't know (`extra="ignore"`), so
the checks on the two new URLs never run, and it has no `app_origin`. The four that pass check
only `DATABASE_URL`, which Phase 0 already handled, or pass because the new fields are ignored.

- [ ] **Step 3: Replace `apps/api/app/core/config.py`**

```python
"""Application settings, read from the environment and validated once at startup."""

import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# What a browser sends in its Origin header: a lowercase scheme and host, an optional port, and
# nothing after them. The same-origin check compares that header with APP_ORIGIN character for
# character, so a trailing slash or a path here would refuse every request.
ORIGIN_PATTERN = re.compile(r"https?://[a-z0-9.-]+(:[0-9]{1,5})?")


class Settings(BaseSettings):
    """Every setting the API reads. A missing or malformed value stops the process at boot."""

    model_config = SettingsConfigDict(
        # Relative to the working directory: `make` and CI always run the API from apps/api.
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # A malformed database URL would otherwise print its password in the startup error.
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    # The API's own login, a member of od_app. Row-level security applies to it.
    database_url: PostgresDsn = Field(repr=False)
    # The database owner, for Alembic and the bootstrap script. The API never uses it.
    migration_database_url: PostgresDsn | None = Field(default=None, repr=False)
    # The cleanup login, a member of od_cleanup: its tests now, and the cleanup job in Phase 8.
    cleanup_database_url: PostgresDsn | None = Field(default=None, repr=False)
    # The web app's origin, for the same-origin check on requests that change state.
    app_origin: str = "http://localhost:5173"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url", "migration_database_url", "cleanup_database_url")
    @classmethod
    def require_asyncpg_driver(
        cls, value: PostgresDsn | None, info: ValidationInfo
    ) -> PostgresDsn | None:
        if value is not None and value.scheme != "postgresql+asyncpg":
            msg = f"{str(info.field_name).upper()} must use the postgresql+asyncpg:// scheme"
            raise ValueError(msg)
        return value

    @field_validator("app_origin")
    @classmethod
    def require_bare_origin(cls, value: str) -> str:
        if not ORIGIN_PATTERN.fullmatch(value):
            msg = "APP_ORIGIN must look like http://localhost:5173: no path and no trailing slash"
            raise ValueError(msg)
        return value


@lru_cache
def get_settings() -> Settings:
    """Read settings once per process."""
    return Settings()
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/test_config.py -q`
Expected: `19 passed`.

- [ ] **Step 5: Pin the new fields in the unit tests' `settings` fixture.** In
      `apps/api/tests/conftest.py`, replace the line `database_url=UNREACHABLE_DATABASE_URL,` with:

```python
        database_url=UNREACHABLE_DATABASE_URL,
        migration_database_url=None,
        cleanup_database_url=None,
        app_origin="http://localhost:5173",
```

- [ ] **Step 6: Pin them in the OpenAPI export too.** In `apps/api/scripts/export_openapi.py`,
      replace the line `database_url=SCHEMA_ONLY_DATABASE_URL,` with:

```python
        database_url=SCHEMA_ONLY_DATABASE_URL,
        migration_database_url=None,
        cleanup_database_url=None,
        app_origin="http://localhost:5173",
```

- [ ] **Step 7: Replace `apps/api/.env.example`**

```
# Copy to apps/api/.env for local development: cp .env.example .env
# This file is committed. Real secrets never go in it: these passwords are throwaway development
# values, and `make db` creates the two login users from them.
APP_ENV=development
# The API's own login, a member of od_app. It owns nothing, and row-level security applies to it.
DATABASE_URL=postgresql+asyncpg://od_app_login:od_app_dev@127.0.0.1:5433/opendoor
# The database owner (the Compose superuser). Alembic and the bootstrap script connect as it.
MIGRATION_DATABASE_URL=postgresql+asyncpg://opendoor:opendoor@127.0.0.1:5433/opendoor
# Optional. The cleanup login, a member of od_cleanup, which may delete only expired tenants.
CLEANUP_DATABASE_URL=postgresql+asyncpg://od_cleanup_login:od_cleanup_dev@127.0.0.1:5433/opendoor
# The web app's origin, which the same-origin check compares with each request's Origin header.
APP_ORIGIN=http://localhost:5173
LOG_LEVEL=INFO
```

- [ ] **Step 8: Run the API checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q && uv run python scripts/export_openapi.py --check`
Expected: `All checks passed!`, `30 files already formatted`,
`Success: no issues found in 30 source files`, `48 passed`, and
`apps/web/openapi.json is up to date.`

### Task 2: A typed engine accessor

This closes the Phase 1 backlog item "A typed engine accessor". The health check keeps its bare
connection, so it stays independent of row-level security.

**Files:**
- Create: `apps/api/app/api/deps.py`
- Modify: `apps/api/app/api/v1/health.py`
- Test: `apps/api/tests/test_deps.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_deps.py`

```python
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
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_deps.py -q`
Expected: a collection error, `ModuleNotFoundError: No module named 'app.api.deps'`.

- [ ] **Step 3: Create `apps/api/app/api/deps.py`**

```python
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
```

- [ ] **Step 4: Replace `apps/api/app/api/v1/health.py`,** so the health check gets its engine
      through `get_engine`

```python
"""GET /api/v1/health: is the API up, and can it reach its database?"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.api.deps import get_engine
from app.db.engine import ping

router = APIRouter(tags=["health"])

DatabasePing = Callable[[], Awaitable[bool]]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    version: str


def get_database_ping(engine: Annotated[AsyncEngine, Depends(get_engine)]) -> DatabasePing:
    """The database check, as a dependency so tests can replace it.

    It uses a bare connection, never a tenant session, so it stays independent of row-level
    security.
    """

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

- [ ] **Step 5: Run the new tests and the health tests**

Run: `cd apps/api && uv run pytest tests/test_deps.py tests/test_health.py -q`
Expected: `6 passed`.

- [ ] **Step 6: Run the API checks.** The schema doesn't change, because the engine isn't part of
      the request.

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q && uv run python scripts/export_openapi.py --check`
Expected: `All checks passed!`, `32 files already formatted`,
`Success: no issues found in 32 source files`, `50 passed`, and
`apps/web/openapi.json is up to date.`

### Task 3: Migrations run as the database owner

This closes the Phase 1 backlog item "Migrate as a separate database role".

**Files:**
- Modify: `apps/api/migrations/env.py`

- [ ] **Step 1: In `apps/api/migrations/env.py`, replace everything above
      `def run_migrations_offline` with:**

```python
"""Alembic's entry point. The database URL comes from the app's settings, never from alembic.ini."""

import asyncio
from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError
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
    """The owner. Migrations create roles, tables, and policies, which the API's login can't."""
    url = get_settings().migration_database_url
    if url is None:
        msg = (
            "MIGRATION_DATABASE_URL is not set. Migrations run as the database owner, not as the "
            "API's login. Add it to apps/api/.env; see .env.example."
        )
        raise CommandError(msg)
    return str(url)
```

Raising Alembic's `CommandError` prints one clear `FAILED:` line instead of a traceback.

- [ ] **Step 2: Confirm Alembic still reaches the database, now as the owner**

Run: `cd apps/api && uv run alembic current`
Expected: `0001 (head)`, after the two `INFO` lines.

- [ ] **Step 3: Confirm the refusal.** Comment out the `MIGRATION_DATABASE_URL` line in
      `apps/api/.env`, run the command below, then restore the line.

Run: `cd apps/api && uv run alembic current`
Expected: exit status 255, and
`FAILED: MIGRATION_DATABASE_URL is not set. Migrations run as the database owner, not as the API's login. Add it to apps/api/.env; see .env.example.`

- [ ] **Step 4: Run the linters and the type check**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: `All checks passed!`, `32 files already formatted`, and
`Success: no issues found in 32 source files`.

### Task 4: The roles and the context functions (migration 0002)

**Files:**
- Create: `apps/api/migrations/versions/0002_app_schema_and_roles.py`,
  `apps/api/tests/integration/conftest.py`
- Test: `apps/api/tests/integration/test_context_functions.py`

- [ ] **Step 1: Create `apps/api/tests/integration/conftest.py`,** with one engine per database
      login. Task 7 adds the tenant factory to this file.

```python
"""Database fixtures for the integration tests: one engine per database login.

`app_engine` connects as DATABASE_URL, `owner_engine` as MIGRATION_DATABASE_URL, and
`cleanup_engine` as CLEANUP_DATABASE_URL. A test that needs a URL that isn't set fails loudly
instead of skipping.
"""

from collections.abc import AsyncIterator

import pytest
from pydantic import PostgresDsn
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.engine import create_engine


@pytest.fixture(scope="session")
def database_settings() -> Settings:
    # Reads the environment (CI) or apps/api/.env (local development).
    return Settings()


def required_url(url: PostgresDsn | None, variable: str) -> str:
    if url is None:
        pytest.fail(f"{variable} is not set, so this test can't run. See apps/api/.env.example.")
    return str(url)


@pytest.fixture
async def app_engine(database_settings: Settings) -> AsyncIterator[AsyncEngine]:
    """The API's own login: a member of od_app, so row-level security applies to it."""
    engine = create_engine(str(database_settings.database_url))
    yield engine
    await engine.dispose()


@pytest.fixture
async def owner_engine(database_settings: Settings) -> AsyncIterator[AsyncEngine]:
    """The database owner, which runs the migrations."""
    url = required_url(database_settings.migration_database_url, "MIGRATION_DATABASE_URL")
    engine = create_engine(url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def cleanup_engine(database_settings: Settings) -> AsyncIterator[AsyncEngine]:
    """The cleanup login: a member of od_cleanup, which may delete only expired tenants."""
    url = required_url(database_settings.cleanup_database_url, "CLEANUP_DATABASE_URL")
    engine = create_engine(url)
    yield engine
    await engine.dispose()
```

- [ ] **Step 2: Write the failing tests** in
      `apps/api/tests/integration/test_context_functions.py`

```python
"""The helper functions every row-level security policy calls."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

READ_CONTEXT = text("SELECT app.current_tenant_id(), app.current_person_id(), app.current_is_hr()")
SET_CONTEXT = text(
    "SELECT set_config('app.tenant_id', :tenant_id, true),"
    " set_config('app.person_id', :person_id, true),"
    " set_config('app.is_hr', :is_hr, true)"
)


async def test_a_fresh_connection_has_no_tenant_person_or_hr(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        row = (await connection.execute(READ_CONTEXT)).one()

    assert tuple(row) == (None, None, False)


async def test_empty_settings_read_as_none_instead_of_failing(app_engine: AsyncEngine) -> None:
    # After one transaction sets a value locally, the next transaction on that connection sees ''
    # rather than NULL, and ''::uuid would raise. The functions turn '' into NULL.
    async with app_engine.connect() as connection:
        await connection.execute(SET_CONTEXT, {"tenant_id": "", "person_id": "", "is_hr": ""})
        row = (await connection.execute(READ_CONTEXT)).one()

    assert tuple(row) == (None, None, False)


async def test_set_values_come_back_typed(app_engine: AsyncEngine) -> None:
    tenant_id, person_id = uuid4(), uuid4()
    async with app_engine.connect() as connection:
        await connection.execute(
            SET_CONTEXT, {"tenant_id": str(tenant_id), "person_id": str(person_id), "is_hr": "true"}
        )
        row = (await connection.execute(READ_CONTEXT)).one()

    assert tuple(row) == (tenant_id, person_id, True)


async def test_the_functions_are_stable_and_never_leakproof_or_security_definer(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT proname, provolatile::text, proleakproof, prosecdef FROM pg_proc"
                " WHERE pronamespace = 'app'::regnamespace ORDER BY proname"
            )
        )
        functions = [tuple(row) for row in rows]

    assert functions == [
        ("current_is_hr", "s", False, False),
        ("current_person_id", "s", False, False),
        ("current_tenant_id", "s", False, False),
    ]
```

`provolatile` is Postgres's one-byte `"char"` type, which asyncpg returns as bytes, so the query
casts it to text.

- [ ] **Step 3: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/integration -q`
Expected: `4 failed, 2 passed`. Each failure ends with
`asyncpg.exceptions.InvalidSchemaNameError: schema "app" does not exist`. The two Phase 0
database tests pass.

- [ ] **Step 4: Create `apps/api/migrations/versions/0002_app_schema_and_roles.py`**

```python
"""Create the database roles and the functions row-level security reads the tenant from.

od_app is the API's role and od_cleanup the expired-tenant cleanup's. Neither can log in: the
bootstrap script (scripts/bootstrap_db_users.py) creates the login users and grants them these
roles. Migration 0003 grants the roles their table privileges.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Roles belong to the whole Postgres server, not to one database, so another database on the same
# server may have created them already.
CREATE_ROLES = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'od_app') THEN
        CREATE ROLE od_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'od_cleanup') THEN
        CREATE ROLE od_cleanup NOLOGIN;
    END IF;
END
$$
"""

# Each setting is set per transaction with set_config(..., true). Once a transaction has set one,
# later transactions on the same connection read '' instead of NULL, and ''::uuid raises an error.
# NULLIF turns '' back into NULL, which matches no row. Never LEAKPROOF, never SECURITY DEFINER.
CONTEXT_FUNCTIONS = (
    """
    CREATE FUNCTION app.current_tenant_id() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$
    """,
    """
    CREATE FUNCTION app.current_person_id() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('app.person_id', true), '')::uuid $$
    """,
    """
    CREATE FUNCTION app.current_is_hr() RETURNS boolean
    LANGUAGE sql STABLE
    AS $$ SELECT coalesce(NULLIF(current_setting('app.is_hr', true), '')::boolean, false) $$
    """,
)


def upgrade() -> None:
    op.execute(CREATE_ROLES)
    op.execute("CREATE SCHEMA app")
    for function in CONTEXT_FUNCTIONS:
        op.execute(function)
    op.execute("GRANT USAGE ON SCHEMA public, app TO od_app, od_cleanup")


def downgrade() -> None:
    op.execute("REVOKE USAGE ON SCHEMA public FROM od_app, od_cleanup")
    op.execute("DROP FUNCTION app.current_is_hr()")
    op.execute("DROP FUNCTION app.current_person_id()")
    op.execute("DROP FUNCTION app.current_tenant_id()")
    op.execute("DROP SCHEMA app")
    # The roles stay. Other databases on the server may use them, and dropping them would also
    # drop the login users' memberships. Upgrading again reuses them.
```

- [ ] **Step 5: Apply it, and run the tests again**

Run: `cd apps/api && uv run alembic upgrade head && uv run pytest tests/integration -q`
Expected:
`Running upgrade 0001 -> 0002, Create the database roles and the functions row-level security reads the tenant from.`,
then `6 passed`.

- [ ] **Step 6: Reverse it, and confirm the roles stay and everything else goes.** Run each from
      the repository root.

Run: `cd apps/api && uv run alembic downgrade 0001`
Expected: `Running downgrade 0002 -> 0001, ...`

Run: `docker compose exec -T db psql -U opendoor -d opendoor -tAc "SELECT rolname FROM pg_roles WHERE rolname IN ('od_app', 'od_cleanup') ORDER BY 1"`
Expected: `od_app` and `od_cleanup`, on two lines.

Run: `docker compose exec -T db psql -U opendoor -d opendoor -tAc "SELECT count(*) FROM pg_namespace WHERE nspname = 'app'"`
Expected: `0`.

- [ ] **Step 7: Apply it again.** The `DO` block finds both roles and reuses them.

Run: `cd apps/api && uv run alembic upgrade head && uv run pytest tests/integration -q`
Expected: `Running upgrade 0001 -> 0002, ...`, then `6 passed`.

- [ ] **Step 8: Run the API checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q`
Expected: `All checks passed!`, `35 files already formatted`,
`Success: no issues found in 35 source files`, and `54 passed`.

### Task 5: The tables, their row-level security, and the grants (migration 0003)

**Files:**
- Create: `apps/api/app/db/models.py`, `apps/api/migrations/versions/0003_tenant_tables.py`
- Modify: `apps/api/app/db/base.py`, `apps/api/migrations/env.py`
- Test: `apps/api/tests/integration/test_row_level_security.py`,
  `apps/api/tests/integration/test_grants.py`

- [ ] **Step 1: Write the failing tests for the schema's rules** in
      `apps/api/tests/integration/test_row_level_security.py`

```python
"""Row-level security covers every tenant table, and nothing in the schema crosses tenants."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

# `sessions` has a tenant_id, but a session is looked up by its token before the tenant is known,
# so row-level security can't filter it. It is the only such table.
NOT_A_TENANT_TABLE = "sessions"

# The catalog queries below find the tables on their own, so a new table is covered without being
# listed. These names only stop a broken query from passing by finding nothing.
KNOWN_TABLES = {"tenants", "locations", "departments", "people", "person_private", "holidays"}
KNOWN_UNIQUE_INDEXES = {"uq_people_tenant_id_work_email", "pk_person_private"}

TABLES_WITH_A_TENANT = """
    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r', 'p')
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND (c.relname = 'tenants' OR EXISTS (
          SELECT FROM pg_attribute a
          WHERE a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
      ))
"""

# Each unique index on a table with a tenant_id, with its first column and that column's type.
# An expression index has no first column, so it comes back with NULLs and fails the rule.
UNIQUE_INDEXES = """
    SELECT c.relname, i.relname, x.indisprimary, x.indnkeyatts, a.attname,
           format_type(a.atttypid, a.atttypmod)
    FROM pg_index x
    JOIN pg_class c ON c.oid = x.indrelid
    JOIN pg_class i ON i.oid = x.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = x.indkey[0]
    WHERE x.indisunique
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND c.relname <> :not_a_tenant_table
      AND EXISTS (
          SELECT FROM pg_attribute t
          WHERE t.attrelid = c.oid AND t.attname = 'tenant_id' AND NOT t.attisdropped
      )
"""

VIEWS_WITHOUT_SECURITY_INVOKER = """
    SELECT n.nspname || '.' || c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'v'
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND NOT coalesce((
          SELECT option_value::boolean FROM pg_options_to_table(c.reloptions)
          WHERE option_name = 'security_invoker'
      ), false)
"""


async def test_every_tenant_table_has_row_level_security_enabled_and_forced(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as connection:
        rows = (await connection.execute(text(TABLES_WITH_A_TENANT))).all()
    tables = {name: (enabled, forced) for name, enabled, forced in rows}

    assert set(tables) >= KNOWN_TABLES
    unprotected = {name for name, flags in tables.items() if flags != (True, True)}
    assert unprotected == {NOT_A_TENANT_TABLE}


async def test_unique_indexes_on_tenant_tables_start_with_tenant_id(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(UNIQUE_INDEXES), {"not_a_tenant_table": NOT_A_TENANT_TABLE}
            )
        ).all()

    assert {index for _, index, *_ in rows} >= KNOWN_UNIQUE_INDEXES
    # A global unique rule would leak whether a value exists in another tenant. The exception is a
    # single-column primary key on a UUID the server generates.
    breaking_the_rule = [
        (table, index)
        for table, index, is_primary, key_count, first_column, first_type in rows
        if first_column != "tenant_id"
        and not (is_primary and key_count == 1 and first_type == "uuid")
    ]
    assert breaking_the_rule == []


async def test_every_view_runs_with_the_callers_permissions(app_engine: AsyncEngine) -> None:
    # A view runs as its owner by default, which would skip row-level security. Phase 1 has no
    # views; this guards the ones to come.
    async with app_engine.connect() as connection:
        result = await connection.execute(text(VIEWS_WITHOUT_SECURITY_INVOKER))
        views: list[str] = list(result.scalars())

    assert views == []
```

- [ ] **Step 2: Write the failing tests for the exact grants** in
      `apps/api/tests/integration/test_grants.py`

```python
"""The two roles have exactly the privileges the spec lists: nothing missing and nothing extra.

A new table that forgets its grants fails closed, because the API can't touch it. A grant broader
than the spec fails these tests.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

ROLES = ("od_app", "od_cleanup")
READ_AND_ADD = ("tenants", "locations", "departments", "people", "person_private", "holidays")

EXPECTED_TABLE_GRANTS = {
    *(("od_app", table, privilege) for table in READ_AND_ADD for privilege in ("SELECT", "INSERT")),
    # Append-only: no UPDATE or DELETE, ever.
    ("od_app", "audit_events", "SELECT"),
    ("od_app", "audit_events", "INSERT"),
    ("od_app", "sessions", "SELECT"),
    ("od_app", "sessions", "INSERT"),
    ("od_app", "sessions", "DELETE"),
    ("od_cleanup", "tenants", "SELECT"),
    ("od_cleanup", "tenants", "DELETE"),
}
EXPECTED_SCHEMA_GRANTS = {(role, schema, "USAGE") for role in ROLES for schema in ("public", "app")}

# Grants to PUBLIC count too, because every role inherits them.
TABLE_GRANTS = """
    SELECT coalesce(r.rolname, 'PUBLIC'), c.relname, a.privilege_type
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL aclexplode(c.relacl) a
    LEFT JOIN pg_roles r ON r.oid = a.grantee
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND (a.grantee = 0 OR r.rolname = ANY(:roles))
"""

COLUMN_GRANTS = """
    SELECT coalesce(r.rolname, 'PUBLIC'), c.relname, col.attname, a.privilege_type
    FROM pg_attribute col
    JOIN pg_class c ON c.oid = col.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL aclexplode(col.attacl) a
    LEFT JOIN pg_roles r ON r.oid = a.grantee
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND (a.grantee = 0 OR r.rolname = ANY(:roles))
"""

SCHEMA_GRANTS = """
    SELECT r.rolname, n.nspname, a.privilege_type
    FROM pg_namespace n
    CROSS JOIN LATERAL aclexplode(n.nspacl) a
    JOIN pg_roles r ON r.oid = a.grantee
    WHERE r.rolname = ANY(:roles)
"""


async def grants(engine: AsyncEngine, query: str) -> set[tuple[str, ...]]:
    async with engine.connect() as connection:
        rows = await connection.execute(text(query), {"roles": list(ROLES)})
        return {tuple(row) for row in rows}


async def test_the_roles_have_exactly_the_planned_table_privileges(
    app_engine: AsyncEngine,
) -> None:
    assert await grants(app_engine, TABLE_GRANTS) == EXPECTED_TABLE_GRANTS


async def test_no_role_has_privileges_on_single_columns(app_engine: AsyncEngine) -> None:
    assert await grants(app_engine, COLUMN_GRANTS) == set()


async def test_the_roles_can_use_exactly_the_public_and_app_schemas(
    app_engine: AsyncEngine,
) -> None:
    assert await grants(app_engine, SCHEMA_GRANTS) == EXPECTED_SCHEMA_GRANTS
```

- [ ] **Step 3: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/integration/test_row_level_security.py tests/integration/test_grants.py -q`
Expected: `3 failed, 3 passed`.
- The coverage and unique-index tests find no tables: `AssertionError: assert set() >= {...}`.
- The table-grants test finds no privileges: `AssertionError: assert set() == {('od_app', ...`.
- The view, column, and schema tests already pass. There are no views and no column grants, and
  migration 0002 granted the schemas.

- [ ] **Step 4: Replace `apps/api/app/db/base.py`**

```python
"""The declarative base every table inherits from."""

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, Text
from sqlalchemy.orm import DeclarativeBase

# Named constraints make migrations reviewable and let Alembic drop them by name later. All of a
# constraint's or index's columns go into its name, so composite ones stay distinct.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Postgres types for plain annotations: `str` is text, not varchar, and every timestamp keeps
    # its time zone (timestamptz), so it is stored as UTC.
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        str: Text(),
        datetime: DateTime(timezone=True),
    }
```

- [ ] **Step 5: Create `apps/api/app/db/models.py`**

```python
"""The Phase 1 tables. Migration 0003 creates them, with their row-level security and grants.

Every table except `tenants` and `sessions` is a tenant table: it has a tenant_id, and Postgres
shows the API only the rows of the tenant its transaction is scoped to (see app/db/tenancy.py).
Three rules keep tenants apart inside the schema:

- Unique rules start with tenant_id, so they never reveal whether a value exists in another
  tenant. A single-column primary key on a server-generated UUID is the only exception.
- Every reference is a composite foreign key that includes tenant_id, against a parent's
  UNIQUE (tenant_id, id), so a row can only point at rows in its own tenant.
- Children are deleted with their tenant (ON DELETE CASCADE from tenants). References between
  children use the default NO ACTION, so one cascading delete removes them together.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TENANT_FK = "tenants.id"


class Tenant(Base):
    """One sandbox company. It and everything in it are deleted 24 hours after it is created."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    # The date the seed data is relative to, so "last week" always means last week.
    anchor_date: Mapped[date]


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    code: Mapped[str]
    name: Mapped[str]
    city: Mapped[str]
    state: Mapped[str]
    # An IANA zone such as America/Denver. Leave dates are calendar dates in this zone.
    timezone: Mapped[str]


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    name: Mapped[str]


class Person(Base):
    """The directory tier. Being a manager is derived from manager_id, never stored."""

    __tablename__ = "people"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "work_email"),
        UniqueConstraint("tenant_id", "persona_key"),
        ForeignKeyConstraint(
            ["tenant_id", "department_id"], ["departments.tenant_id", "departments.id"]
        ),
        ForeignKeyConstraint(["tenant_id", "location_id"], ["locations.tenant_id", "locations.id"]),
        ForeignKeyConstraint(["tenant_id", "manager_id"], ["people.tenant_id", "people.id"]),
        CheckConstraint("employment_type IN ('salaried', 'hourly')", name="employment_type"),
        CheckConstraint("persona_key IN ('priya', 'mateo', 'marcus', 'dana')", name="persona_key"),
        # Directory paging, and the recursive query for a manager's reports.
        Index(None, "tenant_id", "family_name", "given_name", "id"),
        Index(None, "tenant_id", "manager_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    given_name: Mapped[str]
    family_name: Mapped[str]
    title: Mapped[str]
    department_id: Mapped[uuid.UUID]
    location_id: Mapped[uuid.UUID]
    manager_id: Mapped[uuid.UUID | None]
    work_email: Mapped[str]
    employment_type: Mapped[str]
    hire_date: Mapped[date]
    is_hr_admin: Mapped[bool] = mapped_column(server_default=false())
    persona_key: Mapped[str | None]


class PersonPrivate(Base):
    """Private details. Postgres shows a row only to the person themselves and to HR."""

    __tablename__ = "person_private"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "person_id"], ["people.tenant_id", "people.id"]),
        Index(None, "tenant_id", "person_id"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    personal_email: Mapped[str]
    phone: Mapped[str]
    home_address: Mapped[str]
    date_of_birth: Mapped[date]


class Holiday(Base):
    """A company holiday at one location, for the Phase 5 time-off engine."""

    __tablename__ = "holidays"
    __table_args__ = (
        UniqueConstraint("tenant_id", "location_id", "holiday_date"),
        ForeignKeyConstraint(["tenant_id", "location_id"], ["locations.tenant_id", "locations.id"]),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    location_id: Mapped[uuid.UUID]
    holiday_date: Mapped[date]
    name: Mapped[str]


class UserSession(Base):
    """A signed-in visitor. Outside row-level security: it is looked up before the tenant is known.

    Both hashes are SHA-256 digests. The raw tokens live only in the visitor's cookies.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "person_id"], ["people.tenant_id", "people.id"]),
        CheckConstraint("octet_length(token_hash) = 32", name="token_hash_is_sha256"),
        CheckConstraint("octet_length(csrf_hash) = 32", name="csrf_hash_is_sha256"),
        Index(None, "tenant_id", "person_id"),
    )

    token_hash: Mapped[bytes] = mapped_column(primary_key=True)
    csrf_hash: Mapped[bytes]
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    person_id: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Copied from the tenant: a session never outlives its sandbox.
    expires_at: Mapped[datetime]


class AuditEvent(Base):
    """One recorded action. The API may only add and read these rows, never change them.

    IDs are random UUIDs, not a sequence, which would let one tenant estimate another's activity.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "actor_person_id"], ["people.tenant_id", "people.id"]),
        CheckConstraint("via IN ('ui', 'assistant', 'system')", name="via"),
        Index(None, "tenant_id", "occurred_at"),
        Index(None, "tenant_id", "actor_person_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(TENANT_FK, ondelete="CASCADE"))
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
    actor_person_id: Mapped[uuid.UUID | None]
    via: Mapped[str]
    action: Mapped[str]
    target_type: Mapped[str | None]
    target_id: Mapped[uuid.UUID | None]
    # Directory fields only. A read of private details records the field names, never the values.
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    proposal_id: Mapped[uuid.UUID | None]
    request_id: Mapped[str | None]
```

- [ ] **Step 6: Make Alembic see the models.** In `apps/api/migrations/env.py`, replace the line
      `from app.core.config import get_settings` with:

```python
from app.core.config import get_settings

# Importing the models puts every table on Base.metadata, which `alembic check` compares.
from app.db import models  # noqa: F401
```

Ruff's import sorting wants the blank line before the comment.

- [ ] **Step 7: Confirm that `alembic check` now fails,** because the models have tables the
      database doesn't

Run: `cd apps/api && uv run alembic check`
Expected: `FAILED: New upgrade operations detected: [('add_table', Table('tenants', ...`, listing
every table and index in `models.py`.

- [ ] **Step 8: Create `apps/api/migrations/versions/0003_tenant_tables.py`**

```python
"""Create the Phase 1 tables, with row-level security, their policies, and the roles' grants.

Every table except tenants and sessions is a tenant table: row-level security is enabled and
forced, and the tenant_isolation policy shows od_app only the rows of the tenant its transaction
is scoped to. app/db/models.py describes the same tables, and `alembic check` keeps the two in step.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("locations", "departments", "people", "person_private", "holidays", "audit_events")

# Created in this order, dropped in reverse.
ALL_TABLES = (
    "tenants",
    "locations",
    "departments",
    "people",
    "person_private",
    "holidays",
    "sessions",
    "audit_events",
)

# Policies call the functions as (SELECT ...), so Postgres evaluates them once per query, not once
# per row.
ROW_LEVEL_SECURITY = (
    *(
        statement
        for table in TENANT_TABLES
        for statement in (
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"""
            CREATE POLICY tenant_isolation ON {table} FOR ALL TO od_app
                USING (tenant_id = (SELECT app.current_tenant_id()))
                WITH CHECK (tenant_id = (SELECT app.current_tenant_id()))
            """,
        )
    ),
    "ALTER TABLE tenants ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE tenants FORCE ROW LEVEL SECURITY",
    """
    CREATE POLICY tenant_self ON tenants FOR ALL TO od_app
        USING (id = (SELECT app.current_tenant_id()))
        WITH CHECK (id = (SELECT app.current_tenant_id()))
    """,
    # Scoped TO od_cleanup, so the API never inherits them.
    """
    CREATE POLICY cleanup_select ON tenants FOR SELECT TO od_cleanup
        USING (expires_at < now())
    """,
    """
    CREATE POLICY cleanup_delete ON tenants FOR DELETE TO od_cleanup
        USING (expires_at < now())
    """,
    # A second, restrictive rule: a private-details row is visible only to its person and to HR.
    # It covers reads only, so seeding can still insert the rows.
    """
    CREATE POLICY private_self_or_hr ON person_private AS RESTRICTIVE FOR SELECT TO od_app
        USING (person_id = (SELECT app.current_person_id()) OR (SELECT app.current_is_hr()))
    """,
)

# No UPDATE anywhere yet; later phases add exactly what they need. Never TRUNCATE, which ignores
# row-level security, and never REFERENCES or TRIGGER.
GRANTS = (
    "GRANT SELECT, INSERT ON tenants, locations, departments, people, person_private, holidays,"
    " audit_events TO od_app",
    "GRANT SELECT, INSERT, DELETE ON sessions TO od_app",
    "GRANT SELECT, DELETE ON tenants TO od_cleanup",
)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anchor_date", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )
    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_locations_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
        sa.UniqueConstraint("tenant_id", "code", name=op.f("uq_locations_tenant_id_code")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_locations_tenant_id_id")),
    )
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_departments_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_departments_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", "name", name=op.f("uq_departments_tenant_id_name")),
    )
    op.create_table(
        "people",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("given_name", sa.Text(), nullable=False),
        sa.Column("family_name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("manager_id", sa.Uuid(), nullable=True),
        sa.Column("work_email", sa.Text(), nullable=False),
        sa.Column("employment_type", sa.Text(), nullable=False),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("is_hr_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("persona_key", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "employment_type IN ('salaried', 'hourly')",
            name=op.f("ck_people_employment_type"),
        ),
        sa.CheckConstraint(
            "persona_key IN ('priya', 'mateo', 'marcus', 'dana')",
            name=op.f("ck_people_persona_key"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["departments.tenant_id", "departments.id"],
            name=op.f("fk_people_tenant_id_department_id_departments"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["locations.tenant_id", "locations.id"],
            name=op.f("fk_people_tenant_id_location_id_locations"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "manager_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_people_tenant_id_manager_id_people"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_people_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_people")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_people_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "persona_key", name=op.f("uq_people_tenant_id_persona_key")
        ),
        sa.UniqueConstraint("tenant_id", "work_email", name=op.f("uq_people_tenant_id_work_email")),
    )
    op.create_index(
        op.f("ix_people_tenant_id_family_name_given_name_id"),
        "people",
        ["tenant_id", "family_name", "given_name", "id"],
    )
    op.create_index(op.f("ix_people_tenant_id_manager_id"), "people", ["tenant_id", "manager_id"])
    op.create_table(
        "person_private",
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("personal_email", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("home_address", sa.Text(), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_person_private_tenant_id_person_id_people"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_person_private_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("person_id", name=op.f("pk_person_private")),
    )
    op.create_index(
        op.f("ix_person_private_tenant_id_person_id"),
        "person_private",
        ["tenant_id", "person_id"],
    )
    op.create_table(
        "holidays",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["locations.tenant_id", "locations.id"],
            name=op.f("fk_holidays_tenant_id_location_id_locations"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_holidays_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_holidays")),
        sa.UniqueConstraint(
            "tenant_id",
            "location_id",
            "holiday_date",
            name=op.f("uq_holidays_tenant_id_location_id_holiday_date"),
        ),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("csrf_hash", sa.LargeBinary(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "octet_length(csrf_hash) = 32", name=op.f("ck_sessions_csrf_hash_is_sha256")
        ),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("ck_sessions_token_hash_is_sha256")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_sessions_tenant_id_person_id_people"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_sessions_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_sessions")),
    )
    op.create_index(op.f("ix_sessions_tenant_id_person_id"), "sessions", ["tenant_id", "person_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_person_id", sa.Uuid(), nullable=True),
        sa.Column("via", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "via IN ('ui', 'assistant', 'system')", name=op.f("ck_audit_events_via")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_person_id"],
            ["people.tenant_id", "people.id"],
            name=op.f("fk_audit_events_tenant_id_actor_person_id_people"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_audit_events_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        op.f("ix_audit_events_tenant_id_actor_person_id"),
        "audit_events",
        ["tenant_id", "actor_person_id"],
    )
    op.create_index(
        op.f("ix_audit_events_tenant_id_occurred_at"),
        "audit_events",
        ["tenant_id", "occurred_at"],
    )
    for statement in (*ROW_LEVEL_SECURITY, *GRANTS):
        op.execute(statement)


def downgrade() -> None:
    # Dropping a table also drops its indexes, policies, and grants.
    for table in reversed(ALL_TABLES):
        op.drop_table(table)
```

- [ ] **Step 9: Apply it, and confirm the models and migrations agree**

Run: `cd apps/api && uv run alembic upgrade head && uv run alembic check`
Expected:
`Running upgrade 0002 -> 0003, Create the Phase 1 tables, with row-level security, their policies, and the roles' grants.`,
then `No new upgrade operations detected.`
`alembic check` also compares foreign-key options: while planning, dropping `ondelete="CASCADE"`
from one model made it fail.

- [ ] **Step 10: Run the database tests**

Run: `cd apps/api && uv run pytest tests/integration -q`
Expected: `12 passed`.

- [ ] **Step 11: Prove the view guard can fail, then undo.** Run each from the repository root.

Run: `docker compose exec -T db psql -U opendoor -d opendoor -c "CREATE VIEW zz_people AS SELECT id FROM people"`
Then run: `cd apps/api && uv run pytest tests/integration/test_row_level_security.py -q`
Expected: `1 failed, 2 passed`, with `AssertionError: assert ['public.zz_people'] == []`.
Then run: `docker compose exec -T db psql -U opendoor -d opendoor -c "DROP VIEW zz_people"`

The same view created `WITH (security_invoker = on)` passes.

- [ ] **Step 12: Run the API checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
Expected: `All checks passed!`, `39 files already formatted`,
`Success: no issues found in 39 source files`, `Domain code imports no framework KEPT`, and
`60 passed`.

### Task 6: The login users (the bootstrap script)

**Files:**
- Create: `apps/api/scripts/bootstrap_db_users.py`
- Modify: your own `apps/api/.env` (not committed)
- Test: `apps/api/tests/integration/test_logins.py`,
  `apps/api/tests/integration/test_bootstrap.py`

- [ ] **Step 1: Write the failing tests for the logins** in
      `apps/api/tests/integration/test_logins.py`

```python
"""The login users get their privileges only through od_app or od_cleanup, and bypass nothing."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

# pg_has_role(..., 'USAGE') asks whether the login has the role's privileges, which holds only if
# its membership passes them on (INHERIT). Policies written TO od_app reach the login the same way.
WHO_AM_I = """
    SELECT rolname, rolsuper, rolbypassrls, rolcanlogin,
           pg_has_role(current_user, 'od_app', 'USAGE'),
           pg_has_role(current_user, 'od_cleanup', 'USAGE')
    FROM pg_roles WHERE rolname = current_user
"""

# Objects owned by the two roles or by any login that is a member of either.
OWNED_BY_ROLES_OR_LOGINS = """
    WITH accounts AS (
        SELECT oid FROM pg_roles WHERE rolname IN ('od_app', 'od_cleanup')
        UNION
        SELECT member FROM pg_auth_members
        WHERE roleid IN ('od_app'::regrole, 'od_cleanup'::regrole)
    )
    SELECT (SELECT count(*) FROM pg_class WHERE relowner IN (SELECT oid FROM accounts))
         + (SELECT count(*) FROM pg_namespace WHERE nspowner IN (SELECT oid FROM accounts))
         + (SELECT count(*) FROM pg_proc WHERE proowner IN (SELECT oid FROM accounts))
"""

# Privileges granted to a login directly, instead of through its role.
GRANTED_TO_LOGINS = """
    WITH logins AS (
        SELECT member AS oid FROM pg_auth_members
        WHERE roleid IN ('od_app'::regrole, 'od_cleanup'::regrole)
    )
    SELECT c.relname FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a
    WHERE a.grantee IN (SELECT oid FROM logins)
    UNION ALL
    SELECT n.nspname FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a
    WHERE a.grantee IN (SELECT oid FROM logins)
"""


async def who_am_i(engine: AsyncEngine) -> tuple[object, ...]:
    async with engine.connect() as connection:
        return tuple((await connection.execute(text(WHO_AM_I))).one())


async def test_the_api_logs_in_as_its_own_user_with_only_the_app_role(
    app_engine: AsyncEngine,
) -> None:
    name, superuser, bypass_rls, can_login, has_app, has_cleanup = await who_am_i(app_engine)

    assert name not in ("od_app", "od_cleanup")
    assert (superuser, bypass_rls, can_login) == (False, False, True)
    assert (has_app, has_cleanup) == (True, False)


async def test_the_cleanup_login_has_only_the_cleanup_role(cleanup_engine: AsyncEngine) -> None:
    name, superuser, bypass_rls, can_login, has_app, has_cleanup = await who_am_i(cleanup_engine)

    assert name not in ("od_app", "od_cleanup")
    assert (superuser, bypass_rls, can_login) == (False, False, True)
    assert (has_app, has_cleanup) == (False, True)


async def test_the_roles_cannot_log_in_or_bypass_row_level_security(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT rolname, rolsuper, rolbypassrls, rolcanlogin FROM pg_roles"
                " WHERE rolname IN ('od_app', 'od_cleanup') ORDER BY rolname"
            )
        )
        roles = [tuple(row) for row in rows]

    assert roles == [("od_app", False, False, False), ("od_cleanup", False, False, False)]


async def test_the_roles_and_their_logins_own_nothing(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        owned: int = (await connection.execute(text(OWNED_BY_ROLES_OR_LOGINS))).scalar_one()

    assert owned == 0


async def test_the_logins_have_no_privileges_of_their_own(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        direct = (await connection.execute(text(GRANTED_TO_LOGINS))).all()

    assert direct == []
```

- [ ] **Step 2: Write the failing test for the script** in
      `apps/api/tests/integration/test_bootstrap.py`

```python
"""The bootstrap script creates a login user from a URL, quotes it safely, and can run again."""

import asyncio
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.engine import create_engine

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[2]

# Quotes, a semicolon, a comment, a backslash, and placeholder lookalikes. Pasted into SQL by hand,
# any of them would break the statement or change which user and password it sets. The password is
# a test value, not a secret.
ODD_USER = 'od_test_o\'brien "x"; --'
ODD_PASSWORD = 'it\'s "quoted"; -- \\ :name %(x)s %s $1 ?'  # noqa: S105


async def run_bootstrap(database_url: str) -> str:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "scripts/bootstrap_db_users.py",
        cwd=API_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await process.communicate()
    assert process.returncode == 0, output.decode()
    return output.decode()


async def drop_role(owner_engine: AsyncEngine, name: str) -> None:
    async with owner_engine.begin() as connection:
        statement: str = (
            await connection.execute(
                text("SELECT format('DROP ROLE IF EXISTS %I', CAST(:name AS text))"),
                {"name": name},
            )
        ).scalar_one()
        await connection.exec_driver_sql(statement)


async def test_odd_names_and_passwords_are_quoted_and_a_second_run_only_updates(
    database_settings: Settings, owner_engine: AsyncEngine
) -> None:
    url = make_url(str(database_settings.database_url)).set(
        username=ODD_USER, password=ODD_PASSWORD
    )
    odd_url = url.render_as_string(hide_password=False)
    try:
        first = await run_bootstrap(odd_url)
        second = await run_bootstrap(odd_url)

        engine = create_engine(odd_url)
        try:
            async with engine.connect() as connection:
                who = await connection.execute(
                    text("SELECT current_user, pg_has_role(current_user, 'od_app', 'USAGE')")
                )
                row = tuple(who.one())
        finally:
            await engine.dispose()
    finally:
        await drop_role(owner_engine, ODD_USER)

    assert f"{ODD_USER}: created, with od_app" in first
    assert f"{ODD_USER}: password reset, with od_app" in second
    assert row == (ODD_USER, True)
```

- [ ] **Step 3: Point `DATABASE_URL` at the API's own login.** In `apps/api/.env`, replace the
      `DATABASE_URL` line with:

```
DATABASE_URL=postgresql+asyncpg://od_app_login:od_app_dev@127.0.0.1:5433/opendoor
```

- [ ] **Step 4: Run the database tests and watch them fail**

Run: `cd apps/api && uv run pytest tests/integration -q`
Expected: `18 failed`, because the login doesn't exist yet.
- Most fail with
  `asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "od_app_login"`.
  One cleanup-login test fails the same way for `od_cleanup_login`.
- The Phase 0 ping test fails with `assert False is True`.
- The bootstrap test fails with `can't open file '.../apps/api/scripts/bootstrap_db_users.py'`.

- [ ] **Step 5: Create `apps/api/scripts/bootstrap_db_users.py`**

```python
"""Create or update the database login users, and grant each one its role.

Runs as the database owner (MIGRATION_DATABASE_URL), after the migrations have created the roles.
Each login's name and password come from its own URL, so each URL is the single source of truth
for its user:

- DATABASE_URL names the API's login, which gets od_app.
- CLEANUP_DATABASE_URL, if set, names the cleanup login, which gets od_cleanup.

A second run only resets the passwords, so `make db` runs it every time. Postgres quotes every name
and password itself, through format('%I') for names and format('%L') for values, so nothing from a
URL is ever pasted into SQL by hand.
"""

import asyncio
from dataclasses import dataclass, field

from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings

ROLES = ("od_app", "od_cleanup")

CREATE_LOGIN = "CREATE ROLE %I WITH LOGIN PASSWORD %L"
ALTER_LOGIN = "ALTER ROLE %I WITH LOGIN PASSWORD %L"
# The login must inherit the role's privileges: the row-level security policies are written
# TO od_app, and they reach the login only through an inheriting membership.
GRANT_ROLE = "GRANT %I TO %I WITH INHERIT TRUE"

FORMAT = text("SELECT format(CAST(:template AS text), CAST(:first AS text), CAST(:second AS text))")


@dataclass(frozen=True)
class Login:
    user: str
    password: str = field(repr=False)
    role: str


def login_from(url: PostgresDsn, variable: str, role: str, owner: str) -> Login:
    parsed = make_url(str(url))
    if not parsed.username or not parsed.password:
        raise SystemExit(f"{variable} must include a user name and a password.")
    if parsed.username == owner or parsed.username in ROLES:
        raise SystemExit(
            f"{variable} names {parsed.username!r}. It needs a login user of its own, such as "
            f"{role}_login, so that row-level security applies to it. See apps/api/.env.example."
        )
    return Login(parsed.username, parsed.password, role)


async def server_formatted(
    connection: AsyncConnection, template: str, first: str, second: str
) -> str:
    """Fill in a format() template on the server, which quotes both values safely."""
    result = await connection.execute(
        FORMAT, {"template": template, "first": first, "second": second}
    )
    return str(result.scalar_one())


async def ensure_login(connection: AsyncConnection, login: Login) -> str:
    exists = await connection.scalar(
        text("SELECT EXISTS (SELECT FROM pg_roles WHERE rolname = :user)"), {"user": login.user}
    )
    template = ALTER_LOGIN if exists else CREATE_LOGIN
    # exec_driver_sql sends each statement exactly as Postgres built it. text() would read
    # ":name" inside a password as a bind parameter.
    await connection.exec_driver_sql(
        await server_formatted(connection, template, login.user, login.password)
    )
    await connection.exec_driver_sql(
        await server_formatted(connection, GRANT_ROLE, login.role, login.user)
    )
    return f"{login.user}: {'password reset' if exists else 'created'}, with {login.role}"


async def main() -> None:
    settings = get_settings()
    if settings.migration_database_url is None:
        raise SystemExit("MIGRATION_DATABASE_URL is not set. See apps/api/.env.example.")
    owner_url = str(settings.migration_database_url)
    owner = make_url(owner_url).username or ""

    logins = [login_from(settings.database_url, "DATABASE_URL", "od_app", owner)]
    if settings.cleanup_database_url is not None:
        logins.append(
            login_from(settings.cleanup_database_url, "CLEANUP_DATABASE_URL", "od_cleanup", owner)
        )
    if len({login.user for login in logins}) < len(logins):
        raise SystemExit("DATABASE_URL and CLEANUP_DATABASE_URL must name different users.")

    engine = create_async_engine(owner_url)
    try:
        async with engine.begin() as connection:
            existing = await connection.scalars(
                text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
                {"roles": list(ROLES)},
            )
            if set(existing) != set(ROLES):
                raise SystemExit("The od_app and od_cleanup roles don't exist. Run `make migrate`.")
            for login in logins:
                print(await ensure_login(connection, login))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 6: Confirm it refuses to hand the owner's name to the API**

Run: `cd apps/api && DATABASE_URL=postgresql+asyncpg://opendoor:opendoor@127.0.0.1:5433/opendoor uv run python scripts/bootstrap_db_users.py`
Expected: exit status 1, and
`DATABASE_URL names 'opendoor'. It needs a login user of its own, such as od_app_login, so that row-level security applies to it. See apps/api/.env.example.`

- [ ] **Step 7: Run it twice**

Run: `cd apps/api && uv run python scripts/bootstrap_db_users.py && uv run python scripts/bootstrap_db_users.py`
Expected:

```
od_app_login: created, with od_app
od_cleanup_login: created, with od_cleanup
od_app_login: password reset, with od_app
od_cleanup_login: password reset, with od_cleanup
```

- [ ] **Step 8: Run the database tests again**

Run: `cd apps/api && uv run pytest tests/integration -q`
Expected: `18 passed`. The bootstrap test drops its awkward user when it finishes.

- [ ] **Step 9: Run the API checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q`
Expected: `All checks passed!`, `42 files already formatted`,
`Success: no issues found in 42 source files`, and `66 passed`.

### Task 7: The tenant context, and the isolation tests

**Files:**
- Create: `apps/api/app/db/tenancy.py`
- Modify: `apps/api/tests/integration/conftest.py` (adds the tenant factory)
- Test: `apps/api/tests/integration/test_isolation.py`,
  `apps/api/tests/integration/test_private_details.py`,
  `apps/api/tests/integration/test_audit_log.py`, `apps/api/tests/integration/test_cleanup.py`

- [ ] **Step 1: Replace `apps/api/tests/integration/conftest.py`,** adding the `make_tenant`
      factory and the session-end cleanup

```python
"""Database fixtures for the integration tests.

One engine per database login. A test that needs a URL that isn't set fails loudly instead of
skipping:

- `app_engine` connects as DATABASE_URL, the API's own login (a member of od_app).
- `owner_engine` connects as MIGRATION_DATABASE_URL, the database owner.
- `cleanup_engine` connects as CLEANUP_DATABASE_URL, the cleanup login (a member of od_cleanup).

`make_tenant` creates a small sandbox company as the API's login, with a row in every table, and
returns a `SampleTenant`. Every tenant it creates is deleted when the test session ends.
"""

import asyncio
import hashlib
import secrets
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

import pytest
from pydantic import PostgresDsn
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.engine import create_engine
from app.db.models import (
    AuditEvent,
    Department,
    Holiday,
    Location,
    Person,
    PersonPrivate,
    Tenant,
    UserSession,
)
from app.db.tenancy import TenantContext, tenant_session


@pytest.fixture(scope="session")
def database_settings() -> Settings:
    # Reads the environment (CI) or apps/api/.env (local development).
    return Settings()


def required_url(url: PostgresDsn | None, variable: str) -> str:
    if url is None:
        pytest.fail(f"{variable} is not set, so this test can't run. See apps/api/.env.example.")
    return str(url)


@pytest.fixture
async def app_engine(database_settings: Settings) -> AsyncIterator[AsyncEngine]:
    """The API's own login: a member of od_app, so row-level security applies to it."""
    engine = create_engine(str(database_settings.database_url))
    yield engine
    await engine.dispose()


@pytest.fixture
async def owner_engine(database_settings: Settings) -> AsyncIterator[AsyncEngine]:
    """The database owner, which runs the migrations."""
    url = required_url(database_settings.migration_database_url, "MIGRATION_DATABASE_URL")
    engine = create_engine(url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def cleanup_engine(database_settings: Settings) -> AsyncIterator[AsyncEngine]:
    """The cleanup login: a member of od_cleanup, which may delete only expired tenants."""
    url = required_url(database_settings.cleanup_database_url, "CLEANUP_DATABASE_URL")
    engine = create_engine(url)
    yield engine
    await engine.dispose()


@dataclass(frozen=True)
class SampleTenant:
    """A tenant with a row in every table: three people, their private details, and the rest."""

    id: UUID
    # An ordinary employee, with a session. They are the actor on the tenant's audit event.
    employee_id: UUID
    # Another employee in the same tenant.
    colleague_id: UUID
    # The HR partner (is_hr_admin), and the other two people's manager.
    hr_id: UUID


class MakeTenant(Protocol):
    async def __call__(self, *, expired: bool = False) -> SampleTenant: ...


@pytest.fixture(scope="session")
def created_tenant_ids(database_settings: Settings) -> Iterator[list[UUID]]:
    """Every tenant the tests create, deleted through the owner when the test session ends.

    The owner is the Compose superuser in development and CI, and a superuser bypasses row-level
    security, so it can delete any tenant. Each tenant's rows go with it (ON DELETE CASCADE).
    """
    tenant_ids: list[UUID] = []
    yield tenant_ids
    if tenant_ids:
        url = required_url(database_settings.migration_database_url, "MIGRATION_DATABASE_URL")
        asyncio.run(delete_tenants(url, tenant_ids))


async def delete_tenants(url: str, tenant_ids: list[UUID]) -> None:
    engine = create_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
    finally:
        await engine.dispose()


def sha256_of_random_token() -> bytes:
    return hashlib.sha256(secrets.token_bytes(32)).digest()


@pytest.fixture
def make_tenant(app_engine: AsyncEngine, created_tenant_ids: list[UUID]) -> MakeTenant:
    """Create a `SampleTenant` as the API's login. Pass `expired=True` for one past its expiry."""

    async def make(*, expired: bool = False) -> SampleTenant:
        tenant_id = uuid4()
        created_tenant_ids.append(tenant_id)
        now = datetime.now(UTC)
        expires_at = now - timedelta(hours=1) if expired else now + timedelta(hours=24)
        location = Location(
            id=uuid4(),
            tenant_id=tenant_id,
            code="DEN",
            name="Denver HQ",
            city="Denver",
            state="CO",
            timezone="America/Denver",
        )
        department = Department(id=uuid4(), tenant_id=tenant_id, name="People")

        def person(given: str, family: str, manager_id: UUID | None, **extra: object) -> Person:
            return Person(
                id=uuid4(),
                tenant_id=tenant_id,
                given_name=given,
                family_name=family,
                title="Associate",
                department_id=department.id,
                location_id=location.id,
                manager_id=manager_id,
                work_email=f"{given.lower()}@opendoor.example",
                employment_type="salaried",
                hire_date=date(2024, 3, 4),
                **extra,
            )

        hr = person("Dana", "Whitfield", None, is_hr_admin=True, persona_key="dana")
        employee = person("Priya", "Shah", hr.id, persona_key="priya")
        colleague = person("Leo", "Marsh", hr.id)
        private_rows = [
            PersonPrivate(
                person_id=someone.id,
                tenant_id=tenant_id,
                personal_email=f"{someone.given_name.lower()}@example.com",
                phone="555-0100",
                home_address="1 Example Street, Denver, CO",
                date_of_birth=date(1990, 1, 1),
            )
            for someone in (hr, employee, colleague)
        ]

        # WITH CHECK accepts only rows of the tenant the transaction is scoped to, so the context
        # names the new tenant before its first row is written.
        async with tenant_session(app_engine, TenantContext(tenant_id, None)) as session:
            # Each flush writes the rows that the next ones refer to.
            session.add(Tenant(id=tenant_id, expires_at=expires_at, anchor_date=now.date()))
            await session.flush()
            session.add_all([location, department])
            await session.flush()
            session.add(hr)
            await session.flush()
            session.add_all([employee, colleague])
            await session.flush()
            session.add_all(private_rows)
            session.add(
                Holiday(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    location_id=location.id,
                    holiday_date=date(now.year, 1, 1),
                    name="New Year's Day",
                )
            )
            session.add(
                UserSession(
                    token_hash=sha256_of_random_token(),
                    csrf_hash=sha256_of_random_token(),
                    tenant_id=tenant_id,
                    person_id=employee.id,
                    expires_at=expires_at,
                )
            )
            session.add(
                AuditEvent(
                    tenant_id=tenant_id,
                    actor_person_id=employee.id,
                    via="system",
                    action="sandbox.created",
                    target_type="tenant",
                    target_id=tenant_id,
                )
            )
        return SampleTenant(tenant_id, employee.id, colleague.id, hr.id)

    return make
```

- [ ] **Step 2: Write the isolation tests** in `apps/api/tests/integration/test_isolation.py`

```python
"""Tenants can't see or write each other's rows, even on a reused database connection."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Table, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.db.models import Department, PersonPrivate
from app.db.tenancy import NO_TENANT, TenantContext, set_is_hr, tenant_session
from tests.integration.conftest import MakeTenant

pytestmark = pytest.mark.integration

TENANTS = Base.metadata.tables["tenants"]
PEOPLE = Base.metadata.tables["people"]
# Every table with a tenant_id except sessions, which row-level security doesn't cover.
TENANT_TABLES = [
    table
    for table in Base.metadata.sorted_tables
    if "tenant_id" in table.c and table.name != "sessions"
]


async def tenants_seen(session: AsyncSession | AsyncConnection, table: Table) -> set[UUID]:
    """The tenants whose rows in `table` are visible."""
    column = table.c.id if table.name == "tenants" else table.c.tenant_id
    return set((await session.execute(select(column).distinct())).scalars())


async def backend_pid(session: AsyncSession | AsyncConnection) -> int:
    pid: int = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
    return pid


@asynccontextmanager
async def one_connection_engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """An engine whose pool holds exactly one connection, so every use reuses it."""
    engine = create_async_engine(str(settings.database_url), pool_size=1, max_overflow=0)
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_a_tenant_sees_its_own_rows_and_none_of_another_tenants(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine = await make_tenant()
    await make_tenant()  # Another tenant, with rows in every table too.

    async with tenant_session(app_engine, TenantContext(mine.id, mine.hr_id)) as session:
        # As HR, so the private-details rule shows every private row in the tenant.
        await set_is_hr(session, True)
        seen = {
            table.name: await tenants_seen(session, table) for table in [TENANTS, *TENANT_TABLES]
        }

    # Seeing its own rows at all proves the od_app policies reach the login through its
    # membership: with row-level security forced and no policy that applies, Postgres shows nothing.
    assert seen == {name: {mine.id} for name in seen}


async def test_with_no_tenant_every_table_is_empty(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    await make_tenant()

    async with tenant_session(app_engine, NO_TENANT) as session:
        seen = {
            table.name: await tenants_seen(session, table) for table in [TENANTS, *TENANT_TABLES]
        }

    assert seen == {name: set() for name in seen}


async def test_a_reused_connection_carries_nothing_from_one_tenant_to_the_next(
    database_settings: Settings, make_tenant: MakeTenant
) -> None:
    first, second = await make_tenant(), await make_tenant()
    async with one_connection_engine(database_settings) as engine:
        async with tenant_session(engine, TenantContext(first.id, first.employee_id)) as session:
            pid = await backend_pid(session)
            assert await tenants_seen(session, PEOPLE) == {first.id}

        # A bare connection, which no hook touches. Postgres now holds '' for app.tenant_id, not
        # NULL, and that must read as "no tenant" instead of raising.
        async with engine.connect() as connection:
            assert await backend_pid(connection) == pid
            leftover = await connection.scalar(
                text("SELECT current_setting('app.tenant_id', true)")
            )
            assert leftover == ""
            assert await tenants_seen(connection, PEOPLE) == set()

        async with tenant_session(engine, NO_TENANT) as session:
            assert await backend_pid(session) == pid
            assert await tenants_seen(session, PEOPLE) == set()

        async with tenant_session(engine, TenantContext(second.id, second.employee_id)) as session:
            assert await backend_pid(session) == pid
            assert await tenants_seen(session, PEOPLE) == {second.id}


async def test_the_hook_overrides_settings_left_behind_on_a_connection(
    database_settings: Settings, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    leave_behind = text(
        "SELECT set_config('app.tenant_id', :tenant_id, false),"
        " set_config('app.person_id', :person_id, false),"
        " set_config('app.is_hr', 'true', false)"
    )

    async with one_connection_engine(database_settings) as engine:
        # set_config(..., false) lasts for the whole connection, past every transaction.
        async with engine.connect() as connection:
            await connection.execute(
                leave_behind,
                {"tenant_id": str(tenant.id), "person_id": str(tenant.employee_id)},
            )
            await connection.commit()

        async with tenant_session(engine, NO_TENANT) as session:
            nothing = await tenants_seen(session, PEOPLE)

        async with tenant_session(engine, TenantContext(tenant.id, tenant.colleague_id)) as session:
            private = set((await session.execute(select(PersonPrivate.person_id))).scalars())

    assert nothing == set()
    # The hook cleared app.is_hr, so the colleague sees only their own private row.
    assert private == {tenant.colleague_id}


async def test_a_tenant_cannot_write_a_row_into_another_tenant(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()

    with pytest.raises(DBAPIError, match="violates row-level security policy"):
        async with tenant_session(app_engine, TenantContext(mine.id, mine.hr_id)) as session:
            session.add(Department(id=uuid4(), tenant_id=theirs.id, name="Smuggled"))
```

- [ ] **Step 3: Write the private-details tests** in
      `apps/api/tests/integration/test_private_details.py`

```python
"""A private-details row is visible only to its own person and to HR, even to a raw query."""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from tests.integration.conftest import MakeTenant

pytestmark = pytest.mark.integration

# Raw SQL, not the policy layer: the database applies the rule on its own.
PRIVATE_ROWS = text("SELECT person_id FROM person_private")
ONE_PRIVATE_ROW = text("SELECT count(*) FROM person_private WHERE person_id = :person_id")


async def private_rows(session: AsyncSession) -> set[UUID]:
    return set((await session.execute(PRIVATE_ROWS)).scalars())


async def test_an_employee_sees_only_their_own_private_row(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()

    context = TenantContext(tenant.id, tenant.employee_id)
    async with tenant_session(app_engine, context) as session:
        visible = await private_rows(session)
        colleagues = await session.scalar(ONE_PRIVATE_ROW, {"person_id": tenant.colleague_id})

    assert visible == {tenant.employee_id}
    assert colleagues == 0


async def test_hr_sees_every_private_row_in_its_own_tenant(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant, other_tenant = await make_tenant(), await make_tenant()

    async with tenant_session(app_engine, TenantContext(tenant.id, tenant.hr_id)) as session:
        await set_is_hr(session, True)
        visible = await private_rows(session)

    assert visible == {tenant.employee_id, tenant.colleague_id, tenant.hr_id}
    assert other_tenant.employee_id not in visible


async def test_the_hr_flag_lasts_only_until_the_transaction_ends(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    context = TenantContext(tenant.id, tenant.hr_id)

    async with AsyncSession(app_engine, info={"tenant": context}) as session:
        async with session.begin():
            await set_is_hr(session, True)
            during = await private_rows(session)
        async with session.begin():
            after = await private_rows(session)

    assert len(during) == 3
    assert after == {tenant.hr_id}
```

- [ ] **Step 4: Write the audit log tests** in `apps/api/tests/integration/test_audit_log.py`

```python
"""The API can add and read audit events, and never change or remove them."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import AuditEvent
from app.db.tenancy import TenantContext, tenant_session
from tests.integration.conftest import MakeTenant

pytestmark = pytest.mark.integration


async def test_the_api_can_read_the_event_it_added(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()

    async with tenant_session(app_engine, TenantContext(tenant.id, tenant.employee_id)) as session:
        actions = list((await session.execute(select(AuditEvent.action))).scalars())

    assert actions == ["sandbox.created"]


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_events SET action = 'edited'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ],
)
async def test_the_api_cannot_change_or_remove_audit_events(
    app_engine: AsyncEngine, make_tenant: MakeTenant, statement: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(DBAPIError, match="permission denied for table audit_events"):
        async with tenant_session(app_engine, TenantContext(tenant.id, tenant.hr_id)) as session:
            await session.execute(text(statement))
```

- [ ] **Step 5: Write the cleanup tests** in `apps/api/tests/integration/test_cleanup.py`

```python
"""The cleanup login deletes expired tenants, and only those. Their rows go with them."""

from uuid import UUID

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base
from app.db.models import Tenant
from app.db.tenancy import TenantContext, tenant_session
from tests.integration.conftest import MakeTenant

pytestmark = pytest.mark.integration

TABLES_WITH_A_TENANT = [table for table in Base.metadata.sorted_tables if "tenant_id" in table.c]


async def rows_left(owner_engine: AsyncEngine, tenant_id: UUID) -> dict[str, int]:
    """Every table's row count for one tenant. The owner sees all rows in development and CI,
    because it is a superuser, and a superuser bypasses row-level security."""
    counts: dict[str, int] = {}
    async with owner_engine.connect() as connection:
        tenants = select(func.count()).where(Tenant.id == tenant_id)
        counts["tenants"] = (await connection.execute(tenants)).scalar_one()
        for table in TABLES_WITH_A_TENANT:
            rows = select(func.count()).select_from(table).where(table.c.tenant_id == tenant_id)
            counts[table.name] = (await connection.execute(rows)).scalar_one()
    return counts


async def delete_tenant(cleanup_engine: AsyncEngine, tenant_id: UUID) -> int:
    async with cleanup_engine.begin() as connection:
        result = await connection.execute(delete(Tenant).where(Tenant.id == tenant_id))
        return result.rowcount


async def test_the_cleanup_login_deletes_an_expired_tenant_with_all_its_rows(
    cleanup_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    expired = await make_tenant(expired=True)
    before = await rows_left(owner_engine, expired.id)

    deleted = await delete_tenant(cleanup_engine, expired.id)

    assert all(count > 0 for count in before.values()), before
    assert deleted == 1
    assert await rows_left(owner_engine, expired.id) == dict.fromkeys(before, 0)


async def test_the_cleanup_login_can_neither_see_nor_delete_a_live_tenant(
    cleanup_engine: AsyncEngine, owner_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    live, expired = await make_tenant(), await make_tenant(expired=True)
    async with cleanup_engine.connect() as connection:
        visible = set(
            await connection.scalars(select(Tenant.id).where(Tenant.id.in_([live.id, expired.id])))
        )

    deleted = await delete_tenant(cleanup_engine, live.id)

    assert visible == {expired.id}
    assert deleted == 0
    assert (await rows_left(owner_engine, live.id))["tenants"] == 1


async def test_the_api_cannot_see_another_tenants_expired_row(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine, expired = await make_tenant(), await make_tenant(expired=True)

    async with tenant_session(app_engine, TenantContext(mine.id, mine.employee_id)) as session:
        visible = set((await session.execute(select(Tenant.id))).scalars())

    # cleanup_select is written TO od_cleanup, so the API's login never inherits it.
    assert visible == {mine.id}
    assert expired.id not in visible
```

- [ ] **Step 6: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/integration -q`
Expected: `ImportError while loading conftest`, ending with
`ModuleNotFoundError: No module named 'app.db.tenancy'`.

- [ ] **Step 7: Create `apps/api/app/db/tenancy.py`**

```python
"""The tenant context that row-level security reads, set at the start of every transaction.

Postgres policies compare each row's tenant_id with app.current_tenant_id(), which reads the
`app.tenant_id` setting. A listener on every ORM session sets that setting and `app.person_id`,
and clears `app.is_hr`, as each transaction begins. It uses set_config(..., true), so the values
end with the transaction and never reach the next user of a pooled connection. A session with no
context gets empty values, which the policies read as "no tenant", so it sees no rows at all.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session, SessionTransaction


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Whose transaction this is. Both come from the server session, never from request input."""

    tenant_id: UUID | None
    person_id: UUID | None


NO_TENANT = TenantContext(tenant_id=None, person_id=None)

SET_CONTEXT = text(
    "SELECT set_config('app.tenant_id', :tenant_id, true),"
    " set_config('app.person_id', :person_id, true),"
    " set_config('app.is_hr', '', true)"
)
SET_IS_HR = text("SELECT set_config('app.is_hr', :is_hr, true)")


def _setting(value: UUID | None) -> str:
    return "" if value is None else str(value)


def apply_tenant_context(
    session: Session, transaction: SessionTransaction, connection: Connection
) -> None:
    """Scope the transaction that just began to the session's tenant, or to no tenant at all."""
    context = session.info.get("tenant")
    if not isinstance(context, TenantContext):
        context = NO_TENANT
    connection.execute(
        SET_CONTEXT,
        {"tenant_id": _setting(context.tenant_id), "person_id": _setting(context.person_id)},
    )


# On the Session class, so it covers every ORM session, including the one inside each
# AsyncSession. A module runs once per process, so the listener is registered once.
event.listen(Session, "after_begin", apply_tenant_context)


@asynccontextmanager
async def tenant_session(
    engine: AsyncEngine, context: TenantContext
) -> AsyncIterator[AsyncSession]:
    """A session in one transaction scoped to `context`. It commits if the block succeeds and
    rolls back if it raises."""
    async with (
        AsyncSession(engine, info={"tenant": context}, expire_on_commit=False) as session,
        session.begin(),
    ):
        yield session


async def set_is_hr(session: AsyncSession, value: bool) -> None:
    """Tell the private-details policy whether the actor is HR, until the transaction ends."""
    await session.execute(SET_IS_HR, {"is_hr": "true" if value else "false"})
```

- [ ] **Step 8: Run the database tests, and confirm they cleaned up after themselves**

Run: `cd apps/api && uv run pytest tests/integration -q`
Expected: `33 passed`.

Run, from the repository root:
`docker compose exec -T db psql -U opendoor -d opendoor -tAc "SELECT count(*) FROM tenants"`
Expected: `0`.

- [ ] **Step 9: Prove the reused-connection tests catch an empty setting, then undo.** This drops
      `NULLIF` from the tenant function. Run the first command from the repository root.

Run: `docker compose exec -T db psql -U opendoor -d opendoor -c "CREATE OR REPLACE FUNCTION app.current_tenant_id() RETURNS uuid LANGUAGE sql STABLE AS \$\$ SELECT current_setting('app.tenant_id', true)::uuid \$\$"`
Then run: `cd apps/api && uv run pytest tests/integration/test_isolation.py -q`
Expected: `3 failed, 2 passed`, with
`asyncpg.exceptions.InvalidTextRepresentationError: invalid input syntax for type uuid: ""`.
Then restore the function from the migrations:
`cd apps/api && uv run alembic downgrade 0001 && uv run alembic upgrade head`. The login users
keep their roles through that, so `uv run pytest tests/integration -q` gives `33 passed` again.

- [ ] **Step 10: Prove the tests depend on the transaction hook, then undo.** In
      `apps/api/app/db/tenancy.py`, comment out the line
      `event.listen(Session, "after_begin", apply_tenant_context)`.

Run: `cd apps/api && uv run pytest tests/integration -q`
Expected: `15 failed, 18 passed`. Without the hook, `make_tenant` can't write its first row.
Restore the line.

- [ ] **Step 11: Run the API checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
Expected: `All checks passed!`, `47 files already formatted`,
`Success: no issues found in 47 source files`, `Domain code imports no framework KEPT`, and
`81 passed`.

### Task 8: The Makefile, and the migration round trip

This closes the Phase 1 backlog item "Test that migrations reverse cleanly", together with Task 9.

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Update `Makefile`.** Recipe lines start with a **tab**.

Replace the `.PHONY` line with:

```make
.PHONY: help setup db db-stop migrate bootstrap-db migrations-roundtrip dev dev-api dev-web openapi check check-api check-web check-docs check-workflows audit
```

In `help`, change `%-16s` to `%-22s`, so `migrations-roundtrip` fits its column.

Replace the `db`, `db-stop`, `migrate`, and `dev` targets with these. `dev` no longer lists
`migrate`, because `make db` now migrates.

```make
db: ## Start the development Postgres, apply migrations, then create the login users
	docker compose up --detach --wait db
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run python scripts/bootstrap_db_users.py

db-stop: ## Stop the development Postgres (its data is kept)
	docker compose stop db

migrate: ## Apply new database migrations
	cd $(API) && uv run alembic upgrade head

bootstrap-db: ## Create or update the login users named in DATABASE_URL and CLEANUP_DATABASE_URL
	cd $(API) && uv run python scripts/bootstrap_db_users.py

# Not part of check-api: it deletes every row, including the sandboxes you're working in.
migrations-roundtrip: ## Undo every migration, apply them again, and recreate the logins (wipes data)
	cd $(API) && uv run alembic downgrade base
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run python scripts/bootstrap_db_users.py

dev: db ## Run `make db`, then the API (:8000) and the web app (:5173) together
	$(MAKE) -j2 dev-api dev-web
```

Replace the `check-api` target with this, which runs the bootstrap after the migrations:

```make
check-api: ## Lint, type-check, migrate, and test the API; confirm the schema is current
	cd $(API) && uv run ruff check .
	cd $(API) && uv run ruff format --check .
	cd $(API) && uv run mypy
	cd $(API) && uv run lint-imports
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run python scripts/bootstrap_db_users.py
	cd $(API) && uv run alembic check
	cd $(API) && uv run pytest
	cd $(API) && uv run python scripts/export_openapi.py --check
```

- [ ] **Step 2: Check the list of commands**

Run: `make help`
Expected:

```
  help                   List the available commands
  setup                  Install dependencies and git hooks; create apps/api/.env if it's missing
  db                     Start the development Postgres, apply migrations, then create the login users
  db-stop                Stop the development Postgres (its data is kept)
  migrate                Apply new database migrations
  bootstrap-db           Create or update the login users named in DATABASE_URL and CLEANUP_DATABASE_URL
  migrations-roundtrip   Undo every migration, apply them again, and recreate the logins (wipes data)
  dev                    Run `make db`, then the API (:8000) and the web app (:5173) together
  dev-api                Run only the API, with auto-reload
  dev-web                Run only the web app
  openapi                Regenerate the OpenAPI schema and the web app's API client
  check                  Run everything CI runs (start Postgres first with `make db`)
  check-api              Lint, type-check, migrate, and test the API; confirm the schema is current
  check-web              Lint, format-check, type-check, test, and build the web app; confirm the client
  audit                  Scan for leaked secrets and vulnerable dependencies (what the Security workflow runs)
  check-docs             Check spelling (American English), links between files, and leftover placeholders
  check-workflows        Check the GitHub Actions workflows for mistakes (actionlint) and security (zizmor)
```

- [ ] **Step 3: Run `make db`**

Run: `make db`
Expected: Compose reports the database running, `alembic upgrade head` has nothing to apply,
and the bootstrap prints `od_app_login: password reset, with od_app` and
`od_cleanup_login: password reset, with od_cleanup`. While planning, `make db` itself wasn't run,
because it starts the Compose database. Its two new commands were.

- [ ] **Step 4: Run the round trip, with the login users already holding their roles**

Run: `make migrations-roundtrip`
Expected, after the `INFO` lines that name the migration context:

```
Running downgrade 0003 -> 0002, Create the Phase 1 tables, with row-level security, their policies, and the roles' grants.
Running downgrade 0002 -> 0001, Create the database roles and the functions row-level security reads the tenant from.
Running downgrade 0001 -> , Enable the pgvector extension, which stores the handbook's embeddings.
Running upgrade  -> 0001, Enable the pgvector extension, which stores the handbook's embeddings.
Running upgrade 0001 -> 0002, Create the database roles and the functions row-level security reads the tenant from.
Running upgrade 0002 -> 0003, Create the Phase 1 tables, with row-level security, their policies, and the roles' grants.
od_app_login: password reset, with od_app
od_cleanup_login: password reset, with od_cleanup
```

- [ ] **Step 5: Run the full API check**

Run: `make check-api`
Expected: every step passes. That means ruff clean, formatting clean,
`Success: no issues found in 47 source files`, the import contract KEPT, the two
`password reset` lines, `No new upgrade operations detected.`, `81 passed`, and
`apps/web/openapi.json is up to date.`

### Task 9: CI runs as the owner, the round trip, then the tests as the API's login

**Files:**
- Modify: `.github/workflows/ci.yml` (the `api` job)

- [ ] **Step 1: In the `api` job, replace the `env:` block** (from `env:` up to `steps:`) **with
      this,** which adds a comment above it

```yaml
    # The same throwaway credentials as apps/api/.env.example. The tests connect as the API's own
    # login, which the bootstrap step creates; migrations and the bootstrap run as the owner.
    env:
      APP_ENV: test
      DATABASE_URL: postgresql+asyncpg://od_app_login:od_app_dev@127.0.0.1:5433/opendoor
      MIGRATION_DATABASE_URL: postgresql+asyncpg://opendoor:opendoor@127.0.0.1:5433/opendoor
      CLEANUP_DATABASE_URL: postgresql+asyncpg://od_cleanup_login:od_cleanup_dev@127.0.0.1:5433/opendoor
      APP_ORIGIN: http://localhost:5173
```

- [ ] **Step 2: In the same job, replace the three steps from `- run: uv run alembic upgrade head`
      through `- run: uv run pytest` with:**

```yaml
      - name: Migrate as the owner
        run: uv run alembic upgrade head
      # The same sequence as `make migrations-roundtrip`, which the bootstrap below completes.
      - name: Every migration reverses cleanly
        run: |
          uv run alembic downgrade base
          uv run alembic upgrade head
      - name: Create the login users
        run: uv run python scripts/bootstrap_db_users.py
      - name: Models and migrations agree
        run: uv run alembic check
      - name: Tests, connected as the API's own login
        run: uv run pytest
```

The actions stay pinned to their commits, and every checkout keeps `persist-credentials: false`.

- [ ] **Step 3: Check the workflows**

Run: `GH_TOKEN=$(gh auth token) make check-workflows`
Expected: actionlint prints nothing, and zizmor ends with
`No findings to report. Good job! (4 suppressed)`.

While planning, CI's sequence also ran on a Postgres server with no Open Door roles at all, with
the settings in environment variables, as in CI. The first upgrade created the roles, the round
trip reused them, the bootstrap created both logins, `alembic check` was clean, and `81 passed`.

### Task 10: Close Stage 1

**Files:**
- Modify: `CHANGELOG.md`, `docs/ROADMAP.md`, `docs/BACKLOG.md`, `CLAUDE.md`

- [ ] **Step 1: Add to `CHANGELOG.md` under `## [Unreleased]` → `### Added`,** after the
      Phase 1 spec entry

```markdown
- **Tenant isolation in the database** (Phase 1, stage 1). Each sandbox company's data now lives
  in tables that Postgres itself keeps apart, with row-level security. The API sees only the rows
  of the company its transaction belongs to, and a transaction with no company sees nothing, even
  on a reused database connection. A second rule shows a person's private details only to that
  person and to HR. Also added:
  - The eight Phase 1 tables: sandbox companies, locations, departments, people, private details,
    holidays, sessions, and an audit log that the API can add to but never change.
  - Separate database logins. The API connects as its own user, which owns nothing and can't
    skip the security rules. Migrations run as the database owner, and a cleanup user can delete
    only expired sandboxes. `make db` now creates the login users after migrating, from the URLs
    in `apps/api/.env`.
  - Tests against the real database for each guarantee: isolation, the exact privileges of each
    role, the private-details rule, the append-only audit log, and cleanup. CI also undoes and
    reapplies every migration (`make migrations-roundtrip` locally), so a migration that can't be
    reversed fails the build.
  - `APP_ORIGIN`, the web app's address, for the same-origin check that stage 3 adds.

  This closes three backlog items: migrations run as a separate role, migrations are tested in
  reverse, and the health check reaches the database engine through a typed accessor that fails
  with a clear message.
```

- [ ] **Step 2: Update the Phase 1 row in `docs/ROADMAP.md`,** using today's date

```markdown
| 1 Tenancy, identity, permissions | In progress: stage 1 of 4 (roles and tenancy) | `feat/phase-1-tenancy` | — | [phase 1 plan](plans/2026-10-03-phase-1-tenancy-identity-permissions.md) | <today> |
```

- [ ] **Step 3: In `docs/BACKLOG.md`, replace the Phase 1 section** with the two items that are
      still open. The typed engine accessor, migrating as a separate role, and the round trip
      are done.

```markdown
## Phase 1: tenancy, identity, permissions

- **Exempt `/api/v1/health` from authentication and CSRF.**
- **Don't run Alembic inside an async test.** `env.py` calls `asyncio.run`, which fails inside a
  running event loop, and `fileConfig` resets the root log handlers. Test setup should run
  `alembic upgrade head` as a subprocess, or from a synchronous session fixture.
```

- [ ] **Step 4: Update `CLAUDE.md`.** In the Commands block, replace the `make db` line with:

```
make db         start Postgres (127.0.0.1:5433), migrate, then create the login users
```

Then add this after the paragraph that starts "Run a single API test":

```markdown
**The database has three URLs**, all in `apps/api/.env` (see `.env.example`):

- `DATABASE_URL` is the API's own login, `od_app_login`. It owns nothing, row-level security
  applies to it, and the tests connect as it.
- `MIGRATION_DATABASE_URL` is the database owner. Alembic and the bootstrap script connect as it.
- `CLEANUP_DATABASE_URL` is the cleanup login, `od_cleanup_login`, which can delete only expired
  sandboxes.

`make db` does three things in order: it starts Postgres, applies the migrations, and runs
`apps/api/scripts/bootstrap_db_users.py`, which creates the login users from those URLs.
`make migrate` applies new migrations on their own, and `make bootstrap-db` reruns the script
after a password changes. `make migrations-roundtrip` undoes and reapplies every migration, which
wipes the data.
```

- [ ] **Step 5: Run `make check` (with `make db` first)**

Run: `make db && make check`
Expected: every check passes. `check-api` ends with `81 passed` and the schema up to date,
`check-web` passes unchanged, `check-docs` reports `0 Errors` with no placeholders printed, and
zizmor reports `No findings to report`. While planning, `make check-docs` passed with these four
documents edited.

- [ ] **Step 6: Run `/code-review medium` on the whole branch against `dev`,** committed and
      uncommitted work together, and fix anything real it finds. Re-run `make check` after any
      fix.

- [ ] **Step 7: Propose the commit and PR, and wait for the owner's OK.** Commit message:

```
Keep each sandbox company's data apart inside the database

Each sandbox company's data now lives in tables that Postgres itself
keeps apart, with row-level security (RLS): the database shows a
connection only the rows of the company its transaction belongs to,
and a transaction with no company sees nothing, even on a reused
connection. A second rule shows a person's private details only to
that person and to HR.

The API now connects as its own database user, which owns nothing and
can't skip those rules. Migrations run as the database owner, and a
separate cleanup user can delete only expired sandboxes. `make db`
creates the login users after migrating, from the URLs in .env.

Tests against the real database prove each guarantee, and CI now
undoes and reapplies every migration, so a downgrade that breaks fails
the build. This is stage 1 of 4 for Phase 1. The seed company comes
next, then sessions and the API endpoints.
```

- [ ] **Step 8: With the owner's OK, push and open the PR into `dev`.** Title: "Keep each sandbox
      company's data apart inside the database". Body:

```markdown
## What this does
Moves tenant isolation into the database. Every sandbox company's rows sit in tables that Postgres
protects with row-level security, so the API sees only the company its transaction belongs to,
and a transaction with no company sees nothing. Private details get a second rule: only the
person themselves and HR can read them. The API now logs in as its own database user, which owns
nothing and can't skip these rules. Migrations run as the owner, a cleanup user can delete only
expired sandboxes, and `make db` creates the login users after migrating.

## Why
"The model never decides who can see what" is the first rule the assistant can't break.
Enforcing tenant isolation in Postgres means that a bug in a query, or later in an assistant
tool, still can't reach another company's data. This is stage 1 of 4 of the Phase 1 plan.

## How it was checked
`make check-api` passes with 81 tests, 33 of them against the real database. They cover
isolation (on a reused connection too), row-level security on every tenant table, the exact
privileges of each role, the private-details rule, the append-only audit log, and cleanup. Each
guarantee test was shown to fail when its rule was taken away. CI now also undoes and reapplies
every migration before the tests run.

## What to look at
- The policies and grants at the end of migration 0003, and the roles that migration 0002's
  downgrade deliberately leaves in place.
- The transaction hook in `app/db/tenancy.py`, and the reused-connection test that guards it.
- Before `make db`, your `apps/api/.env` needs the new URLs, and `DATABASE_URL` must name
  `od_app_login`. `.env.example` has them all.
```

- [ ] **Step 9: Confirm the pull request's checks are green**

Run: `gh pr checks <stage 1 PR number> --repo musicteachj/open-door --watch`
Expected: CI (Detect what changed, API, Docs, Workflows), Security, and Changelog all pass. The
API job shows the new steps: "Migrate as the owner", "Every migration reverses cleanly", "Create
the login users", and "Tests, connected as the API's own login".

---

# Stage 2: The seed company

**Branch:** `feat/phase-1-seed`, off `dev` after Stage 1 merges.
**Ends with:** every sandbox can be filled with the same fictional company: 120 people in eight
departments across three locations, with the four personas and Leo where the demo expects them.
The company holiday calendar is pure domain code, so the Phase 5 time-off engine can reuse it.
`build_company` builds the company in memory, and `insert_company` writes it under row-level
security, one statement per table. While planning, that took about 15 milliseconds.
`make check-api` passes with 112 tests, 36 of them against the real database.

> **Before you start:** run `make db`. The new database tests seed real sandboxes as the API's
> login, so they need Stage 1's migrations and login users.

## Decisions made while planning this stage

Every code block below is the exact final content of a file that was run in a scratch clone on
2026-10-03, and every "Expected" is the output it produced. Where a task changes part of a file,
the block is the exact text of that part. That ran against Postgres 17.11 (the pgvector image)
with Python 3.13.15, SQLAlchemy 2.1.1, and asyncpg 0.31.0. The scratch database listened on port
5434, and the commands here use 5433, the development port.

- **A year's holiday calendar is the days the company is closed in that calendar year.** New
  Year's Day 2028 falls on a Saturday, so the company closes on Friday 2027-12-31. That date
  belongs to 2027's calendar, and 2028's calendar has no New Year's Day.
  - A sandbox stores two calendar years: its anchor year and the next. Filed under 2028, the
    closed Friday would be missing from a sandbox anchored in 2026, and a day off on
    2027-12-31 would be counted as a working day.
  - Filed this way, a stored calendar never misses a closed day and never lists one outside its
    year.
- **A moved holiday says so in its name.** For example, "Independence Day (observed)" falls on
  Friday 2026-07-03, so the assistant can explain why the office is closed on the 3rd.
- **The holiday rules know the three location codes, and an unknown code is an error.** Without
  that, a typo would quietly return a calendar without Denver's extra day.
- **Dana is the only HR administrator, and the only person in Human Resources.** The spec names
  her as the HR partner and nobody else. A second `is_hr_admin` would widen who can read every
  private detail. One HR partner for 120 people is also realistic.
- **Marcus is the Oakland store manager**, as the Phase 1 spec now says, matching the design brief
  and the initial plan. He reports to the COO at Denver HQ, who also runs the warehouse.
  - **His direct reports** are Priya, Leo, and three department leads: Apparel, Home, and Front
    End.
  - **The leads manage the store's other 39 associates.** So Marcus has 5 direct reports and 44 in
    all, and Stage 3's recursive query for "reports, direct and indirect" has two levels to walk.
  - **Priya and Leo manage no one.** A test asserts it, so the employee persona never gains a
    manager's view of anyone, and Task 12 shows that test failing when Priya is given reports.
- **The org chart has eight departments, each at one location.**
  - **Denver HQ (40 people):** Executive, Human Resources, Finance, Information Technology,
    Merchandising, and Marketing.
  - **The Oakland store (45):** Store Operations. Marcus, Priya, Leo, three leads, and 39
    associates: sales associates, cashiers, and customer service.
  - **The Austin warehouse (35):** Distribution. Mateo works on the day shift.

  The Denver department heads report to the CEO, and the store and warehouse managers to the
  COO.
- **The named people's dates are fixed, and everyone else's are drawn from the seed.** Priya, for
  example, was always hired 1,160 days before the anchor date. A Phase 5 answer that depends on
  tenure then stays the same when the org chart changes.
- **Every first name is different.** There are 120 given names and 120 family names, with no
  repeats, so "Leo" always means exactly one person. That matters for demo questions like
  "What's Leo's home address?".
- **Every random choice goes through `random.random()`.** Python guarantees that method's
  sequence across versions for the same seed, but not the sequences of `choice()` or `shuffle()`.
  So `_Draws` builds its own pick and shuffle on top of `random()`, and a Python upgrade can't
  quietly change the company.
  > Source: the Python 3.13 documentation for `random`, "Notes on Reproducibility", read from
  > docs.python.org on 2026-10-03.
- **The private details are fictional by construction.**
  - Work emails use `opendoor.example`, like Stage 1's sample tenant. The spec gives the company
    no name.
  - Personal emails use `example.com`. RFC 2606 reserves both domains, so no message can reach
    anyone.
  - Phone numbers use the area code of each person's city, with 555-0100 to 555-0199.
  - Street addresses are made up, with real ZIP codes for each city.
- **The insert statements are built from the models, not written as SQL.** SQLAlchemy renders
  `INSERT INTO people (...) SELECT seed.id, ... FROM unnest($1::UUID[], ...) AS seed(id, ...)`,
  and the asyncpg dialect adds each array's type cast itself. So no SQL string is assembled by
  hand, and a unit test checks that each row type's fields are exactly its table's columns.
- **The tests create the tenant row themselves,** in the same transaction as the seed, as Stage
  3's sandbox creation will. A small `create_sandbox` helper in the test module does it. It
  registers each tenant with Stage 1's `created_tenant_ids`, so the session-end cleanup deletes
  it. `make_tenant` stays as it is.
- **The timing test reports the nearest-rank 95th percentile,** the 19th fastest of 20. While
  planning, four runs gave a p50 of 12 to 13 ms and a p95 of 14 to 20 ms, against the 2-second
  budget.
- **Each guarantee was shown to catch a break.**
  - A framework import in the holiday rules breaks the import contract (Task 11).
  - Giving Priya reports fails the test that she and Leo manage no one (Task 12).
  - A global unique index on `people.work_email` makes the coexistence test fail with
    `UniqueViolationError` (Task 13).
- **Stage 2 is about 1,000 lines:** 570 of code, 437 of tests, and 19 in the changelog and the
  roadmap.

### Task 11: The company holiday calendar

**Files:**
- Create: `apps/api/app/domain/holidays.py`
- Test: `apps/api/tests/test_holidays.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_holidays.py`. Every expected
      date was worked out by hand from a calendar, never by running the code.

```python
"""The company holiday calendar. Every expected date was worked out by hand from a calendar."""

from datetime import date

import pytest

from app.domain.holidays import CompanyHoliday, holidays_for

# 2026: January 1 is a Thursday, and July 4 a Saturday, so it is observed on Friday July 3. May 31
# is a Sunday, so Memorial Day, the last Monday in May, is May 25. September 1 is a Tuesday, so
# Labor Day is September 7. November 1 is a Sunday, so the fourth Thursday is November 26.
# Christmas is a Friday.
OAKLAND_AND_AUSTIN_2026 = [
    CompanyHoliday(date(2026, 1, 1), "New Year's Day"),
    CompanyHoliday(date(2026, 5, 25), "Memorial Day"),
    CompanyHoliday(date(2026, 7, 3), "Independence Day (observed)"),
    CompanyHoliday(date(2026, 9, 7), "Labor Day"),
    CompanyHoliday(date(2026, 11, 26), "Thanksgiving"),
    CompanyHoliday(date(2026, 12, 25), "Christmas Day"),
]

DENVER_2026 = [
    CompanyHoliday(date(2026, 1, 1), "New Year's Day"),
    CompanyHoliday(date(2026, 5, 25), "Memorial Day"),
    CompanyHoliday(date(2026, 7, 3), "Independence Day (observed)"),
    CompanyHoliday(date(2026, 9, 7), "Labor Day"),
    CompanyHoliday(date(2026, 11, 26), "Thanksgiving"),
    CompanyHoliday(date(2026, 11, 27), "Day after Thanksgiving"),
    CompanyHoliday(date(2026, 12, 25), "Christmas Day"),
]

# 2027: July 4 is a Sunday, so it is observed on Monday July 5. Christmas is a Saturday, so it is
# observed on Friday December 24. January 1, 2028 is a Saturday, so New Year's Day 2028 is
# observed on Friday December 31, 2027.
DENVER_2027 = [
    CompanyHoliday(date(2027, 1, 1), "New Year's Day"),
    CompanyHoliday(date(2027, 5, 31), "Memorial Day"),
    CompanyHoliday(date(2027, 7, 5), "Independence Day (observed)"),
    CompanyHoliday(date(2027, 9, 6), "Labor Day"),
    CompanyHoliday(date(2027, 11, 25), "Thanksgiving"),
    CompanyHoliday(date(2027, 11, 26), "Day after Thanksgiving"),
    CompanyHoliday(date(2027, 12, 24), "Christmas Day (observed)"),
    CompanyHoliday(date(2027, 12, 31), "New Year's Day (observed)"),
]

# 2028, a leap year: its New Year's Day was observed in 2027, so it has none. July 4 is a Tuesday
# and Christmas a Monday, so neither moves.
DENVER_2028 = [
    CompanyHoliday(date(2028, 5, 29), "Memorial Day"),
    CompanyHoliday(date(2028, 7, 4), "Independence Day"),
    CompanyHoliday(date(2028, 9, 4), "Labor Day"),
    CompanyHoliday(date(2028, 11, 23), "Thanksgiving"),
    CompanyHoliday(date(2028, 11, 24), "Day after Thanksgiving"),
    CompanyHoliday(date(2028, 12, 25), "Christmas Day"),
]


def test_denver_closes_seven_days_in_2026() -> None:
    assert list(holidays_for("den", 2026)) == DENVER_2026


@pytest.mark.parametrize("location_code", ["oak", "aus"])
def test_oakland_and_austin_close_six_days_in_2026(location_code: str) -> None:
    # Everything Denver closes except the day after Thanksgiving.
    assert list(holidays_for(location_code, 2026)) == OAKLAND_AND_AUSTIN_2026


def test_sunday_and_saturday_holidays_move_to_the_nearest_weekday_in_2027() -> None:
    assert list(holidays_for("den", 2027)) == DENVER_2027


def test_2028_has_no_new_years_day_because_2027_observed_it() -> None:
    assert list(holidays_for("den", 2028)) == DENVER_2028


@pytest.mark.parametrize("location_code", ["den", "oak", "aus"])
def test_an_observed_date_belongs_to_the_year_it_falls_in(location_code: str) -> None:
    in_2027 = holidays_for(location_code, 2027)
    in_2028 = holidays_for(location_code, 2028)

    assert in_2027[-1] == CompanyHoliday(date(2027, 12, 31), "New Year's Day (observed)")
    assert [holiday.name for holiday in in_2028 if "New Year" in holiday.name] == []


def test_an_unknown_location_is_an_error_not_an_empty_calendar() -> None:
    with pytest.raises(ValueError, match="Unknown location code 'nyc'"):
        holidays_for("nyc", 2026)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_holidays.py -q`
Expected: a collection error, `ModuleNotFoundError: No module named 'app.domain.holidays'`.

- [ ] **Step 3: Create `apps/api/app/domain/holidays.py`**

```python
"""The company holiday calendar: the days each location is closed, year by year.

Pure, like everything under app.domain: no framework imports, so the time-off engine can rely on
the same rules in Phase 5. The seed generator stores these dates in each sandbox's holidays table.

Every location closes on six holidays. One that falls on a Saturday is observed on the Friday
before, and one on a Sunday on the Monday after. Denver HQ also closes the day after Thanksgiving.

A year's calendar is the days the company is closed in that calendar year. When New Year's Day
falls on a Saturday, as on 2028-01-01, the company closes on Friday 2027-12-31, so that date is in
2027's calendar and 2028's has no New Year's Day. A stored calendar then never misses a closed
day, and never lists one outside its year.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

LOCATION_CODES = frozenset({"den", "oak", "aus"})
# The one difference between locations, so the time-off engine has a real one to get right.
CLOSED_THE_DAY_AFTER_THANKSGIVING = frozenset({"den"})


@dataclass(frozen=True, slots=True)
class CompanyHoliday:
    """A day the company is closed. `holiday_date` is the observed date, not the actual one."""

    holiday_date: date
    name: str


def holidays_for(location_code: str, year: int) -> tuple[CompanyHoliday, ...]:
    """The days the location is closed in `year`, in date order."""
    if location_code not in LOCATION_CODES:
        msg = f"Unknown location code {location_code!r}: expected one of {sorted(LOCATION_CODES)}"
        raise ValueError(msg)
    thanksgiving = _nth_weekday(year, 11, calendar.THURSDAY, 4)
    holidays = [
        _observed("New Year's Day", date(year, 1, 1)),
        _observed("Memorial Day", _last_weekday(year, 5, calendar.MONDAY)),
        _observed("Independence Day", date(year, 7, 4)),
        _observed("Labor Day", _nth_weekday(year, 9, calendar.MONDAY, 1)),
        _observed("Thanksgiving", thanksgiving),
        _observed("Christmas Day", date(year, 12, 25)),
        # Next year's New Year's Day is observed this year when it falls on a Saturday.
        _observed("New Year's Day", date(year + 1, 1, 1)),
    ]
    if location_code in CLOSED_THE_DAY_AFTER_THANKSGIVING:
        holidays.append(CompanyHoliday(thanksgiving + timedelta(days=1), "Day after Thanksgiving"))
    in_year = (holiday for holiday in holidays if holiday.holiday_date.year == year)
    return tuple(sorted(in_year, key=lambda holiday: holiday.holiday_date))


def _observed(name: str, actual: date) -> CompanyHoliday:
    """A Saturday holiday moves to the Friday before, and a Sunday one to the Monday after."""
    if actual.weekday() == calendar.SATURDAY:
        return CompanyHoliday(actual - timedelta(days=1), f"{name} (observed)")
    if actual.weekday() == calendar.SUNDAY:
        return CompanyHoliday(actual + timedelta(days=1), f"{name} (observed)")
    return CompanyHoliday(actual, name)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The nth Monday, Tuesday, and so on of a month: Labor Day is the first Monday."""
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """The last Monday, Tuesday, and so on of a month: Memorial Day is the last Monday."""
    last = date(year, month, calendar.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)
```

The `calendar` module is the standard library's, so the rules stay free of any framework.

- [ ] **Step 4: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/test_holidays.py -q`
Expected: `9 passed`.

- [ ] **Step 5: Prove that import-linter's existing contract covers the new module, then undo.**
      In `apps/api/app/domain/holidays.py`, add the line `import sqlalchemy  # noqa: F401`
      directly below `import calendar`.

Run: `cd apps/api && uv run lint-imports`
Expected: exit status 1, with `Domain code imports no framework BROKEN`,
`app.domain.holidays -> sqlalchemy (l.16)`, and `Contracts: 0 kept, 1 broken.`
Remove the line.

- [ ] **Step 6: Run the API checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
Expected: `All checks passed!`, `49 files already formatted`,
`Success: no issues found in 49 source files`, `Domain code imports no framework KEPT`, and
`90 passed`.

### Task 12: The seed company, built in memory

**Files:**
- Create: `apps/api/app/modules/__init__.py`, `apps/api/app/modules/sandbox/__init__.py`,
  `apps/api/app/modules/sandbox/seed_data.py`, `apps/api/app/modules/sandbox/seed.py`
- Test: `apps/api/tests/test_seed.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_seed.py`

```python
"""The seed company, built in memory: the same fictional company in every sandbox."""

import re
from collections import Counter
from dataclasses import fields
from datetime import date, timedelta
from uuid import UUID

import pytest

# Importing the models puts every table on Base.metadata.
from app.db import models  # noqa: F401
from app.db.base import Base
from app.domain.holidays import holidays_for
from app.modules.sandbox.seed import ROW_TYPES, PersonRow, Row, SeedCompany, build_company

TENANT_ID = UUID("0b6f3f9e-5d0c-4c1e-9a43-6b1f0d3c2a71")
OTHER_TENANT_ID = UUID("d2a4c6e8-1f3b-4d5a-8c7e-9b0a1c2d3e4f")
ANCHOR = date(2026, 10, 5)

# Phones in 555-0100 to 555-0199 are reserved for fiction, so none of them can ring a real person.
FICTIONAL_PHONE = re.compile(r"[0-9]{3}-555-01[0-9]{2}")
WORK_EMAIL = re.compile(r"[a-z]+\.[a-z]+@opendoor\.example")


@pytest.fixture(scope="module")
def company() -> SeedCompany:
    return build_company(TENANT_ID, ANCHOR)


def full_name(person: PersonRow) -> str:
    return f"{person.given_name} {person.family_name}"


def named(company: SeedCompany, name: str) -> PersonRow:
    return next(person for person in company.people if full_name(person) == name)


def location_code(company: SeedCompany, person: PersonRow) -> str:
    return next(row.code for row in company.locations if row.id == person.location_id)


def reports_of(company: SeedCompany, manager: PersonRow) -> set[str]:
    return {full_name(person) for person in company.people if person.manager_id == manager.id}


def all_reports_of(company: SeedCompany, manager: PersonRow) -> set[str]:
    """Direct and indirect reports, as the recursive query on manager_id will find them."""
    found: set[UUID] = set()
    level = {manager.id}
    while level:
        level = {person.id for person in company.people if person.manager_id in level} - found
        found |= level
    return {full_name(person) for person in company.people if person.id in found}


def years_between(earlier: date, later: date) -> int:
    return later.year - earlier.year - ((later.month, later.day) < (earlier.month, earlier.day))


def all_ids(company: SeedCompany) -> set[UUID]:
    return (
        {row.id for row in company.locations}
        | {row.id for row in company.departments}
        | {row.id for row in company.people}
        | {row.id for row in company.holidays}
    )


def test_the_same_tenant_and_anchor_date_build_an_equal_company(company: SeedCompany) -> None:
    assert build_company(TENANT_ID, ANCHOR) == company


def test_another_tenant_gets_the_same_people_under_new_ids(company: SeedCompany) -> None:
    other = build_company(OTHER_TENANT_ID, ANCHOR)

    def directory(seeded: SeedCompany) -> list[tuple[str, str, str]]:
        return [(full_name(person), person.title, person.work_email) for person in seeded.people]

    assert directory(other) == directory(company)
    assert all_ids(other).isdisjoint(all_ids(company))
    assert {person.tenant_id for person in other.people} == {OTHER_TENANT_ID}


def test_120_people_40_in_denver_45_in_oakland_and_35_in_austin(company: SeedCompany) -> None:
    head_count = Counter(location_code(company, person) for person in company.people)

    assert head_count == {"den": 40, "oak": 45, "aus": 35}
    assert len(company.person_private) == 120


def test_eight_departments_and_three_locations_each_with_people(company: SeedCompany) -> None:
    assert len(company.departments) == 8
    assert {row.id for row in company.departments} == {p.department_id for p in company.people}
    assert [(row.code, row.state, row.timezone) for row in company.locations] == [
        ("den", "CO", "America/Denver"),
        ("oak", "CA", "America/Los_Angeles"),
        ("aus", "TX", "America/Chicago"),
    ]


def test_the_four_personas(company: SeedCompany) -> None:
    personas = {person.persona_key: person for person in company.people if person.persona_key}
    priya, mateo, marcus, dana = (personas[key] for key in ("priya", "mateo", "marcus", "dana"))

    assert set(personas) == {"priya", "mateo", "marcus", "dana"}
    assert (full_name(priya), location_code(company, priya)) == ("Priya Raman", "oak")
    assert (priya.employment_type, priya.manager_id) == ("salaried", marcus.id)
    assert (full_name(mateo), location_code(company, mateo)) == ("Mateo Alvarez", "aus")
    assert mateo.employment_type == "hourly"
    assert (full_name(marcus), location_code(company, marcus)) == ("Marcus Bell", "oak")
    assert (full_name(dana), location_code(company, dana)) == ("Dana Whitfield", "den")
    assert (dana.title, dana.is_hr_admin) == ("HR Business Partner", True)


def test_marcus_runs_the_oakland_store_directly_and_through_three_leads(
    company: SeedCompany,
) -> None:
    marcus = named(company, "Marcus Bell")
    his_manager = next(person for person in company.people if person.id == marcus.manager_id)
    direct = reports_of(company, marcus)
    leads = direct - {"Priya Raman", "Leo Nakamura"}
    oakland = {full_name(p) for p in company.people if location_code(company, p) == "oak"}

    assert marcus.title == "Store Manager"
    assert (his_manager.title, location_code(company, his_manager)) == (
        "Chief Operating Officer",
        "den",
    )
    assert {"Priya Raman", "Leo Nakamura"} < direct
    assert len(leads) == 3
    assert all(reports_of(company, named(company, lead)) for lead in leads)
    # Everyone else at the store reports to him, directly or through a lead.
    assert all_reports_of(company, marcus) == oakland - {"Marcus Bell"}
    assert (len(direct), len(all_reports_of(company, marcus))) == (5, 44)


def test_priya_and_leo_manage_no_one(company: SeedCompany) -> None:
    # The employee persona must never gain a manager's view of anyone.
    priya, leo = named(company, "Priya Raman"), named(company, "Leo Nakamura")

    assert reports_of(company, priya) == set()
    assert reports_of(company, leo) == set()
    assert (location_code(company, leo), leo.employment_type, leo.persona_key) == (
        "oak",
        "hourly",
        None,
    )


def test_dana_is_the_only_hr_admin(company: SeedCompany) -> None:
    hr_admins = [full_name(person) for person in company.people if person.is_hr_admin]

    assert hr_admins == ["Dana Whitfield"]


def test_everyone_but_the_ceo_reports_to_someone_in_the_company(company: SeedCompany) -> None:
    ids = {person.id for person in company.people}
    without_a_manager = [person.title for person in company.people if person.manager_id is None]

    assert without_a_manager == ["Chief Executive Officer"]
    assert {p.manager_id for p in company.people if p.manager_id is not None} <= ids


def test_every_reporting_line_reaches_the_ceo_without_a_cycle(company: SeedCompany) -> None:
    manager_of = {person.id: person.manager_id for person in company.people}

    for person in company.people:
        chain = [person.id]
        while (manager_id := manager_of[chain[-1]]) is not None:
            assert manager_id not in chain, f"{full_name(person)}'s reporting line loops"
            chain.append(manager_id)


def test_names_and_work_emails_are_unique(company: SeedCompany) -> None:
    given_names = [person.given_name for person in company.people]
    work_emails = [person.work_email for person in company.people]

    # Every first name is different, so "Leo" or "Priya" always means exactly one person.
    assert len(set(given_names)) == len(given_names)
    assert len(set(work_emails)) == len(work_emails)
    assert all(WORK_EMAIL.fullmatch(email) for email in work_emails)


def test_private_details_are_obviously_fictional(company: SeedCompany) -> None:
    people = {person.id: person for person in company.people}
    places = {row.id: f", {row.city}, {row.state} " for row in company.locations}

    assert {row.person_id for row in company.person_private} == set(people)
    for row in company.person_private:
        person = people[row.person_id]
        assert row.personal_email.endswith("@example.com")
        assert FICTIONAL_PHONE.fullmatch(row.phone)
        assert places[person.location_id] in row.home_address
        assert 21 <= years_between(row.date_of_birth, ANCHOR) <= 65
        assert years_between(row.date_of_birth, person.hire_date) >= 18
        assert person.hire_date < ANCHOR


def test_every_date_moves_with_the_anchor_date(company: SeedCompany) -> None:
    later = build_company(TENANT_ID, ANCHOR + timedelta(days=100))
    hundred_days = timedelta(days=100)

    for before, after in zip(company.people, later.people, strict=True):
        assert after.hire_date - before.hire_date == hundred_days
    for before_private, after_private in zip(
        company.person_private, later.person_private, strict=True
    ):
        assert after_private.date_of_birth - before_private.date_of_birth == hundred_days


def test_holidays_are_the_company_calendar_for_the_anchor_year_and_the_next(
    company: SeedCompany,
) -> None:
    for location in company.locations:
        seeded = {
            (row.holiday_date, row.name)
            for row in company.holidays
            if row.location_id == location.id
        }
        expected = {
            (holiday.holiday_date, holiday.name)
            for year in (2026, 2027)
            for holiday in holidays_for(location.code, year)
        }
        assert seeded == expected
    # Denver closes 7 days in 2026 and 8 in 2027; Oakland and Austin close 6 and 7.
    assert len(company.holidays) == 15 + 13 + 13


@pytest.mark.parametrize(("table_name", "row_type"), ROW_TYPES.items())
def test_each_row_type_has_exactly_its_tables_columns(table_name: str, row_type: type[Row]) -> None:
    # insert_company writes each field to the column of the same name.
    columns = set(Base.metadata.tables[table_name].columns.keys())

    assert {field.name for field in fields(row_type)} == columns
```

The last test is what lets `insert_company` (Task 13) write each field to the column of the
same name. It needs the models imported, so it imports `app.db.models` the way Stage 1's
`migrations/env.py` does.

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_seed.py -q`
Expected: a collection error, `ModuleNotFoundError: No module named 'app.modules'`.

- [ ] **Step 3: Create the two package files.** `apps/api/app/modules/__init__.py`:

```python
"""One package per area of the product. Sandboxes come first; people, the handbook, time off,
cases, and the audit log follow as their phases arrive."""
```

And `apps/api/app/modules/sandbox/__init__.py`:

```python
"""Sandbox companies: the fictional company every visitor gets, and creating one."""
```

- [ ] **Step 4: Create `apps/api/app/modules/sandbox/seed_data.py`,** the company's fixed data

```python
"""The seed company's fixed data: its locations, departments, org chart, and name lists.

The company is fictional, and so is everything about its people. Personal emails use example.com,
phone numbers use 555-0100 to 555-0199, which are reserved for fiction, and street addresses are
made up. seed.py turns this data into rows.
"""

from dataclasses import dataclass

# Every other choice (who gets which name, phone number, and address, and the dates of everyone
# not named below) comes from this seed, so every sandbox gets exactly the same company.
SEED = 20261003

# .example and example.com are reserved for documentation (RFC 2606), so no message sent to these
# addresses can reach anyone.
WORK_EMAIL_DOMAIN = "opendoor.example"
PERSONAL_EMAIL_DOMAIN = "example.com"


@dataclass(frozen=True, slots=True)
class LocationSpec:
    code: str
    name: str
    city: str
    state: str
    timezone: str
    # For the fictional phone numbers and addresses of the people who work there.
    area_code: str
    zip_codes: tuple[str, ...]


LOCATIONS = (
    LocationSpec("den", "Denver HQ", "Denver", "CO", "America/Denver", "303", ("80203", "80211")),
    LocationSpec(
        "oak", "Oakland store", "Oakland", "CA", "America/Los_Angeles", "510", ("94606", "94610")
    ),
    LocationSpec(
        "aus", "Austin warehouse", "Austin", "TX", "America/Chicago", "512", ("78702", "78745")
    ),
)


@dataclass(frozen=True, slots=True)
class PersonSpec:
    """Who fills a seat: a name, and dates counted back from the sandbox's anchor date.

    The people the demo and the evals talk about are written out below, with fixed dates, so an
    answer that depends on tenure never changes. Everyone else is drawn from the seed.
    """

    given_name: str
    family_name: str
    hired_days_ago: int
    born_days_ago: int
    persona_key: str | None = None
    is_hr_admin: bool = False


@dataclass(frozen=True, slots=True)
class Position:
    """A seat in the org chart, or `seats` identical seats under the same manager.

    `key` is stable: the person's ID is made from it, and naming it as another position's
    `manager` makes the reporting line. The people in a position with several seats get the keys
    `key-1`, `key-2`, and so on, so such a position can't be anyone's manager. A position without
    a `person` gets someone drawn from the seed.
    """

    key: str
    title: str
    manager: str | None
    employment_type: str = "salaried"
    seats: int = 1
    person: PersonSpec | None = None


DANA = PersonSpec("Dana", "Whitfield", 1650, 15200, persona_key="dana", is_hr_admin=True)
MARCUS = PersonSpec("Marcus", "Bell", 2400, 16000, persona_key="marcus")
PRIYA = PersonSpec("Priya", "Raman", 1160, 11400, persona_key="priya")
LEO = PersonSpec("Leo", "Nakamura", 700, 9600)
MATEO = PersonSpec("Mateo", "Alvarez", 520, 10300, persona_key="mateo")

HOURLY = "hourly"

# Each department works at one location here. Denver HQ has 40 people, the Oakland store 45, and
# the Austin warehouse 35. Managers come before their reports.
ORG: dict[tuple[str, str], tuple[Position, ...]] = {
    ("Executive", "den"): (
        Position("ceo", "Chief Executive Officer", None),
        Position("coo", "Chief Operating Officer", "ceo"),
        Position("executive-assistant", "Executive Assistant", "ceo"),
    ),
    ("Human Resources", "den"): (Position("dana", "HR Business Partner", "ceo", person=DANA),),
    ("Finance", "den"): (
        Position("cfo", "Chief Financial Officer", "ceo"),
        Position("controller", "Controller", "cfo"),
        Position("accountant", "Accountant", "controller", seats=3),
        Position("payroll", "Payroll Specialist", "controller"),
        Position("payables", "Accounts Payable Specialist", "controller"),
        Position("financial-analyst", "Financial Analyst", "cfo", seats=2),
    ),
    ("Information Technology", "den"): (
        Position("it-director", "Director of IT", "ceo"),
        Position("sysadmin", "Systems Administrator", "it-director", seats=2),
        Position("engineer", "Software Engineer", "it-director", seats=3),
        Position("it-support", "IT Support Specialist", "it-director", seats=2),
        Position("data-analyst", "Data Analyst", "it-director"),
    ),
    ("Merchandising", "den"): (
        Position("merchandising-vp", "VP of Merchandising", "ceo"),
        Position("senior-buyer", "Senior Buyer", "merchandising-vp"),
        Position("buyer", "Buyer", "merchandising-vp", seats=3),
        Position("assistant-buyer", "Assistant Buyer", "senior-buyer", seats=2),
        Position("planner", "Merchandise Planner", "merchandising-vp"),
        Position("allocation", "Allocation Analyst", "merchandising-vp"),
    ),
    ("Marketing", "den"): (
        Position("marketing-director", "Director of Marketing", "ceo"),
        Position("marketing-manager", "Marketing Manager", "marketing-director"),
        Position("designer", "Graphic Designer", "marketing-manager", seats=2),
        Position("copywriter", "Copywriter", "marketing-manager"),
        Position("social", "Social Media Specialist", "marketing-manager"),
        Position("ecommerce", "E-commerce Specialist", "marketing-director", seats=2),
        Position("marketing-coordinator", "Marketing Coordinator", "marketing-manager"),
    ),
    # Marcus runs the store. Priya, Leo, and three department leads report to him directly, and
    # the leads manage everyone else, so he has reports both directly and through the leads.
    # Priya and Leo manage no one.
    ("Store Operations", "oak"): (
        Position("marcus", "Store Manager", "coo", person=MARCUS),
        Position("priya", "Visual Merchandiser", "marcus", person=PRIYA),
        Position("leo", "Sales Associate", "marcus", HOURLY, person=LEO),
        Position("oak-apparel-lead", "Department Lead, Apparel", "marcus"),
        Position("oak-apparel", "Sales Associate", "oak-apparel-lead", HOURLY, seats=13),
        Position("oak-home-lead", "Department Lead, Home", "marcus"),
        Position("oak-home", "Sales Associate", "oak-home-lead", HOURLY, seats=12),
        Position("oak-front-end", "Front End Lead", "marcus"),
        Position("oak-cashier", "Cashier", "oak-front-end", HOURLY, seats=10),
        Position("oak-service", "Customer Service Associate", "oak-front-end", HOURLY, seats=4),
    ),
    ("Distribution", "aus"): (
        Position("aus-manager", "Warehouse Manager", "coo"),
        Position("aus-inventory", "Inventory Control Specialist", "aus-manager", HOURLY, seats=2),
        Position("aus-shipping", "Shipping Coordinator", "aus-manager"),
        Position("aus-days", "Shift Supervisor, Days", "aus-manager"),
        Position("mateo", "Warehouse Associate", "aus-days", HOURLY, person=MATEO),
        Position("aus-day-crew", "Warehouse Associate", "aus-days", HOURLY, seats=12),
        Position("aus-day-forklift", "Forklift Operator", "aus-days", HOURLY, seats=2),
        Position("aus-nights", "Shift Supervisor, Nights", "aus-manager"),
        Position("aus-night-crew", "Warehouse Associate", "aus-nights", HOURLY, seats=12),
        Position("aus-night-forklift", "Forklift Operator", "aus-nights", HOURLY, seats=2),
    ),
}

# Everyone else's names. Each list has more names than the company has unnamed people, and no
# name appears twice, so no two people in a sandbox share a first name. The lists are blocks of
# words rather than tuples, which ruff would format one name per line.
GIVEN_NAMES = """
Aaliyah Aaron Abigail Adrian Aisha Alejandro Alicia Amara Amir Ana
Andre Andrea Angela Anjali Arjun Ava Benjamin Bianca Brandon Brian
Brianna Caleb Camila Carlos Carmen Chloe Christopher Daniel Darius Deepa
Desmond Diego Elena Elijah Emily Emmanuel Eric Erin Esperanza Ethan
Fatima Felix Fernando Gabriel Gloria Grace Hannah Hassan Hector Hiroshi
Imani Isaac Isabel Ivan Jamal James Jasmine Javier Jenna Jordan
Joseph Joy Julia Kai Kayla Keisha Kenji Kevin Khalid Laila
Lauren Layla Lucia Luis Malik Maya Megan Mei Miguel Mina
Nadia Naomi Nathan Nia Nicole Noah Olivia Omar Oscar Rachel
Rafael Rahul Rebecca Ricardo Riya Rosa Ryan Samir Samuel Sara
Sean Sofia Sophie Stephanie Tamika Tariq Teresa Thomas Tiana Tyler
Valentina Victor Vikram Wei Wesley Xavier Yasmin Yuki Zara Zoe
""".split()  # noqa: SIM905

FAMILY_NAMES = """
Abbott Adeyemi Aguilar Ahmed Ali Anderson Baker Banerjee Barnes Bautista
Becker Brooks Bryant Campbell Carter Castillo Chang Chen Choi Coleman
Collins Cruz Delgado Diaz Dixon Edwards Ellis Espinoza Evans Farah
Fischer Flores Foster Garcia Gonzalez Gordon Greene Gupta Gutierrez Hall
Harris Hayes Henderson Hernandez Hoang Hughes Ibrahim Iyer Jackson Jenkins
Jimenez Johnson Kapoor Kaur Kelly Khan Kim Kowalski Lee Lewis
Lopez Mahmoud Martin Martinez Mendoza Mitchell Morales Moreno Murphy Nair
Nelson Nguyen Novak Okafor Okoro Ortiz Owens Park Patel Perez
Peterson Phillips Price Ramirez Ramos Reddy Reyes Richardson Rivera Robinson
Rodriguez Romero Ross Russell Saito Sanchez Santos Shah Silva Singh
Soto Stewart Sullivan Tanaka Taylor Thompson Torres Tran Turner Vargas
Vasquez Walker Washington Watson Williams Wong Wright Yamamoto Young Zhang
""".split()  # noqa: SIM905

STREET_NAMES = """
Alder Aspen Birch Bluebell Cedar Clover Foxglove Hawthorn
Juniper Larkspur Linden Magnolia Marigold Sycamore Thistle Willow
""".split()  # noqa: SIM905
STREET_TYPES = ("Street", "Avenue", "Lane", "Court", "Drive", "Way", "Place")
```

The name lists are blocks of words split at import, because ruff would format a tuple of 120
strings one name per line. Ruff's SIM905 rule prefers a list literal, hence the three `noqa`
comments.

- [ ] **Step 5: Create `apps/api/app/modules/sandbox/seed.py`.** Task 13 adds `insert_company`
      to the end of this file.

```python
"""The seed company: the same fictional company of 120 people in every sandbox.

`build_company` builds it in memory, and `insert_company` writes it into a sandbox. Names come
from fixed lists and every other choice from a fixed seed. IDs are uuid5 of the tenant ID and a
stable key, so only the IDs differ between sandboxes. Dates count back from the tenant's anchor
date, so "last week" always means last week.
"""

import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID, uuid5

from app.domain.holidays import holidays_for
from app.modules.sandbox.seed_data import (
    FAMILY_NAMES,
    GIVEN_NAMES,
    LOCATIONS,
    ORG,
    PERSONAL_EMAIL_DOMAIN,
    SEED,
    STREET_NAMES,
    STREET_TYPES,
    WORK_EMAIL_DOMAIN,
    LocationSpec,
    PersonSpec,
    Position,
)

# Everyone drawn from the seed is 22 to 63 years old, was hired at 19 or older, and joined between
# a month and 12 years before the anchor date.
YOUNGEST_DAYS = 22 * 365
OLDEST_DAYS = 64 * 365
YOUNGEST_AT_HIRE_DAYS = 19 * 365
NEWEST_HIRE_DAYS = 30
LONGEST_TENURE_DAYS = 12 * 365


@dataclass(frozen=True, slots=True)
class LocationRow:
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    city: str
    state: str
    timezone: str


@dataclass(frozen=True, slots=True)
class DepartmentRow:
    id: UUID
    tenant_id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class PersonRow:
    id: UUID
    tenant_id: UUID
    given_name: str
    family_name: str
    title: str
    department_id: UUID
    location_id: UUID
    manager_id: UUID | None
    work_email: str
    employment_type: str
    hire_date: date
    is_hr_admin: bool
    persona_key: str | None


@dataclass(frozen=True, slots=True)
class PersonPrivateRow:
    person_id: UUID
    tenant_id: UUID
    personal_email: str
    phone: str
    home_address: str
    date_of_birth: date


@dataclass(frozen=True, slots=True)
class HolidayRow:
    id: UUID
    tenant_id: UUID
    location_id: UUID
    holiday_date: date
    name: str


type Row = LocationRow | DepartmentRow | PersonRow | PersonPrivateRow | HolidayRow

# The tables the seed fills, parents first, each with its row type. A row type's fields are
# exactly its table's columns, under the same names: insert_company relies on that, and a test
# checks it against the models.
ROW_TYPES: dict[str, type[Row]] = {
    "locations": LocationRow,
    "departments": DepartmentRow,
    "people": PersonRow,
    "person_private": PersonPrivateRow,
    "holidays": HolidayRow,
}


@dataclass(frozen=True, slots=True)
class SeedCompany:
    """One sandbox's seed rows. The fields after the first two are named after their tables."""

    tenant_id: UUID
    anchor_date: date
    locations: tuple[LocationRow, ...]
    departments: tuple[DepartmentRow, ...]
    people: tuple[PersonRow, ...]
    person_private: tuple[PersonPrivateRow, ...]
    holidays: tuple[HolidayRow, ...]


class _Draws:
    """Seeded choices, all made through random.random().

    Python keeps random()'s sequence the same across versions for the same seed, which it doesn't
    promise for choice() or shuffle(). So upgrading Python can't quietly change the company.
    """

    def __init__(self, seed: int) -> None:
        # Not for security: the point is that every sandbox gets the same choices.
        self._random = random.Random(seed)  # noqa: S311

    def below(self, limit: int) -> int:
        """A whole number from 0 up to, but not including, `limit`."""
        return int(self._random.random() * limit)

    def between(self, low: int, high: int) -> int:
        """A whole number from `low` to `high`, both included."""
        return low + self.below(high - low + 1)

    def pick[T](self, items: Sequence[T]) -> T:
        return items[self.below(len(items))]

    def shuffled[T](self, items: Sequence[T]) -> list[T]:
        """A shuffled copy of `items` (a Fisher-Yates shuffle)."""
        result = list(items)
        for index in range(len(result) - 1, 0, -1):
            other = self.below(index + 1)
            result[index], result[other] = result[other], result[index]
        return result


@dataclass(frozen=True, slots=True)
class _Seat:
    key: str
    department: str
    location: LocationSpec
    position: Position


def build_company(tenant_id: UUID, anchor_date: date) -> SeedCompany:
    """Build one sandbox's company in memory. Pure: equal arguments always give equal rows."""

    def make_id(kind: str, key: str) -> UUID:
        return uuid5(tenant_id, f"{kind}:{key}")

    draws = _Draws(SEED)
    seats = list(_seats())
    person_ids = {seat.key: make_id("person", seat.key) for seat in seats}
    given_names = draws.shuffled(GIVEN_NAMES)
    family_names = draws.shuffled(FAMILY_NAMES)
    phone_numbers = {spec.code: iter(draws.shuffled(range(100))) for spec in LOCATIONS}
    people: list[PersonRow] = []
    private: list[PersonPrivateRow] = []
    for seat in seats:
        who = seat.position.person or _someone(draws, given_names.pop(), family_names.pop())
        manager = seat.position.manager
        location = seat.location
        people.append(
            PersonRow(
                id=person_ids[seat.key],
                tenant_id=tenant_id,
                given_name=who.given_name,
                family_name=who.family_name,
                title=seat.position.title,
                department_id=make_id("department", seat.department),
                location_id=make_id("location", location.code),
                manager_id=None if manager is None else person_ids[manager],
                work_email=f"{who.given_name}.{who.family_name}@{WORK_EMAIL_DOMAIN}".lower(),
                employment_type=seat.position.employment_type,
                hire_date=anchor_date - timedelta(days=who.hired_days_ago),
                is_hr_admin=who.is_hr_admin,
                persona_key=who.persona_key,
            )
        )
        born = anchor_date - timedelta(days=who.born_days_ago)
        personal_email = f"{who.given_name}.{who.family_name}{born:%y}@{PERSONAL_EMAIL_DOMAIN}"
        private.append(
            PersonPrivateRow(
                person_id=person_ids[seat.key],
                tenant_id=tenant_id,
                personal_email=personal_email.lower(),
                phone=f"{location.area_code}-555-01{next(phone_numbers[location.code]):02d}",
                home_address=_address(draws, location),
                date_of_birth=born,
            )
        )

    return SeedCompany(
        tenant_id=tenant_id,
        anchor_date=anchor_date,
        locations=tuple(
            LocationRow(
                make_id("location", spec.code),
                tenant_id,
                spec.code,
                spec.name,
                spec.city,
                spec.state,
                spec.timezone,
            )
            for spec in LOCATIONS
        ),
        departments=tuple(
            DepartmentRow(make_id("department", name), tenant_id, name)
            for name in dict.fromkeys(department for department, _ in ORG)
        ),
        people=tuple(people),
        person_private=tuple(private),
        holidays=tuple(
            HolidayRow(
                make_id("holiday", f"{spec.code}:{holiday.holiday_date.isoformat()}"),
                tenant_id,
                make_id("location", spec.code),
                holiday.holiday_date,
                holiday.name,
            )
            for spec in LOCATIONS
            for year in (anchor_date.year, anchor_date.year + 1)
            for holiday in holidays_for(spec.code, year)
        ),
    )


def _seats() -> Iterator[_Seat]:
    """Every seat in the org chart, in order. A position's several seats are numbered from 1."""
    locations = {spec.code: spec for spec in LOCATIONS}
    for (department, location_code), positions in ORG.items():
        for position in positions:
            for number in range(1, position.seats + 1):
                key = position.key if position.seats == 1 else f"{position.key}-{number}"
                yield _Seat(key, department, locations[location_code], position)


def _someone(draws: _Draws, given_name: str, family_name: str) -> PersonSpec:
    """A person drawn from the seed, for a seat without a named person."""
    born_days_ago = draws.between(YOUNGEST_DAYS, OLDEST_DAYS)
    longest = min(LONGEST_TENURE_DAYS, born_days_ago - YOUNGEST_AT_HIRE_DAYS)
    return PersonSpec(
        given_name, family_name, draws.between(NEWEST_HIRE_DAYS, longest), born_days_ago
    )


def _address(draws: _Draws, location: LocationSpec) -> str:
    """A made-up street address in the location's city."""
    street = f"{draws.between(100, 9899)} {draws.pick(STREET_NAMES)} {draws.pick(STREET_TYPES)}"
    return f"{street}, {location.city}, {location.state} {draws.pick(location.zip_codes)}"
```

- [ ] **Step 6: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/test_seed.py -q`
Expected: `19 passed`.

- [ ] **Step 7: Prove the test that Priya and Leo manage no one can fail, then undo.** In
      `apps/api/app/modules/sandbox/seed_data.py`, change the manager of the `oak-service`
      position from `"oak-front-end"` to `"priya"`.

Run: `cd apps/api && uv run pytest tests/test_seed.py -q`
Expected: `1 failed, 18 passed`. `test_priya_and_leo_manage_no_one` fails with an
`AssertionError` that lists the four customer service associates. Change the manager back to
`"oak-front-end"`.

- [ ] **Step 8: Run the API checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
Expected: `All checks passed!`, `54 files already formatted`,
`Success: no issues found in 54 source files`, `Domain code imports no framework KEPT`, and
`109 passed`.

### Task 13: Writing the company into a sandbox

**Files:**
- Modify: `apps/api/app/modules/sandbox/seed.py`
- Test: `apps/api/tests/integration/test_seeding.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/integration/test_seeding.py`

```python
"""Seeding a sandbox as the API's login: every row lands, sandboxes never collide, and it's fast."""

import math
import statistics
import time
from dataclasses import astuple, fields
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base
from app.db.models import Tenant
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.sandbox.seed import ROW_TYPES, SeedCompany, build_company, insert_company

pytestmark = pytest.mark.integration

ANCHOR = date(2026, 10, 5)
SANDBOXES_TIMED = 20
P95_LIMIT_SECONDS = 2.0

type TableRows = dict[str, set[tuple[Any, ...]]]


async def create_sandbox(engine: AsyncEngine, created_tenant_ids: list[UUID]) -> SeedCompany:
    """A new tenant row and its seed company, in one transaction, as sandbox creation will do it.

    The tenant is deleted when the test session ends, like every tenant `make_tenant` creates.
    """
    tenant_id = uuid4()
    created_tenant_ids.append(tenant_id)
    company = build_company(tenant_id, ANCHOR)
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    async with tenant_session(engine, TenantContext(tenant_id, None)) as session:
        session.add(Tenant(id=tenant_id, expires_at=expires_at, anchor_date=ANCHOR))
        # The tenant row goes first: every seeded row refers to it.
        await session.flush()
        await insert_company(session, company)
    return company


def rows_built(company: SeedCompany) -> TableRows:
    return {name: {astuple(row) for row in getattr(company, name)} for name in ROW_TYPES}


async def rows_read_back(engine: AsyncEngine, company: SeedCompany) -> TableRows:
    """Every seeded table's rows, read by the API's login inside the company's own sandbox."""
    rows: TableRows = {}
    async with tenant_session(engine, TenantContext(company.tenant_id, None)) as session:
        # As HR, so the private-details rule shows every private row.
        await set_is_hr(session, True)
        for name, row_type in ROW_TYPES.items():
            table = Base.metadata.tables[name]
            columns = [table.c[field.name] for field in fields(row_type)]
            rows[name] = {tuple(row) for row in await session.execute(select(*columns))}
    return rows


async def test_a_seeded_sandbox_reads_back_exactly_as_built(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    company = await create_sandbox(app_engine, created_tenant_ids)

    read_back = await rows_read_back(app_engine, company)

    assert {name: len(rows) for name, rows in read_back.items()} == {
        "locations": 3,
        "departments": 8,
        "people": 120,
        "person_private": 120,
        "holidays": 41,
    }
    assert read_back == rows_built(company)


async def test_two_sandboxes_with_identical_people_coexist(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    # Every unique rule starts with tenant_id. A global rule on work_email, persona_key, a
    # location code, or a department name would refuse the second sandbox.
    first = await create_sandbox(app_engine, created_tenant_ids)
    second = await create_sandbox(app_engine, created_tenant_ids)

    def unique_values(company: SeedCompany) -> tuple[list[str | None], ...]:
        return (
            [person.work_email for person in company.people],
            [person.persona_key for person in company.people],
            [location.code for location in company.locations],
            [department.name for department in company.departments],
        )

    assert unique_values(first) == unique_values(second)
    assert await rows_read_back(app_engine, first) == rows_built(first)
    assert await rows_read_back(app_engine, second) == rows_built(second)


async def test_creating_a_sandbox_takes_under_two_seconds_at_p95(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    durations: list[float] = []
    for _ in range(SANDBOXES_TIMED):
        started = time.perf_counter()
        await create_sandbox(app_engine, created_tenant_ids)
        durations.append(time.perf_counter() - started)

    p50 = statistics.median(durations)
    # The nearest-rank 95th percentile: the 19th fastest of 20.
    p95 = sorted(durations)[math.ceil(0.95 * len(durations)) - 1]
    print(f"\n{SANDBOXES_TIMED} sandboxes: p50 {p50 * 1000:.0f} ms, p95 {p95 * 1000:.0f} ms")
    assert p95 < P95_LIMIT_SECONDS
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/integration/test_seeding.py -q`
Expected: a collection error,
`ImportError: cannot import name 'insert_company' from 'app.modules.sandbox.seed'`.

- [ ] **Step 3: In `apps/api/app/modules/sandbox/seed.py`, replace the imports above
      `from app.modules.sandbox.seed_data import (` with:**

```python
import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, fields
from datetime import date, timedelta
from uuid import UUID, uuid5

from sqlalchemy import Insert, bindparam, func, insert, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

# Importing the models puts their tables on Base.metadata.
from app.db import models  # noqa: F401
from app.db.base import Base
from app.domain.holidays import holidays_for
```

- [ ] **Step 4: Add this to the end of `apps/api/app/modules/sandbox/seed.py`**

```python
async def insert_company(session: AsyncSession, company: SeedCompany) -> None:
    """Write the company into its sandbox, inside the caller's transaction.

    The session must be scoped to the company's tenant (see app/db/tenancy.py), or row-level
    security refuses every row. Each table takes one INSERT ... SELECT FROM unnest(...), parents
    first, with each column's values sent as one typed array. COPY would be faster, but Postgres
    refuses it into a table under row-level security. Nothing is read back: the private-details
    rule would refuse a RETURNING on person_private.
    """
    for table_name, row_type in ROW_TYPES.items():
        rows: tuple[Row, ...] = getattr(company, table_name)
        values = {
            field.name: [getattr(row, field.name) for row in rows] for field in fields(row_type)
        }
        await session.execute(_INSERTS[table_name], values)


def _unnest_insert(table_name: str, row_type: type[Row]) -> Insert:
    """INSERT INTO <table> (<columns>) SELECT ... FROM unnest(<one typed array per column>)."""
    table = Base.metadata.tables[table_name]
    names = [field.name for field in fields(row_type)]
    arrays = [bindparam(name, type_=ARRAY(table.c[name].type)) for name in names]
    unnested = func.unnest(*arrays).table_valued(*names).render_derived(name="seed")
    return insert(table).from_select(names, select(*unnested.c))


# Built once, from the models, so each array's type always matches its column.
_INSERTS = {name: _unnest_insert(name, row_type) for name, row_type in ROW_TYPES.items()}
```

- [ ] **Step 5: Run the tests, with `-s` so the timing line prints**

Run: `cd apps/api && uv run pytest tests/integration/test_seeding.py -q -s`
Expected: `3 passed`, and a line like `20 sandboxes: p50 13 ms, p95 16 ms`. Your times will
differ. The test fails only if the p95 reaches 2 seconds.

- [ ] **Step 6: Confirm the tests cleaned up after themselves.** Run from the repository root.

Run: `docker compose exec -T db psql -U opendoor -d opendoor -tAc "SELECT count(*) FROM tenants"`
Expected: `0`.

- [ ] **Step 7: Prove the coexistence test catches a global unique rule, then undo.** Run the
      first command from the repository root.

Run: `docker compose exec -T db psql -U opendoor -d opendoor -c "CREATE UNIQUE INDEX zz_people_work_email ON people (work_email)"`
Then run: `cd apps/api && uv run pytest tests/integration/test_seeding.py -q`
Expected: `2 failed, 1 passed`, with
`asyncpg.exceptions.UniqueViolationError: duplicate key value violates unique constraint "zz_people_work_email"`.
The second sandbox can't be written. The timing test fails the same way, because it creates
twenty sandboxes. Stage 1's unique-index test also fails while the index exists.
Then run: `docker compose exec -T db psql -U opendoor -d opendoor -c "DROP INDEX zz_people_work_email"`

- [ ] **Step 8: Run the API checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
Expected: `All checks passed!`, `55 files already formatted`,
`Success: no issues found in 55 source files`, `Domain code imports no framework KEPT`, and
`112 passed`. That is 76 unit tests and 36 database tests.

### Task 14: Close Stage 2

**Files:**
- Modify: `CHANGELOG.md`, `docs/ROADMAP.md`

- [ ] **Step 1: Add to `CHANGELOG.md` under `## [Unreleased]` → `### Added`,** after the stage 1
      entry

```markdown
- **The seed company** (Phase 1, stage 2). Every sandbox can now be filled with the same
  fictional company: 120 people in eight departments, 40 at Denver HQ, 45 at the Oakland store,
  and 35 at the Austin warehouse, with every reporting line leading up to the CEO. The demo's
  people are in it. Marcus manages the Oakland store: Priya (salaried), Leo, and three department
  leads report to him, and the leads manage the store's associates. Mateo is an hourly warehouse
  associate in Austin, and Dana, the HR partner at Denver HQ, is the only HR administrator. Also
  added:
  - The company holiday calendar, as pure rules that the time-off engine can reuse in Phase 5.
    Every location closes on six holidays, moved to the Friday or Monday when one falls on a
    weekend, and Denver HQ also closes the day after Thanksgiving. Each sandbox stores the
    calendar for its anchor year and the next.
  - Private details that are plainly fictional: `example.com` emails, phone numbers in the
    555-0100 to 555-0199 range set aside for fiction, and made-up street addresses.
  - Tests that the same inputs always build the same company, that the personas and reporting
    lines are right, that Priya and Leo manage no one, that two sandboxes with identical people
    sit side by side in the database, and that creating a sandbox takes under 2 seconds at the
    95th percentile.
```

- [ ] **Step 2: Update `docs/ROADMAP.md`.** Replace the Phase 1 row of the status table with this
      one, using today's date and Stage 1's pull request number:

```markdown
| 1 Tenancy, identity, permissions | In progress: stage 2 of 4 (the seed company) | `feat/phase-1-seed` | [#<stage 1 PR number>](https://github.com/musicteachj/open-door/pull/<stage 1 PR number>) | [phase 1 plan](plans/2026-10-03-phase-1-tenancy-identity-permissions.md) | <today> |
```

Then, in the Phase 1 row of the Phases table, replace "the `seed_tenant` generator" with "the
seed company generator". The generator is `build_company` and `insert_company`, and nothing is
called `seed_tenant`.

- [ ] **Step 3: Run `make check` (with `make db` first)**

Run: `make db && make check`
Expected: every check passes.
- `check-api` ends with `112 passed`, `No new upgrade operations detected.`, and the schema up
  to date.
- `check-web` passes unchanged.
- `check-docs` reports `0 Errors`, with no placeholders printed.
- zizmor reports `No findings to report`.

While planning, `make check` passed in the scratch clone with these two documents edited.
`make db` itself wasn't run, because it starts the Compose database. Its migrate and bootstrap
commands were run.

- [ ] **Step 4: Run `/code-review medium` on the whole branch against `dev`,** committed and
      uncommitted work together, and fix anything real it finds. Re-run `make check` after any
      fix.

- [ ] **Step 5: Propose the commit and PR, and wait for the owner's OK.** Commit message:

```
Fill each sandbox with the same fictional company

Every sandbox can now be seeded with one fictional company: 120
people in eight departments across Denver HQ, the Oakland store, and
the Austin warehouse, with a reporting line from everyone up to the
CEO. The people the demo is built around are in it. Marcus manages
the store, where Priya, Leo, and three department leads report to
him; Priya and Leo manage no one. Mateo works at the warehouse, and
Dana is the HR partner and the only HR administrator.

The company is built in memory from fixed name lists and a fixed
random seed, so every sandbox gets exactly the same people under its
own IDs. It is written with one insert per table, which works under
the database's row-level security (RLS). Creating a sandbox took
about 15 milliseconds at the 95th percentile, against a 2-second
budget.

The company holiday calendar is pure code that the time-off engine
can reuse in Phase 5: six holidays, moved off weekends, plus the day
after Thanksgiving at Denver HQ. This is stage 2 of 4 for Phase 1.
Sessions and the API endpoints come next.
```

- [ ] **Step 6: With the owner's OK, push and open the PR into `dev`.** Title: "Fill each sandbox
      with the same fictional company". Body:

```markdown
## What this does
Gives every sandbox the same fictional company. `build_company` builds 120 people in eight
departments across Denver HQ, the Oakland store, and the Austin warehouse, with plainly fictional
private details and two years of company holidays. `insert_company` writes it into a new sandbox
with one insert per table. The demo's people are in it. Marcus manages the Oakland store: Priya,
Leo, and three department leads report to him, and the leads manage the store's associates. Mateo
is an hourly associate at the Austin warehouse, and Dana is the HR partner at Denver HQ and the
only HR administrator.

## Why
Stage 3's personas and permission tests need a real company to sign in to, and every visitor
should see the same one, so the demo and the evals can rely on it. The holiday rules are pure
domain code, ready for the Phase 5 time-off engine, and Denver's extra day off gives that engine
a real difference between locations. This is stage 2 of 4 of the Phase 1 plan.

## How it was checked
`make check-api` passes with 112 tests, 36 of them against the real database. The holiday dates
for 2026, and the moved dates in 2027 and 2028, were worked out by hand from a calendar. The
database tests read every seeded row back as the API's own login, show that two sandboxes with
identical people sit side by side, and time 20 sandbox creations. While planning, the 95th
percentile was about 15 milliseconds, against a 2-second budget. The side-by-side test was shown
to fail when a unique rule that ignores the tenant was added, and the test that Priya and Leo
manage no one was shown to fail when Priya was given reports.

## What to look at
- The org chart, the names, and the fixed dates in `seed_data.py`. The demo and later evals will
  quote them.
- How a holiday observed in another year is filed: New Year's Day 2028 closes the office on
  Friday 2027-12-31, so it's in 2027's calendar.
- `insert_company`, which builds its statements from the models instead of from SQL strings.
```

- [ ] **Step 7: Confirm the pull request's checks are green**

Run: `gh pr checks <stage 2 PR number> --repo musicteachj/open-door --watch`
Expected: CI (Detect what changed, API, Docs, Workflows), Security, and Changelog all pass. The
API job's "Tests, connected as the API's own login" step now runs 112 tests.

---

# Stage 3: Sessions and signing in

**Branch:** `feat/phase-1-sessions`, off `dev` after Stage 2 merges.
**Ends with:** a visitor can start a sandbox, sign in as Priya, Mateo, Marcus, or Dana, switch
persona, and sign out, all over HTTP with real cookies. The session lives in a `__Host-` cookie
the page can't read. Every request that changes something passes a same-origin check, and a
signed-in one also needs its CSRF token. One pure function, `can()`, decides who may see what.
Each sandbox created, persona switched, and session ended is audited, and every refused request
goes to the security log. `make check-api` passes with 217 tests, 77 of them against the real
database.

> **Before you start:** run `make db`. The new tests sign in over HTTP against real sandboxes, so
> they need Stage 1's migrations and login users, and Stage 2's seed company.

## Decisions made while planning this stage

Every code block below is the exact final content of a file that was run in a scratch clone on
2026-10-03, and every "Expected" is the output it produced. Where a task changes part of a file,
the block is the exact text of that part. That ran against Postgres 17.11 (the pgvector image)
with Python 3.13.15, FastAPI 0.142.1, Starlette 1.7.0, pydantic 2.13.5, SQLAlchemy 2.1.1, and
asyncpg 0.31.0, and the web app with Node 24.19.0 and orval 8.39.0. The scratch database listened
on port 5434, and the commands here use 5433, the development port.

- **Phase 1 now has four stages, not three.** The spec's third stage came to about 2,400 lines of
  code and tests, well past the 1,500-line target. This stage covers sessions and signing in.
  Stage 4 adds the directory endpoints and their permission tests, the data inventory, and the
  backlog, and closes Phase 1. Even split, this stage is about 1,860 lines: 920 of code and 940
  of tests. The regenerated schema and client add another 920 generated lines, which need no
  line-by-line review.
- **The cookies work in a real browser over `http://localhost`.** The spec asked for this to be
  checked, because `__Host-` cookies must be `Secure`. While planning, the scratch API ran on
  port 8001 behind a Vite dev server on port 5174, with `APP_ORIGIN=http://localhost:5174`. A
  temporary page then made the app's calls with `fetch`, in headless Google Chrome
  154.0.8037.93. `POST /api/v1/sandboxes` returned 201, `GET /api/v1/me` 200, and
  `PUT /api/v1/session/persona` 200, with the CSRF token read from `document.cookie`. The page
  could read the CSRF cookie and could not see the session cookie. Chrome treats `localhost` as a
  secure context, so the cookies needed no weakening. The page and the proxy change were then
  removed. Other browsers weren't checked.
- **The identity module owns every check on a request.** Tokens, cookies, the security log, the
  same-origin middleware, and the CSRF check all live in `app/modules/identity/`. The middleware
  hashes the session cookie for its log line, so it needs the cookie's name and the hash
  function, and keeping it in the module means `app.core` never imports a module.
- **The CSRF check is part of the session dependency.** Every route that uses the signed-in
  dependency gets the check on POST, PUT, PATCH, and DELETE, so a new route can't forget it.
  `POST /sandboxes` doesn't use that dependency: the visitor has no session yet, so it relies on
  the same-origin check alone, as the spec says.
- **A signed-in request uses two transactions.** The session is looked up first, with no tenant,
  because `sessions` has no row-level security and the transaction hook needs the tenant before
  the request's own transaction begins. The request's transaction then loads the actor, sets the
  HR flag, and runs the route.
- **That transaction commits before the response is sent.** The dependency is declared with
  FastAPI's `Depends(..., scope="function")`. With the default scope, the commit would run after
  the client already had its 200, so a failed commit could never become an error.
- **An event about a request that never reached a session has no tenant or actor.** The
  same-origin check runs before any lookup, and an unknown token matches no session. Those events
  still carry the request ID, the client's IP address, and the first 8 characters of the token
  hash, taken from the cookie. Every reason in the log is a fixed phrase, never text from the
  request.
- **The JSON log formatter now writes structured fields.** A record logged with
  `extra={"fields": {...}}` gets those keys in its JSON line, and they can't overwrite the
  standard ones. Without this, the tenant, actor, IP address, and hash prefix would never reach
  the log.
- **A body that isn't JSON gets a 403, like any other same-origin failure.** The spec makes the
  JSON rule part of that check, so it is refused the same way rather than with a 415.
- **`record_event` refuses private fields in `before` and `after`.** Any private-details column
  name, in the database's spelling or the API's, raises an error. A careless
  `after=details.model_dump()` then fails loudly instead of copying private values into the
  append-only log.
- **What each audit event records:**
  - `sandbox.created`: the persona as the actor, the tenant as the target, and
    `{"personaKey": ...}` after.
  - `session.persona_switched`: the persona switched from as the actor, the one switched to as
    the target, and `personaKey` before and after.
  - `session.ended`: the actor only.
  - All three are recorded `via` `ui`.
- **A new sandbox's persona comes from the built company,** not from a query. `build_company`
  already holds every person, so the session starts in the same transaction that seeds them.
- **`/me`'s `tenantExpiresAt` comes from the session,** which copies the tenant's expiry, so it
  needs no extra query.
- **The persona is a named type in the schema, `PersonaKey`,** so the generated client gets the
  four values as a type. Any other value is a 422.
- **The import contract now covers the policy layer.** It is renamed "Domain and policy code
  import no framework", and CI's step is renamed with it. It also forbids `app.modules`, so
  neither pure layer can import the routes that call it.
- **Error responses aren't declared in the OpenAPI schema yet.** Every error is problem details,
  but the schema shows FastAPI's default 422 body. Stage 4 adds this to the backlog for Phase 2,
  where the screens first handle errors.
- **The backlog item to exempt `/api/v1/health` from authentication and CSRF is closed here.**
  Health is a GET with no session dependency, so neither the session nor the CSRF check reaches
  it, and the same-origin check only applies to requests that change state.
- **Each guarantee was shown to catch a break.**
  - A database import in the policy layer breaks the import contract (Task 15).
  - Dropping the recursive step from the reports query fails the actor tests (Task 18).
  - Swapping the two middlewares, and turning off the CSRF check, each fail five HTTP tests
    (Task 20).

### Task 15: The policy layer

**Files:**
- Create: `apps/api/app/policy/__init__.py`
- Modify: `apps/api/pyproject.toml`, `.github/workflows/ci.yml`
- Test: `apps/api/tests/test_policy.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_policy.py`

```python
"""The permission matrix, as plain values: no database and no HTTP."""

from typing import cast
from uuid import UUID, uuid4

import pytest

from app.policy import Action, Actor, PersonResource, can

TENANT_ID = uuid4()
EMPLOYEE_ID, COLLEAGUE_ID, MANAGER_ID, REPORT_ID, HR_ID = (uuid4() for _ in range(5))

EMPLOYEE = Actor(EMPLOYEE_ID, TENANT_ID, is_hr_admin=False, report_ids=frozenset())
MANAGER = Actor(MANAGER_ID, TENANT_ID, is_hr_admin=False, report_ids=frozenset({REPORT_ID}))
HR = Actor(HR_ID, TENANT_ID, is_hr_admin=True, report_ids=frozenset())

# The spec's matrix: the actor, the target, and what each action allows.
TARGETS: dict[str, tuple[Actor, UUID]] = {
    "self": (EMPLOYEE, EMPLOYEE_ID),
    "another employee": (EMPLOYEE, COLLEAGUE_ID),
    "manager, for a report": (MANAGER, REPORT_ID),
    "HR, for anyone": (HR, COLLEAGUE_ID),
}
MATRIX: dict[Action, dict[str, bool]] = {
    Action.DIRECTORY_READ: {
        "self": True,
        "another employee": True,
        "manager, for a report": True,
        "HR, for anyone": True,
    },
    Action.PERSON_PRIVATE_READ: {
        "self": True,
        "another employee": False,
        "manager, for a report": False,
        "HR, for anyone": True,
    },
}
CASES = [
    (action, relationship, allowed)
    for action, row in MATRIX.items()
    for relationship, allowed in row.items()
]


@pytest.mark.parametrize(("action", "relationship", "allowed"), CASES)
def test_the_permission_matrix(action: Action, relationship: str, allowed: bool) -> None:
    actor, target_id = TARGETS[relationship]

    assert can(actor, action, PersonResource(target_id)) is allowed


def test_the_matrix_covers_every_action_and_every_relationship() -> None:
    # A new action fails here until its row is added to the matrix.
    assert set(MATRIX) == set(Action)
    assert all(set(row) == set(TARGETS) for row in MATRIX.values())


def test_an_action_without_a_rule_is_denied_even_for_hr() -> None:
    unknown = cast(Action, "payroll.read")

    assert can(HR, unknown, PersonResource(HR_ID)) is False


def test_being_a_manager_comes_from_having_reports() -> None:
    assert (EMPLOYEE.is_manager, MANAGER.is_manager, HR.is_manager) == (False, True, False)
```

The unknown action is a string cast to `Action`, because the enum can't hold a member without a
rule. `can()` must refuse it rather than fail.

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_policy.py -q`
Expected: a collection error, `ModuleNotFoundError: No module named 'app.policy'`.

- [ ] **Step 3: Create `apps/api/app/policy/__init__.py`**

```python
"""Who may do what: one pure function that every route asks before it reads or acts.

Pure, like app.domain: no framework or database imports, which import-linter enforces (see
`[tool.importlinter]` in pyproject.toml). Deny by default: an action without a rule is refused.

Tenant scope isn't a rule here. Row-level security already keeps every target inside the actor's
tenant, so a person from another tenant never reaches this function.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Actor:
    """The signed-in person. Every field comes from the server session and the database."""

    person_id: UUID
    tenant_id: UUID
    is_hr_admin: bool
    # Direct and indirect reports, computed fresh for every request and never cached.
    report_ids: frozenset[UUID]

    @property
    def is_manager(self) -> bool:
        """Being a manager is derived from having reports, never stored."""
        return bool(self.report_ids)


class Action(StrEnum):
    DIRECTORY_READ = "directory.read"
    PERSON_PRIVATE_READ = "person_private.read"


@dataclass(frozen=True, slots=True)
class PersonResource:
    """The person an action is aimed at."""

    person_id: UUID


type Rule = Callable[[Actor, PersonResource], bool]


def _anyone_in_the_company(actor: Actor, target: PersonResource) -> bool:
    return True


def _themselves_or_hr(actor: Actor, target: PersonResource) -> bool:
    # A manager gets nothing extra: their reports' private details are not theirs to read.
    return target.person_id == actor.person_id or actor.is_hr_admin


RULES: Mapping[Action, Rule] = MappingProxyType(
    {
        Action.DIRECTORY_READ: _anyone_in_the_company,
        Action.PERSON_PRIVATE_READ: _themselves_or_hr,
    }
)


def can(actor: Actor, action: Action, target: PersonResource) -> bool:
    """Whether `actor` may perform `action` on `target`. An action without a rule is denied."""
    rule = RULES.get(action)
    return rule is not None and rule(actor, target)
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/test_policy.py -q`
Expected: `11 passed`.

- [ ] **Step 5: Show that the import contract doesn't cover the policy layer yet.** In
      `apps/api/app/policy/__init__.py`, add the line `import sqlalchemy  # noqa: F401` directly
      below `from uuid import UUID`. Leave it there for the next step.

Run: `cd apps/api && uv run lint-imports`
Expected: `Domain code imports no framework KEPT`. The contract checks only `app.domain`.

- [ ] **Step 6: Extend the contract.** In `apps/api/pyproject.toml`, replace the whole
      `[[tool.importlinter.contracts]]` table at the end of the file with:

```toml
[[tool.importlinter.contracts]]
name = "Domain and policy code import no framework"
type = "forbidden"
# The pure layers: the domain rules (the time-off engine, the holiday calendar) and the policy layer
# that decides who can see what.
source_modules = ["app.domain", "app.policy"]
# Every framework and I/O dependency they must never touch. Add each new one here.
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
    "app.modules",
]
```

Run: `cd apps/api && uv run lint-imports`
Expected: exit status 1, with `Domain and policy code import no framework BROKEN`,
`app.policy -> sqlalchemy (l.15)`, and `Contracts: 0 kept, 1 broken.`
Remove the `import sqlalchemy` line. Running it again gives
`Domain and policy code import no framework KEPT`.

- [ ] **Step 7: Rename CI's step to match.** In `.github/workflows/ci.yml`, in the `api` job,
      replace the line `      - name: Domain code imports no framework` with:

```yaml
      - name: Domain and policy code import no framework
```

- [ ] **Step 8: Run the API checks and the workflow checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
Expected: `All checks passed!`, `57 files already formatted`,
`Success: no issues found in 57 source files`, `Domain and policy code import no framework KEPT`,
and `123 passed`.

Run: `GH_TOKEN=$(gh auth token) make check-workflows`
Expected: actionlint prints nothing, and zizmor ends with
`No findings to report. Good job! (4 suppressed)`.

### Task 16: Session tokens, their cookies, and the security log

**Files:**
- Create: `apps/api/app/modules/identity/__init__.py`,
  `apps/api/app/modules/identity/tokens.py`, `apps/api/app/modules/identity/cookies.py`,
  `apps/api/app/modules/identity/security_log.py`
- Modify: `apps/api/app/core/logging.py`
- Test: `apps/api/tests/test_session_tokens.py`, `apps/api/tests/test_logging.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_session_tokens.py`

```python
"""Session and CSRF tokens, and the cookies that carry them."""

import hashlib
import re
from datetime import UTC, datetime, timedelta

from starlette.responses import Response

from app.modules.identity.cookies import (
    clear_session_cookies,
    seconds_until,
    set_session_cookies,
)
from app.modules.identity.tokens import SessionTokens, hash_token, new_token, token_matches

# 32 random bytes in URL-safe base64, without padding.
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
EXPIRES = re.compile(r"expires=[^;]+; ")
MAX_AGE = re.compile(r"Max-Age=([0-9]+)")


def test_a_token_is_32_random_bytes_in_43_cookie_safe_characters() -> None:
    tokens = {new_token() for _ in range(100)}

    assert len(tokens) == 100
    assert all(TOKEN.fullmatch(token) for token in tokens)


def test_the_server_keeps_a_tokens_sha256_digest() -> None:
    token = new_token()

    assert hash_token(token) == hashlib.sha256(token.encode()).digest()
    assert len(hash_token(token)) == 32


def test_a_token_matches_only_its_own_hash() -> None:
    token = new_token()

    assert token_matches(token, hash_token(token)) is True
    assert token_matches(new_token(), hash_token(token)) is False
    assert token_matches("", hash_token("")) is False
    assert token_matches(None, hash_token(token)) is False


def test_the_raw_tokens_never_appear_in_a_repr() -> None:
    tokens = SessionTokens.new()

    assert tokens.session not in repr(tokens)
    assert tokens.csrf not in repr(tokens)
    assert (tokens.session_hash, tokens.csrf_hash) == (
        hash_token(tokens.session),
        hash_token(tokens.csrf),
    )


def test_both_cookies_are_host_only_secure_lax_and_last_until_the_sandbox_expires() -> None:
    tokens = SessionTokens("session-token", "csrf-token")
    response = Response()
    expires_at = datetime.now(UTC) + timedelta(hours=24)

    set_session_cookies(response, tokens, expires_at)

    headers = response.headers.getlist("set-cookie")
    max_age = int(MAX_AGE.findall(headers[0])[0])
    assert 86_390 < max_age < 86_400
    assert headers == [
        f"__Host-od_session=session-token; HttpOnly; Max-Age={max_age}; Path=/; SameSite=lax;"
        " Secure",
        f"__Host-od_csrf=csrf-token; Max-Age={max_age}; Path=/; SameSite=lax; Secure",
    ]


def test_an_expired_sandbox_gives_a_cookie_age_of_zero() -> None:
    assert seconds_until(datetime.now(UTC) - timedelta(minutes=1)) == 0


def test_clearing_expires_both_cookies_with_the_same_attributes() -> None:
    response = Response()

    clear_session_cookies(response)

    # Starlette also sends an Expires of the current time, which the comparison leaves out.
    headers = [EXPIRES.sub("", header) for header in response.headers.getlist("set-cookie")]
    assert headers == [
        '__Host-od_session=""; HttpOnly; Max-Age=0; Path=/; SameSite=lax; Secure',
        '__Host-od_csrf=""; Max-Age=0; Path=/; SameSite=lax; Secure',
    ]
```

- [ ] **Step 2: Add a test for structured log fields** to the end of
      `apps/api/tests/test_logging.py`

```python
def test_structured_fields_are_added_but_never_replace_the_standard_keys() -> None:
    record = make_record("security.csrf_rejected")
    record.__dict__["fields"] = {"tenantId": "t-1", "message": "replaced", "level": "DEBUG"}

    entry = json.loads(JsonFormatter().format(record))

    assert entry["tenantId"] == "t-1"
    assert (entry["message"], entry["level"]) == ("security.csrf_rejected", "INFO")
```

- [ ] **Step 3: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_session_tokens.py -q`
Expected: a collection error, `ModuleNotFoundError: No module named 'app.modules.identity'`.

Run: `cd apps/api && uv run pytest tests/test_logging.py -q`
Expected: `1 failed, 6 passed`, with `KeyError: 'tenantId'`. The formatter ignores the fields.

- [ ] **Step 4: Create `apps/api/app/modules/identity/__init__.py`**

```python
"""Who is making a request: sessions, their cookies, the CSRF and same-origin checks, the actor,
and the security log for every refused request."""
```

- [ ] **Step 5: Create `apps/api/app/modules/identity/tokens.py`**

```python
"""Session and CSRF tokens: 32 random bytes each, kept by the server only as SHA-256 hashes.

The raw tokens live only in the visitor's cookies. The sessions table stores their hashes, so a
copy of the table can't be used to sign in, and a token is compared with its hash in constant
time.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

TOKEN_BYTES = 32


def new_token() -> str:
    """32 random bytes, as 43 URL-safe characters that a cookie can hold without quoting."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> bytes:
    """The SHA-256 digest the server stores and looks the token up by."""
    return hashlib.sha256(token.encode()).digest()


def token_matches(token: str | None, expected_hash: bytes) -> bool:
    """Whether `token` hashes to `expected_hash`, compared in constant time."""
    if not token:
        return False
    return hmac.compare_digest(hash_token(token), expected_hash)


@dataclass(frozen=True, slots=True)
class SessionTokens:
    """A new session's two raw tokens, on their way to the visitor's cookies.

    Neither appears in the repr, so logging this object can't leak them.
    """

    session: str = field(repr=False)
    csrf: str = field(repr=False)

    @classmethod
    def new(cls) -> "SessionTokens":
        return cls(new_token(), new_token())

    @property
    def session_hash(self) -> bytes:
        return hash_token(self.session)

    @property
    def csrf_hash(self) -> bytes:
        return hash_token(self.csrf)
```

- [ ] **Step 6: Create `apps/api/app/modules/identity/cookies.py`**

```python
"""The two cookies a session lives in.

Both names start with `__Host-`, which makes the browser insist on Secure, Path=/, and no Domain,
so no other host or path can set or overwrite them. Both last until the sandbox expires.

- `__Host-od_session` holds the session token. It is HttpOnly, so the page's scripts never see it.
- `__Host-od_csrf` holds the CSRF token. The page reads it and sends it back in the X-CSRF-Token
  header on every request that changes something.
"""

from datetime import UTC, datetime

from starlette.responses import Response

from app.modules.identity.tokens import SessionTokens

SESSION_COOKIE = "__Host-od_session"
CSRF_COOKIE = "__Host-od_csrf"
CSRF_HEADER = "X-CSRF-Token"


def seconds_until(expires_at: datetime) -> int:
    """Whole seconds from now until `expires_at`, rounded down, so a cookie never outlives it."""
    return max(0, int((expires_at - datetime.now(UTC)).total_seconds()))


def set_session_cookies(response: Response, tokens: SessionTokens, expires_at: datetime) -> None:
    max_age = seconds_until(expires_at)
    response.set_cookie(
        SESSION_COOKIE,
        tokens.session,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        tokens.csrf,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=False,
        samesite="lax",
    )


def clear_session_cookies(response: Response) -> None:
    """Expire both cookies. A browser accepts the change only with the same `__Host-` attributes."""
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=True, samesite="lax")
```

- [ ] **Step 7: Create `apps/api/app/modules/identity/security_log.py`**

```python
"""Refused requests, recorded in the JSON application log under the `app.security` logger.

Failures go here, not to the audit table: the audit log records what people did, and this records
what they were stopped from doing. Each event carries the request ID, the tenant and actor when
they are known, the client's IP address, and the first 8 characters of the session token's hash,
which is enough to connect events from one session. A raw token is never logged.
"""

import logging
from enum import StrEnum
from uuid import UUID

from starlette.requests import HTTPConnection

from app.core.request_id import request_id_var
from app.modules.identity.cookies import SESSION_COOKIE
from app.modules.identity.tokens import hash_token

logger = logging.getLogger("app.security")

TOKEN_HASH_PREFIX_LENGTH = 8


class SecurityEvent(StrEnum):
    SESSION_INVALID = "security.session_invalid"
    ORIGIN_REJECTED = "security.origin_rejected"
    CSRF_REJECTED = "security.csrf_rejected"
    AUTHZ_DENIED = "security.authz_denied"


def log_security_event(
    event: SecurityEvent,
    request: HTTPConnection,
    reason: str,
    *,
    tenant_id: UUID | None = None,
    actor_id: UUID | None = None,
    target_id: UUID | None = None,
) -> None:
    """Log one refused request. `reason` is a fixed phrase, never text from the request."""
    token = request.cookies.get(SESSION_COOKIE)
    fields = {
        "event": event.value,
        "reason": reason,
        "tenantId": None if tenant_id is None else str(tenant_id),
        "actorId": None if actor_id is None else str(actor_id),
        "targetId": None if target_id is None else str(target_id),
        "clientIp": None if request.client is None else request.client.host,
        "tokenHashPrefix": hash_token(token).hex()[:TOKEN_HASH_PREFIX_LENGTH] if token else None,
    }
    logger.warning(event.value, extra={"request_id": request_id_var.get(), "fields": fields})
```

- [ ] **Step 8: Replace `apps/api/app/core/logging.py`.** It now writes a record's structured
      fields, and `default=str` keeps a stray UUID from breaking a log line.

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
        # Structured fields passed as `extra={"fields": {...}}`. They can't replace the keys above.
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            entry.update({key: value for key, value in fields.items() if key not in entry})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str) -> None:
    """Send every log record, including uvicorn's, through one JSON handler on the root logger.

    Safe to call repeatedly: it replaces only its own handler, so pytest's caplog and any future
    handler (tracing, for example) stay attached.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not isinstance(h.formatter, JsonFormatter)]
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
        # uvicorn pins its own levels; NOTSET defers to the root, so LOG_LEVEL governs everything.
        uvicorn_logger.setLevel(logging.NOTSET)
```

- [ ] **Step 9: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/test_session_tokens.py tests/test_logging.py -q`
Expected: `14 passed`.

- [ ] **Step 10: Run the API checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
Expected: `All checks passed!`, `62 files already formatted`,
`Success: no issues found in 62 source files`, `Domain and policy code import no framework KEPT`,
and `131 passed`.

### Task 17: The same-origin check

**Files:**
- Create: `apps/api/app/modules/identity/same_origin.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_same_origin.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_same_origin.py`. They build a
      small app with the real middleware and problem handlers, so they need no database.

```python
"""The same-origin check, on a small app with the real middleware and problem handlers."""

import json
import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.problems import install_problem_handlers
from app.core.request_id import RequestIdMiddleware
from app.modules.identity.same_origin import SameOriginMiddleware

APP_ORIGIN = "http://localhost:5173"
SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    # As in create_app: the request-ID middleware is added last, so it wraps this check.
    app.add_middleware(SameOriginMiddleware, app_origin=APP_ORIGIN)
    app.add_middleware(RequestIdMiddleware)
    install_problem_handlers(app)

    @app.get("/things")
    async def list_things() -> list[str]:
        return []

    @app.post("/things")
    async def add_thing(thing: dict[str, str] | None = None) -> dict[str, str]:
        return thing or {}

    @app.delete("/things")
    async def clear_things() -> None:
        return None

    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.mark.parametrize(
    "headers",
    [
        SAME_ORIGIN,
        # Sec-Fetch-Site wins over Origin, which can then be anything.
        {**SAME_ORIGIN, "Origin": "https://elsewhere.example"},
        # Without Fetch Metadata, Origin must be the app's.
        {"Origin": APP_ORIGIN},
    ],
)
def test_a_request_from_the_app_passes(client: TestClient, headers: dict[str, str]) -> None:
    assert client.post("/things", json={"name": "lamp"}, headers=headers).status_code == 200
    assert client.delete("/things", headers=headers).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Sec-Fetch-Site": "none"},
        {"Sec-Fetch-Site": "cross-site", "Origin": APP_ORIGIN},
        {"Origin": "https://elsewhere.example"},
        {"Origin": "null"},
        # A trailing slash is a different origin.
        {"Origin": f"{APP_ORIGIN}/"},
        {},
    ],
)
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a_request_from_anywhere_else_is_refused(
    client: TestClient, method: str, headers: dict[str, str]
) -> None:
    response = client.request(method, "/things", headers=headers)

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Forbidden",
        "status": 403,
        "instance": "/things",
        "detail": "Requests that change data must come from the Open Door app, as JSON.",
        "requestId": response.headers["X-Request-ID"],
    }


@pytest.mark.parametrize(
    ("content_type", "status_code"),
    [
        ("application/json", 200),
        ("application/json; charset=utf-8", 200),
        ("text/plain", 403),
        ("application/x-www-form-urlencoded", 403),
        ("multipart/form-data; boundary=x", 403),
        (None, 403),
    ],
)
def test_a_body_must_be_json(
    client: TestClient, content_type: str | None, status_code: int
) -> None:
    headers = dict(SAME_ORIGIN)
    if content_type is not None:
        headers["Content-Type"] = content_type

    response = client.post("/things", content=b'{"name": "lamp"}', headers=headers)

    assert response.status_code == status_code


def test_reads_need_no_origin_headers(client: TestClient) -> None:
    assert client.get("/things").status_code == 200


def test_a_refusal_is_logged_as_a_security_event(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="app.security")
    headers = {"Sec-Fetch-Site": "cross-site", "Cookie": "__Host-od_session=a-raw-session-token"}

    response = client.post("/things", json={}, headers=headers)

    [record] = [record for record in caplog.records if record.name == "app.security"]
    assert record.getMessage() == "security.origin_rejected"
    assert record.__dict__["request_id"] == response.headers["X-Request-ID"]
    fields = record.__dict__["fields"]
    assert fields["event"] == "security.origin_rejected"
    assert fields["reason"] == "Sec-Fetch-Site is not same-origin"
    assert fields["clientIp"] == "testclient"
    assert len(fields["tokenHashPrefix"]) == 8
    # No session lookup happens here, so the tenant and actor are unknown.
    assert (fields["tenantId"], fields["actorId"]) == (None, None)
    assert "a-raw-session-token" not in json.dumps(fields)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_same_origin.py -q`
Expected: a collection error,
`ModuleNotFoundError: No module named 'app.modules.identity.same_origin'`.

- [ ] **Step 3: Create `apps/api/app/modules/identity/same_origin.py`**

```python
"""The same-origin check on every request that changes state: POST, PUT, PATCH, and DELETE.

Plain ASGI middleware, so every endpoint is covered by default, including sandbox creation, which
has no session and so no CSRF token yet. A browser says where a request came from in two
headers, read in this order:

1. `Sec-Fetch-Site` (Fetch Metadata). If present, it must be `same-origin`.
2. Otherwise `Origin`, which must equal APP_ORIGIN exactly.
3. With neither, the request can't show that it came from the app, so it is refused.

A request with a body must also be JSON. A cross-site HTML form can send only form encodings and
plain text, so this closes the path an old browser without either header would leave open.

A refusal is a 403 in problem details. It carries the request ID, because the request-ID
middleware wraps this one.
"""

from starlette import status
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.problems import problem_response
from app.modules.identity.security_log import SecurityEvent, log_security_event

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
JSON_MEDIA_TYPE = "application/json"


def _refusal(headers: Headers, app_origin: str) -> str | None:
    """Why the request is refused, as a fixed phrase for the log, or None if it may proceed."""
    fetch_site = headers.get("sec-fetch-site")
    if fetch_site is not None:
        if fetch_site != "same-origin":
            return "Sec-Fetch-Site is not same-origin"
    elif "origin" not in headers:
        return "neither Sec-Fetch-Site nor Origin is present"
    elif headers["origin"] != app_origin:
        return "Origin is not the app's origin"
    has_body = headers.get("content-length", "0") != "0" or "transfer-encoding" in headers
    media_type = headers.get("content-type", "").split(";")[0].strip().lower()
    if has_body and media_type != JSON_MEDIA_TYPE:
        return "the body is not JSON"
    return None


class SameOriginMiddleware:
    def __init__(self, app: ASGIApp, *, app_origin: str) -> None:
        self.app = app
        self.app_origin = app_origin

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return
        reason = _refusal(Headers(scope=scope), self.app_origin)
        if reason is None:
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        log_security_event(SecurityEvent.ORIGIN_REJECTED, request, reason)
        response = problem_response(
            request,
            status.HTTP_403_FORBIDDEN,
            "Requests that change data must come from the Open Door app, as JSON.",
        )
        await response(scope, receive, send)
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/test_same_origin.py -q`
Expected: `43 passed`.

- [ ] **Step 5: Add the middleware to the app.** Replace `apps/api/app/main.py`:

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
from app.modules.identity.same_origin import SameOriginMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Settings are validated here, so a bad environment fails at boot."""
    if settings is None:
        settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = create_engine(str(settings.database_url))
        try:
            yield
        finally:
            await app.state.engine.dispose()

    app = FastAPI(title="Open Door API", version=__version__, lifespan=lifespan)
    # The middleware added last runs first. The request-ID middleware wraps the same-origin check,
    # so even a refused request carries its ID. There is no CORS middleware: the web app reaches
    # the API on the same origin, so the browser blocks every cross-origin read by default.
    app.add_middleware(SameOriginMiddleware, app_origin=settings.app_origin)
    app.add_middleware(RequestIdMiddleware)
    install_problem_handlers(app)
    app.include_router(api_router)
    return app
```

Starlette runs the middleware added last first. Adding the same-origin check before the request-ID
middleware keeps the request ID outermost, so a refusal still carries it. Task 20 shows a test
failing when the two are swapped.

- [ ] **Step 6: Run the API checks.** Every existing route is a GET, so nothing else changes.

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q && uv run python scripts/export_openapi.py --check`
Expected: `All checks passed!`, `64 files already formatted`,
`Success: no issues found in 64 source files`, `Domain and policy code import no framework KEPT`,
`174 passed`, and `apps/web/openapi.json is up to date.`

### Task 18: Sessions, the actor, and the audit log

**Files:**
- Create: `apps/api/app/modules/identity/sessions.py`, `apps/api/app/modules/identity/actor.py`,
  `apps/api/app/modules/audit/__init__.py`, `apps/api/app/modules/audit/service.py`
- Test: `apps/api/tests/integration/test_identity.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/integration/test_identity.py`

```python
"""Sessions, the actor, and the audit log, as the API's login sees them."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.request_id import request_id_var
from app.db.models import AuditEvent, Tenant
from app.db.tenancy import NO_TENANT, TenantContext, tenant_session
from app.modules.audit.service import record_event
from app.modules.identity.actor import load_actor
from app.modules.identity.sessions import find_session, rotate_session, start_session
from app.modules.sandbox.seed import build_company, insert_company
from tests.integration.conftest import MakeTenant

pytestmark = pytest.mark.integration


async def seeded_tenant(engine: AsyncEngine, created_tenant_ids: list[UUID]) -> UUID:
    """A tenant filled with the seed company. It is deleted when the test session ends."""
    tenant_id = uuid4()
    created_tenant_ids.append(tenant_id)
    now = datetime.now(UTC)
    company = build_company(tenant_id, now.date())
    async with tenant_session(engine, TenantContext(tenant_id, None)) as session:
        tenant = {"id": tenant_id, "expires_at": now + timedelta(hours=24)}
        await session.execute(insert(Tenant).values(**tenant, anchor_date=company.anchor_date))
        await insert_company(session, company)
    return tenant_id


def person_id(tenant_id: UUID, key: str) -> UUID:
    """A seeded person's ID: the same key in every sandbox, under that sandbox's tenant ID."""
    return uuid5(tenant_id, f"person:{key}")


async def test_a_session_is_found_by_its_token_hash_until_it_expires(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    live, expired = await make_tenant(), await make_tenant(expired=True)
    async with tenant_session(app_engine, TenantContext(live.id, None)) as session:
        tokens = await start_session(
            session, live.id, live.employee_id, datetime.now(UTC) + timedelta(hours=1)
        )
    async with tenant_session(app_engine, TenantContext(expired.id, None)) as session:
        old_tokens = await start_session(
            session, expired.id, expired.employee_id, datetime.now(UTC) - timedelta(seconds=1)
        )

    async with tenant_session(app_engine, NO_TENANT) as session:
        found = await find_session(session, tokens.session_hash)
        by_csrf_hash = await find_session(session, tokens.csrf_hash)
        too_late = await find_session(session, old_tokens.session_hash)

    assert found is not None
    assert (found.tenant_id, found.person_id, found.csrf_hash) == (
        live.id,
        live.employee_id,
        tokens.csrf_hash,
    )
    assert (by_csrf_hash, too_late) == (None, None)


async def test_rotating_a_session_replaces_both_tokens_and_keeps_the_expiry(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        tokens = await start_session(session, tenant.id, tenant.employee_id, expires_at)
        current = await find_session(session, tokens.session_hash)
        assert current is not None
        rotated = await rotate_session(session, current, tenant.hr_id)

    async with tenant_session(app_engine, NO_TENANT) as session:
        old = await find_session(session, tokens.session_hash)
        new = await find_session(session, rotated.session_hash)
    assert old is None
    assert new is not None
    assert (new.person_id, new.expires_at, new.csrf_hash) == (
        tenant.hr_id,
        expires_at,
        rotated.csrf_hash,
    )
    assert rotated.csrf_hash != tokens.csrf_hash


@pytest.mark.parametrize(
    ("key", "is_hr_admin", "report_count"),
    [
        ("priya", False, 0),
        ("leo", False, 0),
        ("mateo", False, 0),
        ("dana", True, 0),
        ("oak-front-end", False, 14),
        # Five directly, and the leads' 39 associates through them.
        ("marcus", False, 44),
    ],
)
async def test_the_actor_has_every_report_direct_and_indirect(
    app_engine: AsyncEngine,
    created_tenant_ids: list[UUID],
    key: str,
    is_hr_admin: bool,
    report_count: int,
) -> None:
    tenant_id = await seeded_tenant(app_engine, created_tenant_ids)
    async with tenant_session(app_engine, TenantContext(tenant_id, None)) as session:
        actor = await load_actor(session, tenant_id, person_id(tenant_id, key))

    assert actor is not None
    assert (actor.is_hr_admin, len(actor.report_ids)) == (is_hr_admin, report_count)
    assert actor.is_manager is (report_count > 0)


async def test_marcus_manages_the_leads_and_their_teams(
    app_engine: AsyncEngine, created_tenant_ids: list[UUID]
) -> None:
    tenant_id = await seeded_tenant(app_engine, created_tenant_ids)
    async with tenant_session(app_engine, TenantContext(tenant_id, None)) as session:
        marcus = await load_actor(session, tenant_id, person_id(tenant_id, "marcus"))
        lead = await load_actor(session, tenant_id, person_id(tenant_id, "oak-front-end"))

    assert marcus is not None
    assert lead is not None
    direct = {"priya", "leo", "oak-apparel-lead", "oak-home-lead", "oak-front-end"}
    assert {person_id(tenant_id, key) for key in direct} <= marcus.report_ids
    assert lead.report_ids < marcus.report_ids


async def test_another_tenants_person_is_no_actor(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    mine, theirs = await make_tenant(), await make_tenant()

    async with tenant_session(app_engine, TenantContext(mine.id, None)) as session:
        actor = await load_actor(session, mine.id, theirs.hr_id)

    assert actor is None


async def test_an_audit_event_carries_the_request_id(
    app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    token = request_id_var.set("trace-42")
    try:
        async with tenant_session(app_engine, TenantContext(tenant.id, tenant.hr_id)) as session:
            await record_event(
                session,
                tenant_id=tenant.id,
                actor_id=tenant.hr_id,
                action="person_private.read",
                target_type="person",
                target_id=tenant.colleague_id,
                after={"fields": ["phone"]},
            )
    finally:
        request_id_var.reset(token)

    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        query = select(AuditEvent).where(AuditEvent.request_id == "trace-42")
        [event] = (await session.execute(query)).scalars()
    assert (event.action, event.via, event.actor_person_id, event.target_id, event.after) == (
        "person_private.read",
        "ui",
        tenant.hr_id,
        tenant.colleague_id,
        {"fields": ["phone"]},
    )


@pytest.mark.parametrize("field", ["phone", "home_address", "homeAddress", "dateOfBirth"])
async def test_an_audit_event_refuses_a_private_field(
    app_engine: AsyncEngine, make_tenant: MakeTenant, field: str
) -> None:
    tenant = await make_tenant()

    with pytest.raises(ValueError, match="directory fields only"):
        async with tenant_session(app_engine, TenantContext(tenant.id, tenant.hr_id)) as session:
            await record_event(
                session,
                tenant_id=tenant.id,
                actor_id=tenant.hr_id,
                action="person_private.read",
                after={field: "555-0100"},
            )
```

`seeded_tenant` fills a tenant with the seed company the way Stage 2's `create_sandbox` test helper
does, because the actor tests need the real org chart. The session tests use Stage 1's smaller
`make_tenant`.

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/integration/test_identity.py -q`
Expected: a collection error, `ModuleNotFoundError: No module named 'app.modules.audit'`.

- [ ] **Step 3: Create `apps/api/app/modules/identity/sessions.py`**

```python
"""The sessions table: start, find, rotate, and end a session.

`sessions` is the one table outside row-level security, because a session is looked up before the
tenant is known. So a session is only ever found by its token's hash, never listed or searched.
The API's login may select, insert, and delete these rows, but not update them. Rotating a
session deletes the old row and inserts a new one, in the caller's transaction.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserSession
from app.modules.identity.tokens import SessionTokens


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """A live session, as stored. It holds hashes only, never the raw tokens."""

    token_hash: bytes
    csrf_hash: bytes
    tenant_id: UUID
    person_id: UUID
    # Copied from the tenant: a session never outlives its sandbox.
    expires_at: datetime


async def find_session(session: AsyncSession, token_hash: bytes) -> SessionRecord | None:
    """The live session with this token hash. An expired one is never returned."""
    query = select(
        UserSession.token_hash,
        UserSession.csrf_hash,
        UserSession.tenant_id,
        UserSession.person_id,
        UserSession.expires_at,
    ).where(UserSession.token_hash == token_hash, UserSession.expires_at > func.now())
    row = (await session.execute(query)).one_or_none()
    return None if row is None else SessionRecord(*row)


async def start_session(
    session: AsyncSession, tenant_id: UUID, person_id: UUID, expires_at: datetime
) -> SessionTokens:
    """Store a new session and return its raw tokens, which only the cookies will hold."""
    tokens = SessionTokens.new()
    await session.execute(
        insert(UserSession).values(
            token_hash=tokens.session_hash,
            csrf_hash=tokens.csrf_hash,
            tenant_id=tenant_id,
            person_id=person_id,
            expires_at=expires_at,
        )
    )
    return tokens


async def end_session(session: AsyncSession, token_hash: bytes) -> None:
    await session.execute(delete(UserSession).where(UserSession.token_hash == token_hash))


async def rotate_session(
    session: AsyncSession, current: SessionRecord, person_id: UUID
) -> SessionTokens:
    """Replace `current` with a new session for `person_id`, with a new session token and a new
    CSRF token. Both old tokens stop working when the caller's transaction commits."""
    await end_session(session, current.token_hash)
    return await start_session(session, current.tenant_id, person_id, current.expires_at)
```

The inserts use `insert()` rather than `session.add()`, so SQLAlchemy never adds a `RETURNING` to
read back server defaults.

- [ ] **Step 4: Create `apps/api/app/modules/identity/actor.py`**

```python
"""Loading the actor: who the signed-in person is, and whom they manage.

Being a manager is derived, never stored. A person's reports, direct and indirect, come from a
recursive query on manager_id, run fresh for every request. A change to the org chart therefore
takes effect on the next request, without anyone signing in again.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Person
from app.policy import Actor


async def load_actor(session: AsyncSession, tenant_id: UUID, person_id: UUID) -> Actor | None:
    """The actor for `person_id`, or None if row-level security shows no such person."""
    is_hr_admin = await session.scalar(select(Person.is_hr_admin).where(Person.id == person_id))
    if is_hr_admin is None:
        return None
    reports = select(Person.id).where(Person.manager_id == person_id).cte(recursive=True)
    # UNION, not UNION ALL: a person already found is never walked again, so even a loop in the
    # org chart would end.
    reports = reports.union(select(Person.id).join(reports, Person.manager_id == reports.c.id))
    report_ids: frozenset[UUID] = frozenset(await session.scalars(select(reports.c.id)))
    return Actor(person_id, tenant_id, is_hr_admin=is_hr_admin, report_ids=report_ids)
```

- [ ] **Step 5: Create `apps/api/app/modules/audit/__init__.py`**

```python
"""The audit log: every action taken in a sandbox, recorded by `record_event`."""
```

- [ ] **Step 6: Create `apps/api/app/modules/audit/service.py`**

```python
"""record_event: a row in the append-only audit log for each action taken in a sandbox.

Each row carries the request's ID, so it can be matched with that request's log lines. `before`
and `after` hold directory fields only. A read of private details records the names of the fields
it returned, never their values, so a privacy deletion request never means editing this log.

Refused requests are not audited here. They go to the security log (see
app/modules/identity/security_log.py).
"""

from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from pydantic.alias_generators import to_camel
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_id import request_id_var
from app.db.models import AuditEvent, PersonPrivate

type AuditAction = Literal[
    "sandbox.created",
    "session.persona_switched",
    "session.ended",
    "person_private.read",
]
type Via = Literal["ui", "assistant", "system"]

_PRIVATE_COLUMNS = set(PersonPrivate.__table__.columns.keys()) - {"person_id", "tenant_id"}
# Each private column, as stored and as the API names it. None may be a key in before or after.
PRIVATE_FIELD_NAMES = frozenset(_PRIVATE_COLUMNS | {to_camel(name) for name in _PRIVATE_COLUMNS})


async def record_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: UUID | None,
    action: AuditAction,
    target_type: str | None = None,
    target_id: UUID | None = None,
    before: Mapping[str, object] | None = None,
    after: Mapping[str, object] | None = None,
    via: Via = "ui",
) -> None:
    """Add the event in the caller's transaction, so it commits or rolls back with the action."""
    for snapshot in (before, after):
        if snapshot is not None and not PRIVATE_FIELD_NAMES.isdisjoint(snapshot):
            msg = "An audit event's before and after hold directory fields only, never private ones"
            raise ValueError(msg)
    await session.execute(
        insert(AuditEvent).values(
            tenant_id=tenant_id,
            actor_person_id=actor_id,
            via=via,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=None if before is None else dict(before),
            after=None if after is None else dict(after),
            request_id=request_id_var.get(),
        )
    )
```

- [ ] **Step 7: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/integration/test_identity.py -q`
Expected: `15 passed`.

- [ ] **Step 8: Prove the actor tests need the recursive step, then undo.** In
      `apps/api/app/modules/identity/actor.py`, comment out the line that starts
      `reports = reports.union(`. The query then finds direct reports only.

Run: `cd apps/api && uv run pytest tests/integration/test_identity.py -q`
Expected: `2 failed, 13 passed`. Marcus's case fails with `assert (False, 5) == (False, 44)`, and
`test_marcus_manages_the_leads_and_their_teams` fails because a lead's team is no longer inside
Marcus's reports. Restore the line.

- [ ] **Step 9: Run the API checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
Expected: `All checks passed!`, `69 files already formatted`,
`Success: no issues found in 69 source files`, `Domain and policy code import no framework KEPT`,
and `189 passed`.

### Task 19: How the API shows a person: the directory card and `me`

**Files:**
- Create: `apps/api/app/api/schemas.py`, `apps/api/app/modules/people/__init__.py`,
  `apps/api/app/modules/people/schemas.py`
- Test: `apps/api/tests/test_people_schemas.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_people_schemas.py`. Stage 4
      adds the private details and the directory cursor to this file.

```python
"""Each tier of what the API shows about a person has exactly its own fields, in camelCase."""

from app.modules.people.schemas import DirectoryCard, Me

CARD_FIELDS = {
    "id",
    "givenName",
    "familyName",
    "title",
    "department",
    "location",
    "manager",
    "workEmail",
}
ME_ONLY_FIELDS = {"employmentType", "isManager", "isHrAdmin", "personaKey", "tenantExpiresAt"}
PRIVATE_FIELDS = {"personalEmail", "phone", "homeAddress", "dateOfBirth"}


def json_fields(model: type[DirectoryCard]) -> set[str]:
    return set(model.model_json_schema(by_alias=True)["properties"])


def test_the_directory_card_has_none_of_the_me_only_or_private_fields() -> None:
    assert json_fields(DirectoryCard) == CARD_FIELDS
    assert json_fields(DirectoryCard).isdisjoint(ME_ONLY_FIELDS | PRIVATE_FIELDS)


def test_me_adds_only_the_me_only_fields() -> None:
    assert json_fields(Me) == CARD_FIELDS | ME_ONLY_FIELDS
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_people_schemas.py -q`
Expected: a collection error, `ModuleNotFoundError: No module named 'app.modules.people'`.

- [ ] **Step 3: Create `apps/api/app/api/schemas.py`,** the camelCase base for every body

```python
"""The base for every request and response body: snake_case in Python, camelCase in JSON."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """`given_name` in Python is `givenName` in JSON, both ways. FastAPI serializes by alias."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
        frozen=True,
    )
```

- [ ] **Step 4: Create `apps/api/app/modules/people/__init__.py`**

```python
"""The directory and private details: who works here, and what each person may see of them."""
```

- [ ] **Step 5: Create `apps/api/app/modules/people/schemas.py`.** Stage 4 adds the directory
      page and the private details.

```python
"""What the API shows of a person. Each tier is its own model, so a field can't leak between them.

- `DirectoryCard` is what anyone in the company may see.
- `Me` adds what only the signed-in person sees about themselves.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from app.api.schemas import CamelModel

type PersonaKey = Literal["priya", "mateo", "marcus", "dana"]


class DepartmentRef(CamelModel):
    id: UUID
    name: str


class LocationRef(CamelModel):
    id: UUID
    name: str
    state: str


class PersonRef(CamelModel):
    id: UUID
    given_name: str
    family_name: str


class DirectoryCard(CamelModel):
    id: UUID
    given_name: str
    family_name: str
    title: str
    department: DepartmentRef
    location: LocationRef
    manager: PersonRef | None
    work_email: str


class Me(DirectoryCard):
    """The signed-in person's own card, with the fields only they see."""

    employment_type: Literal["salaried", "hourly"]
    is_manager: bool
    is_hr_admin: bool
    persona_key: PersonaKey
    tenant_expires_at: datetime
```

- [ ] **Step 6: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/test_people_schemas.py -q`
Expected: `2 passed`.

- [ ] **Step 7: Run the API checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
Expected: `All checks passed!`, `73 files already formatted`,
`Success: no issues found in 73 source files`, `Domain and policy code import no framework KEPT`,
and `191 passed`.

### Task 20: Signing in over HTTP

**Files:**
- Create: `apps/api/app/modules/people/queries.py`, `apps/api/app/modules/identity/deps.py`,
  `apps/api/app/modules/identity/routes.py`, `apps/api/app/modules/sandbox/service.py`,
  `apps/api/app/modules/sandbox/routes.py`
- Modify: `apps/api/app/api/v1/router.py`, `apps/api/tests/integration/conftest.py`
- Test: `apps/api/tests/integration/test_api_sessions.py`

- [ ] **Step 1: Give the integration tests a browser.** In
      `apps/api/tests/integration/conftest.py`, replace everything above
      `@pytest.fixture(scope="session")` (the docstring and the imports) with:

```python
"""Database fixtures for the integration tests.

One engine per database login. A test that needs a URL that isn't set fails loudly instead of
skipping:

- `app_engine` connects as DATABASE_URL, the API's own login (a member of od_app).
- `owner_engine` connects as MIGRATION_DATABASE_URL, the database owner.
- `cleanup_engine` connects as CLEANUP_DATABASE_URL, the cleanup login (a member of od_cleanup).

`make_tenant` creates a small sandbox company as the API's login, with a row in every table, and
returns a `SampleTenant`. `browser` and `open_browser` give the HTTP tests a client that behaves
like the web app in a browser. Every tenant either one creates is deleted when the test session
ends.
"""

import asyncio
import hashlib
import secrets
from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.engine import create_engine
from app.db.models import (
    AuditEvent,
    Department,
    Holiday,
    Location,
    Person,
    PersonPrivate,
    Tenant,
    UserSession,
)
from app.db.tenancy import TenantContext, tenant_session
from app.main import create_app
from app.modules.identity.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
```

Then add this to the end of the file:

```python
class Browser:
    """The web app in a browser, as the API sees it.

    It uses HTTPS, because a client never sends a Secure cookie over plain HTTP, and sends
    `Sec-Fetch-Site: same-origin`, as a browser does on the app's own requests. Each browser has its
    own app, database engine, and cookie jar.
    """

    def __init__(self, client: TestClient, created_tenant_ids: list[UUID]) -> None:
        self.client = client
        self._created_tenant_ids = created_tenant_ids

    def create_sandbox(self, body: object = None, **kwargs: Any) -> httpx.Response:
        """POST /sandboxes. A sandbox it creates is deleted when the test session ends."""
        response = self.client.post("/api/v1/sandboxes", json=body, **kwargs)
        if response.status_code == 201:
            self._created_tenant_ids.append(UUID(response.json()["tenant"]["id"]))
        return response

    def start_sandbox(self, persona: str | None = None) -> dict[str, Any]:
        """Create a sandbox as `persona`, or the default, and return the response body."""
        response = self.create_sandbox(None if persona is None else {"persona": persona})
        assert response.status_code == 201, response.text
        sandbox: dict[str, Any] = response.json()
        return sandbox

    @property
    def session_token(self) -> str:
        return self.client.cookies[SESSION_COOKIE]

    @property
    def csrf_token(self) -> str:
        return self.client.cookies[CSRF_COOKIE]

    @property
    def csrf(self) -> dict[str, str]:
        """The header the web app adds to every request that changes something."""
        return {CSRF_HEADER: self.csrf_token}


def session_cookie(token: str) -> dict[str, str]:
    """A Cookie header carrying `token`. It replaces the browser's own cookies for one request."""
    return {"Cookie": f"{SESSION_COOKIE}={token}"}


class OpenBrowser(Protocol):
    def __call__(self, *, same_origin_header: bool = True) -> Browser: ...


@pytest.fixture
def open_browser(
    database_settings: Settings, created_tenant_ids: list[UUID]
) -> Iterator[OpenBrowser]:
    """Open as many browsers as a test needs. Pass `same_origin_header=False` for one that sends
    no Sec-Fetch-Site, as an old browser or a script would."""
    with ExitStack() as stack:

        def open_one(*, same_origin_header: bool = True) -> Browser:
            client = TestClient(
                create_app(database_settings),
                base_url="https://testserver",
                headers={"Sec-Fetch-Site": "same-origin"} if same_origin_header else None,
            )
            return Browser(stack.enter_context(client), created_tenant_ids)

        yield open_one


@pytest.fixture
def browser(open_browser: OpenBrowser) -> Browser:
    return open_browser()


async def audit_events(engine: AsyncEngine, tenant_id: UUID) -> list[AuditEvent]:
    """Every audit event in the tenant, oldest first, read as the API's login."""
    async with tenant_session(engine, TenantContext(tenant_id, None)) as session:
        query = select(AuditEvent).order_by(AuditEvent.occurred_at)
        return list((await session.execute(query)).scalars())
```

`httpx2` is the HTTP client Starlette's `TestClient` uses here. Each browser gets its own app, so
two browsers in one test have separate engines and cookie jars.

- [ ] **Step 2: Write the failing tests** in `apps/api/tests/integration/test_api_sessions.py`

```python
"""Signing in over HTTP: sandboxes, sessions, the CSRF and same-origin checks, and their logs."""

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import JsonFormatter
from app.db.tenancy import TenantContext, tenant_session
from app.modules.identity.sessions import start_session
from app.modules.identity.tokens import hash_token
from tests.integration.conftest import (
    Browser,
    MakeTenant,
    OpenBrowser,
    audit_events,
    session_cookie,
)

pytestmark = pytest.mark.integration

ME_FIELDS = {
    "id",
    "givenName",
    "familyName",
    "title",
    "department",
    "location",
    "manager",
    "workEmail",
    "employmentType",
    "isManager",
    "isHrAdmin",
    "personaKey",
    "tenantExpiresAt",
}
SET_COOKIE = re.compile(
    r"(__Host-od_session|__Host-od_csrf)=[A-Za-z0-9_-]{43}; (HttpOnly; )?Max-Age=([0-9]+); "
    r"Path=/; SameSite=lax; Secure"
)


def security_events(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "app.security"]


def test_a_new_sandbox_signs_the_visitor_in_as_priya(browser: Browser) -> None:
    response = browser.create_sandbox()

    assert response.status_code == 201
    body = response.json()
    expires_at = datetime.fromisoformat(body["tenant"]["expiresAt"])
    assert timedelta(hours=23, minutes=59) < expires_at - datetime.now(UTC) <= timedelta(hours=24)
    assert set(body["me"]) == ME_FIELDS
    assert (body["me"]["givenName"], body["me"]["personaKey"]) == ("Priya", "priya")
    assert body["me"]["tenantExpiresAt"] == body["tenant"]["expiresAt"]


def test_both_cookies_are_set_secure_host_only_and_until_the_sandbox_expires(
    browser: Browser,
) -> None:
    response = browser.create_sandbox({"persona": "mateo"})

    cookies = [SET_COOKIE.fullmatch(header) for header in response.headers.get_list("set-cookie")]
    assert all(cookies), response.headers.get_list("set-cookie")
    named = {match[1]: match for match in cookies if match}
    assert named["__Host-od_session"][2] == "HttpOnly; "
    # The page must read the CSRF token, so that cookie is not HttpOnly.
    assert named["__Host-od_csrf"][2] is None
    assert 86_390 < int(named["__Host-od_session"][3]) < 86_400


@pytest.mark.parametrize(
    ("persona", "name", "employment_type", "is_manager", "is_hr_admin"),
    [
        ("priya", "Priya", "salaried", False, False),
        ("mateo", "Mateo", "hourly", False, False),
        ("marcus", "Marcus", "salaried", True, False),
        ("dana", "Dana", "salaried", False, True),
    ],
)
def test_each_persona_sees_their_own_card_at_me(
    browser: Browser,
    persona: str,
    name: str,
    employment_type: str,
    is_manager: bool,
    is_hr_admin: bool,
) -> None:
    created = browser.start_sandbox(persona)

    response = browser.client.get("/api/v1/me")

    me = response.json()
    assert response.status_code == 200
    assert me == created["me"]
    assert (me["givenName"], me["personaKey"], me["employmentType"]) == (
        name,
        persona,
        employment_type,
    )
    assert (me["isManager"], me["isHrAdmin"]) == (is_manager, is_hr_admin)


@pytest.mark.parametrize("persona", ["leo", "Priya", "", "admin"])
def test_only_the_four_personas_can_sign_in(browser: Browser, persona: str) -> None:
    response = browser.create_sandbox({"persona": persona})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert "__Host-od_session" not in browser.client.cookies


async def test_creating_a_sandbox_is_audited(browser: Browser, app_engine: AsyncEngine) -> None:
    sandbox = browser.start_sandbox("marcus")
    tenant_id = UUID(sandbox["tenant"]["id"])

    [event] = await audit_events(app_engine, tenant_id)

    assert (event.action, event.via, event.actor_person_id) == (
        "sandbox.created",
        "ui",
        UUID(sandbox["me"]["id"]),
    )
    assert (event.target_type, event.target_id, event.after) == (
        "tenant",
        tenant_id,
        {"personaKey": "marcus"},
    )
    assert event.request_id is not None


def test_a_new_sandbox_ends_the_session_the_browser_already_had(browser: Browser) -> None:
    first = browser.start_sandbox()
    first_token = browser.session_token

    second = browser.start_sandbox()

    assert browser.client.get("/api/v1/me", headers=session_cookie(first_token)).status_code == 401
    me = browser.client.get("/api/v1/me").json()
    assert me["id"] == second["me"]["id"] != first["me"]["id"]


def test_without_a_session_the_api_answers_401(
    browser: Browser, caplog: pytest.LogCaptureFixture
) -> None:
    responses = [
        browser.client.get("/api/v1/me"),
        browser.client.put("/api/v1/session/persona", json={"persona": "dana"}),
        browser.client.delete("/api/v1/session"),
        browser.client.get("/api/v1/me", headers=session_cookie("not-a-real-session-token")),
    ]

    assert [response.status_code for response in responses] == [401] * 4
    assert all(r.headers["content-type"] == "application/problem+json" for r in responses)
    reasons = [record.__dict__["fields"]["reason"] for record in security_events(caplog)]
    assert reasons == ["no session cookie"] * 3 + ["unknown or expired session"]


async def test_an_expired_session_is_refused(
    browser: Browser, app_engine: AsyncEngine, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant(expired=True)
    async with tenant_session(app_engine, TenantContext(tenant.id, None)) as session:
        tokens = await start_session(
            session, tenant.id, tenant.employee_id, datetime.now(UTC) - timedelta(seconds=1)
        )

    response = browser.client.get("/api/v1/me", headers=session_cookie(tokens.session))

    assert response.status_code == 401


async def test_switching_persona_issues_new_tokens_and_retires_the_old_ones(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    sandbox = browser.start_sandbox()
    old_session, old_csrf = browser.session_token, browser.csrf_token

    response = browser.client.put(
        "/api/v1/session/persona", json={"persona": "dana"}, headers=browser.csrf
    )

    assert response.status_code == 200
    assert (response.json()["personaKey"], response.json()["isHrAdmin"]) == ("dana", True)
    assert browser.session_token != old_session
    assert browser.csrf_token != old_csrf
    # The old session token is unknown now.
    assert browser.client.get("/api/v1/me", headers=session_cookie(old_session)).status_code == 401
    # The new session token with the old CSRF token can't change anything.
    stale = browser.client.put(
        "/api/v1/session/persona", json={"persona": "priya"}, headers={"X-CSRF-Token": old_csrf}
    )
    assert stale.status_code == 403
    assert browser.client.get("/api/v1/me").json()["personaKey"] == "dana"

    events = await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
    [switch] = [event for event in events if event.action == "session.persona_switched"]
    assert (switch.actor_person_id, switch.target_id) == (
        UUID(sandbox["me"]["id"]),
        UUID(response.json()["id"]),
    )
    assert (switch.before, switch.after) == ({"personaKey": "priya"}, {"personaKey": "dana"})


@pytest.mark.parametrize("csrf_token", [None, "", "not-the-csrf-token"])
def test_a_change_without_the_right_csrf_token_is_refused(
    browser: Browser, caplog: pytest.LogCaptureFixture, csrf_token: str | None
) -> None:
    sandbox = browser.start_sandbox()
    headers = {} if csrf_token is None else {"X-CSRF-Token": csrf_token}
    # The session token is valid, but it is not a CSRF token.
    wrong_kind = {"X-CSRF-Token": browser.session_token}

    for attempt in (headers, wrong_kind):
        switch = browser.client.put(
            "/api/v1/session/persona", json={"persona": "marcus"}, headers=attempt
        )
        sign_out = browser.client.delete("/api/v1/session", headers=attempt)
        assert (switch.status_code, sign_out.status_code) == (403, 403)

    assert browser.client.get("/api/v1/me").json()["personaKey"] == "priya"
    [record, *_] = security_events(caplog)
    assert record.getMessage() == "security.csrf_rejected"
    assert record.__dict__["fields"]["tenantId"] == sandbox["tenant"]["id"]
    assert record.__dict__["fields"]["actorId"] == sandbox["me"]["id"]


def test_an_unknown_persona_switch_is_refused(browser: Browser) -> None:
    browser.start_sandbox()

    response = browser.client.put(
        "/api/v1/session/persona", json={"persona": "leo"}, headers=browser.csrf
    )

    assert response.status_code == 422


async def test_signing_out_ends_the_session_and_clears_both_cookies(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    sandbox = browser.start_sandbox()
    token = browser.session_token

    response = browser.client.delete("/api/v1/session", headers=browser.csrf)

    assert response.status_code == 204
    cleared = response.headers.get_list("set-cookie")
    assert [header.split("=")[0] for header in cleared] == ["__Host-od_session", "__Host-od_csrf"]
    assert all("Max-Age=0; Path=/; SameSite=lax; Secure" in header for header in cleared)
    assert "__Host-od_session" not in browser.client.cookies
    assert browser.client.get("/api/v1/me", headers=session_cookie(token)).status_code == 401
    events = await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
    assert [event.action for event in events] == ["sandbox.created", "session.ended"]


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "https://evil.example"},
        {},
    ],
)
def test_sandbox_creation_and_session_changes_need_the_same_origin(
    open_browser: OpenBrowser, caplog: pytest.LogCaptureFixture, headers: dict[str, str]
) -> None:
    signed_in = open_browser()
    signed_in.start_sandbox()
    script = open_browser(same_origin_header=False)
    cookies = {"Cookie": f"__Host-od_session={signed_in.session_token}"}

    create = script.create_sandbox({}, headers=headers)
    switch = script.client.put(
        "/api/v1/session/persona",
        json={"persona": "dana"},
        headers={**headers, **cookies, **signed_in.csrf},
    )
    sign_out = script.client.delete("/api/v1/session", headers={**headers, **cookies})

    assert (create.status_code, switch.status_code, sign_out.status_code) == (403, 403, 403)
    assert create.json()["requestId"] == create.headers["X-Request-ID"]
    assert "set-cookie" not in create.headers
    assert [record.getMessage() for record in security_events(caplog)] == [
        "security.origin_rejected"
    ] * 3
    assert signed_in.client.get("/api/v1/me").json()["personaKey"] == "priya"


def test_the_app_origin_passes_without_fetch_metadata(open_browser: OpenBrowser) -> None:
    script = open_browser(same_origin_header=False)

    response = script.create_sandbox({}, headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 201


def test_security_events_never_contain_a_raw_token(
    open_browser: OpenBrowser, caplog: pytest.LogCaptureFixture
) -> None:
    browser = open_browser()
    browser.start_sandbox()
    session_token, csrf_token = browser.session_token, browser.csrf_token
    cross_site = open_browser(same_origin_header=False)

    # One of each event this stage logs: a bad CSRF token, a cross-site change, and an unknown
    # session. Each carries the real session token in its cookie.
    browser.client.delete("/api/v1/session", headers={"X-CSRF-Token": "wrong"})
    cross_site.client.delete(
        "/api/v1/session",
        headers={"Sec-Fetch-Site": "cross-site", **session_cookie(session_token)},
    )
    browser.client.delete("/api/v1/session", headers=browser.csrf)
    browser.client.get("/api/v1/me", headers=session_cookie(session_token))

    records = security_events(caplog)
    lines = [JsonFormatter().format(record) for record in records]
    assert [json.loads(line)["event"] for line in lines] == [
        "security.csrf_rejected",
        "security.origin_rejected",
        "security.session_invalid",
    ]
    prefix = hash_token(session_token).hex()[:8]
    for line in lines:
        entry = json.loads(line)
        assert session_token not in line
        assert csrf_token not in line
        assert entry["tokenHashPrefix"] == prefix
        assert entry["clientIp"] == "testclient"
        assert entry["requestId"]
```

- [ ] **Step 3: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/integration/test_api_sessions.py -q`
Expected: `26 failed`. No route exists yet, so every request gets a 404, and most tests fail with
`assert 404 == 201` when they try to create a sandbox.

- [ ] **Step 4: Create `apps/api/app/modules/people/queries.py`.** Stage 4 adds the directory
      list, a single card, and the private details.

```python
"""Reading people, inside the caller's tenant-scoped transaction.

Row-level security limits every query here to the actor's tenant. These functions add no tenant
filter of their own, and they never decide who may see what.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Row, Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import Department, Location, Person
from app.modules.people.schemas import DepartmentRef, LocationRef, Me, PersonRef
from app.policy import Actor

_Manager = aliased(Person, name="manager")


def _cards() -> Select[*tuple[Any, ...]]:
    """Exactly the columns a directory card shows, and nothing else of the person's."""
    return (
        select(
            Person.id,
            Person.given_name,
            Person.family_name,
            Person.title,
            Person.work_email,
            Department.id.label("department_id"),
            Department.name.label("department_name"),
            Location.id.label("location_id"),
            Location.name.label("location_name"),
            Location.state.label("location_state"),
            _Manager.id.label("manager_id"),
            _Manager.given_name.label("manager_given_name"),
            _Manager.family_name.label("manager_family_name"),
        )
        .join(Department, Department.id == Person.department_id)
        .join(Location, Location.id == Person.location_id)
        .outerjoin(_Manager, _Manager.id == Person.manager_id)
    )


def _card_fields(row: Row[Any]) -> dict[str, Any]:
    """A directory card's fields, from one row of `_cards()`."""
    manager = None
    if row.manager_id is not None:
        manager = PersonRef(
            id=row.manager_id,
            given_name=row.manager_given_name,
            family_name=row.manager_family_name,
        )
    return {
        "id": row.id,
        "given_name": row.given_name,
        "family_name": row.family_name,
        "title": row.title,
        "department": DepartmentRef(id=row.department_id, name=row.department_name),
        "location": LocationRef(
            id=row.location_id, name=row.location_name, state=row.location_state
        ),
        "manager": manager,
        "work_email": row.work_email,
    }


async def get_me(session: AsyncSession, actor: Actor, tenant_expires_at: datetime) -> Me:
    """The actor's own card, with the fields only they see."""
    query = _cards().add_columns(Person.employment_type, Person.persona_key)
    row = (await session.execute(query.where(Person.id == actor.person_id))).one()
    return Me(
        **_card_fields(row),
        employment_type=row.employment_type,
        is_manager=actor.is_manager,
        is_hr_admin=actor.is_hr_admin,
        persona_key=row.persona_key,
        tenant_expires_at=tenant_expires_at,
    )
```

- [ ] **Step 5: Create `apps/api/app/modules/identity/deps.py`**

```python
"""The dependencies a signed-in route uses: the session, the CSRF check, and the actor.

For each request:

1. The `__Host-od_session` cookie is hashed and looked up. A missing, unknown, or expired session
   is a 401.
2. A request that changes state must also echo the CSRF token in X-CSRF-Token, matching the
   session's hash in constant time, or it gets a 403. Every session-bound route gets this check,
   with nothing to remember.
3. One transaction opens, scoped to the session's tenant and person. The actor is loaded in it,
   with their reports fresh from the database, and the HR flag is set for the private-details rule.
4. The route runs in that transaction, which commits before the response is sent, and only if the
   route succeeded.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.deps import get_engine
from app.db.tenancy import NO_TENANT, TenantContext, set_is_hr, tenant_session
from app.modules.identity.actor import load_actor
from app.modules.identity.cookies import CSRF_HEADER, SESSION_COOKIE
from app.modules.identity.security_log import SecurityEvent, log_security_event
from app.modules.identity.sessions import SessionRecord, find_session
from app.modules.identity.tokens import hash_token, token_matches
from app.policy import Actor

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

NOT_SIGNED_IN = "There is no current session. Start a sandbox to sign in."


@dataclass(frozen=True, slots=True)
class SignedIn:
    """What a signed-in route works with: the actor, and the request's one transaction."""

    actor: Actor
    db: AsyncSession
    session: SessionRecord


async def current_session(
    request: Request, engine: Annotated[AsyncEngine, Depends(get_engine)]
) -> SessionRecord:
    """The request's live session, after the CSRF check if the request changes state."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        log_security_event(SecurityEvent.SESSION_INVALID, request, "no session cookie")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)
    # The sessions table has no row-level security, so the lookup needs no tenant.
    async with tenant_session(engine, NO_TENANT) as db:
        record = await find_session(db, hash_token(token))
    if record is None:
        log_security_event(SecurityEvent.SESSION_INVALID, request, "unknown or expired session")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)
    if request.method not in SAFE_METHODS and not token_matches(
        request.headers.get(CSRF_HEADER), record.csrf_hash
    ):
        log_security_event(
            SecurityEvent.CSRF_REJECTED,
            request,
            "X-CSRF-Token is missing or wrong",
            tenant_id=record.tenant_id,
            actor_id=record.person_id,
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The CSRF token is missing or wrong.")
    return record


async def signed_in(
    request: Request,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    record: Annotated[SessionRecord, Depends(current_session)],
) -> AsyncIterator[SignedIn]:
    context = TenantContext(record.tenant_id, record.person_id)
    async with tenant_session(engine, context) as db:
        actor = await load_actor(db, record.tenant_id, record.person_id)
        if actor is None:
            # Only if the sandbox was deleted between the session lookup and now.
            log_security_event(SecurityEvent.SESSION_INVALID, request, "the sandbox is gone")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)
        await set_is_hr(db, actor.is_hr_admin)
        yield SignedIn(actor, db, record)


# scope="function" ends the dependency, and so commits the transaction, before the response is
# sent. A failed commit is then a 500, not a success the client was already told about.
SignedInDep = Annotated[SignedIn, Depends(signed_in, scope="function")]
```

- [ ] **Step 6: Create `apps/api/app/modules/identity/routes.py`**

```python
"""Who am I, switching persona, and signing out."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.schemas import CamelModel
from app.db.models import Person
from app.modules.audit.service import record_event
from app.modules.identity.actor import load_actor
from app.modules.identity.cookies import clear_session_cookies, set_session_cookies
from app.modules.identity.deps import SignedInDep
from app.modules.identity.sessions import end_session, rotate_session
from app.modules.people.queries import get_me
from app.modules.people.schemas import Me, PersonaKey

router = APIRouter(tags=["session"])


class PersonaChoice(CamelModel):
    persona: PersonaKey


@router.get(
    "/me",
    operation_id="getMe",
    summary="The signed-in person's own card, and when their sandbox expires",
    response_model=Me,
)
async def get_current_person(signed_in: SignedInDep) -> Me:
    return await get_me(signed_in.db, signed_in.actor, signed_in.session.expires_at)


@router.put(
    "/session/persona",
    operation_id="switchPersona",
    summary="Sign in as another persona in the same sandbox, with new session and CSRF tokens",
    response_model=Me,
)
async def switch_persona(choice: PersonaChoice, signed_in: SignedInDep, response: Response) -> Me:
    db, actor, current = signed_in.db, signed_in.actor, signed_in.session
    person_id = await db.scalar(select(Person.id).where(Person.persona_key == choice.persona))
    new_actor = None if person_id is None else await load_actor(db, actor.tenant_id, person_id)
    if new_actor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This sandbox has no such persona.")
    switching_from = await db.scalar(select(Person.persona_key).where(Person.id == actor.person_id))
    tokens = await rotate_session(db, current, new_actor.person_id)
    await record_event(
        db,
        tenant_id=actor.tenant_id,
        actor_id=actor.person_id,
        action="session.persona_switched",
        target_type="person",
        target_id=new_actor.person_id,
        before={"personaKey": switching_from},
        after={"personaKey": choice.persona},
    )
    set_session_cookies(response, tokens, current.expires_at)
    return await get_me(db, new_actor, current.expires_at)


@router.delete(
    "/session",
    operation_id="endSession",
    summary="Sign out: end the session and clear its cookies",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def sign_out(signed_in: SignedInDep, response: Response) -> None:
    await end_session(signed_in.db, signed_in.session.token_hash)
    await record_event(
        signed_in.db,
        tenant_id=signed_in.actor.tenant_id,
        actor_id=signed_in.actor.person_id,
        action="session.ended",
    )
    clear_session_cookies(response)
```

- [ ] **Step 7: Create `apps/api/app/modules/sandbox/service.py`**

```python
"""Creating a sandbox: a new company, seeded, with the visitor signed in as one of its personas."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import Tenant
from app.db.tenancy import TenantContext, tenant_session
from app.modules.audit.service import record_event
from app.modules.identity.actor import load_actor
from app.modules.identity.sessions import end_session, start_session
from app.modules.identity.tokens import SessionTokens
from app.modules.people.queries import get_me
from app.modules.people.schemas import Me, PersonaKey
from app.modules.sandbox.seed import build_company, insert_company

# A sandbox, and every session in it, is deleted 24 hours after it is created (ADR 0007).
SANDBOX_LIFETIME = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class NewSandbox:
    tenant_id: UUID
    expires_at: datetime
    tokens: SessionTokens
    me: Me


async def create_sandbox(
    engine: AsyncEngine, persona: PersonaKey, replacing: bytes | None
) -> NewSandbox:
    """Create and seed a sandbox, and start a session in it as `persona`, in one transaction.

    `replacing` is the token hash of a session the visitor already had, which is deleted in the
    same transaction: each sandbox creation leaves the browser with exactly one session.
    """
    tenant_id = uuid4()
    created_at = datetime.now(UTC)
    expires_at = created_at + SANDBOX_LIFETIME
    company = build_company(tenant_id, created_at.date())
    person_id = next(person.id for person in company.people if person.persona_key == persona)
    async with tenant_session(engine, TenantContext(tenant_id, person_id)) as db:
        if replacing is not None:
            await end_session(db, replacing)
        await db.execute(
            insert(Tenant).values(
                id=tenant_id, expires_at=expires_at, anchor_date=company.anchor_date
            )
        )
        await insert_company(db, company)
        tokens = await start_session(db, tenant_id, person_id, expires_at)
        await record_event(
            db,
            tenant_id=tenant_id,
            actor_id=person_id,
            action="sandbox.created",
            target_type="tenant",
            target_id=tenant_id,
            after={"personaKey": persona},
        )
        actor = await load_actor(db, tenant_id, person_id)
        if actor is None:
            msg = f"The seed company has no {persona!r} persona"
            raise RuntimeError(msg)
        me = await get_me(db, actor, expires_at)
    return NewSandbox(tenant_id, expires_at, tokens, me)
```

- [ ] **Step 8: Create `apps/api/app/modules/sandbox/routes.py`**

```python
"""POST /api/v1/sandboxes: start a new sandbox company and sign in to it."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import get_engine
from app.api.schemas import CamelModel
from app.modules.identity.cookies import SESSION_COOKIE, set_session_cookies
from app.modules.identity.tokens import hash_token
from app.modules.people.schemas import Me, PersonaKey
from app.modules.sandbox.service import create_sandbox

router = APIRouter(tags=["sandboxes"])


class NewSandboxRequest(CamelModel):
    persona: PersonaKey = "priya"


class TenantInfo(CamelModel):
    id: UUID
    expires_at: datetime


class SandboxCreated(CamelModel):
    tenant: TenantInfo
    me: Me


@router.post(
    "/sandboxes",
    operation_id="createSandbox",
    summary="Start a new sandbox company and sign in to it as one of its personas",
    status_code=status.HTTP_201_CREATED,
    response_model=SandboxCreated,
)
async def post_sandbox(
    request: Request,
    response: Response,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    body: NewSandboxRequest | None = None,
) -> SandboxCreated:
    # The same-origin check has already run. There is no CSRF token to check: a visitor without a
    # session has none, and this creates the session.
    persona = body.persona if body is not None else "priya"
    current = request.cookies.get(SESSION_COOKIE)
    sandbox = await create_sandbox(engine, persona, hash_token(current) if current else None)
    set_session_cookies(response, sandbox.tokens, sandbox.expires_at)
    return SandboxCreated(
        tenant=TenantInfo(id=sandbox.tenant_id, expires_at=sandbox.expires_at), me=sandbox.me
    )
```

- [ ] **Step 9: Replace `apps/api/app/api/v1/router.py`**

```python
"""Every version 1 endpoint, mounted under /api/v1."""

from fastapi import APIRouter

from app.api.v1 import health
from app.modules.identity import routes as identity
from app.modules.sandbox import routes as sandbox

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(sandbox.router)
api_router.include_router(identity.router)
```

- [ ] **Step 10: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/integration/test_api_sessions.py -q`
Expected: `26 passed`.

- [ ] **Step 11: Prove the request ID wraps the same-origin check, then undo.** In
      `apps/api/app/main.py`, swap the two `app.add_middleware(...)` lines, so the same-origin
      check is added last.

Run: `cd apps/api && uv run pytest tests/integration/test_api_sessions.py -q`
Expected: `5 failed, 21 passed`. The four same-origin cases fail with `KeyError: 'requestId'`,
because a refusal no longer passes through the request-ID middleware. The raw-token test fails
too: its `origin_rejected` line has no request ID. Swap the lines back.

- [ ] **Step 12: Prove the CSRF tests need the check, then undo.** In
      `apps/api/app/modules/identity/deps.py`, replace `request.method not in SAFE_METHODS` with
      `request.method == "TRACE"`, which no route accepts.

Run: `cd apps/api && uv run pytest tests/integration/test_api_sessions.py -q`
Expected: `5 failed, 21 passed`: the three wrong-token cases, the persona switch (its old CSRF
token is accepted), and the raw-token test, which no longer sees a `csrf_rejected` event.
Restore the line.

- [ ] **Step 13: Run the API checks**

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
Expected: `All checks passed!`, `79 files already formatted`,
`Success: no issues found in 79 source files`, `Domain and policy code import no framework KEPT`,
and `217 passed`. That is 140 unit tests and 77 database tests.

Run: `cd apps/api && uv run python scripts/export_openapi.py --check`
Expected: exit status 1, and `apps/web/openapi.json is out of date.` Task 21 regenerates it.

### Task 21: Regenerate the schema and the web client

**Files:**
- Generated: `apps/web/openapi.json`, `apps/web/src/api/generated.ts`

- [ ] **Step 1: Regenerate both**

Run: `make openapi`
Expected: `Wrote apps/web/openapi.json`, then orval's success line for `src/api/generated.ts`.
The schema gains `POST /api/v1/sandboxes` (`createSandbox`), `GET /api/v1/me` (`getMe`),
`PUT /api/v1/session/persona` (`switchPersona`), and `DELETE /api/v1/session` (`endSession`),
and the client exports `useCreateSandbox`, `useGetMe`, `useSwitchPersona`, and `useEndSession`.
Nothing in the web app uses them yet.

- [ ] **Step 2: Run the web checks and the schema check**

Run: `make check-web && cd apps/api && uv run python scripts/export_openapi.py --check`
Expected: every web check passes: lint, formatting, types, `6 passed`, the build, and
`src/api/generated.ts is up to date with openapi.json.` Then
`apps/web/openapi.json is up to date.`

### Task 22: Close Stage 3

**Files:**
- Modify: `CHANGELOG.md`, `docs/ROADMAP.md`, `docs/BACKLOG.md`

- [ ] **Step 1: Add to `CHANGELOG.md` under `## [Unreleased]` → `### Added`,** after the stage 2
      entry

```markdown
- **Signing in** (Phase 1, stage 3). A visitor can now start a sandbox company and sign in to it
  as one of four personas: Priya, Mateo, Marcus, or Dana. The session lives in a cookie the page's
  scripts can't read, and it ends when the sandbox does, 24 hours after it was created. Every
  request that changes something must come from the app itself, and a signed-in one must also
  carry a CSRF token (a second secret that another website can't read), so no other site can act
  on a visitor's behalf. Also added:
  - Four endpoints. `POST /api/v1/sandboxes` creates and seeds a sandbox and signs the visitor
    in. `GET /api/v1/me` says who is signed in. `PUT /api/v1/session/persona` switches persona and
    replaces both tokens, so the old ones stop working at once. `DELETE /api/v1/session` signs
    out.
  - The policy layer: one pure function, `can()`, that decides who may see what, and refuses
    anything it has no rule for. Like the domain rules, it may not import any framework or
    database code, which the import check enforces.
  - An audit log entry for each sandbox created, persona switched, and session ended. Every
    refused request goes to a security log instead: a missing or expired session, a request from
    another site, or a wrong CSRF token. No log ever holds a raw token.
  - The web app's generated API client now includes these endpoints. The screens start using them
    in Phase 2.

  This closes the backlog item to keep the health check open: it reads no session, and the
  same-origin and CSRF checks apply only to requests that change something.
```

- [ ] **Step 2: Update `docs/ROADMAP.md`.** Replace the Phase 1 row of the status table with this
      one, using today's date and the first two stages' pull request numbers:

```markdown
| 1 Tenancy, identity, permissions | In progress: stage 3 of 4 (sessions and signing in) | `feat/phase-1-sessions` | [#<stage 1 PR number>](https://github.com/musicteachj/open-door/pull/<stage 1 PR number>), [#<stage 2 PR number>](https://github.com/musicteachj/open-door/pull/<stage 2 PR number>) | [phase 1 plan](plans/2026-10-03-phase-1-tenancy-identity-permissions.md) | <today> |
```

- [ ] **Step 3: In `docs/BACKLOG.md`, delete the Phase 1 item about exempting the health
      check** from authentication and CSRF. The changelog entry records why it's done. Stage 4
      moves the section's other item.

- [ ] **Step 4: Run `make check` (with `make db` first)**

Run: `make db && make check`
Expected: every check passes.
- `check-api` ends with `217 passed`, `No new upgrade operations detected.`, and
  `apps/web/openapi.json is up to date.`
- `check-web` passes, ending with `src/api/generated.ts is up to date with openapi.json.`
- `check-docs` reports `0 Errors`, with no placeholders printed.
- zizmor reports `No findings to report`.

While planning, `make check` passed in the scratch clone with these three documents edited.
`make db` itself wasn't run, because it starts the Compose database. Its migrate and bootstrap
commands were run.

- [ ] **Step 5: Run `/code-review medium` on the whole branch against `dev`,** committed and
      uncommitted work together, and fix anything real it finds. Re-run `make check` after any
      fix.

- [ ] **Step 6: Propose the commit and PR, and wait for the owner's OK.** Commit message:

```
Let visitors start a sandbox and sign in as a persona

A visitor can now create a sandbox company and sign in to it as Priya,
Mateo, Marcus, or Dana, switch persona, and sign out. The session
lives in a cookie the page's scripts can't read, and it ends with the
sandbox, 24 hours after it was created.

Every request that changes something must come from the app itself.
A signed-in one must also echo a CSRF token, a second secret that
another website can't read, so no other site can act on a visitor's
behalf. Switching persona replaces both tokens, so the old ones stop
working at once.

One pure function now decides who may see what, and refuses anything
it has no rule for. Each sandbox created, persona switched, and
session ended is written to the audit log, and every refused request
goes to a security log that never holds a raw token. This is stage 3
of 4 for Phase 1. The directory endpoints come next.
```

- [ ] **Step 7: With the owner's OK, push and open the PR into `dev`.** Title: "Let visitors start
      a sandbox and sign in as a persona". Body:

```markdown
## What this does
Adds signing in. `POST /api/v1/sandboxes` creates and seeds a sandbox and starts a session for
one of the four personas. `GET /api/v1/me` says who is signed in, `PUT /api/v1/session/persona`
switches persona with fresh tokens, and `DELETE /api/v1/session` signs out. The session lives in
an `HttpOnly` `__Host-` cookie. Every request that changes something passes a same-origin check,
and a signed-in one also needs its CSRF token. The policy layer, one pure function called
`can()`, arrives too, along with audit events for these actions and a security log for every
refused request.

## Why
Phase 1 promises that the permission matrix and tenant isolation are proven over HTTP, with real
cookies and CSRF checks, so Phase 2 only has to build screens. This is stage 3 of 4. The spec
planned three stages, but the last one came to about 2,400 lines, so it is split in two.

## How it was checked
`make check` passes, with 217 API tests, 77 of them against the real database. The HTTP tests
sign in as each persona, switch persona and show that both old tokens are refused, try every
same-origin and CSRF failure, and check that no security log line holds a raw token. Each guard
was shown to fail its tests when it was removed or misordered. While planning, the cookies were
also checked in headless Chrome over `http://localhost`, through the Vite proxy: 201, 200, 200.

## What to look at
- The middleware order in `create_app`, and why the request ID must stay outermost.
- The signed-in dependency in `app/modules/identity/deps.py`: the CSRF check, the two
  transactions, and `scope="function"`, which commits before the response is sent.
- What each audit event records, in `app/modules/audit/service.py` and the routes.
```

- [ ] **Step 8: Confirm the pull request's checks are green**

Run: `gh pr checks <stage 3 PR number> --repo musicteachj/open-door --watch`
Expected: CI (Detect what changed, API, Web, Docs, Workflows), Security, and Changelog all pass.
This PR changes `ci.yml` and the web app's generated client, so both the API and Web jobs run,
and the API job's import step is now named "Domain and policy code import no framework".

---

# Stage 4: The directory, and closing Phase 1

**Branch:** `feat/phase-1-directory-api`, off `dev` after Stage 3 merges.
**Ends with:** a signed-in persona can page through the company directory, read anyone's
directory card, and read private details where the policy layer allows: their own, or anyone's
for HR. The permission matrix and tenant isolation are proven over HTTP for every persona. Each
read of private details is audited by field name. `docs/DATA-INVENTORY.md` lists every table and
column, and the backlog holds the later-phase findings with their sources. `make check-api`
passes with 260 tests, 110 of them against the real database, and Phase 1 is done.

> **Before you start:** run `make db`. The new tests sign in over HTTP against real sandboxes.

## Decisions made while planning this stage

Every code block below is the exact final content of a file that was run in a scratch clone on
2026-10-03, and every "Expected" is the output it produced. Where a task changes part of a file,
the block is the exact text of that part. The versions are the same as Stage 3's.

- **The policy layer answers before any lookup.** A persona who isn't HR gets a 403 for anyone's
  private details but their own, whether that person exists or not, so a refusal never reveals
  who exists. A person from another sandbox is a 404 wherever the policy allows the read: in the
  directory for everyone, and for private details as HR. Row-level security makes that person
  look exactly like an ID that exists nowhere.
- **The database's own rule backs up the policy layer, and a test shows it.** Task 24 changes
  `can()` to let managers read their reports' private details. The unit matrix fails, and so does
  the HTTP matrix. Over HTTP, Marcus gets a 404 for Leo's details, not a 200, because the
  database's private-details rule still hides the row.
- **The directory cursor is opaque but not signed.** It is the base64 of the last card's family
  name, given name, and ID. A changed cursor can only move where the page starts inside the
  actor's own sandbox, so signing it would protect nothing. Anything that isn't three strings
  with a valid UUID gets a 422.
- **The list asks the policy layer about each card.** Every directory read is allowed in Phase 1,
  but filtering the page through `can()` means a future rule applies to the list too. The next
  cursor comes from the last row read, not the last card returned, so paging stays correct even
  when cards are filtered out.
- **The card queries select only the card's columns,** so a field that isn't on the card can't
  slip into a response by way of the query.
- **The data inventory's 4-year figure was checked against the statute, as the spec asked.**
  California Government Code §12946(a) requires employers to keep personnel and employment
  records for 4 years. The Civil Rights Council's Final Statement of Reasons for the
  automated-decision rules confirms that §11013(c) applies that period to their data. The adopted
  text itself is a scanned PDF with no text to quote, so the statute is the primary source.
  > Source: California Government Code §12946(a), as amended by SB 807 (Stats. 2021, ch. 278),
  > read from leginfo.legislature.ca.gov on 2026-10-03.
  >
  > Source: Civil Rights Council, Final Statement of Reasons for the employment regulations
  > regarding automated-decision systems (June 2025), read from calcivilrights.ca.gov on
  > 2026-10-03.
- **The Article 50 date was checked too.** Article 50 of the EU AI Act is in Chapter IV, and
  Article 113 applies everything not listed as an exception from 2 August 2026.
  > Source: EU AI Act Article 113, https://artificialintelligenceact.eu/article/113/, read on
  > 2026-10-03. That site is an unofficial consolidation, not EUR-Lex.
- **The backlog after Phase 1:**
  - Stage 3 closed the health check item.
  - "Don't run Alembic inside an async test" is still good advice, because a later test that runs
    migrations would hit it, so it moves to a new "Any phase" section.
  - Two findings from building this phase join the spec's list. Phase 2 should declare the error
    responses in the OpenAPI schema. Phase 8 should read the client's IP address through the
    load balancer, since the security log records the connecting address.
- **`CLAUDE.md` gains a rule to keep the data inventory current,** and the README links to it, as
  it does to every document.
- **Phase 1 closes with four pull requests,** so the roadmap's Done row lists four.
- **Stage 4 is about 760 lines:** 234 of code, 269 of tests, and 254 in the docs. The
  regenerated schema and client add another 750 generated lines.

### Task 23: The directory queries and private details

**Files:**
- Modify: `apps/api/app/modules/people/queries.py`, `apps/api/app/modules/people/schemas.py`
- Test: `apps/api/tests/test_people_schemas.py`

- [ ] **Step 1: Replace `apps/api/tests/test_people_schemas.py`** with the tests for the private
      details and the directory cursor added

```python
"""Each tier of what the API shows about a person has exactly its own fields, in camelCase."""

import base64
import json
from uuid import uuid4

import pytest

from app.modules.people.queries import DirectoryCursor
from app.modules.people.schemas import DirectoryCard, Me, PrivateDetails

CARD_FIELDS = {
    "id",
    "givenName",
    "familyName",
    "title",
    "department",
    "location",
    "manager",
    "workEmail",
}
ME_ONLY_FIELDS = {"employmentType", "isManager", "isHrAdmin", "personaKey", "tenantExpiresAt"}
PRIVATE_FIELDS = {"personalEmail", "phone", "homeAddress", "dateOfBirth"}


def json_fields(model: type[DirectoryCard] | type[PrivateDetails]) -> set[str]:
    return set(model.model_json_schema(by_alias=True)["properties"])


def encoded(key: object) -> str:
    """A key encoded the way a real cursor is, so only its content is wrong."""
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode().rstrip("=")


def test_the_directory_card_has_none_of_the_me_only_or_private_fields() -> None:
    assert json_fields(DirectoryCard) == CARD_FIELDS
    assert json_fields(DirectoryCard).isdisjoint(ME_ONLY_FIELDS | PRIVATE_FIELDS)


def test_me_adds_only_the_me_only_fields() -> None:
    assert json_fields(Me) == CARD_FIELDS | ME_ONLY_FIELDS


def test_private_details_are_a_separate_model() -> None:
    assert json_fields(PrivateDetails) == PRIVATE_FIELDS
    assert not issubclass(PrivateDetails, DirectoryCard)


def test_a_directory_cursor_comes_back_as_it_went_out() -> None:
    cursor = DirectoryCursor("O'Brien", "Zoë", uuid4())

    assert DirectoryCursor.decode(cursor.encode()) == cursor


@pytest.mark.parametrize(
    "garbage",
    [
        "",
        "not-a-cursor",
        encoded([]),
        encoded(["Abbott", "Mina"]),
        encoded([1, 2, 3]),
        encoded(["Abbott", "Mina", 3]),
        encoded(["Abbott", "Mina", "not-a-uuid"]),
        encoded({"family": "Abbott", "given": "Mina", "id": "x"}),
    ],
)
def test_a_cursor_the_api_did_not_issue_is_refused(garbage: str) -> None:
    with pytest.raises(ValueError, match="Not a directory cursor"):
        DirectoryCursor.decode(garbage)
```

`encoded` builds each bad cursor the way a real one is built, so only its content is wrong.

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/test_people_schemas.py -q`
Expected: a collection error,
`ImportError: cannot import name 'DirectoryCursor' from 'app.modules.people.queries'`.

- [ ] **Step 3: Replace `apps/api/app/modules/people/schemas.py`**

```python
"""What the API shows of a person. Each tier is its own model, so a field can't leak between them.

- `DirectoryCard` is what anyone in the company may see.
- `Me` adds what only the signed-in person sees about themselves.
- `PrivateDetails` is visible only to the person themselves and to HR.
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from app.api.schemas import CamelModel

type PersonaKey = Literal["priya", "mateo", "marcus", "dana"]


class DepartmentRef(CamelModel):
    id: UUID
    name: str


class LocationRef(CamelModel):
    id: UUID
    name: str
    state: str


class PersonRef(CamelModel):
    id: UUID
    given_name: str
    family_name: str


class DirectoryCard(CamelModel):
    id: UUID
    given_name: str
    family_name: str
    title: str
    department: DepartmentRef
    location: LocationRef
    manager: PersonRef | None
    work_email: str


class DirectoryPage(CamelModel):
    items: list[DirectoryCard]
    # Pass it back as `cursor` for the next page. Null on the last page.
    next_cursor: str | None


class Me(DirectoryCard):
    """The signed-in person's own card, with the fields only they see."""

    employment_type: Literal["salaried", "hourly"]
    is_manager: bool
    is_hr_admin: bool
    persona_key: PersonaKey
    tenant_expires_at: datetime


class PrivateDetails(CamelModel):
    personal_email: str
    phone: str
    home_address: str
    date_of_birth: date
```

- [ ] **Step 4: Replace `apps/api/app/modules/people/queries.py`**

```python
"""Reading people, inside the caller's tenant-scoped transaction.

Row-level security limits every query here to the actor's tenant, and the private-details rule
limits `person_private` to the person themselves and HR. These functions add no tenant filter of
their own, and they never decide who may see what: the routes ask the policy layer first.
"""

import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, Select, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import Department, Location, Person, PersonPrivate
from app.modules.people.schemas import (
    DepartmentRef,
    DirectoryCard,
    LocationRef,
    Me,
    PersonRef,
    PrivateDetails,
)
from app.policy import Actor

_Manager = aliased(Person, name="manager")

# The directory's order, which the cursor continues from. The index on
# (tenant_id, family_name, given_name, id) serves it.
_DIRECTORY_ORDER = (Person.family_name, Person.given_name, Person.id)


@dataclass(frozen=True, slots=True)
class DirectoryCursor:
    """Where the next page starts: just after this person in the directory's order."""

    family_name: str
    given_name: str
    person_id: UUID

    def encode(self) -> str:
        """Opaque to the client: base64 of the sort key. It reveals nothing a card doesn't."""
        key = json.dumps([self.family_name, self.given_name, str(self.person_id)])
        return base64.urlsafe_b64encode(key.encode()).decode().rstrip("=")

    @classmethod
    def decode(cls, cursor: str) -> "DirectoryCursor":
        """Raises ValueError for anything this API didn't issue."""
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            key = json.loads(raw)
            if not (isinstance(key, list) and all(isinstance(part, str) for part in key)):
                raise TypeError
            family_name, given_name, person_id = key
            return cls(family_name, given_name, UUID(person_id))
        except (binascii.Error, UnicodeDecodeError, TypeError, ValueError) as exc:
            msg = "Not a directory cursor"
            raise ValueError(msg) from exc


@dataclass(frozen=True, slots=True)
class DirectoryResult:
    """One page of cards, and where the next page starts, if there is one."""

    cards: list[DirectoryCard]
    next_cursor: DirectoryCursor | None


def _cards() -> Select[*tuple[Any, ...]]:
    """Exactly the columns a directory card shows, and nothing else of the person's."""
    return (
        select(
            Person.id,
            Person.given_name,
            Person.family_name,
            Person.title,
            Person.work_email,
            Department.id.label("department_id"),
            Department.name.label("department_name"),
            Location.id.label("location_id"),
            Location.name.label("location_name"),
            Location.state.label("location_state"),
            _Manager.id.label("manager_id"),
            _Manager.given_name.label("manager_given_name"),
            _Manager.family_name.label("manager_family_name"),
        )
        .join(Department, Department.id == Person.department_id)
        .join(Location, Location.id == Person.location_id)
        .outerjoin(_Manager, _Manager.id == Person.manager_id)
    )


def _card_fields(row: Row[Any]) -> dict[str, Any]:
    """A directory card's fields, from one row of `_cards()`."""
    manager = None
    if row.manager_id is not None:
        manager = PersonRef(
            id=row.manager_id,
            given_name=row.manager_given_name,
            family_name=row.manager_family_name,
        )
    return {
        "id": row.id,
        "given_name": row.given_name,
        "family_name": row.family_name,
        "title": row.title,
        "department": DepartmentRef(id=row.department_id, name=row.department_name),
        "location": LocationRef(
            id=row.location_id, name=row.location_name, state=row.location_state
        ),
        "manager": manager,
        "work_email": row.work_email,
    }


async def list_directory(
    session: AsyncSession, *, limit: int, after: DirectoryCursor | None
) -> DirectoryResult:
    """One page of the directory, ordered by family name, given name, then ID."""
    query = _cards().order_by(*_DIRECTORY_ORDER).limit(limit + 1)
    if after is not None:
        query = query.where(
            tuple_(*_DIRECTORY_ORDER) > tuple_(after.family_name, after.given_name, after.person_id)
        )
    rows: Sequence[Row[Any]] = (await session.execute(query)).all()
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = page[-1]
        next_cursor = DirectoryCursor(last.family_name, last.given_name, last.id)
    return DirectoryResult([DirectoryCard(**_card_fields(row)) for row in page], next_cursor)


async def get_card(session: AsyncSession, person_id: UUID) -> DirectoryCard | None:
    row = (await session.execute(_cards().where(Person.id == person_id))).one_or_none()
    return None if row is None else DirectoryCard(**_card_fields(row))


async def get_me(session: AsyncSession, actor: Actor, tenant_expires_at: datetime) -> Me:
    """The actor's own card, with the fields only they see."""
    query = _cards().add_columns(Person.employment_type, Person.persona_key)
    row = (await session.execute(query.where(Person.id == actor.person_id))).one()
    return Me(
        **_card_fields(row),
        employment_type=row.employment_type,
        is_manager=actor.is_manager,
        is_hr_admin=actor.is_hr_admin,
        persona_key=row.persona_key,
        tenant_expires_at=tenant_expires_at,
    )


async def get_private_details(session: AsyncSession, person_id: UUID) -> PrivateDetails | None:
    """The person's private details, or None if the private-details rule hides them.

    Only a SELECT: the rule applies to reads, so a RETURNING on this table would be refused too.
    """
    query = select(
        PersonPrivate.personal_email,
        PersonPrivate.phone,
        PersonPrivate.home_address,
        PersonPrivate.date_of_birth,
    ).where(PersonPrivate.person_id == person_id)
    row = (await session.execute(query)).one_or_none()
    if row is None:
        return None
    return PrivateDetails(
        personal_email=row.personal_email,
        phone=row.phone,
        home_address=row.home_address,
        date_of_birth=row.date_of_birth,
    )
```

- [ ] **Step 5: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/test_people_schemas.py -q`
Expected: `12 passed`.

- [ ] **Step 6: Run the API checks.** No route uses the new code yet, so the schema doesn't
      change.

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q && uv run python scripts/export_openapi.py --check`
Expected: `All checks passed!`, `79 files already formatted`,
`Success: no issues found in 79 source files`, `Domain and policy code import no framework KEPT`,
`227 passed`, and `apps/web/openapi.json is up to date.`

### Task 24: The people endpoints

**Files:**
- Create: `apps/api/app/modules/people/routes.py`
- Modify: `apps/api/app/modules/identity/deps.py`, `apps/api/app/api/v1/router.py`
- Test: `apps/api/tests/integration/test_api_people.py`

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/integration/test_api_people.py`

```python
"""The directory and private details over HTTP: the permission matrix, isolation, and paging."""

import logging
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import JsonFormatter
from tests.integration.conftest import Browser, OpenBrowser, audit_events

pytestmark = pytest.mark.integration

CARD_FIELDS = {
    "id",
    "givenName",
    "familyName",
    "title",
    "department",
    "location",
    "manager",
    "workEmail",
}
PRIVATE_FIELDS = {"personalEmail", "phone", "homeAddress", "dateOfBirth"}
ME_ONLY_FIELDS = {"employmentType", "isManager", "isHrAdmin", "personaKey", "tenantExpiresAt"}

# Each persona against themselves, Leo (one of Marcus's reports), and Dana (HR). Marcus is Leo's
# manager, and still may not read his private details.
PRIVATE_MATRIX = {
    ("priya", "self"): 200,
    ("priya", "leo"): 403,
    ("priya", "dana"): 403,
    ("mateo", "self"): 200,
    ("mateo", "leo"): 403,
    ("mateo", "dana"): 403,
    ("marcus", "self"): 200,
    ("marcus", "leo"): 403,
    ("marcus", "dana"): 403,
    ("dana", "self"): 200,
    ("dana", "leo"): 200,
    ("dana", "dana"): 200,
}
MATRIX = [
    (persona, target, kind, 200 if kind == "directory" else private)
    for (persona, target), private in PRIVATE_MATRIX.items()
    for kind in ("directory", "private")
]


def person_id(sandbox: dict[str, object], key: str) -> UUID:
    """A seeded person's ID in this sandbox. `self` is the persona signed in."""
    me = sandbox["me"]
    assert isinstance(me, dict)
    tenant = sandbox["tenant"]
    assert isinstance(tenant, dict)
    if key == "self":
        return UUID(me["id"])
    return uuid5(UUID(tenant["id"]), f"person:{key}")


def path(target_id: UUID, kind: str) -> str:
    return f"/api/v1/people/{target_id}" + ("/private" if kind == "private" else "")


@pytest.mark.parametrize(("persona", "target", "kind", "status_code"), MATRIX)
def test_the_permission_matrix(
    browser: Browser, persona: str, target: str, kind: str, status_code: int
) -> None:
    sandbox = browser.start_sandbox(persona)
    target_id = person_id(sandbox, target)

    response = browser.client.get(path(target_id, kind))

    assert response.status_code == status_code, response.text
    if status_code == 200:
        expected = CARD_FIELDS if kind == "directory" else PRIVATE_FIELDS
        assert set(response.json()) == expected


async def test_hr_reading_private_details_is_audited_by_field_name_only(
    browser: Browser, app_engine: AsyncEngine
) -> None:
    sandbox = browser.start_sandbox("dana")
    leo = person_id(sandbox, "leo")

    response = browser.client.get(path(leo, "private"))

    assert response.status_code == 200
    [read] = [
        event
        for event in await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
        if event.action == "person_private.read"
    ]
    assert (read.actor_person_id, read.via, read.target_type, read.target_id) == (
        person_id(sandbox, "self"),
        "ui",
        "person",
        leo,
    )
    assert read.after == {"fields": sorted(PRIVATE_FIELDS)}
    assert read.request_id == response.headers["X-Request-ID"]
    for value in response.json().values():
        assert value not in str(read.after)


async def test_a_denied_read_is_logged_and_never_audited(
    browser: Browser, app_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    sandbox = browser.start_sandbox("marcus")
    leo = person_id(sandbox, "leo")

    response = browser.client.get(path(leo, "private"))

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    events = await audit_events(app_engine, UUID(sandbox["tenant"]["id"]))
    assert [event.action for event in events] == ["sandbox.created"]
    [record] = [record for record in caplog.records if record.name == "app.security"]
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "security.authz_denied"
    fields = record.__dict__["fields"]
    assert (fields["reason"], fields["tenantId"], fields["actorId"], fields["targetId"]) == (
        "person_private.read",
        sandbox["tenant"]["id"],
        sandbox["me"]["id"],
        str(leo),
    )
    assert record.__dict__["request_id"] == response.headers["X-Request-ID"]
    line = JsonFormatter().format(record)
    assert browser.session_token not in line
    assert browser.csrf_token not in line


@pytest.mark.parametrize(("persona", "kind"), [("priya", "directory"), ("dana", "private")])
def test_a_person_from_another_sandbox_is_not_found(
    open_browser: OpenBrowser, persona: str, kind: str
) -> None:
    mine, theirs = open_browser(), open_browser()
    mine.start_sandbox(persona)
    other = theirs.start_sandbox("dana")

    for target_id in (person_id(other, "leo"), person_id(other, "self"), uuid4()):
        response = mine.client.get(path(target_id, kind))
        assert response.status_code == 404, response.text
        assert response.json()["detail"] == "No such person in this company."


def test_without_permission_a_colleague_and_a_missing_id_look_the_same(browser: Browser) -> None:
    sandbox = browser.start_sandbox("priya")

    responses = [
        browser.client.get(path(target_id, "private"))
        for target_id in (person_id(sandbox, "leo"), uuid4())
    ]

    # The policy layer answers before any lookup, so a 403 never reveals whether someone exists.
    assert [response.status_code for response in responses] == [403, 403]
    assert responses[0].json()["detail"] == responses[1].json()["detail"]


def test_the_directory_pages_through_everyone_in_order(browser: Browser) -> None:
    browser.start_sandbox()

    pages: list[list[dict[str, object]]] = []
    cursor: str | None = None
    while True:
        params = {} if cursor is None else {"cursor": cursor}
        response = browser.client.get("/api/v1/people", params=params)
        assert response.status_code == 200
        body = response.json()
        pages.append(body["items"])
        cursor = body["nextCursor"]
        if cursor is None:
            break

    people = [person for page in pages for person in page]
    assert [len(page) for page in pages] == [50, 50, 20]
    assert len({person["id"] for person in people}) == 120
    keys = [(p["familyName"], p["givenName"], p["id"]) for p in people]
    assert keys == sorted(keys)
    assert all(set(person) == CARD_FIELDS for person in people)


def test_the_page_size_can_be_set_up_to_100(browser: Browser) -> None:
    browser.start_sandbox()

    sizes = [
        len(browser.client.get("/api/v1/people", params={"limit": limit}).json()["items"])
        for limit in (1, 100)
    ]
    refused = [
        browser.client.get("/api/v1/people", params=params).status_code
        for params in ({"limit": 0}, {"limit": 101}, {"cursor": "not-a-cursor"})
    ]

    assert sizes == [1, 100]
    assert refused == [422, 422, 422]


def test_the_directory_shows_only_the_cards_fields(browser: Browser) -> None:
    sandbox = browser.start_sandbox("dana")
    leo = person_id(sandbox, "leo")

    listed = browser.client.get("/api/v1/people").json()["items"]
    card = browser.client.get(path(leo, "directory")).json()
    me = browser.client.get("/api/v1/me").json()

    forbidden = ME_ONLY_FIELDS | PRIVATE_FIELDS | {"hireDate", "managerId", "tenantId"}
    for shown in [*listed, card]:
        assert set(shown) == CARD_FIELDS
        assert forbidden.isdisjoint(shown)
    assert set(me) == CARD_FIELDS | ME_ONLY_FIELDS
    assert set(card["department"]) == {"id", "name"}
    assert set(card["location"]) == {"id", "name", "state"}
    assert set(card["manager"]) == {"id", "givenName", "familyName"}


def test_the_people_endpoints_need_a_session(browser: Browser) -> None:
    some_id = uuid4()

    statuses = [
        browser.client.get(url).status_code
        for url in ("/api/v1/people", path(some_id, "directory"), path(some_id, "private"))
    ]

    assert statuses == [401, 401, 401]
```

Each matrix case starts its own sandbox as its persona, 24 in all. While planning, the whole file
ran in about 3 seconds.

- [ ] **Step 2: Run them and watch them fail**

Run: `cd apps/api && uv run pytest tests/integration/test_api_people.py -q`
Expected: `33 failed`. The people routes don't exist yet, so every read gets a 404, and most
cases fail with `assert 404 == 200` or `assert 404 == 403`.

- [ ] **Step 3: Add the authorization helper.** In `apps/api/app/modules/identity/deps.py`,
      replace the line `from app.policy import Actor` with:

```python
from app.policy import Action, Actor, PersonResource, can
```

Then add this to the end of the file:

```python
def authorize(
    request: Request, signed_in: SignedIn, action: Action, target: PersonResource
) -> None:
    """Ask the policy layer. A denial is a 403, recorded in the security log."""
    if can(signed_in.actor, action, target):
        return
    log_security_event(
        SecurityEvent.AUTHZ_DENIED,
        request,
        action.value,
        tenant_id=signed_in.actor.tenant_id,
        actor_id=signed_in.actor.person_id,
        target_id=target.person_id,
    )
    raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to see this.")
```

- [ ] **Step 4: Create `apps/api/app/modules/people/routes.py`**

```python
"""The directory, and a person's private details.

Each route asks the policy layer before it reads, so a refusal never depends on whether the person
exists. Row-level security then keeps every query inside the actor's tenant, so a person from
another sandbox is simply not found: a 404, the same as an ID that doesn't exist.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.modules.audit.service import record_event
from app.modules.identity.deps import SignedInDep, authorize
from app.modules.people.queries import (
    DirectoryCursor,
    get_card,
    get_private_details,
    list_directory,
)
from app.modules.people.schemas import DirectoryCard, DirectoryPage, PrivateDetails
from app.policy import Action, PersonResource, can

router = APIRouter(prefix="/people", tags=["people"])

NOT_FOUND = "No such person in this company."


@router.get(
    "",
    operation_id="listPeople",
    summary="The company directory, a page at a time",
    response_model=DirectoryPage,
)
async def list_people(
    signed_in: SignedInDep,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DirectoryPage:
    try:
        after = None if cursor is None else DirectoryCursor.decode(cursor)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The cursor is not one this API issued."
        ) from None
    page = await list_directory(signed_in.db, limit=limit, after=after)
    actor = signed_in.actor
    return DirectoryPage(
        items=[
            card
            for card in page.cards
            if can(actor, Action.DIRECTORY_READ, PersonResource(card.id))
        ],
        next_cursor=None if page.next_cursor is None else page.next_cursor.encode(),
    )


@router.get(
    "/{person_id}",
    operation_id="getPerson",
    summary="One person's directory card",
    response_model=DirectoryCard,
)
async def get_person(person_id: UUID, signed_in: SignedInDep, request: Request) -> DirectoryCard:
    authorize(request, signed_in, Action.DIRECTORY_READ, PersonResource(person_id))
    card = await get_card(signed_in.db, person_id)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return card


@router.get(
    "/{person_id}/private",
    operation_id="getPersonPrivate",
    summary="One person's private details, for that person and for HR. Each read is audited.",
    response_model=PrivateDetails,
)
async def get_person_private(
    person_id: UUID, signed_in: SignedInDep, request: Request
) -> PrivateDetails:
    authorize(request, signed_in, Action.PERSON_PRIVATE_READ, PersonResource(person_id))
    details = await get_private_details(signed_in.db, person_id)
    if details is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    await record_event(
        signed_in.db,
        tenant_id=signed_in.actor.tenant_id,
        actor_id=signed_in.actor.person_id,
        action="person_private.read",
        target_type="person",
        target_id=person_id,
        # The names of the fields returned, never their values.
        after={"fields": sorted(details.model_dump(by_alias=True))},
    )
    return details
```

- [ ] **Step 5: Replace `apps/api/app/api/v1/router.py`**

```python
"""Every version 1 endpoint, mounted under /api/v1."""

from fastapi import APIRouter

from app.api.v1 import health
from app.modules.identity import routes as identity
from app.modules.people import routes as people
from app.modules.sandbox import routes as sandbox

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(sandbox.router)
api_router.include_router(identity.router)
api_router.include_router(people.router)
```

- [ ] **Step 6: Run them and watch them pass**

Run: `cd apps/api && uv run pytest tests/integration/test_api_people.py -q`
Expected: `33 passed`.

- [ ] **Step 7: Prove both matrices catch a manager rule, then undo.** In
      `apps/api/app/policy/__init__.py`, change the last line of `_themselves_or_hr` to
      `return target.person_id == actor.person_id or actor.is_hr_admin or target.person_id in actor.report_ids`.

Run: `cd apps/api && uv run pytest tests/test_policy.py tests/integration/test_api_people.py -q`
Expected: `3 failed, 41 passed`.
- The unit matrix fails for "manager, for a report".
- Over HTTP, Marcus reading Leo's private details fails with `assert 404 == 403`, in both the
  matrix and the denied-read test. The policy layer let him through, and the database's
  private-details rule still hid the row.

Restore the line.

- [ ] **Step 8: Run the API checks.** The schema is out of date until Task 25.

Run: `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q`
Expected: `All checks passed!`, `81 files already formatted`,
`Success: no issues found in 81 source files`, `Domain and policy code import no framework KEPT`,
and `260 passed`. That is 150 unit tests and 110 database tests.

### Task 25: Regenerate the schema and the web client

**Files:**
- Generated: `apps/web/openapi.json`, `apps/web/src/api/generated.ts`

- [ ] **Step 1: Regenerate both**

Run: `make openapi`
Expected: `Wrote apps/web/openapi.json`, then orval's success line for `src/api/generated.ts`.
The schema gains `GET /api/v1/people` (`listPeople`), `GET /api/v1/people/{person_id}`
(`getPerson`), and `GET /api/v1/people/{person_id}/private` (`getPersonPrivate`), and the client
exports `useListPeople`, `useGetPerson`, and `useGetPersonPrivate`.

- [ ] **Step 2: Run the web checks and the schema check**

Run: `make check-web && cd apps/api && uv run python scripts/export_openapi.py --check`
Expected: every web check passes, ending with
`src/api/generated.ts is up to date with openapi.json.` Then
`apps/web/openapi.json is up to date.`

### Task 26: The data inventory and the backlog

**Files:**
- Create: `docs/DATA-INVENTORY.md`
- Modify: `docs/BACKLOG.md`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: Verify the statutory figures again, in this session.** `CLAUDE.md` asks for it.
      Read California Government Code §12946(a) on leginfo.legislature.ca.gov, and Article 113 of
      the EU AI Act. If either has changed, update the figure and the "read on" dates below
      before writing them.

- [ ] **Step 2: Create `docs/DATA-INVENTORY.md`**

```markdown
# Data inventory

Every piece of data Open Door stores: what it holds, why it's kept, who can see it, and how long it
stays. Update this file in the same change as any new table, column, cookie, or log field.

Every person in Open Door is fictional. Each visitor gets a sandbox company, seeded with the same
120 made-up people, and the whole sandbox is deleted 24 hours after it is created. The
[Phase 1 spec](specs/2026-10-03-phase-1-tenancy-identity-permissions.md) has the design behind
this, and [ADR 0007](adr/0007-session-lifetime.md) explains why sessions last as long as the
sandbox.

## How long data is kept

**Everything in a sandbox lives for 24 hours.** `tenants.expires_at` is set to 24 hours after
creation. Every other row belongs to a tenant and is deleted with it, through the foreign keys'
`ON DELETE CASCADE`. A session is refused as soon as it expires, even before its row is deleted.
The scheduled cleanup job that deletes expired sandboxes arrives in Phase 8. Until then, the
`od_cleanup` role can delete only expired sandboxes, and tests prove it.

**The 24-hour delete is a demo choice, not a model for real employee data.** A real deployment
would keep audit records for at least 4 years, outside the tenant cascade. California requires
employers to keep personnel and employment records for 4 years, and its rules on
automated-decision systems apply that to the data such systems use and produce.

> Source: California Government Code §12946(a), as amended by SB 807 (Stats. 2021, ch. 278), read
> from leginfo.legislature.ca.gov on 2026-10-03.
>
> Source: Civil Rights Council, employment regulations regarding automated-decision systems,
> 2 CCR §11013(c), effective 2025-10-01. The four-year period was confirmed in the Council's Final
> Statement of Reasons (June 2025), read from calcivilrights.ca.gov on 2026-10-03.

## Who can see what

- **Tenant isolation.** Postgres row-level security shows the API only the rows of the sandbox its
  transaction belongs to. The API's database login can't skip that rule.
- **Directory fields** are visible to everyone in the same sandbox.
- **Private details** are visible only to the person themselves and to HR. Both the policy layer
  (`app/policy`) and a second, database-level rule enforce this.
- **The `/me` fields** (`employmentType`, `isManager`, `isHrAdmin`, `personaKey`) are shown only
  to the signed-in person, about themselves.
- **The database owner** runs migrations. It reads no data in the normal course of things. In
  development it is the Compose superuser.

## Tables

### `tenants`: one sandbox company

| Column | Holds | Why |
|---|---|---|
| `id` | A random UUID | Identifies the sandbox. Random, so one visitor can't guess another's. |
| `created_at` | When the sandbox was created (UTC) | Record of the sandbox's age. |
| `expires_at` | 24 hours after `created_at` | When the sandbox and everything in it are deleted. Copied to each session and to the cookies' `Max-Age`. |
| `anchor_date` | The UTC date the sandbox was created | The seed data's dates count back from it, so "last week" always means last week. |

Visible to the API only for its own sandbox, and to the cleanup role only once it has expired.

### `locations`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id` | IDs | Identity, and the sandbox it belongs to. |
| `code`, `name`, `city`, `state` | Denver HQ (CO), the Oakland store (CA), the Austin warehouse (TX) | The directory shows each person's location and state. Each state's handbook addendum applies by location (Phase 3). |
| `timezone` | An IANA zone, such as `America/Denver` | Leave dates are calendar dates in the location's time zone (Phase 5). |

Visible to everyone in the sandbox. Deleted with the sandbox.

### `departments`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id` | IDs | Identity, and the sandbox it belongs to. |
| `name` | One of eight department names | Shown on each directory card. |

Visible to everyone in the sandbox. Deleted with the sandbox.

### `people`: the directory

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id` | IDs | Identity, and the sandbox. |
| `given_name`, `family_name`, `title`, `work_email` | Fictional names, job titles, and `opendoor.example` addresses | The directory card. |
| `department_id`, `location_id` | References | The directory card, and the rules that depend on location. |
| `manager_id` | The person's manager | The reporting line. Being a manager is derived from it on every request, never stored. |
| `employment_type` | `salaried` or `hourly` | Company PTO accrues at a fixed amount per employment type (Phase 5). Shown only at `/me`. |
| `hire_date` | A date relative to `anchor_date` | Part of a realistic employee record, for later phases. Not shown by any Phase 1 endpoint. |
| `is_hr_admin` | Whether the person is HR | HR may read private details. Shown only at `/me`. |
| `persona_key` | `priya`, `mateo`, `marcus`, `dana`, or null | Which people a visitor can sign in as. Shown only at `/me`. |

The directory fields are visible to everyone in the sandbox. Deleted with the sandbox.

### `person_private`: private details

| Column | Holds | Why |
|---|---|---|
| `person_id`, `tenant_id` | IDs | Whose details these are, and the sandbox. |
| `personal_email` | An `example.com` address | A realistic HR record that the demo can protect. |
| `phone` | A 555-0100 to 555-0199 number, reserved for fiction | The same. |
| `home_address` | A made-up street address | The same. |
| `date_of_birth` | A date relative to `anchor_date` | The same. |

Visible only to the person themselves and to HR. Every read writes a `person_private.read` audit
event that names the fields returned, never their values. Deleted with the sandbox.

### `holidays`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id`, `location_id` | IDs | Identity, the sandbox, and the location that closes. |
| `holiday_date`, `name` | The company holiday calendar for `anchor_date`'s year and the next | The time-off engine skips these days (Phase 5). |

Visible to everyone in the sandbox. Deleted with the sandbox.

### `sessions`: who is signed in

| Column | Holds | Why |
|---|---|---|
| `token_hash` | The SHA-256 hash of the session token | Finds the session from the cookie. The raw token is only in the visitor's cookie. |
| `csrf_hash` | The SHA-256 hash of the CSRF token | Checks the `X-CSRF-Token` header on requests that change something. |
| `tenant_id`, `person_id` | The sandbox, and the persona signed in | Scopes every request to that sandbox and person. |
| `created_at`, `expires_at` | When the session started, and the sandbox's expiry | A session never outlives its sandbox. |

Outside row-level security, because a session is looked up before its sandbox is known. The API
finds a session only by its token hash, and never lists sessions. Switching persona deletes the
row and creates a new one, and signing out deletes it. Deleted with the sandbox in any case.

### `audit_events`: what happened

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id` | A random UUID, and the sandbox | Random rather than a sequence, so one sandbox can't estimate another's activity. |
| `occurred_at` | When it happened (UTC) | The record. |
| `actor_person_id`, `via` | Who acted, and how: `ui`, `assistant`, or `system` | Every action, including the assistant's from Phase 4, is attributed. |
| `action`, `target_type`, `target_id` | What was done, and to what | Phase 1 records `sandbox.created`, `session.persona_switched`, `session.ended`, and `person_private.read`. |
| `before`, `after` | Directory fields only, such as `personaKey`, or the names of the private fields read | Never private values, so a privacy deletion request never means editing this log. |
| `proposal_id` | The confirmed proposal, from Phase 5 | Ties an executed action to what the person confirmed. |
| `request_id` | The request's ID | Matches the event with that request's log lines. |

Append-only: the API can add and read events but never change or delete them. Visible to the API
within its own sandbox. No endpoint shows them yet. Deleted with the sandbox, which is the demo
choice described above.

## Outside the database

### Cookies

| Cookie | Holds | Attributes |
|---|---|---|
| `__Host-od_session` | The session token: 32 random bytes | `HttpOnly; Secure; SameSite=Lax; Path=/`, until the sandbox expires |
| `__Host-od_csrf` | The CSRF token: 32 random bytes | `Secure; SameSite=Lax; Path=/`, readable by the page, until the sandbox expires |

Signing out clears both. There are no tracking or analytics cookies.

### Security log

Refused requests are written to the JSON application log under the `app.security` logger, not to
the audit table. The events are `security.session_invalid`, `security.origin_rejected`,
`security.csrf_rejected`, and `security.authz_denied`. Each carries:

- the request ID
- the sandbox and the actor, when they are known
- the target person's ID, for a denied read
- the client's IP address
- the first 8 characters of the session token's hash

A raw token, a cookie value, or a private detail is never logged. How long logs are kept is set
where they are stored, when Open Door is deployed (Phase 9).
```

- [ ] **Step 3: Update `docs/BACKLOG.md`.** First, replace the whole
      `## Phase 1: tenancy, identity, permissions` section with:

```markdown
## Any phase

- **Don't run Alembic inside an async test.** `env.py` calls `asyncio.run`, which fails inside a
  running event loop, and `fileConfig` resets the root log handlers. Test setup should run
  `alembic upgrade head` as a subprocess, or from a synchronous session fixture. Phase 1's tests
  never needed to, because CI runs the migration round trip as plain commands, but a later test
  that runs migrations will.

## Phase 2: design system, shell, sandbox entry

- **Declare the error responses in the OpenAPI schema.** The endpoints answer every error with
  problem details, but the schema lists only FastAPI's default 422 body, so the generated client
  types errors wrongly. Add a problem-details model, and declare 401, 403, 404, and 422 where each
  can happen, before the screens handle them.

## Phase 3: handbook and retrieval

- **Pin each sandbox to a handbook version** with a `tenants.handbook_version_id` column, so an
  answer cites the handbook the sandbox was created with, even after the handbook changes.
  Source: [the Phase 1 spec](specs/2026-10-03-phase-1-tenancy-identity-permissions.md#later-phases).
```

Next, add these two items at the start of the `## Phase 4: assistant core` list:

```markdown
- **Record why the assistant is not a high-risk AI system.** Annex III of the EU AI Act lists
  systems used for employment decisions as high-risk. Article 6(3) exempts a system that doesn't
  profile people or materially influence decisions, and Article 6(4) requires that assessment to
  be documented. The governance document should record it. The Annex III obligations apply from
  2027-12-02.
  Source: EU AI Act Annex III (https://artificialintelligenceact.eu/annex/3/) and Article 6
  (https://artificialintelligenceact.eu/article/6/), read on 2026-10-03. These pages are an
  unofficial consolidation, not EUR-Lex, and the 2027-12-02 date comes from law-firm summaries of
  the 2026 amendment.
- **The AI disclosure is already required.** Article 50 of the EU AI Act, which requires telling
  people they are talking to an AI, has applied since 2026-08-02. Invariant 7 covers it; the
  Phase 4 disclosure should cite the article.
  Source: EU AI Act Article 113 (https://artificialintelligenceact.eu/article/113/), read on
  2026-10-03. Article 50 is in Chapter IV, which follows the general date of 2 August 2026.
```

Next, add these two sections before `## Phase 8: hardening and deploy-readiness`:

```markdown
## Phase 5: time off

- **Record who confirms a proposal as an audit event of its own,** separate from the action it
  executes, so the log shows both who proposed and who decided.
- **Grant `UPDATE` only where requests and approvals need it.** Phase 1 grants the API no
  `UPDATE` anywhere, and the exact-grants test fails on any grant it doesn't expect.

Source for both: [the Phase 1 spec](specs/2026-10-03-phase-1-tenancy-identity-permissions.md#later-phases).

## Phase 6: cases and escalation

- **Encrypt case narratives.** They are the most sensitive text the app will hold.
  Source: [the Phase 1 spec](specs/2026-10-03-phase-1-tenancy-identity-permissions.md#later-phases).
```

Last, add this to the end of the Phase 8 section, before `## Phase 9: deploy to AWS`:

```markdown
From the Phase 1 review ([the spec's Later phases](specs/2026-10-03-phase-1-tenancy-identity-permissions.md#later-phases)),
plus the last item, found while building Phase 1's security log:

- **Rate limits and Turnstile on sandbox creation.** `POST /api/v1/sandboxes` needs no session,
  and each call seeds 120 people.
- **The scheduled cleanup job.** The `od_cleanup` role can already delete only expired
  sandboxes. Nothing runs it on a schedule yet.
- **Re-test `set_config` under RDS Proxy or PgBouncer.** Row-level security depends on settings
  scoped to one transaction, and a pooler in transaction mode must not carry them between
  clients. The reused-connection tests are the model. Background: the pgsql-bugs thread on local
  settings,
  https://www.postgresql.org/message-id/CA+Q86ij0KDCB0G45G509-8q0DNR611gcKG-sSM83GA1EBL7boA@mail.gmail.com.
- **Database TLS with certificate checks, and secret rotation** for the three database URLs.
- **Deletion from backups.** A sandbox deleted from the database still exists in backups until
  they expire. Document how long, or exclude sandbox data from them.
- **Read the client's IP address through the load balancer.** The security log records the
  connecting address, which behind a load balancer is the balancer's. Trust its forwarded header
  only from the balancer itself, with uvicorn's `--proxy-headers` and `--forwarded-allow-ips`.
```

- [ ] **Step 4: Link the inventory from the README.** In `README.md`'s Documentation table, add
      this row after the Decision records row:

```markdown
| [Data inventory](docs/DATA-INVENTORY.md) | Every piece of data stored, why, who can see it, and how long it's kept |
```

- [ ] **Step 5: Add a rule to `CLAUDE.md`.** In the Conventions section, add this after the
      "Timestamps are UTC" item:

```markdown
- **Keep [`docs/DATA-INVENTORY.md`](docs/DATA-INVENTORY.md) current.** A new table, column,
  cookie, or log field updates it in the same change: what it holds, why, who can see it, and how
  long it's kept.
```

- [ ] **Step 6: Run the docs checks**

Run: `make check-docs`
Expected: typos prints nothing, lychee reports `0 Errors`, and no placeholders are printed. The
anchors `#later-phases` resolve into the Phase 1 spec.

### Task 27: Close Stage 4 and Phase 1

**Files:**
- Modify: `CHANGELOG.md`, `docs/ROADMAP.md`

- [ ] **Step 1: Add to `CHANGELOG.md` under `## [Unreleased]` → `### Added`,** after the stage 3
      entry

```markdown
- **The directory and private details** (Phase 1, stage 4). A signed-in persona can now read the
  company directory and, where allowed, a person's private details. The policy layer decides:
  everyone in the company sees the directory, and only the person themselves and HR see private
  details. A manager gets no special view of their reports' private details. Each read of private
  details goes into the audit log, which records the names of the fields returned, never their
  values. Also added:
  - Three endpoints. `GET /api/v1/people` lists the directory a page at a time, 50 by default
    and up to 100. `GET /api/v1/people/{id}` returns one person's directory card, and
    `GET /api/v1/people/{id}/private` their private details.
  - Tests over HTTP of every persona against themselves, Leo, and Dana, for both the directory
    and private details. They also show that a person from another sandbox is never found, and
    that a directory card carries none of the private or `/me`-only fields.
  - `docs/DATA-INVENTORY.md`, which lists every table and column: what it holds, why, who can
    see it, and how long it's kept. It notes that a real deployment would keep audit records for
    4 years, as California requires, instead of deleting them with the sandbox.
  - The backlog now holds the later-phase findings from the Phase 1 review, each with its source.

  With this, Phase 1 is done: tenancy, identity, and permissions are proven by tests, over HTTP
  and in the database.
```

- [ ] **Step 2: Mark Phase 1 done in `docs/ROADMAP.md`.** Replace the Phase 1 row of the status
      table with this one, using today's date and the four stages' pull request numbers:

```markdown
| 1 Tenancy, identity, permissions | Done | `feat/phase-1-directory-api` | [#<stage 1 PR number>](https://github.com/musicteachj/open-door/pull/<stage 1 PR number>), [#<stage 2 PR number>](https://github.com/musicteachj/open-door/pull/<stage 2 PR number>), [#<stage 3 PR number>](https://github.com/musicteachj/open-door/pull/<stage 3 PR number>), [#<stage 4 PR number>](https://github.com/musicteachj/open-door/pull/<stage 4 PR number>) | [phase 1 plan](plans/2026-10-03-phase-1-tenancy-identity-permissions.md) | <today> |
```

- [ ] **Step 3: Run `make check` (with `make db` first)**

Run: `make db && make check`
Expected: every check passes.
- `check-api` ends with `260 passed`, `No new upgrade operations detected.`, and
  `apps/web/openapi.json is up to date.`
- `check-web` passes, ending with `src/api/generated.ts is up to date with openapi.json.`
- `check-docs` reports `0 Errors`, with no placeholders printed.
- zizmor reports `No findings to report`.

While planning, `make check` passed in the scratch clone with every document in this stage
edited. `make db` itself wasn't run, because it starts the Compose database. Its migrate and
bootstrap commands were run.

- [ ] **Step 4: Run `/code-review medium` on the whole branch against `dev`,** committed and
      uncommitted work together, and fix anything real it finds. Re-run `make check` after any
      fix.

- [ ] **Step 5: Propose the commit and PR, and wait for the owner's OK.** Commit message:

```
Let personas read the directory, and private details where allowed

A signed-in persona can now page through the company directory, read
anyone's directory card, and read private details where the policy
allows: their own, or anyone's for HR. A manager gets no special view
of their reports' private details. Each read of private details is
written to the audit log with the names of the fields returned, never
their values.

Tests over HTTP cover every persona against themselves, a colleague,
and HR, for the directory and for private details. They show that a
person from another sandbox is never found, and that a directory card
carries none of the private or personal fields.

docs/DATA-INVENTORY.md now lists every table and column: what it
holds, why, who can see it, and how long it's kept. The backlog holds
the later-phase findings from the Phase 1 review. This is the last of
four stages, and it completes Phase 1.
```

- [ ] **Step 6: With the owner's OK, push and open the PR into `dev`.** Title: "Let personas read
      the directory, and private details where allowed". Body:

```markdown
## What this does
Adds the directory: `GET /api/v1/people` a page at a time, `GET /api/v1/people/{id}` for one
card, and `GET /api/v1/people/{id}/private` for private details. The policy layer decides each
read. Everyone in the company sees the directory, and only the person themselves and HR see
private details. Each private read is audited by field name. It also adds
`docs/DATA-INVENTORY.md`, fills the backlog with the later-phase findings from the Phase 1
review, and marks Phase 1 done.

## Why
This finishes Phase 1's promise: the permission matrix and tenant isolation are proven over HTTP,
so Phase 2 only has to build screens. It is stage 4 of 4.

## How it was checked
`make check` passes, with 260 API tests, 110 of them against the real database. The HTTP matrix
signs in as each persona and reads themselves, Leo, and Dana. Marcus is refused Leo's private
details, and Dana's read of them writes an audit event with field names only. Other tests cover
another sandbox's people (404), paging through all 120 people in three pages, and the fields each
response may carry. When the policy layer was changed to let managers in, both matrices failed,
and the database's own rule still hid the row.

## What to look at
- The order in each route: the policy layer first, then the query, so a refusal never reveals
  whether someone exists.
- The directory cursor in `app/modules/people/queries.py`, and why it isn't signed.
- `docs/DATA-INVENTORY.md`, especially the retention section and its sources.
```

- [ ] **Step 7: Confirm the pull request's checks are green**

Run: `gh pr checks <stage 4 PR number> --repo musicteachj/open-door --watch`
Expected: CI (Detect what changed, API, Web, Docs, Workflows), Security, and Changelog all pass.
This PR changes the API and the web app's generated client, so both the API and Web jobs run.

---

## Phase 1 is done when

- CI is green on the stage 4 pull request.
- The tests prove what the spec's "Done when" lists:
  - **The permission matrix:** each persona against each target and action, over HTTP (Task 24),
    and as pure values (Task 15).
  - **Isolation:** one tenant can't see another's data, through the API (Task 24) or in SQL
    (Stage 1). An unset tenant sees nothing, even on a reused connection (Stage 1).
  - **Row-level security coverage:** every tenant table has it enabled and forced, and `sessions`
    is the only exception (Stage 1).
  - **Seeding:** a sandbox seeds in under 2 seconds at p95 (Stage 2).
- The roadmap shows Phase 1 as done, and the changelog has an entry for each of the four stages.

## Self-review against the spec

- **Covered by this plan:**
  - The settings, the roles and schema migrations, the bootstrap script, the transaction hook,
    `get_engine`, and every database test (Stage 1).
  - The seed company and its tests (Stage 2).
  - Tokens, cookies, sessions, rotation, and sign-out (Tasks 16, 18, and 20).
  - The same-origin check as ASGI middleware, and the CSRF check (Tasks 17 and 20).
  - The policy layer, pure and checked by import-linter, with its matrix test (Task 15).
  - The actor, with reports from a recursive query on every request (Task 18).
  - `record_event`, the four Phase 1 actions, and directory fields only in `before` and
    `after` (Tasks 18, 20, and 24).
  - The security log's four events, and no raw token in any of them (Tasks 16, 17, 20, and 24).
  - Every endpoint in the spec's API table, with its error statuses (Tasks 20 and 24).
  - Every HTTP test the spec lists (Tasks 20 and 24).
  - The regenerated schema and client (Tasks 21 and 25).
  - No CORS headers (Task 17).
  - ADR 0007 (the docs PR), the data inventory, `CLAUDE.md`, and the backlog (Stage 1 and
    Task 26).
- **Deliberately later:**
  - Everything in the spec's "Later phases", now in the backlog under its phase.
  - The error responses in the OpenAPI schema (Phase 2).
  - The client's IP address behind the load balancer (Phase 8).
- **Changed from the spec:**
  - Four stages instead of three, because the third came to about 2,400 lines.
  - The spec's caution about the 4-year figure is answered: the statute, Government Code
    §12946(a), was read directly.

## Changes made during execution

Record here anything that differs from the plan while it is carried out, with the reason, the way
the Phase 0 plan does.

**Stage 1 (2026-10-03).** For Tasks 1–9, the code in the repository is the source of truth; the
code blocks above show the original plan. Every test count after Task 1 is higher than the plan
says, because of the additions below.

- **Task 1, `APP_ORIGIN`.** The validator also refuses an explicit default port (`:80` with http,
  `:443` with https) and ports outside 1–65535. Browsers leave the default port out of `Origin`,
  so such a value would make the same-origin check refuse every request. The error message now
  says the origin must be lowercase. IPv6 literals stay unsupported. Adds 8 unit tests.
- **Task 3, `alembic.ini`.** Its comment now names `MIGRATION_DATABASE_URL`.
- **Tasks 4–6, from the security review.**
  - **The bootstrap script refuses unsafe logins.** It checks an existing login before changing
    anything, and refuses one with SUPERUSER, BYPASSRLS, CREATEROLE, CREATEDB, or REPLICATION,
    or with any membership besides its own role. Before this fix, a pre-created `BYPASSRLS` login
    was granted `od_app` and could read every tenant.
  - **The plaintext password never reaches the server.** The script computes a SCRAM-SHA-256
    verifier and sends that, so plaintext appears in neither the server log nor an error. It
    accepts only printable-ASCII passwords, which SASLprep leaves unchanged. Its engine hides
    parameters, and a database error is reported by class name only. It gains a pure
    `logins_from()`, and `scripts/` becomes a package so the tests can import it.
  - **Migration 0002 refuses to reuse an unsafe role.** It raises an exception if an existing
    `od_app` or `od_cleanup` has a dangerous attribute or any membership. The context functions
    use SQL-standard `RETURN` bodies, so their names are bound when they're created. Only
    `od_app` gets USAGE on schema `app`, because the cleanup role doesn't need it.
  - **Migration 0003 caps a sandbox's lifetime.** `ck_tenants_lifetime` refuses an expiry more
    than 25 hours after creation.
  - **New and stronger tests:**
    - the refusals and the verifier, with an RFC 7677 vector
    - that the password never leaks
    - each unsafe-role case in the migration
    - the lifetime cap
    - each login's memberships
    - PUBLIC schema grants
    - materialized and foreign tables in the coverage scan
    - a check that no permissive policy widens `tenant_isolation`

    The suite grows from 74 to 123 tests at the end of Task 6.
  - **From the security re-review:**
    - **A trigger stamps `created_at`.** The lifetime cap was measured from `created_at`, a
      column the API could write, so a chosen `created_at` could stretch a sandbox's life
      indefinitely. A `BEFORE INSERT` trigger, `app.stamp_tenant_created_at()`, now always sets
      it to `now()`. The function pins `search_path` and isn't SECURITY DEFINER.
    - **Test roles can't log in.** The refusal tests create their roles as `NOLOGIN` with no
      password, so a killed test run can't leave a usable superuser login behind. An autouse
      sweep at the start of the session drops any leftover `od_test_*` role.
    - **No login may hold its role WITH ADMIN OPTION.** The bootstrap script refuses one, and a
      test checks that nobody holds `od_app` or `od_cleanup` that way.

    The suite is at 129 tests at the end of Task 6, where the plan expects 66.
- **Task 7, the integration conftest.** The conftest was merged, not replaced: it keeps the
  `od_test_*` sweep fixture from Tasks 4–6.
- **Tasks 7–9, from the security review:**
  - **The hook skips savepoints.** SQLAlchemy fires `after_begin` for a savepoint too, so
    `begin_nested()` re-ran the hook and cleared `app.is_hr` for the rest of the transaction.
    HR then saw only their own private row. `apply_tenant_context` now returns early for a
    nested transaction, because the outer transaction has already set the context. A test runs a
    savepoint as HR and checks every private row is still visible.
  - **The hook is registered whenever the database code is imported.** `app/db/engine.py`
    imports `app.db.tenancy` for that side effect, and a test checks it in a fresh interpreter.
  - **Each policy rule is pinned by its own test.**
    - An unfiltered `DELETE FROM tenants` as the cleanup login removes only expired tenants.
    - The cleanup login's two policies are exactly `cleanup_select` and `cleanup_delete`, each
      on `expires_at < now()`.
    - `set_is_hr` lasts only for its transaction on a reused connection.

    Before these tests, loosening `cleanup_delete` alone, or making the HR flag
    connection-wide, passed every test.
  - **The test teardown checks the owner first.** It deletes the tenants it created through the
    owner, so a session fixture fails fast if `MIGRATION_DATABASE_URL` doesn't name a superuser.
    Otherwise row security would let that delete silently remove nothing.

- **From `/code-review medium`:**
  - **The bootstrap script also refuses a login that has members.** Any role that belongs to
    the login would inherit `od_app` once it's granted.
  - **`APP_ORIGIN` rejects a zero-padded port** such as `:05173`, which a browser never sends.
  - **A login made for a sibling database could connect to this one.** The review called this
    plausible. It matters only if environments share a Postgres server, so it's in the backlog
    under Phase 9 instead of being fixed now.

  Stage 1 ends with 152 tests, where the plan expects 81.

**Phase 1 closes with a whole-phase review (owner-approved, 2026-10-03).** `CLAUDE.md` now asks
for a review of every phase's full diff once its last PR merges. Phase 1 guards an invariant, so
after Stage 4 merges it runs `/code-review max` and `/security-review` on `dev` against `d6b652d`,
the commit before Phase 1's first stage. Real findings are fixed in a small follow-up PR before the
`v0.1.0` release.

**Stage 2.** Every pytest total is 71 higher than the plan says, because Stage 1 ended at 152
where the plan expects 81.
- **Tasks 11–13** went in exactly as planned, with no adjustments. 20 sandboxes seeded at p50
  14 ms and p95 17 ms.
- **From the review:**
  - **A new unit test checks that every row gets an ID of its own.** `all_ids()` returns a set,
    so a repeated ID would have shrunk it silently. The test was shown to fail when every person
    was given the same ID.
  - **The previous year's holidays go to the backlog (Phase 5).** A sandbox created in early
    January lacks the previous December's closures.

  Stage 2 ends with 184 tests, where the plan expects 112.

**Stage 3.** For Tasks 15–22, the code in the repository is the source of truth. Every pytest total
is 72 higher than the plan says at the start of Stage 3, and higher still after the review fixes
below.

- **Tasks 15–17** went in exactly as planned.
- **From the security review of Tasks 15–17:**
  - **The same-origin check lists the methods it lets through.** It now skips only `GET`,
    `HEAD`, `OPTIONS`, and `TRACE`, and checks everything else. It used to check only the four
    methods it named. A route declared with `PURGE`, or a lowercase `post` reaching a mounted
    app, then skipped the check entirely: the reviewer showed a cross-site request getting a
    200. Browsers can't send those cross-site without a preflight, which we refuse, so it wasn't
    exploitable, but the check now fails closed. The docstring now describes the JSON rule as
    defense in depth.
  - **`can()` returns a strict bool, and `Actor` checks its types.** A rule result like the
    string `"false"` was truthy, so it granted access. `can()` now returns `rule(...) is True`.
    `Actor` and `PersonResource` refuse wrong types: UUID IDs, a real `bool` for
    `is_hr_admin`, and a `frozenset` for `report_ids`.
  - **New tests for three gaps the reviewer found by mutation:**
    - a chunked non-JSON body
    - an `Origin` that differs only in case
    - that `RULES` can't be modified

    Each was shown to fail under its mutation. The suite is at 292 at the end of Task 17.
  - **The backlog gains the reviewer's notes:**
    - JSON content type for hand-written requests (Phase 2)
    - an `Origin` check on any future WebSocket (any phase)
    - requiring `APP_ORIGIN` in production (Phase 8)
    - trusting forwarded IPs only from the load balancer (Phase 8)
- **Tasks 18–19** went in exactly as planned.
- **From the security review of Tasks 18–19:**
  - **Rotation refuses a session that is already gone.** `end_session` now returns whether it
    deleted a live session. `rotate_session` raises `SessionGoneError` when it didn't, and
    inserts nothing. Before this, signing out in one tab and switching persona in another
    signed the browser back in. Two simultaneous switches also left two live sessions. A test
    runs two rotations of one session at once, and only one wins.
  - **A new session is tied to the transaction's tenant and its expiry.**
    - `start_session(session, tenant_id, person_id)` no longer takes `expires_at`. It inserts
      with `INSERT … SELECT` from `people` joined to `tenants`, so row-level security limits it
      to the current tenant, and the expiry comes from the tenant row.
    - It raises `PersonNotInTenantError` otherwise.
    - Before this, a session could be started for another tenant's person, or with any expiry.
  - **`load_actor` takes the tenant from the person's own row.** A person can't count as their
    own report, even in a reporting loop.
  - **`record_event` checks keys at every level.** It looks inside nested mappings and lists, in
    any letter case, for private field names. A top-level-only check let
    `{"x": {"phone": …}}`, `{"Phone": …}`, and a list of pairs through.
  - **New tests:**
    - cross-tenant audit writes
    - the exact fields of the nested reference models
    - ending a session twice

    The suite is at 350 at the end of Task 19.
  - **Task 20 adapts to these changes:**
    - `create_sandbox` calls `start_session(db, tenant_id, person_id)`.
    - A session test for an expired tenant uses `make_tenant(expired=True)`, because the expiry
      now comes from the tenant.
    - `switch_persona` maps `SessionGoneError` to 401.
    - `sign_out` ignores a session that was already gone.
  - **A caution for Stage 4.** After a persona switch, the rest of that request's transaction
    still runs as the old persona: `app.person_id` and `app.is_hr` aren't updated. Nothing may
    read private details after a switch within the same request.
- **Tasks 20–21** went in as planned, with the Task 20 adaptations listed above.
  - `switch_persona` also logs `security.session_invalid` when the session it rotates is
    already gone.
  - Two extra tests pin the race adaptations: a persona switch on a session another tab just
    ended gets a 401, and a second sign-out writes no second audit event.
- **From the security review of Tasks 20–21:**
  - **Every `/api/` response is marked `Cache-Control: no-store`.** A pure-ASGI middleware,
    `app/core/cache_control.py`, is the outermost user middleware. The unhandled-error handler
    also sets the header, because Starlette sends a 500 from outside every user middleware.
    Without it, a CDN that forwards cookies but leaves them out of its cache key could serve one
    visitor's `/me` to another.
  - **Two tests pin behavior that was correct but unguarded.** Removing either guard used to pass
    every test.
    - A commit that fails during a persona switch returns a 500 with no new cookies, and the old
      session still works. This pins `scope="function"`.
    - A CSRF token from another session is refused, even when sent as both the cookie and the
      header. This pins the stored-hash check.
  - **The "sandbox is gone" security event now logs the tenant and actor,** which it knows from
    the session.
  - **The backlog gains:**
    - Phase 2: the web client's CSRF mutator, resetting caches when the identity changes, the
      real error shapes in the OpenAPI schema, and checking `__Host-` cookies in each browser.
    - Phase 8: a request body size cap.

- **From `/code-review medium`:** one low-severity race, recorded in the backlog under Phase 8
  rather than fixed. A sign-out that runs while another tab switches persona finds the session
  already replaced. It answers 204, and the new session stays valid until the sandbox expires.
  The fix, a session `family_id` that sign-out deletes as a whole, needs a migration.

  Stage 3 ends with 392 tests, where the plan expects 217.
- **Task 10.**
  - The changelog entry also mentions the bootstrap script's refusals, the plaintext-free
    passwords, and the 25-hour cap.
  - The backlog gains the security reviews' non-blocking findings:
    - write policies on `person_private` (any phase)
    - data migrations under forced row security on managed Postgres (Phase 8)
    - a `SECURITY DEFINER` session lookup (Phase 8)
    - the Postgres 16 floor (Phase 8)
  - **Stage 4's backlog task must keep these entries.** Its blocks predate them, so merge them in
    rather than replacing whole sections.

**Stage 4 (2026-10-04).** For Tasks 23–27, the code in the repository is the source of truth. Every
pytest total is 175 higher than the plan says at the start of Stage 4, because Stage 3 ended at
392 where the plan expects 217. It is higher still after the review fixes below.

- **Tasks 23–24** went in as planned, with two differences.
  - **`tests/test_people_schemas.py` was merged, not replaced.** It keeps Stage 3's
    `test_the_nested_references_have_exactly_their_own_fields` and its `json_fields` signature,
    so it has 13 tests where the plan expects 12. The suite was at 402 after Task 23 and 435
    after Task 24.
  - **The manager-rule experiment in Task 24 Step 7 fails 4 tests, not 3.** Stage 3's review
    added `test_can_returns_exactly_true_or_false`, which covers the same "manager, for a report"
    case. The two HTTP failures are as planned: Marcus gets a 404, because the database's
    private-details rule still hides Leo's row.
- **From the security review of Tasks 23–24.** Nothing Critical, High, or Medium. Each fix was
  written test first, and each new test was shown to fail under its mutation.
  - **A crafted directory cursor got a 500.** A name with a NUL character or a lone surrogate
    passed `DirectoryCursor.decode`, then failed inside the database driver. `decode` now refuses
    both, so the client gets a 422.
  - **Reads of `/api/` from another site are refused.** The cookies are `SameSite=Lax`, so a
    cross-site link carries the session, and the same-origin check skipped every GET. Another
    site could make an HR partner's browser perform an audited read of private details, though it
    couldn't see the response. The check now refuses a safe-method request to `/api/` whose
    `Sec-Fetch-Site` is `cross-site` or `same-site`. `same-origin`, `none`, a missing header, and
    paths outside `/api/` pass as before. A differential test of 3,072 request combinations
    showed the check for requests that change data is unchanged.
  - **The checks follow the path the router matches.** Behind `uvicorn --root-path`,
    `scope["path"]` keeps the prefix that the router strips. Then the read check, the no-store
    middleware, and the error handler's no-store all missed API requests. A new
    `app/core/api_paths.py` gives all three `is_api_request(scope)`. Nothing sets a root path
    today, so this was latent.
  - **New tests pin two decisions that were correct but unguarded.** Either mutation used to pass
    every test.
    - Private details are never sent unless their audit row commits. Without
      `scope="function"` on the private route alone, a failed commit returned a 200 with every
      private value.
    - The list asks `can()` about each card, and the cursor continues from the last row read.
      Taking it from the last card returned stopped paging at a page whose rows were all hidden,
      and 117 people vanished.
  - **The backlog gains three items:**
    - hiding SQL parameters from the error log (any phase)
    - keeping the cursor from naming a hidden person (any phase)
    - requiring the CSRF header on audited reads, for browsers that send no Fetch Metadata
      (Phase 6)
- **Task 26.**
  - **The backlog was merged, not replaced.** Two of the plan's items were already there in other
    words, so they were left out: the OpenAPI error shapes (Phase 2) and the client IP behind the
    load balancer (Phase 8). The Alembic item joined the existing "Any phase" section, and the
    Phase 5 items joined the existing Phase 5 section.
  - **The data inventory's `tenants.created_at` row** says the database stamps it, and that the
    25-hour cap counts from it.
  - **The review corrected three slips in the plan's inventory block.**
    - The `/me` fields include `tenantExpiresAt`.
    - The audit log's `before` and `after` hold non-private fields. `personaKey` is a `/me` field,
      not a directory field.
    - The security log also records its fixed reason phrase.

    Phone numbers are described by their last seven digits, and `sessions` is named as the
    exception to row-level security.
  - **The statutes were re-read on 2026-10-04 and are unchanged.** Gov. Code §12946(a) still
    requires four years. EU AI Act Article 113 still applies Chapter IV, and so Article 50, from
    2 August 2026. It also now states the 2 December 2027 date for Annex III systems itself, so
    the Phase 4 backlog item cites the article instead of law-firm summaries.
- **Task 27.** The roadmap row isn't marked Done yet. Phase 1 closes with the whole-phase review,
  so the row names that review as the next step, and its follow-up PR marks Phase 1 Done with all
  the PR numbers. A literal `<stage 4 PR number>` would also fail the placeholder check.
- **From `/code-review medium`:** no findings.

  Stage 4 ends with 477 tests, 183 of them against the real database, where the plan expects 260
  and 110.

## Backlog

Deferred review findings and later-phase items live in [`../BACKLOG.md`](../BACKLOG.md).
