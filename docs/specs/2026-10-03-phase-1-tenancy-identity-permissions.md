# Phase 1: tenancy, identity, and permissions

Written 2026-10-03. This spec goes deeper on Phase 1 of the
[product design](2026-09-29-open-door-design.md). Where the two disagree, this one is newer and
wins. The differences are listed under [Changes from the product design](#changes-from-the-product-design).

**Goal:** every visitor gets an isolated sandbox company, signs in as one of four personas through
a session cookie, and can read only what their role allows. The database enforces tenant isolation,
and one pure function decides who can see what.

**Done when** CI is green and these are proven by tests:

- **The permission matrix:** each persona against each target and action, over HTTP.
- **Isolation:** one tenant can't see another's data, through the API or in SQL. An unset tenant
  sees nothing, even on a reused database connection.
- **Row-level security coverage:** every tenant table has it enabled and forced. `sessions` is the
  only exception.
- **Seeding:** a sandbox seeds in under 2 seconds at p95.

---

## Decisions made while designing (owner-approved, 2026-10-03)

- **Phase 1 ships real endpoints.** These include creating a sandbox, switching persona, signing
  out, "who am I", and reading the directory and private details. So the permission matrix and
  isolation are proven over HTTP with real cookies and CSRF checks, and Phase 2 is only screens.
- **The policy layer covers only Phase 1's data:** the directory and private details. Time off
  (Phase 5) and cases (Phase 6) add their rules to the same matrix test when their tables exist.
- **A migration creates the database roles, and a bootstrap script creates the login users.** The
  permissions are versioned with the schema, and no password is ever stored in git.
- **The design was checked against published standards before it was written down.** The
  standards were:
  - OWASP ASVS 5.0 and the OWASP cheat sheets
  - the PostgreSQL 17 documentation
  - NIST SP 800-63B Rev. 4
  - California's employee-data rules

  Every finding was adopted, including two optional defense-in-depth items. See
  [Sources](#sources).

---

## Changes from the product design

| Product design said | Phase 1 does | Why |
|---|---|---|
| The seed generator bulk-inserts with `COPY` | `INSERT … SELECT FROM unnest(…)`, one statement per table | Postgres refuses `COPY FROM` into a table under row-level security. This was checked on the development database on 2026-10-03. |
| Policies read `current_setting('app.tenant_id', true)` | Policies call `app.current_tenant_id()`, which maps `''` to NULL | After one transaction sets the value locally, the next transaction on the same connection sees `''`, not NULL. `''::uuid` raises an error instead of returning zero rows. This was checked on 2026-10-03. |
| A double-submit CSRF token on state-changing requests | A session-bound CSRF token, plus a same-origin check on every state-changing request, including sandbox creation | Creating a sandbox swaps the visitor's session, so it needs protection too (login CSRF). The same-origin check uses Fetch Metadata. |
| Cookies named for the app | `__Host-od_session` and `__Host-od_csrf` | The `__Host-` prefix makes the browser enforce Secure, no `Domain`, and `Path=/`. |
| Tenant isolation in the database; field rules in the policy layer | Also a second, database-level rule: private details are visible only to the person themselves and to HR | Defense in depth for invariant 1, before the assistant's tools read this data in Phase 4. |

---

## Data model

Every table except `tenants` and `sessions` is a **tenant table**: it has `tenant_id`, row-level
security is enabled and forced, and it is scoped by the policies below. All IDs are UUIDs.
Timestamps are `timestamptz` in UTC, and calendar dates are `date`.

| Table | Columns | Notes |
|---|---|---|
| `tenants` | `id`, `created_at`, `expires_at`, `anchor_date` | One sandbox company. `expires_at` is 24 hours after creation. `anchor_date` is the date the seed data is relative to. Row-level security limits a tenant to its own row. |
| `locations` | `id`, `tenant_id`, `code`, `name`, `city`, `state`, `timezone` | Denver HQ (CO), the Oakland store (CA), the Austin warehouse (TX). |
| `departments` | `id`, `tenant_id`, `name` | About eight. |
| `people` | `id`, `tenant_id`, `given_name`, `family_name`, `title`, `department_id`, `location_id`, `manager_id`, `work_email`, `employment_type`, `hire_date`, `is_hr_admin`, `persona_key` | The directory tier. `employment_type` is `salaried` or `hourly`. `persona_key` is `priya`, `mateo`, `marcus`, `dana`, or null. |
| `person_private` | `person_id`, `tenant_id`, `personal_email`, `phone`, `home_address`, `date_of_birth` | Visible only to the person themselves and to HR. |
| `holidays` | `id`, `tenant_id`, `location_id`, `holiday_date`, `name` | Per location and year, for the Phase 5 engine. |
| `sessions` | `token_hash`, `csrf_hash`, `tenant_id`, `person_id`, `created_at`, `expires_at` | **Outside row-level security**, because a session is looked up before the tenant is known. Both hashes are SHA-256. `expires_at` is copied from the tenant. |
| `audit_events` | `id`, `tenant_id`, `occurred_at`, `actor_person_id`, `via`, `action`, `target_type`, `target_id`, `before`, `after`, `proposal_id`, `request_id` | Append-only for the app. `via` is `ui`, `assistant`, or `system`. `proposal_id` is used from Phase 5. |

**Being a manager is derived, never stored.** A person is a manager if anyone reports to them.
Their reports, direct and indirect, come from a recursive query on `manager_id`. That query runs on
every request and is never cached in the session.

**Rules that keep tenants apart inside the schema:**

- **Unique rules start with `tenant_id`.** For example `(tenant_id, work_email)`,
  `(tenant_id, persona_key)`, `(tenant_id, code)`, and `(tenant_id, location_id, holiday_date)`.
  Postgres checks uniqueness across all rows, whatever the row-level security says. A global
  unique rule would leak whether a value exists in another tenant, and it would also stop the
  second sandbox from seeding, since every sandbox has the same people. A single-column primary
  key on a server-generated UUID, such as `id` or `person_private.person_id`, is the only
  exception.
- **References stay within the tenant.** Every parent table has `UNIQUE (tenant_id, id)`, and
  every reference is a composite foreign key, such as
  `(tenant_id, manager_id) REFERENCES people (tenant_id, id)`. The same applies to department,
  location, `person_private`, holidays, sessions, and the audit actor. Children cascade from
  `tenants` with `ON DELETE CASCADE`. References between children use the default `NO ACTION`,
  so one cascading delete can remove them together.
- **Indexes start with `tenant_id`.** For example `(tenant_id, family_name, given_name, id)` for
  directory paging, and `(tenant_id, manager_id)` for the reporting tree.
- **Audit IDs are random UUIDs, not a sequence.** A shared sequence would let one tenant estimate
  another's activity.

---

## Row-level security and database roles

### Helper functions, in schema `app`

| Function | Returns |
|---|---|
| `app.current_tenant_id()` | `NULLIF(current_setting('app.tenant_id', true), '')::uuid` |
| `app.current_person_id()` | `NULLIF(current_setting('app.person_id', true), '')::uuid` |
| `app.current_is_hr()` | `coalesce(NULLIF(current_setting('app.is_hr', true), '')::boolean, false)` |

These functions are `STABLE` SQL functions. They are never `LEAKPROOF` and never
`SECURITY DEFINER`. Policies call them as `(SELECT app.current_tenant_id())`, so Postgres
evaluates them once per query instead of once per row.

### Policies

- **Every tenant table** has `tenant_isolation`, defined as `FOR ALL TO od_app`, with both
  `USING` and `WITH CHECK` set to `tenant_id = (SELECT app.current_tenant_id())`.
- **`tenants`** has:
  - `tenant_self` for `od_app`, on `id = (SELECT app.current_tenant_id())`
  - `cleanup_select` and `cleanup_delete`, `FOR SELECT` and `FOR DELETE TO od_cleanup`, on
    `expires_at < now()`. Both are scoped with `TO od_cleanup`, so the app never inherits them.
- **`person_private`** also has `private_self_or_hr`, which is
  `AS RESTRICTIVE FOR SELECT TO od_app USING (person_id = (SELECT app.current_person_id()) OR (SELECT app.current_is_hr()))`.
  It applies to reads only, so seeding can still insert rows.
- **No policies for the owner.** With row-level security forced, the schema owner sees no rows
  through these tables.
- **Views, if any are added, use `security_invoker = true`.** Phase 1 has none.

### Roles

The roles are created by a migration and **cannot log in**.

| Role | Grants | Notes |
|---|---|---|
| `od_app` | `SELECT, INSERT` on `tenants`, `locations`, `departments`, `people`, `person_private`, `holidays`, `audit_events`. `SELECT, INSERT, DELETE` on `sessions`. `USAGE` on schemas `public` and `app`. | Owns nothing. No `BYPASSRLS`. No `UPDATE` anywhere yet; later phases add exactly what they need. Never `TRUNCATE`, `REFERENCES`, or `TRIGGER`, because `TRUNCATE` ignores row-level security. |
| `od_cleanup` | `SELECT, DELETE` on `tenants`. `USAGE` on schemas `public` and `app`. | Its policies only let it see and delete expired tenants. Child rows go with the tenant through the foreign-key cascade. The scheduled cleanup job is Phase 8. |
| the migrator | owner | The database owner that runs Alembic. In development this is the Compose superuser. |

A test asserts the **exact** grant set, so a new table that forgets its grants fails closed, and an
over-broad grant fails the build.

### Login users

`apps/api/scripts/bootstrap_db_users.py` creates the login users and grants them the roles. It's
idempotent: it creates each user or updates its password.

- `od_app_login` gets `od_app`, and `od_cleanup_login` gets `od_cleanup`.
- **`make db` does three things in order:** it starts Postgres, applies the migrations, and runs
  this script. `make migrate` still applies new migrations on their own.
- **Passwords come from the connection URLs themselves:** `DATABASE_URL` and
  `CLEANUP_DATABASE_URL`. That makes each URL the single source of truth for its user.
- **The script runs as the migrator.** CI runs it after the migrations, like `make db`.
- In AWS the URLs come from Secrets Manager, which is Phase 9's secrets contract.
- In development the passwords are throwaway values in `.env.example`.

### Settings

| Variable | Used by |
|---|---|
| `DATABASE_URL` | The API, connecting as `od_app_login`. |
| `MIGRATION_DATABASE_URL` | Alembic and the bootstrap script, connecting as the owner. |
| `CLEANUP_DATABASE_URL` | Optional. The cleanup role's tests now, and the Phase 8 job. |
| `APP_ORIGIN` | The same-origin check. In development it's `http://localhost:5173`. |

The health check keeps using a bare connection on the app engine, so it stays independent of row
security.

**The API sends no CORS headers.** The web app reaches the API on the same origin: through Vite's
proxy in development, and through one load balancer in production. So the browser blocks every
cross-origin read by default, which is stricter than allowing one origin.

---

## Request flow

### Sessions

1. Read the `__Host-od_session` cookie and hash it with SHA-256. Look the hash up in `sessions`
   where `expires_at > now()`. If there's no match, return **401**.
2. Open one database transaction for the request. SQLAlchemy's `after_begin` hook runs
   `set_config(…, true)` for `app.tenant_id` and `app.person_id`, taken from the session, and
   clears `app.is_hr` to `''`. It sets all three on every transaction, using `''` when a value
   is absent.
3. Load the actor in that transaction:
   - the person's directory row
   - `is_hr_admin`
   - their report IDs, from the recursive query

   Then set `app.is_hr` with `set_config(…, true)`.
4. The route runs. The transaction commits only if the request succeeds.

The engine is reached through a typed `get_engine(request)` dependency, which closes the Phase 1
backlog item.

### Cookies and CSRF

| Cookie | Holds | Attributes |
|---|---|---|
| `__Host-od_session` | the session token, 32 random bytes | `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=<seconds until the tenant expires>` |
| `__Host-od_csrf` | the CSRF token, 32 random bytes | `Secure; SameSite=Lax; Path=/; Max-Age=…`. It is readable by the page, which echoes it in a header. |

**Every state-changing request** (POST, PUT, PATCH, DELETE) passes two checks:

1. **Same origin.** If the `Sec-Fetch-Site` header is present, it must be `same-origin`.
   Otherwise `Origin` must equal `APP_ORIGIN`. If neither header is present, the request is
   refused with **403**.
   - This runs as plain ASGI middleware, so every new endpoint is covered by default.
   - Requests with a body must also be `application/json`.
2. **CSRF token, on session-bound requests.** The `X-CSRF-Token` header must hash to the
   session's `csrf_hash`, compared in constant time. If it doesn't, the request gets **403**.

**Session lifetime** is 24 hours absolute, the same as the tenant, with no idle timeout. A demo has
no way to sign back in, so an idle timeout would strand the sandbox. NIST SP 800-63B Rev. 4 allows
this at the assurance level that fits a demo. [ADR 0007](../adr/0007-session-lifetime.md) records
the decision and the concurrent-session behavior: each sandbox creation makes one session.

### Endpoints that change the session

- **`POST /api/v1/sandboxes`:**
  1. Passes the same-origin check. It needs no CSRF token, because no session exists yet.
  2. Deletes any session the request already carries.
  3. Creates a tenant with a random ID and seeds it.
  4. Starts a session for the chosen persona (default Priya) and sets both cookies.
- **`PUT /api/v1/session/persona`:** replaces the session row in one transaction, with a new
  session token **and** a new CSRF token. The old tokens stop working at once.
- **`DELETE /api/v1/session`:** deletes the session row and clears both cookies.

---

## The policy layer

`app/policy/` is pure Python. Import-linter forbids framework and database imports, with the same
contract as the time-off engine. It holds:

- `Actor`: `person_id`, `tenant_id`, `is_hr_admin`, and `report_ids` (a frozen set).
- `Action`: an enum. Phase 1 has `DIRECTORY_READ` and `PERSON_PRIVATE_READ`.
- `PersonResource`: the target `person_id`.
- `can(actor, action, resource) -> bool`: deny by default. An action without a rule returns
  `False`.

| Action | Self | Another employee | Manager, for a report | HR |
|---|---|---|---|---|
| `DIRECTORY_READ` | yes | yes | yes | yes |
| `PERSON_PRIVATE_READ` | yes | no | **no** | yes |

**Tenant scope isn't a policy rule.** Row-level security already guarantees that the target is in
the actor's tenant.

**Field allowlists:**

- **The directory card shows** `id`, given and family name, `title`, department, location (with
  state), manager (ID and name), and `workEmail`.
- **Only `/me` adds** `employmentType`, `isManager`, `isHrAdmin`, and `personaKey`.
- **Private details are** `personalEmail`, `phone`, `homeAddress`, and `dateOfBirth`.

A test asserts that the directory schema contains none of the `/me`-only or private fields.

---

## Audit and security logging

**`record_event(...)`** in `app/modules/audit` writes an `audit_events` row with:

- the actor
- `via`
- the action
- the target
- `before` and `after`
- the request ID

**Phase 1 records these actions:**

- `sandbox.created`
- `session.persona_switched`
- `session.ended`
- `person_private.read`

**`before` and `after` hold directory fields only.** A read of private details records the field
*names* it returned, never the values. A privacy deletion request then never means editing an
append-only log.

**Failures go to the JSON application log, not the audit table.** The logger is `app.security`,
and it records these events:

- `security.session_invalid` for a missing, unknown, or expired session
- `security.origin_rejected`
- `security.csrf_rejected`
- `security.authz_denied`

Each event carries the request ID and client IP, and the tenant, the actor, and the first 8
characters of the token hash when they're known. A rejected origin or an unknown session has no
tenant or actor yet. Raw tokens are never logged.

---

## The seed company

`app/modules/sandbox/seed.py` splits into two parts:

- **`build_company(tenant_id, anchor_date)`** is pure. It returns rows as dataclasses.
- **`insert_company(session, company)`** writes them with one `INSERT … SELECT FROM unnest(…)`
  per table.

**Every sandbox is the same company.**

- It's built from fixed name lists with a fixed random seed. There's no Faker dependency.
- IDs are `uuid5(tenant_id, stable_key)`, so they're unique per tenant and repeatable. Tenant IDs
  themselves are random.
- Dates are relative to `anchor_date`, so "last week" always means last week.

**About 120 people:**

| Location | People | Includes |
|---|---|---|
| Denver HQ, CO (`America/Denver`) | about 40 | leadership, HR (**Dana**, HR partner, `is_hr_admin`), finance, IT, merchandising |
| Oakland store, CA (`America/Los_Angeles`) | about 45 | **Marcus**, the store manager. **Priya** (salaried), **Leo**, and a few department leads report to him directly, and the leads manage the store's associates. Priya and Leo manage no one, so the employee persona never has manager powers, and Marcus has both direct and indirect reports. |
| Austin warehouse, TX (`America/Chicago`) | about 35 | **Mateo** (hourly) |

**Holidays** cover `anchor_date`'s year and the next year:

- The company calendar is New Year's Day, Memorial Day, Independence Day, Labor Day,
  Thanksgiving, and Christmas.
- A date that falls on a Saturday is observed on the Friday, and a Sunday date on the Monday.
- Only Denver HQ also closes the day after Thanksgiving. That gives the Phase 5 engine a real
  difference between locations.

**Private details are obviously fictional:**

- `example.com` personal emails
- `555-01xx` phone numbers
- made-up street addresses in each person's city
- dates of birth spread across plausible ages

**The target is under 2 seconds at p95.** A test creates 20 sandboxes and checks the 95th
percentile. A warm pool is added only if this is ever missed.

---

## API

All endpoints live under `/api/v1`. JSON uses camelCase, and errors use the existing RFC 9457
problem-details handlers.

| Method and path | Session | Returns |
|---|---|---|
| `POST /sandboxes` `{persona?}` | none | 201 `{tenant: {id, expiresAt}, me}`, and sets both cookies |
| `GET /me` | yes | `me`: the directory card plus the `/me`-only fields and `tenantExpiresAt` |
| `PUT /session/persona` `{persona}` | yes, plus CSRF | 200 `me`, and sets new cookies |
| `DELETE /session` | yes, plus CSRF | 204, and clears the cookies |
| `GET /people?cursor=&limit=` | yes | `{items: [directory card], nextCursor}`. 50 per page by default, at most 100. The cursor is opaque. |
| `GET /people/{id}` | yes | the directory card |
| `GET /people/{id}/private` | yes | the private details, and writes `person_private.read` |

**Error statuses:**

- **401** when the session is missing, unknown, or expired.
- **403** when the same-origin check fails, the CSRF token is wrong, or the policy denies.
- **404** when the row doesn't exist or belongs to another tenant. The two cases look the same,
  so nothing leaks. For `GET /people/{id}/private`, the policy check comes first, so anyone who
  is neither the person nor HR gets **403** for every ID, in any tenant. Only HR can reach the
  404, and that leaks nothing either.
- **422** when the input is invalid.

The OpenAPI schema and the web app's generated client are regenerated. The web app starts using
these endpoints in Phase 2.

---

## Testing

**Database tests** run against the real Postgres as `od_app_login`, the same login the API uses:

- **Row-level security coverage.** Every table with a `tenant_id` column, plus `tenants`, has
  row-level security enabled and forced. `sessions` is the only allowlisted exception.
- **Isolation.**
  - Tenant A can't see tenant B's rows.
  - An unset tenant sees zero rows.
  - **On one reused connection**, tenant A, then no tenant, then tenant B: no error, zero rows,
    and nothing of A's.
- **Grants.**
  - The exact grant set for `od_app` and `od_cleanup`.
  - `od_app` isn't a superuser, has no `BYPASSRLS`, and owns no tables.
- **Unique rules.** Every unique index on a tenant table starts with `tenant_id`, apart from
  single-column primary keys on server-generated UUIDs.
- **Cleanup.**
  - `od_cleanup_login` deletes an expired tenant, and its children go with it.
  - It can't delete a live tenant.
  - `od_app` can't see expired-tenant rows outside its own tenant.
- **The private-details rule.** In the same tenant, a non-HR person reading someone else's
  `person_private` row gets zero rows, even with a raw query.
- **The audit log is append-only.** `UPDATE` and `DELETE` on `audit_events` as `od_app` are
  refused.
- **Views.** Any view has `security_invoker` set. None exist yet, so the test guards the future.

**Seed tests:**

- `build_company` is deterministic: the same inputs give the same rows.
- The personas and reporting lines are as described above.
- Holiday dates are hand-checked for one year.
- The 20-run p95 is under 2 seconds.

**Policy tests:**

- The matrix in [The policy layer](#the-policy-layer), as a pure table-driven test.
- An unknown action is denied.

**HTTP tests.** These use a `https://testserver` base URL, because a client doesn't send Secure
cookies over plain HTTP.

- **The matrix per persona** (Priya, Mateo, Marcus, Dana) against self, Leo, and Dana, for the
  directory and private details:
  - Marcus reading Leo's private details gets **403**.
  - Dana reading them gets **200** and writes an audit event.
- **Cross-tenant.** A person ID from another sandbox returns **404**.
- **Same-origin.** A cross-site `Sec-Fetch-Site`, a wrong `Origin`, or neither header gets
  **403**, including on `POST /sandboxes`.
- **CSRF.** A missing or wrong token gets 403. After a persona switch, both the old session token
  and the old CSRF token are refused.
- **Expiry.** An expired session returns **401**.
- **Field allowlist.** The directory responses contain no `/me`-only or private fields.

**CI.** The API job runs the migrations as the owner, then the bootstrap script, then the tests as
`od_app_login`.

---

## Docs and housekeeping

- **[ADR 0007, session lifetime](../adr/0007-session-lifetime.md):** 24 hours absolute, no idle
  timeout, and why.
- **`docs/DATA-INVENTORY.md`:**
  - Each table and column: what it holds, why, who can see it, and how long it's kept.
  - The 24-hour delete is a demo choice. A real deployment would keep audit records for at least
    4 years, outside the tenant cascade. California Government Code §12946(a) requires employers
    to keep personnel and employment records for at least four years, and the Civil Rights
    Council's 2025 rules apply that to automated-decision system data.
- **`CLAUDE.md`:** the three database URLs, and the order `make db` runs things in.
- **`docs/BACKLOG.md`:** the later-phase findings below, each with its source.

---

## Delivery: four stages, four pull requests

Each stage is a pull request into `dev`. The spec first planned three. Building them showed the
third came to about 2,400 lines, so it was split into sessions and the directory API. See the
[implementation plan](../plans/2026-10-03-phase-1-tenancy-identity-permissions.md).

1. **Roles and tenancy:**
   - the settings for the three URLs and `APP_ORIGIN`
   - the bootstrap script, wired into `make db` and CI
   - the roles migration and the schema migration, with the policies, grants, indexes, and
     composite keys
   - the per-transaction hook and `get_engine`
   - all the database tests, and the migration round trip in CI
2. **The seed generator:** `build_company` and `insert_company`, with the determinism, persona,
   holiday, and timing tests.
3. **Sessions and signing in:**
   - the policy layer, tokens and cookies, sessions, the same-origin middleware, CSRF,
     `record_event`, and security logging
   - `POST /sandboxes`, `/me`, and `/session`, with their HTTP tests
   - the regenerated schema and client
4. **The directory API:**
   - the people endpoints and the HTTP permission matrix
   - the regenerated schema and client
   - the data inventory and the backlog

---

## Later phases

These are recorded in `docs/BACKLOG.md`.

- **Phase 3:** pin each tenant to a handbook version with a `tenants.handbook_version_id` column.
- **Phase 4, AI governance:**
  - Document why the assistant is not high-risk under EU AI Act Article 6(3). That requires no
    profiling and no employment decisions, recorded as Article 6(4) requires.
  - The Article 50 AI disclosure has applied since 2026-08-02.
- **Phase 5:**
  - Record the person who confirms a proposal as their own audit event.
  - Add `UPDATE` grants only where requests and approvals need them.
- **Phase 6:** encryption for case narratives.
- **Phase 8:**
  - rate limits and Turnstile on sandbox creation
  - the scheduled cleanup job
  - re-testing `set_config` under RDS Proxy or PgBouncer
  - database TLS with certificate checks, and secret rotation
  - deletion from backups

---

## Sources

All of these were read on 2026-10-03.

- **OWASP ASVS 5.0.0** (V3, V7, V8, V16):
  - https://github.com/OWASP/ASVS/tree/v5.0.0/5.0/en
  - https://github.com/OWASP/ASVS/releases
- **OWASP cheat sheets:**
  - Session Management: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
  - CSRF Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
  - Multi-Tenant Security: https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html
  - Authorization: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
  - Logging: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- **PostgreSQL 17 documentation:**
  - Row Security Policies: https://www.postgresql.org/docs/17/ddl-rowsecurity.html
  - CREATE POLICY: https://www.postgresql.org/docs/17/sql-createpolicy.html
  - CREATE VIEW: https://www.postgresql.org/docs/17/sql-createview.html
  - COPY: https://www.postgresql.org/docs/17/sql-copy.html
- **Local settings revert to an empty string:** the pgsql-bugs thread at
  https://www.postgresql.org/message-id/CA+Q86ij0KDCB0G45G509-8q0DNR611gcKG-sSM83GA1EBL7boA@mail.gmail.com.
  This was also reproduced on the development database on 2026-10-03.
- **Multi-tenant row-level security guidance:**
  - AWS: https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/
  - Supabase, on performance: https://supabase.com/docs/guides/troubleshooting/rls-performance-and-best-practices-Z5Jjwv
- **NIST SP 800-63B Rev. 4, session management:** https://pages.nist.gov/800-63-4/sp800-63b/session/
- **California Civil Code 1798.100 (CPRA):** https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1798.100.&lawCode=CIV
- **California Government Code §12946(a)** (as amended by SB 807, effective 2022-01-01): the
  four-year minimum for personnel and employment records. Source: Gov. Code §12946(a), read from
  https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=12946.&lawCode=GOV
  on 2026-10-03.
- **California Civil Rights Council, automated-decision system regulations** (effective
  2025-10-01), which apply that retention to automated-decision system data:
  https://calcivilrights.ca.gov/civilrightscouncil/rulemaking-actions/
- **EU AI Act, Annex III and Article 6:**
  - Annex III: https://artificialintelligenceact.eu/annex/3/
  - Article 6: https://artificialintelligenceact.eu/article/6/
  - These pages are an unofficial consolidation, not EUR-Lex. The 2027-12-02 date for Annex III
    obligations comes from law-firm summaries of the 2026 amendment.
