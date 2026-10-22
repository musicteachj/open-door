# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This is a development log first and a release log second. Entries accumulate under
**Unreleased** on `dev`, and each release pull request from `dev` into `main` cuts them into a
version (`0.x.y` while the app is being built, `1.0.0` when it is complete).

## [Unreleased]

### Added

- **The time-off routes** (Phase 5, stage 3). The time-off service is now reachable over
  HTTP under `/api/v1/time-off`, for the time-off page, the Approvals page, and the home's
  at-a-glance cards. Every route needs a session, every write needs the CSRF header, and every
  amount comes with both its minutes and its label ("8 hours (1 day)").
  - **Reading:** balances for yourself or a person you may read, with the handbook sections they
    rest on; your requests, everyone below you, or the requests waiting for your decision (oldest
    first, whenever their days fall), in a window that defaults to 30 days back and 120 ahead of
    your own today, at most 200 rows; one request; the date picker's marks (your weekdays, your
    location's holidays across New Year, and the earliest day each type allows); and a summary
    with your PTO available, your pending requests, your approver, and, for a manager, how many
    requests wait for them.
  - **Acting:** a check that previews a possible request without writing anything (it answers 200
    even when the request has problems, and names the days another request already covers), then
    make, decide, and cancel. Each is audited as made from the page.
  - **Refusals are problems with a fixed sentence.** A request or person the caller can't read is
    a 404, never a 403, so it looks the same as one that doesn't exist. Someone who can read it
    but may not act (HR or a skip-level manager deciding, a manager canceling a report's request)
    gets a 403. A request that is no longer in the needed status, or has already started, is a 409
    that says where it stands now. The engine's refusals are 422s whose `type` is the code. Each
    code has one plain sentence, written by a person.
  - **PTO for someone with no manager is refused** (`no-approver`), since only a direct manager
    decides PTO and it would wait forever. The engine's own problems come first, and the check
    lists it too, so the form says so before sending. Sick time is unaffected. A pending request
    can still be approved or denied after its days have passed.
  - **Team coverage and "available after"** come with a request for the person's direct manager
    only: who else among the manager's direct reports has approved or recorded time off on the
    request's scheduled days (a waiting request doesn't count), and the person's available PTO as
    it stands. Plain context, never in the audit log or sent to the model.
  - **The engine** gains two small pure functions: the calendar days of a range that existing
    requests already cover, and the dates a request may start and end on, which the evaluation now
    uses too, so the date picker and the refusal can't disagree.

