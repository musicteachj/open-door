# Data inventory

Every piece of data Open Door stores: what it holds, why it's kept, who can see it, and how long it
stays. Update this file in the same change as any new table, column, cookie, or log field.

Every person in Open Door is fictional. Each visitor gets a sandbox company, seeded with the same
120 made-up people, and the whole sandbox is deleted 24 hours after it is created. The
[Phase 1 spec](specs/2026-10-03-phase-1-tenancy-identity-permissions.md) has the design behind
this, and [ADR 0007](adr/0007-session-lifetime.md) explains why sessions last as long as the
sandbox.

## How long data is kept

**Everything in a sandbox lives for 24 hours.** `tenants.expires_at` is set to 24 hours after
creation. Every other row belongs to a tenant and is deleted with it, through the foreign keys'
`ON DELETE CASCADE`. A session is refused as soon as it expires, even before its row is deleted.
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
| `holiday_date`, `name` | The company holiday calendar for `anchor_date`'s year and the next | The time-off engine skips these days (Phase 5). |

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
| `action`, `target_type`, `target_id` | What was done, and to what | Phase 1 records `sandbox.created`, `session.persona_switched`, `session.ended`, and `person_private.read`. |
| `before`, `after` | Non-private fields only, such as `personaKey`, or the names of the private fields read | Never private values, so a privacy deletion request never means editing this log. |
| `proposal_id` | The confirmed proposal, from Phase 5 | Ties an executed action to what the person confirmed. |
| `request_id` | The request's ID | Matches the event with that request's log lines. |

Append-only: the API can add and read events but never change or delete them. Visible to the API
within its own sandbox. No endpoint shows them yet. Deleted with the sandbox, which is the demo
choice described above.

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
- **Assistant questions are sent from Phase 4,** so a question can be searched by meaning.
- **The run-time query cache holds hashes and vectors, never text.**
- **The committed cache files** (`handbook/embeddings/`) hold vectors keyed by hashes of the
  model, the size, and the text, not the text itself.
