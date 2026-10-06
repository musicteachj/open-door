# Open Door roadmap

The living master plan. Every session starts here, and the status table is updated at the end of
every stage.

- **Design:** [`specs/2026-09-29-open-door-design.md`](specs/2026-09-29-open-door-design.md)
- **Original plan (frozen, never edited):**
  [`plans/2026-09-29-open-door-initial-plan.md`](plans/2026-09-29-open-door-initial-plan.md)
- **Scope limits:** [`WHAT-THIS-IS-NOT.md`](WHAT-THIS-IS-NOT.md)
- **Design handoff:** [`design/README.md`](design/README.md)
- **Project rules:** [`../CLAUDE.md`](../CLAUDE.md)

---

## Status

| Phase | Status | Branch | PR | Plan | Updated |
|---|---|---|---|---|---|
| Planning (repo, spec, roadmap, design brief) | Done | `docs/initial-planning` | [#1](https://github.com/musicteachj/open-door/pull/1) | [initial plan](plans/2026-09-29-open-door-initial-plan.md) | 2026-09-29 |
| 0 Foundation | Done | `chore/phase-0-ci` | [#2](https://github.com/musicteachj/open-door/pull/2), [#3](https://github.com/musicteachj/open-door/pull/3), [#4](https://github.com/musicteachj/open-door/pull/4) | [phase 0 plan](plans/2026-09-29-phase-0-foundation.md) | 2026-10-03 |
| 1 Tenancy, identity, permissions | Done. The whole-phase review found nothing high or medium; its fixes are in `fix/phase-1-review`. Released in `v0.1.0`. | `fix/phase-1-review` | [#8](https://github.com/musicteachj/open-door/pull/8), [#9](https://github.com/musicteachj/open-door/pull/9), [#10](https://github.com/musicteachj/open-door/pull/10), [#11](https://github.com/musicteachj/open-door/pull/11), [#14](https://github.com/musicteachj/open-door/pull/14) | [phase 1 plan](plans/2026-10-03-phase-1-tenancy-identity-permissions.md) | 2026-10-04 |
| 2 Design system, shell, sandbox entry | In progress: stage 6 of 6 (the directory and profiles) is built; the phase review comes after it merges. Stages 2 and 4 were two PRs each. | `feat/phase-2-directory` | [#23](https://github.com/musicteachj/open-door/pull/23), [#24](https://github.com/musicteachj/open-door/pull/24), [#25](https://github.com/musicteachj/open-door/pull/25), [#26](https://github.com/musicteachj/open-door/pull/26), [#27](https://github.com/musicteachj/open-door/pull/27), [#28](https://github.com/musicteachj/open-door/pull/28), [#29](https://github.com/musicteachj/open-door/pull/29) | [phase 2 plan](plans/2026-10-05-phase-2-design-system-shell-sandbox-entry.md) | 2026-10-05 |
| 3 Handbook and retrieval | Not started | — | — | — | — |
| 4 Assistant core (read-only) | Not started | — | — | — | — |
| 5 Time off | Not started | — | — | — | — |
| 6 Cases and escalation | Not started | — | — | — | — |
| 7 AI Ops console, reviewer experience, model decision | Not started | — | — | — | — |
| 8 Hardening and deploy-readiness | Not started | — | — | — | — |
| 9 Deploy to AWS | **Held** until the owner deploys all portfolio apps together | — | — | — | — |

**Design track (owner, in Claude Design):** in progress. The design system ("aubergine and
cinnamon", Instrument Sans) and all five Phase 2 screens (the landing page, the app shell, the
assistant home, the directory, and the global states) were approved on 2026-10-04; see
[`design/tokens.md`](design/tokens.md) and [`design/screens/`](design/screens/). **Phase 2's UI
stage is unblocked. Phase 2 is planned: see the
[spec](specs/2026-10-05-phase-2-design-system-shell-sandbox-entry.md) and the
[plan](plans/2026-10-05-phase-2-design-system-shell-sandbox-entry.md). Stages 1–5 are merged,
and stage 6 (the directory and profiles) is built. Next: after it merges, the Phase 2 review
(`/code-review high` on the phase's application code against `de75e53`), a small fix-up PR for
its findings, and the Done row, at effort `medium`.** Later phases' screens are designed
shortly before each phase. **Next for design (decided 2026-10-06):** a logo round now, then the
handbook browser and passage panel before Phase 3's UI stage. The brief's "Decisions from the
2026-10-06 brainstorm" records the rest.
Decided on 2026-10-04, changing the original plan:
- **Mockups are desktop only.** The build still adapts every screen to a phone's width, checked
  automatically at 390 px.
- **Each screen is designed in its final form.** Navigation items, cards, and the tour button
  appear as their phases build them.
- **Our own design system, on shadcn/ui,** not Material or Carbon.

The brief records these, and the Phase 2 decisions on the shell, the assistant home, and the
directory.

**Releases (`dev` → `main`):** `v0.1.0` (2026-10-04): planning, Phase 0, and Phase 1.

---

## Phases

Each phase ends somewhere demoable. Work happens on feature branches off `dev`, and releases go from
`dev` to `main` periodically. A phase's UI stage waits for its screens in `docs/design/`, and its
backend stages do not.

| Phase | Scope | Done when |
|---|---|---|
| **0 Foundation** | Scaffold for `apps/web` and `apps/api`, tooling, Postgres via Docker Compose, Alembic baseline, environment config validated at boot, `/health`, CI (`api`, `web`, `docs`, `workflows`, `security`, `changelog`), Dependabot, pre-commit hooks, `make dev` and `make check`, stubs for DESIGN and WHAT-THIS-IS-NOT | CI is green on a hello-world web app and API in the private repo |
| **1 Tenancy, identity, permissions** | Data model, row-level security and database roles, sessions, the policy layer, the seed company generator, the audit log | Proven by tests: permission matrix, isolation, RLS coverage, seeding under 2 seconds |
| **2 Design system, shell, sandbox entry** | Design tokens into Tailwind, the component library, a component gallery, the app shell, "Try Open Door" and the persona switcher, assistant home (no AI yet), the directory, an accessibility baseline | Screens meet their `notes.md` acceptance criteria and pass the owner's side-by-side review; axe is clean |
| **3 Handbook and retrieval** | The handbook (about 20 sections plus 3 state addenda), ingestion, Voyage embeddings, hybrid search with reciprocal-rank fusion, the applicability filter, the handbook browser with deep links | Retrieval eval at least 90% hit rate at 5, with the negative cases passing |
| **4 Assistant core (read-only)** | Agent loop, guard (with an escalation stub), citation UI, AI disclosure, append-only conversations, budgets, streaming hardening, the fake transport, red-team and Q&A evals, and a local production-like streaming check behind a reverse proxy (no deploy) | Cited, applicability-correct answers stream, including through the proxy; leak attempts are refused |
| **5 Time off** | The pure engine, request and approval UI, balance and proposal tools, stored proposals, audit, action and number evals | The employee-to-manager flow works in chat and in the UI |
| **6 Cases and escalation** | Minimal case model, guard-driven escalation, the HR queue, `summarize_case`, encryption and redaction, the escalation eval | A sensitive message becomes a confirmed case in the HR queue, audited and redacted |
| **7 AI Ops console, reviewer experience, model decision** | The console, the scoreboard generator, the "How it's built" page, the guided tour, the fairness eval, and the Opus 5.5 vs. Sonnet 5.5 comparison (within the budget) | Scoreboards are generated for the README and the app; the tour runs end to end; the owner picks the default model |
| **8 Hardening and deploy-readiness** | Threat model, AI governance doc, CSP and headers, Turnstile, the cleanup job, replay mode, a cost and load test, an accessibility audit, `/security-review`, a production Dockerfile, a secrets contract for AWS, and a deploy workflow drafted but disabled; demo video recorded locally | The checklist is closed; the production image runs locally end to end |
| **9 Deploy to AWS (held)** | ECS Fargate on the shared portfolio cluster, managed Postgres with pgvector, Secrets Manager, a load balancer idle timeout of at least 120 seconds, the OIDC deploy workflow enabled, the portfolio entry | Public URL live |
| **Stretch** | MCP adapter, dark mode, Slack or Teams, onboarding and benefits, SSO and SCIM, a handbook editor, multilingual answers | Optional |

---

## How work flows

- **Branches:** feature branches off `dev` (`feat/`, `fix/`, `chore/`, `docs/`), with PRs back into
  `dev`. Release PRs go from `dev` into `main`, merged with a merge commit and then tagged. The full
  rules are in [`../CLAUDE.md`](../CLAUDE.md).
- **Before every PR:** green CI, the changelog updated, and this table updated. Add
  `/code-review medium` if the PR changes code. Docs-only PRs get the automated checks and the
  owner's read-through instead. Release PRs always get the review.
- **Commits, pushes, and PRs** each need the owner's explicit approval.
- **CI** runs on every push to `dev` or `main` and on every PR:
  - Backend: lint, format, types, engine purity, migrations, tests.
  - Frontend: lint, format, types, tests, build, API-client drift.
  - Offline evals.
  - End-to-end tests with the fake transport.
  - Docs: spelling in American English, links between files, and leftover placeholders. This runs
    on every PR, docs-only ones included.
  - Workflows: mistakes and security problems in the workflow files. Every action is pinned to an
    exact commit.
  - Security scans.
  - The changelog check.

  No paid AI calls run in CI. Live evals are a manual workflow with a budget cap.

---

## Open items

- **GitHub Pro:** required checks and branch protection on a private repository need it. Without
  it, the merge gate is enforced by convention.
- **The default model:** Opus 5.5 or Sonnet 5.5, decided with Phase 7 eval data.
- **The managed Postgres host on AWS:** decided in the held Phase 9.
- **The old EMS deployment:** if it is still public, consider taking it offline, since it is being
  retired.
