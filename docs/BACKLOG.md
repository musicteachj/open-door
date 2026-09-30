# Backlog

Findings from reviews that were deliberately deferred, each with the reason and the phase that
should pick it up. When one is done, delete it here and record it in the changelog.

## Phase 1: tenancy, identity, permissions

- **A typed engine accessor.** `request.app.state.engine` is untyped (`Any`), and a missing
  lifespan gives a 500 instead of a clear error. Add `get_engine(request) -> AsyncEngine` (for
  example in `app/api/deps.py`), build the Phase 1 `get_session` dependency on it, and keep the
  health check on a bare connection so it stays independent of row-level security.
- **Exempt `/api/v1/health` from authentication and CSRF.**

## Phase 4: assistant core

- **Graceful shutdown with open streams.** Streaming responses delay shutdown, and the engine is
  only disposed after they finish. Set uvicorn's `--timeout-graceful-shutdown` below the ECS
  `stopTimeout`.

## Phase 8: hardening and deploy-readiness

- **Pin the pgvector image.** Use a specific `0.8.x-pg17` tag in `compose.yaml` and CI, so
  development and CI run the same extension version.
- **`ping()` has no hard wall-clock bound.** If cancelling the query stalls on the network,
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
