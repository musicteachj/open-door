# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This is a development log first and a release log second. Entries accumulate under
**Unreleased** on `dev`, and each release pull request from `dev` into `main` cuts them into a
version (`0.x.y` while the app is being built, `1.0.0` when it is complete).

## [Unreleased]

### Added

- **The directory and profiles** (Phase 2, stage 6), which complete Phase 2's screens.
  - **The directory:** everyone in the company, 50 at a time with Show more, searched by name,
    title, or work email, and filtered by location, department, and "My team" for managers. The
    search and filters live in the address, so a link or Back keeps them, and Back returns to the
    same scroll position.
  - **Profiles:** work details, with the manager and email as links, and private details for the
    person and HR only. Everyone else sees which fields are private and who can see them, and the
    browser never asks for the values.
  - **Browser tests check the private rule against the real API:** another person's profile holds
    no private value in the page or in any response, and HR's read writes an audit event naming
    only the fields.
- **The landing page, the app shell, the assistant home, and the global states** (Phase 2,
  stage 5). A visitor now picks a persona, lands in a private sandbox, and can switch persona or
  sign out.
  - **Landing:** the four personas as cards. Starting a sandbox shows "Setting up Juniper Row…",
    and a failure offers Retry for the same persona.
  - **The shell:** the sidebar and its nav for each role, the persona menu, the content sheet, and
    the rail with the sandbox countdown. Switching shows "Now viewing as Marcus Bell." Below 3
    hours a banner warns before the sandbox resets, and dismissing it lasts for that sandbox in
    this tab. On a phone the shell becomes a top bar.
  - **The assistant home:** a greeting in the location's own time zone, the composer with the AI
    disclosure, and each persona's "Try asking" questions. Until Phase 4 connects the assistant,
    asking gives one fixed, person-written reply.
  - **The global states:** "This sandbox has reset.", a not-found page, and "Something went wrong"
    with the full request reference to quote.
  - **Every acceptance criterion in the four screens' notes has a browser test,** with axe on every
    state, and the capture report has a row for every design screenshot.
- **`make captures`, the design and the build side by side** (Phase 2, stage 4b). A local report
  sets each design specimen beside a photograph of the build's gallery, one row per state, at
  1440 px. The build is photographed after its hover, keyboard focus, or click, and with any menu,
  list, or tooltip open. The owner reviews it before each UI pull request. It needs a network,
  because the design pages load React from a CDN, and CI never runs it.
- **The assistant, landing, form, and directory components** (Phase 2, stage 4a). The rest of the
  pieces the Phase 2 screens are built from, each in the gallery in every state:
  - **Assistant:** the composer, which always shows the AI disclosure and never sends on an empty
    box or while an input method is composing, and the "Try asking" list.
  - **Landing:** the persona card, which announces "Setting up Juniper Row…" and can't start two
    sandboxes.
  - **Forms:** the search field, the filter select with counts beside each option, and the "My
    team" toggle.
  - **Directory:** the table, each row one link, with a skeleton while loading; and the detail
    list, whose locked rows show who can see a field and never its value.
  - **Browser tests** check the real hover colors, the composer's focus halo, axe with a filter
    open, and rows stacking on a phone.
- **The core, navigation, and feedback components** (Phase 2, stage 3). The pieces the shell and
  every page frame are built from, each in the gallery in every state:
  - **Core and status:** the logo, the page header, the empty state, the sandbox indicator, and the
    at-a-glance link and list.
  - **Navigation:** the nav item, and the persona switcher and its menu. The menu starts focus on
    the current persona, and won't open while a switch or sign-out is under way.
  - **Feedback:** the banner, the inline error, and the full-page message, whose heading takes focus
    when it appears. Errors appear beside what failed, never in a toast.
  - **One tested module holds the accessible names,** such as "Approvals, 1 waiting".
  - **The whole gallery fits a 390 px screen,** checked in a real browser.
- **The restyled components, the gallery, and browser tests** (Phase 2, stage 2b).
  - **Nine primitives** built by hand from the design's sketches and tokens: the button, input,
    textarea, select, dropdown menu, tooltip, toast, avatar, and skeleton. A loading button keeps
    its label and stays focusable, toasts are for confirmations only, and every control shows a
    visible keyboard focus ring.
  - **A component gallery** at `/gallery` shows each one in every state. It exists only in
    development and in the browser-test build, and a check fails if it ever reaches a production
    build.
  - **Browser tests** with Playwright drive the built app against the real API: axe finds no
    WCAG 2.2 AA problems in the gallery, with each overlay open too; a visitor can start, switch
    persona, and sign out; nothing scrolls sideways at 390 px; and the focus ring and color
    transitions match the design. They run in `make check` and in a new CI job.
- **The web app's foundation** (Phase 2, stage 2a). The plumbing the Phase 2 screens are built on:
  - **The design's theme.** The approved tokens are the Tailwind theme, and Tailwind's own
    colors, type sizes, radii, and shadows are removed, so components can use only the design's
    names. The fonts are self-hosted. Tests fail if the theme drifts from the design export, or if
    a component uses a raw color.
  - **One way to the network.** Every API call goes through `apiFetch`. It sends the CSRF token on
    writes, only to the app's own origin, reading it fresh each time, and sends JSON as JSON. A
    failure throws an error carrying the status, the problem details, and the request ID.
  - **Query rules.** Reads never retry a client error, and retry a server or network failure once.
    Writes never retry. A test forbids overriding these anywhere else.
  - **A clean slate on every identity change.** Switching persona or signing out clears all
    cached data and remounts everything signed-in, so the previous person never appears. The same
    happens when another tab changes who is signed in. A test holds a component on screen across a
    switch to prove it.
  - **The router and session guard,** with placeholder pages. A visitor without a session goes to
    the start, a signed-in visitor goes to `/ask`, and a session that ends shows "This sandbox has
    reset." A late refusal from before a switch, or from a signed-out visit, doesn't show it to
    someone who is signed in.
