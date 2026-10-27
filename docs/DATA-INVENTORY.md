# Data inventory

Every piece of data Open Door stores: what it holds, why it's kept, who can see it, and how long it
stays. Update this file in the same change as any new table, column, cookie, or log field.

Every person in Open Door is fictional. Each visitor gets a sandbox company, seeded with the same
145 made-up people, and the whole sandbox is deleted 24 hours after it is created. The
[Phase 1 spec](specs/2026-10-03-phase-1-tenancy-identity-permissions.md) has the design behind
this, and [ADR 0007](adr/0007-session-lifetime.md) explains why sessions last as long as the
sandbox.

## How long data is kept

**Everything in a sandbox lives for 24 hours.** `tenants.expires_at` is set to 24 hours after
creation. Every other row belongs to a tenant and is deleted with it, through the foreign keys'
`ON DELETE CASCADE`, except the handbook tables and `ai_spend_daily`, which have no tenant (see
their sections below). A session is refused as soon as it expires, even before its row is deleted.
The scheduled cleanup job that deletes expired sandboxes arrives in Phase 8. Until then, the
`od_cleanup` role can delete only expired sandboxes, and tests prove it.

**The 24-hour delete is a demo choice, not a model for real employee data.** A real deployment
would keep audit records for at least 4 years, outside the tenant cascade. California requires
employers to keep personnel and employment records for 4 years, and its rules on
automated-decision systems apply that to the data such systems use and produce.

> Source: California Government Code §12946(a), as amended by SB 807 (Stats. 2021, ch. 278), read
> from leginfo.legislature.ca.gov on 2026-10-04.
>
> Source: Civil Rights Council, employment regulations regarding automated-decision systems,
> 2 CCR §11013(c), effective 2025-10-01. The four-year period was confirmed in the Council's Final
> Statement of Reasons (June 2025), read from calcivilrights.ca.gov on 2026-10-03.

## Who can see what

- **Tenant isolation.** Postgres row-level security shows the API only the rows of the sandbox its
  transaction belongs to. The API's database login can't skip that rule. The one exception is
  `sessions`, described below.
- **Directory fields** are visible to everyone in the same sandbox.
- **The assistant's conversations** (messages, turns, and feedback) are visible only to the person
  they belong to, with no HR exception. A second, restrictive Postgres rule enforces it.
- **Time-off requests and opening balances** are tenant rows: Postgres shows them to everyone in
  the sandbox, and the policy layer (`app/policy`) decides who reads which (a manager reads their
  reports', HR reads everyone's).
- **The assistant's proposals** (`ai_proposals`, Phase 5) are visible only to the person they were
  made for, with no HR exception, like the conversations: the same restrictive rule enforces it.
- **Private details** are visible only to the person themselves and to HR. Both the policy layer
  (`app/policy`) and a second, database-level rule enforce this.
