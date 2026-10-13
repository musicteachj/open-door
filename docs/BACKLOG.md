# Backlog

Findings from reviews that were deliberately deferred, each with the reason and the phase that
should pick it up. When one is done, delete it here and record it in the changelog.

## Any phase

- **Locally, the browser tests can reuse a stale server.** `playwright.config.ts` sets
  `reuseExistingServer` off CI, so a preview already on 4173, or an older API on 8100, is tested
  without a rebuild, and `make check` can pass or fail against old code. CI always starts fresh
  servers. Stop old servers before `make e2e`, or run with `CI=1`. (Phase 2 close-out review.)
- **Local development in Safari-family browsers.** WebKit drops every `Secure` cookie on
  `http://localhost`, so the `__Host-` session cookies never stick and sign-in ends at "This
  sandbox has reset." Chromium and Firefox keep them: the session round trip passed in both. Every
  deployed origin is HTTPS, so this is a note for local development, not a defect. Develop and run
  the browser tests in Chromium or Firefox. (Phase 2 stage 2b, checked in WebKit.)
- **Decide whether loading skeletons animate.** The design draws them static, with no shimmer or
  pulse, and the build matches (the skeleton and skeleton-row tests assert it). The owner noticed
  the stillness in the Stage 4a gallery review and may want motion. That's a design change first,
  in Claude Design, then the build. Any animation must stop under `prefers-reduced-motion`, which
  `base.css` already handles. (Phase 2 stage 4a gallery review.)
- **Don't run Alembic inside an async test.** `env.py` calls `asyncio.run`, which fails inside a
  running event loop, and `fileConfig` resets the root log handlers. Test setup should run
  `alembic upgrade head` as a subprocess, or from a synchronous session fixture. Phase 1's tests
  never needed to, because CI runs the migration round trip as plain commands, but a later test
  that runs migrations will.

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

- **Keep the directory cursor and the facet counts from naming a hidden person.** The next cursor is
  the sort key of the last row read, so paging continues past cards the policy layer hides. The
  directory's facet counts (Phase 2) skip the per-card check altogether. Every card is visible in
  Phase 1, so it reveals nothing. Whichever phase first makes the `directory.read` rule refuse
  anyone must encrypt the cursor, or move the filter into the query, and count only the cards it
  shows. Taking the cursor from the last card returned instead is wrong: a page whose rows are all
  hidden would end the directory early. (Stage 4 security review.)

- **Make the HR flag part of the tenant context, and reapply it after a persona switch.**
  `app.is_hr` isn't in `TenantContext`: the transaction hook clears it, and only `signed_in` turns
  it back on. A persona switch also keeps the old persona's `app.person_id` and `app.is_hr` for
  the rest of its request. Neither matters today, since nothing after the switch reads
  `person_private`, and no other tenant session acts for HR. The security reviewer proved the
  switch returns the right `/me` both ways. Whichever phase first reads private details outside
  `signed_in`, or after `rotate_session`, must fold `is_hr` into `TenantContext` and reapply the
  context for the new actor. (Phase 1 close-out review.)
- **`route_path` copies a private Starlette helper.** `app/core/api_paths.py` repeats
  `starlette._utils.get_route_path`, so the no-store and same-origin rules match the path the
  router routes. On a Starlette upgrade, check that the two still agree. (Phase 1 close-out
  review.)
- **Search rebuilds passage text on its own.** `passage_texts` in the handbook search module
  repeats `Passage.text` from the handbook domain over the stored JSON. They agree today; if one
  changes how a list item reads, the excerpt and the hit's passages drift from the indexed chunk
  text. Build both from one helper. (Phase 3 close-out review.)
- **The profile page sends its URL's person ID unencoded.** `/directory/..%2Fme` asks
  `/api/v1/people/../me`, which the URL parser resolves to `/api/v1/me`, and `/directory/facets`
  asks the facets route; either way the page renders the wrong response. It's the session's own data, so nothing leaks, but the page breaks. Encode the
  ID and refuse "." and ".." as the handbook hooks now do, ideally in one shared helper for every
  ID taken from a URL. (Phase 3 close-out review, in Phase 2 code.)
- **The directory's filters can lose a search typed just before them.** Picking a location,
  department, or "My team" within 250 ms of typing pushes an entry without the search, so Back
  loses it. The handbook's Show filter had the same bug; it now writes the pending search first
  (`flushSearch`), and the directory's filters should do the same. (Phase 3 close-out review, in
  Phase 2 code.)
- **The error page doesn't retry a cached error after navigating away and back.** A query that
  throws to the route's error page doesn't retry its cached error on mount, and the page resets
  only from its Retry button. Coming back within the cache time shows the error again with no new
  request. Resetting on navigation would fix it for every page, and let the handbook's overview
  use one cache entry. (Phase 3 close-out review, in Phase 2 code.)
- **State names live in two places.** The API's applicability code and the web's handbook labels
  each keep a state-code-to-name table, so a new state needs both (Georgia did). Have the API send
  the names, and drop the web's copy. (Phase 3 close-out review.)

