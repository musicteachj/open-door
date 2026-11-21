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
- The caps: $1.00 per sandbox and $3.00 a day, in settings. A spend limit set in the Anthropic
  Console is the hard backstop.

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

## Amendment (2026-11-19): a monthly budget, paced by day

Phase 9a puts the public demo under a hard monthly AI budget (`AI_MONTHLY_BUDGET_USD`, which
production requires; `0` turns live AI off). The ledger stays insert-only, and a day's room comes
from the month's rows:

```
left_this_month = budget - every ledger row dated earlier this month (settled costs and open reservations)
allowance_today = min(left_this_month, max(multiplier x left_this_month / days_left_including_today, floor))
admit a reservation if today's rows + reservation <= min(allowance_today, AI_DAILY_BUDGET_USD)
```

- Days and months are UTC, from the database's clock. The multiplier (`AI_PACING_MULTIPLIER`,
  default 3) and the floor (`AI_DAILY_FLOOR_USD`, default $1.00) are settings. The allowance is
  rounded down to the ledger's six places.
- The shared names: `MonthlyBudget` and `allowance_today_usd` in `app/ai/pacing.py`, and `Caps.monthly`
  and `day_room` in `app/ai/budget.py`. `reserve`, `budget_state`, and the availability flag
  read the same `day_room`.
- `AI_DAILY_BUDGET_USD` stays, as a hard daily ceiling. Production sets it equal to the month so
  pacing alone governs, and the paid local runs keep using it as their cap.
- Without a monthly budget (development and the tests) only the daily cap applies, as before.
- The cleanup job's 30-day retention keeps every row of the current month (a month has at most 31
  days, and the job keeps rows from the last 30 days plus today), so the month's sum is complete.
- The day lock stays the only lock. A reservation made just after UTC midnight can miss the
  reservations still waiting on the previous day's lock (one per request in flight at midnight),
  each within that day's allowance, so the month's sum can be short by those.
- There is no sweeper. A reservation that is never settled counts at its full amount for the rest
  of the month, which is what a sweeper would produce elsewhere.
- A 429 for a used-up month sends no `Retry-After`: tomorrow does not help.

### Unbilled failures settle to zero, and the SDK no longer retries

The reserve-then-settle rule stays: a reservation is made before every model attempt, and a settle
never fails a call that was already paid for. What a failed call settles to depends on what the
provider does with it (`classify_status_error` in `app/ai/anthropic_transport.py`):

- **Spend limit** (a 400 with the Console's "You have reached your specified ... API usage limits"
  message, a 402 `billing_error`, or a 429 whose `error.details.error_code` (or `error.error_code`)
  is `enforced_spend_limit_reached`): settles to $0 and stops the assistant with the spend-limit
  text. At the guard it still gives the emergency numbers (911 and 988).
- **Refused before any work** (a 401, 403, 429 without that code, or any 529 or `overloaded_error`
  status): the provider doesn't bill it, so it settles to $0. A guard or summary failure of this
  kind carries zero usage, and the assistant's call settles to $0 in the turn.
- **Anything else** (a 500, a dropped connection, a timeout, or an `overloaded_error` event inside
  a 200 stream): the cost is unknown, so the reservation stays at its full amount. Output may have
  been billed, and so a failure after the person saw text never settles to $0 and is never retried.

The SDK's own retries are off (`MODEL_MAX_RETRIES = 0`): they sent up to three requests under one
reservation. In their place the turn makes one retry of its own, only for an unbilled 429 or 529
on the assistant's call, only when nothing was shown yet, after one second, and under a new
reservation. A recorded eval fixture never holds an unbilled failure (it would replay an outage).
The safety check (the guard), the case summarizer, connection errors, and 5xx responses get no
retry at all, so a single overloaded or dropped call ends that turn with its fixed text (an
unbilled overload settles to $0; a dropped connection keeps its reservation), which a demo accepts.
