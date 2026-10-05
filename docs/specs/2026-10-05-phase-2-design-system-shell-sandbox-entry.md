# Phase 2: design system, shell, and sandbox entry

Written 2026-10-05. This spec goes deeper on Phase 2 of the
[product design](2026-09-29-open-door-design.md). Where the two disagree, this one is newer and
wins. The differences are listed under [Changes from the product design and the brief](#changes-from-the-product-design-and-the-brief).
The approved designs in [`../design/`](../design/README.md) are the visual source of truth, and
this spec doesn't repeat them. It says how the build meets them.

**Goal:** a visitor opens Open Door, picks a persona, and lands in a private sandbox, inside an
app that looks and behaves like the approved designs. They can switch persona, sign out, find
anyone in the directory, and see exactly the profile fields their role allows. The assistant isn't
connected yet: asking a question gives a fixed reply.

**Done when** CI is green, the owner has approved the side-by-side captures, and these are proven
by tests:

- **Every acceptance criterion** in the five screens' `notes.md` files has a named test, listed in
  the plan's self-review table:
  - [landing](../design/screens/01-landing/notes.md)
  - [app shell](../design/screens/02-app-shell/notes.md)
  - [assistant home](../design/screens/03-assistant-home/notes.md)
  - [directory](../design/screens/04-directory/notes.md)
  - [global states](../design/screens/05-global-states/notes.md)
- **axe reports no violations** (WCAG 2.2 AA rules) on every screen state and every gallery
  component state.
- **At 390 px** no page scrolls sideways, and each screen's narrow-screen criteria hold.
- **The design tokens in the build match the exported ones** exactly, and no component uses a raw
  color value.
- **The directory API** searches, filters, and counts as described below, and a person who isn't
  the subject or HR still never receives a private value.

---

## Decisions made while designing (owner-approved, 2026-10-05)

- **Asking a question gives a fixed reply until Phase 4.** The composer sends through a chat
  transport seam that Phase 4 replaces. A fake transport answers with one fixed, person-written
  reply, shown as a plain block under the composer. The conversation view is designed with
  Phase 4, which deletes this block. Tests drive the failed-send state by injecting a transport
  that fails.
- **Side-by-side captures are a local report, not committed images.** `make captures` renders the
  build at 1440 px and writes an HTML page with each design screenshot beside its build capture,
  one row per state, into a gitignored folder. The owner reviews it before each UI pull request.
  CI runs Playwright, axe, and the 390 px checks, but has no pixel baselines: fonts render
  differently on macOS and Linux, so pixel diffs would fail on noise.
- **"My team" ships in Phase 2.** The approved directory notes and the backlog include it, and
  that supersedes the brief, which had put it with approvals in Phase 5.
- **The plan gives outlines, not pre-run code.** Each task names its files, the tests to write
  first and what they prove, and the interfaces later tasks need. Problems are solved during the
  build. Building a phase once to plan it and again to ship it costs a lot and gains little.

---

## Changes from the product design and the brief

| Earlier documents said | Phase 2 does | Why |
|---|---|---|
| A "My team" filter arrives with approvals in Phase 5 (brief) | It ships in Phase 2 | The approved directory design includes it, and it reuses Phase 1's reporting query |
| "Session expired" is shown when the sandbox expires | It's shown when an open tab gets a 401. A visit after the cookies have expired lands on the landing page instead | The browser drops both cookies when they expire (`Max-Age`), so a fresh visit can't tell an expired visitor from a new one. The landing page is the right place for both |
| The assistant home answers with a canned reply (brief) | It does, through a transport seam, with no conversation view | The conversation view is a Phase 4 design. One plain block is the cheapest stand-in, and Phase 4 deletes it |
| Toasts for confirmations | Errors never go in a toast; they appear inline beside what failed | The approved design system's rule |
| A "collapsible navigation" on a phone (brief) | Below 760 px the sidebar becomes a top bar whose navigation scrolls sideways and shows that it does | The assistant home's notes describe this layout and the two fixes it needs |

---

## The design system in code

### Tokens

**`apps/web/src/styles/theme.css`** turns the exported tokens in
[`../design/system/tokens/`](../design/system/tokens/) into Tailwind v4 `@theme` variables:

- **colors**, as `--color-*`: for example `bg-surface`, `text-ink-muted`, `border-input-border`
- **the type scale**, as `--text-*`, with each line height and weight: for example `text-display`,
  `text-ui`
- **radius**, as `--radius-*`, the three shadows, and the motion duration and easing

The spacing base is 4 px, so Tailwind's spacing utilities land on the design's scale. Layout
widths (the 248 px sidebar, the 340 px rail, the 760 px measure) are named tokens too.

**shadcn/ui's variable names** (`--background`, `--primary-foreground`, `--accent`, and so on)
point at these tokens, as [`shadcn.css`](../design/system/tokens/shadcn.css) maps them. Its
`--accent` is shadcn's hover fill (`primary-tint`). The brand's cinnamon accent is called `marker`
and is only ever a mark beside a label.

**Two tests keep the build honest:**

1. **The tokens match the export.** The test parses every custom property in
   `docs/design/system/tokens/*.css` and in `theme.css`, and fails if any value differs or any
   token is missing. A future export that changes a color fails the build until the theme
   follows it.
2. **No raw colors in components.** It fails on any hex, `rgb(`, or `hsl(` value in
   `src/**/*.tsx`.

**Fonts** are self-hosted: Instrument Sans for everything, Geist Mono for the request reference.
They are copied from [`system/assets/fonts/`](../design/system/assets/fonts/) with both SIL Open
Font License texts. Every number uses tabular figures.

**Motion** is color and border transitions only, 150 ms. A global rule removes transitions and
stops the spinner under `prefers-reduced-motion`.

### Components

The shadcn/ui primitives are added with its CLI and restyled to the tokens:

- Button: primary, secondary, ghost, and destructive, at 40 and 32 px, with a loading state.
  The design has no loading state yet, so it shows a spinner and keeps the label.
- Input and textarea
- Select
- Dropdown menu
- Tooltip
- Toast (Radix Toast, which pauses on hover and focus)
- Avatar
- Skeleton

**The product components** follow the inventory in [`components.md`](../design/components.md).
Each is built from its sketch and props in [`system/components/`](../design/system/components/),
which are a reference, not code to ship:

- Logo
- Nav item
- Persona switcher and persona menu
- Banner
- Inline error
- Full-page message
- Page header
- Sandbox indicator
- At-a-glance link and list
- Composer
- "Try asking" list
- Persona card
- Search field
- Filter select and filter toggle
- Directory table, row, and skeleton row
- Detail list and row
- Empty state

**Icons** are Lucide, as the design uses.

### The component gallery

`/dev/gallery` shows every component in every state that
[`components.md`](../design/components.md) lists for it. Each state appears under a heading, so
axe and the capture report can address it.

- **It isn't in the production bundle.** It's compiled in only when `import.meta.env.DEV` is set,
  or when `VITE_GALLERY=true`, which the e2e build sets. A check after `npm run build` fails if
  the gallery's marker string appears in `dist/`.
- **Hover and focus states** are captured by Playwright hovering or focusing the element, so the
  components carry no gallery-only props.

---

## Screens and routes

The screens and their copy are in each screen's `notes.md`. The build adds these rules.

| Route | Shows | Who |
|---|---|---|
| `/` | Landing | Anyone. A signed-in visitor is sent to `/ask` |
| `/ask` | Assistant home | Signed in |
| `/directory` | The directory list. Search and filters live in the URL (`?q=&location=&department=&team=mine`) | Signed in |
| `/directory/:personId` | A profile | Signed in |
| `/dev/gallery` | The component gallery | Development and e2e builds only |
| anything else | Not found, inside the shell, with no nav item current | Signed in. An anonymous visitor is sent to `/` |

The router is React Router in data mode, so `<ScrollRestoration>` returns the list to where the
visitor left it when they come back from a profile.

### Who is signed in

A layout route loads `GET /me` before any signed-in page renders:

- **A 401 on that first load** means no session, so it goes to the landing page.
- **Any other failure on that first load** shows "Something went wrong", outside the shell.
- **A 401 later, while signed in,** shows "This sandbox has reset", outside the shell. Usually
  this is the 24-hour reset.

### Personas

**One client constant** holds each persona's name, title, location, and landing-card copy, plus
their four "Try asking" questions from the
[app shell notes](../design/screens/02-app-shell/notes.md#copy). The landing page, the persona
menu, and the assistant home all use it. The landing page needs it before any session exists. An
e2e test starts a sandbox as each persona and checks that `/me` agrees with the constant, so the
seed and the constant can't drift apart.

### Navigation

**One nav config** lists every item from the app shell notes, with the roles that see it and
whether its page exists yet:

- Approvals is for managers.
- Cases and Console are for HR.
- In Phase 2 only **Ask** and **Directory** exist.

A unit test checks each persona's full list against the notes, with every item marked as
existing, so later phases only flip a flag. "How it's built" and the tour button stay hidden
until Phase 7.

### Assistant home

- **The greeting** uses the person's location's timezone, from `location.timezone` on `/me`: "Good
  morning" from 05:00 to 11:59, "Good afternoon" to 16:59, and "Good evening" otherwise.
- **The composer:**
  - Enter sends, and Shift+Enter adds a line.
  - Ask with an empty box moves focus into the box.
  - A "Try asking" row fills the box without sending.
- **The chat session** lives in a small Zustand store: the draft, the status (idle, sending,
  replied, failed), and the reply. Phase 4 grows it into the streaming state machine.
- **The fake transport** waits briefly, then replies with this fixed text (for the owner's
  approval):

  > The assistant isn't connected yet. When it is, it will answer here and cite the Juniper Row
  > handbook for every policy it mentions.

  On failure the question stays, the inline error appears with Retry, and it is announced
  (`role="alert"`).
- **The right rail** shows the sandbox indicator. The at-a-glance list is hidden while it has
  nothing to show. Its figures arrive with their data in Phases 3 and 5.

### The shell

- **Switching persona** calls `PUT /api/v1/session/persona`. While it runs, the switcher shows
  "Switching to Marcus…" on one line. On success the app:
  1. clears every TanStack Query cache and resets the chat store
  2. stores the new `me`
  3. goes to `/ask` with an empty composer
  4. shows the toast "Now viewing as Marcus Bell."

  Choosing the current persona just closes the menu.
- **Sign out** calls `DELETE /api/v1/session`, clears the same state, and goes to `/`.
- **The persona menu** is a Radix dropdown menu with a radio group, so screen readers hear
  `menuitemradio` and which one is checked. Focus starts on the checked item. Escape or a click
  outside closes it and returns focus to the switcher.
- **The sandbox indicator and expiry banner** count down from `tenantExpiresAt` on `/me`,
  updated each minute:
  - Three hours or more remain: whole hours ("Sandbox resets in 21 h").
  - Under three hours: hours and minutes ("2 h 50 min").
  - At 3 hours or less, the banner appears. Dismissing it is remembered in `sessionStorage` under
    a key that includes `tenantExpiresAt`, so a new sandbox shows it again.
- **Narrow screens.** Below 760 px:
  - the sidebar becomes a top bar
  - the navigation scrolls sideways, with an edge fade that shows there is more
  - the sandbox indicator sits in the top bar beside the persona
  - the rail moves below the content

### Directory

- **The list** reads `q`, `location`, `department`, and `team` from the URL.
  - Search updates the URL as the visitor types, after a 250 ms pause, and replaces the history
    entry rather than adding one.
  - The list is a TanStack infinite query, 50 rows at a time. Show more fetches the next page with
    the API's cursor.
  - Changing a filter starts again from the first page.
  - The header count and the filter counts come from `GET /people/facets`.
  - "My team" appears only when `myTeam` isn't null.
- **The profile** loads `GET /people/{id}`.
  - It loads `GET /people/{id}/private` only when the viewer is that person or HR.
  - Everyone else sees the four locked rows, built from the field names alone, with "Visible to
    Leo and HR" using the person's given name. No request for the values is ever made.
  - The audit note shows whenever values are shown.
  - A 404 shows not found inside the shell.

### Global states

All three pages, plus the not-found route, use the full-page message component:

- **"This sandbox has reset."** Outside the shell, after a 401 while signed in.
- **"We couldn't find that page."** Inside the shell, for an unknown route or a 404 from the API.
- **"Something went wrong on our side."**
  - It's shown for a 5xx or a network failure.
  - It's inside the shell, unless the first `/me` failed.
  - It shows the response's full 32-character `X-Request-ID` in Geist Mono, which selects with
    one click. Retry repeats the failed query.

Each title is the page's `h1` and receives focus when the page appears.

---

## The web client and the API boundary

**`apiFetch`** (`src/lib/api-fetch.ts`) is the generated client's only way to reach the network,
through an Orval `override.mutator`. It lives outside `src/api/`, because Orval's `clean` option
deletes everything else there. It:

- reads `__Host-od_csrf` from `document.cookie` on **every** unsafe request (POST, PUT, PATCH,
  DELETE) and sends it as `X-CSRF-Token`. It reads the cookie fresh each time, because creating a
  sandbox and switching persona both replace it.
- sends `Content-Type: application/json` with every body
- leaves `credentials` at the default, `same-origin`. `/api` stays on the app's origin through
  the Vite proxy in development and in e2e.
- on any non-2xx response, throws `ApiError` with the status, the problem-details body, and the
  `X-Request-ID` header

**Query rules,** set once on the `QueryClient`:

- **Reads:** never retry a 4xx; retry a 5xx or a network failure once.
- **Mutations:** never retry, and never retry after a 403.
- **A 401 on any query while signed in** switches the app to the session-expired page.

**One `resetIdentity()`** runs on a persona switch and on sign-out. It runs `queryClient.clear()`,
then resets every Zustand store, so nothing of the old identity survives.

---

## The directory API

These changes go to `GET /api/v1/people`, and a new endpoint answers the counts. Both keep
Phase 1's rules: a session is required, row-level security scopes the tenant, and the card
schema is unchanged apart from the location's timezone.

### Search and filters

| Query parameter | Meaning |
|---|---|
| `q` | Up to 100 characters, trimmed; blank means none. Matches, case-insensitively and anywhere in the text, the full name ("given family"), the title, or the work email. `%`, `_`, and `\` match themselves. |
| `locationId` | One location |
| `departmentId` | One department |
| `team=mine` | Everyone who reports to the signed-in person, directly or through a lead, from the same recursive query Phase 1 runs on every request. For someone with no reports it matches no one. It's never an error, so it reveals nothing about who manages whom. |
| `cursor`, `limit` | As in Phase 1. The order stays family name, given name, then ID. |

A filter's ID from another tenant matches no one, because row-level security hides it.

### `GET /api/v1/people/facets`

It takes the same filters and returns:

```json
{
  "total": 120,
  "matching": 44,
  "locations": [{ "id": "…", "name": "Austin warehouse", "state": "TX", "count": 0 }],
  "departments": [{ "id": "…", "name": "Distribution", "count": 0 }],
  "myTeam": 44
}
```

- **Each option's count is how many people the list would show if that option were chosen,**
  keeping every other active filter. So a location's count applies the search, the department,
  and the team, but swaps in that location. This is the usual faceted-search rule, and it keeps a
  count from ever promising rows the list won't show.
- **Every location and department is listed,** including those at zero, sorted by name.
- **`myTeam` is `null` for someone with no reports.** The web app hides the toggle when it's null.
- **The counts skip the per-person `can()` check.** That's safe while `DIRECTORY_READ` allows
  everyone in the tenant. The backlog item on hidden people in the directory cursor already
  covers the phase that first restricts it, and it now names the counts too.

### Smaller API changes

- **`location.timezone`** (an IANA name) is added to every card and to `/me`, for the greeting. A
  location's timezone isn't personal data.
- **Work emails** move to `@juniperrow.example`, the employer's domain, as the designs show.
- **The OpenAPI schema describes the real errors.**
  - A `Problem` model mirrors the problem-details body, including `errors` on a 422.
  - Every route declares, through one helper:
    - 401, where a session is needed
    - 403, where CSRF or the policy can refuse. The same-origin check can also refuse a
      cross-site read anywhere under `/api/`, but the web app never causes that, so reads don't
      declare it.
    - 404, where a row can be missing
    - 422, wherever it has parameters or a body
  - FastAPI files every response model as `application/json`, so a small schema hook moves
    `Problem` to `application/problem+json`. FastAPI's default `HTTPValidationError` leaves the
    schema, and the generated client's error types become right.
- **A first visit isn't a security event.** A request with no session cookie logs at DEBUG, with
  no `security.session_invalid` event. A cookie that doesn't match a session is still logged at
  WARNING.

---

## Accessibility

The baseline every page meets:

- **WCAG 2.2 AA.** axe runs with the `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, and `wcag22aa`
  tags, on every screen state in e2e and on every gallery state. The token contrast pairs are
  already checked in [`tokens.md`](../design/tokens.md).
- **The focus ring.** Every control shows the 2 px aubergine ring, offset 2 px, through
  `:focus-visible`.
- **Tab order** follows each screen's notes. The e2e tests walk it with the keyboard.
- **Live regions:**
  - The landing card's starting state is announced politely.
  - The toast and the banner are polite status messages.
  - The failed-send error and the sandbox start error use `role="alert"`.
- **Reduced motion.** No transitions, and no spinning, under `prefers-reduced-motion`.
- **Color never carries meaning alone.** The banner pairs the warning color with its icon and
  text, and a locked row pairs the lock with its reason.

---

## Testing

**API** (pytest, against the real Postgres as `od_app_login`, as in Phase 1):

- **Directory queries:**
  - search by part of a name, a title, and an email
  - a `%` search matches only a literal `%`
  - each filter, and filters combined across a cursor page
- **Facets:**
  - the seed company's real numbers: 120 people; 40 in Denver, 45 in Oakland, and 35 in Austin;
    eight departments; Marcus's team of 44
  - the count rule, with a search and a filter both active
- **HTTP:**
  - every filter narrows the list, and the facets agree with it
  - `team=mine` for Marcus and for Priya
  - a 101-character `q` gets 422
  - another tenant's location ID matches no one
  - anonymous gets 401
- **The schema:**
  - there's no `HTTPValidationError`
  - every operation with input declares a 422 `Problem`
  - every signed-in operation declares 401
- **Logging:** a missing cookie writes no security event, and an unknown cookie still writes the
  warning.

**Web unit and component tests** (Vitest and Testing Library, with MSW for the API):

- the token-sync and no-raw-color tests
- `apiFetch`:
  - the CSRF header on unsafe methods only, read fresh each time
  - the JSON content type
  - `ApiError` with the request ID
- the query rules: no retry on a 4xx, one on a 5xx, and none for mutations
- `resetIdentity` clears every query and store
- the pure helpers: the time-left format, the greeting, and the nav config per persona
- each component's behavior: the persona menu's keyboard and checked item, the toast's pause and
  timeout, the tooltip only when truncated, the composer's keys, and the filter toggle's
  `aria-pressed`

**End to end** (Playwright on Chromium, against the built web app with `VITE_GALLERY=true`, the
real API, and Postgres; the CI job `e2e`):

- one test per acceptance criterion, named after it
- axe on every screen state, and on the gallery
- **at 390 px,** `document.documentElement.scrollWidth` is no wider than the viewport on every
  page, plus each screen's own narrow-screen criteria
- **the expiry banner** uses Playwright's clock to move the browser to 2 h 50 min before
  expiry. The server's session is still valid then, because only the browser's clock moves.
- **every persona's `/me`** matches the client's persona constant
- **The `__Host-` cookies** are checked once, locally, by running the sign-in test in Firefox and
  WebKit too. The result is recorded in the plan. Browsers that refuse `Secure` cookies on
  `http://localhost` affect only local development, since every deployed origin is HTTPS.

**`make captures`** (local, not CI) renders each screen state and gallery state at 1440 px. It
writes `apps/web/captures/index.html`, which sets each design PNG from `docs/design/screens/`
beside its build capture.

**CI.** The new `e2e` job, from the original plan, runs on pull requests and pushes to `dev`
when the web app, the API, or the workflow changes. It:

1. starts Postgres as a service, migrates as the owner, and creates the login users
2. starts the API and builds the web app with `VITE_GALLERY=true`
3. serves the web app with `vite preview`, with `/api` proxied to the API
4. runs Playwright, and uploads the report when it fails

It makes no paid AI calls.

---

## Docs and housekeeping

- **`docs/DATA-INVENTORY.md`:**
  - the `sessionStorage` key for the dismissed banner: what it holds, why, and that it's gone when
    the tab closes
  - that the web app sets no cookies of its own and uses no `localStorage`
  - the timezone now on directory cards
- **`docs/BACKLOG.md`:**
  - remove the Phase 2 items this phase closes
  - add the counts to the hidden-person directory item
  - record the WebKit result if it needs follow-up
- **`docs/design/components.md`:** mark the button's loading state as built, not designed. The
  owner can design it later.
- **`CLAUDE.md`:** add `make e2e` and `make captures` to the Commands block.
- **After Phase 2:** the owner may run `/design-sync` to push the shipped components into the
  Claude Design project, so later phases are designed with them.

---

## Delivery: six stages, six pull requests

Each stage is a pull request into `dev`, sized to the 1,500-line guideline. The backend comes
first because it waits on nothing. The components were planned as one stage and split in two when
they came to about 2,600 lines. See the
[implementation plan](../plans/2026-10-05-phase-2-design-system-shell-sandbox-entry.md).

1. **The directory API, and the backend the screens need:**
   - search, filters, and facets
   - the timezone on cards
   - the email domain
   - the `Problem` schema
   - the quieter first visit
   - the regenerated client
2. **The web foundation:**
   - the theme, fonts, and the two token tests
   - `apiFetch`, the query rules, and `resetIdentity`
   - the router and layouts
   - the restyled shadcn primitives
   - the gallery
   - Playwright and the CI `e2e` job
3. **The core, navigation, and feedback components,** every state in the gallery, with their tests.
4. **The assistant, landing, form, and directory components,** the browser tests for the gallery,
   and the capture report.
5. **The landing page, the shell, the assistant home, and the global states.**
6. **The directory and profiles,** then the phase close.

Every UI stage ends with `make check`, the `e2e` job green, and the owner's review of the capture
report. Then `/code-review medium` runs on the whole branch, and the commit and pull request are
proposed and wait for the owner's OK. The phase closes with `/code-review high` on its
application code (see `CLAUDE.md`). Phase 2 doesn't guard an invariant directly, so it gets no
separate security review. The directory changes are covered by Phase 1's permission tests,
extended here.

---

## Later phases

- **Phase 3:** the Handbook nav item, and the "Handbook updated" at-a-glance figure.
- **Phase 4:**
  - the conversation view, which deletes the fixed reply
  - the docked composer, with its sending, streaming, and disabled states
  - the AI label on each message
  - the budget banner
- **Phase 5:**
  - Time off and Approvals in the nav, with the waiting count
  - the PTO-balance and pending-request figures
- **Phase 6:** Cases in the nav.
- **Phase 7:**
  - Console and "How it's built" in the nav
  - the tour button on the landing page
  - the data-visualization palette
- **Phase 8:** a bundle budget in CI.
- **Any time:** a dark theme. The tokens are semantic, so it only overrides values.

---

## Sources

- **The approved designs:** [`../design/README.md`](../design/README.md),
  [`tokens.md`](../design/tokens.md), [`components.md`](../design/components.md),
  [`BRIEF.md`](../design/BRIEF.md), and the five screens' `notes.md`, all approved on 2026-10-04.
- **The Phase 2 items in [`../BACKLOG.md`](../BACKLOG.md),** from Phase 1's reviews.
- **[The Phase 1 spec](2026-10-03-phase-1-tenancy-identity-permissions.md)** for sessions,
  cookies, CSRF, and the directory API this phase extends.
- **Accessibility references:**
  - WCAG 2.2: https://www.w3.org/TR/WCAG22/
  - The WAI-ARIA Authoring Practices for the menu button pattern and `menuitemradio`:
    https://www.w3.org/WAI/ARIA/apg/patterns/menu-button/
