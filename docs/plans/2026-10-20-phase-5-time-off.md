# Phase 5: Time Off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use
> checkbox (`- [ ]`) syntax for tracking. **Project rule:** never commit, push, or open a PR without
> the owner's explicit OK for that action (see `CLAUDE.md`). Every "Propose the commit" step stops
> and waits.

**Goal:** an employee books time off in plain language or on a page, and their manager approves
it in either place. A pure engine counts every day and balance, the model only proposes, a person
confirms every write, and each AI-started change is audited back to its proposal.

**Architecture:**
- **The engine** (`app/domain/timeoff/`) is pure: schedules, holidays, PTO earning and its
  ceiling, each year's sick grant, and request checks, every result citing its handbook section.
  Balances are derived from an opening balance and the requests on every read (ADR 0012).
- **The time-off service** (`app/modules/timeoff/`) is the only writer of requests: a per-person
  lock, the engine's check against current data, the write, and its audit event, in one
  transaction. The pages call it directly; a confirmed proposal calls it too.
- **Proposals** (`app/ai/proposals.py`): rows bound to the person, the conversation, and the turn,
  with a 15-minute expiry and a one-way status. The confirm route locks the row and executes once.
- **The assistant** gets six tools. A proposal tool ends its turn normally, and its outcome reaches
  the next turn's context (ADR 0013).
- **The web app** adds `/time-off`, `/approvals`, the home's at-a-glance cards, and the confirm card
  in chat.

**Tech stack:** as Phase 4 (FastAPI, SQLAlchemy 2.1 async, Alembic, Postgres 17 with pgvector and
now `btree_gist`; React 19, React Router 7, TanStack Query 5, Zustand 5, Tailwind 4, shadcn/ui,
Orval). No new runtime dependency is planned; a date library is decided in Stage 5 only if the
design needs one.

**Spec:** [`../specs/2026-10-20-phase-5-time-off.md`](../specs/2026-10-20-phase-5-time-off.md) ·
**ADRs:** [0012](../adr/0012-balances-derived-by-the-engine.md),
[0013](../adr/0013-proposals-in-the-turn.md), and the earlier
[0004](../adr/0004-stored-proposals.md) · **Roadmap:** [`../ROADMAP.md`](../ROADMAP.md)

---

## How this plan is written

**Outlines, not finished code,** as in Phases 2 to 4. Each task gives:
- the files
- the tests to write first, and what each proves
- the interfaces later tasks depend on
- "Known:" notes on traps found while planning