- **The `/me` fields** (`employmentType`, `isManager`, `isHrAdmin`, `personaKey`, and
  `tenantExpiresAt`, the sandbox's expiry) are shown only to the signed-in person, about
  themselves.
- **The database owner** runs migrations. It reads no data in the normal course of things. In
  development it is the superuser of the Docker Compose database.

## Tables

### `tenants`: one sandbox company

| Column | Holds | Why |
|---|---|---|
| `id` | A random UUID | Identifies the sandbox. Random, so one visitor can't guess another's. |
| `created_at` | When the sandbox was created (UTC), stamped by the database on insert | The lifetime cap counts from it: `expires_at` may be at most 25 hours later. No one can choose it, so no one can stretch a sandbox's life. |
| `expires_at` | 24 hours after `created_at` | When the sandbox and everything in it are deleted. Copied to each session and to the cookies' `Max-Age`. |
| `anchor_date` | The UTC date the sandbox was created | The seed data's dates count back from it, so "last week" always means last week. |
| `handbook_version_id` | The handbook version the sandbox answers from | A database trigger sets it when the sandbox is created, to the newest published version, whatever the caller supplies, and refuses to create a sandbox if none is published. It's empty only for sandboxes created before the handbook existed. A version a sandbox points to can't be deleted. |

Visible to the API only for its own sandbox, and to the cleanup role only once it has expired.

### `locations`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id` | IDs | Identity, and the sandbox it belongs to. |
| `code`, `name`, `city`, `state` | Denver HQ (CO), the Oakland store (CA), the Austin warehouse (TX), the Atlanta store (GA) | The directory shows each person's location and state. Each state's handbook addendum applies by location (Phase 3). |
| `timezone` | An IANA zone, such as `America/Denver` | Leave dates are calendar dates in the location's time zone (Phase 5). Directory cards and `/me` carry it in their `location`. It describes a place, not a person, so it isn't personal data. |

Visible to everyone in the sandbox. Deleted with the sandbox.

### `departments`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id` | IDs | Identity, and the sandbox it belongs to. |
| `name` | One of eight department names | Shown on each directory card. |

Visible to everyone in the sandbox. Deleted with the sandbox.

### `people`: the directory

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id` | IDs | Identity, and the sandbox. |
| `given_name`, `family_name`, `title`, `work_email` | Fictional names, job titles, and `juniperrow.example` addresses | The directory card. |
| `department_id`, `location_id` | References | The directory card, and the rules that depend on location. |
| `manager_id` | The person's manager | The reporting line. Being a manager is derived from it on every request, never stored. |
| `employment_type` | `salaried` or `hourly` | Company PTO accrues at a fixed amount per employment type (Phase 5). Shown only at `/me`. |
| `hire_date` | A date relative to `anchor_date` | Part of a realistic employee record, for later phases. Not shown by any Phase 1 endpoint. |
| `is_hr_admin` | Whether the person is HR | HR may read private details. Shown only at `/me`. |
| `persona_key` | `priya`, `mateo`, `marcus`, `dana`, or null | Which people a visitor can sign in as. Shown only at `/me`. |
| `scheduled_weekdays` | The ISO weekdays the person works, as a list of numbers from 1 (Monday) to 7 (Sunday), for example `{2,3,4,5,6}`. A check refuses an empty list and any number outside 1 to 7 | The time-off engine counts only these days against a request (Phase 5). The column defaults to Monday to Friday, so a sandbox made before it existed gets a normal week, and the seed writes every person's days explicitly. |

The directory fields are visible to everyone in the sandbox. Deleted with the sandbox.

### `person_private`: private details

| Column | Holds | Why |
|---|---|---|
| `person_id`, `tenant_id` | IDs | Whose details these are, and the sandbox. |
| `personal_email` | An `example.com` address | A realistic HR record that the demo can protect. |
| `phone` | A number ending in 555-0100 to 555-0199, reserved for fiction | The same. |
| `home_address` | A made-up street address | The same. |
| `date_of_birth` | A date relative to `anchor_date` | The same. |

Visible only to the person themselves and to HR. Every read writes a `person_private.read` audit
event that names the fields returned, never their values. Deleted with the sandbox.

### `holidays`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id`, `location_id` | IDs | Identity, the sandbox, and the location that closes. |
| `holiday_date`, `name` | The company holiday calendar from the year before `anchor_date`'s year to two years after it (four years) | The time-off engine skips these days (Phase 5). The year before covers leave taken just before an anchor in early January. The two after reach the engine's last allowed date even when a sandbox crosses New Year. |

Visible to everyone in the sandbox. Deleted with the sandbox.

### `sessions`: who is signed in

| Column | Holds | Why |
|---|---|---|
| `token_hash` | The SHA-256 hash of the session token | Finds the session from the cookie. The raw token is only in the visitor's cookie. |
| `csrf_hash` | The SHA-256 hash of the CSRF token | Checks the `X-CSRF-Token` header on requests that change something. |
| `tenant_id`, `person_id` | The sandbox, and the persona signed in | Scopes every request to that sandbox and person. |
| `created_at`, `expires_at` | When the session started, and the sandbox's expiry | A session never outlives its sandbox. |

Outside row-level security, because a session is looked up before its sandbox is known. The API
finds a session only by its token hash, and never lists sessions. Switching persona deletes the
row and creates a new one, and signing out deletes it. Deleted with the sandbox in any case.

### `audit_events`: what happened

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id` | A random UUID, and the sandbox | Random rather than a sequence, so one sandbox can't estimate another's activity. |
| `occurred_at` | When it happened (UTC) | The record. |
| `actor_person_id`, `via` | Who acted, and how: `ui`, `assistant`, or `system` | Every action, including the assistant's from Phase 4, is attributed. |
| `action`, `target_type`, `target_id` | What was done, and to what | Phase 1 records `sandbox.created`, `session.persona_switched`, `session.ended`, and `person_private.read`. Phase 4 adds `escalation.offered` (target `ai_turn`), written when the assistant shows the crisis, sensitive, or "can't answer right now" panel, and when a budget stop ends a turn before the safety check could run (`kind` `unavailable`, `reason` `budget`: the budget message carries 911 and 988 instead of a panel), and `person_private.read` with `via` `assistant` when `get_my_profile` runs. Phase 5 adds `timeoff.requested` (PTO) and `timeoff.recorded` (sick time) when a request is made, `timeoff.approved`, `timeoff.denied`, and `timeoff.canceled` (target `time_off_request`), and `proposal.created`, `proposal.confirmed`, `proposal.canceled`, and `proposal.failed` (target `ai_proposal`). |
| `before`, `after` | Non-private fields only, such as `personaKey`, the names of the private fields read, an escalation's `kind`, or a time-off request's `status`, `type`, `startDate`, and `endDate` | Never private values, so a privacy deletion request never means editing this log. A denial's note (`decisionNote`, `note`) is refused here like a private field, so text a person wrote can't be logged by mistake. |
| `proposal_id` | The confirmed proposal, from Phase 5. It is a foreign key to `ai_proposals`, within the same sandbox | Ties an executed action to what the person confirmed. |
| `request_id` | The request's ID | Matches the event with that request's log lines. |

Append-only: the API can add and read events but never change or delete them. Visible to the API
within its own sandbox. No endpoint shows them yet. Deleted with the sandbox, which is the demo
choice described above.

### The assistant: `ai_conversations`, `ai_messages`, `ai_turns`, `ai_feedback`, `ai_spend`, `ai_spend_daily`

Added in Phase 4 (migration 0008). Nothing writes to them until the assistant's turn code arrives
later in Phase 4.

**All conversation text is encrypted at rest (Phase 6, migration 0012, ADR 0015).** That is every
question, answer, stored message, tool-call input summary, and feedback reason, whether or not the
guard flagged it. The API seals each value with AES-256-GCM under a data key that belongs to its
conversation, and the database stores only ciphertext: it never holds a key or the text. The data
key is stored wrapped (`ai_conversations.wrapped_key`) by a key-encryption key from the keyring,
and each ciphertext is bound to its table, column, sandbox, and row, so a value copied to another
place fails to open. Labels and numbers stay readable, for the console: the guard's verdict,
statuses, citations (handbook passages), retrieved sections, tool names, results and durations,
tokens, and costs.

**The keyring.** The key-encryption keys are lines of `id:base64`, newest first, in a file
(`apps/api/.keys/keyring`, written by `make setup`, git-ignored, mode 600, refused if anyone but its
owner can read it) or in `ENCRYPTION_KEYRING`. The API will not start without one. Neither value is
ever printed or logged. Tests and CI use a fixed fake key (all zero bytes, ID `test`) that the API
refuses outside `APP_ENV=test`. Losing the keyring makes every sandbox unreadable, which for
24-hour demo sandboxes means starting new ones. Phase 8 adds a managed key service.

**Old plaintext may linger briefly.** Migration 0012 deleted every sandbox and dropped the plaintext
columns, but Postgres keeps the dropped and deleted data in dead rows and in its write-ahead log
until a vacuum and the log's recycling. Only the development databases that ran Phase 4 and 5 are
affected, since nothing is deployed.

The sandbox is fictional, the landing page asks visitors not to enter real personal information,
and everything is deleted with the sandbox after 24 hours.

Every ID below is a random UUID, so one sandbox can't estimate another's activity.

### `ai_conversations`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id`, `person_id` | IDs: the conversation, its sandbox, and the person who owns it | Identity, and the one person who may read it. |
| `created_at` | When it began (UTC) | Finds a person's newest conversation. |
| `key_id`, `wrapped_key` | The ID of the key-encryption key that wrapped this conversation's data key, and the wrapped data key (ciphertext) | Opens the conversation's sealed text. The wrapped key is bound to its sandbox and this row. |
| `model`, `guard_model`, `effort`, `prompt_version`, `toolset_version` | The pins: the assistant's model, the guard's model, the effort setting, and the prompt and tool-set versions at the start | A conversation keeps its model, prompt, and tools for its whole life, so its history stays valid and replayable. |

### `ai_messages`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id`, `person_id`, `conversation_id`, `turn_id` | IDs: the message, its sandbox, its owner, its conversation, and the turn that produced it | Identity and ownership. |
| `position`, `role` | The message's place in the conversation (from 0), and `user`, `assistant`, or `system` | The model has no memory: each turn sends the history back in order. |
| `content_ciphertext` | The message exactly as the model API takes it, as JSON text, encrypted. It decrypts to the same text, byte for byte. It includes the person's question, the model's replies, and tool results such as handbook passages and the person's own directory card or private details | The history for the next turn. The text is kept exactly because the model's signed thinking blocks must come back unchanged. |
| `sources` | For each handbook search result in the message, in order: the section ID, the passage IDs, the title, the group name, the audience label, the last-updated date, and the link. Null when the message has none | The conversation's list of sources, rebuilt for citations, including from turns that were stopped or failed. The result text alone can't give these back reliably. |
| `reported_outcomes` | On a per-turn context message only: for each confirm card whose outcome that context told the model about, `<card id>:<status shown>` (a card whose time ran out shows as `expired`). Null on every other message | The next turn tells the model about each card's status once, and again if the card changes later (expired, then confirmed by a request already in flight). What was told, not a clock comparison across transactions, decides what is news. |
| `created_at` | When it was stored (UTC) | The record. |

### `ai_turns`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id`, `person_id`, `conversation_id` | IDs: the turn, its sandbox, its owner, and its conversation | Identity and ownership. |
| `question_ciphertext` | What the person asked, encrypted | Shown after a reload. |
| `status`, `error_code` | `running`, `completed`, `stopped`, `failed`, `crisis`, or `guard_unavailable`; and a code. A failed turn's code is the one its error event sent (`refusal`, `model-unavailable`, `budget-sandbox`, `budget-daily`, `spend-limit` (Anthropic's Console spend limit), `too-many-calls`, `internal`), or a more exact one the client sees as `internal`: `prompt-leak` (the system prompt's canary was caught and withheld), `guard-error` (the safety check couldn't run), or `abandoned`. A completed turn cut off by the output limit has `max-tokens`. | One turn runs at a time per conversation. The code explains a failure or an incomplete answer. |
| `started_at`, `ended_at` | When the turn began and ended (UTC) | The record. |
| `answer_ciphertext` | The answer, encrypted (a stopped turn keeps its partial text). Null until the turn first saves an answer, and read as an empty answer | What the person sees after a reload. |
| `citations` | The answer's citations as JSON (handbook passages) | What the person sees after a reload. |
| `guard_verdict` | The guard's verdict as JSON; null if the guard did not run | Phase 7's console shows why a turn was routed. The browser gets the category and kind only (`GET /assistant/conversations/current`), never `injectionSuspected`, the cost, or the cache counts. |
| `tool_calls`, `sections_retrieved` | Each tool call (name, a short summary of its input, success, duration), and the handbook sections the search returned. Each input summary is stored encrypted (the base64 of the sealed text, inside the JSON, bound to its place in the list); the name, success, and duration stay readable | What the assistant did. A search's summary holds up to 60 characters of its query (and `find_people`'s up to 40), after control characters are removed. A time-off tool's summary holds its scope, dates, and decision, up to 40 characters of a `person_name`, and a request's ID. Tool calls past the limits (5 per response, 20 per question) aren't run, and a second card in one response isn't made; a round records each kind as one `skipped` entry with a `count`. The summaries never hold private values. |
| `served_by_models`, `effort`, `prompt_version`, `toolset_version` | The model IDs that served the turn, and the settings in effect | Explains a result, and shows when a fallback happened. |
| `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `cost_usd` | Token counts and the cost at list price | Measures cost and caching. |
| `first_event_ms`, `total_ms` | Milliseconds to the first visible event, and in total | Measures latency. |
| `refusal`, `fallback`, `injection_suspected` | Yes or no | Phase 7's console counts these. |

### `ai_feedback`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id`, `person_id`, `turn_id` | IDs: the feedback, its sandbox, its owner, and the answer it rates | One per answer. |
| `helpful`, `reason_ciphertext` | A thumbs up or down, and an optional reason of at most 500 characters, encrypted (the limit is checked before sealing) | So the owner can see which answers helped. |
| `created_at` | When it was given (UTC) | The record. |