- **Proposals and the confirm and dismiss routes** (Phase 5, stage 3). The assistant can
  now propose a time-off request, a decision, or a cancellation, and a person confirms it on a
  card. Nothing is reachable from the assistant yet (stage 4 adds its tools); the server side is
  built and proven first.
  - **The proposal service** stores each proposal for one person with its validated payload and its
    card, a fixed 15 minutes to live, and an audit event from the assistant. A new proposal replaces
    the one still waiting in its conversation, and a turn that doesn't finish cancels its own.
  - **The card is built by the server** from the engine's and the service's results, never from
    the model's words: a booking card (counted and skipped days, the amount, the balance before and
    after, warnings, the approver, and the handbook sections), a decision card (who asked, the
    balance as it stands, and who else on the team is off), and a cancel card (what goes back into
    the balance). A card never holds a note or anything a person wrote.
  - **Confirm** (`POST /api/v1/assistant/proposals/{id}/confirm`) runs the stored payload through
    the time-off service, once, and never anything the browser sends except a denial's note (at most
    300 characters, kept on the request only, never in the proposal or the audit log). The proposal
    is locked first and the person's balance second, so two confirms at once book once. If the
    request no longer fits, the confirm itself still works: the answer is a 200 whose status is
    `failed`, with the engine's code and its fixed sentence (and the clashing days for an overlap).
  - **Dismiss** (`POST /api/v1/assistant/proposals/{id}/cancel`) works even while the answer is
    still streaming.
  - **Refusals:** another person's proposal and a missing one are both a 404. A proposal that has
    already ended is a 409 whose `type` is its status (`executed`, `failed`, `canceled`, or
    `expired`), and one whose answer is still streaming is a 409 `turn-running`. A confirm after
    the 15 minutes marks the proposal expired and keeps that, and so does one for an answer that
    never finished (the proposal is canceled).
  - **The next turn's context** gets one fixed sentence per proposal that ended since the last
    message (made from structured fields only, never from stored text).
  - **The proposal's clock is the database's,** never the caller's.
  - **A card from a turn that didn't finish never runs.** A confirm executes a card only when its
    answer completed. A turn that failed, was stopped, ended in crisis, or was marked abandoned
    cancels its card instead. A proposal can't be stored for a turn that has already ended.
  - **One live card per conversation is held in the database too** (migration `0010`, a unique
    partial index on pending proposals), beside a lock that makes two cards made at once take turns.
  - An ended proposal always answers 409 before a bad note answers 422, and an unexpected status is
    still a 409 with a generic sentence.
  - **A reload shows each card's state.** `GET /api/v1/assistant/conversations/current`
    gives each turn its proposals, oldest first, with the card and the status as of the read (the
    database's clock), in one query for the whole conversation. A waiting card past its 15 minutes
    shows `expired`, and one whose answer never finished shows `canceled` with the reason
    `turn-incomplete`, exactly what a confirm would do, from one shared rule. A read writes
    nothing. Each proposal also says `turnRunning`, true while its answer is still streaming, so the
    web app knows Confirm must wait (the confirm and dismiss answers carry it too, always false).
  - **Each card says what it is** (`kind`: `request`, `decide`, or `cancel`), and the card is a
    discriminated union in the API schema, so the web app can tell them apart without guessing.
  - **The web client is regenerated** for every stage 3 route and schema (`make openapi`).

- **The time-off data and service** (Phase 5, stage 2). The database, the permission rules, the
  service, and the seed that the engine needs to run against a real sandbox. Nothing is reachable
  over HTTP yet; stage 3 adds the routes.
  - **The tables:** each person's working weekdays, an opening PTO balance per person, time-off
    requests, and the assistant's proposals. The API's login can add rows and change only a
    request's status and decision, or a proposal's status. A database trigger lets a status move
    only forward (a final one never changes), a constraint refuses two open requests for the same
    days, and row-level security shows a proposal only to the person it was made for.
  - **The database backs the rules up:** it stamps when a proposal was made and when it ended,
    holds its life to 15 minutes, starts it pending, and refuses to execute it once expired. One
    proposal makes at most one request, and nobody can decide their own request.
  - **Who may do what:** a person reads their own time off, a manager reads anyone below them, and
    HR reads everyone's. Only a person's direct manager decides, and only a pending PTO request. A
    person cancels their own request any time while it is pending, and an approved or recorded one
    until the day before its first day.
  - **The time-off service** makes, decides, and cancels requests. It takes a per-person lock
    first, so two requests that each fit but not together can't both be made, and it checks each
    request with the engine against that person's current data, using today's date at their
    location. Each change is recorded in the audit log with the proposal that led to it, if any,
    and the log never holds a denial's note.
  - **The seed:** every sandbox company now has working weekdays for each person (the stores
    rotate, the Austin night crew works Sunday to Thursday, and Leo works Wednesday to Sunday), an
    opening PTO balance, a few approved PTO requests and the odd recorded sick day each, Leo's time
    off last week, and one pending request in Marcus's queue. Holidays are seeded for four years,
    from the year before the sandbox to two years after, so a sandbox that lasts past New Year is
    still covered.
- **The time-off engine** (Phase 5, stage 1). Pure rules code that counts time off and works out
  balances from the handbook, with no database, no clock, and no framework. Nothing calls it yet;
  stage 2 builds the data and the service on top of it.
  - **Counting a request:** only the person's scheduled weekdays count, and never a company
    holiday at their location. Each skipped day is listed with its reason ("not scheduled", or the
    holiday's name), so a card can say why a day didn't count.
  - **PTO** is worked out on every read from an opening balance and the requests (ADR 0012): 10
    hours on each month's last day for salaried staff and 8 for hourly, paused at the ceiling (180
    and 144 hours), less what's taken (today counts), booked, and pending.
  - **Sick leave** is a yearly grant by state (40 hours in Texas and Georgia, 48 in Colorado, and
    the larger of 40 hours or 5 workdays in California), given on January 1 or the hire date.
    Each sick day is charged to its own calendar year.
  - **Checking a new request** gives the spec's reasons for refusing it (no scheduled days, too
    long, out of range, a bad partial amount, an overlap, not enough time), a short-notice warning
    for more than three PTO days within two weeks, and what it takes from each balance.
  - **Every result cites its handbook section**, and every amount has one shared label ("8 hours
    (1 day)", "4 hours (half a day)", "3 hours"), so the assistant will quote figures and never
    work them out. "Today" comes from the location's time zone, never from the sandbox's anchor
    date.
  - Every expected value in its 176 tests was worked out by hand from the handbook, and each
    batch's reviewer recomputed at least five of them without running the engine.

### Fixed

- **The web theme has the Phase 5 design tokens** (between Phase 5 stages, 2026-10-20). The
  screens PR (#63) added eight tokens to the design export: the warning, danger, and apricot tints
  and borders, the scrim behind a confirm dialog, and the docked panel's width. It didn't add them
  to the web app's theme. The test that checks the theme against the export failed, but CI runs
  the web checks only when the web app changes, so that docs-only PR never ran it. The seven colors
  are now in the theme, and the panel width maps to the existing `--spacing-panel` (so
  `w-panel`), like the other layout widths. CI now also runs the web unit tests when a file they
  read outside the web app changes (`docs/design/`, the personal-data cases shared with the evals,
  and the API's seeded people), the browser tests when the handbook changes, and the API tests
  when the `Makefile` or `.gitignore` changes (the eval runner's tests read both).

### Security

- **Vite updated to 8.3.4 (between Phase 5 stages, 2026-10-20).** Vite 8.3.0 to 8.3.2 bundle a
  `launch-editor` with three advisories published that day (GHSA-r825-w8mm-5pxw,
  GHSA-698v-4r3x-3vcv, GHSA-587h-7wmj-h5pm), the worst a crafted file path that can run a command
  through some editors' command-line flags. It is the development server's "open in editor"
  helper, so it touched developers' machines, not the built app, which Vite only bundles. 8.3.3 is
  the first fixed release; `package.json` now asks for at least 8.3.4, the newest 8.3 release. 8.3.4
  needs `postcss` 8.5.29 or later, so the lockfile also moved `postcss` (to 8.5.31) and its own
  small dependencies.

- **`certifi` updated to 2026.10.19 (between phases, 2026-10-20).** The certificate bundle the API's
  HTTP client trusts (through `httpx`, which reaches Voyage) included the emSign root
  certificates, whose intermediate keys were compromised. A critical advisory, GHSA-6q48-6c7w-9gw2,
  was published that day, and the new release drops those roots. A floor in `pyproject.toml` keeps
  any later re-resolve from going back below it. The Anthropic SDK doesn't use this bundle: it
  trusts the operating system's store, so the deploy phase checks that the production image's CA
  store has dropped the emSign roots too (in the backlog).

## [0.4.0] - 2026-10-20

Phase 4: the assistant core, read-only. Anyone in a sandbox can ask the assistant an HR question
in plain language on `/ask` and get a streamed answer whose every policy sentence cites the
handbook, with "Show your work", "Was this right?", and Stop. A small, fast guard model screens
each message first: a crisis gets fixed, human-written text (911, the 988 Lifeline, the EAP) and
never reaches the main model; a sensitive topic gets an answer and the HR partner's contact; and
if the guard can't answer, the assistant fails closed. Three read-only tools act only for the
signed-in person (the handbook search, their own profile, and the directory). Spending is capped
per sandbox and per day by an insert-only ledger reserved before each call. Development, the
browser tests, and a strict reverse-proxy check run on a scripted stand-in for the model, and CI
replays recorded answers. The last full live eval run (2026-10-19, $8.02) scored the red team, the
citation checks, and the unanswerable questions at 100% in every trial, and the judge at 74% (the
85% bar moves to Phase 7). The phase closed with a whole-phase review, a Fable 5.1 security review,
a release review, and their fixes.

### Changed

- **The assistant cites every policy sentence and stays out of decisions** (Phase 4, answer-quality
  follow-up). The prompt (now version 2026-10.2) asks for a citation on every sentence that states
  or sums up a policy, including which location's rule applies and how HR handles what people tell
  it, and for each paragraph to start with a cited sentence. It gives a rule with its conditions
  (who qualifies, how long they must have worked, whether it is paid, whether unused time carries
  over), searches again when a passage mentions something it doesn't have, names the HR team when
  it can't find an answer, and no longer works out dates from a number of days. Declining an
  employment decision now also means no advice on how to make it ("document the dates first").
  The full live run moved the judge from 67% to 74% (the plan's bar is 85%, carried to Phase 7),
  and every other measure to 100%.
- **The guard gets 10 seconds instead of 4** (Phase 4, answer-quality follow-up). In Stage 6's
  full run the threat-of-violence item twice got no guard answer within 4 seconds and failed
  closed instead of showing the crisis panel. The guard's measured p95 is about 2 seconds, so 4
  seconds left no room for a retry; ADR 0009 is amended with the reasons and how 10 seconds fits
  the turn's deadline and the AWS timeouts. The fresh full run had no guard failures.
- **The eval judge knows the asker's role** (Phase 4, answer-quality follow-up). Its asker line
  now says HR, manager, or employee, the same rule the assistant is told, so an HR person's
  answer that mentions their HR role is no longer graded as a made-up claim. The judge is now
  version 2026-10.2, and its agreement with the independent hand grades is 93%.
- **The offline evals and CI replay the full set** (Phase 4, answer-quality follow-up), every
  red-team and Q&A item instead of the smoke set, from a fresh full run ($8.02) that records
  the crisis item the guard used to time out on. The smoke set gains that item too. Because a
  smoke run re-records only its own items, CLAUDE.md's AI rule now asks for a full run before a
  prompt, tool, guard, or retrieval PR, with smoke runs for trying wording first.

- **The browser's fake assistant is gone** (Phase 4, stage 6). The home's canned reply, its
  transport, and their tests are deleted; development and the browser tests use the server's
  scripted model. The scripted model now cites a state addendum when its search returns one, so
  the demo's California and Texas employees get different citations. Both Playwright configs
  name the scripted model explicitly, so a local `.env` set to `anthropic` can't make the browser
  tests call Anthropic.
- **The assistant evals' first full live run is recorded** (Phase 4, stage 6): every red-team and
  Q&A item, three trials, $6.78. Red team 98%, Q&A citation checks 98%, unanswerable items 97%,
  and the judge 67%, short of the plan's 85%: most misses are policy sentences without a
  citation. The crisis item twice outran the guard's 4-second timeout and failed closed (the
  "can't answer right now" text still gives 911 and 988). The re-recorded fixtures are
  committed; the offline evals stay on the smoke set until a focused follow-up fixes the prompt
  and the guard's timeout and records a fresh full run.
- **Local browser runs clean up their AI reservations** (Phase 4, stage 6). Each scripted answer
  reserves budget in the shared development database's daily ledger, so a full browser run could
  push the day past the $3 cap and then fail the API's own tests. The browser-test and capture
  configs now delete the rows their run created when it ends, through
  `apps/api/scripts/clear_browser_test_spend.py`, which takes its start time from the database's
  own clock and refuses anything older than a day. CI skips it, since its database is new each
  run.
- **The composer has one failed-send message,** under the box (Phase 4, stage 6). The inline
  error with its own Retry is gone: the question stays in the box, so Ask is the retry.
- **The model's working notes no longer show up as answer text** (Phase 4, stage 4). When a model
  call that wrote text ends in a tool call (as in "Missing the rate passage. Search again."), a
  new `text.retracted` event takes that text and its citations back, and the note is shown as a
  progress line instead. If the model then ends with nothing more to say, the taken-back text
  returns as the answer. Nothing sent to the model changes, so the recorded evals still replay;
  only one judge call was re-recorded ($0.01).
- **The Anthropic Console's spend limit has its own error code,** `spend-limit` (Phase 4, stage
  4). It shared `budget-daily` with the demo's own daily cap, so nothing after the turn could tell
  them apart. The person still sees the daily-limit text, already approved, and the eval harness
  reads the code instead of watching the transport.
- **A live eval run reports what it actually paid** (Phase 4, stage 4). Calls answered from a
  reused recording used to be counted as spend, so a run that re-recorded one $0.01 judge call
  printed $0.40. The scoreboard's cost is now the live spend, with the reused recordings' cost
  shown on its own line; the run's cap still counts both, which can only stop a run sooner.
- **The app builds its model transport and embedder at startup** (Phase 4, stage 4), and refuses
  to boot with a setup it can't serve: `scripted` in production, `replay` anywhere, or
  `anthropic` without a key. Voyage is used only when `AI_TRANSPORT=anthropic`, so `make dev`
  and the browser tests make no paid calls even with a Voyage key in `.env`.

- **The live-eval rule names its runs** (Phase 4, stage 3). In `CLAUDE.md`, a change to a prompt,
  a tool, or the guard needs the offline evals green and a smoke run (`make eval-live YES=1`,
  about $1.20, cap $2) before its PR, and a release gets the full run (`SET=full`, about $14, cap
  $16). The "Environment gotcha" note now says `env -u` is no longer needed: the settings have
  ignored an empty exported key since stage 1.
- **The guard's request is built in one place** (Phase 4, stage 3), a pure function that both the
  real call and replay use, so a recording is keyed by exactly what is sent.

- **No em dashes, anywhere** (Phase 4, stage 2). A new writing rule in `CLAUDE.md`, beside the
  American English one. `make check-docs` now fails on an em dash in any file except the frozen
  initial plan, the Claude Design handoff, recorded eval fixtures, and lockfiles. The few in the docs were empty table cells, now "-".
- **The data inventory names Anthropic as a processor** (Phase 4, stage 2): what each turn sends
  to it, what is never sent, and Anthropic's retention and training terms, quoted with their
  source. Voyage now receives the assistant's search queries, not people's whole questions.

### Added

- **The live eval runs time each call** (Phase 4, answer-quality follow-up). Each live guard and
  model call carries its `duration_ms` in the traces, and the scoreboard reports the guard's
  median, p95, and slowest call. The first full run measured a median of 965 ms and a p95 of
  1,992 ms, against the 800 ms target.
- **The conversation page: ask Open Door a question at `/ask` and get a streamed, cited answer**
  (Phase 4, stage 6). The first question turns the assistant home into the conversation, and a
  reload shows it again, a stopped answer included. Every state from screen 07 is on the real
  page now, against the real API.
  - **The answer streams in** with its progress steps ("Searching the handbook…", then "Searched
    the handbook: sick leave"), citation markers as each claim completes, and Stop in place of
    Ask. Source chips, "Was this right?", and "Show your work" appear when it finishes.
  - **A citation opens its handbook passage** beside the conversation on a wide screen (the
    passage stays in the address, so Back closes it), and as a sheet from the bottom on a phone
    or a narrower window, which a swipe down dismisses. Focus returns to the marker that opened
    it.
  - **When the handbook has no answer,** the HR contacts follow it: the HR people from the
    directory, with their job titles and locations, then the shared HR inbox. The server decides
    this from what it stored (a finished answer that searched the handbook and cites nothing),
    never from the model's wording.
  - **The sensitive, crisis, and "can't answer right now" panels** arrive with the answer and are
    announced to screen readers once, never again on a reload. **Budget banners** come from the
    API and disable the composer, and "Start a new sandbox" starts one as the same person.
  - **The composer** checks for a Social Security or card number before sending, so it never
    leaves the browser. That check and the API's share one set of test cases. Pressing Enter while
    an answer streams says "I'm still answering your last question." and keeps the draft. Both
    texts come from a new route, `GET /api/v1/assistant/texts`, so the web app keeps no copy of
    the API's words.
  - **The API sends what the design needs:** HR contacts' titles and locations, each retrieved
    section's title and group (each section listed once), the budget banner's text, and whether
    an answer counts as not found. `GET /api/v1/assistant/budget` gives the same budget state
    before the first question, so the home shows a reached cap too.
  - **Browser tests run against the real API with the scripted model:** one per acceptance
    criterion, with an accessibility scan on each state, the demo's steps (Priya and Mateo get
    their own states' sick leave, Leo's address is refused, the sensitive and crisis paths), a
    persona switch mid-answer, Stop then reload, and the 390 px layout of every state. The
    capture report now shows the real page beside each design.
- **The conversation's components, in every state the design draws** (Phase 4, stage 5). They
  are built and shown in the component gallery on sample data; Stage 6 connects them to the
  live stream and the conversation API. Everything follows screen 07's design and its build
  decisions.
  - **Answers render a small Markdown subset as React elements:** paragraphs, bold, italic,
    lists, and links. Raw HTML shows as plain characters, and only links to `/handbook/` or
    `/directory/` can be clicked. Citation markers are placed where the server says, and the
    model's own text can't fake one.
  - **Markers and source chips are numbered by section,** so marker 1 and chip 1 always name
    the same handbook section. Each marker still opens the exact passage it cites. (The API
    numbers passages, so the web renumbers them in one place.)
  - **Messages:** the person's question, and the assistant's answer with its "AI" label while
    it streams, when it's complete, stopped ("Ask again"), cut off, or failed (the API's own
    error text, with Retry). Progress steps show a spinner on the current step and a check on
    the finished ones.
  - **"Show your work"** lists the safety check's result, the tools called (in plain words, such
    as "Searched the handbook: sick leave"; the profile step just says "Read your profile"), and
    the sections retrieved, each "Cited as N" or "Not cited".
  - **"Was this right?"** with Yes, or No and an optional reason of up to 500 characters, then
    "Thanks for the feedback." Focus moves the way the design's notes say.
  - **The crisis, sensitive, and "can't answer right now" panels** show the API's fixed text
    word for word, are announced to screen readers when they appear, and end with the HR
    contacts: the directory's HR people, then the shared HR inbox. "Call 911" and "call or text
    988" are tap-to-call links in the crisis panel, the can't-answer panel, and both budget
    banners, and the crisis panel also links the 988 chat and the EAP number. No words change.
  - **Budget banners** for a used sandbox budget and the day's demo limit, a conversation header,
    and the composer's new states: Stop while an answer streams, disabled at a budget cap, a
    length hint from 1,800 characters (it blocks sending only past 2,000, counted as the API
    counts), the personal-data warning, the send error, and the long-conversation notice. The
    conversation's composer is one line that grows as you type.
  - **Tests:** unit tests for every component and state, and browser tests for each gallery
    state: an accessibility scan, no sideways scrolling at 390 px, the focus rules, and a check
    that pressing Stop never sends a half-typed next question. The capture report pairs each
    state with its design screenshot.
- **The assistant's conversation routes and its streamed answers** (Phase 4, stage 4). The API
  can now start a conversation, stream an answer to a question, show the current conversation
  after a reload, and take "Was this right?" feedback, all under `/api/v1/assistant`. An answer
  streams as server-sent events: progress notes, tool steps, the answer's text, each citation,
  any escalation to HR, and the end of the turn.
  - **Checks before anything is sent,** each its own error response: the conversation must be
    the person's own (404 otherwise, never 403) and current, the question 1 to 2,000 characters,
    no Social Security or card number in it, one question at a time, and room left in the
    sandbox's and the day's AI budget. The budget check and the page's banner use one
    calculation, so they agree.
  - **A closed tab counts as Stop.** The partial answer is saved as "Stopped", every finished
    model call is settled, and the next question can start. A client that stalls for 30 seconds
    is treated the same way. A call cut off mid-stream keeps its whole reservation, because the
    API reports output tokens only at the end of a stream.
  - **A keep-alive comment every 15 seconds** of silence keeps proxies and load balancers from
    cutting a slow answer, and the stream is never cached or compressed.
  - **A deploy ends streams cleanly.** The app waits up to 12 seconds for open answers to save
    before it closes the database, since uvicorn stops waiting for requests at its own
    graceful-shutdown timeout.
  - **Long conversations:** a new conversation is offered past about 60,000 tokens of history, and
    a question is refused past 80,000, with its own error code, `history-too-long`.
- **`make proxy-check`** (Phase 4, stage 4), also run by `make check` and in CI's browser-test
  job. It puts a deliberately strict nginx (a 20-second read timeout, buffering on, and gzip on
  for event streams) in front of the API with the scripted model, and makes four runs: a
  45-second silent answer must arrive whole, uncompressed, and spread over time, kept alive by
  the heartbeat; a second nginx that compresses anyway must hold the events back, which proves
  the timing checks can fail; the answer with the heartbeat off must be cut at 20 seconds; and an
  API stopped with SIGTERM mid-answer must save the turn as stopped. It takes under two minutes.
  The API runs with `--timeout-graceful-shutdown 15`, which with the app's 12-second drain fits
  ECS's default 30-second stop timeout.
  - **The stream now says `Content-Encoding: identity`.** The check found that an nginx set to
    gzip event streams compresses this one and holds every event back, despite
    `Cache-Control: no-transform`. A proxy leaves a response alone when it already names its
    encoding. RFC 9110 discourages `identity` in this header, but browsers accept it, and it's
    the common way to keep proxies (CloudFront included) from compressing a stream.
- **The personal-data check** (Phase 4, stage 4), `apps/api/app/ai/personal_data.py`. A question
  or feedback reason that holds something shaped like a Social Security number or a card number
  (13 to 19 digits grouped like a real card, passing the Luhn checksum) is refused before it's
  stored or sent. Text pasted from a PDF or Word, with non-breaking spaces, Unicode dashes, or
  full-width digits, is normalized first. Its test cases live in
  `evals/assistant/personal-data-cases.json`, which the web app's copy will read too.
- **`docs/AI-GOVERNANCE.md`** (Phase 4, stage 4): the AI disclosure under Article 50 of the EU AI
  Act, the documented assessment of why the assistant isn't a high-risk system (Annex III,
  Article 6(3) and (4), with the Digital Omnibus's new date of 2 December 2027), the models and
  how they're pinned, the guard, and what goes to Anthropic and Voyage under which terms. Every
  source was read on 2026-10-17.

- **The assistant evals** (Phase 4, stage 3), in `evals/assistant/`. They measure what the
  assistant does with real questions, run through the real turn loop, tools, and database.
  - **Two question sets,** written in employees' own words before any tuning: 42 red-team items
    (other people's private details, injection and impersonation, prompt extraction, and crisis
    and sensitive routing) and 61 Q&A questions (10 the handbook doesn't answer, 6 about another
    state, 4 asking for an employment decision, and "am I talking to a real person?"). A smoke set
    of 25 covers each kind.
  - **Graders by program:** a scan for anyone else's address, phone, personal email, birth date,
    or age, in the many forms a model might write them; the prompt's canary; tool calls outside
    the three tools; crisis and sensitive routing; cited sections that apply to the asker; and
    "couldn't find that in the handbook" with an offer of HR.
  - **A judge,** Claude Sonnet 5.5, answers yes or no on six lines for each Q&A answer: correct,
    faithful to its passages, no uncited policy claim, says whose policy, no employment decision,
    and says it's an AI when asked. It agrees with independent grades on 92% of lines (188 of
    204). Those grades were written by a separate Claude Opus grader that never saw the judge's
    verdicts, and they caught all four deliberately flawed answers. The owner chose not to grade
    by hand, so the judge is validated against another model, not a person: a weaker check, and
    labeled that way.
  - **Offline replay in CI and `make check`.** Live runs record each call's response, keyed by a
    hash of the request, and CI plays them back with no key and no network. A prompt, tool, or
    retrieval change makes a request miss, and the run says to re-record with `make eval-live`.
  - **`make eval-live`** runs the paid evals: smoke by default, `SET=full` or `SET=effort`, and
    only with `YES=1`. Each run has a hard cap ($2, $16, $2) that the budget ledger enforces call
    by call, and writes a scoreboard with the model, versions, dataset hashes, cost, and every
    metric's spread across trials. A re-record calls the model only for requests that changed and
    reuses every other recording; `FRESH=1` re-records everything, and `PRUNE=1` (a full run)
    also drops recordings nothing uses. The run deletes its temporary sandbox and only its own
    daily-ledger rows afterward.
  - **The first live runs:** the smoke set at low effort cost $0.55 and passes every check (red
    team, deterministic Q&A, and unanswerable all at 100%). Medium effort cost $0.66 and fixed
    nothing, so the assistant stays at low effort. They are the first live evidence for stage 2's
    prompts: prompt caching works, the guard's structured output never failed, and every citation
    quotes its passage.
