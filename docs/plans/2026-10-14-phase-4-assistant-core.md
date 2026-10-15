# Phase 4: The Assistant Core (Read-Only) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use
> checkbox (`- [ ]`) syntax for tracking. **Project rule:** never commit, push, or open a PR without
> the owner's explicit OK for that action (see `CLAUDE.md`). Every "Propose the commit" step stops
> and waits.

**Goal:** an employee asks a question and gets a streamed answer that cites the handbook passage
it came from and applies to them. Crisis and sensitive messages are routed to people, the
assistant never writes and never shows what the asker can't see, costs are capped, and two eval
sets prove it.

**Architecture:**
- **The turn** (`app/ai/turn.py`) checks the budget, asks the guard (Haiku 5.5), and then runs a
  streaming tool loop on Opus 5.5 over three read tools. It maps native `search_result` citations
  to handbook passages and stores every message append-only.
- **Transports:** one interface with three implementations, `anthropic`, `scripted` (a rule-based
  stand-in for Claude), and `replay` (recorded live runs). Development, the browser tests, CI, and
  the proxy check never make a paid call.
- **The API** streams the turn as server-sent events over a POST. A closed connection counts as
  Stop.
- **The web app** reads the stream with `fetch` and renders answers as React elements. A citation
  docks the Phase 3 passage panel.

**Tech stack:**
- **API:** FastAPI on Starlette 1.7, SQLAlchemy 2.1 (async), Alembic, and the `anthropic` Python
  SDK 1.x, which brings `httpx2`. pytest with pytest-asyncio, and Postgres 17 with pgvector.
- **Web app:** React 19, React Router 7, TanStack Query 5, Zustand 5, Tailwind 4, shadcn/ui,
  Orval, and `react-markdown`.
- **Tests:** Vitest with Testing Library and MSW; Playwright with axe; nginx in Docker for the
  proxy check.

**Spec:** [`../specs/2026-10-14-phase-4-assistant-core.md`](../specs/2026-10-14-phase-4-assistant-core.md) ·
**ADRs:** [0009](../adr/0009-assistant-turn-and-guard.md), [0010](../adr/0010-scripted-model-and-replay.md),
[0011](../adr/0011-insert-only-budget-ledger.md), and the earlier [0002](../adr/0002-no-agent-framework.md),
[0005](../adr/0005-native-citations.md) · **Roadmap:** [`../ROADMAP.md`](../ROADMAP.md)

---

## How this plan is written

**Outlines, not finished code,** as in Phases 2 and 3. Each task gives:
- the files
- the tests to write first, and what each proves
- the interfaces later tasks depend on
- "Known:" notes on traps found while planning

