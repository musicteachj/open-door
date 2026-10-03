# Backlog

Findings from reviews that were deliberately deferred, each with the reason and the phase that
should pick it up. When one is done, delete it here and record it in the changelog.

## Phase 1: tenancy, identity, permissions

- **Exempt `/api/v1/health` from authentication and CSRF.**
- **Don't run Alembic inside an async test.** `env.py` calls `asyncio.run`, which fails inside a
  running event loop, and `fileConfig` resets the root log handlers. Test setup should run
  `alembic upgrade head` as a subprocess, or from a synchronous session fixture.

## Any phase

- **Guard writes to private details as well as reads.** The database rule that limits
  `person_private` to the person and HR covers `SELECT` only, because the API can't yet update or
  delete those rows. Whichever phase first grants `UPDATE` or `DELETE` on `person_private` must
  add restrictive policies for them in the same migration. (Stage 1 security review.)

## Phase 4: assistant core

- **Graceful shutdown with open streams.** Streaming responses delay shutdown, and the engine is
  only disposed after they finish. Set uvicorn's `--timeout-graceful-shutdown` below the ECS
  `stopTimeout`.

## Phase 5: time off

- **Seed last year's holidays too.** A sandbox stores the holiday calendar for its anchor year and
  the next. One created in early January therefore lacks the previous December's closures, so a
  question about leave taken over the holidays just before it would miss them. If the time-off
  engine answers past-dated questions, seed the prior year as well. (Stage 2 review.)

## Phase 8: hardening and deploy-readiness

- **Data migrations can't see tenant rows on AWS.** With row-level security forced, a table
  owner that isn't a superuser sees no rows. That is the managed-Postgres case, unlike
  development and CI, where the owner is a superuser. A migration that changes data must set the
  tenant context for each tenant, or run under a role made for it. (Stage 1 security review.)
- **Look up sessions without granting the table.** `od_app` can read every tenant's `sessions`
  rows, because a session is looked up before the tenant is known. The spec accepts this. A
  `SECURITY DEFINER` function that returns one session by its token hash would let `od_app` drop
  its `SELECT` on the table. (Stage 1 security review.)
- **Postgres 16 or later.** The bootstrap script grants roles `WITH INHERIT TRUE`, which needs
  Postgres 16. Development and CI run 17. The managed Postgres chosen in Phase 9 must be 16 or
  later.

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

- **Don't share a Postgres server between environments that reuse these role names.** Roles
  belong to the whole server, and Postgres lets every role connect to every database by default.
  If staging and production lived on one server, a login made for one could connect to the other,
  inherit `od_app`, and read any tenant. Both bootstrap runs would also reset the shared login's
  password. Either give each environment its own server, or revoke `CONNECT` on the database from
  `PUBLIC` and grant it only to that database's own logins in the bootstrap script.
  (`/code-review medium` on Phase 1, stage 1.)

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