- **The assistant's turn loop** (Phase 4, stage 2). Nothing is reachable from the web app yet.
  - **One turn is one stream of typed events** (started, status, text, citation, tool started and
    finished, escalation, error, completed). The guard reads the question first. Then the model is
    called at most eight times, tools run at the same time and answer in one message, and every
    call is reserved before it starts and settled once after it ends.
  - **History is only ever added to.** A turn goes into history whole, in one write (question,
    context, every tool round, and the answer), only when it ends with an answer. A stopped,
    refused, or failed turn leaves just the question, and a crisis or "can't answer right now"
    turn leaves nothing. Every crisis, sensitive, and "can't answer right now" escalation is
    audited, and a sensitive turn that ends in an error still shows the HR contact.
  - **A turn that is stopped, or whose client leaves, still saves** its partial answer and its
    trace, because the closing writes are shielded from cancellation. A turn is also cut off after
    eight minutes, inside the ten-minute rule that treats a running turn as abandoned.
  - **An answer cut off by the output limit** keeps its text and is marked incomplete.
- **The safety check and the fixed texts** (Phase 4, stage 2).
  - **The guard reads every message first.** It sends the message (and a short piece of the last
    answer) to a small model in labeled tags, and routes the verdict: crisis ends the turn with
    fixed text, sensitive adds a note for the assistant and an HR contact, and anything unclear
    goes to the safer route. If the check fails, times out (4 seconds), or is refused, the turn
    ends with "can't answer right now", 911 and 988, and the HR team's details.
  - **Every message a model must not write is a fixed text:** the crisis text, the sensitive
    stub, "can't answer right now", and the error messages. The owner approved the
    crisis text and the "can't answer right now" text (which also gives 911 and 988) on
    2026-10-15. A test fails if either changes without a new approval. The two budget messages (the
    sandbox's and the day's) also give 911 and 988, because a budget stop comes before the safety
    check, and are approved and hashed the same way.
  - **The HR contact** (names and work emails) is read from the directory.
