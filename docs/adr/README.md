# Architecture decision records

Short, dated records of the decisions that shape Open Door: the context, the decision, and what was
rejected and why. A decision that is reversed gets a new record that supersedes the old one; old
records are never rewritten.

| # | Decision | Status | Date |
|---|---|---|---|
| [0001](0001-postgres-over-mongo.md) | Postgres with pgvector, not MongoDB | Accepted | 2026-09-29 |
| [0002](0002-no-agent-framework.md) | One assistant with tools on the Anthropic SDK, no agent framework | Accepted | 2026-09-29 |
| [0003](0003-row-level-security-tenancy.md) | Tenant isolation with Postgres row-level security | Accepted | 2026-09-29 |
| [0004](0004-stored-proposals.md) | The model proposes; server-stored proposals are confirmed by a person | Accepted | 2026-09-29 |
| [0005](0005-native-citations.md) | Native `search_result` citations, not prompted sources | Accepted | 2026-09-29 |
| [0006](0006-no-redux.md) | TanStack Query and Zustand, no Redux | Accepted | 2026-09-29 |
| [0007](0007-session-lifetime.md) | Sessions last as long as the sandbox, with no idle timeout | Accepted | 2026-10-03 |

New records copy this shape:

```
# NNNN. Title

Status: Proposed | Accepted | Superseded by NNNN · Date: YYYY-MM-DD

## Context
## Decision
## Rejected alternatives
## Consequences
```