### `ai_spend`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id`, `turn_id` | IDs: the row, its sandbox, and the turn it belongs to | Identity. There is no person: the budget is the whole sandbox's. |
| `kind`, `amount_usd` | `reserve` (the most a call could cost, never negative) or `settle` (the actual cost minus the reservation, so it can be negative); and the dollar amount, between -10 and 10 | The sandbox's AI budget (`AI_SANDBOX_BUDGET_USD`) is the sum. |
| `created_at` | When it was added (UTC) | The record. |

### `ai_spend_daily`

Global: no sandbox, no person, no text, and outside row-level security.

| Column | Holds | Why |
|---|---|---|
| `id` | A random UUID | Identity. |
| `day` | The UTC date the row is added; a settle may instead carry its reservation's day, the day before | The demo's daily cap (`AI_DAILY_BUDGET_USD`) is the sum for a day across all sandboxes. |
| `kind`, `amount_usd` | `reserve` or `settle`, and a dollar amount, with the same limits as `ai_spend` | The same reserve-then-settle ledger. |
| `created_at` | When it was added (UTC), always the server's clock | The record, and what `day` must match. |

**Who sees them.** `ai_conversations`, `ai_messages`, `ai_turns`, and `ai_feedback` are visible to the
person they belong to and to no one else, HR included: Postgres enforces a second, restrictive rule
on top of the sandbox rule. Phase 7 decides what the console may show. `ai_spend` is the sandbox's
own ledger: its sum covers everyone in the sandbox, so people in one sandbox can see each other's
turn IDs and the timing of their calls there, though never a question or an answer. A sandbox is one
visitor playing fictional personas, so that is accepted, and no route returns these rows.
`ai_spend_daily` holds amounts only, so it is visible to every sandbox's API session.