- **The assistant's prompts, per-turn context, tools, and citations** (Phase 4, stage 2). Nothing
  is reachable from the web app yet.
  - **The prompts are versioned text files** for the assistant and for the safety check that reads
    each message first. A test pins each prompt's hash to its version, so a prompt can't change
    without a new version (and the evals rule in `CLAUDE.md`).
  - **Each turn gets a short context message** with the person's first name, role, location, and
    employment type, the handbook version, and today's date in their location's timezone, never the
    sandbox's anchor date.
  - **Three read-only tools:** `search_handbook` (up to five passages as citable sources, for the
    asker's office or a named one), `get_my_profile` (the asker's own details, audited as an
    assistant read), and `find_people` (directory cards only, for everyone or the asker's team).
    No tool input can name whose data to read, and a bad input comes back as an error the model can
    correct. A new `escalation.offered` audit action is ready for the escalation offer.
  - **Citations are mapped to handbook passages.** A citation's result and block numbers become
    one event per cited passage, with a marker that keeps its number when a passage is cited
    again. A citation that doesn't match what was sent is dropped and logged without its text.
- **The assistant's storage, budgets, and model connections** (Phase 4, stage 1). Nothing is
  reachable from the web app yet; stage 2 builds the turn on top of this.
  - **Conversations are stored append-only.** Six new tables hold conversations, messages, turns,
    feedback, and two spending ledgers. Messages come back exactly as they were stored, because
    Claude Opus 5.5 refuses a history whose earlier turns have changed. A turn can be updated
    only while it runs; once it ends, it is frozen.
  - **AI spending is capped:** $1.00 per sandbox and $3.00 a day across every sandbox, set by
    `AI_SANDBOX_BUDGET_USD` and `AI_DAILY_BUDGET_USD`. Before each model call, the server reserves
    what one attempt at the call could cost, under a database lock, and settles the difference
    afterward, so two questions at once can't both slip under a cap. If a safety decline makes a
    call fall back to another model, the declined attempt and the fallback attempt are both
    billed, at the fallback model's higher price for the second, which can carry the total past
    the cap by about one attempt at that price. Prices are pinned per model, with their source.
  - **Three ways to answer, chosen by `AI_TRANSPORT`:**
    - `anthropic`: the real API, with server-side fallbacks and the model's progress notes
    - `scripted`: a rule-based stand-in for Claude, and the default, which costs nothing and
      drives the crisis, sensitive, refusal, not-found, slow, and failing paths on demand
    - `replay`: reserved for stage 3's offline evals

    A transport check refuses `scripted` or `replay` in production, and the `anthropic` transport
    refuses to start without `ANTHROPIC_API_KEY`. Stage 4 runs both when the API starts; until
    then nothing builds a transport. Migrations and scripts need neither.
  - **The Anthropic Python SDK** (`anthropic` 1.13), which only the `app.ai` package may import,
    and `httpx2`, the HTTP library it is built on, as a runtime dependency rather than a test-only
    one.

### Fixed

- **Fixes from the v0.4.0 release review** (Phase 4, before its release).
  - **The evals grade more strictly where it matters.** The unanswerable check no longer takes
    "If you can't find the details in the handbook, ask HR" as the assistant saying it found
    nothing, so a made-up, cited answer to an unanswerable question fails. The red-team scan for
    other people's private details now also reads the status notes and any text the stream took
    back, since both reached the person. Re-grading the recorded 2026-10-19 run moved no score.
  - **Smaller grader fixes:** the asker's own phone number without its area code is no longer
    flagged as someone else's; an age written as "Javier Mendoza, 45," is caught; one leak is
    reported once, wherever it showed; the canary check reads taken-back text too; the search
    query is measured by the tool's own check; and a malformed dataset or traces file gets a clear
    error instead of a traceback.
  - **The conversation page:** "Start a new conversation" can't create two, and a question sent
    while it's starting goes to the new one (or stays in the box if it couldn't start).
  - **The assistant:** a refused answer's partial text is taken back on screen at once, as it
    already was on reload; a question's own problems (too long, personal data) are reported before
    "this conversation is too long"; and the scripted stand-in model searches long questions
    instead of answering "not found".

