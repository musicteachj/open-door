# Threat model

Written 2026-11-09, in Phase 8, Stage 1, before the phase's other hardening code. It names what
Open Door protects, who might attack it, where the trust boundaries are, and for each threat the
control that stops it and the test or eval that proves the control works. It briefs every later
Phase 8 stage and the whole-app security review at the end of the phase.

**Keep it current.** A change to a boundary (a new route family, a new vendor, a new login, a new
place the model reads text from) updates the matching table in the same change. A control marked
**Phase 8** is added in this phase; until its stage lands, the row says which stage brings it.

Related: the [spec's security section](specs/2026-11-05-phase-8-hardening-and-deploy-readiness.md#security),
[`AI-GOVERNANCE.md`](AI-GOVERNANCE.md), [`DATA-INVENTORY.md`](DATA-INVENTORY.md), and the ADRs in
[`adr/`](adr/README.md).

---

## What is protected

| Asset | Why it matters |
|---|---|
| Each sandbox's people data, above all private details (home address, phone, personal email, date of birth) | Fictional, but the product's promise is that only HR sees them, and only with an audit |
| Conversation text and case text | A person's own words about their job, health, or a complaint; stored only as ciphertext |
| The system prompt and its canary | Leaking it shows how to steer the assistant; the canary is a tripwire |
| The AI budget (per sandbox and per day) | The demo is public and free; the owner pays for every model call |
| The encryption keyring | It unwraps every conversation's and case's data key |
| The owner's accounts: Anthropic, Voyage, Cloudflare, AWS, GitHub | Keys or tokens here cost money or let someone change the code |
| The audit log and the AI Ops console | They are how a person checks what the assistant and HR did |

## Who might attack

| Attacker | What they can do |
|---|---|
| An anonymous visitor | Start sandboxes, call any public route, script requests, send any body or header |
| A visitor inside their own sandbox | Every persona is theirs to switch to, so they can read whatever any persona may read in that sandbox |
| Someone holding a leaked session cookie | Act as that persona until the session ends or the sandbox expires |
| Text that reaches the model | A question, a directory value, a case's words, or a tool result written to steer the model (prompt injection) |
| A compromised dependency or CI action | Run code in CI or in the image |
| An insider with database or AWS access | Out of scope beyond stating it: such a person can read the database and the keys |

## Trust boundaries

```
  browser ──(1)── load balancer ──(2)── API (uvicorn, FastAPI) ──(3)── Postgres (row-level security)
                                         │
                                         ├──(4)── Anthropic, Voyage, Cloudflare Turnstile
                                         │
                                         └──(5)── the model ⇄ the tools (server-side, actor from the session)

  GitHub ──(6)── CI (Actions) ──► the image ──► the deploy role (Phase 9)
```

1. **Browser and load balancer.** Everything from the browser is untrusted: cookies, headers,
   bodies, the `Origin`, and the forwarded address.
2. **Load balancer and API.** The API trusts the forwarded client address only from the load
   balancer's addresses.
3. **API and Postgres.** The API's login (`od_app_login`) owns nothing; row-level security decides
   which rows each transaction sees from the tenant context set from the server session.
4. **API and the vendors.** Outbound only. What is sent to each is listed in
   [`AI-GOVERNANCE.md`](AI-GOVERNANCE.md#what-is-sent-to-anthropic-and-voyage).
5. **The model and the tools.** The model chooses tools and arguments. The tools take the actor
   from the server session, never from the model, and the model never writes.
6. **GitHub, CI, and the deploy role.** Code and dependencies enter here. The deploy role is built
   in Phase 9.

---

## STRIDE per boundary

S spoofing, T tampering, R repudiation, I information disclosure, D denial of service, E elevation
of privilege. Paths are relative to `apps/api/` unless they start with `apps/web/`, `evals/`, or a
root folder.

### 1. Browser and load balancer

| | Threat | Control | Proof |
|---|---|---|---|
| S | A cross-site page sends a state-changing request with the visitor's cookie | `__Host-` cookies with `SameSite=Lax`; the same-origin check on unsafe methods (`app/modules/identity/same_origin.py`); the CSRF token in `X-CSRF-Token`, compared in constant time | `tests/test_same_origin.py`, `tests/integration/test_api_sessions.py` |
| S | A cross-site page reads data with a signed-in `GET` (a navigation, an `<img>`, a form) | **Phase 8, Stage 1:** CSRF on every signed-in API request, any method, which retires the per-route audited-read check. A refusal is a 403 of type `csrf-rejected`, which the web app treats as signed out | `tests/integration/test_csrf.py` |
| T | A huge body exhausts a task's memory | **Phase 8, Stage 1:** a 64 KiB body cap in the ASGI layer, by `Content-Length` and by counting a streamed body; schema ceilings at twice the real limits | `tests/test_body_limit.py` |
| I | The page loads script or style from somewhere else, or is framed | **Phase 8, Stage 2:** the API serves the built app with a strict CSP and a fresh nonce on every page (`app/web_app.py`), no inline script, `frame-ancestors 'none'`; HSTS, `nosniff`, `Referrer-Policy: same-origin`, a closed `Permissions-Policy`, and COOP on every response, a 500 included (`app/core/security_headers.py`; ADR 0020) | `tests/test_web_app.py`, `tests/test_security_headers.py`; CI runs the browser suite against the image, and any CSP violation fails the test (`apps/web/e2e/fixtures.ts`, proved by `e2e/csp-guard.spec.ts`) |
| I | API docs reveal every route in production | **Phase 8, Stage 1:** `/docs`, `/redoc`, `/openapi.json` are 404 in production; **Stage 2:** the image runs uvicorn with `--no-server-header` | `tests/test_app_state.py`, `make image-check` |
| D | A script starts sandboxes in a loop | **Phase 8, Stage 4:** Cloudflare Turnstile on `POST /sandboxes`, checked first; then 5 an hour and 20 a day per address and 500 a UTC day in all, counted in Postgres (`sandbox_starts`, migration 0019) and recorded under one advisory lock in a short transaction of its own, so two starts can't both slip under; 429 with `Retry-After` (ADR 0021, `app/modules/sandbox/limits.py`) | `tests/integration/test_sandbox_limits.py`, `test_sandbox_start.py`, `tests/test_turnstile.py` |
| D | A script spends the AI budget | Insert-only budget ledger, per-sandbox and per-day caps checked before every call (ADR 0011, `app/ai/budget.py`, `app/ai/admission.py`); a 429 with **Phase 8, Stage 1** `Retry-After` for the daily cap | `tests/integration/test_budget.py`, `tests/test_admission.py`, `tests/integration/test_turn_stream.py` |
| E | Another tab keeps showing HR's private view after this tab signed out | **Phase 8, Stage 1:** a `BroadcastChannel` message makes every tab refetch `/me` at once | `apps/web/src/lib/session-channel.test.ts`, `apps/web/e2e/session.spec.ts` |
| T | A stream that ends early is taken as finished, so a dropped crisis or "can't answer" stream reads as answered | **Phase 8, Stage 5:** every turn read to its end sends exactly one closing event (`turn.completed` or `error`), last; the chat page treats a stream with no closing event as stopped, for every kind, and the panel still shows | `tests/integration/test_turn_endings.py`, `apps/web/src/features/chat/store.test.ts` |

### 2. Load balancer and API

| | Threat | Control | Proof |
|---|---|---|---|
| S | A client forges `X-Forwarded-For` to dodge the limits or poison the security log | **Phase 8:** the `FORWARDED_ALLOW_IPS` setting (Stage 1) feeds uvicorn's `--forwarded-allow-ips` through the image's entrypoint (Stage 2); unset or empty, no proxy is trusted and the peer address is used | `tests/test_config.py`, `tests/test_image_check_script.py`, `make image-check` (a forged header is ignored, and trusted only from the named address); **Stage 4:** production requires the setting unless the origin is loopback, and a forged header from an untrusted peer doesn't change the counted address | `tests/test_config.py`, `tests/test_image_check_script.py`, `make image-check` (a forged header is ignored, and trusted only from the named address), `tests/integration/test_sandbox_limits.py` |
| I | A raw client address is stored | Only the access log and the security log see an address; **Stage 4:** the limits store an HMAC-SHA256 under `SANDBOX_IP_HASH_KEY` (an IPv6 address as its /64), which production requires and the development value can't fill; Cloudflare receives the address when a sandbox starts (`docs/DATA-INVENTORY.md`) | `tests/test_sandbox_address.py`, `tests/integration/test_sandbox_limits.py`, `tests/test_config.py` |
| D | Health checks load the database or flood the log | **Phase 8, Stage 1:** `/health/live` never touches the database; `/health` pings with a 2-second limit, cached for 1 second, one check at a time; both kept out of the access log | `tests/test_health.py` |
| D | The load balancer sends a request on a connection the task is closing, and the visitor gets a 502 | **Phase 8, Stage 7:** the load test found uvicorn closing idle connections after 5 seconds; the image now keeps them 130 seconds, longer than the load balancer's idle timeout (at most 120, Phase 9), so the load balancer closes them first. Only the load balancer connects to a task, so the longer wait holds no visitor's connection | `tests/test_image_check_script.py`, `make load` |

### 3. API and Postgres

| | Threat | Control | Proof |
|---|---|---|---|
| S | A code path (a bug, or a query without a tenant filter) inserts a session for another sandbox (the Phase 1 close-out finding) | **Phase 8, Stage 1:** row-level security on `sessions`: insert only for the transaction's sandbox, with an expiry no later than the sandbox's (migration 0017). Raw SQL as the app's login sets its own context, so that login's password stays a full-access secret (see the accepted risks) | `tests/integration/test_sessions_rls.py` |
| I | The app's login lists every sandbox's sessions | **Phase 8, Stage 1:** the `SELECT` policy shows only the presented token's row or the current sandbox's rows; a bare `SELECT` sees nothing | `tests/integration/test_sessions_rls.py` |
| I | A request reads another sandbox's rows | Row-level security on every tenant table, forced, with the tenant context set from the server session (ADR 0003, `app/db/tenancy.py`) | `tests/integration/test_row_level_security.py`, `test_isolation.py`, `test_grants.py` |
| I | A non-HR persona reads private details or case words | Restrictive policies on `person_private` and the case tables, `can(actor, action, resource)` in `app/policy/` | `tests/integration/test_private_details.py`, `test_cases_tables.py`, `tests/test_policy.py` |
| I | Ciphertext read from the database reveals text | AES-256-GCM under a data key per conversation and per case, bound to table, column, sandbox, and row (ADR 0015); **Phase 8, Stage 3:** a time-off denial's note too, with a data key per noted request (migration 0018) | `tests/test_encryption.py`, `tests/integration/test_encrypt_migration.py`, `test_denial_note_sealed.py` |
| I | A denial note is read by someone the request rules don't allow, or stored in plain text by the assistant's confirm | **Phase 8, Stage 3:** the note is opened only after the request's policy check, only for rows that have one, and in the conversation read only for the person who decided it; the audit log and the proposal hold no note | `tests/integration/test_denial_note_sealed.py`, `test_proposal_routes.py` |
| D | One value that won't decrypt breaks a page for everyone who sees it | **Phase 8, Stage 3:** a conversation that won't decrypt reads as unreadable (no turns, a fixed line, "Start a new conversation") and refuses questions with a 409; a denial note that won't decrypt is left off the page; the log names only the IDs | `tests/integration/test_unreadable_conversation.py`, `test_denial_note_sealed.py`, `test_proposal_routes.py` |
| T | A migration drops data its owner can't see under forced row-level security | **Phase 8, Stage 3:** 0018's data step runs with the table's forced row-level security off, so an owner that isn't a superuser still sees every row | `tests/integration/test_denial_note_sealed.py` (the data step on a scratch table) |
| I | The API process holds the owner's database credentials, which bypass row-level security | **Phase 8, Stage 1:** the API's settings load only `DATABASE_URL`; Alembic, the bootstrap script, the cleanup job, and the owner scripts read their own settings | `tests/test_config.py` |
| T | A request does tenant work before its tenant context is set, or on a second connection that sees another state | **Phase 8, Stage 1:** one transaction and one connection per signed-in request, the tenant context set in the lookup's own transaction. (A sign-out that commits during a request doesn't stop that request, as in any web app.) | `tests/test_deps.py`, `tests/integration/test_csrf.py` |
| R | An action leaves no trace | Every write and every private read records an audit event in the same transaction; audit rows can't be updated by the app | `tests/integration/test_audit_log.py` |
| D | A slow query or an idle transaction holds a connection | **Phase 8, Stage 1:** `statement_timeout` 10 s, `idle_in_transaction_session_timeout` 30 s, the confirm's `lock_timeout` 5 s | `tests/integration/test_timeouts.py` |
| D | A failed or hung end-of-turn write loses the crisis text a person was shown: the row stays `running`, then reads back as abandoned with no panel | **Phase 8, Stage 5:** the crisis verdict is stored on the running row in its own short write before the 988 and EAP text goes out (the text goes out even if that write fails), and any turn whose stored verdict is crisis shows the crisis panel on reload, whatever its status; the abandoned turn's console row stays redacted | `tests/integration/test_crisis_survives.py`, `tests/test_escalation_kind.py` |
| D | A database that stops answering (a failover, a silent network path) holds the crisis text past its bound | **Phase 8, Stage 5:** the two database steps before the crisis text (the verdict write and the HR contact lookup) run together and stop waiting at 2 seconds; a step past its bound is canceled and left to finish on its own, since `asyncio.timeout` waited for a canceled query's cleanup (the Opus 5.5 reviewer's frozen-link probe: no text in 120 s before, 2.04 s after) | `tests/integration/test_crisis_survives.py` |
| E | Sign-out leaves a persona switch's new session alive | **Phase 8, Stage 1:** each session carries a `family_id` that a switch copies, and sign-out deletes the family | `tests/integration/test_sessions_rls.py`, `test_api_sessions.py` |
| E | The cleanup login deletes more than expired data | **Phase 8, Stage 4:** `SELECT, DELETE` only on `tenants`, `ai_spend_daily`, `sandbox_starts`, and `handbook_versions`, with policies that show it only expired sandboxes, spend rows over 30 days old, and start counts over a day old; a trigger refuses deleting the newest published handbook version, and a pinned one is refused by its foreign key (migration 0019) | `tests/integration/test_cleanup_job.py`, `test_cleanup.py`, `test_grants.py` |

