# 0016. The console reads its own rows, redacted when written, with no person ID

Status: Accepted · Date: 2026-10-31

## Context

Phase 7's AI Ops console shows HR a trace for every turn in the sandbox: the safety check's
verdict, the tools, the handbook sections, tokens, cost, and timing. Sensitive and crisis turns
must be redacted, because the handbook promises that a message alone never reaches HR (§2.2,
§2.3, §7.2).

The turn's metadata already lives on `ai_turns`, but that table's restrictive `own_rows` rule
shows each row only to its person, HR included (migration 0008). The table owner sees no rows
either, because row-level security is forced on it. And the project never uses
`SECURITY DEFINER` functions (migration 0002), so a function can't read across people on HR's
behalf.

## Decision

- **Each finished turn writes a console row** to `ai_console_turns`, in the transaction that
  finishes the turn: the metadata the console shows, copied as labels.
- **No row holds a person ID, a conversation ID, a name, or any text.** The asker is a role and a
  location. Nothing on the row links it back to a person (but see the amendment below).
- **A flagged turn's row is redacted when it's written:** only its date and its counts (tokens,
  cost, timings, model and versions). No time, turn ID, role, location, outcome, verdict, tools,
  or sections. A check constraint refuses a flagged row that holds any of them.
- **Only HR reads the rows,** by a restrictive rule on `app.current_is_hr()` inside the tenant,
  behind a new `console.read` policy action. The app's login may insert; nobody may update or
  delete (the rows go with the sandbox).
- **`ai_turns` and its `own_rows` rule are unchanged.**

## Rejected alternatives

- **Widen `own_rows` on `ai_turns` to let HR read:** every column of every turn, flagged ones
  included, would be in HR's reach, and redaction would depend on each query remembering to
  apply it.
- **A view or a `SECURITY DEFINER` function over `ai_turns`:** a view runs as its owner, whom the
  forced rules show nothing, or as the caller, who needs the widened rule above. A definer
  function breaks the project's rule against them.
- **Redact in the API only:** one query that forgets the rule shows a flagged turn's details.

## Consequences

The console can't show anything the row doesn't hold: no question text, no names, no per-person
view, and no conversation count (a conversation ID on flagged rows would tie them to the person's
other turns), so the tile is "cost per answered question". Role and location are coarse, not
anonymous: in a small team, or a four-persona demo, a person could be recognized by hand.
`AI-GOVERNANCE.md` says so. A turn later marked abandoned gets a redacted row, since its verdict
was never stored. Each new metadata field the console needs is a column here, written at the
turn's end.

## Amendment (2026-10-31, Phase 7 Stage 1)

Stage 1's security review corrected two things, and the owner agreed to both.

- **"Nothing in the database links a console row back to a person" was too strong.** HR's own
  database session can already read the spend ledger (`ai_spend`, open to the whole sandbox, with
  a turn ID per charge) and the audit log's `escalation.offered` events (shown to HR by Phase 6's
  rule, with the person and the turn). A flagged row's exact cost matches one turn's charges in
  the ledger, and that turn's audit event names the person. So a flagged row hides the turn's
  details (its time, verdict, tools, sections, and card), not the fact that a person was offered
  HR, or when, which HR could already see. What the match adds is the counts. No console row
  holds a person or conversation ID, and no route returns `ai_spend` or audit rows per turn: the
  console's routes read the ledger only as sums. A flagged row's counts can also hint whether it
  was a crisis (no answer, so no first-word time) or sensitive.
- **The safety check's `kind` isn't stored.** The console never shows it, and on an unflagged row
  it would put a topic (such as harassment or a medical accommodation) beside the time, role, and
  location. The column is dropped; the kind still decides whether a turn is flagged. The database
  also refuses an unflagged row whose category isn't ordinary.
- **The "Cards confirmed by a person" tile counts every confirmed card,** a flagged turn's
  included, from the audit log. Set beside the unflagged rows' card actions, it can show that a
  flagged turn offered a card of one action that someone confirmed. HR's session already reads
  those audit events and sees the time-off requests themselves, so the tile adds nothing new.
- **An abandoned turn's row says it was abandoned** (`abandoned`, always on a redacted row), so the
  escalation rate counts only turns the safety check flagged, and the page can word that row
  differently. It says only that a turn died.