- **Small fixes from the Phase 4 review** (Phase 4, phase review).
  - **The conversation page:**
    - Under a budget stop, "Ask again" and "Try again" are hidden like Retry. Before, they sent a
      question the server refused, and it vanished without a word.
    - A "still answering" reply now loads the turn that's running.
    - A conversation that no longer exists stops being checked for unfinished answers.
    - A question with spaces around it is no longer sent twice when the connection drops before
      the answer starts.
    - A reply that isn't an answer stream (a misconfigured proxy's page) counts as a failed send
      and keeps the question in the box.
    - Opening a source no longer reloads the whole conversation.
  - **The assistant:**
    - A broken character in the model's text (a lone UTF-16 surrogate) becomes a replacement
      character, instead of failing the turn and leaving the conversation busy for 10 minutes.
    - The directory search measures the model's query after cleaning it, as the handbook search
      already did.
  - **The evals and the proxy check:**
    - Their cleanup deletes the run's daily spending rows and its sandbox in one transaction, and
      the eval keeps its sandbox when it can't read the sandbox's spending, so a failure can't
      leave rows behind that fill the shared daily cap.
    - The scoreboard's commit is read before the run saves its recordings, so it is no longer
      always marked "dirty".
    - A wrong `--compare` file is refused before any paid call.
    - The proxy check's holding control fails on an error response.
    - CI now runs the proxy check's own tests when only its script changes, and lint and type
      checks cover it.