### 4. API and the vendors

| | Threat | Control | Proof |
|---|---|---|---|
| S | A forged Turnstile token passes | **Phase 8, Stage 4:** server-side `siteverify` with the client address and an idempotency key; only `success` for this app's host and the `start-sandbox` action passes; a failed or spent token is a 403, and an unreachable or misconfigured check a 503, so starts fail closed. Cloudflare's test keys are answered inside the API, and production refuses them unless the origin is loopback | `tests/test_turnstile.py`, `tests/test_config.py`, `tests/integration/test_sandbox_start.py` |
| I | A key leaks in a log, a problem response, or the image | Keys are `SecretStr` and never print; problems carry no exception text; gitleaks in pre-commit and CI; **Stage 2:** the keyring, `.env`, and tests stay out of the image (`.dockerignore`), and the test runs pass the keyring through the environment, never on the command line | `tests/test_config.py`, `tests/test_problems.py`, `.github/workflows/security.yml`, `make image-check`, `tests/test_image_container.py` |
| I | More personal data than needed reaches a vendor | The personal-data check refuses card and ID numbers before a question is sent, written in any script's digits (**Phase 8, Stage 3**); only the needed fields reach the model | `tests/test_personal_data.py`, `apps/web/src/lib/personal-data.test.ts`, `evals/assistant/personal-data-cases.json` |
| T | A test transport reaches production | Production refuses the scripted and replay transports and the test keyring at start; **Phase 8, Stage 3:** `make prod-local` runs the image with production settings, its own throwaway database, and its secrets passed through the environment only; **Stage 7:** production also refuses the load test's delay profile (`SCRIPTED_DELAY_PROFILE` other than `none`), on its own and with the real transport | `tests/test_transport_startup.py`, `tests/test_app_state.py`, `tests/test_key_provider_settings.py`, `tests/test_prod_local.py`, `make prod-local-check` |
| D | A vendor outage hangs a turn | Timeouts on every model call; the guard's 10-second limit (ADR 0009) | `tests/integration/test_turn.py`, `tests/test_guard.py` |

