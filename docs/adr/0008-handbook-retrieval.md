# 0008. Handbook retrieval: hybrid search in Postgres, with embeddings cached in the repository

Status: Accepted · Date: 2026-10-07

## Context

Every policy answer must cite the handbook (invariant 4), so the assistant needs to find the right
passages, and only ones that apply to the person asking: Priya in California and Mateo in Texas
get different sick-leave rules. Employees rarely use the handbook's words. "Can I stay home when my
kid has the flu?" is answered by a passage about caring for a family member. Exact terms matter
too: "FMLA" or "COMPS Order" should land on the section that names them.

The handbook is small (a few hundred passages) and versioned, and each sandbox pins a version. CI
may make no paid AI call, and the development budget is $25 a month.

## Decision

- **Hybrid search in Postgres:** full-text search and an exact pgvector scan, over the applicable
  sections of the sandbox's pinned version, merged with reciprocal-rank fusion (constant 60). Both
  run in the same database as the tenant data, so "applies to this person, in this version" is part
  of the query.
- **Voyage `voyage-4` embeddings at 1,024 dimensions,** called through a small `httpx` client.
  Anthropic has no embedding model and recommends Voyage.
- **Both the passage and the eval-question embeddings are cached in committed files.** CI and tests
  never call Voyage, and the retrieval eval is deterministic, so it gates CI for free. `make embed`
  is the only command that calls Voyage.
- **No approximate vector index.** An exact scan over a few hundred chunks takes milliseconds and
  never varies.
- **Full-text only when Voyage fails,** reported as the search's mode.

## Rejected alternatives

- **A separate vector database** (Pinecone, Weaviate, and the like): a second system to secure and
  keep in step, and the applicability and version filters would have to be copied into it.
- **Vector search alone:** it misses exact terms and acronyms. **Full-text search alone:** it
  misses paraphrases.
- **Calling Voyage in CI:** a paid call on every push, and an eval that varies with the network.
- **`voyage-context-4`** (each passage embedded with its whole section): possibly better on short
  passages, but a different API. It's the first fallback if the eval misses 90%.
- **An HNSW index:** approximate, and needless at this size.

## Consequences

- Changing a passage means running `make embed` and committing the cache. CI fails with that
  instruction on a miss.
- The cached vectors add about 1 MB to the repository for each handbook version's changed text.
- From Phase 4, each assistant question is sent to Voyage to be embedded. The data inventory
  records Voyage as a processor, and the owner turns off its model-training data collection.
