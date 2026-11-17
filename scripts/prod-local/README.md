# prod-local

`make prod-local` runs the production image (`open-door:prod`) with production settings on its own
empty database, so you can see what a deploy will run. It is a Python launcher (`start.py`) that
reuses `scripts/image/container.py`, not a compose file.

What it does:

1. Starts a throwaway Postgres (the same image as `compose.yaml`) on a private docker network,
   `open-door-prod-local`. The database is not published to the host, has no volume, and is gone when
   you stop. It never touches the development database. Its passwords are made fresh each run and
   travel only in the docker client's environment.
2. Runs the deploy's one-off setup as a separate container: migrations, the login users, and the
   handbook load. This container gets no keyring and no API keys.
3. Runs the API: `APP_ENV=production`, the `anthropic` transport, `APP_ORIGIN=http://localhost:8300`,
   published on `127.0.0.1:8300`. The keyring comes from `apps/api/.keys/keyring` (or
   `ENCRYPTION_KEYRING`), and `ANTHROPIC_API_KEY` (and `VOYAGE_API_KEY`, if set) from `apps/api/.env`.

**Any question asked through it is a paid call.** Production accepts only the real transport, so it
refuses to start without `ANTHROPIC_API_KEY`. Ctrl-C stops the API and the database.

`make prod-local-check` starts everything, fetches `/` (200, with a Content-Security-Policy nonce) and
a route that needs no session, then stops. It asks the model nothing and starts no sandbox.

`SKIP_BUILD=1` reuses the `open-door:prod` image already built. `--port` changes the port (not 5173,
which production refuses as the development origin).

There are no Turnstile keys yet: they arrive with Stage 4.