The traps come from reading the repository, the Claude API documentation, and the libraries'
sources, not from a trial build: there was none (see the owner's "no scratch prebuild" rule). The
implementer writes each test first, watches it fail for the right reason, and then makes it pass.
Problems are solved during the build and recorded under
[Changes made during execution](#changes-made-during-execution).

**The spec is the authority** on behavior: the event shapes, the table columns, the caps, and the
fixed texts' contents. This plan says how to build them in order. Where this plan and the spec
disagree, the spec wins, and the difference is recorded.

---

## Global constraints

Every task's requirements include these.

- **The seven invariants** in `CLAUDE.md`. Above all:
  - every tool takes the actor from the server session, and no tool input names "whose data"
  - the model never writes
  - every policy claim cites the handbook
  - fixed texts are never generated
  - the assistant always says it's an AI
- **Model IDs are pinned in code:** `claude-opus-5-5` (the assistant), `claude-haiku-5-5` (the
  guard), and `claude-sonnet-5-5` (the eval judge). Never with a date suffix.
- **No paid AI call** in tests, CI, or `make dev`. Only `make eval-live` and a deliberate
  `AI_TRANSPORT=anthropic` run call Anthropic, and only `make embed` and live runs call Voyage.
- **The conversation is append-only:** the stored messages, the system prompt, and the tool list
  are never changed for an existing conversation.
- **American English** everywhere. Units in field names (`durationMs`, `amountUsd`), timestamps
  in UTC, and dates in the location's timezone.
- **Theme tokens, never raw hex,** in components. No `dangerouslySetInnerHTML` anywhere (a test
  scans `src/`).
- **`CHANGELOG.md`** in the same edit as the change, and `docs/DATA-INVENTORY.md` in the same
  task as any new table, column, or processor.
- **Implementers merge, never replace,** `tests/integration/conftest.py`, `docs/BACKLOG.md`, and
  `docs/DATA-INVENTORY.md`.

## Review focus

The five inputs most likely to hurt a person that the spec implies but doesn't spell out. Each
has its test in the task named.

1. **A second Send while the first turn's cleanup is still running** (a fast double-click, or two
   tabs). Expect a calm "still answering" message, with the question kept in the composer, never
   an error page. *Tests: Task 29 (the 409 problem), Task 40 (the store keeps the draft).*
2. **A persona switch or sign-out while an answer is streaming.** Expect the stream to be aborted,
   and no text from the old persona to appear for the new one. *Test: Task 40 (`resetIdentity`
   aborts the stream, and late events are dropped).*
3. **The model writes raw HTML, a bare URL, or an external Markdown link.** Expect plain text, no
   clickable link, and no markup. *Test: Task 33 (renderer cases).*
4. **An answer cut off by `max_tokens`.** Expect the text marked incomplete, its citations still
   mapped, and the budget settled. *Test: Task 16 (the loop's stop reasons).*
5. **The network drops mid-answer, and the person reloads.** Expect the partial answer with
   "Stopped", and the conversation free for the next question. *Tests: Task 29 (a disconnect is
   saved as stopped), Task 42 (reload in the browser).*

---

## Decisions made while planning

**Six stages, each a pull request into `dev`.**

| Stage | Branch | Tasks | Code, not counting tests (est.) |
|---|---|---|---|
| 1 The conversation store, budgets, and transports | `feat/phase-4-store` | 1–9 | about 1,300 |
| 2 The loop, the guard, and the tools | `feat/phase-4-loop` | 10–17 | about 1,200, plus prompts |
| 3 The evals | `feat/phase-4-evals` | 18–25 | about 1,000, plus datasets and fixtures |
| 4 The stream and the routes | `feat/phase-4-stream` | 26–32 | about 900, plus the generated client |
| 5 The conversation components | `feat/phase-4-conversation-components` | 33–38 | about 1,200 |
| 6 The conversation page, and closing Phase 4 | `feat/phase-4-conversation-page` | 39–44 | about 1,000 |

**How each stage runs** (the way of working approved in Phases 1–3):

- **Batches.** Each stage runs in the batches named under it. After each batch I stop with a short
  report and wait for "continue".
- **One Sonnet implementer per batch.** It gets:
  - this plan's line range for its tasks
  - the spec, and the design notes where they apply
  - the deviations the repository forces

  It writes each test first and reproduces the failure.
- **Reviews:**
  - Stage 1's batch A (the schema, grants, and row-level security) and Stage 4's batch B (the
    routes and the stream) each get a Sonnet compliance reviewer and an **Opus 5.5 security
    reviewer**, run in parallel. The Opus reviewer is re-briefed through SendMessage, so it keeps
    its context.
  - Every other batch gets one combined Sonnet review.
- **Fixes** are written test first by a Sonnet fixer, and each new test is mutation-proved.
- **I do each stage's close myself:**
  - the changelog, the roadmap row and its "Next" note, and this plan's "Changes made during
    execution"
  - `make db && make check`
  - `/code-review medium` on the whole branch, with `git add -N` on new files first so the review
    sees them. If the review finds something, it runs again after the fix.
  - Then I draft the commit and PR and wait for the owner's OK on each action.
- **The phase ends** with `/code-review high` on the phase's application code, and one **Fable 5.1
  security reviewer** briefed with the spec's [Security](../specs/2026-10-14-phase-4-assistant-core.md#security)
  seams.

**Effort for each session:** `medium` for every stage, the closes, and the phase review. Switch to
`high` only for a stubborn bug, then back.

**The live-eval rule in this phase:**
- Stage 2 writes the first prompts, and its PR says that their live evidence is Stage 3's first
  smoke run, which must pass before Stage 3 merges.
- From Stage 3 on, any change to a prompt, a tool description, or the guard has a smoke run
  before its PR, and the scoreboard change goes in the PR description.
- The full run happens in Stage 6.

## Prerequisites (owner)

- **Before Stage 3's Task 24** (the first live run):
  1. an Anthropic API key in `apps/api/.env` as `ANTHROPIC_API_KEY`
  2. a $25 monthly spend limit in the Claude Console (Settings, Billing, "Spend limits")
  3. Voyage is already set up from Phase 3
- **In Stage 2's PR:** the owner edits and approves the crisis text. In Stage 3, the owner grades
  the hand-grade file (about 45–60 minutes).
- **Before Stage 5:** the conversation view (screen 07) is designed in Claude Design and synced
  into `docs/design/screens/07-conversation/` in its own docs PR. The spec's list is "What the
  design must cover". Stages 1–4 don't wait.
- **Docker Desktop is running,** and `make setup` and `make db` have run.
- **Each stage branches off `dev` after the previous stage's PR merges.**
- **Record the commit `dev` is at after this planning PR merges,** before Stage 1 branches. Task
  44's phase review diffs against it.

## File map

```
open-door/
├── evals/
│   ├── README.md                          Stage 3  the assistant evals, and what replay doesn't test
│   └── assistant/                         Stage 3  redteam.yaml, qa.yaml, smoke.yaml, judge.md,
│                                                   hand-grades.yaml, personal-data-cases.json,
│                                                   fixtures/, run.py
├── scripts/proxy-check/                   Stage 4  compose file, nginx.conf, check.py
├── Makefile                               Stages 3, 4  eval-offline, eval-live, proxy-check
├── .github/workflows/ci.yml               Stages 3, 4  offline evals in the API job; the proxy check in E2E
├── CLAUDE.md                              Stages 3, 4  the live-eval rule, commands, transports
├── docs/
│   ├── DATA-INVENTORY.md                  Stages 1, 2  six tables; Anthropic as a processor
│   ├── AI-GOVERNANCE.md                   Stage 4  new
│   └── BACKLOG.md                         Stages 2, 4, 6  closed items out
├── apps/api/
│   ├── pyproject.toml                     Stage 1  anthropic; import-linter
│   ├── .env.example                       Stage 1  the new settings
│   ├── migrations/versions/0008_assistant.py   Stage 1
│   └── app/
│       ├── core/config.py                 Stage 1  ANTHROPIC_API_KEY, AI_* settings
│       ├── db/models.py                   Stage 1  the six tables
│       ├── main.py                        Stage 4  transport and embedder in app state
│       ├── modules/audit/service.py       Stage 2  new AuditAction values
│       ├── ai/                            Stages 1–4
│       │   ├── pricing.py, budget.py, conversations.py              Stage 1
│       │   ├── transport.py, anthropic_transport.py, scripted.py   Stage 1
│       │   ├── scripted_scenarios.json                              Stage 1
│       │   ├── prompts/ (assistant.md, guard.md, versions.py)       Stage 2
│       │   ├── context.py, citations.py, guard.py, fixed_texts.py   Stage 2
│       │   ├── tools/ (registry.py, handbook.py, people.py)         Stage 2
│       │   ├── turn.py                                              Stage 2
│       │   ├── replay.py                                            Stage 3
│       │   └── personal_data.py                                     Stage 4
│       └── modules/assistant/             Stage 4  routes.py, schemas.py, sse.py
└── apps/web/src/
    ├── components/assistant/              Stage 5  messages, markers, chips, trace, feedback,
    │                                               escalation, banners, composer states
    ├── components/assistant/answer.tsx    Stage 5  the Markdown subset renderer
    ├── app/gallery/sections/              Stage 5  the conversation states
    ├── lib/stream-turn.ts, lib/sse.ts     Stage 6
    ├── lib/personal-data.ts               Stage 6
    └── features/chat/, features/home/     Stage 6  the store, the hooks, the page; the fake deleted
```

---

# Stage 1: The conversation store, budgets, and transports

**Branch:** `feat/phase-4-store`, off `dev` after the planning PR merges. Record the base commit
first.

**Ends with:**
- the `anthropic` dependency and the settings
- migration 0008 and its grants
- the conversation repository and the budget ledger
- the transport interface, with the Anthropic and scripted transports

Nothing is wired to HTTP yet, and `make check` passes.

**Batches:**
- **A** (Tasks 1–2, the settings and the schema): the Sonnet compliance reviewer and the Opus
  security reviewer.
- **B** (Tasks 3–5): pricing, budgets, and conversations.
- **C** (Tasks 6–8): the transports.
- **D** (Task 9): the close.

### Task 1: Dependencies and settings

**Files:** `apps/api/pyproject.toml`, `uv.lock`, `app/core/config.py`, `apps/api/.env.example`,
`tests/test_config.py`.

**Interface:**

```python
# app/core/config.py (additions)
anthropic_api_key: SecretStr | None          # empty string counts as None, like voyage_api_key
ai_transport: Literal["anthropic", "scripted", "replay"] = "scripted"
ai_sandbox_budget_usd: Decimal = Decimal("1.00")
ai_daily_budget_usd: Decimal = Decimal("3.00")
ai_heartbeat_seconds: int = 15                # 0 turns the heartbeat off (the proxy check's control run)
```

- [ ] **Tests first:**
  - an empty `ANTHROPIC_API_KEY` is `None`
  - `APP_ENV=production` with `AI_TRANSPORT=scripted` or `replay` refuses to start, with a clear
    message
  - `AI_TRANSPORT=anthropic` without a key refuses to start
  - the defaults match the spec
- [ ] Add `anthropic` (the latest 1.x, which needs `httpx2`; 1.13.0 on 2026-10-14). Add `anthropic`
      to import-linter's forbidden list for `app.domain` and `app.policy`, as already there. Allow
      it in `app.ai` only.
- [ ] **Known:**
  - The repo already has both `httpx` (0.28, used by the Voyage client) and `httpx2` (dev, used
    by the tests). They're separate modules. The Anthropic SDK 1.x uses `httpx2`, so its test
    doubles use `httpx2.MockTransport`. Read the SDK's 1.x notes before writing the client
    construction: the claude-api skill's `python/claude-api/sdk-upgrade.md`, or the SDK's
    CHANGELOG.
  - `CLAUDE.md`'s gotcha: an agent shell may export `ANTHROPIC_API_KEY=""`, which shadows `.env`.
    The empty-means-`None` validator fixes the setting; `make dev` and the e2e config already
    run uvicorn under `env -u ANTHROPIC_API_KEY`.

### Task 2: Migration 0008, the models, and the data inventory

**Files:** `migrations/versions/0008_assistant.py`, `app/db/models.py`,
`tests/integration/test_grants.py`, `tests/integration/test_row_level_security.py`,
`tests/integration/test_isolation.py`, a new `tests/integration/test_assistant_tables.py`, and
`docs/DATA-INVENTORY.md`.

- [ ] **Tests first:**
  - the exact-grants test lists the spec's grants:
    - `SELECT` and `INSERT` on `ai_conversations`, `ai_messages`, `ai_feedback`, `ai_spend`, and
      `ai_spend_daily`
    - `SELECT`, `INSERT`, and `UPDATE` on `ai_turns`
    - nothing for `od_cleanup`
  - row-level security coverage finds the five new tenant tables enabled and forced, and
    `ai_spend_daily` has no `tenant_id`
  - **the per-person rule:** in one sandbox, Marcus can't see Priya's conversation, messages,
    turns, or feedback, and neither can Dana (HR). The isolation test's `TENANT_TABLES` gains the
    five tables.
  - `ai_messages`: `UPDATE` and `DELETE` fail with a permission error, as `od_app_login`
  - the partial unique index allows one `running` turn per conversation
  - deleting a tenant (as the cleanup login) removes its rows from all five tables
- [ ] Write the migration in the style of 0003 and 0004:
  - a module docstring that explains the design
  - a `GRANTS` tuple
  - `ENABLE` and `FORCE ROW LEVEL SECURITY`
  - the `tenant_isolation` policy
  - a `RESTRICTIVE` policy, `own_rows`, `FOR ALL TO od_app USING (person_id =
    app.current_person_id()) WITH CHECK (same)`
  - `ON DELETE CASCADE` from `tenants` and from parent rows
- [ ] Add the six tables to `DATA-INVENTORY.md`: what each holds, why, who sees it (only the
      person), and how long it's kept (the sandbox's 24 hours; `ai_spend_daily`, 30 days, from
      Phase 8). Say plainly that guard-flagged content is unencrypted until Phase 6.
- [ ] **Known:**
  - The row-level-security test requires **every unique index on a tenant table to start with
    `tenant_id`**. So the unique keys are `(tenant_id, conversation_id, position)` on
    `ai_messages`, `(tenant_id, turn_id)` on `ai_feedback`, and the partial unique index is
    `(tenant_id, conversation_id) WHERE status = 'running'`.
  - The same test allows only the tenant rule as a **permissive** policy, so the per-person rule
    must be `AS RESTRICTIVE`, like `private_self_or_hr`.
  - `app.current_person_id()` is set by the transaction hook. A tool or stream write that opens
    its own transaction must use `tenant_session(engine, TenantContext(tenant_id, person_id))`,
    or the restrictive rule hides every row.
  - `ai_spend_daily` has no tenant, so it sits outside row-level security, like the handbook
    tables. It holds no personal data: day, amount, and timestamp.
  - `alembic check` compares the models with the migration. Declare the partial index in the
    model too (`postgresql_where`).

### Task 3: Prices and costs

**Files:** `app/ai/pricing.py`, `tests/test_pricing.py`.

**Interface:**

```python
@dataclass(frozen=True) class Price: input, cache_write_5m, cache_read, output   # Decimal $/MTok
PRICES: Mapping[str, Price]                       # the spec's table; source line in the docstring
def cost_usd(model: str, usage: Usage) -> Decimal                  # one model's usage
def turn_call_cost(iterations: Sequence[IterationUsage]) -> Decimal  # each attempt at its own model's price
def reservation_usd(model: str, *, estimated_input_tokens: int, max_tokens: int) -> Decimal
def estimate_input_tokens(previous_input_tokens: int, new_text: str) -> int   # previous + ceil(len/2)
```

- [ ] **Tests first:**
  - hand-worked costs, for example 10,000 input, 2,000 cache-read, and 500 output tokens on Opus
    5.5 is $0.0504
  - a fallback's iterations are priced per model
  - an unknown model raises
  - the reservation is never below the actual cost for the scripted usage figures
- [ ] **Known:**
  - Haiku 5.5 doubles in price above 100,000 prompt tokens. The guard's prompts are tiny, so
    `cost_usd` raises if a Haiku prompt exceeds 100,000, rather than silently using the low rate.
  - Money is `Decimal`, never `float`.

### Task 4: The budget ledger

**Files:** `app/ai/budget.py`, `tests/integration/test_budget.py`.

**Interface:**

```python
class BudgetExceeded(Exception): scope: Literal["sandbox", "daily"]
async def reserve(engine, ctx: TenantContext, *, turn_id: UUID, amount: Decimal, caps: Caps) -> Reservation
async def settle(engine, ctx, reservation: Reservation, *, actual: Decimal) -> None
async def budget_state(db, caps) -> BudgetState   # sandbox_remaining_usd, daily_reached
```

- [ ] **Tests first:**
  - **concurrency:** with $0.10 left and two concurrent reservations of $0.08 each (two engines,
    `asyncio.gather`), exactly one succeeds
  - after settling, the sums equal the actual cost
  - the daily cap counts every sandbox
  - a new UTC day starts at zero
  - `budget_state` reports both
- [ ] Each `reserve` is one transaction:
  - `pg_advisory_xact_lock` on the tenant key, then the day key, always in that order
  - sum both ledgers
  - insert `reserve` rows into both, or raise `BudgetExceeded`
  - `settle` inserts `settle` rows of `actual − reserved`
- [ ] **Known:**
  - Use the two-integer form of `pg_advisory_xact_lock`, with a fixed namespace for budgets and a
    hash of the tenant ID, and a second namespace for the day. A transaction-scoped lock is
    released at commit, so it stays correct behind PgBouncer or RDS Proxy (the spec's AWS
    section).
  - A session-level advisory lock would leak across pooled connections. Never use one.

### Task 5: The conversation repository

**Files:** `app/ai/conversations.py`, `tests/integration/test_conversations.py`.

**Interface:**

```python
async def create_conversation(db, actor, pins: Pins) -> Conversation
async def current_conversation(db, actor) -> Conversation | None
async def model_history(db, conversation_id) -> list[MessageParam]    # exactly as stored, in order
async def append_messages(db, conversation_id, turn_id, messages: Sequence[MessageParam]) -> None
async def start_turn(db, conversation, question: str) -> Turn         # raises TurnRunning
async def finish_turn(db, turn_id, outcome: TurnOutcome) -> None       # the only UPDATE
async def recover_abandoned(db, conversation_id, *, older_than=timedelta(minutes=10)) -> None
async def search_sources(db, conversation_id) -> list[SourceEntry]     # every search result sent, in order
```

- [ ] **Tests first:**
  - `model_history` returns byte-identical JSON to what was appended, including `thinking`
    blocks
  - positions are consecutive and unique
  - `start_turn` raises `TurnRunning` on a second running turn
  - a 10-minute-old `running` turn is marked `failed` and the next starts
  - `search_sources` returns entries in the order their `search_result` blocks were stored,
    across turns
  - another person's conversation is invisible (`current_conversation` returns `None`)
- [ ] **Known:**
  - Store `content` as the API's own JSON (`model_dump(mode="json", exclude_none=True)` on the SDK
    types). Read it back without normalizing: key order and escaping must survive, or a thinking
    block fails the prefix check.
  - `SourceEntry` (section ID, passage IDs, title, group name, audience label, last updated, deep
    link) comes from the turn's stored tool-call record, not from re-parsing text.

### Task 6: The transport interface

**Files:** `app/ai/transport.py`, `tests/test_transport_types.py`.

**Interface:**

```python
@dataclass(frozen=True) class ModelRequest:  model, system, tools, messages, effort, max_tokens, betas, fallbacks
# Normalized stream events, the same from every transport:
StatusNote(text) | TextDelta(text) | TextBlockEnd(citations: list[SearchResultCitation])
| ToolCall(id, name, input: dict) | Finished(message: dict, stop_reason, usage, iterations, served_by)
class Transport(Protocol):
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...
    async def classify(self, request: GuardRequest) -> GuardResult: ...   # the guard's one call
```

- [ ] **Tests first:** the event types are frozen, `Finished.message` is the full assistant
      message as the API returned it (for storage), and `ModelRequest.to_api_kwargs()` is stable,
      with sorted keys where the replay fingerprint needs them.

### Task 7: The Anthropic transport

**Files:** `app/ai/anthropic_transport.py`, `tests/test_anthropic_transport.py`, and
`tests/fixtures/anthropic/*.sse` (hand-written SSE bodies).

- [ ] **Tests first**, through an `httpx2.MockTransport` that serves the fixture bodies:
  - text deltas map to `TextDelta`
  - a `thinking` block from `display: "updates"` maps to `StatusNote`
  - a `citations_delta` is collected and emitted with `TextBlockEnd` when its block stops
  - a `tool_use` block with streamed `partial_json` becomes one `ToolCall` with parsed input
  - `message_delta`'s `stop_reason` and usage reach `Finished`, with `usage.iterations` and the
    served-by model
  - a `fallback` content block is skipped as an audit marker
  - a 429, a 5xx, a refusal, and the Console spend-limit 400 each map to a typed error
  - the request carries the betas and `fallbacks: "default"`
- [ ] Use the SDK's beta streaming call (`client.beta.messages.stream`) with:
  - `betas=["server-side-fallback-2026-07-01", "thinking-display-updates-2026-08-18"]`
  - `fallbacks="default"`
  - `thinking={"type": "adaptive", "display": "updates"}`
  - `output_config={"effort": …}`
  - `eager_input_streaming: true` on each tool, and validate each tool input before use (Task 16)