**How long.** The first five are deleted with the sandbox, 24 hours after it is created.
`ai_spend_daily` has no sandbox to be deleted with: its rows older than 30 days are deleted by
Phase 8's cleanup job. The API can add rows but not change or delete them, except that a turn's
outcome and trace columns can be updated while it is `running`. Once it ends, a trigger refuses any
further change.

### Time off: `time_off_openings`, `time_off_requests`, `ai_proposals`

Added in Phase 5 (migration 0009). Every ID is a random UUID. The time-off service
(`app/modules/timeoff`) is the only writer of requests; the proposal confirm route arrives in
stage 3.

#### `time_off_openings`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id`, `person_id` | IDs: the row, its sandbox, and whose balance it is | Identity. One row per person. |
| `as_of`, `amount_minutes` | A date, and the person's PTO balance on it in minutes (never negative) | The engine counts a balance forward from here on every read. A balance is never stored (ADR 0012). |
| `created_at` | When it was added (UTC) | The record. |

#### `time_off_requests`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id`, `person_id` | IDs: the request, its sandbox, and who it is for | Identity. |
| `type` | `pto` or `sick` | A PTO request is approved by a manager. A sick day is recorded, with no approval. |
| `start_date`, `end_date` | Calendar dates in the person's location's time zone, both inclusive, at most 31 days apart | The days asked for. |
| `partial_minutes` | Null for whole days. Otherwise 240 (half a day of PTO) or a whole number of hours from 60 to 480 (sick leave), on a single day | A partial day. |
| `amount_minutes` | The engine's count when the request was made | Kept for the record, so a later change to a schedule or the holidays doesn't rewrite what a person was shown. |
| `status` | `pending`, `approved`, `denied`, `recorded` (a sick day), or `canceled` | Where the request stands. It moves one way: a trigger refuses any other change. |
| `created_at`, `created_via` | When (UTC), and `ui` or `assistant` | How it was made. |
| `proposal_id` | The assistant's proposal that made it, or null for a request made on the page | Ties the request to what the person confirmed. It is always the same person's proposal, and one proposal makes at most one request. |
| `decided_by`, `decided_at` | Who approved or denied it, and when | The decision's record. They stay when an approved request is canceled. A person never decides their own request: a database check refuses it. |
| `decision_note` | A manager's reason for a denial, up to 300 characters, or null | Shown to the employee on the page and the card. Also read back to the manager who wrote it, in the conversation read (`deniedNote` on an executed denial's card), so the card can say whether a note was sent after a reload; no other person gets it there, and the stream event and the confirm's own answer never carry it. **User-written text: it is never sent to a model**, in a tool result or anywhere else. |
| `canceled_at` | When it was canceled, or null | The record. |