### 5. The model and the tools

| | Threat | Control | Proof |
|---|---|---|---|
| S | The model claims to act as another user | Every tool takes the actor from the server session; no tool input names an actor (invariant 1) | `tests/integration/test_tools.py`, the red team's `actions` group |
| T | The model writes data | The model only proposes; a person confirms, and the server re-validates and executes once (invariant 3, ADR 0004, ADR 0013) | `tests/integration/test_proposals.py`, `test_proposal_routes.py`, the `actions` eval |
| I | Prompt injection makes the model reveal private details or the prompt | No tool returns another person's private details; the prompt's canary closes the stream; the guard screens every question (ADR 0009) | the red team's `private_details`, `injection`, and `prompt_extraction` groups; `tests/integration/test_turn_canary.py` |
| I | A directory value written like an instruction steers the model | **Phase 8, Stage 6:** directory values reach the model as quoted data in the per-turn context | Stage 6's red-team item and golden hashes |
| I | Case words leak to a manager or coworker | Case tools return metadata only, to HR; the case summary is written by a call with no tools, with the words in an untrusted-text tag | the red team's `cases` group, `tests/integration/test_case_tools.py`, the case-summary eval |
| E | The model decides an employment matter or misroutes a crisis | The prompt's rules; the guard routes crisis and sensitive topics to people, with fixed human-written text (invariants 5 and 6) | the escalation eval, the red team's `routing` group, `tests/test_fixed_texts.py` |
| E | The model calculates a balance wrongly | The pure time-off engine calculates; the model only turns words into ISO dates (invariant 2) | the time-off engine's unit tests, the `numbers` eval |