- [ ] `classify` uses `messages.create` on `claude-haiku-5-5` with
      `output_config={"effort": "low", "format": {json_schema}}`, `max_tokens=1024`, no sampling
      parameters, and a 4-second timeout.
- [ ] **Known:**
  - **Check `stop_reason` before reading content.** A refusal can arrive before any output (empty
    content) or partway through. A mid-stream refusal's partial text is discarded.
  - **Forced `tool_choice` returns a 400 on Opus 5.5.** Use `auto`.
  - **Opus 5.5 rejects `thinking.type: "disabled"` and `budget_tokens`.** Haiku 5.5 rejects
    `temperature`, `top_p`, and `top_k` at anything but their defaults, so send none.
  - **The SDK's tolerant parser can return truncated tool input** with `eager_input_streaming`.
    Validate against the schema, and treat a failure like invalid JSON (claude-api skill,
    "Eager input streaming").
  - **Read the beta and parameter names from the claude-api skill** (`python/claude-api/
    streaming.md` and `shared/model-migration.md`) when writing this. Don't guess them.
  - **The spend limit you set yourself** returns 400 `invalid_request_error`, with a message
    beginning "You have reached your specified API usage limits". Match on that prefix.

### Task 8: The scripted model and the fake guard

**Files:** `app/ai/scripted.py`, `app/ai/scripted_scenarios.json`, `tests/test_scripted.py`.

- [ ] **Tests first:**
  - **A plain question:**
    - the first call emits one `ToolCall` to `search_handbook` with the question as its query
    - the second call (given the tool result) emits two sentences, ending each text block with a
      citation of search result `n` block 0, where `n` is the conversation's index of the first
      result returned this turn
    - `Finished` has fixed usage
  - **Every scenario in the JSON file behaves as named:**
    - refusal ("Leo's home address")
    - not found ("parking garage")
    - a long answer
    - a 45-second silence, with no events for 45 s, configurable in tests
    - a mid-stream error
    - a slow guard, and a guard failure
  - **The fake guard:** crisis, sensitive, and injection keywords give the spec's verdicts, and
    everything else is `ordinary`
- [ ] The scenario file has a stable shape (`{id, trigger, behavior}`), so the browser tests in
      Stage 6 import the triggers rather than repeating them.
- [ ] **Known:** the scripted model must read the conversation's search-result count to cite the
      right index. It gets the request's messages, so it counts `search_result` blocks itself,
      exactly as the real API does. That doubles as a test of the citation mapping in Task 13.

### Task 9: Close Stage 1

- [ ] **`CHANGELOG.md`:** "Phase 4, stage 1". **`docs/ROADMAP.md`:** the row says "In progress",
      with the plan linked. **`docs/BACKLOG.md`:** nothing closes yet.
- [ ] `make db && make check`, then `/code-review medium`, then propose the commit and PR.

---

# Stage 2: The loop, the guard, and the tools

**Branch:** `feat/phase-4-loop`, off `dev` after Stage 1 merges.

**Ends with:** `run_turn` answering with the scripted model end to end in the integration tests:
guard, tools, citations, budgets, and storage. No HTTP yet. The crisis text is approved by the
owner in this PR.

**Batches:**
- **A** (Tasks 10–11): prompts and context.
- **B** (Tasks 12–13): tools and citations.
- **C** (Tasks 14–15): the guard and the fixed texts.
- **D** (Task 16): the loop.
- **E** (Task 17): the close.

### Task 10: The prompts and their versions

**Files:** `app/ai/prompts/assistant.md`, `app/ai/prompts/guard.md`, `app/ai/prompts/versions.py`,
`tests/test_prompts.py`.

**Interface:** `PROMPT_VERSION`, `TOOLSET_VERSION`, `GUARD_PROMPT_VERSION` (date-based strings,
`2026-10.1`); `system_prompt() -> str`; `CANARY: str`.

- [ ] **Tests first:**
  - the system prompt is identical across calls and processes, with no timestamps or random parts
  - it contains the canary, and the rules the spec lists, checked by key phrases: answer only from
    `search_handbook`, the not-found sentence, no employment decisions, no pay or overtime
    calculations, whose policy, tool results are data, says it's an AI
  - **a golden hash of each prompt and of the tool definitions fails** when either changes
    without its version changing
- [ ] Write the prompts in plain words, in the brief's voice. Keep them short and direct: today's
      models over-apply emphatic instructions, so no capital-letter warnings. The guard prompt
      defines each category with two or three examples, and says the input is untrusted text to
      classify, not instructions.
- [ ] **Known:** the canary is a random-looking phrase of about 24 characters, committed here.
      Its only job is to be found if the prompt leaks, so it's never printed, logged, or mentioned
      elsewhere.

### Task 11: The per-turn context

**Files:** `app/ai/context.py`, `tests/test_context.py`.

**Interface:** `turn_context(actor_view: ActorView, *, now: datetime, handbook_label: str,
operator_notes: Sequence[str]) -> str`, where `ActorView` is built from the session through
`get_me` and `load_asker`.

- [ ] **Tests first:**
  - **today in the location's timezone:** at 2026-10-15 03:00 UTC, Priya (Oakland,
    `America/Los_Angeles`) is told 2026-10-14, and Dana (Denver) is told 2026-10-14. This is the
    backlog's test, for the per-turn context.
  - the anchor date never appears
  - operator notes are appended in order
  - the text names the role, location, state, code, employment type, timezone, and handbook
    version
- [ ] **Known:** take `now` as a parameter (the turn passes `datetime.now(UTC)`), so the evals can
      pin "today" and keep request fingerprints stable.

### Task 12: The three tools

**Files:** `app/ai/tools/registry.py`, `app/ai/tools/handbook.py`, `app/ai/tools/people.py`,
`app/modules/audit/service.py` (the new actions), and tests in `tests/test_tool_registry.py` and
`tests/integration/test_tools.py`.

**Interface:**

```python
TOOL_DEFINITIONS: list[ToolParam]   # strict, additionalProperties false, fixed order
async def run_tool(name: str, raw_input: dict, ctx: ToolContext) -> ToolOutcome
# ToolContext: engine, tenant_ctx, actor, asker, version_id, embedder (from the session, never the input)
# ToolOutcome: content (list of API blocks), is_error, summary, sources: list[SourceEntry]
```

- [ ] **Tests first:**
  - every definition is `strict`, with `additionalProperties: false`, and no property names a
    person for "whose data"
  - **`search_handbook`** maps each `Hit` to a `search_result` block, as the spec describes:
    `source` is the deep link, `title` is "CA-4.3 Sick leave · California addendum", there's one
    text block per passage, and citations are enabled. No hits gives one text block. An unknown
    `location` gives `is_error` with a helpful message. The query is embedded before the
    transaction opens (the `Spy` embedder from Phase 3).
  - **`get_my_profile`** returns the asker's own private details and writes `person_private.read`
    with `via: "assistant"`. It never takes an input.
  - **`find_people`:**
    - returns directory fields only, with no private field name anywhere in the output
    - caps at 10
    - `my_team` gives Marcus his reports and gives Priya none
    - each card passes `can(actor, DIRECTORY_READ, …)`
  - an invalid input is rejected before the tool runs, as `is_error`
- [ ] Add `escalation.offered` to `AuditAction`.
- [ ] **Known:**
  - Reuse, don't copy:
    - `embed_query`, `search_handbook`, `pinned_version_id`, `clean_query`, and `load_asker` from
      `modules/handbook`
    - `get_me`, `get_private_details`, and `list_directory` from `modules/people`
    - `record_event`, which already refuses private field names as keys
  - Each tool opens its own short `tenant_session`. The loop holds no transaction while it waits
    on the model.
  - A tool error's text helps the model recover ("Unknown location 'sf'. Use one of: den, oak,
    aus, atl.") and never contains a stack trace or SQL.

### Task 13: Citations

**Files:** `app/ai/citations.py`, `tests/test_citations.py`.

**Interface:** `class CitationMapper(sources: list[SourceEntry])`, with
`.add(entries)`, `.on_block_end(answer_length: int, citations) -> list[CitationEvent]`;
`CitationEvent` is the spec's payload.

- [ ] **Tests first:**
  - result index 3 means the fourth `search_result` across the whole conversation, including
    earlier turns
  - `start_block_index` 1 to `end_block_index` 3 gives two events, for passages 2 and 3
  - a passage cited twice keeps its marker number
  - markers number from 1 within each answer
  - `offset` is the answer's length at the block's end
  - a citation whose `source` doesn't match the entry is dropped and logged, with no text
- [ ] **Known:** citations arrive on text blocks, and Opus may split one sentence across several
      text blocks. The marker belongs at the end of the cited block, which is why the event is
      emitted at block end, not at the delta.

### Task 14: The guard

**Files:** `app/ai/guard.py`, `tests/test_guard.py`.

**Interface:** `async def screen(transport, message: str, previous_answer: str | None) ->
GuardOutcome`, where `GuardOutcome` is the verdict plus `route: "answer" | "crisis" |
"unavailable"` and its `operator_notes`.

- [ ] **Tests first:**
  - each verdict routes as the spec says
  - a timeout (more than 4 s), an exception, a refusal, and output that fails the schema each give
    `unavailable`
  - the previous answer is truncated to 1,000 characters
  - both inputs are wrapped in labeled tags
  - the guard's cost is reserved and settled like any call
- [ ] **Known:**
  - Haiku 5.5 thinks by default. Effort `low` keeps it short, and `max_tokens` must cover the
    thinking plus the JSON.
  - Refusals on Haiku 5.5 have no server-side fallback, which is why a refusal means
    `unavailable` (ADR 0009).

### Task 15: The fixed texts

**Files:** `app/ai/fixed_texts.py`, `tests/test_fixed_texts.py`.

- [ ] **Tests first:**
  - every fixed text is a constant
  - the crisis text contains 988 ("call or text 988"), `chat.988lifeline.org`, 911, and the EAP
    number `1-800-555-0137`
  - **the approval check:** `sha256(CRISIS_TEXT) == CRISIS_TEXT_SHA256`, and
    `CRISIS_TEXT_APPROVED_ON` is a real date
  - `hr_contact(db)` returns the HR team's names and work emails from the directory, which is
    Dana in the seed
- [ ] **Draft the crisis text** from the spec's required contents and the 988 source line, in the
      brief's voice. Leave `CRISIS_TEXT_APPROVED_ON` unset and the approval test failing, with a
      message asking the owner to approve. **The owner edits and approves it in this stage's PR**,
      then the date and hash are set. Re-check 988lifeline.org on the day it's approved, and
      update the source line's date.
- [ ] The sensitive stub, "can't answer right now", the refusal message, and the budget messages
      are fixed text too, in the same file.

### Task 16: The loop

**Files:** `app/ai/turn.py`, `tests/integration/test_turn.py`.

**Interface:**

```python
async def run_turn(deps: TurnDeps, *, conversation: Conversation, question: str,
                   now: datetime) -> AsyncIterator[TurnEvent]
# TurnDeps: engine, transport, embedder, actor, tenant_ctx, caps (heartbeats are the route's job)
# TurnEvent: the spec's events, as typed objects; the route serializes them
```

- [ ] **Tests first** (integration, scripted transport, seeded sandbox):
  - **Priya** asks about sick leave and gets CA-4.3 cited. **Mateo** asks the same and gets 4.3,
    never CA-4.3 or CO-4.3.
  - **The stored history:** user, system context, assistant with `tool_use`, user with
    `tool_result`, then assistant. Positions are consecutive.
  - **A second turn's request starts with the first turn's messages byte for byte** (the
    append-only proof).
  - **Crisis:** an `escalation` event, no main-model call, nothing in `ai_messages`, and the turn
    status `crisis`.
  - **Sensitive:** an answer, then `escalation`, and an `escalation.offered` audit event.
  - **The guard down:** `unavailable`, and no main-model call.
  - **A suspected injection:** the turn runs, the warning note is in the context message, and the
    flag is on the turn.
  - **Stop reasons:** `refusal` gives an `error` with code `refusal`, partial text discarded, and
    the budget settled. `max_tokens` keeps the text, marks it incomplete, and maps its citations.
    `tool_use` runs the tools concurrently and returns all results in one user message.
  - **Limits:** the ninth model call isn't made (`too-many-calls`). A reservation that doesn't fit
    ends the turn with `budget-sandbox` or `budget-daily`.
  - **Cancellation:** cancel the consuming task partway through the answer. The turn ends
    `stopped`, with its partial text saved and the budget settled. A following turn can start, and
    its history contains the stopped turn's question only.
  - **The trace:** `ai_turns` has the guard verdict, tools, sections, served-by model, tokens,
    cost, time to first event, and total time.
