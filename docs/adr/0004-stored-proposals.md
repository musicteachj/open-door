# 0004. The model proposes; server-stored proposals are confirmed by a person

Status: Accepted · Date: 2026-09-29

## Context

The assistant can book time off, approve requests, and open cases. The owner's earlier EMS assistant
gated writes behind a confirm button, but the proposal was not tied to anything on the server: any
logged-in client could post any allowed action straight to the confirm endpoint.

## Decision

A write tool never writes. It creates an `ai_proposals` row bound to the user and the conversation,
with an expiry (15 minutes by default), and the UI shows a confirm card. The confirm endpoint locks
the row, re-validates everything against current data, executes once, and writes the audit event in
the same transaction. The outcome is appended to the conversation.

## Rejected alternatives

- **Letting the model write directly:** fast, but a single bad tool call changes real records with
  no person in the loop.
- **A client-held proposal:** it can be forged or replayed, which is the EMS weakness.

## Consequences

Double-clicks execute once. A stale proposal fails with a reason instead of doing the wrong thing.
Every AI-initiated change is traceable from audit event to proposal to conversation.