### 6. GitHub, CI, and the deploy role

| | Threat | Control | Proof |
|---|---|---|---|
| T | A compromised action or base image runs in CI or ships | Every action pinned by commit, every Docker base image by digest (Stage 2); Dependabot opens updates as PRs, now for the production image's base images too (the proxy check's nginx and the pre-commit hooks are updated by hand, with `make check-workflows` keeping the hooks' versions equal to the other copies); the image's CA store has no emSign root | `.github/workflows/`, `.github/dependabot.yml`, `Dockerfile`, `make image-check` |
| T | A vulnerable dependency ships | `pip-audit` (over the app's locked dependencies only, **Stage 2**) and `npm audit` in CI (`security.yml`), `make audit` locally | `.github/workflows/security.yml` |
| I | A secret is committed | gitleaks in pre-commit and on every commit in CI, one version in all three places (**Stage 2**) | `.github/workflows/security.yml`, `.pre-commit-config.yaml`, `scripts/check_tool_versions.py` |
| E | CI spends money on the model | CI replays recorded fixtures; no paid call on push or PR; a live eval is a local, capped run | `make eval-offline` in CI |
| E | The deploy role does more than deploy | Phase 9 | Phase 9 |

---

## The OWASP Top 10 for LLM applications

The 2025 list, mapped to the seven invariants in [`CLAUDE.md`](../CLAUDE.md#invariants) and to
the evals that measure each.

| Risk | How Open Door meets it | Invariant | Evidence |
|---|---|---|---|
| LLM01 Prompt injection | The guard screens each question; untrusted text sits in escaped tags; the tools take the actor from the session; the model can't write | 1, 3 | red team `injection`, `actions`; the canary |
| LLM02 Sensitive information disclosure | No tool returns another person's private details; case tools are metadata only; the personal-data check | 1, 6 | red team `private_details`, `cases` |
| LLM03 Supply chain | Pinned models (ADR 0018), pinned actions and images, dependency audits | - | `security.yml`; the model decision board |
| LLM04 Data and model poisoning | The handbook is the only retrieval source, loaded by the owner and versioned; no learning from visitors | 4 | the retrieval eval |
| LLM05 Improper output handling | Answers render as text with citation markers checked by the server; no HTML from the model | 4 | `tests/test_citations.py`, `tests/test_turn_markup.py` |
| LLM06 Excessive agency | Proposals only, confirmed by a person, re-validated and executed once | 3, 5 | the `actions` eval, `tests/integration/test_proposals.py` |
| LLM07 System prompt leakage | The canary closes the stream; the prompt holds no secrets | 7 | red team `prompt_extraction`, `test_turn_canary.py` |
| LLM08 Vector and embedding weaknesses | Retrieval reads only the published handbook version pinned to the sandbox; embeddings hold handbook text only | 4 | the retrieval eval, `test_sandbox_handbook.py` |
| LLM09 Misinformation | Every policy claim cites the handbook, or the assistant says it couldn't find it and offers escalation | 4 | the Q&A, unanswerable, and judge metrics |
| LLM10 Unbounded consumption | Per-sandbox and per-day budgets, admission before every call, token limits, and (Phase 8) the sandbox start limits | 7 | `test_budget.py`; `make load` and [`CAPACITY.md`](CAPACITY.md) (Stage 7: the caps measured, with what one tour costs) |

Invariant 7 (every AI action audited, and the assistant says it is an AI) underlies the console and
the audit rows that let a person check every row above.

---

## Accepted risks

Each is accepted on purpose, with the reason.

- **Encryption binds a message to its row but not to its order.** Someone with database write
  access could reorder or replay ciphertexts within a conversation. Database write access is out of
  scope (the insider).
- **The personal-data check misses a card number written after other four-digit numbers.**
  Catching it would refuse ordinary lists of years.
- **The canary check misses look-alike letters.** It is a tripwire, not a boundary; the prompt
  holds no secret.
- **A sandbox's own personas can read what each persona may read.** The demo hands the visitor
  every persona, so switching to Dana shows HR's views by design.
- **The app's database login can act in any sandbox if its password leaks.** Row-level security
  reads the tenant context that each transaction sets for itself, so someone running SQL as
  `od_app_login` can set any sandbox's context and read or write as the API would there (a session
  they forge still can't outlive its sandbox). The API must be able to set the context, so SQL
  can't close this. The login's password is a secret held only by the API process (the API no
  longer holds the owner's or the cleanup login's), and Phase 9 keeps it in the secrets store.
- **One actor with many addresses can use up the day's sandbox starts.** The 500-a-day total
  bounds what new sandboxes can cost, and each start still needs a solved Turnstile check, but an
  IPv6 block wider than a /64 is many buckets, and 25 IPv4 addresses at 20 a day reach 500. New
  visitors then see "come back tomorrow" until midnight UTC; existing sandboxes keep working.
  Stage 7's load test kept the numbers: a start took about 100 ms at p95 on 1 vCPU, and the daily
  AI cap ends a busy day long before 500 starts do (at $3, about 17 tours get answers; at the
  $12 [`CAPACITY.md`](CAPACITY.md) suggests for 50 tours, about 65). So an actor who uses up the
  starts costs the seeding and the cleanup of up to 500 sandboxes, not AI spend. Phase 9 can alert
  when the total is reached (found by Stage 4's security review).
- **A deleted sandbox lives in database backups until they expire.** Phase 9's deploy keeps the
  backup window short and says how long.

## Residual risks Phase 9 owns

- The deploy role's permissions, the secrets store, and the KMS key provider (ADR 0015's
  amendment, ADR 0022).
- The load balancer's real addresses for `FORWARDED_ALLOW_IPS`, and TLS to the database (the
  certificate bundle).
- The cleanup job's schedule; until then `make cleanup` runs it by hand.
- Backup retention and the managed database's own access rules.

---

## Review

Re-reviewed at the end of Phase 8 by the whole-app security reviewer, who reads this document as
the brief and proves each finding with the smallest experiment. Each stage's close updates its
rows here.
