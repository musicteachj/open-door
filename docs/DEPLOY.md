# Deploying Open Door

The contract the infrastructure phase copies: what runs, which settings each piece reads, what the
task definitions look like, and what the shared server must provide. The files that deploy it are
in `deploy/` (below); nothing is deployed until the first run of the CI `deploy` job on `main`.
The decisions behind it are in [ADR 0023](adr/0023-phase-9-on-the-shared-portfolio-server.md); the
measurements are in [`CAPACITY.md`](CAPACITY.md).

## What runs

One image, `open-door:prod`, runs as three ECS task definitions on the shared portfolio EC2
instance (bridge networking, behind the shared load balancer):

| Definition | What it does | How it runs |
|---|---|---|
| **API** | Serves the API and the web app on port 8000 (`/app/entrypoint.sh`, the image's default) | A service of one task, rolling deploy, minimum healthy 100%, maximum 200% |
| **Setup** | Migrates, creates the database logins, loads the handbook (`/app/setup.sh`) | A one-off before each service update, started with RunTask. RunTask can't override an entrypoint, so the setup has its own definition. It must exit 0 before the service updates. |
| **Cleanup** | Deletes expired sandboxes and old rows (`/app/cleanup.sh`) | EventBridge Scheduler, hourly, with an alarm on a non-zero exit |

`/app/entrypoint.sh` takes no argument: any argument exits 64, so a mistyped job never serves.

## The deploy files

- `deploy/ecs/web.json`, `setup.json`, and `cleanup.json` are the three task definitions, and
  `deploy/ecs/service.json` creates the service. The fragments below are what they hold.
- `deploy/deploy.sh <image>` registers the three, runs the setup task to completion, then creates or
  updates the service, waits for it to settle on the new revision, runs `deploy/smoke.sh`, and last
  writes the cleanup's revision to `/portfolio/opendoor/cleanup-revision`. A failed setup stops it
  before the service is touched and prints the setup's log.
- The `deploy` job at the end of `.github/workflows/ci.yml` builds and pushes the image, then runs
  `deploy.sh`. It runs on `main` only, after the other jobs pass, and waits for approval in the
  `production` environment. Run the workflow by hand on `main` to redeploy the current commit.
  `deploy/head-of-main.sh` refuses a run whose commit is not the current head of `main`, once before
  the job takes AWS credentials and again right before the image is pushed. A run refused by either
  check pushes and deploys nothing; if a newer run exists it deploys main's head, and otherwise run
  the workflow by hand. A run that passed the second check still deploys if main moves during its
  build and push, and the newer run, queued behind it, deploys after it. The job stops after 58 minutes, and the build and push step after 8 (the worst case is
  8 + 10 for setup + 30 for settling + 5 for smoke + 1 for the rest, 54).
- The setup task counts as done only if every container exited 0 and ECS's stop code is
  `EssentialContainerExited`. A task stopped with any other stop code (a manual stop is
  `UserInitiated`) fails the deploy before the service is touched and names the stop code, even if a
  migration trapped the signal and exited 0 half done; a task whose containers all exited 0 but that
  has no stop code at all is not trusted either, and fails with its own message; a task that never started
  (`TaskFailedToStart`) says to check the image pull and the instance's free memory. A task still
  `STOPPING` when the wait gave up counts as finished only if every container has an exit code and ECS
  has set its stop code. A task that stopped just after the wait gave
  up is judged the same way; one still running fails with its ARN and the warning not to re-run.
- `deploy.sh` prints the setup task's log into the Actions log. Checked on 2026-11-24: against
  an unreachable database with a marker password, the setup's scripts and the cleanup printed
  neither a URL nor the password. A real Postgres authentication failure was not exercised.
- `web.json` leaves out `VOYAGE_API_KEY`: it is optional, the setup never embeds, and a missing SSM
  parameter would stop the task from starting.

## The settings

Secrets live in SSM Parameter Store under `/portfolio/opendoor/` (SecureStrings, except
`AI_MONTHLY_BUDGET_USD`, a String). The task definitions name each one in `secrets`, so the values
never sit in a file. "Plain" values sit in the task definition's `environment`.

| Setting | Read by | Kind | Production value or source |
|---|---|---|---|
| `APP_ENV` | API, setup | plain | `production` (the image's default; leave it) |
| `APP_ORIGIN` | API, setup | plain | The site's https origin, planned `https://opendoor.jameslittlefield.net`. Production refuses http, except a loopback origin with a port (`http://localhost:<port>` or `http://127.0.0.1:<port>`), and the development default (`app/core/config.py`, `refuse_a_test_origin_in_production`), and the setup loads the same settings, so it needs it too. |
| `DATABASE_URL` | API, setup | secret | The API's login, `od_app_login`, on the shared Postgres: `postgresql+asyncpg://od_app_login:<password>@172.17.0.1:5432/opendoor` |
| `MIGRATION_DATABASE_URL` | setup | secret | The owner: `postgresql+asyncpg://opendoor_owner:<password>@172.17.0.1:5432/opendoor` |
| `CLEANUP_DATABASE_URL` | setup, cleanup | secret | The cleanup login: `postgresql+asyncpg://od_cleanup_login:<password>@172.17.0.1:5432/opendoor` |
| `ENCRYPTION_KEYRING` | API | secret | The keyring lines (`id:base64`, newest first). The setup needs none. |
| `ANTHROPIC_API_KEY` | API | secret | The key of the "Open Door" workspace, which has a $22 spend limit |
| `VOYAGE_API_KEY` | API | secret, optional | Without it, handbook search is full-text only (`app/main.py` builds no embedder, and `app/modules/handbook/search.py` returns no vector) |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | API | secret | Real Cloudflare keys, set up in Phase 3 of the deploy. Production refuses the test keys. |
| `SANDBOX_IP_HASH_KEY` | API | secret | At least 32 bytes, random |
| `FORWARDED_ALLOW_IPS` | API | plain | The VPC's CIDR, so only the load balancer is trusted (never `*` or `0.0.0.0/0`; production refuses an empty value) |
| `AI_TRANSPORT` | API | plain | `anthropic` (production refuses any other) |
| `AI_MONTHLY_BUDGET_USD` | API | secret (a String parameter) | `20`. Production refuses to start without it. `0` turns live AI off. It lives in SSM so the off switch needs no commit. |
| `AI_PACING_MULTIPLIER` | API | plain | `3` |
| `AI_DAILY_FLOOR_USD` | API | plain | `1.00` |
| `AI_DAILY_BUDGET_USD` | API | plain | `20` (equal to the month, so pacing alone governs) |
| `AI_SANDBOX_BUDGET_USD` | API | plain | `0.50` |
| `SANDBOX_STARTS_PER_HOUR`, `SANDBOX_STARTS_PER_DAY`, `SANDBOX_STARTS_DAILY_TOTAL` | API | plain | `15`, `50`, `1000` (these are the code defaults) |

The cleanup reads `CLEANUP_DATABASE_URL` and nothing else. The setup reads no keyring and no model
key. `PORT` and `HOST` are never set in the deploy.

How the monthly budget paces each day is in [ADR 0011](adr/0011-insert-only-budget-ledger.md).

## The task definitions

JSON fragments, not whole definitions: the family, the image, the roles, and the log configuration
are the infrastructure phase's. Every container runs as the image's user with the same hardened
flags.

**API:**

```json
{
  "portMappings": [{ "containerPort": 8000, "hostPort": 0, "protocol": "tcp" }],
  "memoryReservation": 256,
  "memory": 512,
  "stopTimeout": 30,
  "user": "10001:10001",
  "readonlyRootFilesystem": true,
  "linuxParameters": {
    "capabilities": { "drop": ["ALL"] },
    "tmpfs": [{ "containerPath": "/tmp", "size": 64 }]
  },
  "dockerSecurityOptions": ["no-new-privileges"],
  "healthCheck": {
    "command": [
      "CMD",
      "python",
      "-c",
      "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=3).status == 200 else 1)"
    ],
    "interval": 15,
    "timeout": 5,
    "retries": 3,
    "startPeriod": 20
  }
}
```

There is no CPU reservation. ECS ignores the image's own `HEALTHCHECK`, and the image has no `curl`,
which is why the check is spelled out. The host port is 0 so ECS picks a free port, and the load
balancer's target group follows it.

**Setup:**

```json
{
  "entryPoint": ["/app/setup.sh"],
  "memory": 256,
  "user": "10001:10001",
  "readonlyRootFilesystem": true,
  "linuxParameters": {
    "capabilities": { "drop": ["ALL"] },
    "tmpfs": [{ "containerPath": "/tmp", "size": 64 }]
  },
  "dockerSecurityOptions": ["no-new-privileges"]
}
```

The deploy waits for the task to stop and checks its exit code is 0 before it updates the service.
Each step repeats safely, so a failed setup can be run again. `make prod-local` ran everything under
these flags and nothing wrote outside `/tmp`.

**Cleanup:**

```json
{
  "entryPoint": ["/app/cleanup.sh"],
  "memory": 128,
  "user": "10001:10001",
  "readonlyRootFilesystem": true,
  "linuxParameters": {
    "capabilities": { "drop": ["ALL"] },
    "tmpfs": [{ "containerPath": "/tmp", "size": 64 }]
  },
  "dockerSecurityOptions": ["no-new-privileges"]
}
```

Put an alarm on a non-zero exit, so a stuck cleanup is noticed (it writes one line of counts and no
row contents).

## The load balancer

- **Target group health check:** `GET /api/v1/health/live`, expecting 200. Liveness never touches
  the database, so a database outage doesn't pull the only task out of rotation (ADR 0023).
- **Idle timeout:** 120 seconds, under the image's keep-alive of 130
  (`scripts/image/entrypoint.sh`, `--timeout-keep-alive 130`), so the load balancer closes idle
  connections first. Streams send a keep-alive comment every 15 seconds. If the idle timeout ever
  goes above 120, raise the keep-alive first.
- **Deregistration delay:** 90 seconds.
- **WAF "expensive paths"** for Open Door, with a stricter rate rule: `POST /api/v1/sandboxes` and
  `POST /api/v1/assistant/conversations/*/turns`.

## Shutdown order

When ECS stops the task:

1. The target group drains for the deregistration delay (90 s). This runs first, as the load
   balancer stops sending new requests.
2. ECS sends SIGTERM. uvicorn stops accepting and waits up to 15 s for open requests
   (`--timeout-graceful-shutdown 15`).
3. The app then waits up to 12 s for open answer streams to save their turns
   (`app/main.py`, `STREAM_DRAIN_SECONDS`), before it closes the database engine.

Steps 2 and 3 take at most 27 s and sit inside `stopTimeout` 30. If the graceful timeout is ever
raised, raise `stopTimeout` (at most 120) with it.

## Smoke tests after a deploy

Run these once the service is stable. All must pass. `deploy/smoke.sh` retries each one until it
passes or its window ends: `/` gets 180 seconds, because on a first service creation the load balancer
can answer 503 until it marks the new target healthy, and each later check gets its own 30 seconds
(`SMOKE_FIRST_SECONDS` and `SMOKE_SECONDS` can be set to any whole number of seconds, and
`SMOKE_DELAY_SECONDS`, 5 seconds between tries, to a whole number of at least 1, so the load balancer
is never hit with no pause; anything else exits 2 naming the setting). The first check to run out of time ends the run, so smoke takes under 5 minutes.

1. `GET /` returns 200 (the web app).
2. `GET /api/v1/health` returns 200 (readiness: the database answers). This is for the smoke test
   only; no probe uses it.
3. `GET /api/v1/assistant/availability` returns 200 with `{"available": ...}`.

## The database on the shared server

Open Door shares one Postgres 17 server (with pgvector) that runs as an ECS service on the
instance. Its port is bound to the Docker bridge's gateway, `172.17.0.1:5432`, and never to a
public interface, so all three URLs use that host and port, the database `opendoor`, and the
`postgresql+asyncpg://` scheme (the settings table above). There is no TLS, because the traffic
never leaves the instance's Docker bridge, and no pooler. Passwords are `scram-sha-256`.

1. **Before the init SQL, check `log_statement` is `none`** on the shared server, or run
   `SET log_statement = 'none';` at the start of that psql session (the init superuser may). Also
   run `SET log_min_error_statement = 'panic';` there, because the default (`error`) logs the
   statement text if the `CREATE ROLE` fails. The init SQL sends the owner's password once as a
   literal (`PASSWORD :'od_owner_password'`), and `ddl`, `mod`, and `all` would all write that
   statement, password included, to the server log.
2. **Run `scripts/image/postgres-open-door.sql` once,** as the init superuser, connected to the
   `postgres` database, with `OD_OWNER_PASSWORD` in psql's environment. It creates the owner
   `opendoor_owner` (a non-superuser with `CREATEROLE`) and the database `opendoor`, revokes
   `CONNECT` from `PUBLIC`, and creates the `vector` extension. **The extension must be created
   here:** `CREATE EXTENSION vector` needs a superuser, and the non-superuser owner gets "permission
   denied to create extension" if the migrations try.
3. **Run the setup.** It migrates as the owner. Migration 0020 gives `CONNECT` to the roles `od_app`
   and `od_cleanup`, and the bootstrap creates the two logins from their URLs and refuses to run if
   either role has a member other than those logins.

**Rotating a database password:** change the URL in SSM, run the setup (the bootstrap resets each
login's password from its URL), then force a new deployment of the service (it reads its secrets
only when a task starts).

**Data migrations and row-level security:** the owner isn't a superuser, so with forced row-level
security a data step sees no tenant rows. A migration that changes tenant data must set the tenant
context for each tenant, or turn forcing off around the step as migration 0018 does. `make
prod-local` migrates as a non-superuser owner, so it catches this. Migration 0018's data step needs
the keyring only on a database that already holds denial notes; production starts empty.

## Turning live AI off

Set the SSM parameter `/portfolio/opendoor/AI_MONTHLY_BUDGET_USD` to `0` and force a new
deployment of the service (no commit needed). The assistant stops answering with the
model, and the landing offers the recorded walkthrough in place of the tour. Disabling the Anthropic
key alone also stops spending, but the landing keeps offering the tour.
