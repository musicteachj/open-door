# 0012. Time-off balances are derived by the engine, not posted to a ledger

Status: Accepted · Date: 2026-10-20

## Context

Invariant 2 says the model never calculates balances or durations: a pure engine does, and every
result cites the handbook. The product design planned a `time_off_ledger` with posted rows for
each accrual, front-load, use, carryover, and expiry. Something would then have to post each
month's PTO on its last day and each January's sick grant, on time, in every sandbox. Sandboxes
live for 24 hours and there is no scheduled job until Phase 8, so a month's end or a new year can
pass during a sandbox's life with nothing to post it. A posted balance can also drift from the
rules it was posted under, and changing it needs `UPDATE` grants the API otherwise doesn't have.

## Decision

The database stores only facts a person or the seed created:

- one opening PTO balance per person, as of January 1 of the sandbox's anchor year (or the hire
  date, if later)
- the requests, with their status

The pure engine (`app/domain/timeoff/`) derives everything else on every read: the PTO earned on
each month's last day, the ceiling that pauses it, PTO taken, booked, and pending, each year's
sick grant by state, and what's available. It takes "today" as an input, from the location's time
zone. Every figure carries the handbook sections it came from.

## Rejected alternatives

- **A posted ledger with a job:** the conventional design, and easy to audit row by row. But it
  needs the job (or posting on read, which is the derivation with extra writes), `UPDATE` or
  compensating rows, and a rule for what happens when a request is approved after the month it
  falls in.
- **Computing from the hire date with no opening balance:** no seeded state at all, but every
  long-serving person would sit at the ceiling, and a realistic history would need years of
  seeded requests.

## Consequences

A month's end or a new year during a sandbox's life just works, and the balance can never
disagree with the rules, because it is the rules applied. A balance read costs one pass over a
person's requests for the year, which is cheap at sandbox scale. The audit trail for a balance is
its opening, its requests, and the engine's version. An HR adjustment, if one is ever needed,
would be a new kind of row the engine adds, not an edit.