The traps come from reading the repository and the spec, not from a trial build: there was none
(the owner's "no scratch prebuild" rule). The implementer writes each test first, watches it fail
for the right reason, and then makes it pass. Problems are solved during the build and recorded
under [Changes made during execution](#changes-made-during-execution).

**The spec is the authority** on behavior: the engine's rules, the table columns, the routes, the
event shape, and the tools. Where this plan and the spec disagree, the spec wins, and the
difference is recorded.

---

## Global constraints

Every task's requirements include these.

- **The seven invariants** in `CLAUDE.md`. Above all, for this phase:
  - the model never calculates a day, an hour, or a balance: the engine does, and the model
    quotes the engine's labels
  - the model never writes: a turn's only writes are proposals and their audit events
  - every tool takes the actor from the session; `person_name` is resolved only among the people
    the actor may read
  - no text a person wrote reaches the model
- **The engine is pure:** no framework imports (import-linter already enforces it), no clock, no
  database. "Today" is an input, from the location's time zone, never the anchor date.
- **Engine tests use hand-worked fixtures only.** Each expected value is worked out by hand from
  the handbook's rule, with the arithmetic in a comment. Never run the engine and paste its
  output.
- **Units:** integer minutes in the engine and the database (`amount_minutes`), `amountMinutes` in
  the API, plus the shared label. Timestamps in UTC; leave dates are calendar dates.
- **No paid AI call** in tests, CI, or `make dev`, and none at all before Stage 4. The scripted
  model drives development and the browser tests.
- **Theme tokens, never raw hex,** in components. No `dangerouslySetInnerHTML`.
- **`CHANGELOG.md`** in the same edit as the change. **`docs/DATA-INVENTORY.md`** in the same task
  as any new table or column.
- **Implementers merge, never replace,** `tests/integration/conftest.py`, `docs/BACKLOG.md`, and
  `docs/DATA-INVENTORY.md`.
- **Mutation proofs:** restore with plain `cp` (not `-p`) or `touch` the file afterward, delete
  `__pycache__` under `apps/api/app` and `tests`, and rerun the suite.

## Review focus

The inputs most likely to hurt a person that the spec implies but doesn't spell out. Each has its
test in the task named.

1. **A double click on Confirm, or the same card confirmed in two tabs.** Expect one request, and
   the second click to show the executed card calmly, never an error page. *Tests: Task 17 (two
   concurrent confirms), Task 33 (the card after a 409).*
2. **The balance changes between the card and the confirm** (a request approved on the page, or a
   second card). Expect the card to fail with the engine's reason, never an overdraft. *Tests:
   Task 10 (the lock and the re-check), Task 17 (a stale card fails).*
3. **A persona switch while a card is pending.** Expect the new persona never to see or confirm
   it, and no old data in their cache. *Tests: Task 17 (404 for another person), Task 34
   (`resetIdentity` and invalidation, never `setQueryData`).*
4. **"Tomorrow" or "next Friday" asked late in the evening in Oakland** (already tomorrow in UTC).
   Expect the location's date. *Tests: Task 2 (`today_at`), Task 21 (the tools use the turn's
   `now`), Task 25 (action items).*
5. **A request that crosses a holiday, a day off, or December 31,** or a half day on a day the
   person doesn't work. Expect the right count with each skipped day's reason, or a plain
   refusal. *Tests: Tasks 3 to 5.*
6. **A manager approving a request the employee just canceled,** or approving their own. Expect a
   calm 409 or a refusal, and no write. *Tests: Task 9 (the matrix), Task 10, Task 14.*
7. **A card left open past 15 minutes.** Expect the expired state and an "Ask again", and a confirm
   refused. *Tests: Task 16, Task 33.*

---

## Decisions made while planning

**Six stages, each a pull request into `dev`.**

| Stage | Branch | Tasks | Code, not counting tests (est.) |
|---|---|---|---|
| 1 The engine | `feat/phase-5-engine` | 1–7 | about 800 |
| 2 The data and the service | `feat/phase-5-data` | 8–13 | about 1,200 |
| 3 The routes and proposals | `feat/phase-5-routes` | 14–19 | about 1,100, plus the generated client |
| 4 The assistant | `feat/phase-5-assistant` | 20–28 | about 1,400, plus datasets and fixtures |
| 5 The components | `feat/phase-5-components` | 29–32 | about 1,300 |
| 6 The pages, and closing Phase 5 | `feat/phase-5-pages` | 33–38 | about 1,300 |

Stage 4 is the closest to the 1,500-line guideline. If it passes it, the PR gets a reading guide:
the tools and the turn changes first, then the eval changes, with the datasets and fixtures
skimmed.

**Order and branches:**
- Stages 1 to 3 branch off `dev` in turn, each after the last merges. None changes what the model
  sees, so CI's offline replay stays green.
- **Stage 4** is the only stage that changes the tools, the prompt, or the handbook text, so it's
  the only one that needs a paid run, and it can't merge until its full run (early November) is
  committed.
- **Stage 5** waits for the Phase 5 screens in `docs/design/screens/`, branches off `dev` after
  Stage 3 merges (it needs only the generated client), and can run while Stage 4 waits for its
  full run.
- **Stage 6** branches off `dev` after Stages 4 and 5 merge, since its browser tests need the
  tools and the scripted scenarios.

**How each stage runs** (the way of working from Phases 1 to 4):

- **Batches.** Each stage runs in the batches named under it. After each batch I stop with a short
  report and wait for "continue".
- **One Sonnet implementer per batch.** It gets this plan's line range for its tasks, the spec,
  the design notes where they apply, and the deviations the repository forces. It writes each test
  first and reproduces the failure.
- **Reviews:**
  - Stage 2's batch A (the schema, grants, triggers, and row-level security) and Stage 3's batch B
    (the proposal service and the confirm route) each get a Sonnet compliance reviewer and an
    **Opus 5.5 security reviewer**, in parallel. The Opus reviewer is re-briefed through
    SendMessage, so it keeps its context.
  - Stage 1's engine batches get a **hand-worked check** in their combined review: the reviewer
    recomputes at least five fixtures by hand from the handbook and the spec, without running
    the engine.
  - Every other batch gets one combined Sonnet review.
- **Fixes** are written test first by a Sonnet fixer, and each new test is mutation-proved.
- **I do each stage's close myself:** the changelog, the roadmap row and its "Next" note, this
  plan's "Changes made during execution", `make db && make check`, and `/code-review medium` on the
  whole branch (with `git add -N` on new files first). I stop the review loop at the first round
  with nothing high or medium, and record the lows. Then I draft the commit and PR and wait for
  the owner's OK on each action.
- **The phase ends** with `/code-review high` on the phase's application code and one **Fable 5.1
  security reviewer**, briefed with the spec's
  [Security](../specs/2026-10-20-phase-5-time-off.md#security) seams.

**Effort for each session:** `medium` for every stage, the closes, and the phase review. `high`
only for a stubborn bug, then back.

**The live-eval rule in this phase:**
- Stages 1 to 3 make no paid calls and don't touch the prompt, the tools, the guard, the
  retrieval, or the handbook text.
- Stage 4 tries the prompt's wording with one or two smoke runs (about $0.80 each) and repeats the
  judge agreement run (about $0.40), which fit October's remaining budget. Its full run (about $9
  to $11, cap $16) waits for November's budget, and the PR waits for the full run.

## Prerequisites (owner)

- **Record the commit `dev` is at after this planning PR merges,** before Stage 1 branches. Task
  38's phase review diffs against it.
- **In Stage 4's PR:** the owner approves the handbook additions (the wording is in the spec), and
  OKs each paid run: the smokes, the agreement run, and the November full run.
- **Before Stage 5:** done. The Phase 5 screens (08 to 10) were designed and approved on 2026-10-20,
  and synced into `docs/design/screens/` in their own docs PR.
- **Docker Desktop is running,** and `make setup` and `make db` have run.

## File map

```
open-door/
├── handbook/sections/                      Stage 4  3.1, 4.1, 4.3 additions; embeddings cache
├── evals/assistant/                        Stage 4  actions.yaml (new), redteam.yaml, qa.yaml,
│                                                    smoke.yaml, judge.md, run.py, graders.py,
│                                                    datasets.py, fixtures/
├── CLAUDE.md                               Stage 4  the full run's cost line
├── docs/
│   ├── DATA-INVENTORY.md                   Stage 2  three tables and a column; 145 people
│   ├── AI-GOVERNANCE.md                    Stage 4  the proposal flow
│   └── BACKLOG.md                          Stages 2, 3, 4, 6  closed items out
├── apps/api/
│   ├── migrations/versions/0009_time_off.py        Stage 2
│   └── app/
│       ├── domain/timeoff/                 Stage 1  model, calendar, pto, sick, evaluate,
│       │                                            rules, labels, today
│       ├── db/models.py                    Stage 2  the new tables and the column
│       ├── policy/__init__.py              Stage 2  four actions, the request resource
│       ├── modules/identity/actor.py       Stage 2  direct_report_ids
│       ├── modules/sandbox/seed.py, seed_data.py   Stage 2  schedules, openings, history
│       ├── modules/audit/service.py        Stage 2  proposal_id, new actions
│       ├── modules/timeoff/                Stage 2  service.py, queries.py
│       │                                   Stage 3  routes.py, schemas.py
│       ├── ai/proposals.py                 Stage 3
│       ├── modules/assistant/              Stage 3  confirm and cancel routes; proposals in display
│       ├── ai/tools/timeoff.py, registry.py        Stage 4
│       ├── ai/prompts/, context.py, turn.py        Stage 4
│       └── ai/scripted.py, scripted_scenarios.json Stage 4
└── apps/web/src/
    ├── components/timeoff/                 Stage 5  balance card, request row, status badge,
    │                                                request form, date picker, approval row
    ├── components/assistant/confirm-card.tsx       Stage 5
    ├── app/gallery/sections/               Stage 5  the time-off and card states
    ├── features/time-off/, features/approvals/     Stage 6
    ├── features/home/, features/chat/      Stage 6  cards; the proposal event and the card
    ├── app/nav.ts, app/router.tsx          Stage 6
    └── app/use-scroll-restoration.ts       Stage 6
```

---

# Stage 1: The engine

**Branch:** `feat/phase-5-engine`, off `dev` after the planning PR merges. Record the base commit
first.

**Ends with:** `app/domain/timeoff/`, pure, with hand-worked tests for every rule in the spec's
[The engine](../specs/2026-10-20-phase-5-time-off.md#the-engine). Nothing calls it yet, and
`make check` passes.

**Batches:**
- **A** (Tasks 1–3): the types, today, the labels, and counting.
- **B** (Tasks 4–6): PTO, sick leave, and evaluating a request.
- **C** (Task 7): the close.

### Task 1: The types and the rules

**Files:** `app/domain/timeoff/model.py`, `rules.py`, `tests/test_timeoff_model.py`.

**Interface:**

```python
EmploymentType = Literal["salaried", "hourly"]
State = Literal["CA", "CO", "TX", "GA"]
LeaveType = Literal["pto", "sick"]
RequestStatus = Literal["pending", "approved", "denied", "recorded", "canceled"]
DAY_MINUTES = 480
HALF_DAY_MINUTES = 240

@dataclass(frozen=True)
class Schedule: weekdays: frozenset[int]            # ISO 1..7, non-empty
@dataclass(frozen=True)
class Person: employment_type; state; hire_date: date; schedule: Schedule
@dataclass(frozen=True)
class Opening: as_of: date; amount_minutes: int     # PTO only
@dataclass(frozen=True)
class Request: id: str; type: LeaveType; start: date; end: date;
               partial_minutes: int | None; status: RequestStatus
@dataclass(frozen=True)
class Rule: section_id: str; rule: str              # "4.1", "pto-earning"
```

- [ ] **Tests first:** a `Schedule` refuses an empty set or a weekday outside 1 to 7; a `Request`
      refuses an end before its start; `Rule` IDs come from one table (`RULES`), and every
      `section_id` in it is one of `3.1`, `4.1`, `4.2`, `4.3`, `CA-4.3`, `CO-4.3`.
- [ ] **Known:** the engine names sections by ID only. Titles and deep links are resolved by the
      service from the pinned handbook (Task 10), so the engine stays free of the database.

### Task 2: Today, and the labels

**Files:** `app/domain/timeoff/today.py`, `labels.py`, `tests/test_timeoff_today.py`,
`tests/test_timeoff_labels.py`.

**Interface:** `today_at(timezone: str, now: datetime) -> date` (refuses a naive `now`);
`label(minutes: int) -> str`.

- [ ] **Tests first:**
  - at 2026-10-16 03:00 UTC, Oakland and Austin are still on October 15 (Austin is at 22:00 on
    the 15th), and Atlanta and Denver too; at 2026-10-16 08:00 UTC every location is on the 16th
  - the labels, worked by hand: 480 is "8 hours (1 day)", 240 "4 hours (half a day)", 5,400
    "90 hours (11.25 days)", 180 "3 hours", 0 "0 hours", 60 "1 hour"
- [ ] **Known:** the label is the one string the API and the tool results share, so the model
      never divides by 8. Settle the format for fractions of a day here (quarters appear, since
      hourly earning is 8 hours and salaried 10) and pin it in the tests. Fractions below a
      quarter can't occur in PTO, but sick hours can; a sick label shows hours only.

### Task 3: Counting a request

**Files:** `app/domain/timeoff/calendar.py`, `tests/test_timeoff_calendar.py`.

**Interface:** `count_days(person, start, end, holidays: Mapping[date, str]) -> Counted` with
`counted: tuple[date, ...]` and `skipped: tuple[Skipped, ...]` (date and reason: `"not
scheduled"` or the holiday's name).

- [ ] **Tests first** (hand-worked, each with its calendar in a comment):
  - Monday to Friday over a week with a Monday holiday counts 4
  - Leo's Wednesday-to-Sunday schedule over Monday to Sunday counts 5, skipping Monday and Tuesday
    as "not scheduled"
  - Thanksgiving week 2026 in Denver (Thursday and Friday closed) counts 3 for a Monday-to-Friday
    person, and in Oakland 4
  - December 27, 2027 to January 2, 2028: Friday, December 31, 2027 is the observed New Year's
    Day, skipped by name
  - a range with no counted day returns an empty `counted`
- [ ] **Known:** the holidays come in as data; the service loads every year the range touches.
      `app/domain/holidays.py` already computes the observed dates for the seed. The engine
      takes the stored rows, not that function, so a sandbox's calendar is what it stored.

### Task 4: PTO

**Files:** `app/domain/timeoff/pto.py`, `tests/test_timeoff_pto.py`.

**Interface:** `pto_balance(person, opening, requests, today) -> PtoBalance` with
`earned_minutes`, `taken_minutes`, `booked_minutes`, `pending_minutes`, `available_minutes`,
`ceiling_minutes`, `next_earning: date | None` (None when paused at the ceiling),
`next_earning_minutes`, and `rules`.

- [ ] **Tests first** (hand-worked):
  - a salaried person with an opening of 4,800 on January 1, no requests, on October 20: nine
    month-ends (January to September) at 600 each, so earned 4,800 + 5,400 = 10,200
  - the same person at the ceiling: an opening of 10,500 earns 300 in January (to 10,800), then
    nothing until PTO is taken; after a 2-day request in March is approved and taken, the March
    month-end earns 600 again (10,800 − 960 + 600 = 10,440)
  - hourly: 480 a month, ceiling 8,640
  - a hire on June 30 earns on June 30 (the first month counts); a hire on July 1 first earns on
    July 31
  - taken, booked, and pending split by status and by date against `today`
  - denied and canceled requests count nowhere
- [ ] **Known:** the ceiling check runs at each month-end against the opening, plus earning so far,
      minus approved PTO on dates up to that month-end. Approving a request after a month-end it
      falls before changes that month's earning. That's correct (the balance is the rules
      applied), and a test shows it.

### Task 5: Sick leave

**Files:** `app/domain/timeoff/sick.py`, `tests/test_timeoff_sick.py`.

**Interface:** `sick_balance(person, requests, year, today) -> SickYear` with `granted_minutes`,
`used_minutes`, `booked_minutes`, `available_minutes`, and `rules`. `sick_years(person, requests,
today) -> tuple[SickYear, ...]`: the current year, plus next year once a request falls in it.

- [ ] **Tests first** (hand-worked):
  - Texas and Georgia grant 2,400 on January 1; Colorado 2,880; California the larger of 2,400
    and 5 scheduled days × 480 = 2,400, with CA-4.3 cited
  - a hire in the year gets the grant on the hire date
  - a request from December 30 to January 2 is split: the December days against this year, the
    January days against next year's grant
  - recorded sick time in the past is used, in the future booked; a canceled one counts nowhere
- [ ] **Known:** CO-4.3's "raised back to 48" is the grant of 48; the engine never adds a carryover
      on top (the spec says why). California's "5 of your workdays" is computed from the schedule
      times 480, so a change to day length would show up there.

### Task 6: Evaluating a request

**Files:** `app/domain/timeoff/evaluate.py`, `tests/test_timeoff_evaluate.py`.

**Interface:**

```python
def evaluate(person, opening, requests, holidays, new: NewRequest, today) -> Evaluation
# Evaluation: ok, problems: tuple[str, ...] (the spec's codes), warnings (short-notice),
#   counted, skipped, amount_minutes, available_before/after (PTO: one figure; sick: per year),
#   rules
```

- [ ] **Tests first,** one per refusal code in the spec (`no-scheduled-days`, `too-long`,
      `out-of-range` in each of its three forms, `bad-partial` in each of its forms, `overlaps`,
      `not-enough`), plus:
  - a PTO half day on a scheduled day: 240
  - sick hours: 3 hours on one day is 180; 0 or 9 hours is `bad-partial`
  - PTO of 4 counted days starting 10 days from today is accepted with `short-notice`
  - `not-enough` counts pending and booked requests against what's available
  - an overlap with a pending, approved, or recorded request refuses; with a denied or canceled
    one it doesn't
  - sick time starting 30 days back is allowed; 31 days back refuses
- [ ] **Known:** the evaluation never decides who may act. The policy layer does that (Task 9).
      The engine answers only "what would this count, and does it fit".

### Task 7: Close Stage 1

- [ ] **`CHANGELOG.md`:** "Phase 5, stage 1". **Roadmap:** the row says In progress, with the
      branch and the planning PR. **This plan:** the base commit and any deviations.
- [ ] `make db && make check`, `/code-review medium` until a round has nothing high or medium,
      then propose the commit and PR.

---

# Stage 2: The data and the service

**Branch:** `feat/phase-5-data`, off `dev` after Stage 1 merges.

**Ends with:** migration 0009, the seed's schedules, openings, and history, the four policy
actions, and the time-off service with its audit events. Nothing is reachable over HTTP yet.

**Batches:**
- **A** (Task 8): the schema. The Sonnet compliance reviewer and the Opus security reviewer.
- **B** (Tasks 9–11): the policy, the service, and the audit changes.
- **C** (Task 12): the seed.
- **D** (Task 13): the close.

### Task 8: Migration 0009 and the models

**Files:** `migrations/versions/0009_time_off.py`, `app/db/models.py`,
`tests/integration/test_grants.py`, `test_row_level_security.py`, `test_isolation.py`, a new
`tests/integration/test_time_off_tables.py`, and `docs/DATA-INVENTORY.md`.

- [ ] **Tests first:**
  - the exact-grants test lists `SELECT` and `INSERT` on `time_off_openings`; `SELECT`, `INSERT`,
    and the column `UPDATE`s on `time_off_requests` and `ai_proposals`; nothing for `od_cleanup`
  - row-level security coverage finds the three tables enabled and forced
  - **the restrictive rule on `ai_proposals`:** in one sandbox, Marcus can't read or update
    Priya's proposal, and neither can Dana
  - **the triggers:** every illegal request and proposal status change fails, a final status
    can't change, and the ungranted columns can't change at all (as `od_app_login`)
  - **the exclusion constraint:** two overlapping pending requests for one person fail; for two
    people, or with one canceled, they don't
  - a proposal can't name another person's conversation or turn (the composite keys)
  - deleting a tenant (as the cleanup login) removes every new row
  - `people.scheduled_weekdays` refuses an empty array and a value outside 1 to 7
- [ ] Write the migration in 0008's style: a docstring explaining the design, a `GRANTS` tuple,
      `ENABLE` and `FORCE ROW LEVEL SECURITY`, `tenant_isolation`, the restrictive `own_rows` on
      `ai_proposals`, the column grants and their triggers (copy 0008's `ai_turns` pattern), and
      `CREATE EXTENSION IF NOT EXISTS btree_gist`.
- [ ] Add the three tables and the column to `DATA-INVENTORY.md`: what each holds, why, who sees
      it, and how long. The denial note is user-written text, never sent to a model. Correct "120
      made-up people" to 145.
- [ ] **Known:**
  - The RLS test requires every unique index on a tenant table to start with `tenant_id`, and
    allows only the tenant rule as a permissive policy, so `own_rows` is `AS RESTRICTIVE`. Start
    the exclusion constraint with `tenant_id` too.
  - Declare the exclusion constraint in the model (`postgresql.ExcludeConstraint`) and the
    trigger-backed columns as they are, or `alembic check` reports drift.
  - `ADD COLUMN scheduled_weekdays smallint[] NOT NULL DEFAULT '{1,2,3,4,5}'` gives existing dev
    sandboxes Monday to Friday. Keep or drop the default deliberately, and say which in the
    docstring.
  - `make migrations-roundtrip` downgrades too. The downgrade leaves `btree_gist` in place, like
    0001's `vector`, and says why.

### Task 9: The policy actions

**Files:** `app/policy/__init__.py`, `app/modules/identity/actor.py`, `tests/test_policy.py`,
`tests/integration/test_actor.py`.

**Interface:** `Action.TIMEOFF_READ | TIMEOFF_REQUEST | TIMEOFF_DECIDE | TIMEOFF_CANCEL`;
`TimeOffRequestResource(person_id, type, status, start_date)`; `Actor.direct_report_ids`;
`can(actor, action, resource, *, today: date | None = None)`.

- [ ] **Tests first:** the matrix gains a row per action and relationship: self, another employee,
      a direct manager, a manager two levels up, and HR. In particular:
  - Marcus decides Priya's pending PTO; the COO (two levels up) can read it but not decide it;
    Dana reads but doesn't decide; and Priya can't decide a request of Priya's own
  - nobody decides a sick record, or a request that isn't pending
  - Priya cancels an approved PTO request the day before its first day, not on it
  - `load_actor` returns Marcus's 5 direct reports and 44 in all
- [ ] **Known:** `RULES` maps an action to `Callable[[Actor, PersonResource], bool]` today. Widen
      it to the two resource types without loosening deny-by-default. The matrix test's
      every-action check (`set(MATRIX) == set(Action)`) makes a missing row fail.

### Task 10: The time-off service

**Files:** `app/modules/timeoff/service.py`, `queries.py`, `tests/integration/test_timeoff_service.py`.

**Interface:**

```python
async def balances(db, actor, person_id, now) -> Balances
async def check(db, actor, new: NewRequest, now) -> Evaluation
async def create(db, actor, new: NewRequest, now, *, via, proposal_id=None) -> Created | Refused
async def decide(db, actor, request_id, decision, note, now, *, via, proposal_id=None) -> ...
async def cancel(db, actor, request_id, now, *, via, proposal_id=None) -> ...
def resolve_rules(rules, version_id) -> tuple[RuleRef, ...]   # title and deep link
```

- [ ] **Tests first:**
  - **the lock:** two concurrent `create`s that each fit but not together: one succeeds, and the
    other is refused `not-enough` (two sessions, a barrier)
  - `create` of PTO is `pending`, of sick time `recorded`, each with its audit event
  - `decide` and `cancel` re-check the policy and the status under the lock; deciding a request
    canceled a moment earlier is refused, not written
  - the exclusion constraint's error becomes `overlaps`, never a 500
  - `balances` for a report, as their manager, matches a hand-worked figure from the seeded rows
  - every rule resolves to a section in the sandbox's pinned handbook; a missing one fails the
    test
- [ ] **Known:**
  - The lock is `pg_advisory_xact_lock` on a key derived from the tenant and the person, taken
    before any read, so it lasts the transaction and is safe behind a pooler (as ADR 0011's).
  - "Today" is `today_at(location.timezone, now)`; `now` is passed in, never read inside, so the
    evals' fixed NOW reaches the engine.
  - Load holidays for every year the range touches, plus the year before (New Year's observed on
    December 31).

### Task 11: The audit changes

**Files:** `app/modules/audit/service.py`, `tests/integration/test_audit.py`.

- [ ] **Tests first:** `record_event` writes `proposal_id`; the new `AuditAction` values exist; a
      decision's `before` and `after` hold status, type, and dates, and never the note.
- [ ] **Known:** `record_event` already refuses private field names in `before` and `after`. Add
      `decision_note` to the refused names, so a note can never be logged by mistake.

### Task 12: The seed

**Files:** `app/modules/sandbox/seed.py`, `seed_data.py`, `tests/test_seed.py`,
`tests/integration/test_seeding.py`.

- [ ] **Tests first:**
  - every person has a schedule, per the spec's patterns; the personas' are exact (Leo Wednesday
    to Sunday, the others Monday to Friday)
  - every person has one opening, below their ceiling, as of January 1 of the anchor year or
    their hire date
  - Leo has approved PTO from Wednesday to Friday of the week before the anchor's week
  - Marcus's queue has exactly one pending request, from a direct report who isn't Priya, about
    three weeks after the anchor
  - no seeded request overlaps another, or falls before its person's opening or after the anchor
    (except the pending one)
  - holidays cover the year before the anchor, the anchor year, and the next (update the
    expected counts)
  - the existing people, IDs, and private details are unchanged (the new draws use their own
    random stream)
  - seeding stays under 2 seconds at p95
- [ ] **Known:**
  - `insert_company` writes with `INSERT ... SELECT FROM unnest(arrays)`. `unnest` flattens an
    array of arrays into one column of elements, so schedules can't be passed as `smallint[][]`.
    Pass each schedule as a text literal (`'{3,4,5,6,7}'`) and cast it, or another shape that
    keeps one row per person.
  - Request IDs are `uuid5(tenant_id, f"timeoff:{key}")`, like the other seeded IDs, so the eval
    sandbox's repeat.
  - A sandbox made in early January has almost no history this year; that's fine. The tests
    cover an anchor of January 2.

### Task 13: Close Stage 2

- [ ] `CHANGELOG.md` "Phase 5, stage 2"; roadmap; this plan's notes; `docs/BACKLOG.md`: remove "Seed
      last year's holidays", "Never treat the anchor date as today", "Grant `UPDATE` only where
      requests and approvals need it", and "Record who confirms a proposal" moves to Stage 3's
      close when the confirm route writes it.
- [ ] `make db && make check`, `/code-review medium`, then propose the commit and PR.

---

# Stage 3: The routes and proposals

**Branch:** `feat/phase-5-routes`, off `dev` after Stage 2 merges.

**Ends with:** the time-off routes, the proposal service, the confirm and cancel routes, proposals
in `GET /conversations/current`, and the regenerated web client. No tool makes a proposal yet:
the tests insert them through the service.

**Batches:**
- **A** (Tasks 14–15): the time-off routes and the summary.
- **B** (Tasks 16–17): the proposal service and its routes. The Sonnet compliance reviewer and the
  Opus security reviewer.
- **C** (Task 18): proposals in the conversation display, and the client.
- **D** (Task 19): the close.

### Task 14: The time-off routes

**Files:** `app/modules/timeoff/routes.py`, `schemas.py`, `app/api/v1/router.py`,
`tests/integration/test_timeoff_routes.py`.

- [ ] **Tests first,** for each route in the spec's table:
  - the session (401) and CSRF (403) on writes
  - 404, never 403, for a request or person the caller can't read
  - every engine refusal as a 422 problem with its code and plain text
  - a decision on a request that's no longer pending is a 409
  - `scope=waiting` returns only pending PTO from direct reports; `scope=team` everyone below
  - the default window and the 200-row limit
  - team coverage on `GET /requests/{id}` and on each `scope=waiting` row, for its direct manager
    only, counting approved and recorded time off (a waiting request doesn't count)
  - `GET /time-off/calendar`: the caller's scheduled weekdays, the location's holidays with names
    (across a year boundary), and the earliest day per type (today for PTO, 30 days back for sick)
- [ ] **Known:** follow `people/routes.py`: `SignedInDep`, `authorize()`, `problem_responses`. Every
      response carries both `amountMinutes` and its label.

### Task 15: The summary

**Files:** `app/modules/timeoff/routes.py`, `tests/integration/test_timeoff_routes.py`.

- [ ] **Tests first:** `GET /time-off/summary` gives PTO available (minutes and label), the
      caller's pending count, and for a manager the waiting count; an employee's has no waiting
      count.

### Task 16: The proposal service

**Files:** `app/ai/proposals.py`, `tests/integration/test_proposals.py`.

**Interface:**

```python
async def create_proposal(engine, ctx, *, conversation_id, turn_id, action, payload, card) -> ProposalRef
async def cancel_turn_proposals(engine, ctx, turn_id, reason) -> None
async def confirm(db, actor, proposal_id, note, now) -> ProposalOut   # raises Conflict(status)
async def cancel(db, actor, proposal_id) -> ProposalOut
def status_as_of(row, now) -> ProposalStatus                          # "expired" past expires_at
def outcomes_since(rows, since) -> tuple[str, ...]                    # Task 22's context lines
```

- [ ] **Tests first:**
  - a new proposal cancels a pending one in the same conversation ("replaced")
  - `status_as_of` shows expired after 15 minutes; `confirm` then marks it expired and refuses
  - `confirm` runs the stored payload through the service: executed with the request's ID, or
    failed with the engine's code and text; both write `proposal.confirmed` or `proposal.failed`
    plus the action's own event with the `proposal_id`
  - a confirm while the proposal's turn is `running` is refused `turn-running`
  - `cancel_turn_proposals` cancels only that turn's pending proposals
  - `outcomes_since` lines are made from structured fields only (a test feeds a payload with
    instruction-like text in a person's name and checks it can't reach the line; names come from
    the directory, never a note)
- [ ] **Known:** the decision's optional note is the only thing the confirm takes from the client.
      It's at most 300 characters and stored on the request, never in the proposal's payload or
      outcome.

### Task 17: The confirm and cancel routes

**Files:** `app/modules/assistant/routes.py`, `schemas.py`,
`tests/integration/test_proposal_routes.py`.

- [ ] **Tests first:**
  - `POST /assistant/proposals/{id}/confirm` and `/cancel`: CSRF; 404 for another person's
    proposal (a second persona in the same sandbox); 409 with the current status when it isn't
    pending; 409 `turn-running`
  - **two concurrent confirms** (two connections, a barrier): one executes, the other gets 409
    `executed`, and exactly one request exists
  - a stale card (the balance changed after it was made) fails with `not-enough` and its text
  - after a persona switch, the old persona's proposal is a 404 for the new one
- [ ] **Known:** the route locks the row with `SELECT … FOR UPDATE` inside the request's own
      transaction, then calls the service, which takes the per-person lock. Take the locks in
      that order everywhere, or two confirms can deadlock.

### Task 18: Proposals in the conversation display, and the client

**Files:** `app/modules/assistant/display.py`, `schemas.py`, `apps/web/openapi.json`,
`apps/web/src/api/generated.ts`, `tests/integration/test_assistant_routes.py`.

- [ ] **Tests first:** `GET /conversations/current` gives each turn its proposals, each with the
      status as of the read and its card. A proposal made in another conversation never appears.
- [ ] `make openapi`. The web app compiles against the new client; nothing in it uses the new
      routes yet.

### Task 19: Close Stage 3

- [ ] `CHANGELOG.md` "Phase 5, stage 3"; roadmap; this plan's notes; `docs/BACKLOG.md`: remove
      "Record who confirms a proposal as an audit event of its own".
- [ ] `make db && make check`, `/code-review medium`, then propose the commit and PR.

---

# Stage 4: The assistant

**Branch:** `feat/phase-5-assistant`, off `dev` after Stage 3 merges.

**Ends with:** the six tools, the new prompt and tool-set versions, the `proposal` event, the
per-turn context's outcomes, the scripted scenarios, the handbook additions, the action eval and
the other eval changes, and a committed full run. The PR waits for the full run.

**Batches:**
- **A** (Tasks 20–21): the eval harness fixes and the tools.
- **B** (Tasks 22–23): the turn and the scripted model.
- **C** (Tasks 24–25): the handbook additions and the evals.
- **D** (Tasks 26–27): the prompt's wording with smoke runs, and the full run (with the owner).
- **E** (Task 28): the close.

### Task 20: The trial-1 save gate, and graders for every tool

**Files:** `evals/assistant/run.py`, `graders.py`, `tests/evals/`.

- [ ] **Tests first:**
  - a fresh run that stops in trial 2 still saves (and prunes against) trial 1's complete
    recordings; one that stops in trial 1 saves nothing, as now
  - `_tool_problems` checks each call with its own tool's parser; an unknown name is a problem,
    never a handbook search
  - `_schema_problems` handles booleans, integers, nullable types, and dates
- [ ] **Known:** the gate is `_save_recordings` and `_ran_everything` calling `_all_items_ran()`
      across every trial (backlog). Only trial 1 is ever recorded, so gate both on trial 1 alone.
      Do this first: Task 27's full run depends on it.

### Task 21: The six tools

**Files:** `app/ai/tools/timeoff.py`, `base.py`, `registry.py`, `app/ai/prompts/versions.py`,
`tests/test_tool_registry.py`, `tests/integration/test_timeoff_tools.py`.

- [ ] **Tests first:**
  - each tool's schema is strict and passes the registry tests; the person-input ban has exactly
    two named exceptions (`person_name` on the balance and request tools); the optional-property
    limit is raised with its reason (under 16 of the API's 24)
  - `person_name` matches only people the actor may read: Priya asking for Leo's balance gets a
    tool error that names no one Priya can't read; an ambiguous name lists the matches' names and
    titles
  - `check_time_off` writes nothing (row counts before and after)
  - each proposal tool writes one proposal and `proposal.created`, and nothing else; a refusal
    writes nothing
  - **no tool result holds a random ID or a note:** a test scans every tool's result over the
    seeded sandbox for UUIDs that aren't seeded request IDs, and for a denial note seeded for the
    purpose
  - the decision tool's result never holds team coverage
  - `TOOLSET_VERSION` is `2026-11.1`, and the golden-hash table gains its row (rows are only ever
    added)
- [ ] **Known:**
  - `ToolContext` gains `now`, set from the turn; the tools compute today from it.
  - Strict schemas reject `minimum` and `maximum`; `hours`' range lives in the description and the
    pydantic model.
  - A proposal tool needs the turn and conversation IDs: add them to `ToolContext` too.

### Task 22: The turn: the `proposal` event, and outcomes in the context

**Files:** `app/ai/turn.py`, `context.py`, `app/modules/assistant/routes.py` (the SSE event list),
`tests/test_context.py`, `tests/integration/test_turn_proposals.py`.

- [ ] **Tests first:**
  - a proposal tool's run emits `proposal` after its `tool.finished`, with the spec's shape
  - a turn that's stopped, fails, hits its deadline, or stores only its question cancels its
    proposals; `recover_abandoned` cancels an abandoned turn's
  - the next turn's per-turn context carries one line per proposal that changed since the last
    turn, and none when nothing changed
  - a sensitive turn can still propose, and the HR panel still follows
- [ ] **Known:** the cancel goes inside the shielded `finish()` (10-second `CLEANUP_TIMEOUT`), in
      its own transaction, after `finish_turn`. The context line is part of the stored `system`
      message, so it's replayed exactly; never rebuild it for an old turn.

### Task 23: The scripted model

**Files:** `app/ai/scripted.py`, `scripted_scenarios.json`, `tests/test_scripted.py`,
`tests/integration/test_scripted_proposals.py`.

- [ ] **Tests first:** each new scenario in the spec calls the real tools and produces its card:
      "book next Friday" (the date worked out from the per-turn context's "Today:" line), "I'm
      sick tomorrow", "what's my balance", "anything waiting on me", "approve it", "deny it", and
      "cancel my request".
- [ ] **Known:** the scripted model sees the per-turn context as the last `system` message
      (`Today: <Weekday>, <ISO date> (<timezone>)`); parse it there, never from a clock. Scenarios
      chain two tool rounds ("anything waiting" then a decision needs a request ID), so
      `_is_second_call` grows into a small per-scenario step count.

### Task 24: The handbook additions

**Files:** `handbook/sections/3.1-schedules-and-timekeeping.md`, `4.1-paid-time-off.md`,
`4.3-sick-leave.md`, `handbook/handbook.yaml` (the version), `handbook/embeddings/`,
`evals/retrieval/` if a label moves.

- [ ] Add the spec's sentences word for word, the new source line in §4.3, and today's `updated`
      dates. `make ingest`, `make embed` (a fraction of a cent, needs `VOYAGE_API_KEY`), commit
      the cache, and `make eval-retrieval` stays at 100% at 5.
- [ ] **Known:** a new sandbox pins the newest published version; existing ones keep theirs. The
      engine's rules cite section IDs that both versions have.

### Task 25: The evals

**Files:** `evals/assistant/actions.yaml` (new), `redteam.yaml`, `qa.yaml`, `smoke.yaml`,
`judge.md`, `datasets.py`, `graders.py`, `run.py`, `evals/README.md`.

- [ ] **Tests first** (offline, on hand-made traces):
  - the action graders: the expected proposal tool and payload (with alternatives), "no write"
    (request rows before and after the turn), at most one proposal, and **numbers match the
    engine** (every days or hours figure in the text equals a label or figure in that turn's tool
    results; "8 hours (1 day)" and "1 day" both match)
  - the judge gets the non-handbook tool results and the turn's date, and the rubric's new line
    says a tool's figure isn't a policy claim; `JUDGE_VERSION` moves
- [ ] Write about 30 action items, about 8 red-team items, and a few Q&A items, in employees' and
      managers' own words, before any tuning. The owner reviews them in the PR. The smoke set
      gains about 6 action items.
- [ ] The eval sandbox's `ANCHOR_DATE` becomes `NOW`'s date, and the harness adds its own requests
      after the seed (the spec's list), with derived IDs.
- [ ] **Known:** "next Friday" asked on Thursday, October 15 could mean the 16th or the 23rd; such
      items list both readings, or accept a clarifying question. Write the dates out in each item's
      comment.

### Task 26: The prompt, with smoke runs

**Files:** `app/ai/prompts/assistant.md`, `versions.py`, `tests/test_prompts.py`.

- [ ] Make the spec's prompt changes; `PROMPT_VERSION` moves and the golden table gains its row.
      The pinned-phrase tests change with it ("You can't book" goes; the proposal and date rules
      come in).
- [ ] With the owner's OK for each spend: one or two smoke runs (`make eval-live YES=1`, about
      $0.80, cap $2), and the judge agreement run (about $0.40, cap $1). Record each in this
      plan's notes.

### Task 27: The full run (November, with the owner)

- [ ] With the owner's OK: `make eval-live SET=full FRESH=1 PRUNE=1 YES=1` (cap $16). It must
      pass `--check`; the action set at 95% or more over three trials, numbers-match at 100% in
      every trial, and the red team at 100% in every trial. Commit the recordings, switch CI's
      offline replay to them, and update `CLAUDE.md`'s full-run cost line with the measured cost.
      The scoreboard goes in the PR description.

### Task 28: Close Stage 4

- [ ] `CHANGELOG.md` "Phase 5, stage 4"; roadmap; this plan's notes; `docs/AI-GOVERNANCE.md`: the
      proposal flow; `docs/BACKLOG.md`: remove the trial-1 gate item, and the judge's tool-facts
      item from Phase 7's list.
- [ ] `make db && make check` (including `make eval-offline` on the new recordings),
      `/code-review medium`, then propose the commit and PR.

---

# Stage 5: The components

**Branch:** `feat/phase-5-components`, off `dev` after Stage 3 merges and once the Phase 5 screens
are in `docs/design/screens/`.

**Ends with:** every Phase 5 component in every state from the screens' notes, in the gallery,
against the generated client's types. No page uses them yet.

**Batches:**
- **A** (Tasks 29–30): fill the acceptance-criteria table below with the owner; the form fields,
  status badges, and date picker.
- **B** (Task 31): the time-off components and the confirm card.
- **C** (Task 32): the gallery, the browser tests, and the close.

### Task 29: The acceptance criteria

- [ ] At the stage's start, fill [Self-review: acceptance criteria to tasks](#self-review-acceptance-criteria-to-tasks)
      from the screens' `notes.md`, and get the owner's approval, as in Phase 4's Stage 5.

### Task 30: The form fields, status badges, and the date picker

**Files:** `apps/web/src/components/ui/` (labeled field, radio group or segmented control as the
design has it), `components/timeoff/status-badge.tsx`, `date-picker.tsx`, their tests.

- [ ] **Tests first:** every state in the notes; the picker marks unscheduled days and holidays,
      disables past days for PTO, and is usable by keyboard alone; status badges pair color with
      text.
- [ ] **Known:**
  - `new Date("2026-10-23")` is midnight UTC, which renders as October 22 in Pacific time. Treat
    leave dates as plain `YYYY-MM-DD` strings, and format them with `Intl.DateTimeFormat` and
    `timeZone: "UTC"`. A test renders a date under `TZ=America/Los_Angeles`.
  - If the design's picker needs a library, choose one here (small, maintained, accessible), and
    record why.

### Task 31: The time-off components and the confirm card

**Files:** `components/timeoff/` (balance card, request row, request form with its live preview,
approval row with coverage), `components/assistant/confirm-card.tsx`, their tests.

- [ ] **Tests first:** the confirm card in each variant (request, decision, cancel) and state
      (pending with Confirm, Cancel, and the expiry; executed; failed with the reason; canceled;
      expired), with "Proposed by the AI. Nothing happens until you confirm." and Confirm disabled
      while its turn is running; the form shows the preview's counted and skipped days and the
      warning; every figure is the API's label.

### Task 32: The gallery, and close Stage 5

- [ ] The gallery's time-off and card sections, a browser test per gallery state, axe clean,
      nothing sideways at 390 px. The capture comparison against the screens, checked by me first
      (every state, 1440 and 390 px, hover and focus) before the owner looks.
- [ ] `CHANGELOG.md` "Phase 5, stage 5"; roadmap; `make check`; `/code-review medium`; propose the
      commit and PR.

---

# Stage 6: The pages, and closing Phase 5

**Branch:** `feat/phase-5-pages`, off `dev` after Stages 4 and 5 merge.

**Ends with:** `/time-off`, `/approvals`, the home's cards, the confirm card in chat, the browser
tests for the employee-to-manager flow, the captures, and the phase review.

**Batches:**
- **A** (Tasks 33–34): the chat's `proposal` event and card, and the time-off hooks.
- **B** (Tasks 35–36): the two pages, the nav, the home, and scroll restoration.
- **C** (Task 37): the browser tests and the captures.
- **D** (Task 38): the close and the phase review.

### Task 33: The `proposal` event and the card in chat

**Files:** `apps/web/src/lib/stream-turn.ts`, `features/chat/store.ts`, `features/chat/`
(the message list), their tests.

- [ ] **Tests first:** `proposal` joins the stream client's allow-list and the store's events; the
      card appears under its message; Confirm and Cancel call the routes and then invalidate; a
      409 shows the card's current state calmly; a reload shows each card's stored state; an
      expired card offers "Ask again".

### Task 34: The time-off hooks, and identity

**Files:** `features/time-off/use-time-off.ts`, `lib/identity.ts` if needed, tests.

- [ ] **Tests first:** every write invalidates the time-off queries and the conversation and never
      calls `setQueryData`; a write that finishes after a persona switch leaves nothing in the new
      cache (the backlog's item).

### Task 35: The pages

**Files:** `features/time-off/`, `features/approvals/`, `app/router.tsx`, `app/nav.ts`, tests.

- [ ] **Tests first:** each page in every state in the notes; Time off and Approvals become
      available; Approvals shows for managers only, with "Approvals, N waiting"; a switch from
      Marcus to Priya hides it (the backlog's `navFor` item, and the shell's switch test).

### Task 36: The home, and scroll restoration

**Files:** `features/home/`, `app/use-scroll-restoration.ts`, `features/chat/source-url.ts`, tests.

- [ ] **Tests first:** the at-a-glance cards from `GET /time-off/summary`; a navigation marked in
      history state as opening a panel keeps the scroll for push, replace, and Back, and the
      `?source=` special case is gone (the backlog's item).
- [ ] Take the backlog's conversation-page glitches if this stage's changes touch them, with
      browser tests; otherwise leave them in the backlog.

### Task 37: Browser tests and captures

**Files:** `apps/web/e2e/time-off.spec.ts`, `approvals.spec.ts`, `proposals.spec.ts`, the capture
config.

- [ ] One test per acceptance criterion, named after it. The flow both ways: Priya books in chat
      and Marcus approves on the page; Priya books on the page and Marcus approves in chat. A
      card that expires (a short expiry in the test settings). 390 px on each state. axe clean.
- [ ] `make captures`; I check every state first, then the owner reviews.
- [ ] **Known:** locally, Playwright can reuse a stale server (the backlog's note). Stop old servers
      or run with `CI=1`.

### Task 38: Close Stage 6 and Phase 5

- [ ] `CHANGELOG.md` "Phase 5, stage 6"; `docs/BACKLOG.md`: the remaining Phase 5 items closed or
      moved with a reason; roadmap.
- [ ] `make check`, the owner's capture review, `/code-review medium`, then propose the commit and
      PR.
- [ ] **After it merges, review the whole phase:** `/code-review high` on `dev` against the commit
      recorded before Stage 1, limited to the code that counts toward the PR-size guideline:
      `apps/api/app`, `apps/api/migrations`, `apps/api/scripts`, `apps/api/pyproject.toml`,
      `evals/assistant/run.py`, `graders.py`, and `datasets.py`, `apps/web/src` minus
      `api/generated.ts`, the `Makefile`, and `.github`.
- [ ] **The security review:** one **Fable 5.1** reviewer, briefed with the invariants and the
      spec's Security seams, proving each finding with the smallest experiment that shows it.
- [ ] Fix real findings in a small follow-up PR, and backlog the rest. Mark the roadmap row Done,
      and set the "Next" note to the release, then Phase 6 planning at effort `high`.

---

## Phase 5 is done when

- [ ] The engine's tests cover every rule in the spec with hand-worked fixtures, and a reviewer
      recomputed a sample by hand.
- [ ] The action eval passes 95% or more over three trials, numbers-match is 100% in every trial,
      and the red team is 100% in every trial; offline replay passes in CI.
- [ ] The proposal tests prove the binding, the expiry, re-validation, exactly-once execution
      under concurrent confirms, and that a turn writes only proposals.
- [ ] The employee-to-manager flow passes in the browser both ways.
- [ ] Every acceptance criterion in the Phase 5 screens' notes has a passing test, axe is clean,
      and nothing scrolls sideways at 390 px.
- [ ] The owner has approved the handbook additions, the eval items, the gallery, and the capture
      report.
- [ ] Every Phase 5 item in `docs/BACKLOG.md` is closed or moved, with its reason.
- [ ] The phase review's and the security review's real findings are fixed.

## Self-review: spec to tasks

| Spec section | Tasks |
|---|---|
| The handbook additions | 24 |
| The engine (inputs, counting, PTO, sick, rules, labels, tests) | 1–6 |
| Data model (tables, triggers, exclusion, grants) | 8 |
| The seed | 12 |
| Who can do what | 9 |
| The time-off service and routes | 10, 14, 15 |
| Audit events | 11, 16 |
| Proposals (lifecycle, expiry, confirm, the event, outcomes) | 16, 17, 18, 22 |
| The assistant (tools, prompt, scripted model) | 21, 22, 23, 26 |
| The pages | 33–36 |
| Evals (action set, set changes, runs, budget) | 20, 25, 26, 27 |
| Security | Stage 2 batch A and Stage 3 batch B reviews, 38 |
| Testing | every task's tests; 37 |
| Docs and housekeeping | 8, 13, 19, 28, 38 |

## Self-review: acceptance criteria to tasks

Filled at Stage 5's start (Task 29) from the Phase 5 screens' `notes.md`, and approved by the
owner.

| Criterion | Task |
|---|---|
| (filled in Task 29) | - |

## Changes made during execution

Record here anything that differs from this plan, with the reason, each stage's final test counts,
and the commit `dev` was at before Stage 1 (the phase review's base).

## Backlog

Deferrals found during execution go in `docs/BACKLOG.md` under the phase that should pick them up,
not here.
