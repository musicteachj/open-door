# Backlog

Findings from reviews that were deliberately deferred, each with the reason and the phase that
should pick it up. When one is done, delete it here and record it in the changelog.

## Phase 1: tenancy, identity, permissions

- **Don't run Alembic inside an async test.** `env.py` calls `asyncio.run`, which fails inside a
  running event loop, and `fileConfig` resets the root log handlers. Test setup should run
  `alembic upgrade head` as a subprocess, or from a synchronous session fixture.

## Any phase

- **Stop a person from managing themselves, directly or in a loop.** `people.manager_id` has no
  `CHECK (manager_id <> id)` and nothing prevents a reporting loop. Phase 1 is safe: the API can't
  update people, the seed has no loops, and `load_actor` drops the actor from their own reports.
  Whichever phase first grants `UPDATE` on `people` must add the check, and refuse an update that
  would create a loop. Otherwise approval rules could let someone approve their own request.
  (Stage 3 security review.)

- **Check `Origin` on any WebSocket endpoint.** The same-origin middleware passes WebSocket
  connections through untouched, because none exist. Whichever phase adds one must refuse a
  cross-site `Origin` on the handshake, against cross-site WebSocket hijacking. (Stage 3 security
  review.)

- **Guard writes to private details as well as reads.** The database rule that limits
  `person_private` to the person and HR covers `SELECT` only, because the API can't yet update or
  delete those rows. Whichever phase first grants `UPDATE` or `DELETE` on `person_private` must
  add restrictive policies for them in the same migration. (Stage 1 security review.)

## Phase 2: design system, shell, sandbox entry

- **Send the CSRF token from the web client.** The generated client sends no `X-CSRF-Token`, so
  every state-changing call would get a 403. Add an Orval `override.mutator`: a custom fetch that
  reads `__Host-od_csrf` from `document.cookie` on every unsafe request. Read it fresh each time,
  because it changes when a sandbox is created and when a persona switches. Keep
  `Content-Type: application/json`. (Stage 3 security review.)
- **Reset client state when the identity changes.** Clear every TanStack Query cache on a persona
  switch or sign-out. Treat any 401 as "go to sandbox entry", and never auto-retry a
  state-changing request after a 403. (Stage 3 security review.)
- **Describe the real error shapes in the OpenAPI schema.** The schema shows FastAPI's default
  422 body (`detail`), but the API returns problem details (`errors`), and it doesn't list the
  401, 403, and 404 responses at all. Declare `responses=` with a `Problem` model on each route,
  so the generated client's error types are right. (Stage 3 security review.)
- **Check the `__Host-` cookies in each target browser.** They are `Secure`. Chrome and Firefox
  accept them on `http://localhost`, but Safari has historically refused them. Keep `/api` on the
  same origin through the Vite proxy, and test sign-in in each browser the demo supports.

- **Send JSON as JSON.** The same-origin check refuses a state-changing request whose body isn't
  `application/json`. Orval's generated client sets the header. A hand-written
  `fetch(url, { method: "POST", body: JSON.stringify(x) })` sends `text/plain` and gets a 403, so
  any request outside the client must set `Content-Type: application/json` itself. (Stage 3
  security review.)

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

- **Make sign-out end a session's replacements too.** If one tab switches persona while another
  signs out, the switch replaces the session first. The sign-out then finds nothing to end and
  answers 204, but the new persona's session stays valid until the sandbox expires. Give each
  session a `family_id` that rotation carries over, and have sign-out delete the whole family.
  The race needs two tabs acting within milliseconds, in a 24-hour sandbox, and exposes nothing
  across users. (`/code-review medium` on Phase 1, stage 3.)

- **Cap request body size.** Nothing limits it: a 40 MiB JSON body to `POST /sandboxes` was read
  and parsed in full, using about 120 MiB of memory. Phase 1 already reads the body before any
  session check. Cap bodies at about 64 KiB in the ASGI layer or at the proxy, so a few large
  requests can't exhaust a task's memory. (Stage 3 security review.)

- **Require `APP_ORIGIN` in production.** It defaults to `http://localhost:5173`, so a production
  deploy that forgets it refuses every state-changing request. That fails closed, but silently.
  Make settings refuse to start when `APP_ENV=production` and `APP_ORIGIN` is still the default.
  (Stage 3 security review.)
- **Trust forwarded client IPs only from the load balancer.** Security events log the client IP
  that uvicorn reports. Behind the load balancer that depends on `--forwarded-allow-ips`. Setting it
  to `*` would let a client spoof the logged IP, so list only the load balancer's addresses.
  (Stage 3 security review.)

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