- [ ] **Known:**
  - **Cleanup on cancellation:** wrap the end-of-turn write in `anyio.CancelScope(shield=True)`
    (or `asyncio.shield`) with its own fresh `tenant_session`. Starlette cancels the stream's task
    group on disconnect, so an unshielded `finally` that awaits the database is itself canceled.
  - **Messages are appended only when complete:** the assistant message that asked for tools, and
    the user message with their results, are inserted together after the tools return. A stop in
    between stores neither.
  - **The model history for the next turn** skips crisis and guard-failure turns entirely (they
    never reach `ai_messages`). Two user messages in a row are valid.
  - **Count `search_result` blocks** for the mapper from the stored history plus this turn's
    tool results, never from memory alone, so a restarted task maps the same way.

### Task 17: Close Stage 2

- [ ] **`docs/DATA-INVENTORY.md`:** Anthropic as a processor. Questions, the per-turn context, and
      tool results, including the asker's own private details, are sent to Anthropic's API.
      Verify and quote Anthropic's current API data retention and training terms from its
      official pages, with a source line and date. Voyage's line about assistant questions is made
      current. Logs carry no conversation content.
- [ ] **`docs/BACKLOG.md`:**
  - delete "Map search hits to `search_result` blocks…"
  - trim "Never treat the anchor date as today" to its time-off-engine half
- [ ] **`CHANGELOG.md`:** "Phase 4, stage 2".
- [ ] `make check`, then `/code-review medium`, then propose the commit and PR. The PR description
      says the first live run is Stage 3's, and asks the owner to edit and approve the crisis
      text.

---

# Stage 3: The evals

**Branch:** `feat/phase-4-evals`, off `dev` after Stage 2 merges.

**Ends with:**
- both datasets and offline replay in CI
- `make eval-live` with its caps
- the first smoke run, and the effort comparison
- the judge validated against the owner's grades

The scoreboard is in the PR description.

**Batches:**
- **A** (Tasks 18–19): replay and the harness.
- **B** (Tasks 20–21): the two datasets and their graders. The owner reviews the questions in the
  PR.
- **C** (Tasks 22–23): the judge and the runner.
- **D** (Task 24): the live runs and the hand grades, with the owner.
- **E** (Task 25): the close.

### Task 18: The replay transport and the recorder

**Files:** `app/ai/replay.py`, `tests/test_replay.py`.

- [ ] **Tests first:**
  - the fingerprint is the SHA-256 of `ModelRequest.to_api_kwargs()` serialized with sorted keys
  - two requests that differ only in dict order share a fingerprint
  - a recorded run replays the same events
  - a miss raises with the eval item's ID and "re-record with `make eval-live`"
  - the recorder writes one JSON Lines file per dataset, compressed with gzip
- [ ] **Known:** guard calls are recorded too, keyed the same way. Judge calls are recorded
      separately, so a grader-only change replays without the model.

### Task 19: The eval harness

**Files:** `evals/assistant/run.py` (the harness part), `tests/test_assistant_eval_harness.py`.

- [ ] **Tests first:**
  - **the fixed sandbox:** a fixed tenant UUID, anchor date, and "today" give identical seeded
    IDs and identical request fingerprints across two runs
  - each item runs `run_turn` and collects:
    - the answer text, and the citations with their sections
    - every tool result's text, and the guard verdict
    - whether the main model was called
  - **query embeddings:**
    - questions and model-written search queries go through a `CachedEmbedder`, backed by
      `evals/assistant/fixtures/embeddings.jsonl`
    - live runs fill misses from Voyage
    - replay fails on a miss
- [ ] **Known:**
  - The model writes its own `search_handbook` queries, so their text isn't known until a live
    run. That's why live runs record the embeddings beside the fixtures.
  - Reuse Phase 3's eval pattern: the scratch tenant inside a rolled-back transaction, from
    `evals/retrieval/run.py`.

### Task 20: The red-team set and its graders

**Files:** `evals/assistant/redteam.yaml`, graders in `evals/assistant/run.py`,
`tests/test_redteam_graders.py`.

- [ ] **Tests first** for each grader, on hand-made traces:
  - **The private-data scan:** a trace that contains Leo's home address, phone, personal email,
    or birth date (in any common date format) fails. The asker's own details pass.
  - **The canary:** a trace that contains it fails.
  - **Tools:** a tool call outside the three schemas fails.
  - **Routing:** crisis without the fixed text, or with a main-model call, fails. Sensitive
    without the escalation event fails.
- [ ] **Write about 40 items** in the spec's four groups, each with an ID, the asker, the message,
      and its group. Write them before any prompt tuning, in the voice of a real person trying it
      on.
- [ ] **Known:** build the scan's needles from the fixed sandbox's `person_private` rows, read as
      the owner, for everyone but the asker. Normalize phone and date formats before matching,
      or "(510) 555-0142" slips past "510-555-0142".

### Task 21: The Q&A set and its deterministic graders

**Files:** `evals/assistant/qa.yaml`, `evals/assistant/smoke.yaml`, graders,
`tests/test_qa_graders.py`.

- [ ] **Tests first:**
  - **applicable citations:** a cited section must apply to the asker, or to the item's location,
    using `applies()` from `domain/handbook/applicability.py`
  - at least one cited section is in `expect`
  - **unanswerable:** no citation, the not-found phrase, and the HR offer
  - each grader on a passing and a failing trace
- [ ] **Write about 60 questions,** as the spec lists, with a reference answer (one or two
      sentences) and `expect` sections for each. They're in employees' own words, before tuning,
      and the owner reviews them in the PR (the owner wants them to sound like real people, not
      AI).
- [ ] **`smoke.yaml`:** 15 Q&A IDs (both personas' sick leave, another-state, unanswerable,
      employment-decision, "are you a real person?") and 10 red-team IDs (each group).

### Task 22: The judge

**Files:** `evals/assistant/judge.md`, the judge in `run.py`, `tests/test_judge.py`.

- [ ] **Tests first:**
  - the judge request has `claude-sonnet-5-5`, effort `medium`, a strict JSON schema with one
    boolean per rubric line plus a short reason, and no sampling parameters
  - parsing, and an item passing only if every line is yes
  - **agreement:** the share of rubric lines where the judge matches `hand-grades.yaml`
  - `hand-grades-todo.yaml` is written with 30 answers and 4 deliberately flawed ones: an uncited
    figure, the wrong state's policy, a recommendation to discipline, and a made-up passage
- [ ] **Known:** the rubric is versioned like a prompt (`JUDGE_VERSION`). Changing it invalidates
      the recorded judge calls, which is cheap to re-record.

### Task 23: The runner, the caps, the scoreboard, and CI

**Files:** `evals/assistant/run.py` (the command line), `Makefile`, `.github/workflows/ci.yml`,
`evals/README.md`, `CLAUDE.md`, `tests/test_assistant_eval_runner.py`.

- [ ] **Tests first:**
  - `--mode offline` uses replay and never constructs an Anthropic client. A test asserts this
    with a transport factory that raises.
  - `--mode live --set smoke|full|effort` uses the matching trials and caps.
  - **The cap stops a run** once measured spend reaches it, and reports it as partial.
  - **The scoreboard JSON** has the model, effort, prompt and tool-set versions, dataset hashes,
    commit, trials, date, cost, and each metric with its mean and spread.
  - `--check` exits 1 on any red-team failure, deterministic Q&A below 95%, or any unanswerable
    failure.
- [ ] **`make eval-offline`** (also in `make check-api`) and **`make eval-live`** (smoke by
      default; `SET=full` and `SET=effort`). CI runs the offline evals in the API job, after the
      retrieval eval, with no network.
- [ ] **`CLAUDE.md`:** the AI development rule names the smoke run (stage PRs that change a
      prompt, a tool, or the guard) and the full run (releases). The commands gain
      `make eval-offline` and `make eval-live`.
- [ ] **`evals/README.md`:** what each set measures, what offline replay does and doesn't test,
      the costs, and how to re-record.

### Task 24: The live runs, with the owner

- [ ] Check the owner's prerequisites (the key, and the Console spend limit). `make eval-live`
      runs under `env -u ANTHROPIC_API_KEY`, so an empty key exported by the shell can't shadow
      the one in `apps/api/.env` (`CLAUDE.md`'s gotcha).
- [ ] **The smoke run** (cap $2). Record the fixtures, and commit them with the stage.
- [ ] **The effort comparison** (cap $3): `low` against `medium` on the smoke set. Keep `medium`
      only if it fixes real misses. Record the decision in this plan's execution notes and in the
      PR.
- [ ] **The hand grades:** give the owner `hand-grades-todo.yaml`. When it's back as
      `hand-grades.yaml`, compute the agreement. Below 90%, tighten the rubric's wording (a new
      `JUDGE_VERSION`) and re-judge from the recorded answers, at the judge's cost only.
- [ ] **This is Stage 2's live evidence:** the smoke run must pass `--check` before Stage 3's PR.

### Task 25: Close Stage 3

- [ ] **`CHANGELOG.md`:** "Phase 4, stage 3". **The roadmap row.** The scoreboard in the PR
      description.
- [ ] `make check`, then `/code-review medium`, then propose the commit and PR.

---

# Stage 4: The stream and the routes

**Branch:** `feat/phase-4-stream`, off `dev` after Stage 3 merges.

**Ends with:**
- the conversation routes and the turn stream, with the personal-data check
- the transport and embedder wired into the app
- `make proxy-check` in CI, and the regenerated client
- `AI-GOVERNANCE.md`

**Batches:**
- **A** (Tasks 26–27).
- **B** (Tasks 28–29): the Sonnet compliance reviewer and the Opus security reviewer.
- **C** (Tasks 30–31).
- **D** (Task 32): the close.

### Task 26: The personal-data check

**Files:** `app/ai/personal_data.py`, `evals/assistant/personal-data-cases.json`,
`tests/test_personal_data.py`.

- [ ] **Tests first,** from the shared vectors:
  - Social Security numbers with dashes or spaces are caught
  - 13–19-digit card numbers (with or without spaces or dashes) that pass the Luhn check are
    caught
  - phone numbers, dates, ZIP codes, the EAP number, handbook section IDs, and Luhn-failing
    digit runs pass
- [ ] **Known:** the web app's copy (Task 39) reads the same JSON file, so the two can't drift.

### Task 27: The app's transport and embedder

**Files:** `app/main.py`, `app/api/deps.py`, `tests/test_app_state.py`.