### Security

- **A card number followed by its expiry or security code is caught** (Phase 4, v0.4.0 release
  review). The personal-data check read "4242 4242 4242 4242 123" as one 19-digit number, which
  failed the card checksum, so the card went through to the model and the database. Each grouped
  number is now also tried without its last group, in the API and the browser alike.

- **A stopped sensitive question still reaches HR, and the model can't fake a citation** (Phase 4,
  phase review). The whole-phase review found no high issues and these two medium ones:
  - A question the safety check marked sensitive (harassment, for example) that the person then
    stopped got no HR contact panel and no audit event, live or after a reload. Sensitive topics go
    to a person on every ending now, including a stop (invariants 6 and 7).
  - The model could write an HTML character reference (`&#xE000;`) that the answer renderer
    turned into a working citation marker, so an uncited sentence looked cited (invariant 4). Those
    references are now dropped before the markers are placed.

  The personal-data check also catches a Social Security number written as nine digits in a row, or
  with dots or slashes between its groups, in the API and the browser alike.

- **One visitor can't stall the API, and a question can't get stuck** (Phase 4, stage 4). An Opus
  security review of the routes and the stream found one high issue, now fixed: about 15
  questions sent at once each held a database connection while waiting for a second one, which
  froze every request in the process for 30 seconds. The stream route now never holds one
  connection while it takes another. A failure or a cancel right after a question was saved can
  no longer leave it "running" for 10 minutes, and the prompt's canary check now also catches
  the canary in capitals, spaced out, or split by Markdown. The cache of embedded search queries
  is kept per sandbox, so a fast search can't tell a visitor that someone in another sandbox
  asked the same thing. The review confirmed the rest: every
  route answers 404 for another person's conversation or turn, the stream needs the CSRF token
  and the same-origin check, and many conversations at once can't spend past the sandbox's cap.

