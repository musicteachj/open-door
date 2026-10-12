# Phase 3: Handbook and Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use
> checkbox (`- [ ]`) syntax for tracking. **Project rule:** never commit, push, or open a PR without
> the owner's explicit OK for that action (see `CLAUDE.md`). Every "Propose the commit" step stops
> and waits.

**Goal:** Juniper Row has a real handbook, about 23 company sections and three state addenda,
with every statutory figure checked against its official source. Anyone in a sandbox can browse
it, search it, and open a deep link that highlights one passage. A retrieval service finds the
passages that answer a question and apply to the person asking, and an eval in CI proves it: at
least 90% hit rate at 5, with every negative case passing.

**Architecture:**
- **The handbook** is markdown in `handbook/`, one file per section, with front matter for who it
  applies to. Ingestion validates a strict markdown subset, splits each section into numbered
  passages and chunks, embeds the chunks, and loads one immutable version into three global,
  read-only tables.
- **Embeddings** come from Voyage `voyage-4` at 1,024 dimensions, through a small `httpx` client.
  Both the passage and the eval-question vectors are cached in committed files, so CI and tests
  never call Voyage.
- **Each sandbox pins** the newest published version when it's created.
- **Hybrid search** runs Postgres full-text search and an exact pgvector scan over the applicable
  sections of the pinned version, and fuses them with reciprocal-rank fusion. It falls back to
  full-text search when Voyage fails.
- **The browser** reads four handbook routes and renders the structured blocks as React elements,
  never HTML.

**Tech stack:**
- **API:** FastAPI, SQLAlchemy 2.1 with `pgvector`'s SQLAlchemy type, Alembic, `markdown-it-py`,
  PyYAML, `httpx`, pytest, and Postgres 17 with pgvector.
- **Web app:** as in Phase 2: React 19, React Router 7, TanStack Query 5, Zustand 5, Tailwind 4,
  shadcn/ui, and Orval.
- **Tests:** Vitest with Testing Library and MSW, and Playwright with axe.

**Spec:** [`../specs/2026-10-07-phase-3-handbook-and-retrieval.md`](../specs/2026-10-07-phase-3-handbook-and-retrieval.md) ·
**Design:** [`../design/screens/06-handbook/notes.md`](../design/screens/06-handbook/notes.md) ·
**ADR:** [`../adr/0008-handbook-retrieval.md`](../adr/0008-handbook-retrieval.md) ·
**Roadmap:** [`../ROADMAP.md`](../ROADMAP.md)

---

## How this plan is written