- **Directory search, filters, and counts** (Phase 2, stage 1). `GET /api/v1/people` now searches
  by name, title, or work email, and filters by location, department, and "My team" (everyone who
  reports to a manager, directly or through a lead). A new `GET /api/v1/people/facets` returns the
  counts the directory shows: everyone, the people matching, and beside every filter option how
  many the list would show if it were picked. Searches can't use `%` or `_` as wildcards, and a
  search containing a NUL character is refused rather than failing. Other sandboxes' locations and
  departments match no one, and a person with no reports gets an empty team, never an error.
- **Each card's location carries its timezone** (Phase 2, stage 1), such as `America/Denver`, so
  the web app can greet people at the right time of day. A location's timezone isn't personal data.
- **The Phase 2 spec and plan** (Phase 2 planning). The spec says how the build meets the approved
  designs: the directory API's search, filters, and counts; the theme and its token tests; the web
  client's CSRF handling and error rules; the screens and their routes; accessibility; and testing,
  with Playwright and axe in a new CI job and a local side-by-side capture report. The plan builds
  it in six stages, each a pull request, with test-first task outlines rather than pre-run code.
- **The design system and the assistant home** (Phase 2 design). Designed in Claude Design and
  approved: the "aubergine and cinnamon" palette, from Wada Sanzo's *A Dictionary of Color
  Combinations*, set in Instrument Sans.
  - `docs/design/tokens.md` lists every color, type, spacing, radius, shadow, and motion token,
    with contrast ratios checked independently. All text meets WCAG 2.2 AA.
  - `docs/design/system/` holds the design system's source as Claude Design exported it: the
    tokens as CSS, the component sketches, the specimen pages, and the fonts with their licenses.
  - `docs/design/screens/03-assistant-home/` has the approved screen, its states, and its notes,
    including the acceptance criteria.
  - The component inventory marks what is designed so far.
  - The fictional employer is now named Juniper Row.
- **The landing page and the directory** (Phase 2 design). Both approved in Claude Design, with
  their states and notes in `docs/design/screens/`.
  - The landing page explains the product and starts a sandbox with one click on a persona card.
  - The directory lists everyone with search and filters, and profiles show private details only
    to the person and HR. Everyone else sees which fields are private and who can see them.
  - The design system gains the persona card, search, filters, the directory list, and profile
    detail rows.
  - The backlog notes what the directory needs from the API in Phase 2: search, filters, and
    counts, and work emails on the employer's domain.
- **The app shell and the global states** (Phase 2 design). The last two Phase 2 screens,
  approved in Claude Design, so every Phase 2 screen is now designed.
  - The shell adds the persona menu, switching with a confirming toast, the navigation for each
    persona (Approvals for managers, Cases and Console for HR), and a banner when the sandbox
    has 3 hours or less left.
  - The global states are a session that has expired, a page that doesn't exist, and an
    unexpected error that shows the request's reference for support.
  - The notes also settle the "Try asking" questions for each persona.

### Changed

- **The API's schema describes the errors it really sends** (Phase 2, stage 1). Every route
  declares its 401, 403, 404, and 422 responses as the problem-details body the API returns, filed
  as `application/problem+json`, in place of FastAPI's default validation error. The generated
  web client now types its errors correctly, and gains the directory's filters and counts. A test
  keeps the schema in step with the real error bodies.
- **Work emails are on the employer's domain** (Phase 2, stage 1): `first.last@juniperrow.example`,
  as the designs show, instead of the product's name.
- **A first visit is no longer a security event** (Phase 2, stage 1). A request with no session
  cookie is logged at debug level, so the security log holds only real refusals. A cookie that
  doesn't match a session is still a warning.
- **The design brief is ready for Claude Design** (Phase 2 planning). Mockups are now desktop
  only; the build still makes every screen usable on a phone, checked automatically at 390 px.
  Screens are designed in their final form, and the build hides what isn't ready yet. The brief
  records the Phase 2 decisions:
  - The navigation is designed in full, and each item appears once its page exists.
  - Switching persona needs no confirmation.
  - A banner warns before the sandbox expires.
  - The directory is one list, with a "My team" filter for managers.
  - A profile shows the fields you can't see as locked rows, by name only.

  It also adds guidance on what makes an HR product look professional, with references to borrow
  ideas from rather than copying an existing design system. The component list is now a living
  inventory. "Indigo with gold" left the list of colors to avoid, because the app that used it is
  leaving the portfolio and Open Door replaces it. The handoff loop is now one screen per round:
  - Claude Code writes each prompt for Claude Design and reviews the result.
  - The first round settles the look as a design-system project.
  - Claude Design's HTML export is preferred over screenshots alone.
  - Claude Code writes each screen's notes.

### Fixed

- **The right rail now appears only on the assistant home** (Phase 2, stage 6). The shell showed it
  on every page, which squeezed the directory: its toolbar wrapped and the profile's panels
  stacked.
- **"Show more" keeps keyboard focus while it loads** (Phase 2, stage 6). It was disabled while
  loading, which dropped focus.

### Security

- **A switch, a sign-out, or a change in another tab never shows the previous person** (Phase 2,
  stage 5). A security re-check proved the switch toast could name the wrong person after another
  tab changed the session or the sandbox expired. The toast now resets with the identity, and
  shows only for the person it names.

## [0.1.0] - 2026-10-04

The first release: the planning documents, the Phase 0 foundation, and Phase 1's tenancy,
identity, and permissions, proven by tests and closed out with a whole-phase review.

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
