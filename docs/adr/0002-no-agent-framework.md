# 0002. One assistant with tools on the Anthropic SDK, no agent framework

Status: Accepted · Date: 2026-09-29

## Context

The assistant has to answer mixed questions ("How much PTO do I have, and can I carry it over?"
needs personal data and the handbook in one turn), propose actions, and hand off sensitive topics.
The project exists partly to show how an agent works, in enough detail to explain in an interview.

## Decision

A single agent loop written directly on the Anthropic Python SDK. Handbook search and HR data are
tools scoped to the user; writes are proposal tools; a guard model screens each message first.

## Rejected alternatives

- **A router with fixed pipelines** (policy Q&A, my data, actions, escalation): each path is easier
  to test alone, but mixed questions become awkward and the product feels rigid.
- **LangGraph or a similar framework:** it provides graphs, checkpoints, and pause-for-approval, but
  it hides the mechanics this project is meant to show and adds a heavy dependency.

## Consequences

We own the loop: streaming, tool validation, iteration caps, cancellation, and cost accounting. The
tool registry does not depend on the transport, so an MCP server can be a thin adapter later.