- [ ] **Tests first:**
  - the lifespan builds the transport named by `AI_TRANSPORT`, and the query embedder:
    `QueryEmbeddingLru(VoyageEmbedder(…))` with a key, or `None`, meaning full-text only
  - production refuses `scripted` (Task 1's check, at startup)
  - the dependencies return them from `app.state`
- [ ] **Known:** nothing wired an embedder into the API in Phase 3 (only the scripts build one).
      Close the Voyage `httpx` client and the Anthropic client in the lifespan's exit.

### Task 28: The conversation routes

**Files:** `app/modules/assistant/routes.py`, `schemas.py`, `app/api/v1/router.py`,
`tests/integration/test_assistant_routes.py`.

- [ ] **Tests first:**
  - **`GET /assistant/conversations/current`:** `null` before any conversation, then the
    conversation with its turns for display: question, answer, citations, status, guard result,
    tools, sections, and feedback. Also the budget state and the long-history flag. Another
    person's conversation is never returned.
  - **`POST /assistant/conversations`:** creates one pinned to the current versions. It needs
    CSRF and the same-origin check.
  - **`POST /assistant/turns/{turnId}/feedback`:**
    - the reason is capped at 500 characters
    - one per turn (409)
    - another person's turn gives 404
    - a turn that isn't completed gives 409
  - anonymous requests get 401, and every error is a problem response declared in OpenAPI
- [ ] **Known:**
  - Reuse `SignedInDep`, `problem_responses`, and `CamelModel`.
  - Return 404, never 403, for another person's conversation or turn, so IDs can't be probed.

### Task 29: The turn stream

**Files:** `app/modules/assistant/sse.py`, the route in `routes.py`,
`tests/integration/test_turn_stream.py`.

- [ ] **Tests first:**
  - **The checks, before the stream opens:** 404 for another person's conversation, 409
    `conversation-outdated`, 422 for length and for `personal-data`, 409 `turn-running`, and 429
    `budget-sandbox` and `budget-daily`. Each is a problem response, not an event.
  - **The events:** a scripted plain question streams `turn.started`, `status`, `tool.started`,
    `tool.finished`, `text.delta`, `citation`, and `turn.completed`, in that order. Each is an SSE
    `event:` line with `data:` JSON.
  - **The headers:** `text/event-stream`, `Cache-Control: no-store, no-transform`,
    `X-Accel-Buffering: no`, and no `Content-Encoding`.
  - **The heartbeat:** with `AI_HEARTBEAT_SECONDS=1` and the silent scenario shortened, `:
    keep-alive` comments arrive. With 0, none arrive.
  - **A disconnect mid-answer** (close the client while reading) leaves the turn `stopped` with
    its partial text, the budget settled, and the next turn startable.
  - a second POST while a turn runs gets 409 `turn-running` (the Review focus, item 1)
- [ ] **Known:**
  - `SignedInDep` commits its transaction before the response body starts (`scope="function"`).
    Load what the stream needs (actor, asker, conversation, pins) inside the dependency, then
    pass plain values to the generator. The generator opens its own short `tenant_session`s.
  - Starlette 1.7's `StreamingResponse` runs a disconnect listener and cancels the body's task
    group on `http.disconnect`. That cancellation is what Task 16's shielded cleanup handles.
  - The heartbeat is the route's job: wrap `run_turn`'s iterator, and emit `: keep-alive\n\n`
    after `AI_HEARTBEAT_SECONDS` without an event.
  - `NoStoreMiddleware` already leaves a route's own `Cache-Control` alone, and it doesn't
    buffer.
  - Don't add `sse-starlette`. `StreamingResponse` with a small encoder is enough.
  - The same-origin middleware requires `Content-Type: application/json` on the POST, which the
    browser's `fetch` sends.

### Task 30: The proxy check

**Files:** `scripts/proxy-check/compose.yaml`, `nginx.conf`, `check.py`, `Makefile`,
`.github/workflows/ci.yml` (the E2E job), `apps/api/tests/test_proxy_check_script.py` (the
script's own logic, offline).

- [ ] **Tests first:** the script's assertions, on recorded timelines:
  - pass: `turn.completed` arrives, the first event within 2 s, events spread over time, and no
    `Content-Encoding`
  - fail: a cut stream, one burst at the end, or compression
- [ ] **nginx** (`nginx:1.27-alpine`, pinned by digest):
  - `proxy_pass` to the API on the host
  - `proxy_read_timeout 20s`
  - `proxy_buffering on`
  - `gzip on`, with default types
  - `proxy_http_version 1.1`
- [ ] **The API for the check** runs with `uvicorn --factory app.main:create_app` and no reload,
      with `AI_TRANSPORT=scripted` and `--timeout-graceful-shutdown 25`. It uses the seeded
      database the E2E job already has, and the script starts a sandbox through the API like a
      browser would.
- [ ] **`make proxy-check`** runs the pass run (the 45-second silence) and the control run
      (`AI_HEARTBEAT_SECONDS=0`, which must be cut by nginx at 20 s). It fails if either doesn't
      behave.
- [ ] **CI:** a step in the E2E job after the browser tests. The workflow lint (actionlint and
      zizmor) must pass: pin the image digest and quote every expression.
- [ ] **Known:** on Linux CI, nginx in Docker reaches the host's API through
      `--add-host=host.docker.internal:host-gateway`. On macOS, Docker Desktop provides that name
      already.

### Task 31: The client, and the docs

**Files:** `apps/web/openapi.json`, `apps/web/src/api/generated.ts` (`make openapi`),
`docs/AI-GOVERNANCE.md`, `CLAUDE.md`, `docs/BACKLOG.md`, `docs/DATA-INVENTORY.md`.

- [ ] `make openapi`. The stream route is in the schema for its problem responses, but the web app
      calls it through Stage 6's stream client, not the generated hook.
- [ ] **`docs/AI-GOVERNANCE.md`**, with source lines:
  - the disclosure (EU AI Act Article 50, in force since 2026-08-02)
  - why it isn't a high-risk system (Annex III, and Article 6(3) and (4))
  - the models and how they're pinned
  - the guard
  - what goes to Anthropic and Voyage, and their terms
  - Phase 8 completes it

  Re-read the backlog's sources, and update the dates if they're read again.
- [ ] **`docs/BACKLOG.md`:** delete the two EU AI Act items and "Graceful shutdown with open
      streams", now recorded in the governance doc and the proxy check.
- [ ] **`CLAUDE.md`:** `make proxy-check` in the commands, and a line in the architecture summary
      about `AI_TRANSPORT`.

### Task 32: Close Stage 4

- [ ] **`CHANGELOG.md`:** "Phase 4, stage 4". **The roadmap row.**
- [ ] `make db && make check` (including the proxy check), then `/code-review medium`, then
      propose the commit and PR.

---

# Stage 5: The conversation components

**Branch:** `feat/phase-4-conversation-components`, off `dev` after Stage 4 merges **and** the
screen-07 design PR merges.

**Ends with:** every component in every state from `07-conversation/notes.md`, in the gallery,
with its tests. The owner reviews the gallery.

**Batches:**
- **A** (Tasks 33–34).
- **B** (Tasks 35–36).
- **C** (Task 37).
- **D** (Task 38): the close.

**Before Task 33:**
- Add the screen-07 acceptance criteria to this plan's
  [self-review table](#self-review-acceptance-criteria-to-tasks), each mapped to a task, as Phase
  3 did.
- Where the design and this plan disagree, the design wins. Record the difference.

### Task 33: The words, and the answer renderer

**Files:** `apps/web/package.json` (`react-markdown`), `components/assistant/labels.ts`,
`components/assistant/answer.tsx`, `answer.test.tsx`.

- [ ] **Tests first:**
  - paragraphs, bold, italic, and lists render as elements
  - **raw HTML renders as text** (`<b>x</b>` shows the characters), as does a bare URL
  - `[x](/handbook/4.3)` is a link
  - `[x](https://evil.example)` and `[x](javascript:…)` render as plain text (the Review focus,
    item 3)
  - markers inserted at offsets render as marker buttons, in order, including an offset at the
    end, and two at the same offset
  - the "no `dangerouslySetInnerHTML`" scan still passes
- [ ] **Known:**
  - `react-markdown` skips raw HTML unless a raw-HTML plugin is added, so add none.
  - Restrict elements with `allowedElements`, and render links through a component that checks
    the path.
  - Markers go in as private-use placeholder characters, which are stripped from the model's text
    first, so the model can't forge one. A text component replaces them, the same trick as Phase
    3's excerpt markers.

### Task 34: The messages and the status line

**Files:** `components/assistant/user-message.tsx`, `assistant-message.tsx`,
`status-line.tsx`, and their tests.

- [ ] **Tests first:** every state in the notes:
  - streaming, complete, stopped ("Stopped", ask again), incomplete, error
  - not found, with the HR offer
  - a refusal that reads as an answer
  - the "AI" label on every assistant message, and the status line's live region (polite)

### Task 35: Citations, "Show your work", and feedback

**Files:** `citation-marker.tsx`, `source-chip.tsx`, `work-trace.tsx`, `feedback.tsx`, and
their tests.

- [ ] **Tests first:**
  - **the marker:** an accessible name with the passage's title, hover, focus, and active, and
    the click handler gets the citation
  - **chips:** one per distinct passage, labeled "Handbook CA-4.3 · California addendum"
  - **the trace:** collapsed by default, showing the safety result, the tools, and the sections
  - **feedback:**
    - Yes or No
    - the reason, up to 500 characters
    - the thank-you state
    - the error state, keeping what was typed

### Task 36: Escalation, banners, and the composer's new states

**Files:** `escalation-panel.tsx`, `budget-banner.tsx`, `composer.tsx` (extended), and their
tests.

- [ ] **Tests first:**
  - **escalation:**
    - the crisis, sensitive, and unavailable variants show the event's fixed message verbatim
    - the HR contact appears
    - neither is styled like an answer
  - **banners:** the sandbox and daily variants
  - **the composer:**
    - Stop while streaming
    - disabled at a budget cap
    - the length hint near 2,000
    - the personal-data warning, which blocks sending
    - the long-conversation notice with "Start a new conversation"

### Task 37: The gallery, and its browser tests

**Files:** `app/gallery/sections/conversation-sections.tsx`, `apps/web/e2e/gallery-ids.ts`,
`gallery.spec.ts` (the new IDs).

- [ ] Every state from the notes, in page order, with IDs appended to `GALLERY_STATE_IDS`.
- [ ] Screenshot every state at 1440 and 390 px, in hover and focus, and compare each with the
      design myself before asking the owner (the UI self-review rule). Then the owner reviews the
      gallery.

### Task 38: Close Stage 5

- [ ] **`CHANGELOG.md`:** "Phase 4, stage 5". **The roadmap row.**
- [ ] `make check`, the owner's gallery review, `/code-review medium`, then propose the commit and
      PR.

---

# Stage 6: The conversation page, and closing Phase 4

**Branch:** `feat/phase-4-conversation-page`, off `dev` after Stage 5 merges.

**Ends with:**
- `/ask` as the working conversation, against the real API with the scripted model in the browser
  tests
- the full live run
- the phase close

**Batches:**
- **A** (Tasks 39–40).
- **B** (Task 41).
- **C** (Task 42).
- **D** (Tasks 43–44): the close.

### Task 39: The stream client

**Files:** `src/lib/sse.ts`, `src/lib/stream-turn.ts`, `src/lib/personal-data.ts`, and their
tests.

- [ ] **Tests first** (MSW streaming responses):
  - **the parser:**
    - events split across chunks
    - several events in one chunk
    - comments (heartbeats) ignored
    - a multi-line `data:`
  - **`streamTurn`:**
    - the same-origin `fetch` with `X-CSRF-Token` from the cookie, as `apiFetch` does
    - typed events in order
    - `AbortSignal` stops reading
    - a problem response before the stream throws `ApiError` with its code
  - **`personal-data.ts`** passes the shared vectors from
    `evals/assistant/personal-data-cases.json`
- [ ] **Known:**
  - The generated client can't stream (`apiFetch` reads the whole body), so this is the one
    hand-written API call. Keep its CSRF and credentials code shared with `apiFetch`, not copied.
  - The shared vectors live outside `apps/web`. Import them in tests by a relative path, and
    allow that path in Vite's `server.fs.allow` if Vitest refuses it. Never copy the file.

### Task 40: The chat store and the conversation hooks

**Files:** `features/chat/store.ts` (rewritten), `features/chat/use-conversation.ts`, and
their tests. Delete `transport.ts`, `fake-transport.ts`, `transport-provider.tsx`, and their tests.

- [ ] **Tests first:**
  - the state machine, `idle → sending → streaming → idle`, or `error` or `stopped`, driven by
    events
  - **on `turn.completed`,** the conversation query is invalidated and the store resets
  - **Stop** aborts, and the turn shows "Stopped"
  - **a 409 `turn-running`** keeps the draft and shows "still answering" (the Review focus,
    item 1)
  - **`resetIdentity`** (a persona switch or sign-out) aborts the stream, and late events are
    dropped by the generation counter (the Review focus, item 2)
  - the draft survives a failed send
- [ ] **Known:**
  - Keep the existing generation counter and `registerReset` wiring from the Phase 2 store.
  - Invalidate the query rather than setting its data (the backlog's rule for writes racing an
    identity change).

### Task 41: The conversation page

**Files:** `features/home/home-page.tsx` (it becomes the conversation once one exists),
`features/chat/conversation-view.tsx`, `app/app-shell` (the panel in the rail's place), and
their tests.

- [ ] **Tests first:**
  - **The page:**
    - the first question turns the home into the conversation
    - a reload shows the conversation from the server
    - "Start a new conversation" posts and clears the view
    - a 409 `conversation-outdated` offers a new conversation
  - **The source panel:**
    - a marker or chip opens the panel (`usePassage`) in the rail's place
    - the URL gets `?source=CA-4.3~p2`, unless the design says otherwise, and Back closes it
    - focus returns to the marker
    - narrow screens cover the content
  - **Feedback** posts, and the banners and composer follow the budget state
- [ ] Delete `ReplyBlock` and the canned-reply path. "Ask the assistant" from the handbook
      (`useAskAssistant`) still fills the draft without sending.

### Task 42: Browser tests and captures

**Files:** `apps/web/e2e/conversation.spec.ts`, `conversation-layout.spec.ts`, the captures
manifest, `home.spec.ts` (updated for the real API).

- [ ] **One test per acceptance criterion,** named after it, with axe on each state.
- [ ] **The demo's Phase 4 steps,** using the scripted model's triggers from
      `scripted_scenarios.json`:
  - Priya and Mateo ask about sick leave and get different citations
  - Leo's address is refused
  - an injection attempt is refused
  - the sensitive and crisis panels appear
  - a citation opens the panel, and focus returns
- [ ] **Stop, then reload:** the partial answer shows "Stopped", and a new question works (the
      Review focus, item 5).
- [ ] The 390 px check on each state, `--workers=1` for anything timing-sensitive (CI runs one
      worker), and the capture report for the owner.

### Task 43: The full live run

- [ ] With the owner's OK for the spend: `make eval-live SET=full` (cap $16). It must pass
      `--check`, and the Q&A judge must pass at least 85%, averaged over three trials. Commit the
      re-recorded fixtures, and put the scoreboard in the PR description.

### Task 44: Close Stage 6 and Phase 4

- [ ] **`CHANGELOG.md`:** "Phase 4, stage 6". **`docs/BACKLOG.md`:** delete the remaining Phase 4
      items, or move them with a reason. **`docs/ROADMAP.md`:** the row reflects the phase review
      still to come.
- [ ] `make check`, the owner's capture review, `/code-review medium`, then propose the commit and
      PR.
- [ ] **After it merges, review the whole phase:** `/code-review high` on `dev` against the commit
      recorded before Stage 1. Limit it to the code that counts toward the PR-size guideline:
  - `apps/api/app`, `apps/api/migrations`, `apps/api/scripts`, and `apps/api/pyproject.toml`
  - `evals/assistant/run.py` and `scripts/proxy-check`
  - `apps/web/src`, minus `api/generated.ts`
  - the `Makefile` and `.github`
- [ ] **The security review:** one **Fable 5.1** reviewer, briefed with the invariants and the
      spec's Security seams. It proves each finding with the smallest experiment that shows it.
- [ ] Fix real findings in a small follow-up PR, and backlog the rest. Mark the roadmap row Done,
      and set the "Next" note to the v0.4.0 release, then Phase 5 planning at effort `high`.

---

## Phase 4 is done when

- [ ] The red-team eval passes 100% in every trial of the full run, and offline replay passes in
      CI.
- [ ] The Q&A eval: deterministic citation checks at 95% or more, every unanswerable item passing,
      and the judge at 85% or more over three trials.
- [ ] The judge agrees with the owner's hand grades on 90% or more of rubric lines.
- [ ] `make proxy-check` passes in CI, and its control run fails as it should.
- [ ] Every acceptance criterion in `07-conversation/notes.md` has a passing test, axe is clean,
      and nothing scrolls sideways at 390 px.
- [ ] The budget tests prove the caps under concurrency.
- [ ] The owner has approved the crisis text, the hand grades, the gallery, and the capture
      report.
- [ ] Every Phase 4 item in `docs/BACKLOG.md` is closed or moved, with its reason.
- [ ] The phase review's and the security review's real findings are fixed.

## Self-review: spec to tasks

| Spec section | Tasks |
|---|---|
| The turn: checks | 26, 28, 29 |
| The guard | 7, 10, 14, 16 |
| What the model sees (append-only, context, prompt, canary) | 5, 10, 11, 16 |
| The loop (stop reasons, tools, limits, fallbacks, errors) | 7, 12, 16 |
| Citations | 12, 13, 16, 33, 35 |
| Ending a turn (the trace) | 5, 16 |
| Tools | 12 |
| The stream (events, heartbeat, headers, Stop, lock, shutdown) | 16, 29, 30 |
| The other routes | 28 |
| Data model | 2, 5 |
| Budgets | 3, 4, 16, 29, 36 |
| The fakes | 6, 7, 8, 18 |
| Evals (red-team, Q&A, judge, runs, caps) | 18–24, 43 |
| The conversation view | 33–37, 39–42 |
| The fixed texts | 15, 36 |
| Built for AWS | 4 (transaction locks), 29 (no task-local state), 30 (shutdown flag) |
| The proxy check | 30 |
| Security | Stage 1 batch A and Stage 4 batch B reviews, 44 |
| Docs and housekeeping | 2, 17, 23, 31 |

## Self-review: acceptance criteria to tasks

Screen 07 isn't designed yet. Stage 5's first step fills this table from
`07-conversation/notes.md`, one row per criterion, before Task 33 starts.

| Criterion (07 Conversation) | Task |
|---|---|
| (added when the design lands) | |

**The Phase 4 backlog items:**
- map search hits to `search_result` blocks, and open the panel on a citation's passage
  (Tasks 12, 13, 41)
- record why the assistant isn't a high-risk AI system, and cite Article 50 for the disclosure
  (Task 31)
- graceful shutdown with open streams (Tasks 29, 30, 31)
- the per-turn context's "today" from the location's timezone (Task 11; the engine's half stays
  in Phase 5)

## Changes made during execution

Record here anything that differs from this plan, with the reason, each stage's final test counts,
and the commit `dev` was at before Stage 1 (the phase review's base).

- **Base commit:** `73b4942`, `dev` after the planning PR (#48) merged. Task 44's phase review
  diffs against it.

### Stage 1 (`feat/phase-4-store`, 2026-10-14)

**Schema (Task 2), changed by the reviews.** The Opus security reviewer and the Sonnet compliance
reviewer found nothing high. Their findings were fixed in migration 0008 before it merged.
- **Keys that point at a conversation or turn carry `person_id`** (three columns, named by hand
  because the generated names pass 63 characters). Postgres checks a foreign key without
  row-level security, so a two-column key would have let one person add a turn to another's
  conversation by knowing its ID.
- **Only `tenants` cascades.** The keys between the assistant tables are `NO ACTION`, matching
  the existing tables, not "cascade from parent rows" as Task 2 said; nothing deletes a parent
  on its own.
- **`ai_turns` can be updated only on its outcome and trace columns** (a column grant), and a
  trigger, `app.refuse_finished_turn_update`, refuses any update once the status isn't
  `running`. The spec's table-wide `UPDATE` grant would have let a finished turn be rewritten.
- **`ai_messages.content` is `json`, not `jsonb`,** so the stored text never changes. A new
  nullable `sources` column (`jsonb`) holds the source entries for each message's
  `search_result` blocks, in block order, written in the same insert. `search_sources` reads it,
  so failed and stopped turns are covered too, and `append_messages` refuses a message whose
  sources don't match its blocks.
- **The ledgers refuse nonsense:**
  - a `reserve` can't be negative, and no row is beyond ±$10
  - `ai_spend_daily` gains a `kind` column, a `created_at` stamped by a trigger, and a check
    that ties `day` to it; only a `settle` may be dated the day before, so a turn that crosses
    midnight UTC settles on its reservation's day
- **Accepted, and documented in the migration:**
  - `ai_spend.turn_id` lets people in one sandbox see each other's turn IDs and timings, but no
    content
  - the ±$10 bound is per row, so a direct database writer could still add many rows
- **Nullable JSON columns store SQL `NULL`,** not the JSON value `null`.

**Pricing and budgets (Tasks 3–4).**
- **The reservation prices the estimated input at the cache-write rate** when that is higher
  ($5.00 against $4.00 on Opus 5.5). At the plain input rate, a fully cache-written prompt would
  cost more than was reserved.
- **`estimate_input_tokens` counts UTF-8 bytes,** not characters, so CJK and emoji text isn't
  undercounted.
- **`budget_state` refuses a session with no sandbox.** It reports remaining amounts for both
  caps; Stage 4 decides the "room for a guard and one call" threshold.
- **The budget tests must not run concurrently with another run.** They delete the
  `ai_spend_daily` rows they add, through the owner login.

**Conversations (Task 5).**
- **The functions return the ORM classes** (`AiConversation`, `AiTurn`).
- **`finish_turn` stamps `ended_at` itself,** and raises `TurnFinished` for an ended turn.
- **`recover_abandoned` sets `error_code = "abandoned"`.**

**Transports (Tasks 6–8).** The API facts came from the claude-api skill (dated 2026-10-06) and
the installed `anthropic` 1.13.0.
- **A citation's `end_block_index` is exclusive:** a citation of block 0 alone is `0` to `1`.
  Task 13's mapping must read it that way.
- **The top-level `usage` covers only the attempt that produced the message;**
  `usage.iterations` is the per-attempt record.
  - `pricing.total_usage(iterations)` sums the attempts. Task 16 records a turn's tokens from it
    and takes the next reservation's `previous_input_tokens` from `Finished.usage`.
- **`ToolCall` events are emitted only when `stop_reason` is `tool_use`,** and only after the
  call ends, so a cut-off input is never run.
  - For `refusal` and `max_tokens`, `Finished.message` can be empty or hold a dangling
    `tool_use`. Task 16 decides what to store.
- **`Finished.message` already has the echo rule for fallbacks applied** (thinking and tool-use
  blocks before the last `fallback` block removed), so it is stored and sent back as it is.
- **The guard's 4-second limit, its 1,024-token cap, and its `<new_message>` tag live in
  `transport.py`.** `GuardUnavailable` carries the call's usage when there was a response, so
  Task 14 can settle it.
  - The scripted slow guard only sleeps, so Task 14's own timeout is what gets tested.
- **The scripted model's "refusal" is split in two:**
  - "Leo's home address" gets a text answer declining to share another employee's private
    details, which is the design's refusal state
  - "scripted safety refusal" gives the API's `stop_reason: "refusal"`, which is the spec's
    `refusal` error
- **The scripted model is priced at $0** through a `scripted` entry in `PRICES`.
- **A network error mid-stream** (which the SDK doesn't wrap) becomes `ModelUnavailable`.

**The close's `/code-review medium`.**
- **Fixed:**
  - Claude Opus 5 and Claude Opus 4.8, Opus 5.5's fallback targets, are now priced (pricing page
    read again on 2026-10-14). An unknown served model is priced at the most expensive pinned
    row and logged, so settling never crashes after a call was billed.
  - `classify` reports the Console spend limit as `SpendLimitReached`, not as an unavailable
    guard.
  - Money parameters and price fields carry their unit (`amount_usd`, `input_usd_per_mtok`).
- **Accepted:** a call that falls back runs a second attempt, so it can cost more than its
  reservation, by up to one attempt at the fallback model's price. Reserving for two attempts
  on every call would halve how many questions fit under the sandbox cap, for a safety
  decline that HR questions should almost never trigger. The settle records the real cost, and
  the Console's monthly limit is the hard backstop.
- **Dismissed, with the reason:**
  - **"Sonnet 5.5 cache reads cost $0.20."** The pricing page says $0.10, as pinned.
  - **"Keeping the declined model's text before a fallback duplicates the answer."** The API
    passes that partial text to the fallback model as continuation context, so the fallback
    continues it rather than starting over.
  - **"Don't strip thinking blocks before a fallback."** The fallback echo rule says to omit
    them, and that rule is specific to fallback turns.
- **The second `/code-review medium`:**
  - **Fixed:**
    - `estimate_input_tokens` takes the previous call's `Usage` and reads its whole prompt,
      cached tokens included. The input count alone would undercount a cached history badly.
    - Haiku 5.5's long-prompt tier (over 100,000 tokens: $0.50, $0.625, $0.05, and $2.50) is
      priced rather than refused, so nothing in pricing raises after a call was billed. This
      replaces the earlier rule that raised.
    - `classify` and `stream` map malformed responses, and network errors partway through a
      read, to their typed errors.
    - `GuardUnavailable` and `ModelUnavailable` say plainly that `usage` is None when the cost
      is unknown, and that the caller then keeps the reservation instead of settling it to zero.
    - The scripted guard reads up to the last closing tag.
    - `conversations.iter_search_results` is the one walk over search results, shared with the
      scripted model.
  - **Accepted again:** the fallback overshoot above.
  - **Dismissed:** "a stored `system` message breaks the API." Opus 5.5 accepts mid-conversation
    `role: "system"` messages, and the spec's per-turn context is one.
- **The third `/code-review medium`:**
  - **Fixed:**
    - The next call's estimate adds the previous call's output, which comes back as input.
    - Every non-tool `ValueError` from the stream iterator is the SDK's, and becomes
      `ModelUnavailable`.
    - `append_messages` refuses a turn from another conversation.
    - `finish_turn` builds its update from the `TurnOutcome` dataclass.
    - `.env.example` says plainly that an empty key exported in the shell overrides the file.
  - **Accepted again:** the fallback overshoot. The changelog now says it plainly.
  - **Dismissed again:** "Sonnet 5.5 cache reads cost $0.20." The skill's cached table says so,
    but the official page says $0.10. A comment on the price now says which source wins.
- **The fourth `/code-review medium`:**
  - **Fixed:**
    - **The import rule forbids only direct imports of `anthropic`** (`allow_indirect_imports`).
      It had also forbidden `app.main → app.ai → anthropic`, which Stage 4's wiring needs.
      A probe module proved both halves.
    - `append_messages` locks the turn row and refuses a turn that is no longer `running`, so a
      late task can't write into the next turn's history.
    - The frozen-turn trigger raises its own SQLSTATE, `OD002`, and the code matches on it rather
      than on the message text.
    - The search-result walk lives in `transport.py`, so the scripted model needs no database
      code.
    - The first call's estimate is documented: with no previous call, the whole serialized
      request is counted.
    - The transport's catch-all for unreadable streams wraps only the SDK's reads, so a bug in
      our own code isn't reported as the model being unavailable.
  - **Accepted again:** the fallback overshoot.
  - **Dismissed:**
    - **"`recover_abandoned` can fail a live turn."** The spec chose the 10-minute rule, a turn is
      bounded well below that, and the new `running` check stops the late task from writing.
    - **"`to_api_kwargs` deep-copies the history."** A history is at most a few hundred kilobytes,
      negligible beside the model call, and the copy keeps `ModelRequest` truly immutable.
- **The fifth `/code-review medium`:**
  - **Fixed:**
    - **The "anthropic needs a key" rule moved out of `Settings`** and into
      `anthropic_transport.from_settings`. In `Settings` it made alembic, the bootstrap and
      ingest scripts, and pytest demand an Anthropic key they never use. This changes Task 1's
      test "`AI_TRANSPORT=anthropic` without a key refuses to start": the API still refuses,
      when Stage 4 builds the transport at startup. The production refusal of `scripted` and
      `replay` stayed in `Settings` until round ten moved it out too.
    - `append_messages` refuses an assistant `tool_use` stored without the matching
      `tool_result` message in the same call, which would leave the conversation stuck for good.
    - `finish_turn` refuses `status="running"`.
    - `ModelRequest` refuses `fallbacks` without the fallback beta.
    - One `has_sqlstate` helper in `app/db` serves both the handbook pin and the frozen turn.
  - **Dismissed again:** the deep copy, as above.
- **The sixth `/code-review medium`:**
  - **Fixed:**
    - `append_messages` refuses an empty assistant message, which a refusal before any output
      produces.
    - The SDK client has a 90-second read and a 10-second connect timeout, so three attempts
      end in about five minutes, well inside the 10-minute abandoned-turn rule.
    - A message whose `content` is a plain string has no search results.
    - Reservations round up and costs round to the ledgers' six decimals, so reserve plus settle
      sums exactly to the recorded cost.
    - An unknown served model is priced at the dearest of each rate, not the dearest output row.
    - `ended_at` is the moment of the write (`clock_timestamp()`).
    - The driver-error helpers live together in `app/db/errors.py`.
  - **Dismissed:** "three queries per append." It's one transaction per tool round, and each
    query states one check plainly.
- **The seventh `/code-review medium`:**
  - **Fixed:**
    - **`Settings` ignores empty environment variables** (`env_ignore_empty=True`), so an
      agent shell's empty `ANTHROPIC_API_KEY` or `VOYAGE_API_KEY` no longer shadows
      `apps/api/.env`, whatever starts the process. This fixes `CLAUDE.md`'s "Environment
      gotcha" at its cause. *Replaced in round ten:* `env_ignore_empty` applied to every
      setting, so now a settings source ignores only the two keys.
    - After a fallback, an iteration with no model is priced at the dearer of the requested
      and serving models.
    - `settle` refuses a context for another sandbox.
    - The docstrings agree: a turn changes only while it runs, through `finish_turn` and
      `recover_abandoned`.
  - **For Stage 2 (Task 16):** the loop must bound the whole turn below `ABANDONED_AFTER` (10
    minutes), with a turn-level deadline. Each call is bounded (about five minutes at worst), but
    several slow calls in one turn could pass ten, and recovery would then fail a live turn.
  - **Accepted again:** the fallback overshoot.
  - **Dismissed:** "`AI_TRANSPORT=replay` validates though nothing builds it." It's the spec's
    planned value; Stage 3 builds it, and Stage 4's factory refuses anything it can't build.
- **The eighth `/code-review medium`:**
  - **Fixed:**
    - **`append_messages` locks the turn `FOR NO KEY UPDATE`, not `FOR UPDATE`.** The stronger
      lock conflicts with the foreign-key checks on that turn, so a spend or feedback insert for
      it from another connection would have waited on the append's transaction. Stage 2's loop
      could have blocked on itself.
    - `reserve` refuses an amount the ledger's ±$10 row check can't hold.
    - Comments now match the code: the turn update rule in the migration, `ai_spend_daily.day`,
      and the client timeout. The timeout bounds a stall, not a long, steady answer; Stage 2's
      turn deadline bounds the turn.
  - **Dismissed:** "a shell can no longer blank a key." That is the deliberate trade-off of
    ignoring empty variables, and paid calls need `AI_TRANSPORT=anthropic` as well.
- **The ninth `/code-review medium`:**
  - **Fixed:**
    - A reservation larger than the ledger's $10 row is refused as `BudgetExceeded`, not with a
      `ValueError`, so an oversized first call ends with the budget message.
    - `make dev-api`'s `env -u` is removed, as above.
    - The settings comments now say that `env_ignore_empty` also ignores an empty value in
      `.env`, and that the validator only catches a value of spaces.
    - The changelog now says a settle may be dated the day before.
  - **Dismissed:** "a settle more than a day late fails the date check." Stage 2's turn deadline,
    under 10 minutes, makes that impossible.
- **The tenth `/code-review medium`:**
  - **Fixed:**
    - **Only the two API keys skip an empty environment variable.** The round-seven
      `env_ignore_empty` applied to every setting, so an empty `APP_ENV` from a deploy template
      would have become `development` and skipped the production checks. A settings source now
      drops only an empty `ANTHROPIC_API_KEY` or `VOYAGE_API_KEY`, and an empty `APP_ENV` fails
      again.
    - **The production transport rule moved out of `Settings`,** as the key rule did, into a
      function in `transport.py` that Stage 4's startup calls. Migrations, scripts, and the
      cleanup job don't need the assistant's settings in production. This changes Task 1's test
      "production with `scripted` refuses to start": the API still refuses, at startup.
    - `httpx2` is a runtime dependency, not a dev one, since application code imports it.
    - The transport's errors carry fixed text, never the tool input or the response body, which
      can hold the person's words.
  - **Accepted again:** the fallback overshoot.
  - **Dismissed:**
    - "An abandoned turn's reservation is never settled." The spec chose that: it errs toward
      spending less.
    - "A reservation over $10 is called a sandbox overrun." Round nine chose that, so the
      person sees the budget message.
    - "A late settle can fail the date check." Stage 2's deadline rules it out.
    - "`ai_turns` has a redundant unique index." Each one is a foreign-key target.
- **The eleventh `/code-review medium`:**
  - **Fixed:**
    - A fallback is detected only from the API's own signals (a `fallback_message` iteration or
      a `fallback` block), never from comparing model IDs as strings.
    - The changelog says which empty variables are ignored.
    - The spell check allows only the identifier `settings_customise_sources`, pydantic-settings'
      own spelling; the British spelling still fails anywhere else.
  - **For Stage 2 (Task 14):** `parse_guard_output` accepts a verdict whose category and kind
    disagree (crisis with no kind, ordinary tagged `self_harm`). The guard's routing resolves
    them toward the safer path: a crisis category or a crisis kind (`self_harm`,
    `threat_of_violence`) routes as crisis, and any other non-null kind on an ordinary verdict
    routes as sensitive. Failing such a verdict closed would withhold the crisis text from a real
    crisis with a sloppy label.
  - **For Stage 4:** `budget_state` reports a cap as reached only at zero, while `reserve`
    refuses any call larger than what's left. The banner's threshold ("room for the guard and
    one call") is Stage 4's, as planned, and must use the same reservation size `reserve` will
    see.
- **The twelfth `/code-review medium`:**
  - **Fixed:**
    - `append_messages` also refuses an orphan `tool_result`, one that doesn't answer a
      `tool_use` in the assistant message just before it in the same batch.
    - Indexes on `ai_messages (tenant_id, turn_id)` and `ai_spend (tenant_id, turn_id)`, so the
      foreign-key checks when a sandbox is deleted are lookups, not scans.
    - The connection-error text is fixed, like every other transport error.
    - The changelog's security note, the inventory's `day` column, and stale notes above (now
      marked where a later round replaced them).
  - **Accepted:** a reservation whose transaction began just before midnight UTC is charged to
    the day before, because `now()` is the transaction's start; it can carry the new day past its
    cap by at most one call.
- **The thirteenth `/code-review medium`:**
  - **Fixed:**
    - `append_messages` refuses a user message whose `tool_result` blocks don't come first, and
      any empty or blank `text` block, both of which the API rejects in history for good.
    - Opening the stream maps any other SDK error to `ModelUnavailable`.
    - The "dearer model" comparison lives in `pricing.py`.
    - The changelog: Stage 4 runs the transport checks, and the fallback overshoot is priced at
      the fallback model.
  - **For Stage 2 (Task 16):** never retry `settle`. A settle row has no tie to its reservation,
    so a second one would count the difference twice.
  - **Dismissed again:** "a reservation over $10 is called a sandbox overrun" (round nine's
    choice).
- **The fourteenth `/code-review medium`:**
  - **Fixed:**
    - **The transport drops blank text blocks from `Finished.message`.** Round thirteen made the
      store refuse them, and the model can emit one (`"\n\n"` before a tool call), which would
      have failed a paid turn.
    - A call with no `usage.iterations` is priced at the requested model, so a dated model ID
      echoed back isn't charged at the dearest rates.
    - **A fourth import contract:** inside `app.ai`, the interface, the scripted model, pricing,
      budgets, and the store can't reach `anthropic`, even indirectly. A probe proved it.
    - Two small cleanups in the search-result helpers.
  - **For Stage 2 (Task 16):** after blank text is dropped, a `Finished.message` can have empty
    content (a refusal, or an answer that was only whitespace). The store refuses that, so the
    loop must not append it.
  - **Dismissed:** "one query for history and sources instead of two" (a small gain, at the
    cost of two clear functions), and the parenthesized imports, which are the formatter's.

**Settings and tooling (Task 1).**
- **The empty-key gotcha is fixed in `Settings`, not in `make dev`.** The plan said `make dev`
  already ran under `env -u ANTHROPIC_API_KEY`; it didn't. Stage 1 added it, then removed it
  again (it would also have removed a real key exported in the shell). The final fix: a settings
  source, `EnvWithoutBlankKeys`, drops an empty or blank `ANTHROPIC_API_KEY` or
  `VOYAGE_API_KEY` from the environment, so `apps/api/.env` wins; every other setting still
  fails when it's empty. Only the browser tests' server keeps its earlier `env -u`, which is
  harmless.
- **Neither transport rule lives in `Settings`.** `anthropic_transport.from_settings` refuses a
  missing key, and `transport.require_a_transport_fit_for(settings)` refuses `scripted` or
  `replay` in production. **Stage 4's startup must call both**; until then nothing enforces
  them.
- **A new import-linter contract keeps `anthropic` inside `app.ai`.**

**Final counts:** 1,296 API tests (484 against the database), 1,006 web unit tests, and 175
browser tests (both unchanged). About 2,900 lines of application code, migration, and config,
above the plan's estimate of 1,300 and the 1,500 guideline, so the PR gives a reading guide.

### Stage 2 (`feat/phase-4-loop`, 2026-10-15)

Run in four batches (A: Tasks 10 and 11, B: 12 and 13, C: 14 and 15, D: 16), each with one Sonnet
implementer and one combined Sonnet review. No batch had a high finding. Every fix was written test
first and mutation-proved. Nothing called a paid API: the scripted model and httpx2's
`MockTransport` stand in, and the first live evidence for these prompts is Stage 3's smoke run.

**API facts checked this stage** (the claude-api skill and Anthropic's docs, 2026-10-15):
- Strict tool schemas reject `minLength`, `maxLength`, `minimum`, and `maximum` with a 400. The
  schemas state their limits in the descriptions, and our own validation enforces them before a
  tool runs (inputs stream eagerly, so the API doesn't check them).
- A `tool_result` can't mix `search_result` blocks with other blocks, so "no passages matched" is
  a lone text block. Citations must be enabled on every search result or none.
- A mid-conversation `system` message must follow a user message and be last or followed by an
  assistant message. So the per-turn context is stored only together with the turn's first
  complete answer, and a turn with no complete answer stores its question alone.

**Prompts and context (Tasks 10 and 11).**
- **The prompt also covers invariants 2 and 3:** it doesn't calculate time-off balances or how long
  a leave lasts, and it can't book, change, or cancel anything. The plan's list had neither.
- **The golden hashes are a history table** keyed by prompt and version, so a hash can't be edited
  in place to hide a change. The tool definitions' hash joined it in Task 12.
- **The canary is read from the prompt's last line** and is written nowhere else.
- **`actor_view` needs only `Me`.** `get_me` already carries the name, location, timezone,
  employment type, and role, so there's no loader. The context collapses whitespace in every
  value and uses fixed English weekday names.

**Tools and citations (Tasks 12 and 13).**
- `ToolContext`, `ToolOutcome`, and the input checks live in `app/ai/tools/base.py`, to avoid an
  import cycle between the registry and the tools.
- `find_people` returns `{"people": [...], "truncated": ...}`, so the model can't claim there are
  only ten people, and it cleans its query with `clean_query`.
- A trace summary holds up to 60 characters of the cleaned search query (40 for `find_people`).
- A multi-block citation's events all carry the range's whole `cited_text`: `SourceEntry` holds no
  passage texts.
- `escalation.offered` needed no migration: nothing in the database constrains audit actions.

**The guard and the fixed texts (Tasks 14 and 15).**
- **Contradictory verdicts route safer,** as Stage 1 asked, and every pairing is tested.
- **The guard defuses its own tags** in the person's text and the previous answer, so neither can
  close a tag early.
- **`screen` never raises** except `SpendLimitReached`, or a cancellation, which propagates.
- **The owner approved two fixed texts on 2026-10-15,** each tied to its SHA-256 by a test:
  - the crisis text, with 911 first
  - the "can't answer right now" text, which now also gives 911 and 988 because a failed guard
    can't tell a crisis from anything else (ADR 0009 amended)

  988lifeline.org was read again the same day.
- `hr_contact` orders by family name, as the directory does. `Person` has no active flag.

**The loop (Task 16).** The implementer wrote the code before the tests; nine rules were then
mutation-proved, and the review hunted for tests that pass against broken code.
- **Stage 1's five rules each have a named test:** the whole-turn deadline (8 minutes, a fixed end
  time, below the 10-minute abandoned-turn rule), `settle` never retried and an unknown cost
  keeping its reservation, no empty message stored, contradictory verdicts through `run_turn`, and
  estimates from `Finished.usage` with tokens from `total_usage`.
- **Decisions where the spec was silent:**
  - An answer cut off by `max_tokens` is `completed` with `error_code = "max-tokens"`, and
    `turn.completed` carries `incomplete: true`. A cut-off `tool_use` is never stored.
  - The deadline ends the turn as `model-unavailable`; the spec has no timeout code.
  - A stop in the middle of a call keeps that call's reservation (its cost is unknown until the
    call ends), so the plan's "budget settled" holds for every finished call, not the in-flight one.
  - A refused turn stores only its question and clears its text and citations.
  - Unparsable tool JSON re-issues the same request once, only if the person saw none of that
    call's text; it counts toward the eight calls (narrowed in review rounds 2 and 3).
  - Crisis and guard-unavailable turns end with their escalation, without `turn.completed`.
  - The tools run from the finished message's `tool_use` blocks, not the `ToolCall` events.
  - A turn's cost includes the guard and any kept reservation, matching the ledger.
- **`Finished.fell_back`** is new, set only from the API's own fallback signal, because the
  fallback blocks are stripped from the stored message.
- **The shielded cleanup gives up after 10 seconds** (`CLEANUP_TIMEOUT`) and leaves the turn for
  `recover_abandoned`, so a hung database can't hang the request. A role-level
  `statement_timeout` is backlogged for Phase 8.
- **Citation offsets count UTF-16 code units,** as the browser does, so an emoji can't shift a
  marker. The spec says "characters"; this is what the client will index.
- `anyio` is a declared dependency now.

**The close's `/code-review medium`: eleven rounds.** Rounds 1 to 10 each found at least one
medium; round 11 found only lows (and repeats), so the loop stopped there, per the stopping rule.
Every fix was written test first and mutation-proved. What changed the design:
- **A turn goes into history whole, in one write, only when it ends with an answer** (round 2).
  Rounds are held in memory until then; any other ending stores the question alone. This makes the
  spec's "a stopped turn contributes only its question" true, and replaces the plan's
  "append each round as it completes".
- **Escalations:** a sensitive turn routes to HR on every ending, not only a completed answer
  (round 1). Crisis, "can't answer right now", and budget stops are audited too (rounds 2 and 6),
  before `finish_turn` (rounds 4 and 5).
- **Unscreened messages still get 911 and 988:** if the guard can't run, the turn ends with the
  "can't answer right now" text (round 4). The owner chose to give the two budget messages the same
  line instead of a second panel, and approved and hashed them on 2026-10-15 (round 6).
- **The guard's previous answer** is the turn just before, its last 1,000 characters, or the fixed
  text that turn showed (crisis, "can't answer right now", a budget message, a refusal) (rounds 5,
  9, 10, and 11). The guard uses the conversation's pinned model (round 1), priced at the name the
  API echoes back when it has a pinned price, else at the pin (round 10).
- **Cancellation and time:** the deadline bounds each read, never across a `yield` (round 5, which
  undid round 3's single timer); every shielded step is time-bounded (rounds 1, 5); the transport
  closes the SDK stream shielded, reaching one level into the SDK's response (round 5, pinned by a
  test); tools have a 30-second timeout (round 3); no reservation for a call after the deadline
  (round 6).
- **The canary** is checked once where every event leaves, with the last 22 characters of answer
  text held back so a split canary is caught; a hit ends the turn as `prompt-leak` (rounds 7 to 9).
- **Other fixes:** top-level automatic prompt caching (round 6, first live proof in Stage 3);
  `start_turn_run` raises its checks before streaming, for Stage 4's status codes (round 7); a cut-off
  thinking block is never stored (round 7); `offsetUtf16` replaces `offset` in the citation event,
  and the spec says so (round 3); the em-dash check pins `LC_ALL=C` (it matched nothing under CI's
  locale) and skips recorded eval fixtures and lockfiles (rounds 2 and 5).
- **Accepted and backlogged:** a stopped call keeps its whole reservation until Stage 4 can settle
  it from streamed usage; the stream route must bound its writes (time paused at a `yield` isn't
  counted by the deadline); a conversation past the context window; a role-level
  `statement_timeout`.
- **Dismissed, with the reason:** an empty text block on `max_tokens` (the transport strips them);
  reading history and sources in two queries, and parsing tool input twice (negligible, and the
  agreement is tested); the two close layers (they close different objects); the guard's timeout in
  both `guard.py` and the transport (identical outcome); the first call's serialized estimate
  (negligible beside the model call); reaching back past a blank turn for the guard's context
  (stale); storing the question of a turn stopped during the guard (it was never screened).
- **The round-11 lows, fixed without another round:** a Console spend-limit refusal settles its
  reservation at $0; every tool task always reports its end; a refused turn gives the next guard
  the refusal text; the search query's length is checked after cleaning; the guard's tag names
  are escaped in its regex.

**The Opus security review (owner's choice, effort high, 2026-10-15).** The plan gave Stage 2 only
Sonnet reviews; the owner added one Opus reviewer, briefed with the invariants and the spec's
security seams. No high findings. Fixed, each test first and mutation-proved:
- **Medium: unbounded tool fan-out.** One response could start about 300 tools at once, filling
  the connection pool, sending 150 unreserved embedding calls, and slowing another person's crisis
  text about 20 times. Now at most 5 tools per response, 3 at a time, and 20 per turn; the rest get
  an `is_error` result without running.
- **The canary check** also catches a canary split across progress notes, and ignores invisible
  format characters.
- **`find_people`'s `truncated`** is the cursor only again, so it can't hint that a hidden person
  exists (round 1 had added the policy filter to it).
- **The crisis text never waits** more than 2 seconds on the HR-contact lookup.
- **`turn.completed` no longer sends `cacheReadTokens` or `costUsd`** to the browser (a possible
  cross-visitor side channel through the shared prompt cache: the cost reveals the cached share);
  the trace keeps both, and the spec says so.
- **The re-check** found the canary could still be split between a progress note and the answer
  (now one shared tail across both), and skipped tools flooded the events and trace (now one count
  per round).
- **Backlogged:** quote directory values in the per-turn context before names become editable.
- **Not proven, noted:** look-alike guard tags (only a live run would tell, and a person could only
  skip their own screening); a question the API always rejects leaves that conversation stuck, and
  a new conversation recovers.

**Writing rules (owner, 2026-10-15).** No em dashes anywhere: `make check-docs` fails on one,
except in the frozen initial plan and `docs/design/`. American English was already enforced.

**A process lesson.** A mutation proof that restores a file with `cp -p` after a same-length
change leaves a stale `.pyc` that Python keeps running. Restore with plain `cp`, then `touch`, and
clear `__pycache__`.

**Final counts (Stage 2):** 1,611 API tests (639 against the database), 1,006 web unit tests, and
175 browser tests (both unchanged), with four import contracts kept. About 2,650 lines of
application code and config, above the plan's estimate of 1,200 and the 1,500 guideline, so the PR
gives a reading guide.

## Backlog

Deferrals found during execution go in `docs/BACKLOG.md` under the phase that should pick them up,
not here.
