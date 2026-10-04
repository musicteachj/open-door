# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This is a development log first and a release log second. Entries accumulate under
**Unreleased** on `dev`, and each release pull request from `dev` into `main` cuts them into a
version (`0.x.y` while the app is being built, `1.0.0` when it is complete).

## [Unreleased]

### Added

- The repository: README, license notice, `.gitignore`, and this changelog.
- **The plan, before any code** (planning). The approved initial plan is kept verbatim and frozen in
  `docs/plans/`. `docs/ROADMAP.md` is the living plan, with a status table for all ten phases. The
  design spec in `docs/specs/` records each decision and the reason for it. Also added:
  - `docs/WHAT-THIS-IS-NOT.md`, which says what the app and its assistant will never do.
  - Six decision records in `docs/adr/`.
  - `CLAUDE.md`, the project rules.
- **The Claude Design brief and handoff format** (planning). `docs/design/BRIEF.md` can be pasted
  into Claude Design to start the design system and screens. The rest of `docs/design/` defines how
  designs come back: tokens, a component inventory, and a per-screen `notes.md` with acceptance
  criteria.
- The README now states the seven rules the assistant never breaks and links to every document.
- **A rule that commits and pull requests must be human readable** (planning): plain-language
  subjects, short explanations of what changed and why, and a standard four-part PR description.
- **The API foundation** (Phase 0, stage 1). A FastAPI backend with a health check at
  `/api/v1/health` that says whether the API can reach its database. Settings are checked at
  startup, so a missing or malformed value stops the server instead of failing later. Every
  response carries a request ID that also appears in the logs, errors come back in the standard
  problem-details format without leaking internal details, and logs are one JSON object per
  line. Also added:
  - A development Postgres with pgvector in Docker, and the first database migration, which turns
    on the vector extension for handbook search. New migrations come out already linted and
    formatted.
  - Integration tests that run against the real database.
  - An export of the API's OpenAPI schema to `apps/web/openapi.json`, which the web app's client
    will be generated from. A check fails if the file falls out of date.
  - A `Makefile` for the everyday commands: `make db`, `make migrate`, `make dev-api`,
    `make openapi`, and `make check-api`, which runs every API check.

  Review findings deliberately left for later phases are recorded in `docs/BACKLOG.md`.
- **The web app foundation** (Phase 0, stage 2). A React app that shows the product name and
  whether the API is reachable: "ok", "degraded" when the database is down, or "unreachable" when
  the API itself is. It talks to the API through a client generated from the API's own schema, so
  the two can't silently drift apart. `make setup` installs everything, `make dev` runs the API and
  the web app together, and `make check` runs every check CI will run.
- **Automatic checks on every push and pull request** (Phase 0, stage 3). GitHub now runs the API
  and web checks, but only for the parts that changed. It scans for leaked secrets and vulnerable
  dependencies, weekly as well, and requires a changelog entry when code changes. Dependabot opens
  grouped weekly update pull requests against `dev`, and pre-commit hooks catch the quick problems
  before a commit is made. `make audit` runs the security scans locally, including a scan of the
  whole git history for secrets.

  Every pull request, docs-only ones included, also gets two quick checks. The docs check covers
  spelling in American English, links between files, and leftover placeholders. The workflow
  check looks for mistakes and security problems in the workflows themselves. Every action is
  pinned to an exact commit, and Dependabot waits 7 days before proposing a new release.
