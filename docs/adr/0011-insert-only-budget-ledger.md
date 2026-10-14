# 0011. AI budgets are an insert-only ledger, reserved before each call

Status: Accepted · Date: 2026-10-14

## Context

Every visitor can ask the assistant questions that cost real money, and the app will run as
several tasks behind a load balancer. A cap checked after a call, or checked without a lock, lets
two concurrent questions both slip under it. The API's database role has no `UPDATE` anywhere it
doesn't need it, and a running counter would need one.

## Decision

- Before each model call (the guard's included), the server reserves the most the call could
  cost: the estimated input plus `max_tokens` of output, at list price.
- The reservation is a row in `ai_spend` (per sandbox, under row-level security) and in
  `ai_spend_daily` (every sandbox together, with no tenant column). It's inserted only after
  summing both under `pg_advisory_xact_lock`, and only if both stay under their caps.
- After the call, a `settle` row of (actual − reserved) brings the total to the real cost.
- The caps: $1.00 per sandbox and $3.00 a day, in settings. The Anthropic Console's monthly spend
  limit is the hard backstop.

## Rejected alternatives

- **A counter column on `tenants` or a counter table:** needs `UPDATE` grants, and a lost update
  under concurrency unless every write locks the row anyway.
- **Checking after the call:** the call that crosses the cap has already been paid for.
- **Counting tokens only:** the caps are about money, and the models' prices differ by twentyfold.

## Consequences

The locks last one transaction, so they're safe behind a connection pooler and across tasks. A
reservation whose task crashes is never settled and stays counted, which errs toward spending
less. Summing rows is cheap at sandbox scale. Phase 8's cleanup job deletes daily rows older than
30 days, and its load test checks the global lock under contention.
