# prod-local

`make prod-local` runs the production image (`open-door:prod`) with production settings on its own
empty database, so you can see what a deploy will run. It is a Python launcher (`start.py`) that
reuses `scripts/image/container.py`, not a compose file.

What it does:

1. Starts a throwaway Postgres (the same image as `compose.yaml`) on a private docker network,
   `open-door-prod-local`. The database is not published to the host, has no volume, and is gone when
   you stop. It never touches the development database. Its passwords are made fresh each run and
   travel only in the docker client's environment.
2. Runs the deploy's one-off setup as a separate container from its own entrypoint, `/app/setup.sh`:
   migrations, the login users, and the handbook load. This container gets no keyring and no API
   keys, and a 256 MiB memory limit.
3. Runs the API from the image's own entrypoint (`/app/entrypoint.sh`, which serves and takes no
   command) with a 512 MiB memory limit: `APP_ENV=production`, the `anthropic` transport,
   `APP_ORIGIN=http://localhost:8300`, published on `127.0.0.1:8300`. The keyring comes from
   `apps/api/.keys/keyring` (or `ENCRYPTION_KEYRING`), and `ANTHROPIC_API_KEY` (and
   `VOYAGE_API_KEY`, if set) from `apps/api/.env`.

**Every container runs as production does.** Each gets a read-only root filesystem with a tmpfs at
`/tmp`, all Linux capabilities dropped, and `no-new-privileges` (the flags are
`container.HARDENED_FLAGS`). The limits are 512 MiB for the API, 256 MiB for the setup, and 128 MiB
for the cleanup job. The cleanup job has its own entrypoint, `/app/cleanup.sh`, and reads only
`CLEANUP_DATABASE_URL`. If something in the image needs to write outside `/tmp`, the run fails
instead of hiding it, which is the point.

**Any question asked through it is a paid call.** Production accepts only the real transport, so it
refuses to start without `ANTHROPIC_API_KEY`. Ctrl-C stops the API and the database.

`make prod-local-check` starts everything, then checks: `/` answers 200 with a
Content-Security-Policy nonce and names `https://challenges.cloudflare.com` in `script-src` and
`frame-src`; the live and database health routes answer 200; `/api/v1/assistant/availability`
answers 200 with a boolean `available`; `/openapi.json` and `/docs` do not serve the API schema or
Swagger; and the cleanup container, run once, exits 0 and prints "cleanup finished". Then it stops.
It asks the model nothing and starts no sandbox.

`SKIP_BUILD=1` reuses the `open-door:prod` image already built. `--port` changes the port (not 5173,
which production refuses as the development origin).

The Turnstile keys are Cloudflare's always-pass test keys (`entry_env` in `start.py`), which
production accepts only because the origin is loopback; the API answers them locally and never
calls Cloudflare. A fresh `SANDBOX_IP_HASH_KEY` is made each run.
