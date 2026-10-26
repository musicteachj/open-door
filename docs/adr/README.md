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
| [0008](0008-handbook-retrieval.md) | Hybrid handbook search in Postgres, with embeddings cached in the repository | Accepted | 2026-10-07 |
| [0009](0009-assistant-turn-and-guard.md) | Each turn is screened by a guard first, and fails closed | Accepted | 2026-10-14 |
| [0010](0010-scripted-model-and-replay.md) | A scripted model for development and tests, and recorded replay for CI's evals | Accepted | 2026-10-14 |
| [0011](0011-insert-only-budget-ledger.md) | AI budgets are an insert-only ledger, reserved before each call | Accepted | 2026-10-14 |
| [0012](0012-balances-derived-by-the-engine.md) | Time-off balances are derived by the engine, not posted to a ledger | Accepted | 2026-10-20 |
| [0013](0013-proposals-in-the-turn.md) | A proposal ends its turn normally, and its outcome reaches the next turn's context | Accepted | 2026-10-20 |

New records copy this shape:

```
# NNNN. Title

Status: Proposed | Accepted | Superseded by NNNN · Date: YYYY-MM-DD

## Context
## Decision
## Rejected alternatives
## Consequences
```
