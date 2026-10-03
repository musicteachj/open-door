# Backlog

Findings from reviews that were deliberately deferred, each with the reason and the phase that
should pick it up. When one is done, delete it here and record it in the changelog.

## Phase 1: tenancy, identity, permissions

- **A typed engine accessor.** `request.app.state.engine` is untyped (`Any`), and a missing
  lifespan gives a 500 instead of a clear error. Add `get_engine(request) -> AsyncEngine` (for
  example in `app/api/deps.py`), build the Phase 1 `get_session` dependency on it, and keep the
  health check on a bare connection so it stays independent of row-level security.
- **Exempt `/api/v1/health` from authentication and CSRF.**
- **Migrate as a separate database role.** `migrations/env.py` reads only `DATABASE_URL`. Once
  the app connects as a non-owner role, migrations need the owner. Add a setting such as
  `MIGRATION_DATABASE_URL` that `env.py` prefers, and make sure that role can run
  `CREATE EXTENSION`.
- **Don't run Alembic inside an async test.** `env.py` calls `asyncio.run`, which fails inside a
  running event loop, and `fileConfig` resets the root log handlers. Test setup should run
  `alembic upgrade head` as a subprocess, or from a synchronous session fixture.
- **Test that migrations reverse cleanly.** Add a CI step that runs `alembic downgrade base` and
  then `alembic upgrade head` again. Row-level security policies and roles make downgrades easy to
  break, and nothing exercises them today.

## Phase 4: assistant core

- **Graceful shutdown with open streams.** Streaming responses delay shutdown, and the engine is
  only disposed after they finish. Set uvicorn's `--timeout-graceful-shutdown` below the ECS
  `stopTimeout`.

## Phase 8: hardening and deploy-readiness

- **One source for tool versions.** The gitleaks version is written in three places: the Security
  workflow, the `Makefile`, and the pre-commit config. The ruff hook's version separately follows
  `uv.lock`. Dependabot has a `pre-commit` ecosystem that could keep the hook versions current.
  Add it with the same 7-day cooldown, and make the `Makefile`'s hand-bumped versions the only
  manual ones.
- **The pre-commit hook lives in uv's cache.** `uvx pre-commit install` points the git hook at a
  cached Python, so `uv cache clean` breaks commits until `make setup` runs again. Installing it
  with `uv tool install pre-commit` would make the hook durable.
- **Audit only the app's dependencies.** `uv run --with pip-audit` also audits pip-audit's own
  dependencies, so an advisory in one of those would fail the Security workflow for a reason
  unrelated to the app. The lockfile-only form is
  `uv export --locked --no-emit-project | uvx pip-audit -r - --no-deps --disable-pip`.

- **Pin the pgvector image.** Use a specific `0.8.x-pg17` tag in `compose.yaml` and CI, so
  development and CI run the same extension version.
- **`ping()` has no hard wall-clock bound.** If canceling the query stalls on the network,
  closing the connection can take longer than the timeout, because SQLAlchemy shields the close.
  The orchestrator's own probe timeout covers it; revisit only if health checks need a strict
  bound.
- **Hide the API docs in production.** Set `docs_url`, `redoc_url` and `openapi_url` to `None`
  when `APP_ENV=production`, and keep `app.openapi()` working for the schema export. Also drop
  the `server: uvicorn` header (`--no-server-header`) and send `Cache-Control: no-store` on
  health.
- **Keep probe traffic out of logs and traces.** Filter `/api/v1/health` from `uvicorn.access`,
  and from OpenTelemetry if it's enabled.

## Phase 9: deploy to AWS

- **Separate liveness from readiness.** ECS container health checks must not depend on the
  database, or an RDS failover would restart every task. Add `GET /api/v1/health/live`, which
  never touches the database, for the container check, and keep `/api/v1/health` as the load
  balancer's readiness check.
- **Align the ping and probe timeouts.** The ping and asyncpg connect timeouts are both 5 s, the
  same as the default load balancer and ECS probe timeouts, so a blackholed database times the
  probe out instead of returning a clean 503. Use about 2 s for the health ping, or a probe
  timeout of 6 s or more.
- **Protect the health endpoint from abuse.** Every call is an unauthenticated database round
  trip. Cache the result for 1–2 s with a single in-flight check, or rate-limit the path at the
  load balancer.