- **The assistant can't be turned against its own server or other visitors** (Phase 4, stage 2).
  An Opus security review found no high issues and one medium, now fixed: a single model response
  could start hundreds of tools at once. Now at most 5 run per response, 3 at a time, and 20 per
  question. The system prompt's canary (a hidden phrase that exposes a leaked prompt) is withheld
  from everything sent to the browser, even split across messages or padded with invisible
  characters. The crisis text never waits more than 2 seconds on the HR contacts, and the browser
  no longer receives cache counts or costs that could hint at another visitor's question.
- **No one, HR included, can read another person's conversations** (Phase 4, stage 1). Every
  assistant table that holds a sandbox's data has row-level security, which is Postgres hiding
  rows the database session isn't allowed to see. It's scoped to the sandbox, and a second rule
  scopes the conversation tables to the person. The one global table, the demo's daily spending
  total, holds only dates and amounts.
  Keys that point at a conversation or turn also name its owner, so no one can attach a row to
  someone else's conversation even by knowing its ID. The spending ledgers refuse negative
  reservations, out-of-range amounts, and forward-dated days; only a settlement may be dated
  the day before, so a question that crosses midnight UTC settles on the day it reserved.
- **An empty API key in the shell no longer hides the one in `apps/api/.env`** (Phase 4, stage
  1). The settings ignore `ANTHROPIC_API_KEY` or `VOYAGE_API_KEY` when the shell sets it to an
  empty string, so an agent shell that exports one empty can't shadow the real key, whatever
  starts the process. Every other setting still fails when it's empty.

## [0.3.0] - 2026-10-14

Phase 3: the handbook and its search. Juniper Row's fictional handbook (23 company sections, plus
state addenda for California, Colorado, Texas, and Georgia, with every statutory figure checked
against its official source) is loaded into the database with its embeddings, and each sandbox is
pinned to one version of it. Hybrid search (full text and embeddings, fused by rank) scores 100%
at 5 on the retrieval eval, with every negative case passing. Anyone in a sandbox can browse,
search, and deep-link the handbook, and see which sections apply to them. A new Atlanta store
brings the company to 145 people. The phase closed with a whole-phase review, a release review,
and their fixes.

### Added

- **Juniper Row opens an Atlanta store, and the handbook gains Georgia's rules** (Phase 3, stage
  6).
  - **The company grows to 145 people,** with 25 at the Atlanta store. Everyone who existed before
    is unchanged, and a test pins that.
  - **Georgia's addendum (GA-4.5):** court attendance is job-protected, and anyone in Georgia may
    take up to 2 paid hours to vote on Election Day or an early-voting day, whatever their
    schedule.
  - **A lactation section for everyone (5.4):** paid breaks as often and as long as needed,
    whatever the child's age, and a clean, safe, private space that is never a restroom. A
    California addendum (CA-5.4) adds the state's premium pay and complaint rights. Each figure
    was checked against its official source on 2026-10-13.
  - **Handbook version 2026.10.1.** Links to addendum sections no longer carry a section sign
    ("CA-5.1", not "§CA-5.1").
  - **The retrieval eval** gains 16 questions from Georgia staff and about lactation, and still
    scores 100% at 5, with every negative passing.

- **The handbook browser** (Phase 3, stage 5). Handbook is in everyone's navigation.
  - **The handbook home** lists every section by chapter, then the state addenda, with who each
    applies to, when it was last updated, and an "Applies to you" marker on the restricted
    sections that cover you. "Applies to me" narrows the list, and search finds sections by their
    words, applicable ones first, with the matched words marked. No results offers "Ask the
    assistant", which puts the search in the chat box without sending it.
  - **A section page** shows the section with its state rules or the company section it adds to,
    its sources, previous and next, and the chapter navigator. A deep link such as
    `/handbook/CA-4.3?passage=p2` highlights the passage and moves focus to it. A section that
    doesn't apply to you says why and links to the one that does, and a section that isn't in
    your handbook version says so.
  - **The assistant home** shows when the handbook was last updated.
  - Every acceptance criterion in the design notes has a browser test, with axe on every state
    and a check at phone width.

- **The handbook components** (Phase 3, stage 4), built from the approved design and shown in
  every state in the gallery: the "Applies to" badge, the "applies to you" marker, the last
  updated date, section rows and groups, the chapter navigator, search results with the matched
  words highlighted, the section body, the cited passage with "Clear highlight", the "State
  rules" and "Supplements" blocks, the Sources block, and the passage panel (open, loading,
  error, and a long passage that scrolls inside). Everything renders as React elements; a new
  test fails if any file ever renders raw HTML. Each state has an axe check, and the passage
  panel's focus behavior is tested in a real browser. The API's references to related sections
  now carry the addendum's name ("California addendum").

- **Handbook search, its eval, and the handbook API** (Phase 3, stage 3).
  - **Search for the assistant:** `search_handbook` finds the passages that answer a question by
    combining keyword search with search by meaning, merged into one ranking, and only over the
    sections that apply to the person asking, in their sandbox's handbook. If Voyage can't be
    reached it falls back to keywords alone and says so. Phase 4's assistant will call it.
  - **The retrieval eval:** 71 questions written in employees' own words, including 14 that must
    never show someone another state's rules or a section for hourly staff they aren't. CI fails
    below a 90% hit rate in the top 5 or on any failed negative, with no network. It scores 100%
    (57 of 57) with a mean reciprocal rank of 0.841. `make eval-retrieval` runs it.
  - **Four handbook routes** for the browser: the section list with "Applies to", "Last updated",
    and whether each section applies to you; one section as structured content (never HTML); one
    passage with its neighbors, for the passage panel; and keyword search that requires every word
    and marks the matched words. Each reads only the sandbox's own handbook version.

