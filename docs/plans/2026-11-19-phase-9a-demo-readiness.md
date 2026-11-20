# Phase 9a: Demo Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use
> checkbox (`- [ ]`) syntax for tracking. **Project rule:** never create the branch, commit, push,
> or open a PR without James's explicit OK for that one action (`CLAUDE.md`, "Git: hard rule").
> Every step that starts with **Stop:** waits for him.

**Goal:** Open Door is ready to deploy as a public, no-sign-up demo under a hard monthly AI budget.
Every change the portfolio deployment design lists for Open Door is built and proven on James's
machine with Docker, with no paid AI call and nothing deployed.

**Architecture:** The insert-only ledger (ADR 0011) gains a monthly budget, paced by UTC day under
the existing day lock. Known-unbilled API failures settle to $0, and every provider limit becomes
the friendly spend-limit stop. Refusals and a public, cached availability flag point visitors to
the recorded walkthrough. The image gets one entrypoint per job (serve, setup, cleanup), the
database setup is proven on the shared server's role layout, AI-written text carries a
machine-readable mark (EU AI Act, Article 50(2)), and a new `docs/DEPLOY.md` becomes the contract
that the AWS foundation (the master plan's Phase 2) copies into CDK.

**Tech stack:** as Phase 8: FastAPI, SQLAlchemy 2 (async), Alembic, Postgres 17 with pgvector, the
Anthropic SDK 1.13 on httpx2, React 19 with TanStack Query and the Orval client, Vitest, Playwright,
and Docker. No new dependency.

**Spec:** `/Users/jameslittlefield/Documents/github_things/portfolio-infra/docs/design/2026-11-18-portfolio-apps-aws-deployment-design.md`
(v2.1). It lives outside this repository, so it is written as a path, not a link, and
`make check-docs` stays green. Sections 5.1, 5.2, 5.3, 5.4 (Open Door), 5.10 (the items that touch
this repository), and 10 apply. The master plan is
`/Users/jameslittlefield/Documents/github_things/portfolio-infra/PLAN.md`; this plan is its Phase 1
for Open Door, and the first part of Open Door's own Phase 9.

**Session effort:** `medium` for every task (`CLAUDE.md`, "Effort level"), `high` only while a
stubborn bug is being found. Say the level in one line at the start of each session.

---

## Global constraints

Every task's requirements include these.

- **The seven invariants** (`CLAUDE.md`, "Invariants"). Above all: a budget stop that comes before
  the safety check shows a fixed text with 911 and 988, and the assistant always says it is an AI.
- **No paid AI call anywhere** (James, 2026-11-18: "no expensive paid runs"). Tests use the scripted
  and replay transports and the recorded fixtures. Never run `make eval-live`, `make live-check
  YES=1`, `make walkthrough YES=1`, `make embed`, or `make prod-local` in serve mode. The free
  paths are `make prod-local-check`, `make live-check DRY_RUN=1`, and `make load`.
- **The stale-card fix ships without its paid runs.** The full eval run for prompt version
  2026-11.5 and the walkthrough re-take are waived for this launch (spec section 10, item 1). Never
  re-record a fixture with a paid call.
- **Git:** work on one branch off `dev`. Local `main` is 104 commits behind `origin/main` and is
  never used, not even as a diff base. Every branch creation, commit, push, and PR waits for
  James's OK, one action at a time.
- **Writing:** American English, and no em dashes anywhere (`make check-docs` fails on both).
  Commit subjects are one plain imperative sentence of at most 72 characters (`CLAUDE.md`,
  "Writing").
- **Fixed texts** change only with James's approval, a new approval date, and a new SHA-256 in
  `app/ai/fixed_texts.py`.
- **Money is `Decimal`,** to the ledgers' six places. A reservation is made before every model
  attempt; a settle never fails a call that was already paid for.
- **Nothing the model reads changes, except in Task 7.** `make eval-offline` stays green after
  every other task, unchanged.
- **Production refuses every test value,** as today, and now also refuses a missing monthly budget.
- **`CHANGELOG.md` in the same edit as the change,** under Added, Changed, Fixed, or Security, each
  entry tagged "(Phase 9a)". `docs/DATA-INVENTORY.md` stays current. Decisions get ADRs.
- **PR size:** about 1,500 lines of reviewable code (application code, migrations, scripts,
  config) per PR (`CLAUDE.md`, "Reviews and pull requests"). Tests, generated files, and docs don't
  count.

## Shared names and values

These names are fixed for this plan and for the master plan. The values in the last column go into
`docs/DEPLOY.md` (Task 11) as production's.

| Setting | Code default | Production |
|---|---|---|
| `AI_MONTHLY_BUDGET_USD` (new) | unset: no monthly budget | `20`; `0` turns live AI off |
| `AI_PACING_MULTIPLIER` (new) | `3` | `3` |
| `AI_DAILY_FLOOR_USD` (new) | `1.00` | `1.00` |
| `AI_DAILY_BUDGET_USD` (a hard daily ceiling) | `3.00` | `20` (equal to the month, so pacing alone governs) |
| `AI_SANDBOX_BUDGET_USD` | `1.00` | `0.50` |
| `SANDBOX_STARTS_PER_HOUR` | `15` (was 5) | `15` |
| `SANDBOX_STARTS_PER_DAY` | `50` (was 20) | `50` |
| `SANDBOX_STARTS_DAILY_TOTAL` | `1000` (was 500) | `1000` |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`, `SANDBOX_IP_HASH_KEY` | unchanged | real values, Phase 3 |
| `FORWARDED_ALLOW_IPS` | empty | the VPC CIDR, Phase 2 |

**Pacing,** with UTC days and months:

```
left_this_month = budget - (every ledger row dated earlier this month: settled costs and open reservations)
allowance_today = min(left_this_month, max(multiplier x left_this_month / days_left_including_today, floor))
admit a reservation if today's rows + reservation <= min(allowance_today, AI_DAILY_BUDGET_USD)
```

## Decisions made while planning

The spec left these open. Each is the plan's choice; James can change any of them at the Task 1
review.

1. **`AI_MONTHLY_BUDGET_USD` has no code default.** Unset means no monthly budget, as in
   development, CI, and every test harness today, which set `AI_DAILY_BUDGET_USD=1000` to mean "no
   limit" in eight places (`playwright.config.ts:83`, `scripts/image/container.py:120`,
   `scripts/load/drive.py:334-339`, and others). Production refuses to start without it, and `0`
   means live AI off. `make prod-local` sets it to `20`.
2. **`AI_DAILY_BUDGET_USD` keeps its type and its $3 default.** Production sets it to the monthly
   budget, so pacing alone governs there, and the paid local runs keep using it as their cap
   (`scripts/prod-local/start.py:163`, `live_check.py:121`, `scripts/walkthrough/record.py:208`).
3. **`AI_SANDBOX_BUDGET_USD` keeps its $1.00 code default** for development and tests; production
   and `make prod-local` set `0.50`.
4. **No sweeper.** The ledger is insert-only: a reservation that is never settled already counts at
   its full amount forever (`app/ai/budget.py:5-7`), which is what a sweeper produces elsewhere.
5. **A plain 429 (`rate_limit_error`) also settles to $0.** Anthropic doesn't bill a rate-limited
   request; the spec's list named only the spend-limit 429.
6. **"Overloaded before any output" means an HTTP 529,** or any error status whose type is
   `overloaded_error`. An `overloaded_error` event inside a 200 stream keeps the reservation, since
   output may have been billed.
7. **SDK retries are off for every call** (spec 5.2), with **one app-level retry per turn** for an
   unbilled 429 or 529 on the assistant's call, after 1 second, under its own reservation. Today the
   SDK retries twice under one reservation (`app/ai/anthropic_transport.py:76, 284-297`).
8. **The spend-limit 400 is matched by one pattern** covering the plain, workspace, and
   organization messages. The 429's code is read from `error.details.error_code`, then from
   `error.error_code`. The implementer confirms the organization message's exact words on
   Anthropic's errors page (a free read) and records the source and date in a comment.
9. **The daily text drops "Please try again tomorrow."** It is also shown for the Anthropic spend
   limit, a used-up month, and live AI turned off, where "tomorrow" is false. `Retry-After` is sent
   only when the month still has room for the question.
10. **The public flag** is `GET /api/v1/assistant/availability`, answering `{"available": bool}`:
    true when today's room is at least $0.25 (a test proves a first question fits under it). It is
    cached for 30 seconds in each process and sent with `Cache-Control: public, max-age=30`. The
    page fails open: if the flag can't be read, the tour button shows.
11. **The landing, when live AI is unavailable,** replaces the tour button and its Turnstile slot
    with the walkthrough as the action, and adds one note. The persona cards stay, because the
    non-AI app still works. There is no Claude Design round: it is a state of screen 01 built from
    existing parts, and James sees a screenshot at the copy stop and can ask for one.
12. **`SANDBOX_STARTS_DAILY_TOTAL` rises to 1,000** (20 addresses at 50 a day), and the code
    defaults become 15, 50, and 1,000.
13. **CI's offline replay stays green by replaying under the recorded prompt.** An archived copy of
    the 2026-11.4 prompt, checked against its golden hash, stands in for the system prompt in
    offline mode only. Every eval item is one turn in a new conversation, so the patch's change to
    the "Since the last message" line reaches none of them (`docs/BACKLOG.md:222-223`).
14. **One entrypoint per job:** `/app/setup.sh` and `/app/cleanup.sh`. `/app/entrypoint.sh` now
    refuses any command (exit 64) instead of silently serving the API.
15. **`make prod-local` mirrors the shared server's database layout:** an init superuser, a
    non-superuser owner with `CREATEROLE`, `vector` pre-created, `CONNECT` revoked from `PUBLIC`.
    The setup runs twice, the cleanup runs as its own container, and every container runs with
    production's memory limit and hardened flags (read-only root, tmpfs `/tmp`, all capabilities
    dropped, `no-new-privileges`).
16. **`CONNECT` belongs to the roles, not the logins:** migration 0020 revokes it from `PUBLIC` and
    grants it to `od_app` and `od_cleanup`, which the logins inherit. The bootstrap refuses when
    either role has a member other than the configured logins, ignoring the owner running it
    (Postgres 16 and later give a `CREATEROLE` creator an admin membership in each role it
    creates).
17. **The Article 50(2) mark** is an `aiGenerated` object on stored answers (`TurnOut`) and on
    written case summaries (`CaseSummaryOut`), `"aiGenerated": true` on the stream's
    `turn.started`, and `data-ai-generated="true"` on the page wherever model text shows (answers,
    the case summary, the walkthrough transcript). It gets its own ADR, 0024.
18. **The retention and processors line goes in the public pages' footer:** Open Door has no
    privacy page.
19. **ADR numbers:** 0023 records the Phase 9 deployment decisions (and the stale-card waiver);
    0024 records the AI mark.
20. **One branch,** `feat/phase-9a-demo-readiness`, with a PR-size checkpoint after Task 6.
21. **Task sizes:** one API task, no CPU reservation, 256 MiB reserved and 512 MiB hard; setup 256
    MiB; cleanup 128 MiB.
22. **The SSM prefix** is proposed as `/portfolio/open-door/`; Phase 2 confirms it.
23. **The day lock stays** (as the shared conventions ask). A reservation made just after UTC
    midnight can miss one uncommitted reservation from the previous day of the same month, bounded
    by one call's reservation (under $1). ADR 0011's amendment says so.

## Where the spec doesn't fit this repository

- **5.10 item 3 is already done here.** All three workflows set `permissions: contents: read` at the
  top (`.github/workflows/ci.yml:19-20`, `security.yml:18-19`, `changelog.yml:8-10`), and every
  `uses:` is pinned to a full commit, which `make check-workflows` (zizmor) enforces
  (`ci.yml:1-2`, `Makefile:293-297`). Task 11 only verifies it.
- **The entrypoint doesn't just ignore a command, it hides the mistake** (`scripts/image/entrypoint.sh:26-31`):
  a scheduled cleanup task given a command override would start a second web server that never
  exits, once an hour. Task 8 makes it fail loudly.
- **Liveness for the load balancer** (spec 5.3) reverses `docs/BACKLOG.md:538-541` and the
  docstring in `app/api/v1/health.py:5-9`. With Postgres in a container on the same instance, a
  database outage then leaves the target healthy while every page that reads data fails, and
  Route 53 doesn't fail over. The plan follows the spec and records the trade-off in ADR 0023.
- **Postgres 16's `CREATEROLE` rules break the bootstrap's second run on a non-superuser owner.**
  The creator becomes an admin member of `od_app_login`, and the "has members" check
  (`apps/api/scripts/bootstrap_db_users.py:83-87, 174-177`) would refuse it. Task 9 fixes the check
  and proves a double setup.
- **Turning live AI off by disabling the Anthropic key is only half an off switch** (spec 5.10 item
  10). Questions fail with the friendly text and cost nothing, but the landing flag can't see the
  key and keeps offering the tour. `AI_MONTHLY_BUDGET_USD=0` and a restart is the clean switch;
  `docs/DEPLOY.md` says so.
- **AI-written case summaries need the mark too.** HR reads them in the sandbox
  (`app/modules/cases/api_schemas.py:163-169`); the spec says "answers".
- **The prompt rule applies to this branch's PR, not only the release.** `CLAUDE.md:162-167`
  requires a full run before any PR that changes a prompt. The waiver goes in this PR's description
  as well as the CHANGELOG and ADR 0023.
- **The 512 MiB limit was measured with the scripted transport** (`docs/CAPACITY.md:56-58`, peak
  142 MB). The real SDK adds TLS and parsing; measure again after launch.
- **`FORWARDED_ALLOW_IPS` as the whole VPC CIDR** trusts the header from any host in the VPC. Only
  the load balancer and the instance live there, and uvicorn 0.54 takes the rightmost untrusted
  address (`uvicorn/middleware/proxy_headers.py:169-187`), so a forged leftmost entry is ignored.

## Review focus

The five conditions most likely to hurt a visitor that no requirement names directly. Each has a
test in the task that owns the code.

1. **A month boundary mid-call:** a reservation made on the last day of a month and settled after
   midnight stays in the old month, and the new month starts with its full paced allowance (Task 2:
   `test_last_months_rows_do_not_count`, `test_the_first_of_the_month_gets_three_even_shares`).
2. **A month already over budget** from fallback settles (a settle can be positive,
   `app/ai/budget.py:170-173`): the allowance is 0, never negative; the banner says the limit is
   reached, the flag says unavailable, and the 429 has no `Retry-After` (Task 2:
   `test_an_overspent_month_allows_nothing`, `test_a_used_month_sends_no_retry_after`; Task 5:
   `test_the_flag_is_false_when_the_month_is_used`).
3. **Two questions racing for the last of the day's room:** exactly one reservation fits (Task 2:
   `test_two_reservations_race_for_the_last_paced_room`).
4. **A call that fails after the visitor saw text:** the reservation is kept, not settled to $0,
   and no retry runs (Task 3: `test_a_failure_after_text_keeps_the_reservation_and_is_not_retried`).
5. **The setup runs on every deploy:** a second run on a non-superuser owner passes, and a stranger
   holding `od_app` stops it (Task 9: `test_the_owners_own_membership_is_not_a_stranger`,
   `test_a_stranger_holding_od_app_stops_the_bootstrap`, and the double setup in
   `make prod-local-check`).

## File map

| Area | Files |
|---|---|
| Pacing and the ledger | create `apps/api/app/ai/pacing.py`; modify `app/ai/budget.py`, `app/core/config.py`, `app/main.py`, `app/modules/assistant/routes.py`, `app/ai/pricing.py:87-88`, `apps/api/.env.example` |
| Failures and retries | `app/ai/anthropic_transport.py`, `app/ai/transport.py`, `app/ai/case_summary.py`, `app/ai/guard.py`, `app/ai/replay.py`, `app/ai/turn.py` |
| Refusals and the flag | `app/ai/fixed_texts.py`; create `app/modules/assistant/availability.py`; `app/modules/assistant/schemas.py`; web `features/landing/landing-page.tsx`, `components/landing/public-footer.tsx`, `components/assistant/answer.tsx`, `features/chat/turn-view.tsx`, create `features/chat/walkthrough-offer.ts`, `components/walkthrough/walkthrough-link.tsx`; `apps/web/openapi.json` and `apps/web/src/api/generated.ts` (generated) |
| The stale-card fix | the patch's files; create `evals/assistant/recorded_prompt.py`, `evals/assistant/fixtures/recorded-under.json`, `evals/assistant/fixtures/assistant-prompt-2026-11.4.md`; modify `evals/assistant/run.py`, `evals/README.md` |
| The image and jobs | `scripts/image/entrypoint.sh`; create `scripts/image/setup.sh`, `scripts/image/cleanup.sh`, `scripts/image/postgres-open-door.sql`; `Dockerfile`, `scripts/image/container.py`, `scripts/image/check.py`, `scripts/prod-local/start.py`, `scripts/prod-local/README.md`, `Makefile` |
| Database roles | create `apps/api/migrations/versions/0020_database_connect_for_its_roles.py`; modify `apps/api/scripts/bootstrap_db_users.py` |
| The AI mark | create `app/ai/provenance.py`; `app/modules/assistant/display.py`, `app/ai/turn.py` (`TurnStarted`), `app/modules/cases/api_schemas.py` and its builder; web `components/cases/case-summary-block.tsx`, `features/walkthrough/transcript.tsx` |
| Docs | create `docs/DEPLOY.md`, `docs/adr/0023-phase-9-on-the-shared-portfolio-server.md`, `docs/adr/0024-ai-written-text-is-marked.md`; modify ADRs 0011, 0015, 0021, 0022, the ADR index, `CLAUDE.md:222`, `docs/ROADMAP.md`, `docs/CAPACITY.md`, `docs/DATA-INVENTORY.md`, `docs/THREAT-MODEL.md`, `docs/AI-GOVERNANCE.md`, `docs/BACKLOG.md`, `docs/specs/2026-10-20-phase-5-time-off.md:463-464`, `app/api/v1/health.py` (docstring), `CHANGELOG.md` |

Test commands: one API test with `cd apps/api && uv run pytest tests/<file>.py -q` (integration
tests need `make db` first), one web test with `cd apps/web && npx vitest run src/<file>`, one
browser test with `cd apps/web && npx playwright test e2e/<file>.spec.ts`.

---

### Task 1: The work branch and this plan

**Files:**
- Create: `docs/plans/2026-11-19-phase-9a-demo-readiness.md` (this file, already written)
- Modify: `docs/ROADMAP.md:29` (the status table)

- [x] **Step 1: Say the session's effort level** in one line (`medium`).
- [x] **Step 2: Confirm the checkout.**
  Run: `git rev-parse --abbrev-ref HEAD && git rev-parse --short HEAD && git status --short`
  Expected: `dev`, `bd2fea3`, and only `?? docs/plans/2026-11-19-phase-9a-demo-readiness.md`.
  Anything else: stop and tell James.
- [x] **Step 3: Compare with GitHub.** Run `git fetch origin dev` and
  `git rev-parse --short origin/dev`. Expected: `bd2fea3`. If `origin/dev` moved, stop and ask
  whether to start from it instead.
- [x] **Step 4: Stop:** propose creating `feat/phase-9a-demo-readiness` from `dev`, and wait for
  James's OK. Then run `git switch -c feat/phase-9a-demo-readiness dev`.
- [x] **Step 5: Add the status row** above the Phase 9 row (`docs/ROADMAP.md:29`), and append
  "; 9a (local readiness) comes first" to the Phase 9 row's status cell:

  ```
  | 9a Demo readiness (local, before the deploy) | In progress: the monthly AI budget, friendly refusals and the landing flag, the stale-card fix (no paid runs), the job entrypoints, the database roles, the AI mark, and the deploy contract | `feat/phase-9a-demo-readiness` | - | [phase 9a plan](plans/2026-11-19-phase-9a-demo-readiness.md) | 2026-11-19 |
  ```

- [x] **Step 6: Check the docs.** Run `make check-docs`. Expected: passes (spelling, links,
  placeholders, em dashes).
- [x] **Step 7: Stop:** show the diff summary and the proposed commit message, and wait for James's
  explicit OK before committing.
  Proposed message: subject "Plan Phase 9a: Open Door's demo readiness before the deploy"; body: one
  paragraph saying the plan builds every local change the portfolio deployment design asks of Open
  Door, with no paid runs, and that the roadmap row tracks it.

  ```bash
  git add docs/plans/2026-11-19-phase-9a-demo-readiness.md docs/ROADMAP.md
  git commit -F /tmp/od-9a-commit.txt
  ```

---

### Task 2: A monthly AI budget, paced by day

**Files:**
- Create: `apps/api/app/ai/pacing.py`, `apps/api/tests/test_pacing.py`,
  `apps/api/tests/integration/test_budget_pacing.py`
- Modify: `apps/api/app/ai/budget.py:36-62, 88-160, 211-221`; `apps/api/app/core/config.py:238-240`
  and a new check beside `require_entry_settings_fit_for_production` (`:386-421`);
  `apps/api/app/main.py:80`; `apps/api/app/modules/assistant/routes.py:735-763`;
  `apps/api/app/ai/pricing.py:87-88`; `apps/api/.env.example:54-56`;
  `scripts/prod-local/start.py` (`BUDGET_SETTINGS`, `budget_env`, `api_env`);
  `docs/adr/0011-insert-only-budget-ledger.md` (amendment); `docs/DATA-INVENTORY.md:276`;
  `CHANGELOG.md`
- Test: `apps/api/tests/test_config.py`, `apps/api/tests/test_prod_local.py`,
  `apps/api/tests/integration/test_cleanup_job.py`,
  `apps/api/tests/integration/test_assistant_routes.py`, `apps/api/tests/integration/conftest.py`

**Interfaces:**
- Produces, in `app/ai/pacing.py`:
  - `@dataclass(frozen=True) class MonthlyBudget: budget_usd: Decimal; multiplier: Decimal; floor_usd: Decimal`
  - `def days_left_in_month(today: date) -> int` (today included)
  - `def allowance_today_usd(budget: MonthlyBudget, *, spent_before_today_usd: Decimal, today: date) -> Decimal`
- Produces, in `app/ai/budget.py`:
  - `Caps(sandbox_usd: Decimal, daily_usd: Decimal, monthly: MonthlyBudget | None = None)`; every
    existing `Caps(a, b)` call keeps working, with no monthly budget.
  - `BudgetState(sandbox_remaining_usd, daily_remaining_usd, month_remaining_usd: Decimal | None = None)`
  - `@dataclass(frozen=True) class DayRoom: limit_usd: Decimal; spent_today_usd: Decimal; month_remaining_usd: Decimal | None`
  - `async def day_room(db: AsyncSession | AsyncConnection, caps: Caps) -> DayRoom`, the one
    reading that `reserve`, `budget_state`, and Task 5's flag share.
- Produces, in `app/core/config.py`: `Settings.ai_monthly_budget_usd: Decimal | None` (ge 0, blank
  is unset), `ai_pacing_multiplier: Decimal` (default 3, ge 1), `ai_daily_floor_usd: Decimal`
  (default 1.00, ge 0), and `def require_ai_budget_fit_for_production(settings: Settings) -> None`.

- [x] **Step 1: Write the failing pacing tests** in `apps/api/tests/test_pacing.py`:

  ```python
  MONTH = MonthlyBudget(budget_usd=Decimal("20"), multiplier=Decimal("3"), floor_usd=Decimal("1.00"))

  def test_days_left_counts_today() -> None:
      assert days_left_in_month(date(2026, 11, 1)) == 30
      assert days_left_in_month(date(2026, 11, 30)) == 1
      assert days_left_in_month(date(2026, 12, 1)) == 31
      assert days_left_in_month(date(2027, 2, 1)) == 28
      assert days_left_in_month(date(2028, 2, 29)) == 1

  def test_the_first_of_the_month_gets_three_even_shares() -> None:
      assert allowance_today_usd(MONTH, spent_before_today_usd=Decimal(0), today=date(2026, 11, 1)) == Decimal("2.000000")

  def test_the_share_rounds_down_to_the_ledgers_places() -> None:
      assert allowance_today_usd(MONTH, spent_before_today_usd=Decimal(0), today=date(2026, 12, 1)) == Decimal("1.935483")

  def test_the_floor_applies_when_the_share_is_small() -> None:
      assert allowance_today_usd(MONTH, spent_before_today_usd=Decimal("18.50"), today=date(2026, 11, 2)) == Decimal("1.000000")

  def test_never_more_than_is_left() -> None:
      assert allowance_today_usd(MONTH, spent_before_today_usd=Decimal("19.60"), today=date(2026, 11, 2)) == Decimal("0.400000")

  def test_the_last_day_may_spend_everything_left() -> None:
      assert allowance_today_usd(MONTH, spent_before_today_usd=Decimal("12.75"), today=date(2026, 11, 30)) == Decimal("7.250000")

  def test_an_overspent_month_allows_nothing() -> None:
      assert allowance_today_usd(MONTH, spent_before_today_usd=Decimal("20.30"), today=date(2026, 11, 9)) == Decimal(0)

  def test_a_zero_budget_allows_nothing() -> None:
      off = MonthlyBudget(Decimal(0), Decimal(3), Decimal("1.00"))
      assert allowance_today_usd(off, spent_before_today_usd=Decimal(0), today=date(2026, 11, 1)) == Decimal(0)

  def test_the_cleanup_rule_keeps_every_day_of_the_month() -> None:
      # The cleanup deletes rows with `day < today - 30` (app/jobs/cleanup.py:54-56).
      day = date(2024, 1, 1)
      while day <= date(2028, 12, 31):
          assert day.replace(day=1) >= day - timedelta(days=30)
          day += timedelta(days=1)
  ```

- [x] **Step 2: Run them.** `cd apps/api && uv run pytest tests/test_pacing.py -q`. Expected: FAIL,
  `ModuleNotFoundError: No module named 'app.ai.pacing'`.
- [x] **Step 3: Write `app/ai/pacing.py`.** `days_left_in_month` uses `calendar.monthrange`. The
  allowance, rounded down so it never admits more than the formula:

  ```python
  def allowance_today_usd(budget, *, spent_before_today_usd, today):
      left = budget.budget_usd - spent_before_today_usd
      if left <= 0:
          return Decimal(0)
      paced = budget.multiplier * left / days_left_in_month(today)
      return min(left, max(paced, budget.floor_usd)).quantize(LEDGER_PLACES, rounding=ROUND_FLOOR)
  ```

  The module docstring states the formula, that days and months are UTC, and that the caller
  passes the database's date.
- [x] **Step 4: Run them.** Same command. Expected: PASS.
- [x] **Step 5: Write the failing ledger tests** in `tests/integration/test_budget_pacing.py`.
  First move `insert_spend` from `tests/integration/test_cleanup_job.py:28-50` into
  `tests/integration/conftest.py` as
  `insert_dated_spend(owner_engine, *, days_ago: int, amount_usd: Decimal = Decimal("0.000001")) -> UUID`,
  and use it from both files. Each test reads the month's sums first (a `month_sums(owner_engine)`
  helper running the same SQL as `MONTH_SUMS` below) and sets the budget relative to them, because
  the daily ledger is shared by every test (`tests/integration/test_budget.py:1-6`). A multiplier of
  0 makes the allowance `min(left, floor)`, so the tests don't depend on the date (`MonthlyBudget`
  doesn't validate; `Settings` does). `sandbox_usd` and `daily_usd` are 1000 unless a test says
  otherwise. Delete every row
  a test adds in `finally`.
  - `test_the_floor_bounds_today`: budget = before + today + 100, multiplier 0, floor = today +
    0.50. Reserving 0.50 fits; then 0.01 more raises `BudgetExceeded("daily")`.
  - `test_spend_earlier_this_month_counts` (skipped on the 1st): budget = before + today + 0.50,
    floor 100; insert 0.30 dated yesterday. Reserving 0.25 is refused; 0.20 fits.
  - `test_last_months_rows_do_not_count`: insert 9.00 dated the last day of last month
    (`days_ago=today.day`); with budget = before + today + 0.50 and floor 100, reserving 0.50 fits.
  - `test_the_daily_ceiling_still_applies`: a generous monthly budget, `daily_usd` = today + 0.30;
    reserving 0.50 raises `BudgetExceeded("daily")`.
  - `test_a_zero_monthly_budget_refuses_everything`: `MonthlyBudget(Decimal(0), Decimal(3), Decimal(1))`; reserving
    0.000001 raises `BudgetExceeded("daily")` and writes nothing.
  - `test_two_reservations_race_for_the_last_paced_room`: the pattern of
    `test_two_reservations_wait_for_each_other_and_only_one_fits` (`test_budget.py:560`) with
    pacing caps leaving room for one; exactly one succeeds.
  - `test_the_budget_state_reports_the_paced_room`: `daily_remaining_usd` equals the allowance
    minus today's rows, and `month_remaining_usd` equals budget minus the month's rows.
  - `test_without_a_monthly_budget_nothing_changes`: `Caps(LOTS, today + 0.50)` behaves as today and
    `month_remaining_usd` is None.
  And in `tests/integration/test_cleanup_job.py`:
  `test_the_job_keeps_the_whole_current_month` inserts a row dated the 1st of this month
  (`days_ago=today.day - 1`) and one 31 days back; after `run_cleanup`, the first is kept.
- [x] **Step 6: Run them.** `cd apps/api && uv run pytest tests/integration/test_budget_pacing.py tests/integration/test_cleanup_job.py -q`.
  Expected: FAIL, `TypeError` on `Caps(..., monthly=...)` (the cleanup test passes already).
- [x] **Step 7: Change `app/ai/budget.py`.** Add `MONTH_SUMS` (keep `DAY_SUM`, which the eval
  harness reads):

  ```sql
  WITH today AS (SELECT (now() AT TIME ZONE 'UTC')::date AS d)
  SELECT today.d,
         coalesce(sum(s.amount_usd) FILTER (WHERE s.day < today.d), 0),
         coalesce(sum(s.amount_usd) FILTER (WHERE s.day = today.d), 0)
  FROM today LEFT JOIN ai_spend_daily s
    ON s.day >= date_trunc('month', today.d)::date AND s.day <= today.d
  GROUP BY today.d
  ```

  `day_room` runs it and returns `limit_usd = min(caps.daily_usd, allowance)` (just
  `caps.daily_usd` with no monthly budget) and `month_remaining_usd = budget - before - today`.
  `reserve` calls it after `TAKE_DAY_LOCK`, in place of `DAY_SUM`, and raises
  `BudgetExceeded("daily")` when `spent_today + amount > limit`. `budget_state` builds
  `daily_remaining_usd = limit - spent_today` from it. `Caps.from_settings` fills `monthly` when
  `ai_monthly_budget_usd` is set. Update the module docstring with the pacing rule and the
  midnight bound (decision 23).
- [x] **Step 8: Run them.** Same command, plus `uv run pytest tests/integration/test_budget.py -q`.
  Expected: PASS.
- [x] **Step 9: Write the failing settings and route tests.**
  - `tests/test_config.py`: `test_the_monthly_budget_is_unset_by_default`;
    `test_a_zero_monthly_budget_parses` (`"0"` gives `Decimal(0)`);
    `test_a_blank_monthly_budget_is_unset`; `test_the_pacing_settings_refuse_bad_values` (a negative
    budget or floor, a multiplier under 1); `test_production_needs_a_monthly_budget`
    (`require_ai_budget_fit_for_production` raises in production without it, naming
    `AI_MONTHLY_BUDGET_USD`, passes with `0`, and passes outside production without it).
  - `tests/integration/test_assistant_routes.py`, with the existing `open_browser_with` fixture
    (`:807`): `test_a_used_month_sends_no_retry_after` (`ai_monthly_budget_usd=Decimal(0)`: the
    question gets 429 `budget-daily` and no `Retry-After`) and
    `test_a_used_day_still_sends_retry_after` (the daily ceiling at today's spend, a large monthly
    budget: `Retry-After` is present).
  - `tests/test_prod_local.py`: `test_production_runs_get_the_portfolio_budgets` (`api_env` sets
    `AI_MONTHLY_BUDGET_USD=20` and `AI_SANDBOX_BUDGET_USD=0.50` unless a run lowers them) and
    `test_only_the_monthly_budget_may_be_zero` (`budget_env({"monthly": "0"})` works,
    `{"daily": "0"}` still raises `LaunchError`). Update `test_only_the_two_budgets_can_be_set`
    (`:388`) to the three.
- [x] **Step 10: Run them.** `uv run pytest tests/test_config.py tests/test_prod_local.py tests/integration/test_assistant_routes.py -q`.
  Expected: FAIL on the new tests.
- [x] **Step 11: Implement.** The three settings, with `ai_monthly_budget_usd` added to a blank-is-
  unset validator; `require_ai_budget_fit_for_production`, called in `create_app` right after
  `require_entry_settings_fit_for_production` (`app/main.py:80`), so tests that build the app with
  `app_env="production"` (`grep -rln 'app_env="production"' apps/api/tests`) now pass
  `ai_monthly_budget_usd`; the `Retry-After` rule in
  `routes.py:756-763` (keep the `budget_state` result in a variable, and send the header only when
  `state.month_remaining_usd is None or state.month_remaining_usd >= needed`); `start.py`'s
  `BUDGET_SETTINGS` gains `"monthly": "AI_MONTHLY_BUDGET_USD"`, `budget_env` allows 0 for it only,
  and `api_env` defaults the two portfolio values. In `pricing.py:87-88`, drop the sentence about
  the claude-api skill's table (it now says $0.10 too) and keep "per the pricing page read on
  2026-10-14".
- [x] **Step 12: Run them.** Same command. Expected: PASS.
- [x] **Step 13: Write the docs that travel with it.**
  - `apps/api/.env.example`: commented `AI_MONTHLY_BUDGET_USD=20`, `AI_PACING_MULTIPLIER=3`,
    `AI_DAILY_FLOOR_USD=1.00`, with one line each on what they do and that production requires the
    first (and `0` turns live AI off).
  - ADR 0011: a dated "Amendment (2026-11-19): a monthly budget, paced by day" section: the
    formula, the shared names, the daily ceiling kept for paid local runs, the midnight bound, and
    no sweeper (decision 4). Old text is not rewritten.
  - `docs/DATA-INVENTORY.md:276`: the `day` column also feeds the month's pacing.
  - `CHANGELOG.md`, Added: "The assistant's spend is a monthly budget, paced by day (Phase 9a)".
- [x] **Step 14: Run the API checks.** `make db && make check-api`, then `make eval-offline`.
  Expected: both pass; the offline evals are unchanged.
- [x] **Step 15: Stop:** show the diff summary and the proposed commit message, and wait for
  James's explicit OK before committing.
  Proposed subject: "Pace the assistant's spend from a monthly budget". Body: the formula in one
  sentence, that production must set `AI_MONTHLY_BUDGET_USD` and `0` turns live AI off, that the
  daily cap stays as a ceiling for paid local runs, and that a 429 no longer promises tomorrow when
  the month is used.

---

### Task 3: Unbilled failures cost nothing, and every limit is named

**Files:**
- Modify: `apps/api/app/ai/anthropic_transport.py:76, 86-94, 142-157, 172-179, 222-233, 282-297, 335-356`;
  `apps/api/app/ai/transport.py:231-271`; `apps/api/app/ai/case_summary.py:70` (`SummaryUnavailable`);
  `apps/api/app/ai/guard.py:193-210`; `apps/api/app/ai/replay.py:286-292`;
  `apps/api/app/ai/turn.py:1330-1443`; `docs/adr/0011-insert-only-budget-ledger.md`; `CHANGELOG.md`
- Test: `apps/api/tests/test_anthropic_transport.py`, `tests/test_anthropic_summarizer.py`,
  `tests/test_guard.py`, `tests/test_replay.py`, `tests/integration/test_turn_endings.py`,
  `tests/integration/test_case_summary_task.py`

**Interfaces:**
- Consumes: Task 2's ledger (unchanged `settle`).
- Produces:
  - `type ApiFailure = Literal["spend-limit", "unbilled", "unknown"]` and
    `def classify_status_error(error: APIStatusError) -> ApiFailure` in `anthropic_transport.py`.
  - `ModelUnavailable(message, *, status_code=None, request_id=None, unbilled: bool = False)`,
    `GuardUnavailable(message, *, usage=None, unbilled: bool = False)`,
    `SummaryUnavailable(message, *, usage=None, unbilled: bool = False)`. An unbilled guard or
    summary failure carries `usage=Usage(0, 0, 0, 0)`, so the existing settle code prices it at $0.
  - `MODEL_MAX_RETRIES = 0`; in `turn.py`, `UNBILLED_RETRY_STATUSES = frozenset({429, 529})` and
    `UNBILLED_RETRY_DELAY = timedelta(seconds=1)`.

- [x] **Step 1: Write the failing classification test,** table-driven, building each
  `APIStatusError` the way the file's existing tests do:

  | Status | Body | Expected |
  |---|---|---|
  | 400 | `invalid_request_error`, "You have reached your specified API usage limits. ..." | `spend-limit` |
  | 400 | the same with "workspace API usage limits" | `spend-limit` |
  | 400 | the same with "organization API usage limits" | `spend-limit` |
  | 400 | any other `invalid_request_error` | `unknown` |
  | 402 | `billing_error` | `spend-limit` |
  | 429 | `rate_limit_error` with `details.error_code` `enforced_spend_limit_reached` | `spend-limit` |
  | 429 | the same code at `error.error_code` | `spend-limit` |
  | 429 | `rate_limit_error`, no code | `unbilled` |
  | 401 | `authentication_error` | `unbilled` |
  | 403 | `permission_error` | `unbilled` |
  | 529 | `overloaded_error` | `unbilled` |
  | 500 | `api_error` | `unknown` |
  | 200 (an `event: error` in the stream) | `overloaded_error` | `unknown` |

  Also: `test_the_stream_reports_each_failure_as_its_kind` (a 402 raises `SpendLimitReached`, a 401
  raises `ModelUnavailable` with `unbilled=True`, a 500 with `unbilled=False`);
  `test_the_guard_and_the_summary_classify_alike` (a 402 raises `SpendLimitReached` from both; a
  529 gives `GuardUnavailable` and `SummaryUnavailable` with `unbilled=True` and zero usage); and
  `test_the_client_makes_one_attempt` (`from_settings(...).client.max_retries == 0`). Update the
  worst-case test (`test_anthropic_transport.py:945-949`) to one attempt.
- [x] **Step 2: Run them.** `cd apps/api && uv run pytest tests/test_anthropic_transport.py tests/test_anthropic_summarizer.py -q`.
  Expected: FAIL (`classify_status_error` undefined).
- [x] **Step 3: Implement the classifier** and use it in all three call paths, in place of
  `is_spend_limit` (keep `is_spend_limit` only if another module imports it). The message pattern:
  `re.compile(r"You have reached your specified (?:(?:workspace|organization) )?API usage limits")`,
  matched at the start. Read the organization message's exact words on Anthropic's errors page
  and record "Source: ..., read on <date>" beside the pattern; adjust it if the words differ. Set
  `MODEL_MAX_RETRIES = 0` and rewrite the comment above it (one attempt per reservation, spec 5.2).
- [x] **Step 4: Run them.** Same command. Expected: PASS.
- [x] **Step 5: Write the failing ledger tests.**
  - `tests/test_replay.py`: `test_an_unbilled_failure_is_never_recorded`
    (`is_transient(GuardUnavailable("x", usage=Usage(0, 0, 0, 0), unbilled=True))` is True, and the
    same for `SummaryUnavailable`).
  - `tests/test_guard.py`: `test_an_unbilled_guard_failure_settles_to_zero` (the screening outcome
    is `unavailable` with zero usage, so `guard_cost` prices it at $0).
  - `tests/integration/test_turn_endings.py`, with the file's fake transports:
    - `test_an_unbilled_failure_settles_the_call_to_zero`: the call raises
      `ModelUnavailable(status_code=401, unbilled=True)`; the turn fails `model-unavailable`, the
      call's reserve and settle rows sum to 0, and nothing is retried.
    - `test_an_overloaded_call_is_tried_once_more`: a 529 (unbilled), then a normal answer; the turn
      completes, the ledger has two reservations, and the first nets to 0.
    - `test_only_one_unbilled_retry_per_turn`: two 529s; the turn fails `model-unavailable`, and
      both reservations net to 0.
    - `test_a_failure_after_text_keeps_the_reservation_and_is_not_retried`: a `TextDelta`, then
      `ModelUnavailable(unbilled=False)`; the reservation stays at its full amount, and there is
      one call.
    - `test_a_spend_limit_on_the_guard_still_gives_the_emergency_numbers`: the guard raises
      `SpendLimitReached`; the error is `spend-limit`, its text holds "911" and "988", and the
      guard's reservation nets to 0.
  - `tests/integration/test_case_summary_task.py`: `test_an_unbilled_summary_failure_settles_to_zero`.
- [x] **Step 6: Run them.** `uv run pytest tests/test_replay.py tests/test_guard.py tests/integration/test_turn_endings.py tests/integration/test_case_summary_task.py -q`.
  Expected: FAIL on the new tests.
- [x] **Step 7: Implement.** `is_transient` also returns True for `unbilled`. `guard.screen` turns
  an unbilled `GuardUnavailable` into `_unavailable(Usage(0, 0, 0, 0))`. In `turn.py`'s
  `except ModelUnavailable` (`:1432-1435`):

  ```python
  if error.unbilled:
      await self._settle(reservation, lambda: Decimal(0))  # Refused before any work: not billed.
      if (error.status_code in UNBILLED_RETRY_STATUSES and not self.unbilled_retried
              and len(self.shown) == shown_before and self.deadline_loop_s - _clock() > 1):
          self.unbilled_retried = True
          await asyncio.sleep(UNBILLED_RETRY_DELAY.total_seconds())
          continue
  else:
      self._keep(reservation)
  self.fail("model-unavailable", request_id=error.request_id)
  return
  ```

  `unbilled_retried` starts False in `TurnRun.__init__`. The retry goes back to the top of the
  loop, which builds the same request and reserves for it again.
- [x] **Step 8: Run them.** Same command, then `uv run pytest tests/integration/test_turn.py -q`.
  Expected: PASS.
- [x] **Step 9: Docs.** Add the settle rules and "retries off, one app-level retry" to ADR 0011's
  amendment. `CHANGELOG.md`, Fixed: "A failed call the provider doesn't bill no longer uses up the
  day's budget (Phase 9a)", and Changed: "The Anthropic workspace, organization, billing, and
  enforced spend limits all stop the assistant with the spend-limit text (Phase 9a)".
- [x] **Step 10: Run the API checks.** `make check-api && make eval-offline`. Expected: PASS.
- [x] **Step 11: Stop:** show the diff summary and the proposed commit message, and wait for
  James's explicit OK before committing.
  Proposed subject: "Settle unbilled model failures to zero and name every spend limit". Body:
  which errors now cost $0, which count as the spend limit, that the SDK no longer retries under
  one reservation, and the single retry for an overload or rate limit.

---

### Task 4: Refusals that point to the walkthrough

**Files:**
- Modify: `apps/api/app/ai/fixed_texts.py:57-74, 115-138`; `apps/web/src/components/assistant/answer.tsx`;
  `apps/web/src/features/chat/turn-view.tsx:262-290, 420-450`;
  `apps/web/src/app/gallery/sections/conversation-fixtures.ts`; `apps/web/e2e/conversation-helpers.ts`;
  `apps/web/e2e/conversation.spec.ts`; `CHANGELOG.md`
- Create: `apps/web/src/features/chat/walkthrough-offer.ts`
- Test: `apps/api/tests/test_fixed_texts.py:116-180`, `apps/web/src/components/assistant/answer.test.tsx`,
  `apps/web/src/features/chat/walkthrough-offer.test.ts`,
  `apps/web/src/components/assistant/budget-banner.test.tsx`,
  `apps/web/src/app/gallery/sections/conversation-sections.test.tsx`

**Interfaces:**
- Produces: `BUDGET_DAILY_TEXT` (new words), `BUDGET_DAILY_TEXT_APPROVED_ON`,
  `BUDGET_DAILY_TEXT_SHA256` (the sandbox text keeps `BUDGET_TEXTS_APPROVED_ON`);
  `MODEL_UNAVAILABLE_TEXT`, `MODEL_UNAVAILABLE_TEXT_AUTHOR`, `_APPROVED_ON`, `_SHA256`, used as
  `ERROR_TEXTS["model-unavailable"]`; in the web app,
  `export function offersWalkthrough(code: string | undefined): boolean` and an `offerWalkthrough`
  prop on the answer's error state.
- Produces for Task 5: the approved `LIVE_PAUSED_NOTE` and `RETENTION_NOTE` words.

- [x] **Step 1: Stop:** show James every new visitor-facing string, with a screenshot of the gallery's
  daily-limit state, and wait for his approval of the words (he may rewrite them). Proposed:
  - Daily limit (also the Anthropic spend limit, a used month, and live AI off): "The demo's live
    assistant has reached its limit for now. You can still watch the recorded walkthrough. If you
    or someone else is in danger, call 911, or call or text 988 to reach the 988 Suicide & Crisis
    Lifeline."
  - Model unavailable (the guard has already passed the message): "I can't reach the assistant
    service right now. You can try again later, or watch the recorded walkthrough."
  - Landing note, for Task 5: "The live assistant has reached its limit for now. The recorded
    walkthrough shows a full tour, and you can still explore a sandbox."
  - Footer, for Task 5: "Each sandbox is removed after 24 hours. Server backups keep copies for up
    to 7 days, and server logs, which include IP addresses, are kept for 14 days. Anthropic (AI
    answers), Voyage (handbook search), Cloudflare (the bot check), and AWS (hosting) process
    this data."
  Record the approval date he gives.
- [x] **Step 2: Write the failing text tests** in `tests/test_fixed_texts.py`: change
  `test_the_budget_texts_say_which_limit_was_reached` to assert `"tomorrow" not in` and
  `"walkthrough" in ERROR_TEXTS["budget-daily"]`; change `test_the_budget_texts_are_the_approved_words`
  to the approved daily words; add `test_the_daily_text_is_approved` and
  `test_the_model_unavailable_text_is_approved` (date parses; SHA-256 matches, like
  `test_the_guard_down_text_is_approved` at `:133`), and
  `test_the_model_unavailable_text_names_no_fictional_contact` (`"HR team" not in` it,
  `"walkthrough" in` it, `"in a moment" not in` it). `test_each_budget_text_gives_911_and_988`
  stays as it is.
- [x] **Step 3: Run them.** `cd apps/api && uv run pytest tests/test_fixed_texts.py -q`. Expected:
  FAIL.
- [x] **Step 4: Change the texts,** then compute each hash:
  `cd apps/api && uv run python -c "import hashlib; from app.ai import fixed_texts as f; print(hashlib.sha256(f.BUDGET_DAILY_TEXT.encode()).hexdigest(), hashlib.sha256(f.MODEL_UNAVAILABLE_TEXT.encode()).hexdigest())"`.
  Keep `ERROR_TEXTS["spend-limit"] = BUDGET_DAILY_TEXT`, and update the comment above it.
- [x] **Step 5: Run them.** Same command. Expected: PASS.
- [x] **Step 6: Write the failing web tests.**
  - `walkthrough-offer.test.ts`: true for `model-unavailable`, `spend-limit`, and `budget-daily`;
    false for `budget-sandbox`, `budget-conversation`, `internal`, `refusal`, and `undefined`.
  - `answer.test.tsx`: "an error that offers the walkthrough shows its link under the text" (the
    link named "Watch the recorded walkthrough" follows the error message), and "an internal error
    shows no walkthrough link".
- [x] **Step 7: Run them.** `cd apps/web && npx vitest run src/features/chat/walkthrough-offer.test.ts src/components/assistant/answer.test.tsx`.
  Expected: FAIL.
- [x] **Step 8: Implement.** `offersWalkthrough` in `walkthrough-offer.ts`; the answer's error
  state renders `<WalkthroughLink />` in a `mt-2 block` span when `offerWalkthrough` is true (the
  spacing `budget-banner.tsx:54-64` uses for WCAG 2.5.8); `turn-view.tsx` passes
  `offerWalkthrough={offersWalkthrough(turn.error?.code)}` for a stored failed turn and the same
  for the live turn's error. Update the gallery fixture, the banner test, and the two e2e files to
  the new daily words (`grep -rn "try again tomorrow\|ask the HR team directly" apps/web/src apps/web/e2e`
  finds them; leave `docs/design/` and ADR 0019 as records).
- [x] **Step 9: Run them.** Same command, then `make check-web`. Expected: PASS.
- [x] **Step 10: Changelog.** `CHANGELOG.md`, Changed: "Limit and outage messages point to the
  recorded walkthrough (Phase 9a)", with the approval date and that the HR team (fictional) is no
  longer the fallback.
- [x] **Step 11: Run the checks.** `make check-api && make eval-offline && make e2e`. Expected: PASS.
- [x] **Step 12: Stop:** show the diff summary and the proposed commit message, and wait for
  James's explicit OK before committing.
  Proposed subject: "Point the limit and outage messages to the recorded walkthrough".

---

### Task 5: The public live-assistant flag and the landing page

**Files:**
- Create: `apps/api/app/modules/assistant/availability.py`,
  `apps/api/tests/test_availability_cache.py`,
  `apps/api/tests/integration/test_assistant_availability.py`
- Modify: `apps/api/app/modules/assistant/routes.py` (the route), `schemas.py`
  (`AssistantAvailabilityOut`), `apps/api/app/main.py` (one cache on `app.state`);
  `apps/web/openapi.json`, `apps/web/src/api/generated.ts` (by `make openapi`);
  `apps/web/src/features/landing/landing-page.tsx`, `apps/web/src/components/landing/public-footer.tsx`,
  `apps/web/src/components/walkthrough/walkthrough-link.tsx`; `scripts/prod-local/start.py`
  (`--ai-off`); `Makefile` (`prod-local-check`); `CHANGELOG.md`
- Test: `apps/web/src/features/landing/landing-page.test.tsx`,
  `apps/web/src/components/landing/public-footer.test.tsx` (create), `apps/web/e2e/landing.spec.ts`,
  `apps/api/tests/test_prod_local.py`

**Interfaces:**
- Consumes: `day_room` and `Caps` (Task 2); the approved landing note and footer line (Task 4).
- Produces:
  - `LANDING_ROOM_USD: Final = Decimal("0.25")`, `AVAILABILITY_TTL_SECONDS: Final = 30`
  - `class AvailabilityCache: def __init__(self, ttl_seconds: float = AVAILABILITY_TTL_SECONDS, clock: Callable[[], float] = time.monotonic)`
    and `async def get(self, compute: Callable[[], Awaitable[bool]]) -> bool`: one computation in
    flight, its answer kept for the TTL (the shape of `ReadinessCache`, `app/api/v1/health.py:46-87`).
  - `async def live_assistant_available(engine: AsyncEngine, caps: Caps) -> bool`: on a plain
    connection (the API's login may read every `ai_spend_daily` row,
    `migrations/versions/0019_sandbox_starts.py:96`),
    `room.limit_usd - room.spent_today_usd >= LANDING_ROOM_USD`.
  - `GET /api/v1/assistant/availability`, operation `getAssistantAvailability`, no session, answer
    `AssistantAvailabilityOut(available: bool)` with `Cache-Control: public, max-age=30`; a
    database error answers 503 with the problem type `availability-unknown`.
  - Web: `WalkthroughButton` (the walkthrough link with `buttonVariants({ variant: 'secondary' })`
    from `components/ui/button-variants.ts`, the tour button's look).

- [x] **Step 1: Write the failing API tests.**
  - `tests/test_availability_cache.py`: `test_a_fresh_answer_is_reused` (a second `get` inside the
    TTL doesn't compute), `test_an_old_answer_is_computed_again` (move the fake clock past 30 s),
    `test_concurrent_callers_compute_once`.
  - `tests/integration/test_assistant_availability.py`: `test_the_flag_needs_no_session` (no cookie:
    200 with a boolean `available`); `test_the_flag_is_cacheable` (`Cache-Control: public,
    max-age=30`); `test_the_flag_is_false_when_the_month_is_used` (`ai_monthly_budget_usd=0`);
    `test_the_flag_is_false_when_today_has_less_than_a_question` (the daily ceiling at today's
    spend plus 0.10); `test_the_flag_is_true_with_room`; and
    `test_the_landing_room_covers_a_first_question`: `room_needed_usd(...)` for a seeded sandbox's
    Priya, an empty history, `CURRENT_PINS`, and "How many sick days do I get?" is at most
    `LANDING_ROOM_USD` and more than `Decimal("0.15")`, so the threshold stays meaningful.
- [x] **Step 2: Run them.** `cd apps/api && uv run pytest tests/test_availability_cache.py tests/integration/test_assistant_availability.py -q`.
  Expected: FAIL.
- [x] **Step 3: Implement** the module, the schema, and the route (no `SignedInDep`; the cache
  from `app.state`, created in `create_app` beside `ReadinessCache`). Then run `make openapi`.
- [x] **Step 4: Run them.** Same command, then `uv run python scripts/export_openapi.py --check`.
  Expected: PASS.
- [x] **Step 5: Write the failing web tests.**
  - `landing-page.test.tsx`: with availability `false`, there is no "Take the tour" button and no
    tour Turnstile slot, the walkthrough is a single button-styled link, the approved note shows,
    and the persona cards are enabled; with `true`, while pending, and after a failed read, the
    tour button shows as today.
  - `public-footer.test.tsx`: the approved retention line shows.
  - `e2e/landing.spec.ts`: one test routes `**/api/v1/assistant/availability` to
    `{"available": false}` and checks that the walkthrough replaces the tour button.
- [x] **Step 6: Run them.** `cd apps/web && npx vitest run src/features/landing/landing-page.test.tsx src/components/landing/public-footer.test.tsx`.
  Expected: FAIL.
- [x] **Step 7: Implement.** The landing reads `useGetAssistantAvailability` with
  `staleTime: 30_000` and `retry: false`, and treats anything but `data.available === false` as
  available. When unavailable it renders `LIVE_PAUSED_NOTE` under the sandbox notes and
  `WalkthroughButton` in the tour button's place, and drops the text link and the tour's
  `TurnstileSlot`. `RETENTION_NOTE` joins the footer's notices.
- [x] **Step 8: Run them.** Same command, then `npx playwright test e2e/landing.spec.ts` and
  `make check-web`. Expected: PASS.
- [x] **Step 9: The production-image check with live AI off.** Write the failing tests in
  `tests/test_prod_local.py`: `test_the_ai_off_check_sets_a_zero_monthly_budget` and
  `test_the_ai_off_check_never_passes_the_real_key` (`api_env` for it holds
  `ANTHROPIC_API_KEY=not-a-real-key-ai-off-check`, so an accidental call fails unbilled, and
  `read_secrets` isn't asked for a key). Then add `--ai-off` to `start.py --check`: it starts the
  image with production settings and `AI_MONTHLY_BUDGET_USD=0`, then checks that the flag says
  `false`, that a sandbox starts with Turnstile's `DUMMY_TOKEN` (`app/modules/sandbox/turnstile.py:40`),
  and that a question gets 429 `budget-daily` with the approved text and no `Retry-After`. The
  HTTP steps follow `scripts/proxy-check/check.py` (`start_sandbox`, `new_conversation`,
  `turns_url`). In the `Makefile`, `prod-local-check` passes `--ai-off` when `AI_OFF=1`.
- [x] **Step 10: Run it.** `uv run pytest tests/test_prod_local.py -q`, then
  `make prod-local-check AI_OFF=1`. Expected: PASS, and the run prints that no model was called.
- [x] **Step 11: Show James the landing.** Take a screenshot of the landing with the flag false
  (from the e2e run's trace, or the gallery). **Stop:** wait for his OK on the look; if he wants a
  Claude Design round, pause this task and follow `CLAUDE.md`, "Design".
- [x] **Step 12: Changelog.** Added: "The landing page says when the live assistant is out of
  budget and offers the walkthrough instead of the tour (Phase 9a)", and the footer's retention
  line.
- [x] **Step 13: Run the checks.** `make check-api && make check-web && make eval-offline`.
  Expected: PASS.
- [x] **Step 14: Stop:** show the diff summary and the proposed commit message, and wait for
  James's explicit OK before committing.
  Proposed subject: "Tell visitors on the landing page when the live assistant is out".

---

### Task 6: Sandbox start limits for shared office networks

**Files:**
- Modify: `apps/api/app/core/config.py:215-219`, `apps/api/.env.example:39-41`, `docs/CAPACITY.md:146-149`,
  `docs/adr/0021-sandbox-entry-protection.md` (amendment), `docs/THREAT-MODEL.md:84, 195-203`,
  `docs/DATA-INVENTORY.md:299`, `CHANGELOG.md`
- Test: `apps/api/tests/test_config.py`

- [x] **Step 1: Write the failing test.** `test_the_start_limits_fit_an_office_network`: a default
  `Settings` has `sandbox_starts_per_hour == 15`, `sandbox_starts_per_day == 50`, and
  `sandbox_starts_daily_total == 1000`.
- [x] **Step 2: Run it.** `cd apps/api && uv run pytest tests/test_config.py -q`. Expected: FAIL.
- [x] **Step 3: Change the three defaults** and `.env.example`. The load test keeps its own values
  (`scripts/load/drive.py:327-331`), which its measurements used.
- [x] **Step 4: Run it,** then `uv run pytest tests/integration/test_sandbox_limits.py tests/integration/test_sandbox_start.py -q`.
  Expected: PASS.
- [x] **Step 5: Measure one sandbox's size** in the development database, for the 1,000 total:
  `docker compose exec -T db psql -U opendoor -d opendoor -Atc "SELECT pg_size_pretty(sum(pg_total_relation_size(c.oid)) / greatest((SELECT count(*) FROM tenants), 1)) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r'"`
  (the `db` service of `compose.yaml`). Multiply by 1,000 and confirm it is a small share
  of the 20 GB data volume.
- [x] **Step 6: Docs.** `CAPACITY.md:146-149`: 15 an hour and 50 a day per address, sized for a
  hiring team behind one address, and 1,000 a day in all, with the measured size. ADR 0021: a
  dated amendment with the new numbers (the decision at `:19-20` is not rewritten).
  `THREAT-MODEL.md:197`: "20 IPv4 addresses at 50 a day reach 1,000", and the AI budget's
  sentence in `:198-201` now names the monthly budget. `DATA-INVENTORY.md:299`: the new numbers.
  `CHANGELOG.md`, Changed.
- [x] **Step 7: Run the checks.** `make check-api && make check-docs`. Expected: PASS.
- [x] **Step 8: Stop:** show the diff summary and the proposed commit message, and wait for
  James's explicit OK before committing.
  Proposed subject: "Raise the sandbox start limits for shared office networks".
- [x] **Step 9: The PR-size checkpoint.** Count the reviewable lines so far:
  `git diff --shortstat dev...HEAD -- apps/api/app apps/api/migrations apps/api/scripts scripts evals/assistant apps/web/src Makefile Dockerfile ':!*.test.ts' ':!*.test.tsx' ':!apps/web/src/api/generated.ts' ':!evals/assistant/fixtures' ':!*.json'`.
  Over 1,200 inserted lines: **Stop:** propose opening a PR of Tasks 1 to 6 into `dev` first (the
  review and PR steps of Tasks 12 and 13, for this part), and wait for James's decision.

---

### Task 7: The stale-card fix, shipped without paid runs

**Files:**
- Apply: `/Users/jameslittlefield/Documents/github_things/open-door-patches/stale-card-recap.patch`
  (`apps/api/app/ai/prompts/assistant.md`, `prompts/versions.py`, `app/ai/proposals.py`,
  `app/ai/turn.py`, and five test files)
- Create: `evals/assistant/recorded_prompt.py`, `evals/assistant/fixtures/recorded-under.json`,
  `evals/assistant/fixtures/assistant-prompt-2026-11.4.md`,
  `apps/api/tests/test_eval_recorded_prompt.py`,
  `docs/adr/0023-phase-9-on-the-shared-portfolio-server.md` (Proposed; Task 11 completes it)
- Modify: `evals/assistant/run.py`, `evals/README.md` (after "What offline replay tests, and what
  it doesn't"), `docs/specs/2026-10-20-phase-5-time-off.md:463-464`, `docs/BACKLOG.md:206-228`,
  `docs/AI-GOVERNANCE.md:446-459`, `CHANGELOG.md`

**Interfaces:**
- Produces, in `evals/assistant/recorded_prompt.py`:
  - `PIN_FILE = "recorded-under.json"`, holding
    `{"promptVersion": "2026-11.4", "file": "assistant-prompt-2026-11.4.md", "sha256": "f860ec09cd6de4a3b845795f84d809737efa803e2154b5e5dd9c586c83998b27", "why": "..."}`
  - `@dataclass(frozen=True) class RecordedPrompt: prompt_version: str; text: str`
  - `def recorded_prompt(fixtures_dir: Path) -> RecordedPrompt | None`: None without the file;
    `ValueError` when the text's SHA-256 differs from the file's, or when `promptVersion` equals
    the current `PROMPT_VERSION` ("a full run recorded the current prompt: delete the pin").
  - `@contextmanager def replaying_under_recorded_prompt(fixtures_dir: Path) -> Iterator[RecordedPrompt | None]`:
    patches `app.ai.turn.system_prompt` (the one caller, `app/ai/turn.py:729`) to return the pinned
    text for the block, and prints one line naming both versions.

- [ ] **Step 1: Apply the patch.** `git apply --check /Users/jameslittlefield/Documents/github_things/open-door-patches/stale-card-recap.patch`,
  then `git apply` it. If the check fails because Task 3 moved lines in `turn.py`, use
  `git apply --3way` and keep both changes; the patch's intent is the authority.
- [ ] **Step 2: Run the patch's tests.** `cd apps/api && uv run pytest tests/test_prompts.py tests/test_outcomes_window.py tests/test_context.py tests/integration/test_proposals.py tests/integration/test_turn_proposals.py -q`.
  Expected: PASS.
- [ ] **Step 3: Confirm the replay breaks, and how.** Run `make eval-offline`. Expected: the full
  set FAILS with replay misses only, and the escalation and case-summary sets pass (their prompts
  didn't change). Record the miss count under "Changes made during execution". Any other kind of
  failure: stop and ask James.
- [ ] **Step 4: Write the failing pin tests** in `apps/api/tests/test_eval_recorded_prompt.py`:
  - `test_the_pin_names_an_older_prompt`: the committed pin's version is not `PROMPT_VERSION`.
  - `test_the_pinned_text_is_its_versions_golden_prompt`: its SHA-256 equals
    `GOLDEN_HASHES[("assistant", pin.prompt_version)]` from `tests/test_prompts.py`.
  - `test_the_pinned_text_has_the_current_canary`: `canary_from(pin.text) == CANARY`.
  - `test_the_pin_changes_only_the_system_prompt`: inside the context, `model_request(...)`'s
    system text is the pinned text and its tools are unchanged; after it, both are current.
  - `test_no_pin_changes_nothing` and `test_a_pin_with_the_wrong_hash_is_refused` (a temporary
    folder).
- [ ] **Step 5: Run them.** `uv run pytest tests/test_eval_recorded_prompt.py -q`. Expected: FAIL.
- [ ] **Step 6: Implement.** Copy the 2026-11.4 prompt out of git, byte for byte:
  `git show dev:apps/api/app/ai/prompts/assistant.md > evals/assistant/fixtures/assistant-prompt-2026-11.4.md`,
  and check it with `shasum -a 256` (expected `f860ec09...c98b27`). Write the JSON and the module.
  In `run.py`, wrap every offline run of the assistant sets (smoke, full, effort; not escalation
  or case-summary) in `replaying_under_recorded_prompt`. If the harness tests
  (`tests/integration/test_assistant_eval_harness.py`, `test_assistant_eval_runner_db.py`) replay
  committed fixtures through a lower function, apply it there instead. A live run with a pin
  present prints that the pin must be deleted after the next full `FRESH=1 PRUNE=1` run.
- [ ] **Step 7: Run them.** `uv run pytest tests/test_eval_recorded_prompt.py tests/integration/test_assistant_eval_harness.py -q`,
  then `make eval-offline`. Expected: PASS, with the pin's line printed once per set it applies to.
- [ ] **Step 8: Docs.**
  - `evals/README.md`: a short section, "Replaying under a recorded prompt": when the pin is
    allowed (an owner's waiver of the full run), what it tests (the plumbing and the graders on the
    old recordings) and what it doesn't (the new prompt), and that the next full run deletes it.
  - `docs/specs/2026-10-20-phase-5-time-off.md:463-464`: "...was confirmed, and the request was
    sent to Marcus Bell for approval."
  - `docs/BACKLOG.md:206-228`: the item becomes a short follow-up: shipped in prompt 2026-11.5
    without its full run; after the deploy, run the full set, record the walkthrough again (steps
    5 and 6 are the check), and delete the pin.
  - `docs/AI-GOVERNANCE.md:446-459`: the stale status is fixed in 2026-11.5, which has had no eval
    run; the published scoreboard is still 2026-11.4's.
  - ADR 0023, created with Status "Proposed" and a first decision: the waiver. No full eval run for
    prompt 2026-11.5 before launch, the walkthrough recorded again after the deploy (James,
    2026-11-18), and CI replays under the recorded prompt until then.
  - `CHANGELOG.md`, Fixed: "The assistant no longer tells a request's old status as current
    (Phase 9a, prompt 2026-11.5)", stating the waiver: no eval run for 2026-11.5 before launch, the
    walkthrough video recorded again after deployment, and CI replaying the 2026-11.4 recordings.
- [ ] **Step 9: Run the checks.** `make check-api && make eval-offline && make check-docs`.
  Expected: PASS.
- [ ] **Step 10: Stop:** show the diff summary and the proposed commit message, and wait for
  James's explicit OK before committing.
  Proposed subject: "Stop the assistant telling a request's old status as current". Body: the bug
  (Priya told her request still waits after Marcus approved it), the fix, the version bump, the
  waiver, and how CI stays green.

---

### Task 8: One entrypoint per job, and the hardened run

**Files:**
- Modify: `scripts/image/entrypoint.sh:17-31`; `Dockerfile:71-72`; `scripts/image/container.py:37-45, 225-262`;
  `scripts/image/check.py` (`problems_in_config`, `check_contents`, `problems_in_forwarding`,
  `check_running`); `scripts/prod-local/start.py` (`setup_run_args`, `api_run_args`,
  `problems_in_pages`, `check`); `scripts/prod-local/README.md`; `CHANGELOG.md`
- Create: `scripts/image/setup.sh`, `scripts/image/cleanup.sh`
- Test: `apps/api/tests/test_image_container.py`, `tests/test_prod_local.py`,
  `tests/test_image_check_script.py`

**Interfaces:**
- Produces: `/app/entrypoint.sh` (serve; any argument exits 64), `/app/setup.sh`, `/app/cleanup.sh`
  in the image; `container.setup_run_args(name, network, env, *, memory="256m")`,
  `container.cleanup_run_args(name, network, env, *, memory="128m")`,
  `container.HARDENED_FLAGS = ["--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true"]`.
  `SETUP_SCRIPT` goes away. `docs/DEPLOY.md` (Task 11) copies the entrypoints and limits.

- [ ] **Step 1: Write the failing tests.**
  - `test_image_container.py`: `test_the_setup_runs_its_own_entrypoint` (`--entrypoint
    /app/setup.sh`, no command after the image, `--memory 256m`, and the hardened flags);
    `test_the_cleanup_runs_its_own_entrypoint_with_one_setting` (`--entrypoint /app/cleanup.sh`,
    `--memory 128m`, and `CLEANUP_DATABASE_URL` the only `--env`).
  - `test_prod_local.py`: update `test_the_setup_runs_the_deploy_steps_in_order...` (`:178-195`) to
    the new entrypoint; add `test_the_api_runs_with_productions_memory_limit_and_flags` (`--memory
    512m` and the hardened flags), and `test_the_page_check_wants_turnstile_the_flag_and_no_docs`:
    split the judgment out of `problems_in_pages` into a plain function of the responses, the way
    `scripts/image/check.py` does, and test that a CSP without `https://challenges.cloudflare.com`
    in `script-src` or `frame-src`, a flag without a boolean, and an `/openapi.json` that serves
    JSON are each a problem.
  - `test_image_check_script.py`: `test_the_job_scripts_must_be_present_and_read_only` (missing or
    writable scripts are problems); `test_an_entrypoint_that_takes_a_command_is_a_problem`;
    `test_a_forged_leftmost_address_must_not_win` (`problems_in_forwarding` given a trusted log
    showing `198.51.100.7` for the header `198.51.100.7, 203.0.113.9` is a problem, and one showing
    `203.0.113.9` isn't).
- [ ] **Step 2: Run them.** `cd apps/api && uv run pytest tests/test_image_container.py tests/test_prod_local.py tests/test_image_check_script.py -q`.
  Expected: FAIL.
- [ ] **Step 3: Write the scripts.** `scripts/image/setup.sh`:

  ```sh
  #!/bin/sh
  # The deploy's one-off setup: migrate, create the login users, load the handbook. Runs on every
  # deploy, before the service updates; each step is safe to repeat.
  set -eu
  cd /app/apps/api
  alembic upgrade head
  python scripts/bootstrap_db_users.py
  exec python scripts/ingest_handbook.py ingest
  ```

  `scripts/image/cleanup.sh`: the same header, then `cd /app/apps/api` and
  `exec python -m app.jobs.cleanup` (it reads only `CLEANUP_DATABASE_URL`). In `entrypoint.sh`,
  before the `set --` line:

  ```sh
  if [ "$#" -gt 0 ]; then
    echo "This entrypoint serves the API and takes no command (got: $1). Run a job with its own" \
      "entrypoint: /app/setup.sh or /app/cleanup.sh." >&2
    exit 64
  fi
  ```

  The `Dockerfile` copies both scripts beside the entrypoint, mode `0555`.
- [ ] **Step 4: Update the launchers.** `container.py`: the two `*_run_args` and
  `HARDENED_FLAGS`; the load test keeps working through `setup_run_args`. `start.py`: setup with
  its limit and flags; the API with `--memory 512m` and the flags; `--check` also runs the cleanup
  container once and requires exit 0 and its "cleanup finished" line, requires `script-src` and
  `frame-src` in the page's CSP to name `https://challenges.cloudflare.com`, requires
  `GET /api/v1/health` and `GET /api/v1/assistant/availability` to answer 200 (the second with a
  boolean `available`), and requires `/openapi.json` and `/docs` not to serve the API schema or
  Swagger (the web app's page is fine).
  `check.py`: the job scripts present and `0555`, the entrypoint exiting 64 on an argument
  (`docker run --rm open-door:test serve`), and the forwarded check also sends
  `X-Forwarded-For: 198.51.100.7, 203.0.113.9` from the trusted peer and expects `203.0.113.9`.
- [ ] **Step 5: Run them.** Same command. Expected: PASS.
- [ ] **Step 6: Prove it in the image.** `make image-check`, then `make prod-local-check SKIP_BUILD=1`,
  then `make live-check DRY_RUN=1 SKIP_BUILD=1` (free: the scripted model). Expected: all pass,
  with the API under a read-only root. If something writes outside `/tmp`, find it and either
  stop it writing or give it a tmpfs, and record which under "Changes made during execution".
- [ ] **Step 7: Docs.** `scripts/prod-local/README.md`: the setup and cleanup containers, the
  limits, and the flags. `CHANGELOG.md`, Changed: "The image runs each job from its own
  entrypoint, and refuses a command it doesn't know (Phase 9a)".
- [ ] **Step 8: Run the checks.** `make check-api && make check-docs`. Expected: PASS.
- [ ] **Step 9: Stop:** show the diff summary and the proposed commit message, and wait for
  James's explicit OK before committing.
  Proposed subject: "Give the setup and cleanup jobs their own image entrypoints".

---

### Task 9: One Postgres server, two apps: the database roles

**Files:**
- Create: `apps/api/migrations/versions/0020_database_connect_for_its_roles.py`,
  `apps/api/tests/integration/test_database_connect.py`, `scripts/image/postgres-open-door.sql`
- Modify: `apps/api/scripts/bootstrap_db_users.py:76-87, 160-185`; `scripts/image/container.py`
  (the shared-server database); `scripts/prod-local/start.py` (`db_env`, `Passwords`,
  `start_database`, `setup_env`, `query_args`, `check`); `CHANGELOG.md`
- Test: `apps/api/tests/integration/test_bootstrap.py`, `tests/integration/test_grants.py`,
  `tests/test_prod_local.py`

**Interfaces:**
- Produces: migration 0020; the bootstrap's `STRANGERS` check; `scripts/image/postgres-open-door.sql`
  (the init superuser's setup of Open Door's database, which Phase 2 runs on the shared server);
  in `container.py`, `SHARED_INIT_USER = "postgres_init"` and `OPEN_DOOR_OWNER = "opendoor_owner"`.
  The load test keeps its single-superuser database.

- [ ] **Step 1: Write the failing tests.**
  - `test_database_connect.py`: `test_public_cannot_connect` (no `aclexplode(datacl)` entry for
    grantee 0 with `CONNECT` on `current_database()`); `test_open_doors_roles_can_connect`
    (`has_database_privilege('od_app', current_database(), 'CONNECT')`, and for `od_cleanup`);
    `test_a_login_without_open_doors_roles_cannot_connect` (the owner makes a throwaway `LOGIN`
    role; connecting as it fails with "permission denied for database"; drop it in `finally`).
  - `test_bootstrap.py`: `test_a_stranger_holding_od_app_stops_the_bootstrap` (a role granted
    `od_app` that no URL names: `SystemExit` naming both, nothing changed);
    `test_the_owners_own_membership_is_not_a_stranger` (grant `od_app_login` to `current_user`
    `WITH ADMIN OPTION, INHERIT FALSE, SET FALSE`, as Postgres 16 does for a `CREATEROLE` creator;
    the bootstrap runs twice and passes; revoke after).
- [ ] **Step 2: Run them.** `cd apps/api && uv run pytest tests/integration/test_database_connect.py tests/integration/test_bootstrap.py -q`.
  Expected: FAIL.
- [ ] **Step 3: Implement.** Migration 0020, as the database owner:

  ```python
  def upgrade() -> None:
      op.execute("DO $$ BEGIN EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', current_database());"
                 " EXECUTE format('GRANT CONNECT ON DATABASE %I TO od_app, od_cleanup', current_database()); END $$")

  def downgrade() -> None:  # the reverse: revoke from the two roles, grant to PUBLIC
  ```

  In the bootstrap, `MEMBERS` leaves out `current_user`, and a new check lists each role's members
  (`pg_auth_members` where the role is `od_app` or `od_cleanup`) other than the configured logins
  and `current_user`, refusing with the role, the members, and "another database's login would
  inherit Open Door's access", before anything changes. Update the module docstring's rules.
- [ ] **Step 4: Run them,** then `uv run pytest tests/integration/test_grants.py tests/integration/test_role_migration.py -q`
  and `make migrations-roundtrip` (it wipes the development data; run `make db` after). Expected:
  PASS.
- [ ] **Step 5: Write the shared-server setup** in `scripts/image/postgres-open-door.sql`:

  ```sql
  -- Open Door's database on the shared portfolio Postgres server. Run once, as the server's init
  -- superuser, connected to `postgres`, with OD_OWNER_PASSWORD in psql's environment. The
  -- password is sent once; password_encryption (scram-sha-256) stores only its verifier.
  \set ON_ERROR_STOP on
  \getenv od_owner_password OD_OWNER_PASSWORD
  CREATE ROLE opendoor_owner LOGIN CREATEROLE PASSWORD :'od_owner_password';
  CREATE DATABASE opendoor OWNER opendoor_owner;
  REVOKE CONNECT ON DATABASE opendoor FROM PUBLIC;
  \connect opendoor
  CREATE EXTENSION IF NOT EXISTS vector;
  ```

- [ ] **Step 6: Write the failing prod-local tests.** `test_the_database_starts_with_an_init_superuser_only`;
  `test_open_doors_database_is_made_by_the_init_sql` (the password travels as `--env`, never on a
  command line); `test_the_setup_connects_as_a_non_superuser_owner`
  (`MIGRATION_DATABASE_URL` names `opendoor_owner`); `test_queries_run_as_the_init_superuser`
  (the owner sees no tenant rows under forced row-level security, so `query` can't use it);
  `test_the_check_runs_the_setup_twice`.
- [ ] **Step 7: Run them.** `uv run pytest tests/test_prod_local.py -q`. Expected: FAIL.
- [ ] **Step 8: Implement** in `container.py` and `start.py`: start Postgres with
  `POSTGRES_USER=postgres_init`, wait for it, feed the SQL file to
  `docker exec -i -e OD_OWNER_PASSWORD <db> psql -U postgres_init -d postgres`, and connect the
  setup as `opendoor_owner`. `--check` runs the setup twice.
- [ ] **Step 9: Run them,** then `make prod-local-check SKIP_BUILD=1` and
  `make live-check DRY_RUN=1 SKIP_BUILD=1`. Expected: PASS: migrations run as a non-superuser, the
  second setup says "password reset", and the dry run's database reads still work.
- [ ] **Step 10: Learn whether `vector` needs a superuser.** In the prod-local database container
  while a check runs (or a scratch `docker run` of `pgvector/pgvector:0.8.7-pg17`), as
  `opendoor_owner` in a scratch database it owns, run `CREATE EXTENSION vector;`. Record the
  result in "Changes made during execution"; `docs/DEPLOY.md` keeps the pre-creation either way.
- [ ] **Step 11: Changelog.** Security: "Open Door's database admits only its own logins, and the
  setup refuses a role that would inherit its access (Phase 9a)".
- [ ] **Step 12: Run the checks.** `make check-api && make eval-offline`. Expected: PASS.
- [ ] **Step 13: Stop:** show the diff summary and the proposed commit message, and wait for
  James's explicit OK before committing.
  Proposed subject: "Admit only Open Door's own logins to its database".

---

### Task 10: AI-written text is marked as AI-generated (Article 50(2))

**Files:**
- Create: `apps/api/app/ai/provenance.py`, `docs/adr/0024-ai-written-text-is-marked.md`
- Modify: `apps/api/app/modules/assistant/schemas.py:111-135` (`TurnOut`), `display.py` (fills
  it), `apps/api/app/ai/turn.py:265-270` (`TurnStarted.to_json`), `routes.py:661-663` (the stream's
  description), `apps/api/app/modules/cases/api_schemas.py:163-169` and where `CaseSummaryOut` is
  built; `apps/web/openapi.json`, `apps/web/src/api/generated.ts` (`make openapi`);
  `apps/web/src/components/assistant/answer.tsx`, `components/cases/case-summary-block.tsx`,
  `features/walkthrough/transcript.tsx`; `docs/adr/README.md`, `docs/AI-GOVERNANCE.md:26-63`,
  `CHANGELOG.md`
- Test: `apps/api/tests/test_assistant_schemas.py`, `tests/integration/test_assistant_routes.py`,
  `tests/integration/test_case_routes.py`, a turn-event test in `tests/integration/test_turn.py`;
  `apps/web/src/components/assistant/answer.test.tsx`,
  `components/cases/case-summary-block.test.tsx`, `features/walkthrough/walkthrough-page.test.tsx`

**Interfaces:**
- Produces, in `app/ai/provenance.py`: `GENERATOR: Final = "Open Door AI assistant"`,
  `DIGITAL_SOURCE_TYPE: Final = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"`.
- Produces, in the schemas: `class AiGeneratedOut(CamelModel): generator: str; models: list[str]; digital_source_type: str`;
  `TurnOut.ai_generated: AiGeneratedOut | None` (set when the model wrote any of `answer_text`);
  `CaseSummaryOut.ai_generated: AiGeneratedOut | None` (set when `status == "written"`).
- Produces, on the page: `data-ai-generated="true"` on the element that holds model-written text.

- [ ] **Step 1: Read the guidance first.** Read the European Commission's current guidance and
  code of practice on marking and labeling AI-generated content, from the Commission's own site,
  and record "Source: ..., read from ... on <date>" for ADR 0024 (`CLAUDE.md`, "Research and
  sources"). If it asks for a different technique for text (a specific metadata standard, for
  example), **Stop:** tell James, and wait for his choice before building.
- [ ] **Step 2: Write the failing API tests.** `test_a_completed_answer_carries_the_mark` (the
  conversation read's turn has `aiGenerated` with the generator, the served models, and the IPTC
  term); `test_a_crisis_turn_carries_no_mark` (the fixed text has no mark);
  `test_a_failed_turn_with_partial_text_is_marked`; `test_turn_started_says_its_text_is_ai_generated`
  (`TurnStarted(id).to_json() == {"turnId": str(id), "aiGenerated": True}`);
  `test_a_written_summary_carries_the_mark` and `test_a_failed_summary_carries_none`.
- [ ] **Step 3: Run them.** `cd apps/api && uv run pytest tests/test_assistant_schemas.py tests/integration/test_assistant_routes.py tests/integration/test_case_routes.py -q`.
  Expected: FAIL.
- [ ] **Step 4: Implement,** then `make openapi`.
- [ ] **Step 5: Run them.** Same command, plus `uv run python scripts/export_openapi.py --check`.
  Expected: PASS.
- [ ] **Step 6: Write the failing web tests.** The answer's model text carries
  `data-ai-generated="true"`, and an error with no text, the crisis panel, and the person's own
  question don't; the case summary block's written summary carries it; each answer in the
  walkthrough transcript carries it and each question doesn't.
- [ ] **Step 7: Run them.** `cd apps/web && npx vitest run src/components/assistant/answer.test.tsx src/components/cases/case-summary-block.test.tsx src/features/walkthrough/walkthrough-page.test.tsx`.
  Expected: FAIL.
- [ ] **Step 8: Implement.** The attribute only; nothing visible changes (each answer is already
  labeled as the AI's on screen).
- [ ] **Step 9: Run them,** then `make check-web`. Expected: PASS.
- [ ] **Step 10: Docs.** ADR 0024 (context: Article 50(2) and its source; decision: the three
  places the mark is, and the IPTC term; rejected: a visible label only, a watermark in the words,
  an HTTP header alone; consequences: the API change, the scoreboard and console unchanged). Add
  its row to `docs/adr/README.md`. `AI-GOVERNANCE.md`: the Article 50(2) section says how answers
  and summaries are marked, with the source line, and the "Phase 9 item" bullet goes. `CHANGELOG.md`,
  Added.
- [ ] **Step 11: Run the checks.** `make check-api && make check-docs && make eval-offline`.
  Expected: PASS.
- [ ] **Step 12: Stop:** show the diff summary and the proposed commit message, and wait for
  James's explicit OK before committing.
  Proposed subject: "Mark AI-written answers and summaries as AI-generated".

---

### Task 11: The deploy contract and the docs that change

**Files:**
- Create: `docs/DEPLOY.md`
- Modify: `docs/adr/0023-phase-9-on-the-shared-portfolio-server.md` (complete, then Accepted),
  `docs/adr/0015-envelope-encryption.md` (amendment), `docs/adr/0022-claude-api-from-aws.md`
  (amendment), `docs/adr/README.md`, `CLAUDE.md:222`, `docs/ROADMAP.md:98, 133`, `docs/CAPACITY.md`,
  `docs/DATA-INVENTORY.md:19, 291, 311-313, 576-584`, `docs/THREAT-MODEL.md`, `docs/AI-GOVERNANCE.md`
  (the deployed data path), `docs/BACKLOG.md:467-566`, `apps/api/app/api/v1/health.py:1-9`,
  `CHANGELOG.md`

- [ ] **Step 1: Confirm the workflows need nothing** (spec 5.10, item 3).
  Run: `grep -n "^permissions:" -A 2 .github/workflows/*.yml` and
  `grep -hn "uses:" .github/workflows/*.yml | grep -v "@[0-9a-f]\{40\}"`.
  Expected: every file has `contents: read` at the top, and the second command prints nothing. Then
  `make check-workflows` passes. If a gap shows, fix it here and note it in the changelog.
- [ ] **Step 2: Write `docs/DEPLOY.md`,** the contract Phase 2 copies:
  - **What runs:** the `open-door:prod` image as three task definitions: the API service (one
    task, rolling, minimum 100% and maximum 200%), the setup (a one-off before each service
    update, run with RunTask, which can't override the entrypoint, so it has its own definition),
    and the cleanup (EventBridge Scheduler, hourly).
  - **The settings contract:** one row per setting: which of the three reads it, secret or plain,
    and production's value or source. The API: `APP_ENV` (the image's `production`), `APP_ORIGIN`
    (the site's https origin; planned `https://opendoor.jameslittlefield.net`, spec section 7),
    `DATABASE_URL`, `ENCRYPTION_KEYRING`, `ANTHROPIC_API_KEY` (the "Open Door" workspace, $22
    limit), `VOYAGE_API_KEY` (optional: without it, search is full-text only,
    `app/modules/handbook/search.py:110`), the Turnstile pair, `SANDBOX_IP_HASH_KEY` (at least 32
    bytes), `FORWARDED_ALLOW_IPS` (the VPC CIDR), `AI_TRANSPORT=anthropic`, and the "Shared names
    and values" above. The setup: `APP_ENV`, `APP_ORIGIN` (https; `app/core/config.py:359-372`),
    `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `CLEANUP_DATABASE_URL`, and no keyring or API key.
    The cleanup: `CLEANUP_DATABASE_URL` only. Secrets live in SSM SecureString under
    `/portfolio/open-door/` (decision 22).
  - **The three definitions,** as JSON fragments: the API (`portMappings` 8000 to host port 0,
    `memoryReservation` 256, `memory` 512, no CPU reservation, `stopTimeout` 30, `user`
    `10001:10001`, `readonlyRootFilesystem`, a 64 MiB tmpfs at `/tmp`, `capabilities.drop` ALL,
    `dockerSecurityOptions` `no-new-privileges`, and a health check
    `["CMD", "python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=3).status == 200 else 1)"]`
    every 15 s, timeout 5, 3 retries, start period 20, because ECS ignores the image's
    `HEALTHCHECK` and the image has no curl); the setup (`entryPoint` `["/app/setup.sh"]`,
    memory 256, must exit 0); the cleanup (`entryPoint` `["/app/cleanup.sh"]`, memory 128, an
    alarm on a non-zero exit). Each job gets the API's user and hardened flags.
  - **The load balancer:** the target group checks `/api/v1/health/live` (200); idle timeout 120
    s, under the image's keep-alive of 130 (`scripts/image/entrypoint.sh:13-16`); deregistration
    delay 90 s. WAF's "expensive paths" for Open Door: `POST /api/v1/sandboxes` and
    `POST /api/v1/assistant/conversations/*/turns`.
  - **Shutdown order:** draining for the deregistration delay, then SIGTERM, uvicorn's 15 s, and
    the app's 12 s to save open streams, inside `stopTimeout` 30.
  - **Smoke tests after a deploy:** `GET /` 200, `GET /api/v1/health` 200 (readiness), and
    `GET /api/v1/assistant/availability` 200.
  - **The database on the shared server:** run `scripts/image/postgres-open-door.sql` once as the
    init superuser; the owner is a non-superuser with `CREATEROLE`; `CONNECT` revoked; scram-sha-256
    passwords; no TLS, because the traffic never leaves the instance's Docker bridge; no pooler.
    Rotating a database password: change the URL in SSM, run the setup (the bootstrap resets each
    login's password from its URL), then restart the service. Data migrations under forced
    row-level security see no tenant rows for a non-superuser owner: set the tenant context per
    tenant, or turn forcing off around the step as 0018 does. Migration 0018's data step needs the
    keyring only on a database that already holds denial notes; production starts empty.
  - **Turning live AI off:** `AI_MONTHLY_BUDGET_USD=0` and a restart (the landing then offers the
    walkthrough). Disabling the Anthropic key alone also stops spending, but the landing keeps
    offering the tour.
- [ ] **Step 3: Complete ADR 0023** and mark it Accepted: Open Door on the shared portfolio server.
  Decisions, each with what it replaces: ECS on one EC2 instance in bridge mode, not Fargate; one
  task at 256/512 MiB, not two at 1 vCPU and 2 GB; Postgres 17 with pgvector as an ECS service on
  the instance, not managed, with the role layout of Task 9; SSM Parameter Store, not Secrets
  Manager; the local key provider with its keyring from SSM, not KMS; no per-task egress limit
  (bridge mode can't, and the instance blocks the metadata service); the load balancer on
  liveness (with the trade-off above); the monthly paced budget and $0.50 per sandbox; the job
  entrypoints; and the stale-card waiver (Task 7). Rejected: Fargate (about $130 a month against
  about $72), RDS, Secrets Manager, building the KMS provider. Add its row to `docs/adr/README.md`.
- [ ] **Step 4: The amendments.** ADR 0015: a dated amendment: for the portfolio deployment,
  production uses the local provider with `ENCRYPTION_KEYRING` from an SSM SecureString
  (`app/core/encryption.py:251-252`); the KMS provider isn't built, so "production refuses
  `local`" (`:81`) no longer holds; why (fictional data deleted within a day, a key in task memory
  accepted by ADR 0023). ADR 0022: a dated amendment: egress isn't limited per task on the shared
  server (ADR 0023).
- [ ] **Step 5: The living docs.**
  - `CLAUDE.md:222`: "Open Door deploys to AWS (ECS on the shared portfolio EC2 server, one task
    behind the shared load balancer) as the last step, ..."
  - `docs/ROADMAP.md:98`: Phase 9's scope matches ADR 0023 (the shared server, Postgres on it,
    SSM, the local keyring); `:133`: the Postgres host is decided (ADR 0023).
  - `docs/CAPACITY.md`, "Recommendations": one task, 256 MiB reserved and 512 MiB hard (the peak
    was 142 MB), no CPU reservation; the AI limits rewritten for the paced month: $20 buys about
    115 tours; a 30-day month's even share is about $0.67 a day, a busy day up to $2.00, and the
    $1.00 floor lets about four first questions start at once; $0.50 a sandbox is one full tour
    plus several follow-up questions, because each question needs about $0.21 of room
    (`app/ai/admission.py:56-101`, `app/ai/turn.py:158`).
  - `docs/DATA-INVENTORY.md`: application logs in CloudWatch for 14 days, with client IP
    addresses (`app/core/security_log.py:48` and uvicorn's access log); load balancer access logs
    in S3 for 14 days, with IP addresses; daily snapshots of the data volume kept 7 days, so a
    sandbox's rows can outlive it by up to 7 days in backups; AWS (us-east-1) as the host; and the
    sentences that said "set at deployment (Phase 9)" now state these.
  - `docs/THREAT-MODEL.md`: the shared Postgres server (`CONNECT`, the membership checks); the
    public availability route (a cached boolean, no session); the per-address limits behind the
    load balancer (the VPC CIDR, the rightmost untrusted address); egress open per task, the
    metadata service blocked; WAF's rate rules.
  - `docs/AI-GOVERNANCE.md`: the deployed data path on AWS, which ADR 0022 left to Phase 9.
  - `apps/api/app/api/v1/health.py:1-9`: the load balancer and ECS use liveness; readiness is for
    the deploy's smoke tests.
- [ ] **Step 6: Account for the Phase 9 backlog** (`docs/BACKLOG.md:467-566`). Each item moves to
  done, deferred, or closed with its reason:

  | Item (lines) | Becomes |
  |---|---|
  | KMS key provider (473-476) | Closed: not built; the keyring comes from SSM (ADR 0015 amendment) |
  | Secrets and settings contract (477-483) | Done: `docs/DEPLOY.md` |
  | ECS task definitions and the cleanup's schedule (484-488) | Done as written definitions in `docs/DEPLOY.md`; registering them is Phase 2/3 |
  | The deploy workflow (489-490) | Deferred to Phase 2/3 |
  | `FORWARDED_ALLOW_IPS` in the task (491-494) | Documented; the CIDR is Phase 2's |
  | Idle timeout 120, keep-alive 130 (495-499) | Documented; the load balancer is Phase 2's |
  | Postgres 16 or later (500-502) | Closed: Postgres 17 (ADR 0023) |
  | Database TLS and secret rotation (503-504) | Closed: no TLS on the Docker bridge; rotation in `docs/DEPLOY.md` |
  | Backup retention (505-509) | Done: `docs/DATA-INVENTORY.md` (7-day snapshots) |
  | Data migrations under forced RLS (510-515) | Closed: the rule is in `docs/DEPLOY.md`; prod-local migrates as a non-superuser |
  | Migration 0018 and the keyring (516-519) | Closed: production starts empty; noted in `docs/DEPLOY.md` |
  | `set_config` under a pooler (520-525) | Closed: no pooler |
  | Shared server role names (527-536) | Done: Task 9 |
  | Probe paths (538-541) | Done: both checks use liveness (spec 5.3) |
  | Shutdown timeouts (543-548) | Done: `docs/DEPLOY.md` |
  | Turnstile with real keys (549-554) | Deferred to Phase 3's go-live checks |
  | The Article 50(2) mark (555-560) | Done: Task 10 |
  | `ping()` bound (561-564) | Closed: no probe uses readiness now; only smoke tests do |
  | Probe traffic in traces (565-566) | Closed: no tracing, and Container Insights is off |

- [ ] **Step 7: Changelog.** Added: "`docs/DEPLOY.md`, the deploy's settings and task contract
  (Phase 9a)"; Changed: the ADRs and the docs above, in one entry.
- [ ] **Step 8: Run the checks.** `make check-docs && make check-api`. Expected: PASS (`health.py`
  changed only in its docstring).
- [ ] **Step 9: Stop:** show the diff summary and the proposed commit message, and wait for
  James's explicit OK before committing.
  Proposed subject: "Write the deploy contract and update the docs for the shared server".

---

### Task 12: Reviews

- [ ] **Step 1: Everything CI runs.** `make db && make check`. Expected: PASS (it builds both
  images, and runs the image check, the browser tests against the image, and the proxy check).
- [ ] **Step 2: `/code-review medium`** on the whole branch against `dev`, committed and uncommitted
  work together (`CLAUDE.md`, "Reviews and pull requests"). Never `max` or `ultra`.
- [ ] **Step 3: `/security-review`** on the branch (spec 5.10: every implementation PR gets one).
  Brief it with what this branch guards: money (reserve and settle, pacing, the classifier), the
  public route, the database roles, the image's entrypoints, and the waiver.
- [ ] **Step 4: Fix each real finding** test-first, one commit per fix, each behind its own
  **Stop:** show the diff summary and the proposed commit message, and wait for James's explicit
  OK before committing. Record each finding not fixed, and why, under "Changes made during
  execution".
- [ ] **Step 5: Run everything again.** `make check`. Expected: PASS.

---

### Task 13: Local verification, the records, and the PR

None of these steps calls a paid model.

- [ ] **Step 1: Build.** `make db && make image`.
- [ ] **Step 2: The image.** `make image-check SKIP_BUILD=1`. Expected: PASS: non-root, no
  `.env`, `.keys`, or tests inside, the job scripts present and `0555`, the entrypoint refusing a
  command, a forged `X-Forwarded-For` ignored with no trusted proxy, and the rightmost address
  winning over a forged leftmost one behind a trusted proxy. The start key is that address
  (`app/modules/sandbox/routes.py:80-91`). Also run
  `docker run --rm --entrypoint sh open-door:prod -c 'find / -xdev -name ".env*" 2>/dev/null'`:
  expected empty.
- [ ] **Step 3: Production settings.** `make prod-local-check SKIP_BUILD=1`. Expected: PASS:
  liveness and readiness 200, the CSP's nonce and Turnstile sources, the flag answering 200, the
  API docs off, the setup run twice as a non-superuser owner, the cleanup container exiting 0
  under 128 MiB, and the API serving under 512 MiB with a read-only root.
- [ ] **Step 4: Live AI off.** `make prod-local-check SKIP_BUILD=1 AI_OFF=1`. Expected: PASS: the
  flag is false, and a question gets 429 `budget-daily` with the approved text and no
  `Retry-After`.
- [ ] **Step 5: A scripted tour turn.** `make live-check DRY_RUN=1 SKIP_BUILD=1`. Expected: PASS:
  a sandbox starts with Turnstile's test keys, a cited answer streams, a card is booked, and no
  CSP violation shows. While it runs, in a second shell, run
  `docker stats --no-stream open-door-prod-local-api` a few times. Expected: memory under 512 MiB.
- [ ] **Step 6: Memory under load.** `make load SKIP_BUILD=1 LOAD_ARGS="--sizes 0.5:512m --visitors 10 --no-real-caps-run"`.
  Expected: every tour completes, and the report's memory peak is under 512 MiB. Record the peak
  in `docs/CAPACITY.md` beside the old measurements.
- [ ] **Step 7: The money tests and the evals.**
  `cd apps/api && uv run pytest tests/test_pacing.py tests/integration/test_budget_pacing.py tests/integration/test_turn_endings.py -q`,
  then `make eval-offline`. Expected: PASS, with the recorded-prompt line.
- [ ] **Step 8: Docs, workflows, and audit.** `make check-docs check-workflows audit`. Expected:
  PASS.
- [ ] **Step 9: The roadmap.** The 9a row says "Done locally: ready for the deploy", with the PR
  number once it exists and the date; the "Next" note names the deploy (the master plan's Phase
  2, then Open Door's Phase 3) and the effort level (`medium`). Add the results of Steps 2 to 6 to
  "Changes made during execution".
- [ ] **Step 10: Stop:** show the diff summary and the proposed commit message, and wait for
  James's explicit OK before committing.
  Proposed subject: "Record Phase 9a's local verification".
- [ ] **Step 11: The master plan.** In
  `/Users/jameslittlefield/Documents/github_things/portfolio-infra/PLAN.md`, set Open Door's
  Phase 1 row to done, with the branch and this plan's path. If the file or the row doesn't exist
  yet, **Stop:** ask James where it goes. If `portfolio-infra` is a git repository, **Stop:** show
  the diff summary and the proposed commit message, and wait for James's explicit OK before
  committing there.
- [ ] **Step 12: Stop:** propose `git push -u origin feat/phase-9a-demo-readiness`, and wait for
  James's explicit OK before pushing.
- [ ] **Step 13: Stop:** show the PR title and body, and wait for James's explicit OK before
  running `gh pr create --base dev`. The body has `CLAUDE.md`'s four sections ("What this does",
  "Why", "How it was checked", "What to look at"). "How it was checked" lists Steps 2 to 8 and
  states the waiver: no full eval run for prompt 2026-11.5 before launch (James, 2026-11-18), CI
  replaying the 2026-11.4 recordings, and the walkthrough recorded again after the deploy. "What
  to look at" is a reading guide if the counted lines pass 1,500: `app/ai/budget.py` and
  `pacing.py` first, then `anthropic_transport.py` and the `turn.py` hunk, then the migration and
  the bootstrap, then the rest.

---

## Deferred to Phase 2/3 (AWS)

No tasks here; each is the master plan's.

- CDK in `portfolio-infra`: the instance, the retained data volume, the ALB, WAF, the cluster, the
  services, and the roles.
- An ECR repository for Open Door, and its image pushes.
- Registering the three task definitions from `docs/DEPLOY.md`, the service, and the hourly
  cleanup schedule.
- The deploy workflow: OIDC, the `production` environment, `id-token: write` on its job only, the
  setup task before the service update, and the smoke tests.
- The per-app IAM roles and the GitHub OIDC deploy role.
- The SSM parameters and their values (James enters them).
- Real Turnstile keys, and proving them on the deployed page (`docs/BACKLOG.md:549-554`).
- `FORWARDED_ALLOW_IPS` as the VPC CIDR, and `APP_ORIGIN` as the final hostname.
- The shared Postgres service, and running `scripts/image/postgres-open-door.sql` as its init
  superuser.
- The Route 53 failover pair, the fallback site (with a copy of the walkthrough video), and the
  WAF rules.
- The Anthropic "Open Door" workspace ($22 limit, alerts at $10 and $18) and the dev workspace.
- The go-live checks of spec 5.9 and 5.10 on AWS, including the $0 refusal and the failover drill.
- GitHub settings: secret scanning, push protection, Dependabot security updates, and protecting
  `main` (the master plan's Phase 0).
- The release PR from `dev` into `main`, with the waiver in its description.
- The whole-phase `/code-review high` at the end of Phase 9, once the deploy workflow has landed.
- After the deploy: the full eval run for prompt 2026-11.5, recording the walkthrough again, and
  deleting the replay pin.
- Before 2027-01-17: the npm audit exception expires (`scripts/check_npm_audit.py:58`).
- The portfolio's "Live demo" link (Phase 4).

## Changes made during execution

Task 4: the composer's disabled placeholder said 'until tomorrow' too; the owner approved 'The live assistant isn't available right now.' on 2026-11-19.

The implementer also records here: the base commit, the replay miss count (Task 7), what
the read-only root needed (Task 8), whether `vector` needs a superuser (Task 9), the review
findings left unfixed (Task 12), and the verification results (Task 13).
