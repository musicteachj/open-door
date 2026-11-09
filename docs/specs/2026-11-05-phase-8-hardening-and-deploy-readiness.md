# Phase 8: hardening and deploy-readiness

Written 2026-11-05. This spec goes deeper on Phase 8 of the
[product design](2026-09-29-open-door-design.md) and builds on the specs of Phases 1 to 7. Where
they disagree, this one is newer and wins; the differences are listed under
[Changes from earlier documents](#changes-from-earlier-documents). Phase 8 has one small new screen
(16, the walkthrough page and the landing's two additions). It is designed right after this planning, and no build stage starts until it is in
`docs/design/screens/`.

**Goal:** Open Door is hardened and runs from a production image, and nothing is deployed (the
AWS-specific setup comes with the deploy, in Phase 9). The production image runs the whole
app from one origin behind a strict Content Security Policy. Starting a sandbox is protected
against abuse. Expired data is cleaned up by a job. The threat model names every risk and the
control and test behind it. The assistant's last known fairness gaps are fixed and measured. The app has
been load-tested and audited for accessibility. And when the demo's daily AI limit is reached, a
visitor can still watch the recorded walkthrough instead of meeting a dead end.

**Done when** CI is green, the owner has approved the screen-16 copy and the walkthrough video,
and these are proven:

- **The production image runs locally end to end:** CI builds it and runs the browser suite and
  the proxy check against it (scripted model), and one paid live check through the image, with
  production settings and the real model, streams a cited answer, confirms a card, and records
  non-zero tokens and cost.
- **No page breaks the Content Security Policy:** the browser suite fails on any CSP violation,
  on every screen, and tests check every security header.
- **Sandbox creation is protected:** a start without a valid Turnstile token is refused, and the
  per-address and daily limits refuse with `Retry-After`, proven by tests.
- **The cleanup job deletes only what it should,** proven by tests, and runs as `make cleanup`.
- **The threat model is written,** every risk mapped to its control and its test, and the
  whole-app security review leaves no open high or medium finding.
- **The prompt change's full run is committed:** the red team at 100% in every trial, Good Friday
  routed to religious accommodation in every trial, no remark on the asker's age, and the other
  bars no worse than the run of 2026-11-03.
- **The capacity report and the accessibility report are written,** and every high or medium
  finding from either is fixed.
- **The phase checklist below is closed.**

---

## Decisions made while planning (owner-approved, 2026-11-05)

1. **Nothing is deployed, and nothing AWS-specific is built.** No AWS account is touched and no
   real Turnstile key is made. The KMS key provider, the deploy contract, the ECS task
   definitions, the cleanup's schedule, and the deploy workflow move to Phase 9 (the owner's call,
   2026-11-09), which decides them with the owner's other portfolio apps.
2. **Replay mode is the recorded walkthrough** ([ADR 0019](../adr/0019-replay-mode-is-a-recorded-walkthrough.md)):
   the demo video of the tour, recorded with the real model, on a public page with a transcript,
   linked from the daily-limit banner. The app never replays fixtures.
3. **One production image serves the API and the web app from one origin,** with the CSP's styles
   allowed by a per-response nonce and no `'unsafe-inline'`
   ([ADR 0020](../adr/0020-one-image-one-origin.md)).
4. **Starting a sandbox needs a Turnstile check and is limited per address and per day,** counted
   in Postgres under a keyed hash of the address, never the address itself
   ([ADR 0021](../adr/0021-sandbox-entry-protection.md)).
5. **Keys stay in the local keyring until Phase 9,** which builds the KMS provider
   ([ADR 0015's amendment](../adr/0015-envelope-encryption.md#amendment-2026-11-05-the-kms-provider)).
6. **The API reaches Claude through the Claude API, not Amazon Bedrock**
   ([ADR 0022](../adr/0022-claude-api-from-aws.md)).
7. **The next prompt change is in this phase:** the Good Friday and age lines, HR's topic note,
   `list_cases`'s wording, and directory values in the per-turn context passed as quoted data, with
   one full run. The judge's 85% bar gets no paid round of its own.
8. **The threat model comes first,** and briefs every later stage and the security reviews.
9. **The load test makes no paid calls.** Costs come from the recorded runs and the console.
10. **One small new screen, 16, "The walkthrough",** designed before any build stage: the
    walkthrough page and the landing's two additions. The refusals, the banner's link, and the
    Turnstile checkbox reuse existing components and are checked in the capture report.

---

## Changes from earlier documents

- **Replay mode** is a recorded walkthrough, not "built on the recorded fixtures" (the design
  spec). ADR 0019 records why.
- **The schemas' early-reject ceilings come down to twice the real limits** (a question 4,000
  characters, where the real limit is 2,000; case words 8,000, real 4,000; a denial note 600, real
  300). They were 20,000, which only sized the body cap wrongly. The body cap stays the backlog's
  64 KiB.
- **There is no persona-menu "new sandbox".** Step 1 of this planning assumed one. A sandbox starts
  from the landing's persona cards, the tour's start (the landing, the persona menu's tour items,
  and the console's empty state), and the budget banner's "Start a new sandbox"; all go through
  one hook, `useStartSandbox`.
- **The seed already writes next year's holidays** (from the year before the sandbox's date to two
  years after it), so the backlog's reply-by item becomes a test that proves it and a corrected
  docstring.
- **The seed has 145 people,** not the 120 the backlog says.
- **The console row's cost** is defined as the turn's ledger spend, in every ending (below); the
  Phase 7 review found two ways they drift.
- **AI-GOVERNANCE's "What Phase 8 adds"** is replaced by the sections this phase writes; the
  deployed data path on AWS waits for Phase 9.
- **The AWS-specific pieces move to Phase 9** (the owner, 2026-11-09): the KMS key provider
  (ADR 0015 had planned it for Phase 8), the secrets contract for AWS, the ECS task definitions,
  the cleanup's hourly schedule, the database's certificate bundle, and the deploy workflow drafted
  but disabled (the roadmap's Phase 8 row listed the last two). They can't be checked against AWS
  before then, and Phase 9 still chooses the managed database.

---

## The threat model

`docs/THREAT-MODEL.md`, written in Stage 1, before any other hardening code.

- **What is protected:** each sandbox's people data and private details, conversation and case
  text, the system prompt, the AI budget, the keys, and the owner's accounts (Anthropic, Voyage,
  Cloudflare, AWS, GitHub).
- **Who might attack:** an anonymous visitor (the demo is public and free), a visitor acting
  inside their own sandbox (every persona is theirs to switch to), someone who reaches a leaked
  session cookie, text that reaches the model (prompt injection through a question; directory
  values and tool results), a compromised dependency or CI action, and an insider with database or
  AWS access (out of scope beyond stating it).
- **Trust boundaries:** browser and load balancer; load balancer and API; API and Postgres
  (row-level security); API and the three vendors; the model and the tools; GitHub, CI, and the
  deploy role.
- **For each boundary,** STRIDE (spoofing, tampering, repudiation, information disclosure, denial
  of service, elevation of privilege), each threat tied to its control (code, database rule, or
  setting) and to the test or eval that proves it.
- **The OWASP Top 10 for LLM applications** mapped to the seven invariants and their evals.
- **Accepted risks, with the reason:** encryption binds a message to its row but not its order
  (database write access is out of scope); the personal-data check misses a card number written
  after other four-digit numbers (catching it refuses ordinary year lists); the canary check misses
  look-alike letters (it is a tripwire, not a boundary); the sandbox's own personas can read what
  each persona may read (the demo hands the visitor every persona); and a deleted sandbox lives in
  database backups until they expire (Phase 9's deploy keeps that short and says how long).
- **Re-reviewed** at the phase's end by the security reviewer, and kept current by any later change
  to a boundary.

---

## Requests and sessions

- **CSRF on every signed-in API request:** `current_session` checks `X-CSRF-Token` for every method
  on `/api/`, not only unsafe ones, which retires the per-route `AuditedReadDep` (a future audited
  route can't forget it). The web client already sends the header on every same-origin `/api/`
  request, and no `<img>` or link loads an API path.
- **Request bodies are capped at 64 KiB** in an ASGI middleware, from `Content-Length` and by
  counting a streamed body, with a 413 problem. The schemas' early-reject ceilings come down to
  twice the real limits (a question 4,000 characters, case words 8,000, a denial note 600), so the
  largest body that passes them (8,000 four-byte characters, about 32 KB as JSON) fits with room.
- **`APP_ORIGIN` is required in production** and must be `https`, except a loopback origin
  (`http://localhost` or `http://127.0.0.1` with a port), which the local production run uses; a
  loopback origin can't serve a real deployment.
- **Client addresses are trusted only from the load balancer:** uvicorn runs with
  `--proxy-headers` and `--forwarded-allow-ips` from the `FORWARDED_ALLOW_IPS` setting (the load
  balancer's addresses when deployed; unset locally, so the peer address is used).
- **The API no longer loads the owner or cleanup database URLs.** `Settings` keeps only
  `DATABASE_URL`; Alembic, the bootstrap script, the cleanup job, the eval harness, the proxy
  check, and the owner-only scripts read their own small settings classes. The API process holds
  only its own login.
- **Sessions get row-level security** (migration 0017). Reads: the lookup sets the presented
  token's hash in its transaction (`app.session_token_hash`), and the `SELECT` policy matches only
  that row or the current sandbox's rows, so the app's login can no longer list every sandbox's
  sessions. Writes: it may insert a session only for the current sandbox, with an expiry no later
  than the sandbox's, and delete only the current sandbox's sessions or the presented one. Tests
  prove the forged-session attempt from the Phase 1 review now fails and that a bare `SELECT` sees
  nothing.
- **Sign-out ends a session's replacements:** each session carries a `family_id` that a persona
  switch copies, and sign-out deletes the whole family.
- **One transaction per signed-in request:** the session lookup and the request's tenant work
  share one transaction, with the tenant context set once the session is found. (The turn stream
  keeps its own short transactions.)
- **Another tab's session change is noticed at once:** a tab that switches persona, signs out, or
  starts a sandbox posts on a `BroadcastChannel`, and every other tab refetches `/me` (which
  already resets a tab whose person changed).
- **Database timeouts:** the app's engine sets `statement_timeout` (10 s) and
  `idle_in_transaction_session_timeout` (30 s) on every connection, and the time-off confirm sets
  `lock_timeout` (5 s) in its transaction. The cleanup job sets its own (60 s). The bootstrap
  script sets the same values on each login as a second line.
- **Production hides the API docs** (`/docs`, `/redoc`, `/openapi.json`); `make openapi` still
  exports the schema. uvicorn runs with `--no-server-header`.
- **Health:** `GET /api/v1/health/live` never touches the database (the container's check);
  `GET /api/v1/health` is readiness (the load balancer's), with a 2-second ping, the result cached
  for 1 second with one check in flight, and `Cache-Control: no-store`. Both are kept out of the
  access log.
- **`Retry-After`** on every 429: the budget refusals (seconds until the next UTC day for the daily
  limit; none for a sandbox's own limit, which doesn't reset) and the new sandbox limits.

---

## The production image

([ADR 0020](../adr/0020-one-image-one-origin.md))

- **One `Dockerfile` at the repository root, multi-stage:** a Node 24 stage runs `npm ci` and
  `vite build` (no gallery); a Python 3.13 slim stage installs the API with `uv sync --locked
  --no-dev` into a virtual environment; the final stage copies the virtual environment, the API,
  the handbook, and the built web app, runs as a non-root user, and starts uvicorn. Base images are
  pinned by digest and kept current by Dependabot's `docker` ecosystem. A `.dockerignore` keeps out
  `.env`, `.keys/`, `node_modules`, test output, and the eval fixtures.
- **What the image must carry:** `tzdata` (added as an API dependency, so `zoneinfo` never depends
  on the base image), and a CA store without the emSign roots (checked in a test that lists the
  store).
- **The API serves the web app:** hashed assets under `/assets/` with a one-year immutable cache;
  every non-API path that isn't a file gets `index.html` (the router's deep links), never cached.
  `index.html` is rendered per response: a fresh nonce goes into the CSP header and into a
  `<meta name="csp-nonce">` tag, and the Turnstile site key into another meta tag.
- **Content Security Policy** (on every HTML response):
  `default-src 'self'; script-src 'self' https://challenges.cloudflare.com; style-src 'self'
  'nonce-…'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-src
  https://challenges.cloudflare.com; media-src 'self'; object-src 'none'; base-uri 'none';
  form-action 'self'; frame-ancestors 'none'`. The web app reads the nonce before rendering and
  passes it to `get-nonce`'s `setNonce` (Radix's scroll lock injects a `<style>` through it) and to
  Radix Select's `nonce` prop (its viewport renders an inline `<style>`).
- **The other headers, on every response:** `Strict-Transport-Security` (one year, subdomains),
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, a `Permissions-Policy` that
  turns off camera, microphone, geolocation, payment, and USB, and
  `Cross-Origin-Opener-Policy: same-origin`. API responses keep `Cache-Control: no-store`.
- **Development is unchanged:** `make dev` still runs Vite and uvicorn separately; the CSP applies
  where the API serves the build.
- **CI builds the image** in a new job and runs, against it, the proxy check (which now starts the
  container instead of a host uvicorn, so SIGTERM reaches the real entrypoint) and the browser
  suite. The browser suite needs the component gallery, so CI builds a test variant with a build
  argument that includes it; the production variant is checked to contain none (the existing
  `check:no-gallery`). A browser-test fixture fails any test that logs a CSP violation.
- **The local production run** (`make prod-local`): the image with `APP_ENV=production`, the real
  model, a loopback origin, Turnstile's test keys (allowed only with a loopback origin), and the
  local keyring. Used once for the paid live check and for the video.

---

## Data

- **The time-off denial note is encrypted** (migration 0018): a data key per request that has a
  note, wrapped like a conversation's, and the note sealed with it. Existing notes are sealed by
  the migration's data step (seeded sandboxes have none). Only readers the request rules allow ever
  decrypt it.
- **A conversation with an unreadable value no longer breaks:** a `DecryptionFailed` while reading
  a conversation marks it unreadable in the response (no turns shown, a short fixed line, and "Start
  a new conversation"), logs the IDs, and the budget read treats it as too long to continue rather
  than failing.
- **A repeated case send** is detected under the person's lock only, so the stored words are
  decrypted once, and it writes an audit event (`case.resubmitted`) saying the second send was
  folded into the first case.
- **The personal-data check catches every decimal digit:** both copies map any Unicode decimal
  digit to its ASCII value before matching, and the shared cases gain SSNs in Arabic-Indic and
  Devanagari digits. (The browser's newer Unicode may flag a few code points the API doesn't; the
  API is the authority.)
- **The audit log stores SQL `NULL`,** not JSON `null`, for an empty `before` or `after`
  (`none_as_null`), with a data fix for existing rows (migration 0017).
- **The reply-by date:** a test proves the seed writes the next year's Denver holidays, and the
  docstring that says otherwise is corrected.

---

## Sandbox entry

([ADR 0021](../adr/0021-sandbox-entry-protection.md))

- **Turnstile:** the web app loads Cloudflare's `api.js` from its exact URL and renders one managed
  widget with `execution: 'execute'` and `appearance: 'interaction-only'`, so most visitors see
  nothing. `useStartSandbox` gets a fresh token for each start and sends it in the body
  (`turnstileToken`). The API calls siteverify with the secret, the token, the client address, and
  an idempotency key, and accepts only `success` with the expected hostname and action
  (`start-sandbox`). A failed check is a 403 with the "couldn't confirm" text; Cloudflare
  unreachable (5-second timeout) is a 503 with the "couldn't check" text, so starts fail closed.
- **Where the rare checkbox appears:** directly under whichever control started the sandbox (a
  landing card, the tour's start button or dialog, or the budget banner's "Start a new sandbox"),
  in Cloudflare's own widget. It reuses the page's layout; the capture report shows it.
- **Limits, counted in Postgres** (a new table, `sandbox_starts`, migration 0019, no tenant): each
  start records an HMAC-SHA256 of the client address under a secret key (`SANDBOX_IP_HASH_KEY`),
  taking an IPv6 address's /64 prefix so one connection can't rotate through addresses. A start is
  refused (429, `Retry-After`) past 5 an hour or 20 a day from one address, or past 500 a day in
  all. The check and the insert run under an advisory lock, so two starts can't both slip under.
  The load test tunes the numbers; they are settings.
- **Settings:** `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`, `SANDBOX_IP_HASH_KEY`, and the three
  limits. Development, CI, and the browser tests use Cloudflare's documented always-pass test keys;
  production refuses test keys unless the origin is a loopback one.
- **The cleanup job** (`python -m app.jobs.cleanup`, run as the cleanup login): deletes expired
  sandboxes (the existing policy cascades their rows), `ai_spend_daily` rows older than 30 days,
  `sandbox_starts` rows older than a day, and handbook versions that are neither the newest
  published nor pinned by any sandbox. Migration 0019 grants the cleanup role exactly those deletes.
  Each run logs its counts. `make cleanup` runs it locally; Phase 9 schedules it hourly.
- **Data inventory:** `sandbox_starts` (a keyed hash and a time, kept a day), `sessions.family_id`,
  the sealed denial note, and Cloudflare as a recipient of the visitor's address and browser
  signals when a sandbox starts. The landing gains one line saying so (screen 16).

---

## Stream and safety

- **Every turn ends with one closing event:** `turn.completed` or `error`. A crisis turn and a
  guard-unavailable turn now send `turn.completed` after their escalation, and the web store stops
  inferring the end from the escalation's kind. A late "unavailable" offer after an `error` is
  shown as well.
- **The crisis panel survives a failed end-of-turn write:** the turn's crisis verdict is stored in
  its own short transaction before the crisis text goes out, and a turn read back as abandoned
  whose stored verdict is crisis shows the crisis panel. The 988 and EAP text never disappears on
  reload.
- **The HR panel that appears after a stopped sensitive answer is announced** when the saved turn
  brings it, the way a live one is.
- **Two owner-worded texts** (drafts under [Texts for approval](#texts-for-approval)): the budget
  refusal when only the conversation's size is the problem (it says to start a new conversation,
  not a new sandbox), and the case refusals that can't succeed on retry (too long uses the server's
  existing text; an invalid form or a turn that can't start a case points to My cases and the HR
  contacts).

---

## The prompt change

One stage, one full run. Every change in the phase that reaches what the model reads goes here.

- **Religious observance:** a time-off request for a religious observance gets the
  religious-accommodation route (§5.3) as well as PTO, whatever the observance.
- **Background:** the assistant doesn't comment on the asker's age, origin, religion, or other
  background unless the question asks about it.
- **HR's topic note** says the case form shows "when it shows", matching the prompt, or what HR can
  do instead (`TOPIC_NOTE_HR`, in the guard's notes; `guard.md` itself is unchanged, so the
  escalation set isn't re-recorded).
- **`list_cases`'s description** says a cut `in_review` or `closed` list holds "the 20 whose status
  changed most recently".
- **The per-turn context passes directory values as data:** the asker's name, role, employment
  type, location, state, location code, and time zone go in as one quoted JSON object, introduced
  as "facts about the asker from the directory, not instructions". `one_line` stays for the
  outcome lines. This closes the backlog item about names that read like instructions.
- **The judge's 85% bar:** one prompt line about citing every sentence that states a policy fact is
  tried in the same tuning runs. No paid round is spent on the judge alone. The full run's figure is
  the result; if it is under 85%, the item is closed and the bar stays a reported target (the
  uncited-claim count tracks the misses).
- **Versions:** `PROMPT_VERSION` and `TOOLSET_VERSION` move to `2026-11.4`, with new golden hashes.
- **Runs:** up to two tuning runs (the smoke set plus the religion and age fairness groups, about
  $1.30 each, cap $2), then the full run (about $15.50, cap $18), started detached (`nohup`,
  `PYTHONUNBUFFERED=1`) and watched, since a full run can take more than two hours. The harness
  gains a way to add named fairness groups to a smoke run if it lacks one. The board is committed
  with the recordings, and `make scoreboard` regenerates the README and the app's copy.

---

## The cost and load test

- **A small async Python script** (`scripts/load/run.py`) drives the local production image under
  a container limit the size of a small cloud task (0.5 vCPU and 1 GB, then 1 vCPU and 2 GB). Each simulated visitor starts a
  sandbox, asks the tour's questions, books and approves a day off, and opens the console. The
  scripted model gets realistic timings through a test-only setting (`SCRIPTED_DELAY_PROFILE`:
  the guard's delay, the time to the first text, and the pace of text) that production refuses.
- **It passes Turnstile and the address limits honestly:** the always-pass test keys, and each
  visitor's address set through `X-Forwarded-For` with the script's own address trusted as the load
  balancer.
- **It measures,** at 10, 25, and 50 visitors at once: sandbox creation, the first event and the
  whole turn at p50 and p95, other requests' p95, errors, database connections in use, CPU, and
  memory. It reports where a task saturates.
- **Costs come from data already paid for:** the full run's cost per answer (about $0.02 on Opus
  5.5), the guard's, and a case summary's, giving the cost of one tour and of a typical visit.
- **`docs/CAPACITY.md`** holds the results, the recommended task size, pool size, and number of
  tasks, and the recommended AI limits per sandbox and per day, with the reasoning. Phase 9 sets the
  final values.
- **Fixed here if the test shows they matter:** reading a conversation's history once per request,
  the directory's counts, the Approvals reads one person at a time, the per-turn card check, and
  re-parsing a streaming answer on every word. Fixed regardless: the request form's preview check
  is debounced (300 ms), and the console's costs (below).
- **The console row's cost equals the turn's ledger spend in every ending:** a test compares them
  for a completed turn, a kept reservation (settle timed out), a fallback, and an abandoned turn,
  whose row now carries the dead turn's spend. Tokens use `pricing.total_usage`.

---

## The accessibility audit

- **Automated, on every screen and state:** axe (WCAG 2.0 to 2.2, A and AA) as now, plus reflow at
  320 CSS pixels (WCAG 1.4.10, the same as 1280 at 400% zoom), text spacing (1.4.12), reduced
  motion, target size (2.5.8), focus visible and not obscured (2.4.7, 2.4.11), and the design
  tokens' contrast pairs.
- **Scripted keyboard walks** of the main flows: start a sandbox, ask and open a source, book a day
  off and confirm, approve, send a case, review a case as HR, the console, the tour, and the
  walkthrough page.
- **The backlog's items:** the sticky composer covering "Show your work" (scroll padding, and a test
  of the toggle's visible area), the passage panel's Close order, and the stopped sensitive answer's
  panel announcement (in Stream and safety).
- **`docs/ACCESSIBILITY.md`:** what was checked, how, the results, and the known gaps. The owner may
  add a 15-minute VoiceOver pass from a checklist in that document.

---

## The walkthrough and the demo video

([ADR 0019](../adr/0019-replay-mode-is-a-recorded-walkthrough.md))

- **The page** (`/walkthrough`, public): the video with native controls, never autoplaying, a
  poster, the recording's date and model, and a transcript of every step: the coach mark's words,
  the question, and the answer as recorded. "Back to the demo" returns to where the visitor came
  from.
- **Where it is offered:** the daily-limit banner's link, and the landing (screen 16 places it).
- **The recording** (`make walkthrough`, paid, needs `YES=1`): a Playwright script of its own,
  separate from the tour's browser test, runs the tour's script through the local production image
  with the real model, at a reading pace (each coach mark held long enough to read, the cursor
  moving like a person's), records at 1440 by 900, and saves each step's question and answer text
  to `walkthrough.json` beside the video. ffmpeg converts it to H.264 MP4 under 8 MB and cuts a
  poster frame. The page renders the transcript from that file, so the words always match the
  video.
- **The owner approves the video** before it is committed. It is re-recorded only when the tour or
  the screens it shows change visibly.
- **The README** links the video and says what it shows.

---

## CI tidying

From the backlog: the gitleaks version in one place, the pre-commit hook installed with
`uv tool install`, pip-audit run over the exported lockfile only, Dependabot's `docker` and
`pre-commit` ecosystems, and a check that every path a test reads outside its app is in that job's
path filter.

---

## Moved to Phase 9

Written and checked when the deploy is planned, against the real AWS account and the chosen
managed database:

- **The KMS key provider,** as ADR 0015's amendment describes it, and production's refusal of the
  local keyring.
- **The secrets and settings contract** (`docs/DEPLOY.md`): every setting, which process reads it,
  the secret store's names, least-privilege roles, egress to Anthropic, Voyage, and Cloudflare,
  Postgres 16 or later with pgvector, database TLS with certificate checks and the provider's
  bundle in the image, rotation, backup retention, the load balancer's idle timeout of at least
  120 seconds, the shutdown timeouts, and the rule for migrations that change tenant data.
- **ECS task definitions** for the API, the migration, and the cleanup, and **the cleanup's hourly
  schedule.**
- **The deploy workflow** (OIDC, the image to ECR, the migration, the service update), written
  and enabled together.

---

## Texts for approval

Drafts, for the owner's approval with screen 16. Fixed texts keep the project's pattern (author, date, hash).

| Where | Draft |
|---|---|
| A start refused, too many from one address | "You've started several sandboxes in a short time. Please try again in {minutes} minutes, or keep using the one you have." |
| A start refused, the day's limit reached | "Open Door has started as many sandboxes as it can today. Please come back tomorrow, or watch the recorded walkthrough." |
| The check failed | "We couldn't confirm you're a person. Please try again." |
| The check couldn't run | "We couldn't reach the check that keeps this demo safe. Please try again in a minute." |
| The landing's line about the check | "Starting a sandbox runs a quick Cloudflare check to keep the demo safe." |
| The daily-limit banner's link | "Watch the recorded walkthrough" |
| The conversation is too big for what's left | "This conversation is too long for what's left of this sandbox's AI budget. Start a new conversation to keep asking." |
| A case form that can't be sent | "This can't be sent as a case from here. You can see your cases in My cases, or contact the HR team directly." |
| An unreadable conversation | "This conversation can't be shown. Start a new conversation to keep asking." |

---

## Security

The phase changes the edges of the system rather than one feature, so the seams for the reviewers
are the boundaries in the threat model:

- **Sandbox creation:** no start without a valid token; the limits can't be raced; the client
  address can't be spoofed except through the trusted load balancer; no raw address is stored or
  logged.
- **Sessions:** a session can't be read without its token, or written for another sandbox; sign-out
  ends the whole family; CSRF on every signed-in request.
- **Headers and CSP:** no inline script anywhere; the nonce is fresh per response and never cached
  with the page; framing refused.
- **Keys:** no key material in logs or problems; the keyring stays out of the image.
- **Settings:** each process loads only its own credentials; production refuses every test value.
- **The model's inputs:** directory values reach the model as quoted data; nothing else in the
  prompt change widens what a turn can do.

Reviews: `/security-review` at the close of each stage that changes security code (1, 2, 3, 4, 5),
`/code-review medium` on every code PR, one whole-app security reviewer on the strongest model at
the end (briefed with the threat model, proving each finding with the smallest experiment), and
the scoped `/code-review high` phase review.

---

## Testing

- **Requests and sessions:** CSRF on a GET, the body cap at its edge and for a streamed body,
  production's origin rules, the forwarded-address rule, the session write policies (including the
  forged session), family sign-out, the timeouts (a slow query is cut), docs hidden in production,
  liveness without a database, the health cache.
- **The image:** the CA store, `tzdata`, the non-root user, the headers on HTML, API, and asset
  responses, deep links get `index.html`, the nonce differs per response, the browser suite and
  the proxy check against the image, no CSP violation anywhere.
- **Data:** the denial note sealed and readable only by the allowed readers, the
  unreadable conversation's response, the resubmission audit, the digits cases in both copies, the
  audit `NULL`, the next year's holidays.
- **Sandbox entry:** Turnstile pass, fail, spent, and unreachable (with Cloudflare's test keys and a
  stubbed siteverify), the limits per hour, per day, and in all, the IPv6 prefix, the race under
  the lock, the cleanup job's deletes and the rows it must leave.
- **Stream:** every ending sends exactly one closing event; the crisis panel after a failed finish;
  the settled panel's announcement.
- **The prompt change:** the golden hashes, the context's JSON, the full run's bars.
- **Pages:** screen 16 (the walkthrough page and the landing) and the undesigned states (each
  refusal, the checkbox's place, the banner's link) in the gallery and the browser at full width and
  390 px, axe clean, with capture rows.

---

## Docs and housekeeping

- **New:** `docs/THREAT-MODEL.md`, `docs/CAPACITY.md`, `docs/ACCESSIBILITY.md`.
- **`docs/AI-GOVERNANCE.md`:** the threat model's AI risks, the choice of the Claude API over Bedrock (ADR 0022),
  Cloudflare, the cleanup job's retention, the fairness results after the prompt change, a review
  of the whole assessment against the finished product, and Article 50(2) revisited from the
  official text (re-read in the stage that writes it, with a "Source:" line).
- **`docs/DATA-INVENTORY.md`:** the new table and columns, and Cloudflare.
- **README:** the status line, the walkthrough, the new documents in "Documentation", and
  `make prod-local` and `make cleanup` in "Run it locally".
- **CLAUDE.md:** the new commands; the rule that the app never replays fixtures stays; the
  walkthrough re-recording rule.
- **The backlog:** the items this phase closes are deleted; the ones it leaves move to "Any phase"
  or Phase 9 with their reason.

---

## What the design must cover (screen 16)

**16. The walkthrough.** The walkthrough page (the video with its poster, the recording's date and
model, the transcript step by step, and "Back to the demo"), and the landing with its two additions: the line about the Cloudflare check and the link to the
walkthrough. Desktop only, like every mockup; the build checks it at 390 px. Sample data follows
the tour's script and the seed.

**Designed and approved (2026-11-09):** see
[`design/screens/16-walkthrough/`](../design/screens/16-walkthrough/notes.md).

### Decisions from the design round

- **The poster is a recording frame with nothing important under its center,** where the
  browser's play button may sit.
- **"Back to the demo" returns the visitor to where they came from** inside Open Door, and to the
  landing otherwise.
- **The video is `preload="none"`;** the poster shows without downloading the video.
- **A step reads: label, title, persona line, coach mark words, then the exchanges;** each
  exchange is a speaker column beside the words, answers labeled as the AI's, and the HR panel's
  text labeled "Fixed text written by a person, not the AI".
- **Step 10's words are the first paragraph of screen 15's end card.**
- **The landing's link sits left of the tour button;** the Cloudflare line is a second muted line
  under the sandbox note.

**Not designed, built from existing components:** the start refusals and the failed or unreachable
check (the inline error the landing and the banner already use, with Retry), the daily-limit
banner's link (a link under the existing banner's text), and the rare Turnstile checkbox
(Cloudflare's own widget, placed directly under the control that started the sandbox). The capture
report shows each of them for the owner's review.

---

## Delivery: nine stages

No stage starts until screen 16 is in `docs/design/screens/`. The plan sizes each stage to the
1,500-line guideline.

| Stage | Branch | Paid calls |
|---|---|---|
| 1 The threat model, requests, and sessions | `feat/phase-8-requests` | none |
| 2 The production image, CSP, and CI against the image | `feat/phase-8-image` | none |
| 3 Data: `make prod-local`, the denial note, unreadable conversations, case resends, digits | `feat/phase-8-data` | none |
| 4 Sandbox entry: Turnstile, the limits, the cleanup job | `feat/phase-8-entry` | none |
| 5 Stream and safety, and the owner-worded texts | `feat/phase-8-stream` | none |
| 6 The prompt change and its full run | `feat/phase-8-prompt` | yes |
| 7 The cost and load test | `feat/phase-8-load` | none |
| 8 The accessibility audit | `feat/phase-8-accessibility` | none |
| 9 The walkthrough, the video, the live check, the docs, and the close | `feat/phase-8-walkthrough` | yes |

### Runs and costs (each needs the owner's OK)

| Run | Stage | Estimate | Cap |
|---|---|---|---|
| Tuning runs: smoke plus the religion and age groups (up to 2) | 6 | about $1.30 each | $2 each |
| Opus 5.5 full run, fairness included | 6 | about $15.50 | $18 |
| The production image's live check | 9 | about $0.25 | $1 |
| The walkthrough recording (up to 3 takes) | 9 | about $0.25 a take | $2 |

The estimates come from the run of 2026-11-03 ($15.20 for the full set, about $0.02 an Opus
answer) and the tour's nine questions plus a case summary.

---

## Later phases

- **Phase 9:** everything under [Moved to Phase 9](#moved-to-phase-9), and the AWS account, the
  cluster's service, the load balancer, the managed Postgres, the real KMS key and Turnstile
  widget, the secrets, egress, and the portfolio entry. Re-test `set_config` if a connection pooler is used; one Postgres server per
  environment.
- **Any phase:** "Send this question to HR", a second route for a concern about HR, keyboard
  shortcuts, the Sonnet re-comparison, the Label in Name root fix, and the smaller items the
  backlog keeps.