- **The Juniper Row employee handbook** (Phase 3, stage 1). Twenty-two company sections in seven
  chapters, plus twelve state addendum sections for California, Colorado, and Texas, written as
  markdown in `handbook/` for the retrieval work that follows. Every statutory figure, such as an
  overtime threshold, a final-pay deadline, or a sick-leave amount, was checked against the state
  labor department, the U.S. Department of Labor, or the statute on 2026-10-07, and each section
  records its sources. The company's own figures (paid time off, sick leave, bereavement, jury
  pay) are fictional policy chosen to meet or beat all three states. Paid time off has a balance
  ceiling rather than a year-end carryover cap, because California and Colorado don't allow earned
  vacation to be forfeited. The handbook is demo content, not legal advice, and says so.
- **The handbook becomes data** (Phase 3, stage 2), ready for the search that follows.
  - **Ingestion:** `make ingest` checks every section against a strict markdown subset (no HTML,
    images, tables, or outside links; links only to other sections), reporting every problem
    with its file and line. It numbers each paragraph and list as a citable passage, groups
    passages into chunks for search, and loads the result as one immutable, published version.
    `make db` now ends with it. Running it again on unchanged files does nothing.
  - **Embeddings:** each chunk's meaning is captured as a vector from Voyage AI's `voyage-4`
    model, through a small client that batches, retries, and never logs the key. The vectors are
    committed in `handbook/embeddings/`, so tests and CI never call Voyage. `make embed` is the
    only command that does, and it costs nothing within Voyage's free allowance. A version's
    fingerprint covers the files and the vectors, so a changed vector needs a new version label.
  - **Each new sandbox is pinned** to the newest published handbook by the database itself, so an
    answer always cites the handbook the sandbox was created with. With no handbook loaded,
    starting a sandbox answers "The handbook isn't loaded yet." and creates nothing.
  - **Who a section applies to** (by state, employment type, and location) is decided by one pure
    function, with exact expected sections recorded for every persona.
  - **The API can only read the handbook.** Its database role has `SELECT` on the three new
    tables and nothing else, and only the ingestion script, connecting as the database owner,
    can write them.

### Changed

- **Search excerpts start at the beginning of the sentence** with the match, and list items are
  separated (Phase 3, stage 5).
- **The development and CI databases use a pinned image,** `pgvector/pgvector:0.8.7-pg17`, rather
  than whatever `pg17` pointed to on the day (Phase 3, stage 2).
- **The secret scan skips the generated embedding caches** (Phase 3, stage 2). Each line's key is
  a hash of public handbook text, which gitleaks mistook for an API key. Every other file is
  scanned with the default rules, as before.

### Security

- **Failed database statements no longer log their values** (Phase 3, stage 3), so an error can
  never write a search question or other bound text to the log.

### Fixed

- **Fixes from the v0.3.0 release review** (Phase 3, before its release).
  - **A search result's excerpt always comes from the passage it links to.** When the words
    matched only a heading, or only the meaning matched, the excerpt showed other text from the
    section while the link highlighted a different passage.
  - **A search of only invisible characters** (such as a zero-width space) is no search, instead
    of an error that Retry could never clear.
  - **A passage ID that can't exist** gets "This passage isn't in that section", not the
    missing-section message.
  - **The retrieval eval says "Run `make db` first"** when no handbook is published, instead of
    ending in a database traceback.

- **Fixes from the Phase 3 close-out review** (Phase 3, the whole-phase review).
  - **A search result's highlighted words now show on its one line at desktop width.** A match
    that ended past the edge of the line at 1440 px was cut off; the excerpt now starts a few
    words before any match more than 90 characters in, and never cuts into the match itself. On
    a phone's narrower line, a later match can still fall past the edge.
  - **A section page stays up when only the handbook overview fails,** leaving out the chapter
    navigator instead of showing "Something went wrong". Coming from the list, the navigator
    still shows at once.
  - **Changing the Show filter right after typing keeps the search,** so Back undoes only the
    filter.
  - **A section or passage ID of "." or ".." no longer reaches another API path;** it shows as
    missing without a request.
  - **`make check` loads the handbook, as CI does,** so it no longer tests against an old or
    missing handbook version.

- **A flaky browser test in CI** (after Phase 2). The check that another person's profile leaks no
  private value read each API response's body after the fact, and on CI's single worker one body
  was gone by then. It now records every body as the response passes through, so none can be
  lost. A planted background request for private details still fails it.

## [0.2.0] - 2026-10-06

Phase 2: the design system, the app shell, and sandbox entry. A visitor picks a persona, lands in
a private sandbox, and can switch persona, sign out, and find anyone in the directory, seeing only
the profile fields their role allows. The design is built from the approved Claude Design screens,
every acceptance criterion has a browser test with axe, and the phase closed with a whole-phase
review and a new logo. The assistant itself arrives in Phase 4; until then it gives one fixed,
person-written reply.

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

- **A new logo: the door ajar** (Phase 2 close, with Claude Design). The mark is an aubergine tile
  with a doorway and its open door. The app's logo draws it in theme colors, and the browser now
  gets real icons: an SVG favicon, 16 and 32 px fallbacks, an Apple touch icon, and a web app
  manifest with a 512 px icon. The design's mark is updated to match.
- **The design plan for the phases ahead** (design track, 2026-10-06). After the Phase 2 screens,
  Claude Design proposed enhancements. The brief now records what was settled:
  - the order of design work, which follows the build order: a logo round first, then the handbook
    browser;
  - corrections where an idea would contradict the project's rules: no "the AI won't read it", no
    conversation deletion, and no memory of past questions;
  - new screens for later phases, with matching backlog entries.
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
- **Phase 2 close-out review fixes.**
  - **Directory links from another sandbox:** a location or department that isn't one of this
    sandbox's options is no filter, instead of "0 of 120 people" under menus that say "All".
  - **Directory filters that fail to load:** the list still shows, the count and the menus are
    hidden, and a "We couldn't load the filters." message offers Retry.
  - **Opening a row quickly after typing a search** no longer loses the search when you come back.
  - **A read that gets a 401 asks who is signed in before deciding.** Another tab's switch or
    sign-out no longer shows "This sandbox has reset." while the sandbox is alive, and an expired
    sandbox no longer bounces from the landing page to the assistant and back.
  - **The schema hook** rewrites any default 422 to the problem-details body, so a route that
    forgets to declare it can't leave a dangling reference.
  - **The production-build check for the component gallery** now shares its marker with the
    gallery's heading and fails if the two drift apart.
  - **A profile test** no longer depends on the time of day.

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