Two open requests (pending, approved, or recorded) for one person can't share a day: an exclusion
constraint refuses them in the database.

#### `ai_proposals`

| Column | Holds | Why |
|---|---|---|
| `id`, `tenant_id`, `person_id`, `conversation_id`, `turn_id` | IDs: the proposal, its sandbox, the person it was made for, and the conversation and turn that made it | Identity and ownership. The keys make the conversation and turn that person's own. |
| `action` | `timeoff.request`, `timeoff.decide`, or `timeoff.cancel` | What confirming it would do. |
| `payload` | The validated tool input, as JSON in camelCase: for a request its type, dates, and partial minutes; for a decision the request's ID and `approve` or `deny`; for a cancel the request's ID | The model proposes and never writes: confirming runs this stored payload, never anything the browser sends. It never holds a note. |
| `card` | The details the server built for the confirm card, as JSON in camelCase: the type and dates, the counted and skipped days, amounts and balances (each a flat pair such as `amountMinutes` and `amountLabel`, the same as the time-off routes; a request card's balances are a `draws` list, one entry per calendar year the request draws on, with its year, amount, and balance before and after, the same shape as the request check), warning codes, the approver's name, handbook section links, and for a decision the requester's name and title and the names and days of teammates who are off | What the person sees and confirms. It is built from the engine's results and the directory, never from model text, and never holds a note or anything a person wrote. A teammate's days off are context for the person deciding and are never sent to a model. |
| `status` | `pending`, `executed`, `failed`, `canceled`, or `expired` | A proposal ends once, from `pending` to one of the others. A trigger refuses any other change. |
| `created_at`, `expires_at`, `ended_at` | When it was made, when it stops being confirmable, and when it ended (set exactly when it is not pending) | A proposal is refused after it expires. `created_at` and `ended_at` are the database's clock, never the caller's: a trigger stamps `created_at` on insert and `ended_at` on the move out of pending. A check holds `expires_at` to at most 15 minutes after `created_at`, and a proposal cannot be executed once it has expired. |
| `outcome` | `{"requestId"}` when executed; `{"code", "text"}` when failed (the engine's or the service's code and its fixed sentence, plus `dates` for an overlap: the days that clash); `{"reason"}` when canceled (`dismissed`, `replaced`, or `turn-incomplete`); null when expired or pending | What happened. Never a note. The next turn's context line is made from the code or reason, never from the text. |

**What the seed writes.** Every sandbox is seeded with time-off data, the same in each (apart from
IDs), all fictional. Each person gets working weekdays (Denver Monday to Friday; the stores rotate
through four five-day patterns, with the managers and the personas on fixed ones; the Austin night
crew works Sunday to Thursday), and one opening balance as of January 1 of the anchor year, or the
hire date if later (0 for a hire since January 1). It also writes a few approved PTO requests and
the odd recorded sick day per person in the past, all counted by the engine and made through the
page (`created_via` `ui`, no proposal). Two requests are fixed: Leo's approved PTO from Wednesday to
Friday of the week before the anchor's week, and one pending request from Zara Bautista in Marcus's
queue, about three weeks after the anchor. It is the only pending request. No seeded request is a
denial, so none has a `decision_note`, and no proposal is seeded.

**Who sees them.** Requests and openings are visible to everyone in the sandbox at the database
level, and the policy layer limits each read. A proposal is visible only to the person it was made
for, HR included. The audit event for a confirmed proposal names it in `audit_events.proposal_id`.

**How long.** All three are deleted with the sandbox, 24 hours after it is created. The API can
add rows. It can change only a request's status, decision columns, and `canceled_at`, and a
proposal's status, `ended_at`, and `outcome`, and never delete one.

### The handbook: `handbook_versions`, `handbook_sections`, `handbook_chunks`

The fictional Juniper Row employee handbook, loaded from the `handbook/` folder by
`scripts/ingest_handbook.py`. These three tables are global: they have no `tenant_id` and sit
outside row-level security. They hold company-public policy text and its search data, with no
personal data and no sandbox data.

| Table | Holds | Why |
|---|---|---|
| `handbook_versions` | One row per loaded edition: its label (`2026.10.1`), a content hash, the embedding model and size, the "Handbook updated" date, its title, its chapter and addendum names (`group_names`), and when it was published | A sandbox is pinned to one version, so its answers never change under it; the names label a hit's group ("Time off", "California addendum"). |
| `handbook_sections` | One row per section per version: its key (`4.3`, `CA-4.3`), title, who it applies to (states, employment types, locations), its source citations, and its structured text | What the handbook screens show, and what a citation points to. |
| `handbook_chunks` | The runs of passages that retrieval searches: their text, a full-text search vector, and a 1024-number embedding | Hybrid (keyword and meaning) search over the handbook. |

The API's login can only read these tables. Ingestion writes them as the database owner. They are
kept while any sandbox uses their version. Phase 8 deletes versions no sandbox uses.

## Outside the database

### Cookies

| Cookie | Holds | Attributes |
|---|---|---|
| `__Host-od_session` | The session token: 32 random bytes | `HttpOnly; Secure; SameSite=Lax; Path=/`, until the sandbox expires |
| `__Host-od_csrf` | The CSRF token: 32 random bytes | `Secure; SameSite=Lax; Path=/`, readable by the page, until the sandbox expires |

Signing out clears both. There are no tracking or analytics cookies.

The web app sets no cookies of its own: these two come from the API, and the page only reads the
CSRF one.

### Browser storage

The web app uses no `localStorage`. It keeps two keys in `sessionStorage`:

| Key | Holds | Why |
|---|---|---|
| `od.expiryBannerDismissed.<tenantExpiresAt>` | `1`, once the visitor has closed the "This sandbox resets in …" banner. The key ends with the sandbox's expiry time, which is not secret. | So the banner stays closed across a reload. A new sandbox has a new expiry, so it gets a new key and shows the banner again. |
| `od.scrollPositions` | How far each page in the tab's history was scrolled, as a list of `[history entry key, pixels]` pairs, newest last, capped at the last 50. The keys are random router-generated strings, not addresses. | So Back or a reload returns to where the visitor was in a long list. |

Only the person at that browser tab can see it. It is gone when the tab closes, and the API never
receives it.

### Security log

Refused requests are written to the JSON application log under the `app.security` logger, not to
the audit table. The events are `security.session_invalid`, `security.origin_rejected`,
`security.csrf_rejected`, and `security.authz_denied`. Each carries:

- the request ID
- a fixed phrase saying why it was refused, such as "unknown or expired session"
- the sandbox and the actor, when they are known
- the target person's ID, for a denied read
- the client's IP address
- the first 8 characters of the session token's hash

A request with no session cookie at all, such as a first visit, isn't a refusal worth recording, so
it logs nothing here (only a DEBUG line with the method and path). A raw token, a cookie value, or a
private detail is never logged. How long logs are kept is set
where they are stored, when Open Door is deployed (Phase 9).

### Voyage (embeddings)

Voyage AI turns text into the vectors that handbook search compares.

- **The handbook's text is sent now,** by `make embed` only, and only for passages that have no
  vector in the committed cache yet. CI and the tests never call Voyage: they read the cache.
- **The assistant's search queries are sent from Phase 4.** When the assistant calls
  `search_handbook`, its query (written by the model from the person's question, up to 500
  characters) is turned into a vector before the database is read. The person's whole question
  isn't sent to Voyage, only that query.
- **The API calls Voyage only when `AI_TRANSPORT=anthropic`.** With the scripted model (`make
  dev`, the browser tests, the proxy check), search is full text only, even with a key in `.env`.
- **Voyage's terms:** it stores API data and may use it for training unless the organization opts
  out, which also gives zero-day retention: "customers can opt-out from Voyage storing and using
  their data for future model training so that there is a zero-day retention of the data."
  **Open Door's Voyage organization has opted out** (the owner, confirmed on 2026-10-17), so
  Voyage keeps none of the text it embeds.

> Source: Voyage AI, "FAQ" (docs.voyageai.com/docs/faq, last updated 2026-08-03), read on
> 2026-10-17.

- **The run-time query cache holds hashes and vectors, never text.**
- **The committed cache files** (`handbook/embeddings/`) hold vectors keyed by hashes of the
  model, the size, and the text, not the text itself.

### Anthropic (the assistant's models)

Anthropic runs the models behind the assistant: Claude Opus 5.5 answers, and Claude Haiku 5.5 is
the safety check that reads each message first. Anthropic is the data processor for the Claude API.

- **What is sent, on each turn:**
  - to the safety check: the person's new message, and up to 1,000 characters of the assistant's
    last answer
  - to the assistant: the system prompt, the tool definitions, the conversation so far, the new
    question, and a short context message (the person's first name, role, location, employment
    type, today's date, and the handbook version; and, when one of the person's confirm cards was
    confirmed, dismissed, replaced, canceled, failed, or expired since the last message, one line
    saying so, made from the card's action, dates, and a directory name only if it is a plain name)
  - the tools' results, which include handbook passages, directory cards, and, when someone asks
    the assistant about themselves, their own private details (personal email, phone, home
    address, and date of birth)
- **What isn't sent:** a crisis message, or a message the safety check couldn't read, never
  reaches the assistant model. A crisis message does go to the safety check, which is what
  recognizes it.
- **Nothing is sent from tests, CI, or `make dev`.** They use the scripted stand-in. Only a
  deliberate `AI_TRANSPORT=anthropic` run or a live eval calls the API.
- **Anthropic's terms, quoted:**
  - Retention: "we automatically delete inputs and outputs on our backend within 30 days of
    receipt or generation". Exceptions: inputs and outputs flagged for a usage policy violation
    are kept "for up to 2 years and trust and safety classification scores for up to 7 years",
    and data may be kept "as required by law".
  - Training: "Retained data is never used for model training without your express permission."
  - Open Door gives no such permission, sends no feedback to Anthropic, and doesn't use zero data
    retention (ZDR), which needs a separate agreement.

> Source: Anthropic, "How long do you store my organization's data?" (privacy.claude.com, last
> updated 2026-07-01), and "API and data retention" (platform.claude.com/docs), both read on
> 2026-10-15.

### The assistant evals (`evals/assistant/`)

The evals run real turns against a fictional sandbox and keep what they need to replay them. No
real person's data is involved: every name, address, phone, email, and birth date comes from the
seed generator.

- **The eval sandbox** is a normal sandbox with a fixed ID, created at the start of a run and
  deleted at the end through the owner login (the cascade removes its people, conversations,
  turns, spend, and audit rows). The run also deletes the `ai_spend_daily` rows it added, and
  only those. A crashed run's sandbox is removed at the next run's start.
- **The recorded fixtures** (`fixtures/*.jsonl.gz`, committed): each model, guard, and judge call
  as a hash of its request and the response the model gave (the answer text, tool calls, usage,
  and citations). The responses can include the fictional asker's own private details, when an
  item asks the assistant about themselves. They change only when a live run re-records them.
- **The query embeddings** (`fixtures/embeddings.jsonl`, committed): vectors keyed by a hash of
  the model, the size, and the text. The text itself isn't stored.
- **The hand grades** (`hand-grades.yaml` and `hand-grades-key.yaml`, committed): 34 recorded
  answers with their questions, cited passages, and a yes or no on each rubric line, and which 4
  answers were planted with flaws.
- **Each run's scoreboard and traces** (`runs/`, git-ignored, on the machine that ran it): the
  scores, costs, and every item's answer, tool results, and guard verdict.
- **Who receives what in a live run:** Anthropic receives the eval questions and the fictional
  sandbox's tool results (Opus 5.5 and Haiku 5.5), and the judge (Sonnet 5.5) receives each
  answer with its question, reference answer, and cited passages. Voyage receives the eval
  questions' and the model's search queries, to embed them. Live runs happen only on the owner's
  machine, with `make eval-live YES=1`; CI replays the fixtures with no network.

- **Logs hold no conversation content.** The API logs IDs, timings, exception types, and stop
  reasons, never a question, an answer, a tool result, or the system prompt. The turn stream adds
  two fixed warnings with no fields: a client that stopped reading a stream, and streams still
  open at shutdown (with a count). A refused question (too long, or a Social Security or card
  number) is a problem response; the text is never logged, stored, or echoed back.