## Handbook content

- **A military leave section.** The handbook has none. A company section under the federal
  reemployment law for service members (USERRA) comes first; state addenda follow, such as
  Georgia's leave for state guard members (O.C.G.A. §38-2-279, not verified). (Phase 3 stage 6.)
- **A Georgia persona,** if the owner wants one: a fifth sign-in card for an Atlanta employee,
  with a design pass on the landing page first and a migration for the new persona key. Georgia is
  covered today by Atlanta employees in the directory and Georgia askers in the eval. (Phase 3
  stage 6.)

## Phase 4: assistant core

- **Map search hits to `search_result` blocks, and open the passage panel on a citation's
  passage.** Each `search_handbook` hit carries its deep link, title, and passage texts, so it
  maps one to one onto a Claude `search_result` block, and a citation's block index names a
  passage. Call `embed_query` before opening the database session, and take the version only from
  `pinned_version_id`. A section can appear twice, once per chunk; dedupe if the answer view
  wants one card per section. (Phase 3 spec, "The shape Phase 4 cites".)
- **Record why the assistant is not a high-risk AI system.** Annex III of the EU AI Act lists
  systems used for employment decisions as high-risk. Article 6(3) exempts a system that doesn't
  profile people or materially influence decisions, and Article 6(4) requires that assessment to
  be documented. The governance document should record it. The Annex III obligations apply from
  2027-12-02.
  Source: EU AI Act Annex III (https://artificialintelligenceact.eu/annex/3/) and Article 6
  (https://artificialintelligenceact.eu/article/6/), read on 2026-10-03, and Article 113
  (https://artificialintelligenceact.eu/article/113/), read on 2026-10-04, which sets
  2 December 2027 "as regards AI systems classified as high-risk pursuant to Article 6(2) and
  Annex III". These pages are an unofficial consolidation, not EUR-Lex.
- **The AI disclosure is already required.** Article 50 of the EU AI Act, which requires telling
  people they are talking to an AI, has applied since 2026-08-02. Invariant 7 covers it; the
  Phase 4 disclosure should cite the article.
  Source: EU AI Act Article 113 (https://artificialintelligenceact.eu/article/113/), read on
  2026-10-04. Article 50 is in Chapter IV, which follows the general date of 2 August 2026.
- **Graceful shutdown with open streams.** Streaming responses delay shutdown, and the engine is
  only disposed after they finish. Set uvicorn's `--timeout-graceful-shutdown` below the ECS
  `stopTimeout`.

## Phase 5: time off

- **Show team coverage beside a manager's approval.** When Marcus reviews a request, show who else
  on his team is off on those dates. It's context only: the assistant never recommends approving
  or denying (invariant 5). (2026-10-06 design brainstorm.)
- **Check the nav after a switch from a manager to an employee.** `navFor` builds the nav from the
  fresh `/me` inside a remounted shell, but in Phase 2 everyone sees only Ask and Directory, so the
  manager's items disappearing after a switch can't be observed. When Approvals becomes available,
  add a `navFor` test and extend the shell's switch test to prove the employee never sees it.
  (Phase 2 stage 5 security re-check.)
- **Keep a write from the old identity out of the new cache.** `resetIdentity` clears the query
  cache, but a mutation already in flight still runs its callbacks when it finishes. If its
  `onSuccess` calls `setQueryData`, the old person's data lands in the new person's cache. Phase
  2's only writes start or end a session, so nothing does this yet. Write hooks should invalidate
  queries rather than set their data. Where one must set data, `resetIdentity` should count
  identities and the write should check the count first. (Phase 2 stage 2 security review.)
- **Seed last year's holidays too.** A sandbox stores the holiday calendar for its anchor year and
  the next. One created in early January therefore lacks the previous December's closures, so a
  question about leave taken over the holidays just before it would miss them. If the time-off
  engine answers past-dated questions, seed the prior year as well. (Stage 2 review.)
- **Never treat the anchor date as today.** `create_sandbox` sets `tenants.anchor_date` to
  today's date in UTC, not in any location's timezone. Every seeded location is in the US, so a
  sandbox created in the US evening is anchored to the location's tomorrow. Seed dates are only
  shifted by a day, which is harmless, but invariant 2 needs today's date in the location's
  timezone. The time-off engine and the per-turn context must compute today from the location's
  `timezone`, never from `anchor_date`. A test should create a sandbox at, say, 03:00 UTC and
  check that a Pacific-time employee's "tomorrow" is the right date. (`/code-review medium` on
  the `v0.1.0` release.)

- **Record who confirms a proposal as an audit event of its own,** separate from the action it
  executes, so the log shows both who proposed and who decided.
- **Grant `UPDATE` only where requests and approvals need it.** Phase 1 grants the API no
  `UPDATE` anywhere, and the exact-grants test fails on any grant it doesn't expect.

Source for both: [the Phase 1 spec](specs/2026-10-03-phase-1-tenancy-identity-permissions.md#later-phases).

## Phase 6: cases and escalation

- **The hand-off says only what's true.** Before the person writes anything, say:
  - only HR sees it, never managers;
  - it's encrypted;
  - when to expect a reply;
  - the AI writes HR a neutral summary.

  Never say "the AI won't read it": the guard reads every message, and `summarize_case` is
  AI-written. (2026-10-06 design brainstorm.)
- **Encrypt case narratives.** They are the most sensitive text the app will hold.
  Source: [the Phase 1 spec](specs/2026-10-03-phase-1-tenancy-identity-permissions.md#later-phases).

- **Require a header no navigation can send on audited reads.** A read of `/api/` whose
  `Sec-Fetch-Site` says it came from another site is refused, so another site can't make an HR
  partner's browser perform an audited read. Two cases still pass: a browser too old to send the
  header (Safari before 16.4, for example), and a navigation the user starts themselves, which
  sends `none`. Before case reads are audited, require the `X-CSRF-Token` header on audited reads
  too, since no navigation can send it. Today an attacker would also need a person's ID. Seeded
  IDs are derived from the sandbox's random tenant ID, which is shown only inside that sandbox.
  (Stage 4 security review.)

## Phase 7: AI Ops console, reviewer experience, model decision

- **Report the questions the handbook couldn't answer.** The console lists them, so HR can see
  what to write next. The question text is user-written, so it's untrusted data, and it's redacted
  for guard-flagged turns. Fold the "design notes" idea into the tour and the "How it's built" page
  rather than adding a third explainer. (2026-10-06 design brainstorm.)

## Phase 8: hardening and deploy-readiness

- **Delete handbook versions no sandbox uses.** Each `make ingest` of changed text adds a version,
  and nothing removes old ones. A cleanup step can delete unpublished versions and published ones
  that are neither the newest nor pinned by any sandbox; the foreign key already refuses to delete
  a version in use. (Phase 3 spec, Data model.)
- **Make the directory's counts cheaper.** `GET /people/facets` runs up to five queries one after
  another (total, matching, the location and department menus, and "My team") on every debounced
  search. Total and matching can be one `count(*) FILTER (WHERE …)`, and the total doesn't change
  with the filters. Measure in the load test first. (Phase 2 close-out review.)
- **Keyboard shortcuts.** Add `/` to focus the composer (never while typing in a field) and ⌘K to
  jump to a page. Both need screen-reader and conflict checks. (2026-10-06 design brainstorm.)
- **Notice another tab's session change at once.** If another tab switches persona or signs out,
  this tab keeps showing what it had loaded, such as HR's view of someone's private details, until
  it next refetches `/me`: on focus, on navigation, or after a 401. It's the same visitor, and every
  new read goes out with the new cookie and is refused, so nothing new leaks. Listen for the
  change and refetch `/me` straight away, for example with a `BroadcastChannel` message from the
  tab that changed it. (Phase 2 stage 6 security check.)
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
  its `SELECT` on the table. (Stage 1 security review.) `od_app` can also insert and delete any
  tenant's sessions, with any expiry: the Phase 1 close-out security review forged an HR session in
  another tenant from `psql`. No route can do this, since `start_session` builds the row through a
  tenant-scoped select, but SQL access as `od_app` would become a working login anywhere. Enable
  row-level security on `sessions`, with an insert policy that requires the current tenant and
  person, keep the expiry within the tenant's, and test that an insert for another tenant fails.
- **Keep the owner's database URL out of the API.** The API's settings load
  `MIGRATION_DATABASE_URL` and `CLEANUP_DATABASE_URL` though it uses neither, so the API process
  holds the owner's credentials, which bypass row-level security. Give Alembic and the bootstrap
  script their own settings class, and give the API task only `DATABASE_URL` in the AWS secrets
  contract. (Phase 1 close-out review.)
- **One transaction per signed-in request.** `signed_in` looks the session up in one transaction
  and does the tenant's work in a second, so each request pays two round trips and two pool
  checkouts, and a session can end between them. Set the tenant context in the lookup's own
  transaction. (Phase 1 close-out review.)
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

From the Phase 1 review ([the spec's Later phases](specs/2026-10-03-phase-1-tenancy-identity-permissions.md#later-phases)):

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

## Phase 9: deploy to AWS

- **Don't share a Postgres server between environments that reuse these role names.** Roles
  belong to the whole server, and Postgres lets every role connect to every database by default.
  If staging and production lived on one server, a login made for one could connect to the other,
  inherit `od_app`, and read any tenant. Both bootstrap runs would also reset the shared login's
  password. Either give each environment its own server, or revoke `CONNECT` on the database from
  `PUBLIC` and grant it only to that database's own logins in the bootstrap script.
  (`/code-review medium` on Phase 1, stage 1.) Migration 0002 also reuses an existing `od_app` or
  `od_cleanup` after checking what that role is a member of, but not which roles are members of
  it, so another database's login granted `od_app` would inherit Open Door's access. Check
  `pg_auth_members` in both directions. (Phase 1 close-out review.)

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
