# Open Door: project rules

An AI-first HR help desk. The assistant is the product. The HR system underneath is deliberately
thin: narrow, not flimsy. Employees, managers, and HR ask questions in plain language. Every policy
answer cites the handbook. The assistant proposes actions and a person confirms them. Sensitive
topics go to humans.

**Start every session by reading [`docs/ROADMAP.md`](docs/ROADMAP.md).** It holds the phase status
table and links to the current spec and plan. **Update its status table at the end of every stage.**
[`docs/plans/2026-09-29-open-door-initial-plan.md`](docs/plans/2026-09-29-open-door-initial-plan.md)
is the frozen record of the original decisions. Never edit it. Record changes in the roadmap, in a new
dated plan, or in an ADR under `docs/adr/`.

---

## Git: hard rule

**Never `git commit`, `git push`, or open a pull request without explicit, per-action approval.**

- "Build X" or "fix Y" is **not** approval. It means implement to a reviewable state and stop, with
  the changes left uncommitted in the working tree.
- Approval is per-action and does not carry over. Approving one commit does not approve the next.
- You may draft a commit message or PR body and propose it. Running the command still needs approval.

### Branch flow

```
main  ──●──────────────────●──────────────●──   releases only, tagged v0.x.y
         \                ↗ release PR    ↗
dev       ●──●──●──●──●──●──●──●──●──●──●──   integration branch (GitHub default)
             ↖ feat/…  ↖ fix/…  ↖ docs/…
```

- Feature branches come off `dev`, named `feat/`, `fix/`, `chore/` or `docs/` (for example
  `feat/phase-1-rls`), and open a PR back into `dev`.
- **Release PRs go from `dev` into `main`**, periodically, usually after a phase or two lands.
  - Before opening one, on `dev`: cut the changelog's `[Unreleased]` entries into
    `## [0.x.y] - YYYY-MM-DD` and update the roadmap.
  - Before merging: green CI, `/code-review medium`, and a live eval run with the scoreboard change
    in the PR description.
  - **Merge with a merge commit, never a squash.** A squash makes `main` and `dev` diverge and
    produces confusing conflicts on the next release.
  - After merging, tag `main` with `v0.x.y`.

---

## Reviews and pull requests

- **Run `/code-review medium` before creating every PR that changes code.** That includes
  application code, tests, evals, migrations, CI workflows, and build or tooling config.
  - Review the whole branch against the PR's base (`dev`, or `main` for a release PR), with
    committed and uncommitted work together, because that is exactly what the PR will contain.
  - Don't review only the working tree. A commit already on the branch would go unreviewed.
- **Docs-only PRs skip the code review.** `/code-review` hunts for code bugs, and on markdown it
  spends tokens and finds nothing. They get the automated checks (spelling, links, placeholders) and
  the owner's read-through instead.
- **Release PRs (`dev` → `main`) always get `/code-review medium`**, whatever they contain.
- **At the end of every phase, review the whole phase.** After its last PR merges, run
  `/code-review high` on the phase's application code: `dev` against the commit before the phase
  began, limited to the paths that count toward the PR-size guideline below (application code,
  migrations, scripts, and config). Tests, generated files, and docs were already reviewed with
  their stage's code. The phase review catches problems between stages that per-PR reviews can't
  see. Fix real findings in a small follow-up PR before the phase is released.
  - **The phases that guard the invariants also get one security review.** Phase 1 (permissions
    and tenant isolation), Phase 4 (the assistant loop, the guard, prompt injection), Phase 5
    (proposals, the first write path the model can start), and Phase 6 (cases, encryption,
    escalation) add a single reviewer on the strongest model. It is briefed
    with the invariants the phase guards and the seams between its stages. It proves each finding
    with the smallest experiment that shows it, not with exhaustive fuzzing.
- **Never run `/code-review max` or `/code-review ultra`.** `max` sends many reviewers over the
  whole diff in parallel. On Phase 1 it used up the session limit before its bug-hunting passes
  finished. `ultra` is billed separately. The reviews above cover what either would.
- **Open a PR when unmerged work reaches about 1,500 lines, or at a stage boundary, whichever comes
  first.** Size is what breaks reviews, both for tools and for people, so size is the trigger.
  - Count the code a reviewer must read closely: application code, migrations, scripts, and
    config. Tests, generated files (the OpenAPI schema, the generated client, lockfiles), and docs
    don't count toward the 1,500. Tests still go in the same PR as the code they prove.
  - A PR over the guideline gives a short reading guide in "What to look at": which files to read
    closely, in what order, and what can be skimmed.
- Before creating a PR:
  - CI is green (`make check` locally mirrors it).
  - `CHANGELOG.md` is updated.
  - The roadmap status is current.

---

## Effort level

Claude Code's effort setting (`/effort`) controls how much the model thinks on every step. The
agents a session launches run at the session's level unless their own definition sets one. Higher
effort costs more on every step, so match it to the work:

