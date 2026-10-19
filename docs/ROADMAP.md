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
| 2 Design system, shell, sandbox entry | Done. The whole-phase review found nothing high; its fixes are in `fix/phase-2-review`. Released in `v0.2.0`. | `fix/phase-2-review` | [#23](https://github.com/musicteachj/open-door/pull/23), [#24](https://github.com/musicteachj/open-door/pull/24), [#25](https://github.com/musicteachj/open-door/pull/25), [#26](https://github.com/musicteachj/open-door/pull/26), [#27](https://github.com/musicteachj/open-door/pull/27), [#28](https://github.com/musicteachj/open-door/pull/28), [#29](https://github.com/musicteachj/open-door/pull/29), [#30](https://github.com/musicteachj/open-door/pull/30), [#32](https://github.com/musicteachj/open-door/pull/32) | [phase 2 plan](plans/2026-10-05-phase-2-design-system-shell-sandbox-entry.md) | 2026-10-06 |
| 3 Handbook and retrieval | Done. The whole-phase review found five real bugs, none high; its fixes are in `fix/phase-3-review`. Released in `v0.3.0`. Its screens are designed ([#36](https://github.com/musicteachj/open-door/pull/36)) | `fix/phase-3-review` | [#37](https://github.com/musicteachj/open-door/pull/37), [#38](https://github.com/musicteachj/open-door/pull/38), [#39](https://github.com/musicteachj/open-door/pull/39), [#40](https://github.com/musicteachj/open-door/pull/40), [#41](https://github.com/musicteachj/open-door/pull/41), [#42](https://github.com/musicteachj/open-door/pull/42), [#43](https://github.com/musicteachj/open-door/pull/43), [#44](https://github.com/musicteachj/open-door/pull/44), [#45](https://github.com/musicteachj/open-door/pull/45) | [phase 3 plan](plans/2026-10-07-phase-3-handbook-and-retrieval.md) | 2026-10-14 |
| 4 Assistant core (read-only) | Done. The whole-phase review (`/code-review high` and a Fable 5.1 security review) found two medium bugs and no high ones; its fixes are in `fix/phase-4-review`. Next is the `v0.4.0` release | `fix/phase-4-review` | [#48](https://github.com/musicteachj/open-door/pull/48), [#49](https://github.com/musicteachj/open-door/pull/49), [#50](https://github.com/musicteachj/open-door/pull/50), [#51](https://github.com/musicteachj/open-door/pull/51), [#52](https://github.com/musicteachj/open-door/pull/52), [#53](https://github.com/musicteachj/open-door/pull/53), [#54](https://github.com/musicteachj/open-door/pull/54), [#55](https://github.com/musicteachj/open-door/pull/55), [#56](https://github.com/musicteachj/open-door/pull/56), [#57](https://github.com/musicteachj/open-door/pull/57) | [phase 4 plan](plans/2026-10-14-phase-4-assistant-core.md) | 2026-10-19 |
| 5 Time off | Not started | - | - | - | - |
| 6 Cases and escalation | Not started | - | - | - | - |
| 7 AI Ops console, reviewer experience, model decision | Not started | - | - | - | - |
| 8 Hardening and deploy-readiness | Not started | - | - | - | - |
| 9 Deploy to AWS | **Held** until the owner deploys all portfolio apps together | - | - | - | - |

**Design track (owner, in Claude Design):** in progress. The design system ("aubergine and
cinnamon", Instrument Sans) and all five Phase 2 screens (the landing page, the app shell, the
assistant home, the directory, and the global states) were approved on 2026-10-04; see
[`design/tokens.md`](design/tokens.md) and [`design/screens/`](design/screens/). **Phase 2's UI
stage is unblocked. Phase 2 is planned: see the
[spec](specs/2026-10-05-phase-2-design-system-shell-sandbox-entry.md) and the
[plan](plans/2026-10-05-phase-2-design-system-shell-sandbox-entry.md). Phase 2 is done and
released in `v0.2.0`. Phase 3 is planned: see the
[spec](specs/2026-10-07-phase-3-handbook-and-retrieval.md), the
[plan](plans/2026-10-07-phase-3-handbook-and-retrieval.md), and
[ADR 0008](adr/0008-handbook-retrieval.md). Phase 3 stage 1, the handbook text, is written
and fact-checked. Stage 2 loads it into the database with its embeddings, and pins each new
sandbox to the newest version. Stage 3 adds the search, the retrieval eval (100% hit rate at 5),
and the handbook API. Stage 4 builds the handbook components, shown in the gallery, and stage 5
the handbook pages, so anyone in a sandbox can browse, search, and deep-link the handbook. Stage 6
opens an Atlanta store and adds Georgia's rules and a lactation section for everyone (plan:
[`plans/2026-10-13-phase-3-stage-6-georgia.md`](plans/2026-10-13-phase-3-stage-6-georgia.md)).
The whole-phase review's fixes merged in #44, and the release review's in #45. **Phase 3 is done
and released in `v0.3.0`.**
Phase 4 is planned: see the
[spec](specs/2026-10-14-phase-4-assistant-core.md), the
[plan](plans/2026-10-14-phase-4-assistant-core.md), and ADRs
[0009](adr/0009-assistant-turn-and-guard.md), [0010](adr/0010-scripted-model-and-replay.md), and
[0011](adr/0011-insert-only-budget-ledger.md). Phase 4's base commit is `73b4942`. Stage 1, the
conversation store, budgets, and transports, merged in #49, and stage 2, the loop, the guard, and
the tools, in #50. Stage 3, the evals, merged in #51: two question sets, the
graders, a Sonnet 5.5 judge (92% agreement with independent Claude Opus grades; the owner chose
not to grade by hand), offline replay in CI, and `make eval-live`. Its first live runs cost $1.60
in all, and the assistant stays at low effort. Stage 4, the stream and the routes, merged in #52: the conversation routes, the streamed answer with its checks, Stop, and heartbeat, the personal-data check, `make proxy-check` behind a strict nginx, the regenerated web client, and [`AI-GOVERNANCE.md`](AI-GOVERNANCE.md). The Voyage training opt-out is recorded (#53), and screen 07, the conversation view, is designed and synced (#54). Stage 5, the conversation components, merged in #55. Stage 6, the conversation page, merged in #56: `/ask` streams cited answers from the real API, the browser tests run against the scripted model, and the first full live eval run is recorded ($6.78). The answer-quality follow-up merged in #57: a fresh full run ($8.02) has the red team, the citation checks, and the unanswerable items at 100% in every trial, the judge at 74% (up from 67%; the owner accepted it for Phase 4, and the 85% bar moves to Phase 7 with the judge's strictness and a retrieval miss), and the guard at no failures with a 10-second limit (ADR 0009 amended); the offline evals and CI now replay the full set. The whole-phase review ran on 2026-10-19 (three `/code-review high` runs, one per area, and one Fable 5.1 security reviewer). It found no high issues and two medium ones: a sensitive question the person stopped got no HR panel or audit event, and the model could fake a citation marker. Both are fixed, with about fifteen small ones, on `fix/phase-4-review`; the rest is in the backlog. Next: the `v0.4.0` release (cut the changelog, a release PR from `dev` to `main` with `/code-review medium`, a merge commit, the tag; its eval evidence is the 2026-10-19 full run, since no fix changed a prompt, a tool's description or schema, the guard, or retrieval), then Phase 5 planning at effort `high`.** Later phases' screens are designed
shortly before each phase. **Design for Phase 3 is done:** the handbook browser and the passage
panel were approved on 2026-10-07 (see [`design/screens/06-handbook/`](design/screens/06-handbook/notes.md)),
so Phase 3's UI stage is unblocked. **Design for Phase 4 is done:** the conversation view (screen 07) was synced in #54. **Next for design:** Phase 5's screens (time off, approvals, and confirm cards). The brief's "Decisions from the 2026-10-06
brainstorm" records the rest.
Decided on 2026-10-04, changing the original plan:
- **Mockups are desktop only.** The build still adapts every screen to a phone's width, checked
  automatically at 390 px.
- **Each screen is designed in its final form.** Navigation items, cards, and the tour button
  appear as their phases build them.
- **Our own design system, on shadcn/ui,** not Material or Carbon.

The brief records these, and the Phase 2 decisions on the shell, the assistant home, and the
directory.

**Releases (`dev` → `main`):** `v0.1.0` (2026-10-04): planning, Phase 0, and Phase 1. `v0.2.0`
(2026-10-06): Phase 2. `v0.3.0` (2026-10-14): Phase 3.

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
