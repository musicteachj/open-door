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
- **Open a PR when unmerged work reaches about 1,500 lines, or at a stage boundary, whichever comes
  first.** Size is what breaks reviews, both for tools and for people, so size is the trigger.
- Before creating a PR:
  - CI is green (`make check` locally mirrors it).
  - `CHANGELOG.md` is updated.
  - The roadmap status is current.

---

## Writing

- **American English everywhere:** docs, UI copy, code comments, identifiers, and commit and PR
  text. Write "color", "organization", "canceled", "labeled", "behavior".
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

- **A change to a prompt, tool schema, or the guard needs the offline evals green and a live eval
  run before the PR.** Put the scoreboard change in the PR description.
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

---

## Conventions

- **Units live in the field name:** `amountMinutes`, `durationMs`. Never a bare `amount`.
- **Server state lives in TanStack Query. The chat session lives in a Zustand store.** Shareable UI
  state lives in the URL. There is no Redux.
- **Timestamps are UTC.** Leave dates are calendar dates in the location's timezone.

---

## Environment gotcha

**In a Claude agent shell, `ANTHROPIC_API_KEY` may be exported as an empty string**, and
`pydantic-settings` gives real environment variables precedence over `.env`. The empty value then
silently shadows the key in `apps/api/.env`. This was learned the hard way on the owner's EMS
project. When running the API from an agent shell, unset it first:

```
env -u ANTHROPIC_API_KEY uv run uvicorn app.main:app --reload
```