| Session | Effort |
|---|---|
| Planning a phase: the spec, the plan, design decisions | `high`, or `xhigh` for a genuinely hard design problem |
| Carrying out a stage: implementers, reviews, the close | `medium` |
| A phase's close-out review | `medium` |
| A stubborn bug | `high` until it's found, then back to `medium` |
| Quick questions, doc edits, PR text | `low` or `medium` |

- **Say the level at the start of every session,** in one line, then get on with the work. Claude
  can't see the current setting, so the owner changes it with `/effort` if needed.
- **The roadmap's "Next" note names the level** for the next session.
- **Avoid `xhigh` and `max` in a session that launches many agents.** Each agent inherits the
  level, so the cost multiplies.

---

## Writing

- **American English everywhere:** docs, UI copy, code comments, identifiers, and commit and PR
  text. Write "color", "organization", "canceled", "labeled", "behavior". `make check-docs` fails
  on British spellings.
- **No em dashes anywhere:** UI copy, fixed texts, prompts, the handbook, docs, code comments,
  and commit and PR text. Use a comma, a colon, parentheses, or two sentences. An empty table cell
  is "-". `make check-docs` fails on an em dash, except in the frozen initial plan, the Claude
  Design handoff in `docs/design/`, recorded eval fixtures (model output), and lockfiles.
- **Commits and pull requests must be human readable.** Someone who never saw the session should
  understand what changed and why from the message alone.
  - **Commit subject:** one plain sentence in the imperative, at most 72 characters. Say what
    changed for the product or the project, not which files moved.
  - **Commit body:** a few short sentences or bullets covering what changed, why, and anything a
    reader should know. Explain any acronym or project term the first time it appears. Don't list
    files one by one; git already records that.
  - **PR description:** four short sections, "What this does", "Why", "How it was checked", and
    "What to look at". Lead with plain sentences. Use a table only when it genuinely makes things
    clearer.
  - **Avoid jargon a newcomer couldn't follow,** like internal shorthand, bare file paths used as
    explanations, and walls of technical detail. Put the detail in the docs and link to it.
- **Update `CHANGELOG.md` in the same edit as the change**, never as a separate pass afterward.
  Group entries under Added, Changed, Fixed, or Security, and note the phase and stage. CI fails a PR
  that changes code without touching the changelog, unless it carries the `skip-changelog` label.
- **Architecture decisions get an ADR** in `docs/adr/NNNN-title.md`: short, dated, with the
  context, the decision, and what was rejected.

---

## Invariants

These are the reasons the assistant can be trusted. A change that would weaken one needs an ADR and
the owner's explicit agreement first.

1. **The model never decides who can see what.** Every tool gets the actor from the server session.
   No tool input can say "as user X". Tenant isolation is enforced by Postgres row-level security.
2. **The model never calculates balances or durations.** It only turns natural language into ISO
   dates, using today's date and the location's timezone from the per-turn context. The pure
   time-off engine calculates days and balances, and every result carries its handbook citation.
3. **The model never writes.** It proposes. The server stores the proposal, bound to the user with
   an expiry. A person confirms, and the server re-validates and executes it exactly once.
4. **Every policy claim cites the handbook.** With no supporting passage, the assistant says it
   could not find the answer and offers escalation.
5. **The model never makes or recommends employment decisions:** no discipline, termination, or
   performance ratings.
6. **Sensitive topics go to humans.** Crisis text (the 988 Lifeline, the EAP) is fixed and written
   by a person, never generated.
7. **Every AI action is audited, and the assistant always says it is an AI.**

---

## AI development rules

