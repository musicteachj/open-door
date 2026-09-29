# 0006. TanStack Query and Zustand, no Redux

Status: Accepted · Date: 2026-09-29

## Context

Most of the web app's state is server data: people, balances, requests, cases, and the handbook. The
one piece of rich client state is the live chat turn.

## Decision

- **TanStack Query** owns server state: caching, refetching, and invalidation.
- **A Zustand store with a typed reducer** owns the chat session, modeled as a small state machine
  (idle, sending, streaming, awaiting confirmation, error, canceled).
- **URL search params** hold shareable UI state.
- **React Hook Form with Zod** handles forms.

When a proposal executes, the matching query caches are invalidated, so the chat and the pages
always agree.

## Rejected alternatives

- **Redux Toolkit:** capable, but here it would duplicate what TanStack Query already does for
  server state and add boilerplate for little benefit.
- **XState for the chat:** a full statechart library is more than a six-state reducer needs.

## Consequences

Less code, and a clear rule for where each kind of state lives. "Server state versus client state"
is the interview answer for why there is no Redux.
