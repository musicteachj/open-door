# 0003. Tenant isolation with Postgres row-level security

Status: Accepted · Date: 2026-09-29

## Context

Every demo visitor gets a private sandbox company. Isolation between sandboxes is both a safety
requirement and one of the things the demo exists to prove.

## Decision

Every tenant table has row-level security enabled and forced. The tenant is set per transaction
with `set_config('app.tenant_id', …, true)` in SQLAlchemy's `after_begin` hook. Policies read
`current_setting('app.tenant_id', true)`, so an unset tenant sees zero rows. The app role owns no
tables and cannot bypass the policies. A test asserts that every table with a `tenant_id` column has
row-level security enabled and forced.

## Rejected alternatives

- **Filtering by tenant in application code:** one forgotten `WHERE` clause leaks another tenant's
  data, and nothing catches it.
- **A schema or database per tenant:** strong isolation, but heavy to create per visitor and
  awkward for migrations.
- **A session-level `SET`:** it leaks the tenant across pooled connections.

## Consequences

`sessions`, the global budget counters, and the handbook tables sit outside row-level security by
design. A separate cleanup role deletes expired tenants. A pooler (RDS Proxy, PgBouncer) would need
asyncpg's `statement_cache_size=0`.