- **A change to a prompt, a tool description or schema, the guard, or the retrieval needs a full
  run before its PR** (`make eval-live SET=full FRESH=1 PRUNE=1 YES=1`, estimated at $14, cap $16;
  with Phase 5's 153 items, the runs of 2026-10-25 cost $10.31 and $10.39). CI replays the full
  set offline, and a smoke run re-records only its own items, so CI stays red until the full run is
  committed. Use smoke runs (`make eval-live YES=1`, about $0.80, cap $2) to try wording before
  that. Put the scoreboard change in the PR description.
  **A release gets the full run too**, unless the last one already covers everything it ships.
- **Model IDs are pinned.** A new model is adopted only after an eval comparison.
- **No paid AI calls on push or PR.** CI replays recorded fixtures. Live evals are a manual
  workflow with a budget cap.
- **The development AI budget is $25/month**, across Anthropic and Voyage. Use the fake transport
  for UI and most development work. Size live eval runs to fit.
- **Tool results that contain user-written text are untrusted data.** Turns that process them get no
  proposal tools.

---

## Research and sources

**Verify every statutory figure against the official source, in the session that writes it.** Use
the state labor department sites (CA DIR, CO CDLE, TX TWC) or the statute itself, never memory.
Search the web freely: that research is part of the job, not a detour from it.

**Record what was read and when**, next to the figure:

> Source: <statute and section>, read from <official site> on <YYYY-MM-DD>.

The handbook is fictional company policy and is labeled as demo content, not legal advice.

---

## Design

- **`docs/design/` is the visual source of truth.** The owner designs in Claude Design and hands off
  screenshots plus `notes.md` guidelines. Where they disagree with any palette in the plan, the
  design wins.
- **A phase's UI stage does not start until its screens are in `docs/design/`.** Backend stages do
  not wait.
- **Use theme tokens, never raw hex, in components.**

---

## Deployment

**Held.** Open Door deploys to AWS (ECS Fargate on the shared portfolio cluster) as the very last
step, when the owner deploys all portfolio apps together. Until then everything is built to be
deploy-ready, and nothing is deployed.

---

## Architecture (summary; the detail is in the spec)

```
apps/web/              React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui (restyled)
apps/api/              FastAPI + SQLAlchemy 2 (async) + Alembic, managed with uv
  app/domain/timeoff/  PURE engine: no framework imports (enforced by import-linter)
  app/policy/          can(actor, action, resource)
  app/ai/              agent loop, tool registry, guard, prompts, proposals, budgets
  app/modules/         people, handbook, timeoff, cases, sandbox, audit
handbook/              the fictional handbook, as markdown with section IDs
evals/                 datasets, offline replay and live runners, scoreboard
docs/                  roadmap, spec, plans, ADRs, design handoff, governance docs
```

`AI_TRANSPORT` picks the model transport: `anthropic`, `scripted`, or `replay`. `scripted` is the
default for development, the browser tests, and the proxy check. `replay` is for the eval harness
only: the app refuses it everywhere. Production refuses anything but `anthropic`.

---

## Commands

Prerequisites: Node 24, uv, and Docker Desktop running.

```
make setup      install dependencies; create apps/api/.env from .env.example
make db         start Postgres (127.0.0.1:5433), migrate, then create the login users
make ingest     load and publish the handbook from handbook/ and its committed embeddings
make embed      fetch missing embeddings from Voyage (needs VOYAGE_API_KEY); commit the cache
make eval-retrieval  score handbook search against the labeled questions (needs `make db`; no network)
make eval-offline  replay the recorded assistant evals (needs `make db`; no network)
make eval-live  paid; smoke by default, `SET=full` or `SET=effort`, and `YES=1` to run
make dev        Postgres, migrations, API (:8000) and web app (:5173) together
make check      everything CI runs; needs `make db` first
make e2e        the browser tests (Playwright, Chromium) against the real API on :8100
make proxy-check  the turn stream through a strict nginx (needs `make db` and Docker)
make captures   a local report of each design beside the build (needs `make db` and a network; not in CI)
make openapi    after changing an API route: regenerate the schema and the web client
make audit      scan for leaked secrets and vulnerable dependencies
```

Run a single API test: `cd apps/api && uv run pytest tests/test_health.py -q`. Run a single web
test: `cd apps/web && npx vitest run src/lib/api-fetch.test.ts`. Run a single browser test:
`cd apps/web && npx playwright test e2e/session.spec.ts`. The first `make e2e` (and so the first
`make check`) downloads Chromium, about 170 MB. The component gallery is at `/gallery` in
development and never in a production build.

**The database has three URLs**, all in `apps/api/.env` (see `.env.example`):

- `DATABASE_URL` is the API's own login, `od_app_login`. It owns nothing, row-level security
  applies to it, and the tests connect as it.
- `MIGRATION_DATABASE_URL` is the database owner. Alembic and the bootstrap script connect as it.
- `CLEANUP_DATABASE_URL` is the cleanup login, `od_cleanup_login`, which can delete only expired
  sandboxes.

`make db` does four things in order: it starts Postgres, applies the migrations, runs
`apps/api/scripts/bootstrap_db_users.py`, which creates the login users from those URLs, and
loads the handbook (`make ingest`) from `handbook/` and its committed embeddings.
`make migrate` applies new migrations on their own, and `make bootstrap-db` reruns the script
after a password changes. `make migrations-roundtrip` undoes and reapplies every migration, which
wipes the data.

---

## Conventions

- **Units live in the field name:** `amountMinutes`, `durationMs`. Never a bare `amount`.
- **Server state lives in TanStack Query. The chat session lives in a Zustand store.** Shareable UI
  state lives in the URL. There is no Redux.
- **Timestamps are UTC.** Leave dates are calendar dates in the location's timezone.
- **Keep [`docs/DATA-INVENTORY.md`](docs/DATA-INVENTORY.md) current.** A new table, column,
  cookie, or log field updates it in the same change: what it holds, why, who can see it, and how
  long it's kept.

---

## Environment gotcha

**A Claude agent shell may export `ANTHROPIC_API_KEY` as an empty string.** The settings now ignore
an empty or blank `ANTHROPIC_API_KEY` or `VOYAGE_API_KEY` in the environment (a settings source
drops only those two when blank), so the key in `apps/api/.env` wins and no `env -u` is needed. It
was learned on the owner's EMS project and fixed in Phase 4, stage 1.