- **The Phase 1 spec** (Phase 1, planning). `docs/specs/` now describes how Phase 1 delivers its
  three pieces: tenancy (every visitor's sandbox company is walled off in the database), identity
  (signing in as a persona through a session cookie), and permissions (one function decides who
  can see what). It was checked against OWASP, PostgreSQL, NIST, and California guidance before
  being written down, and it records two problems that checking found: Postgres can't bulk-load
  with `COPY` under row-level security, and a cleared tenant setting reads back as an empty
  string. A new decision record, ADR 0007, explains why sessions last as long as the sandbox.
  The implementation plan in `docs/plans/` splits the work into four stages, each a pull request.
  Every code block in it was built and run before it was written down.

- **Tenant isolation in the database** (Phase 1, stage 1). Each sandbox company's data now lives
  in tables that Postgres itself keeps apart, with row-level security. The API sees only the rows
  of the company its transaction belongs to, and a transaction with no company sees nothing, even
  on a reused database connection. A second rule shows a person's private details only to that
  person and to HR. Also added:
  - The eight Phase 1 tables: sandbox companies, locations, departments, people, private details,
    holidays, sessions, and an audit log that the API can add to but never change. A sandbox can
    live at most 25 hours, and the database stamps its creation time itself.
  - Separate database logins. The API connects as its own user, which owns nothing and can't
    skip the security rules. Migrations run as the database owner, and a cleanup user can delete
    only expired sandboxes. `make db` now creates the login users after migrating, from the URLs
    in `apps/api/.env`. The script that creates them refuses any existing user with powers that
    would skip the rules, and never sends a password to the database in plain text.
  - Tests against the real database for each guarantee: isolation, the exact privileges of each
    role, the private-details rule, the append-only audit log, and cleanup. Each was shown to fail
    when its rule is removed. CI also undoes and reapplies every migration
    (`make migrations-roundtrip` locally), so a migration that can't be reversed fails the build.
  - `APP_ORIGIN`, the web app's address, for the same-origin check that stage 3 adds.

  This closes three backlog items: migrations run as a separate role, migrations are tested in
  reverse, and the health check reaches the database engine through a typed accessor that fails
  with a clear message.
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
  - Tests that the same inputs always build the same company, that every row gets its own ID,
    that the personas and reporting lines are right, that Priya and Leo manage no one, that two
    sandboxes with identical people sit side by side in the database, and that creating a
    sandbox takes under 2 seconds at the 95th percentile.
- **Signing in** (Phase 1, stage 3). A visitor can now start a sandbox company and sign in to it
  as one of four personas: Priya, Mateo, Marcus, or Dana. The session lives in a cookie the page's
  scripts can't read, and it ends when the sandbox does, 24 hours after it was created. Every
  request that changes something must come from the app itself, and a signed-in one must also
  carry a CSRF token (a second secret that another website can't read), so no other site can act
  on a visitor's behalf. Also added:
  - Four endpoints. `POST /api/v1/sandboxes` creates and seeds a sandbox and signs the visitor
    in. `GET /api/v1/me` says who is signed in. `PUT /api/v1/session/persona` switches persona and
    replaces both tokens, so the old ones stop working at once. `DELETE /api/v1/session` signs
    out. Signing out in one tab while switching in another can't leave a session behind.
  - The policy layer: one pure function, `can()`, that decides who may see what, refuses
    anything it has no rule for, and answers only a strict yes or no. Like the domain rules, it
    may not import any framework or database code, which the import check enforces.
  - An audit log entry for each sandbox created, persona switched, and session ended. Every
    refused request goes to a security log instead: a missing or expired session, a request from
    another site, or a wrong CSRF token. No log ever holds a raw token, and the audit log refuses
    private fields at any depth.
  - Every API response is marked `Cache-Control: no-store`, so no cache can hand one visitor's
    data to another.
  - The web app's generated API client now includes these endpoints. The screens start using them
    in Phase 2.

  This closes the backlog item to keep the health check open: it reads no session, and the
  same-origin and CSRF checks apply only to requests that change something.
- **The directory and private details** (Phase 1, stage 4). A signed-in persona can now read the
  company directory and, where allowed, a person's private details. The policy layer decides:
  everyone in the company sees the directory, and only the person themselves and HR see private
  details. A manager gets no special view of their reports' private details. Each read of private
  details goes into the audit log, which records the names of the fields returned, never their
  values, and the details are never sent unless that audit entry is saved. Also added:
  - Three endpoints. `GET /api/v1/people` lists the directory a page at a time, 50 by default
    and up to 100. `GET /api/v1/people/{id}` returns one person's directory card, and
    `GET /api/v1/people/{id}/private` their private details. A page cursor the API didn't issue
    is refused.
  - Reads of the API from another website are now refused as well, not only requests that change
    something. Reading private details writes an audit entry, so without this another site could
    make an HR partner's browser perform a read in their name. Links into the web app, the health
    check, and scripts are unaffected.
  - Tests over HTTP of every persona against themselves, Leo, and Dana, for both the directory
    and private details. They also show that a person from another sandbox is never found, and
    that a directory card carries none of the private or `/me`-only fields.
  - `docs/DATA-INVENTORY.md`, which lists every table and column: what it holds, why, who can
    see it, and how long it's kept. It notes that a real deployment would keep audit records for
    4 years, as California requires, instead of deleting them with the sandbox.
  - The backlog now holds the later-phase findings from the Phase 1 review, each with its source.
  - The web app's generated API client includes the three endpoints.

  The API now recognizes its own requests by the path its router matches, so the no-store and
  same-origin rules still hold if it is ever served under a path prefix. With this stage, all of
  Phase 1 is built: tenancy, identity, and permissions are proven by tests, over HTTP and in the
  database. A review of the whole phase comes before its release.

### Changed

- **A whole-phase review at the end of every phase** (project rules). After a phase's last PR
  merges, `/code-review high` runs on the phase's application code, to catch problems between
  stages that per-PR reviews can't see. Tests, generated files, and docs are left out, because
  they were reviewed with their stage's code. The phases that guard the invariants (1, 4, and 6)
  also get one security reviewer, briefed with those invariants and told to prove findings with
  small experiments. `/code-review max` was the first choice for those phases. It was dropped
  after its run on Phase 1 used up the session limit before finishing, and it is never used now,
  like the billed `/code-review ultra`.

- **The PR-size guideline counts the code that needs reading** (project rules). The 1,500-line
  trigger now counts application code, migrations, scripts, and config, not tests, generated
  files, or docs, and a PR over the guideline gives a short reading guide. Security-heavy work
  carries many tests, which inflated the old count without adding much to read.

- **Quieter dependency updates** (tooling). Dependabot now checks monthly instead of weekly, and
  proposes only patch and minor updates. A major version, such as TypeScript 7 or the types for a
  newer Node, is a deliberate decision made by hand in its own pull request.

- **The pre-PR code review covers the whole branch** (project rules). `/code-review medium` now
  reviews everything the pull request will contain, measured against its base branch, not just
  the uncommitted changes. That closes a gap where a commit already on the branch could go
  unreviewed.

- **An effort level for each kind of session** (project rules). `CLAUDE.md` now says which Claude
  Code effort level suits planning, building, reviewing, and debugging, and asks Claude to name
  the level at the start of each session. The roadmap's next step names it too. Running every
  session at `xhigh` made each step, and each agent a session launched, think harder than the work
  needed.

- **The data inventory stays current** (project rules). `CLAUDE.md` now asks that a new table,
  column, cookie, or log field update `docs/DATA-INVENTORY.md` in the same change.

### Fixed

- **One list of safe methods** (Phase 1 close-out). The same-origin check treated `TRACE`
  as a method that changes nothing, while the CSRF check didn't. No route accepts `TRACE`, so
  nothing could exploit it, but the two checks now share one list (`GET`, `HEAD`, `OPTIONS`) and
  can't drift apart. The default persona for a new sandbox is also defined in one place.

### Security

- **Starting a new sandbox audits the end of the old session** (Phase 1 close-out). A visitor who
  starts a second sandbox has their first session ended, but that happened inside the new
  sandbox's transaction, so the first sandbox's audit log never recorded it. The old session now
  ends in its own transaction, scoped to its own sandbox, which writes `session.ended` there
  (invariant 7: every action is audited).
- **The whole-phase review of Phase 1.** `/code-review high` on the phase's application code and
  one security reviewer, briefed with tenant isolation and the audit log, checked the seams
  between the four stages: the database roles with sessions, the transaction-scoped tenant
  settings, seeding, persona switching with private reads, the same-origin and CSRF checks, the
  audit log, and the cleanup role. They found nothing high or medium. The fixes above came from
  it, and the other findings are in `docs/BACKLOG.md` under the phase that needs them.
