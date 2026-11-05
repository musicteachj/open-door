# 0010. A scripted model for development and tests, and recorded replay for CI's evals

Status: Accepted · Date: 2026-10-14

## Context

No paid AI call may run on a push or a pull request, and every paid run needs the owner's OK.
The browser tests, UI work, and the reverse-proxy check need answers that stream realistically,
cost nothing, and never change, including slow, failing, and refused answers. The offline evals
need to replay what the real model actually did, so the graders and the plumbing are tested on
real output.

## Decision

One transport interface on the server, with three implementations chosen by `AI_TRANSPORT`:

- **`anthropic`:** the real SDK.
- **`scripted`:** a small rule-based stand-in for Claude, the default for `make dev`, the browser
  tests, and the proxy check. It runs the real loop, tools, database, citation mapping, and
  stream. It calls `search_handbook` and cites the first passage, a keyword guard drives the
  crisis and sensitive paths, and trigger phrases pick scenarios (refusal, not found, a long
  silence, a mid-stream error). The API refuses to start with it in production.
- **`replay`:** CI's offline evals. Live eval runs record each request and response, keyed by a
  hash of the request, with the sandbox and "today" fixed so the hashes repeat. A miss fails and
  names the item to re-record.

The browser-only fake that Phase 2 shipped is retired: the web app always talks to the API.

## Rejected alternatives

- **Recordings for everything:** realistic text, but every prompt or tool change would need a
  paid re-recording before the browser tests pass, and slow or failing answers can't be recorded
  on demand.
- **Keeping a browser-only fake as well:** quicker UI iteration without the API, but two fakes to
  keep in step, and the browser tests would skip the real stream.
- **Live model calls in CI:** cost and nondeterminism, which the project rules forbid.

## Consequences

The browser tests prove the whole stack except the model's judgment, which only the live evals
measure, and the README says so. A change to retrieval, a prompt, or a tool invalidates the
affected fixtures, so CI asks for a smoke run (about $1.20) to re-record them.