**Outlines, not finished code,** as in Phase 2. Each task gives the files, the tests to write first
and what each proves, the interfaces later tasks depend on, and "Known:" notes on traps found while
planning. Those come from reading the repository and the libraries' documentation, not from a
trial build: there was none. The implementer writes the code test first, watches each test fail
for the right reason, and then makes it pass. Problems are solved during the build and recorded
under [Changes made during execution](#changes-made-during-execution).

---

## Decisions made while planning

**Five stages, each a pull request into `dev`.**

| Stage | Branch | Tasks | Code, not counting tests (est.) |
|---|---|---|---|
| 1 The handbook | `docs/phase-3-handbook` | 1–6 | none (about 10,000 words of content) |
| 2 Schema, ingestion, and embeddings | `feat/phase-3-ingestion` | 7–17 | about 1,300 |
| 3 Retrieval, the eval, and the handbook API | `feat/phase-3-retrieval` | 18–25 | about 1,100, plus the eval set |
| 4 The handbook components | `feat/phase-3-handbook-components` | 26–32 | about 1,000 |
| 5 The handbook pages, and closing Phase 3 | `feat/phase-3-handbook-pages` | 33–38 | about 1,000 |

**How each stage runs** (the way of working approved in Phases 1 and 2):

- **Batches.** Each stage runs in the batches named under it. After each batch I stop with a short
  report and wait for "continue".
- **One Sonnet implementer per batch.** It gets this plan's line range for its tasks, the spec, the
  design notes where they apply, and the deviations the repository forces. It writes each test
  first and reproduces the failure.
- **Reviews:**
  - A batch that touches who can read or write what gets a Sonnet compliance reviewer and one
    Opus security reviewer, run in parallel. In Phase 3 that's only Stage 2's batch A (the schema
    and grants), and its re-check of batch C (ingestion as the owner, and pinning). The Opus
    reviewer is re-briefed through SendMessage, so it keeps its context.
  - Every other batch gets one combined Sonnet review.
  - Stage 1 is content: a Sonnet fact-checker re-reads every source line against its page.
- **Fixes** are written test first by a Sonnet fixer, and each new test is mutation-proved.
- **I do each stage's close myself:** the changelog, the roadmap row and its "Next" note, this
  plan's "Changes made during execution", `make db && make check`, and `/code-review medium` on the
  whole branch (`git add -N` new files first so the review sees them). If the review finds
  something, it runs again after the fix. Then I draft the commit and PR and wait for the owner's
  OK on each action.
- **Implementers merge, never replace,** `tests/integration/conftest.py`, `docs/BACKLOG.md`, and
  `docs/DATA-INVENTORY.md`.

**Effort for each session:** `medium` for every stage, the closes, and the phase review. The
statutory research in Stage 1 is careful reading, not hard reasoning. Switch to `high` only for a
stubborn bug, then back.

**Other decisions that affect more than one stage:**
- **Every UI stage ends the same way:** `make check` (with the browser tests), the owner's review of
  the capture report (or of the gallery, in Stage 4), `/code-review medium`, and the proposed commit
  and PR.
- **The roadmap's status row and "Next" note change at every close,** and the note names the next
  session's effort level.
- **`docs/DATA-INVENTORY.md`** changes in the same task as the data it describes, and
  **`docs/BACKLOG.md`** items are deleted when they're done and recorded in the changelog.

## Prerequisites (owner)

- **Before Stage 2's Task 16** (the first `make embed`):
  1. a Voyage API key in `apps/api/.env` as `VOYAGE_API_KEY`
  2. a payment method on file: without one, Voyage allows only 3 requests and 10,000 tokens a
     minute, too few for the handbook's first run (the free tokens still apply with a card)
  3. a budget alert in the Voyage dashboard (it only emails; Voyage has no hard spending cap)
  4. model-training data collection turned off for the organization (this needs the payment
     method)

  These were corrected during Stage 2; see [Changes made during execution](#changes-made-during-execution).
- **Docker Desktop is running,** and `make setup` and `make db` have run.
- **Each stage branches off `dev` after the previous stage's PR merges.**
- **Record the commit `dev` is at before Stage 1 branches.** Task 38's phase review diffs against
  it.

## File map

```
open-door/
├── handbook/                              Stage 1  handbook.yaml, sections/, addenda/
│   └── embeddings/voyage-4-1024.jsonl     Stage 2  the committed passage-embedding cache
├── evals/
│   ├── README.md                          Stage 3
│   └── retrieval/                         Stage 3  dataset.yaml, run.py, embeddings/
├── compose.yaml                           Stage 2  the pinned pgvector tag
├── Makefile                               Stages 2, 3  ingest, embed, eval-retrieval; db ends with ingest
├── .github/workflows/ci.yml               Stages 2, 3  pinned image; ingest in api and e2e; the eval step
├── _typos.toml                            Stage 1  any legal terms the spell check rejects
├── CLAUDE.md                              Stages 2, 3  the new make targets
├── docs/
│   ├── DATA-INVENTORY.md                  Stage 2  three tables, the tenants column, Voyage
│   ├── BACKLOG.md                         Stages 2, 3, 5  closed items out; new Phase 4 and 8 items in
│   └── adr/0008-handbook-retrieval.md     planning
├── apps/api/
│   ├── pyproject.toml                     Stage 2  dependencies; the import-linter list
│   ├── migrations/versions/0004_handbook.py   Stage 2
│   ├── scripts/ingest_handbook.py         Stage 2  ingest and embed
│   └── app/
│       ├── core/config.py                 Stage 2  VOYAGE_API_KEY
│       ├── db/engine.py                   Stage 3  hide_parameters
│       ├── db/models.py                   Stage 2  the three tables; Tenant.handbook_version_id
│       ├── domain/handbook/               Stage 2  parse, validate, passages, chunks, applicability, hash
│       ├── domain/retrieval.py            Stage 3  reciprocal-rank fusion
│       ├── ai/embeddings.py               Stage 2  the Voyage client, the cache, the fake
│       └── modules/
│           ├── sandbox/service.py         Stage 2  pin the version at creation
│           └── handbook/                  Stages 2, 3  load, queries, search, routes, schemas
└── apps/web/src/
    ├── components/handbook/               Stage 4  the nine components and the block renderer
    ├── app/gallery/                       Stage 4  the handbook states
    ├── app/nav.ts, app/router.tsx         Stage 5  Handbook on; the two routes
    └── features/handbook/                 Stage 5  hooks, the home page, the section page
```

---

# Stage 1: The handbook

**Branch:** `docs/phase-3-handbook`, off `dev`.
**Ends with:** the whole handbook in `handbook/`, written to the spec's front matter and markdown
subset, with a source line for every statutory figure. The owner has read it. There's no code, so
there's no `/code-review`.
**Batches:** A (Tasks 1–2, the company handbook), B (Tasks 3–5, the addenda), C (Task 6, the close).
A Sonnet writer per batch, then a Sonnet fact-checker over every source line in the batch.

**Rules for every task in this stage:**
- **Follow the spec's [handbook section](../specs/2026-10-07-phase-3-handbook-and-retrieval.md#the-handbook)**:
  the file names, the front matter, the markdown subset, and the rules for the text.
- **Verify every statutory figure in the session that writes it.** Open the official page (CA DIR,
  CO CDLE, TX TWC, the U.S. Department of Labor) or the statute, read the figure there, and add the
  source line with that day's date. Never write a figure from memory. If two official sources
  disagree, or a law changed recently, say so in the batch report rather than choosing silently.
- **Keep each section short:** 150 to 450 words, with `##` headings an employee would scan for
  ("How much you receive", "When you can use it", "Giving notice").
- **Use the seed company's facts:** the three locations, and the 120 people, salaried and hourly.
  No section names a real person or a real company.
- **The design's sample text** (`docs/design/system/Handbook.dc.html`) is only layout. Its figures
  are placeholders and aren't copied.

### Task 1: `handbook.yaml`, and Chapters 1, 2, 6, and 7

**Files:** `handbook/handbook.yaml`; `handbook/sections/1.1-…` to `2.4-…`, `6.1-…`, `6.2-…`,
`7.1-…`, `7.2-…`.

- [ ] **`handbook.yaml`:** version `2026.10`, the title "Juniper Row Employee Handbook", the seven
      chapter names, the three addendum names, and the location codes `den`, `oak`, and `aus` with
      the seed's names.
- [ ] **1.1** says the company and the handbook are fictional demo content, not legal advice, and
      explains the addenda: where a state addendum applies, the employee gets the more generous
      rule.
- [ ] **1.2** defines salaried and hourly employment the way the seed uses it.
- [ ] **2.2 and 2.3:** how to raise a concern, including going straight to HR, never only through a
      manager, and the non-retaliation promise. They match the escalation rules: managers never see
      cases, and HR reads them.
- [ ] **6.2** names the fictional Employee Assistance Program, and 988 for a crisis.
- [ ] **7.2** says only what's true of Phase 6's cases (the backlog's "hand-off says only what's
      true" item): only HR sees a case; it's stored encrypted; when to expect a reply; and the AI
      writes HR a neutral summary with no recommendation.

### Task 2: Chapters 3, 4, and 5

**Files:** `handbook/sections/3.1-…` to `5.3-…`.

- [ ] **Company figures,** chosen and stated plainly. Phase 5 builds the time-off engine from them:
  - PTO accrual per month, by employment type, in hours, with a carryover cap
  - the company sick-leave amount for states without a law, front-loaded on January 1
  - bereavement days
- [ ] **Federal figures, verified:** the FLSA's overtime threshold and rate (3.2), and FMLA's leave
      length and eligibility (5.1). Juniper Row has 120 people, but no location has 50 within 75
      miles, which bears on FMLA eligibility. Check the rule, and write what it means honestly.
- [ ] **4.2 Holidays** says exactly what `app/domain/holidays.py` does: the six holidays, the
      observed-date rule, and Denver HQ also closing the day after Thanksgiving, with
      `applies_to.locations` left empty and the Denver rule written as one passage.
- [ ] **4.3 Sick leave** is the company rule, and says that a state addendum may give more.
- [ ] **3.2 and 3.3** are for hourly staff (`employment_types: [hourly]`).
- [ ] Propose nothing yet: batch A's report lists every figure, its source, and anything uncertain.

### Task 3: The California addendum

**Files:** `handbook/addenda/ca/CA-3.2-…`, `CA-3.3-…`, `CA-3.4-…`, `CA-4.3-…`, and any added section.

- [ ] **Verify and write:** daily and weekly overtime and double time (CA-3.2); meal and rest
      periods and the premium for a missed one (CA-3.3); final pay timing on discharge and on
      resignation, with and without notice (CA-3.4); and paid sick leave's amount, front-loading,
      carryover or cap, and uses (CA-4.3).
- [ ] **Sources:** CA DIR's pages and the Labor Code sections they cite. Each source line names
      the section and the page it was read from.
- [ ] **Decide, and report:** whether California's family leave law (CFRA) warrants CA-5.1. It
      probably does, since it covers smaller employers than FMLA.

### Task 4: The Colorado addendum

**Files:** `handbook/addenda/co/CO-3.2-…`, `CO-3.3-…`, `CO-4.3-…`, and any added section.

- [ ] **Verify and write:** daily and weekly overtime (CO-3.2) and meal and rest periods (CO-3.3)
      under the current COMPS Order; and paid sick leave under the Healthy Families and Workplaces
      Act: the amount, accrual or front-loading, carryover, and uses (CO-4.3).
- [ ] **Sources:** CO CDLE's pages, the COMPS Order by number, and the statute.
- [ ] **Decide, and report:** whether Colorado's FAMLI program warrants CO-5.1.

### Task 5: The Texas addendum

**Files:** `handbook/addenda/tx/TX-3.4-…`, `TX-4.5-…`.

- [ ] **Verify and write:** final pay timing on discharge and on resignation under the Texas Payday
      Law (TX-3.4), and jury duty and voting leave (TX-4.5).
- [ ] **Confirm, and record in TX-3.4's report:** that Texas has no state paid-sick-leave law, so
      company section 4.3 applies to Texas employees. If a city ordinance is relevant, check its
      status at the official source.
- [ ] **Sources:** TX TWC's pages and the statutes.

### Task 6: Close Stage 1

- [ ] **The fact-check:** a Sonnet fact-checker opens every source line's page and confirms each
      figure. Every mismatch is fixed or explained.
- [ ] **A self-check against the spec:** every file's ID matches its name, every `supplements`
      target exists, every `handbook:` link resolves, and only the subset is used. Stage 2's
      validator will check this mechanically, so this is a careful read, not a script.
- [ ] **`make check-docs`.** Add legal terms the spell check rejects to `_typos.toml`, never a
      British spelling.
- [ ] **`CHANGELOG.md`:** "Phase 3, stage 1", under Added. **`docs/ROADMAP.md`:** the Phase 3 row
      reads "In progress: stage 1 of 5 (the handbook)", and the "Next" note names Stage 2 at
      effort `medium`.
- [ ] **The owner reads the handbook.** Their edits go in before the PR.
- [ ] Propose the commit and PR, and wait for the owner's OK.

---

# Stage 2: Schema, ingestion, and embeddings

**Branch:** `feat/phase-3-ingestion`, off `dev` after Stage 1 merges.
**Ends with:** migration 0004 and its grants; the pure handbook domain; the Voyage client and both
caches; `make ingest` and `make embed`; `make db` ingesting the handbook; each new sandbox pinned
to the newest published version; CI ingesting before the tests; the pinned pgvector image; and the
data inventory current. `make check` passes.
**Batches:**
- **A (Tasks 7–9):** the image pin, dependencies, migration 0004, and the grants. A Sonnet
  compliance reviewer and the Opus security reviewer, in parallel.
- **B (Tasks 10–12):** the pure domain. One combined review.
- **C (Tasks 13–16):** embeddings, ingestion, pinning, and CI. One combined review, plus the Opus
  reviewer's re-check of ingestion as the owner and of pinning.
- **D (Task 17):** the close.

> **Before you start:** `make db`. Task 16 needs the owner's Voyage key.

### Task 7: Pin the pgvector image

**Files:** `compose.yaml`, `.github/workflows/ci.yml` (both Postgres services), `docs/BACKLOG.md`.

- [ ] Choose the newest `0.8.x-pg17` tag, and use it in all three places.
  - **Known:** check the tag exists on Docker Hub before using it. Don't guess it.
- [ ] Delete the backlog's "Pin the pgvector image" item.

### Task 8: Dependencies

**Files:** `apps/api/pyproject.toml`, `uv.lock`.

- [ ] Add `pgvector`, `markdown-it-py`, `pyyaml`, and `httpx` as runtime dependencies. Use the
      latest versions that resolve, and record them in Changes made during execution.
- [ ] **Import-linter:** add `pgvector` and `yaml` to the forbidden list for `app.domain` and
      `app.policy`. `markdown_it` stays allowed: it's a parser, not a framework. The domain gets
      text in and returns data out, and reading files stays in the module.
  - **Known:** `httpx` is already on the list. `app/ai/embeddings.py` isn't under `app.domain`, so
    it may use it.
- [ ] `uv run lint-imports` passes.

### Task 9: Migration 0004 and the models

**Files:** `apps/api/migrations/versions/0004_handbook.py`, `app/db/models.py`,
`tests/integration/test_grants.py`, `tests/integration/test_handbook_schema.py` (new).

- [ ] **Test first:**
  - the exact-grants test lists `SELECT` for `od_app` on the three tables, and nothing for
    `od_cleanup`. Watch it fail until the migration exists.
  - as `od_app`, an `INSERT`, `UPDATE`, or `DELETE` on each handbook table is refused
  - `tenants.handbook_version_id` exists and is nullable, and deleting a version a tenant uses is
    refused
  - the row-level-security coverage test still passes, untouched
- [ ] **The migration** follows the spec's [data model](../specs/2026-10-07-phase-3-handbook-and-retrieval.md#data-model):
      the three tables, the unique constraints, the GIN index on `search`, the generated
      `tsvector`, `vector(1024)`, the new column, and the grants. The downgrade drops them in
      reverse order.
- [ ] **The models** in `app/db/models.py` match the migration exactly, so `alembic check` finds
      nothing.
  - **Known:** declare the generated column with `Computed(..., persisted=True)` and the embedding
    with `pgvector.sqlalchemy.Vector(1024)`. Otherwise `alembic check` reports a difference.
  - **Known:** a generated column must use an immutable expression. `to_tsvector('english', …)`
    with the configuration written as a literal is immutable; without it, it isn't.
  - **Known:** the column is added to `tenants`, which has forced row-level security. Adding a
    column doesn't change its policies. The cleanup role's delete still works, because the foreign
    key points from `tenants` to `handbook_versions`.
- [ ] `make migrations-roundtrip`, then `make bootstrap-db`, then the tests.

### Task 10: Parse and validate

**Files:** `app/domain/handbook/{__init__,source,validate}.py`; tests in
`tests/test_handbook_validate.py`, with small fixture handbooks under `tests/fixtures/handbook/`.

**Interface:**

```python
@dataclass(frozen=True)
class SourceFile:          # what the module reads from disk and hands to the domain
    path: str
    text: str

def load_handbook(config_text: str, files: Sequence[SourceFile]) -> Handbook  # raises HandbookInvalid
class HandbookInvalid(Exception):
    errors: list[HandbookError]   # each has path, line, and message; every error at once
```

- [ ] **Tests first, one per rule,** each asserting the file and line in the error:
  - front matter: a missing or unknown field, a bad date, an unknown state, employment type, or
    location code, and an ID that doesn't match the file name
  - the subset: raw HTML, an image, a table, a code block, a quote, a nested list, a `#` heading,
    and an external link
  - links: `handbook:` to a missing section, and `supplements` naming a missing or non-company
    section
  - duplicate IDs
  - a valid fixture handbook loads, with every error reported at once
- [ ] Use `markdown-it-py`'s token stream to walk the body, and refuse any token type outside the
      subset.

### Task 11: Blocks, passages, chunks, and the content hash

**Files:** `app/domain/handbook/{blocks,chunks,hashing}.py`; tests in `tests/test_handbook_chunks.py`.

**Interface:**

```python
Block = Heading | Passage           # Passage: id "p1"…, kind paragraph|list, inlines or items
Inline = {text, bold, italic, link_section_id | None}
Chunk(section_id, position, heading, passage_ids, text, embed_text)
CHUNKER_VERSION = 1
def chunks_for(section: Section, *, max_tokens: int = 350) -> list[Chunk]
def content_hash(handbook: Handbook, *, model: str, dimensions: int) -> str
```

- [ ] **Tests first:**
  - passages are numbered in order, paragraphs and lists alike, and headings get no ID
  - a chunk never splits a passage, and never crosses a `##` heading
  - a long run of passages splits before `max_tokens`
  - `embed_text` is `"{id} {title} · {chapter or addendum}\n{heading}\n\n{text}"`
  - the hash changes when any file, the model, the dimensions, or `CHUNKER_VERSION` changes, and
    not when the files are read in a different order
- [ ] **Known:** count tokens roughly, at four characters a token. The cap is only a size guide.
      Voyage's own limit is far above it.

### Task 12: Applicability, and the audience label

**Files:** `app/domain/handbook/applicability.py`; tests in `tests/test_handbook_applicability.py`.

**Interface:**

```python
@dataclass(frozen=True)
class Asker:
    state: str; employment_type: str; location_code: str
    @classmethod
    def from_actor(cls, actor) -> "Asker"   # lives in the module, not the domain: it reads Actor

def applies(audience: Audience, asker: Asker) -> bool
def audience_label(audience: Audience, location_names: Mapping[str, str]) -> str
```

- [ ] **Tests first:**
  - `applies` for every combination of empty and non-empty lists
  - labels: "Everyone", "California employees", "Hourly staff", "Hourly staff in California",
    "Denver HQ"
  - a test that runs `applies` over every section of the real handbook for each persona, so Stage
    3's SQL filter has a reference to agree with
- [ ] `Asker.from_actor` goes in `app/modules/handbook/asker.py`, since the domain can't import the
      actor.

### Task 13: Embeddings: the client, the cache, and the fake

**Files:** `app/ai/__init__.py`, `app/ai/embeddings.py`, `app/core/config.py`; tests in
`tests/test_embeddings.py`.

**Interface:**

```python
MODEL = "voyage-4"; DIMENSIONS = 1024
class Embedder(Protocol):
    async def embed(self, texts: Sequence[str], *, input_type: Literal["document", "query"]) -> list[list[float]]
class VoyageEmbedder: ...           # httpx, POST https://api.voyageai.com/v1/embeddings
class EmbeddingCache:              # JSON Lines; key = sha256(model|dims|input_type|text); base64 float32
    def get(...) -> list[float] | None; def put(...); def save(path); def prune(keep: set[str])
class CachedEmbedder:              # cache first; on a miss, the inner embedder, or EmbeddingMissing
class FakeEmbedder:                # deterministic vectors from a hash, for tests
```

- [ ] **Tests first:**
  - the cache key, and the base64 float32 round trip, both exact
  - `CachedEmbedder` with no inner embedder raises `EmbeddingMissing`, naming the count of misses
  - `VoyageEmbedder`, against an `httpx.MockTransport`: the request body (model,
    `output_dimension`, `input_type`), batching across the per-request limits, a retry on 429 and
    on 503, giving up after a few attempts, a timeout, and the key sent only in the header and
    never logged
- [ ] **Settings:** `voyage_api_key: SecretStr | None`. An empty string counts as none.
  - **Known:** the empty `ANTHROPIC_API_KEY` trap in `CLAUDE.md` applies to `VOYAGE_API_KEY` too.
    Run the script with `env -u VOYAGE_API_KEY` if the key seems missing.
  - **Known:** Voyage's limits for `voyage-4` are 1,000 inputs and 320,000 tokens per request (read
    2026-10-06). Accounts without a payment method get lower rate limits, so keep batches modest
    and back off on 429.

### Task 14: Load a version, and the script

**Files:** `app/modules/handbook/{__init__,load}.py`, `scripts/ingest_handbook.py`, `Makefile`;
tests in `tests/integration/test_handbook_ingest.py`.

**Interface:**

```python
async def ingest(conn: AsyncConnection, handbook: Handbook, embedder: Embedder, *, publish: bool) -> IngestResult
# IngestResult: "loaded" | "unchanged", with the version id
```

- [ ] **Tests first,** as the owner, each inside a transaction that's rolled back, so the published
      handbook stays as it is:
  - a fixture handbook loads with `publish=False`: its sections, blocks, chunks, and embeddings
  - a second run is `unchanged`
  - a changed file under the same label fails, with a message asking for a new label
  - a load that fails part of the way leaves no rows
- [ ] **The script:**
  - `ingest` reads `handbook/`, validates, embeds from the cache, and loads and publishes, as the
    owner (`MIGRATION_DATABASE_URL`).
  - `embed` fills the misses in both caches through Voyage (the handbook's, and the eval's from
    Stage 3 once it exists), prunes unused entries, and saves.
  - Each exits non-zero with a clear message on a validation error, a cache miss ("run `make
    embed` and commit the cache"), or a missing key.
- [ ] **`Makefile`:** `ingest`, `embed`, and `db` ending with `ingest`. Add them to `make help` and
      to `CLAUDE.md`'s commands.
  - **Known:** `ingest` takes a connection and never opens its own transaction, so the test can
    roll it back. The script owns the transaction.

### Task 15: Pin each new sandbox

**Files:** `app/modules/sandbox/service.py`, `app/db/models.py`, `tests/integration/conftest.py`
(merge), `tests/integration/test_sandbox_handbook.py` (new), `docs/DATA-INVENTORY.md`.

- [ ] **Tests first:**
  - a new sandbox's `handbook_version_id` is the newest published version
  - with a newer version published inside a rolled-back transaction, a sandbox created in that
    transaction pins the newer one
  - with no published version, `POST /sandboxes` answers a 503 problem and creates no tenant
- [ ] **The conftest** gets a session fixture that fails fast, with "run `make ingest`", when no
      version is published.
- [ ] **The data inventory:** the three tables (global, no personal data, kept while a sandbox uses
      their version), the new column, and a "Voyage" section under "Outside the database".

### Task 16: CI, the real handbook, and the first embedding run

**Files:** `.github/workflows/ci.yml`, `tests/test_handbook_real.py` (new),
`handbook/embeddings/voyage-4-1024.jsonl`.

- [ ] **Tests:**
  - the real handbook validates
  - every holiday name `holidays_for` gives, for each location, appears in 4.2, and "day after
    Thanksgiving" appears with Denver HQ
  - every location code in `handbook.yaml` matches the seed's
- [ ] **Fix any format slip** the validator finds in the handbook. A wording change needs the
      owner's OK.
- [ ] **The owner's Voyage key is in place:** run `make embed`, check the cache's size (about 1 MB)
      and its line count (one per chunk), and commit it in this stage's PR.
- [ ] **CI:** the API and e2e jobs run `uv run python scripts/ingest_handbook.py ingest` after the
      bootstrap step and before the tests. The job has no Voyage key, so a miss fails it.

### Task 17: Close Stage 2

- [ ] **`CHANGELOG.md`:** "Phase 3, stage 2", under Added and Changed (the pgvector pin).
      **`docs/ROADMAP.md`:** the row and the "Next" note (Stage 3, effort `medium`).
- [ ] Run `make db && make check`, then `/code-review medium` on the branch against `dev`.
- [ ] Propose the commit and PR, and wait for the owner's OK.

---

# Stage 3: Retrieval, the eval, and the handbook API

**Branch:** `feat/phase-3-retrieval`, off `dev` after Stage 2 merges.
**Ends with:** `search_handbook` with hybrid search and its fallback; the eval set, its runner, and
its CI gate at 90% or better; the four handbook routes; `hide_parameters`; and the regenerated
client. `make check` passes, and the eval's result is in the PR description.
**Batches:** A (Tasks 18–21, search), B (Task 22, the eval), C (Tasks 23–24, the API), D (Task 25,
the close). One combined review per batch.

### Task 18: Hide SQL parameters from the error log

**Files:** `app/db/engine.py`; a test in `tests/integration/test_engine_logging.py`.

- [ ] **Test first:** a statement that fails with a bound string logs at ERROR without the value.
- [ ] Set `hide_parameters=True` in `create_engine`. Delete the backlog item.

### Task 19: The applicability filter in SQL

**Files:** `app/modules/handbook/queries.py`; tests in `tests/integration/test_handbook_filter.py`.

- [ ] **Test first:** for every section of the real handbook, and for every combination of the
      seed's states, both employment types, and the three location codes, the SQL filter keeps
      exactly the sections that `applies()` says.
- [ ] Write the filter on `handbook_sections.audience` with `jsonb` operators. An empty or missing
      list means no restriction.

### Task 20: The two searches, and fusion

**Files:** `app/modules/handbook/queries.py`, `app/domain/retrieval.py`; tests in
`tests/test_retrieval_fusion.py` and `tests/integration/test_handbook_search_queries.py`.

**Interface:**

```python
def fuse(*rankings: Sequence[ChunkKey], k: int = 60) -> list[Fused]   # pure; ties by section, then chunk position
async def fulltext_candidates(db, version_id, asker, query, limit=20) -> list[ChunkKey]
async def vector_candidates(db, version_id, asker, embedding, limit=20) -> list[ChunkKey]
```

- [ ] **Tests first:**
  - `fuse` on hand-worked rankings: a chunk in both lists outranks one in only one; exact ties
    break by position; one empty list
  - full-text: "How much sick leave do I get?" finds 4.3 even though "get" and "much" appear
    nowhere. That proves the words are joined with OR.
  - vector: with the fake embedder, the order is deterministic
  - both stay inside the version and the applicable sections
- [ ] **Known:** `websearch_to_tsquery` joins words with AND, so a natural question rarely matches
      anything. Build the OR query from the question's own lexemes, in SQL, with `to_tsvector`
      and `tsvector_to_array` joined by `' | '`. Don't parse the question in Python.
- [ ] **Known:** cosine distance is `<=>`. Bind the query vector through the `Vector` type, or as a
      string cast to `::vector` in a `text()` query.

### Task 21: `search_handbook`, and the fallback

**Files:** `app/modules/handbook/search.py`; tests in `tests/integration/test_search_handbook.py`.

**Interface:**

```python
async def search_handbook(db, *, version_id, asker: Asker, query: str, embedder: Embedder,
                          location_code: str | None = None, limit: int = 5) -> SearchResult
# SearchResult(mode: "hybrid" | "fulltext", location_used, hits: list[Hit])
# Hit: section_id, title, group_name, audience_label, last_updated, passage_ids,
#      passages: list[str], deep_link, fulltext_rank, vector_rank
```

- [ ] **Tests first:**
  - the same question gives the same hits, in the same order, every time
  - `location_code="oak"` for a Texas asker returns CA-4.3 for a sick-leave question, and
    `location_used` says `oak`
  - an embedder that raises gives `mode="fulltext"`, still returns hits, and logs one warning
    event with the reason and no query text
  - the query is embedded before the session's first statement. A spy embedder proves it.
  - each hit's `deep_link` is `/handbook/{id}?passage={first passage}`
- [ ] A small in-process LRU of query embeddings, keyed by the cache hash, holding no text. Phase 4
      uses it.

### Task 22: The retrieval eval

**Files:** `evals/README.md`, `evals/retrieval/{dataset.yaml,run.py}`,
`evals/retrieval/embeddings/voyage-4-1024.jsonl`, `Makefile` (`eval-retrieval`), `.github/workflows/ci.yml`.

- [ ] **Write the dataset first, before running anything,** to the spec's [Evals](../specs/2026-10-07-phase-3-handbook-and-retrieval.md#evals)
      section: about 60 questions, about 15 negatives, a few `location_code` questions, and
      askers beyond the personas. The owner reviews it in the PR.
- [ ] **Run `make embed`** to cache the questions' vectors, and commit the cache.
- [ ] **The runner** (`uv run python ../../evals/retrieval/run.py`, from `apps/api`):
  - it prints hit rate at 5 and mean reciprocal rank, overall and per asker, every miss with what
    came back, and every negative
  - `--check` exits non-zero below 0.90 or on any failed negative
  - `--json PATH` writes the scoreboard fields: the model, the dimensions, the dataset's hash, the
    commit, the date, and the results
- [ ] **CI:** the API job runs `run.py --check` after pytest. A missing query embedding fails it,
      with "run `make embed`".
- [ ] **If the first run is under 90%,** try these in order, and record each attempt and its score
      under Changes made during execution:
  1. the chunk size
  2. what goes in front of each passage when it's embedded
  3. the title and heading weights in full-text search
  4. how many candidates each list keeps
  5. `voyage-context-4`, which needs the owner's OK, since it changes the model

  The questions themselves don't change to raise the score. A wrong label can be fixed, with the
  owner's OK and a note.

### Task 23: The handbook routes

**Files:** `app/modules/handbook/{routes,schemas}.py`, `app/api/v1/router.py`; tests in
`tests/integration/test_handbook_api.py`.

- [ ] **Tests first,** for each route in the spec's [API table](../specs/2026-10-07-phase-3-handbook-and-retrieval.md#the-handbook-api):
  - the fields, in camelCase, as the other routes use
  - `appliesToMe` for Priya, Mateo, and Dana on CA-4.3, CO-4.3, 3.2, and 4.2
  - the 404 problems for an unknown section or passage, and for a sandbox with no pinned version
  - search: every word required ("dental plan" finds nothing), the sections that apply first,
    segments that mark the matched words, the control characters stripped from the query, a
    101-character query gets 422, and anonymous gets 401
  - a sandbox reads only its own version. Pin two tenants to two versions inside a rolled-back
    transaction.
- [ ] **Known:** `ts_headline` returns text with the start and stop markers you choose. Use two
      control characters (`\x02` and `\x03`), strip both from the query first, and split on them
      to build the segments.
- [ ] Declare every route's errors through `problem_responses`, as the directory does.

### Task 24: Regenerate the schema and the client

- [ ] Run `make openapi`, then `make check-web`. The client gains the four handbook hooks.

### Task 25: Close Stage 3

- [ ] **`CHANGELOG.md`:** "Phase 3, stage 3". **`docs/BACKLOG.md`:**
  - delete "hide SQL parameters" (Task 18)
  - add to Phase 4: "map search hits to `search_result` blocks, and open the passage panel on a
    citation's passage"
  - add to Phase 8: "delete handbook versions no sandbox uses"
- [ ] **`docs/ROADMAP.md`:** the row and the "Next" note (Stage 4, effort `medium`).
- [ ] Run `make db && make check` and `make eval-retrieval`. Put the eval's numbers in the PR
      description.
- [ ] `/code-review medium` on the branch, then propose the commit and PR.

---

# Stage 4: The handbook components

**Branch:** `feat/phase-3-handbook-components`, off `dev` after Stage 3 merges.
**Ends with:** every component in `components.md`'s Handbook table, built from its sketch in
`docs/design/system/components/handbook/`, shown in every state in the gallery, with its tests. The
owner has reviewed the gallery. `make check` passes.
**Batches:** A (Tasks 26–28), B (Tasks 29–30), C (Tasks 31–32). One combined review per batch.

**For every component:** its sketch, props (`.d.ts`), and usage note are the specification. Use the
theme's tokens, never a raw color. The no-raw-colors test enforces it.

### Task 26: The words and the formats

**Files:** `src/components/handbook/labels.ts`, `src/lib/format-date.ts` (extend if it exists);
tests beside them.

- [ ] **Tests first:** every string in the notes' Copy section comes from one place; "Last updated
      Sep 12, 2026"; the eyebrows "§4.3 · Time off" and "CA-4.3 · California addendum", and the
      panel's "Handbook …" form.

### Task 27: The badge, the marker, and the date

**Files:** `ApplicabilityBadge.tsx`, `AppliesMarker.tsx`, `LastUpdated.tsx`; tests.

- [ ] **Tests first:** the badge's label comes from the API's `audienceLabel`; the marker's two
      variants each have their icon and text, and the icon is hidden from screen readers.

### Task 28: The section row, the group, the navigator, and the search result

**Files:** `SectionRow.tsx`, `SectionGroup.tsx`, `ChapterNav.tsx`, `SearchResultRow.tsx`; tests.

- [ ] **Tests first:**
  - a row is one link, and its accessible name is its number, title, audience, the marker if
    shown, and the date
  - in list mode, the marker shows only when the section `appliesToMe` and its audience isn't
    everyone
  - the navigator marks the current section `aria-current="page"`
  - a search result renders its segments, with each match in `<mark>`
  - there's no arrow-key handler

### Task 29: The blocks, the cited passage, and the link blocks

**Files:** `HandbookBlocks.tsx`, `CitedPassage.tsx`, `LinkBlock.tsx`, `SourcesBlock.tsx`; tests,
including `src/no-inner-html.test.ts` (new).

- [ ] **Tests first:**
  - headings, paragraphs, both list kinds, bold, italic, and a `handbook:` link (a router link)
    each render as elements
  - the cited passage is a region labeled "Cited passage", with the quote icon and "Clear
    highlight" when `onClear` is given
  - "State rules" and "Supplements" render their rows and markers
  - the Sources block has no "Source:" prefix
  - **no file in `src/` uses `dangerouslySetInnerHTML`,** a test that scans the source

### Task 30: The passage panel

**Files:** `PassagePanel.tsx`; tests.

- [ ] **Tests first:**
  - open, loading, and error ("Couldn't load this passage." with Retry, `role="alert"`)
  - on open, focus moves to the title; Escape and the close button call `onClose`, and the host
    returns focus to the citation (tested with a small host)
  - the body scrolls inside the panel and takes focus
  - "Open in handbook" links to the deep link, and stays in the error state
- [ ] **Known:** the panel isn't a Radix Dialog. It isn't modal and doesn't trap focus. Write the
      focus handling directly.

### Task 31: The gallery, and its browser tests

**Files:** `src/app/gallery/` (the handbook section), `e2e/gallery-handbook.spec.ts`, the capture
manifest.

- [ ] Every state from the notes and `components.md`, each under its own heading.
- [ ] **Browser tests:** axe on every handbook gallery state; hover and focus captures; and the
      panel's focus behavior in a real browser.
- [ ] Add a capture row for each component state with a design screenshot.

### Task 32: Close Stage 4

- [ ] **`CHANGELOG.md`:** "Phase 3, stage 4". **`docs/design/components.md`:** note any state that
      was built but not designed. **`docs/ROADMAP.md`:** the row and the "Next" note.
- [ ] `make check`, then the owner's review of the gallery (I start `make dev` in the background
      and give the URL, then stop it after), then `/code-review medium`, then propose the commit
      and PR.

---

# Stage 5: The handbook pages, and closing Phase 3

**Branch:** `feat/phase-3-handbook-pages`, off `dev` after Stage 4 merges.
**Ends with:** `/handbook` and `/handbook/:sectionId` meet every acceptance criterion in the
notes; the Handbook nav item is on; the assistant home shows "Handbook updated"; and every
criterion has a browser test. Then the phase review.
**Batches:** A (Tasks 33–34), B (Tasks 35–36), C (Task 37), D (Task 38). One combined review per
batch.

### Task 33: The data hooks and the URL state

**Files:** `src/features/handbook/{use-handbook,use-section,use-handbook-search,use-passage}.ts`,
`src/features/handbook/url-state.ts`; tests.

- [ ] **Tests first:**
  - `q` and `show` read from and write to the URL; search writes after 250 ms and replaces the
    history entry
  - "Clear highlight" removes `passage` and replaces the entry
  - the four hooks wrap the generated client, and a 404 maps to the missing-section state

### Task 34: The handbook home

**Files:** `src/features/handbook/handbook-page.tsx`, `src/app/router.tsx`; tests.

- [ ] **Tests first,** with MSW:
  - the list is grouped by chapter, then "State addenda" and the three addendum groups
  - the Show menu's counts match the list, and "Applies to me" keeps exactly the sections that
    apply
  - the search results; and no results, with "Clear search" and "Ask the assistant"
  - loading is skeleton rows, with the header, toolbar, and column labels kept
  - the demo notice is always shown

### Task 35: The section page

**Files:** `src/features/handbook/section-page.tsx`; tests.

- [ ] **Tests first:**
  - the header fields, the demo notice, "State rules" or "Supplements", the body, Sources on an
    addendum, previous and next, and the chapter navigator
  - `?passage=p2` highlights that passage, scrolls it into view, and moves focus to it
  - "Clear highlight" works as Task 33 says
  - the neutral note for a section that doesn't apply, naming the person's location and linking to
    the company section
  - an unknown ID shows the missing-section page inside the shell
- [ ] **Known:** move focus after the section has rendered, and only once per `passage` value, so a
      refetch doesn't steal focus back.

### Task 36: The nav item, the home figure, and "Ask the assistant"

**Files:** `src/app/nav.ts`, `src/features/shell/app-shell.tsx`, the chat store,
`e2e/shell.spec.ts`; tests.

- [ ] **Tests first:**
  - every persona's nav includes Handbook. The `navFor` test and the e2e shell test that asserted
    it was absent both flip.
  - the at-a-glance list shows "Sep 12" (the version's `updatedOn`) and "Handbook updated", linking
    to `/handbook`, and the rail shows the list
  - "Ask the assistant" puts the search text in the composer's draft and goes to `/ask` without
    sending

### Task 37: Browser tests for each acceptance criterion, and the captures

**Files:** `e2e/handbook.spec.ts`, the capture manifest.

- [ ] One test per criterion in the notes, named after it (see the self-review table below),
      against the real API and the ingested handbook:
  - Priya's list marks only CA-3.4 and CA-4.3 (or whichever restricted sections cover her in the
    real handbook)
  - Mateo on CA-4.3 sees the neutral note
  - a deep link moves focus to the cited passage
  - search for "overtime" as Mateo puts 3.2 first
  - `/handbook/8.2` shows the missing-section page
  - axe on every state, and the 390 px check on both pages
- [ ] A capture row for each screenshot in `06-handbook/`.
- [ ] **Known:** CI runs Playwright with one worker. Run new tests with `--workers=1` locally before
      the PR.

### Task 38: Close Stage 5 and Phase 3

- [ ] **`CHANGELOG.md`:** "Phase 3, stage 5". **`docs/BACKLOG.md`:** delete the remaining Phase 3
      items. **`docs/ROADMAP.md`:** the row reflects the phase review still to come.
- [ ] `make check`, then the owner's capture review, then `/code-review medium`, then propose the
      commit and PR.
- [ ] **After it merges, review the whole phase:** `/code-review high` on `dev` against the commit
      recorded before Stage 1. Limit it to the code that counts toward the PR-size guideline:
      `apps/api/app`, `apps/api/migrations`, `apps/api/scripts`, `apps/api/pyproject.toml`,
      `evals/retrieval/run.py`, `apps/web/src` (minus `api/generated.ts`), the `Makefile`,
      `compose.yaml`, and `.github`.
- [ ] Fix real findings in a small follow-up PR, and backlog the rest. Phase 3 gets no separate
      security review (see `CLAUDE.md`).
- [ ] Mark the roadmap row Done, and set the "Next" note to planning Phase 4 at effort `high`.

---

## Phase 3 is done when

- [ ] The retrieval eval passes in CI: at least 90% hit rate at 5, and every negative case.
- [ ] Every statutory figure in the handbook has a source line, and the fact-check confirmed each.
- [ ] Every acceptance criterion in `06-handbook/notes.md` has a passing test (table below).
- [ ] axe finds no violations on any handbook state or gallery state, and nothing scrolls sideways
      at 390 px.
- [ ] The owner has approved the handbook text, the gallery, and the capture report.
- [ ] Each sandbox pins its version, and the API can't write the handbook tables.
- [ ] Every Phase 3 item in `docs/BACKLOG.md` is closed or moved, with its reason.
- [ ] The phase review's real findings are fixed.

## Self-review: acceptance criteria to tasks

| Criterion (06 Handbook) | Task |
|---|---|
| Matches the screenshots at 1440 px | Captures, 31, 37, 38 |
| Usable at 390 px: columns stack, the navigator moves, the panel covers, nothing overflows | 34, 35, 37 |
| The list shows every section of the pinned version, grouped, with "Applies to" and "Last updated" | 15, 23, 28, 34, 37 |
| In the list, the marker only on restricted sections that cover the person | 12, 23, 28, 37 |
| Section pages, results, and the panel show the marker on every section, with its icon | 27, 28, 30, 35, 37 |
| A section page shows its header, notice, link block, and Sources | 29, 35, 37 |
| A deep link scrolls, highlights, and moves focus; "Cited passage" is heard first | 29, 35, 37 |
| "Clear highlight" removes `passage` without a history entry | 33, 35, 37 |
| A section not in the version shows the missing-section page inside the shell | 23, 35, 37 |
| Search: applicable first, then by rank, matches emphasized; no results offers both actions | 23, 28, 34, 36, 37 |
| "Applies to me" keeps exactly the applicable sections, and the counts match | 19, 34, 37 |
| The panel: focus to the title, Escape and close, focus returns, scrolls inside, inline error | 30, 31 |
| The cinnamon bar is decoration, beside the label and icon | 29 |
| The navigator marks the current section `aria-current="page"` | 28, 35 |
| Keyboard and focus ring everywhere; axe is clean | 31, 37 |

**The Phase 3 backlog items:**
- "Applies to" and "Last updated" on each cited section (Tasks 23, 27, 30, 35)
- each sandbox pinned to a handbook version (9, 15)
- pin the pgvector image, pulled in from Phase 8 (7)
- hide SQL parameters from the error log, pulled in from "the first phase to bind user-written text"
  (18)

## Changes made during execution

Record here anything that differs from this plan, with the reason, each stage's final test counts,
and the retrieval eval's score at each stage close.

**The phase's base commit:** `8db9ef5` (`dev` after the plan merged). Task 38's phase review
diffs against it.

**Stage 1 (the handbook), 2026-10-07:**
- **PTO has a balance ceiling, not a carryover cap.** California (DIR's vacation FAQ, Labor Code
  §227.3) and Colorado (CDLE INFO #3E) forbid forfeiting earned vacation, and both count PTO as
  vacation, but both allow a ceiling at which new earning stops. Section 4.1 caps the balance at
  1.5 times a year's PTO (180 hours salaried, 144 hourly), nothing earned is ever lost, and unused
  PTO is paid out at separation. Phase 5's engine builds this rule, not Task 2's "carryover cap".
- **Three addendum sections were added,** for twelve in all: CA-5.1 (the California Family Rights
  Act, which has no 75-mile test, so Oakland staff qualify), CO-5.1 (Colorado's paid FAMLI
  program), and CO-3.4 (Colorado requires final pay immediately on discharge, sooner than the
  company's next-payday rule).
- **Colorado sick leave** (CO-4.3) is 48 hours on January 1, and unused hours carry over by raising
  the balance back to 48 each January, which meets the state's 48-hour rollover rule. Company
  section 4.3 stays at 40 hours front-loaded with no carryover, which California allows under its
  up-front method (DIR's posting amended effective 2026-01-01).
- **Federal FMLA likely reaches none of the locations** (none has 50 employees within 75 miles),
  so section 5.1 offers the company's own unpaid, job-protected leave on FMLA-like terms, as the
  owner decided.
- **Voting leave** (4.5) gives up to 2 paid hours when someone lacks 3 consecutive hours off work
  while the polls are open, generous enough for the Texas and Colorado tests.
- **Colorado requires the COMPS poster with any handbook.** CO-3.3 says Juniper Row hands it out;
  a real deployment would attach it.
- **Section titles** follow the design's list, and addenda reuse their company section's title.

**Stage 2 (schema, ingestion, and embeddings), 2026-10-07 to 2026-10-12:**
- **Versions:** the image is `pgvector/pgvector:0.8.7-pg17` (the newest 0.8.x for Postgres 17 on
  Docker Hub, published 2026-10-01). The dependencies resolved to `pgvector` 0.5.0,
  `markdown-it-py` 4.2.0, `pyyaml` 6.0.3, and `httpx` 0.28.1, plus `types-pyyaml` for mypy.
- **Pinning is done by the database** (migration 0005, the owner's decision after the batch A
  security review). A `BEFORE INSERT` trigger on `tenants` always sets `handbook_version_id` to
  the newest published version (by `published_at`, then `created_at`, then `id`), whatever the
  caller supplies, and raises SQLSTATE `OD001` when none is published. The sandbox service maps
  that to the 503 problem. Without it, the API's role could have pinned a draft or nothing. The
  migration also revokes `EXECUTE` from `PUBLIC` on both trigger functions.
- **Task 16's first `make embed` ran before Task 15.** With the trigger, every test that creates a
  tenant needs a published handbook, which needs the cache. 214 chunks, about 20,000 tokens, all
  inside the free allowance. `make db` and `make migrations-roundtrip` both end with `make ingest`.
- **YAML is read in the module, not the domain,** because Task 8 forbids `yaml` in `app.domain`.
  `app/modules/handbook/source.py` parses the files and hands `load_handbook(config, files)`
  `SourceFile`s with the parsed data and each field's line, so errors still name the file line.
- **`Asker.from_actor` became `load_asker(session, actor)`,** because the actor carries only the
  person and the tenant. It reads the person's state, employment type, and location under
  row-level security.
- **Schema details:** `handbook_chunks` copies `section_key` and `section_title` from its section,
  because a generated column can read only its own row. `heading` is nullable, for text before
  the first `##`. Every table has a UUID `id`.
- **Stricter validation than the spec:** an addendum applies to exactly its own state and can't omit `applies_to`; a file sits
  in the folder its ID implies and is named `{id}-{slug}.md`; a section needs at least one
  passage; links in headings and empty list items are refused. Lists record `ordered`.
- **The content hash covers the vectors and the parsed output,** not only the source files (a
  security review finding and a `/code-review` finding). A change to the committed cache alone,
  or a code change that renumbers passages or changes the stored blocks, makes a new hash, so it
  needs a new label and shows in review. Ingestion therefore embeds from the cache before checking
  for an unchanged version. Cached and ingested vectors must be finite and of unit length.
- **`make embed` is a separate command,** as this plan says, not the spec's `--fetch-missing`
  flag. Voyage is told not to truncate, so an over-long chunk fails loudly.
- **Voyage prerequisites were wrong** and are corrected above and in the spec: there's no spending
  cap (the budget limit only emails), an account without a card gets 3 requests a minute, and the
  training opt-out needs a card. An Atlas-created key works only with `ai.mongodb.com`. ADR 0008
  no longer says Anthropic "recommends" Voyage: its guide uses Voyage as its example provider.
- **Notes for Stage 3:** retrieval must take the version from the sandbox's tenant row, read
  under row-level security, never from a request. The `embed` command already fills an eval cache
  from `evals/retrieval/dataset.yaml`, accepting a list (or a `questions:` list) of strings or of
  mappings with a `question` key. Re-ingesting an older version's files reports "unchanged", doesn't
  republish it, and warns that the newer version stays current (a warning, not an error, so
  switching branches doesn't break `make db`).
- **Tests at the close:** 744 API tests (258 against the database), 773 web unit tests, and 108
  browser tests.

**Stage 3 (retrieval, the eval, and the handbook API), 2026-10-12:**
- **The retrieval eval scored 100% hit rate at 5 on its first run, with no tuning:** 53 of 53,
  mean reciprocal rank 0.863, all 14 negatives passing. The batch review then found three labels
  that accepted a section giving the wrong answer, one negative that could never fail, a filler
  entry in another, two questions that read as machine-written, and four sections that were
  never the sole answer. With the owner's OK (2026-10-12), the labels were tightened, the negative
  reworded so the forbidden sections rank without the filter, the two questions rewritten, and
  four sole-answer questions added (CO-5.1, TX-3.4, 2.1, 2.3). **The score after the change:**
  100% (57 of 57), mean reciprocal rank 0.841, all 14 negatives passing. 71 questions in all.
  Before anything ran, five questions were also reworded for voice.
- **The query is embedded outside the database session.** `embed_query(embedder, query)` runs
  first and returns the vector, or None after one logged warning, and
  `search_handbook(db, *, version_id, asker, query, query_vector, …)` takes the vector. Callers
  call `embed_query` before opening `tenant_session`, and take the version only from
  `pinned_version_id(db)`. A small `QueryEmbeddingLru` wraps the embedder for Phase 4.
- **`search_handbook` accepts up to 500 characters** (the browser's search route keeps 100), and
  drops control, format, surrogate, private-use, and unassigned characters. The spec says so now.
- **`location_code` reads the tenant's own locations under row-level security** for the state and
  the location names, and keeps the asker's employment type.
- **Migrations 0006 and 0007 store the chapter and addendum names, and the title, on each
  version,** written by ingest and backfilled for 2026.10, instead of copying `handbook.yaml`
  into code.
- **The eval runs as the app login** inside a scratch tenant (with the three seed locations) that
  it always rolls back, because `location_code` reads locations under row-level security. It
  refuses to run, with "run `make embed`", if any question's vector is missing, and counts any
  keyword-only fallback as a failure. Ruff and mypy now cover `evals/`.
- **The browser's search returns one result per section,** each with the `passageId` of the
  passage holding the match (an addition to the spec's table), so the link and the excerpt agree.
  Excerpts are built with `ts_headline` and control-character markers stripped from both the
  query and the stored text, so no HTML is ever sent and no match can be forged.
- **Search hits are per chunk,** so a section can appear twice in `search_handbook`'s results;
  the eval counts any chunk of an expected section.
- **Tests at the close:** 863 API tests (332 against the database) and 773 web unit tests.

## Backlog

New items from planning, added in the tasks named:
- **Map search hits to `search_result` blocks, and open the passage panel on a citation's passage**
  (Phase 4; Task 25).
- **Delete handbook versions no sandbox uses** (Phase 8; Task 25).
