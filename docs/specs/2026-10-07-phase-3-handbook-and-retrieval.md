# Phase 3: handbook and retrieval

Written 2026-10-07. This spec goes deeper on Phase 3 of the
[product design](2026-09-29-open-door-design.md). Where the two disagree, this one is newer and
wins. The differences are listed under
[Changes from the product design and the brief](#changes-from-the-product-design-and-the-brief).
The approved design in [`../design/screens/06-handbook/`](../design/screens/06-handbook/notes.md)
is the visual source of truth, and this spec doesn't repeat it. It says how the build meets it.

**Goal:** Juniper Row has a real handbook: about 23 company sections and three state addenda,
fictional but written with care, with every statutory figure checked against its official source.
Anyone in a sandbox can browse it, search it, and open a deep link that highlights one passage. A
retrieval service finds the passages that answer a question and apply to the person asking. Phase
4's assistant cites those passages, and this phase proves the service finds the right ones.

**Done when** CI is green, the owner has approved the handbook text and the side-by-side
captures, and these are proven:

- **The retrieval eval** reaches a hit rate of at least 90% at 5, and every negative case passes.
  It runs in CI on every change to the handbook, the retrieval code, or the eval, from committed
  embeddings, with no paid call.
- **Every acceptance criterion** in the [handbook notes](../design/screens/06-handbook/notes.md) has
  a named test, listed in the plan's self-review table. axe reports no violations, and no page
  scrolls sideways at 390 px.
- **Every statutory figure** in the handbook has a source line naming the statute or official page
  and the date it was read.
- **Each sandbox is pinned** to the handbook version it was created with, and the handbook tables
  are global and read-only to the API.

---

## Decisions made while designing (owner-approved, 2026-10-07)

- **The statutory figures are verified in the handbook stage,** by the session that writes the
  text, against the official source. This spec names the topics each addendum covers, not the
  figures, so nothing is verified twice.
- **The handbook ships first, as its own content-only pull request,** with the owner's
  read-through and no `/code-review`. Ingestion, the eval, and the design's sample text are all
  built on settled words.
- **The browser's search box uses full-text search only.** It's free, instant, deterministic, and
  it knows which words matched, which the design emphasizes. Hybrid search is for the assistant and
  the eval.
- **Negative cases are applicability negatives.** For a given asker, a section that doesn't apply
  to them must never be returned. Questions the handbook can't answer belong to Phase 4's Q&A eval:
  fused rank scores can't reliably say "nothing here is relevant".
- **A hit is any passage from an expected section in the top 5.** Mean reciprocal rank is reported
  beside it, so ranking quality stays visible.
- **The eval set is about 60 questions,** written by Claude in employees' own phrasing before any
  tuning, and reviewed by the owner in the pull request. About 15 are negatives.
- **One Opus security reviewer** checks the schema-and-ingestion stage, which changes database
  grants and the `tenants` table. Every other stage gets the normal review.
- **Embeddings: Voyage `voyage-4` at 1,024 dimensions.** Each passage is embedded with its section
  number and title in front of it. `voyage-context-4` is the fallback if the eval misses 90%.
- **Versions:** a new sandbox pins the newest published version. A version stays while any sandbox
  uses it, and deleting unused ones is backlogged for Phase 8's cleanup job.
- **The plan gives outlines, not pre-run code,** as in Phase 2.

---

## Changes from the product design and the brief

| Earlier documents said | Phase 3 does | Why |
|---|---|---|
| Retrieval is hybrid (product design) | The assistant and the eval use hybrid search; the browser's search box uses full-text only | The browser needs matched words and instant results, and it shouldn't send every keystroke to Voyage |
| Query embeddings are cached so the eval is deterministic | The passage embeddings are cached too, in committed files, and CI never calls Voyage | "No paid AI calls on push or PR" applies to Voyage as much as to Anthropic. With both caches committed, the eval is a real CI gate at no cost |
| The eval includes "negative-applicability cases" | Negatives are applicability only; unanswerable questions move to Phase 4 | See the decisions above |
| A source chip reads "Handbook §4.3 · California addendum" (brief) | Addendum sections have their own IDs, such as `CA-4.3`, and the chip reads "Handbook CA-4.3 · California addendum" | The approved design: the ID is the same in the list, the URL, and the chip |
| Markdown is sanitized with DOMPurify (product design, for answers) | The handbook is a restricted markdown subset, validated at ingest and served as structured blocks; nothing renders HTML | No HTML ever reaches the page, so there is nothing to sanitize. DOMPurify stays Phase 4's tool for the model's answers |
| Pin the pgvector image (backlogged for Phase 8) | Done in Phase 3 | Phase 3 is the first phase to depend on the extension |
| Hide SQL parameters from the error log (backlogged for "the first phase that binds user-written text") | Done in Phase 3 | A search query is user-written text |
| The embedding model is chosen at build time | `voyage-4`, 1,024 dimensions, pinned in code | Decided now, with the eval as the check |

---

## The handbook

### Files

```
handbook/
  handbook.yaml            the version label, the title, the chapters, the addenda, and the
                           location names
  sections/
    1.1-about-this-handbook.md
    …
    4.3-sick-leave.md
  addenda/
    ca/CA-4.3-sick-leave.md
    co/CO-4.3-sick-leave.md
    tx/TX-3.4-final-pay.md
  embeddings/
    voyage-4-1024.jsonl    the committed passage-embedding cache (see Embeddings)
```

`handbook.yaml` holds the version label (`2026.10`), the handbook's title, the chapter names
("Time off"), the addendum names ("California addendum"), and the location codes the handbook may
name (`den`: "Denver HQ"). The locations are the seed company's, so a test checks that the codes
match the seed's.

### Front matter

Every section file starts with YAML front matter:

```yaml
id: CA-4.3                 # unique within the version; the URL and citation ID
title: Sick leave
updated: 2026-09-12        # "Last updated", an authored date
applies_to:                # every list is optional; an empty or missing list doesn't restrict
  states: [CA]
  employment_types: []     # salaried, hourly
  locations: []            # handbook.yaml location codes
supplements: "4.3"         # addenda only: the company section this one adds to
sources:                   # addenda and any section with a statutory figure
  - "California Labor Code §246, read from leginfo.legislature.ca.gov on 2026-10-08."
```

A company section's ID is its number (`4.3`) and its chapter comes from the number. An addendum
section's ID is the state code and the company section's number (`CA-4.3`), and its `supplements`
must name a company section that exists. Ingestion refuses a file whose ID doesn't match its
file name.

### The markdown subset

Ingestion accepts only:

- `##` and `###` headings (the title is the front matter's, so no `#`)
- paragraphs
- bulleted and numbered lists, one level deep
- **bold** and *italic*
- links to another section, written `[§4.3 Sick leave](handbook:4.3)`, whose target must exist

Anything else fails ingestion with the file and line: raw HTML, images, tables, code, quotes,
nested lists, and external links. The subset keeps the content plain, keeps every passage
citable, and means the API serves structured blocks the web app renders as React elements, never
HTML. Links go only to handbook sections, so the handbook can't carry a phishing link either.

### Passages and their IDs

Each paragraph and each list in a section is a **passage**, numbered in order: `p1`, `p2`, and so
on. Headings aren't passages. The deep link `/handbook/CA-4.3?passage=p2` names one. IDs are
stable within a version, and a sandbox only ever sees its own version, so a link never points at
changed text.

### Contents

The approved design's list is the plan. The handbook stage may change titles, and may add an
addendum section where a state's law genuinely differs from the company section (California's
family leave law and Colorado's paid family leave program are the likely ones). The cap is about
23 company sections and 12 addendum sections.

| Chapter | Sections |
|---|---|
| 1 Welcome | 1.1 About this handbook · 1.2 Employment types |
| 2 Working here | 2.1 Equal opportunity · 2.2 Harassment and discrimination · 2.3 Raising a concern · 2.4 Workplace conduct |
| 3 Hours and pay | 3.1 Schedules and timekeeping · 3.2 Overtime · 3.3 Meal and rest breaks · 3.4 Paydays and final pay |
| 4 Time off | 4.1 Paid time off · 4.2 Holidays · 4.3 Sick leave · 4.4 Bereavement leave · 4.5 Jury duty and voting |
| 5 Leaves of absence | 5.1 Family and medical leave · 5.2 Parental leave · 5.3 Accommodations |
| 6 Health, safety, and support | 6.1 Workplace safety · 6.2 Employee Assistance Program |
| 7 Privacy and confidential cases | 7.1 Your personal information · 7.2 How confidential HR cases work |

| Addendum | Sections, and what each must cover |
|---|---|
| California | CA-3.2 daily and weekly overtime and double time · CA-3.3 meal and rest periods, and the premium for a missed one · CA-3.4 final pay timing · CA-4.3 paid sick leave: the amount, front-loading, carryover, and uses |
| Colorado | CO-3.2 daily and weekly overtime · CO-3.3 meal and rest periods · CO-4.3 paid sick leave under the state's Healthy Families and Workplaces Act: the amount, front-loading, carryover, and uses |
| Texas | TX-3.4 final pay timing · TX-4.5 jury duty and voting leave |

**Rules for the text:**

- **Every statutory figure** (an amount, a threshold, a deadline) has a line in `sources` naming
  the statute or official page and the date it was read: CA DIR, CO CDLE, TX TWC, the U.S.
  Department of Labor, or the statute itself. The session that writes the figure reads the source.
- **Company figures are fictional policy,** chosen to be at least what the law requires: PTO
  accrual per month by employment type, its carryover cap, the company's own sick-leave amount for
  states without a law, bereavement days. They need no source, and Phase 5's time-off engine is
  built from them.
- **The Texas default.** Texas has no paid sick leave law, so Mateo's answer comes from the
  company section, 4.3. The handbook stage confirms this against the official source too.
- **Holidays (4.2) say exactly what `app/domain/holidays.py` does:** the six holidays, the
  observed-date rule, and Denver HQ also closing the day after Thanksgiving. A test checks that
  every holiday the code names appears in 4.2.
- **Overtime and meal breaks** are written for hourly staff, and the handbook only states the
  rules. Nothing in Open Door calculates overtime.
- **Section 1.1** says Juniper Row is fictional and the handbook is demo content, not legal advice.
  The browser shows the same notice on every page.
- **Original text,** never copied from a real employer's handbook. American English, plain and
  specific, in the brief's voice.
- **No employment decisions.** The handbook describes the process for a concern or a leave. It
  never tells a manager what outcome to reach (invariant 5).

---

## Data model

Three global tables, outside row-level security, and one new column. Migration 0004 adds them.

### `handbook_versions`

| Column | Holds |
|---|---|
| `id` | UUID |
| `label` | `2026.10`, from `handbook.yaml`; unique |
| `content_hash` | A SHA-256 over the source files, the chunker's version, and the embedding model and dimensions; unique |
| `embedding_model`, `embedding_dimensions` | `voyage-4`, 1024 |
| `updated_on` | The latest section's `updated` date: the "Handbook updated" figure |
| `published_at` | When ingestion published it; null for a version loaded but not published |
| `created_at` | When it was loaded |

### `handbook_sections`

One row per section per version: `version_id`, `section_key` (`4.3`, `CA-4.3`), `position` (the
handbook's order), `kind` (`company` or `addendum`), `chapter` or `addendum_state`, `title`,
`supplements_key`, `audience` (JSON: `states`, `employmentTypes`, `locations`), `updated_on`,
`sources` (a JSON list of strings), and `blocks` (the structured body: headings, passages with
their IDs, and inline runs). It's unique on `(version_id, section_key)`.

### `handbook_chunks`

What retrieval searches: `version_id`, `section_id`, `position`, `heading` (the `##` it sits
under), `passage_ids` (the passages it covers, in order), `text`, `search` (a generated
`tsvector`: the section's ID, title, and heading weighted A, the text weighted B), and
`embedding` (`vector(1024)`, not null).

- A chunk is the run of passages under one heading, split before about 350 tokens. A passage is
  never split, so a citation maps to whole passages.
- A GIN index serves full-text search. **The vector search is an exact scan, with no approximate
  index:** a version has a few hundred chunks, so the scan takes milliseconds, and an exact result
  never varies.

### `tenants.handbook_version_id`

A nullable foreign key to `handbook_versions`, `ON DELETE RESTRICT`, so a version in use can't be
deleted. `create_sandbox` sets it to the newest published version, and refuses to create a sandbox
(a 503 problem) if none is published. It's nullable only because sandboxes created before the
migration have none. They expire within 24 hours, and the handbook endpoints answer them with a
404 problem until then.

### Grants and roles

- **`od_app` gets `SELECT`** on the three handbook tables, and nothing else on them. The
  exact-grants test lists this.
- **`od_cleanup` gets nothing** on them.
- **Ingestion runs as the database owner,** through `MIGRATION_DATABASE_URL`, like the bootstrap
  script. The API can never write the handbook.
- The tables have no `tenant_id`, so the row-level-security coverage test rightly skips them. A new
  test asserts that the API's role can't insert, update, or delete any handbook row.

---

## Ingestion

`apps/api/scripts/ingest_handbook.py`, run by `make ingest`:

1. **Parse** `handbook.yaml` and every section file.
2. **Validate:** the front matter, the markdown subset, the IDs and file names, every
   `supplements` and `handbook:` link target, the location codes, and no duplicate IDs. It
   reports every error at once, with file and line.
3. **Build** each section's blocks and passages, then its chunks.
4. **Embed** each chunk from the cache (see below). A miss fails, unless `--fetch-missing` is
   given and a Voyage key is set.
5. **Load** the version, its sections, and its chunks in one transaction, and publish it.

- **It's idempotent.** If a version with the same content hash exists, it does nothing. If the
  label exists with a different hash, it fails and asks for a new label. A published version is
  never changed.
- **`make db` ends with `make ingest`,** so a fresh development database has a handbook, and so do
  the CI database and the e2e database.
- **Pure parts** (parsing, validation, passages, chunking, applicability) live in
  `app/domain/handbook/`, with no framework imports. Loading and the command line live in
  `app/modules/handbook/` and the script.

---

## Embeddings

- **Model:** Voyage `voyage-4`, 1,024 dimensions, float, pinned in code beside the version's
  record. Changing the model or the size changes every version's content hash, so it's a new
  version.
- **What's embedded:** for a chunk, `"{id} {title} · {addendum name or chapter name}\n{heading}\n\n{text}"`,
  with `input_type: "document"`. For a query, the question alone, with `input_type: "query"`.
- **The client** is a small module in `app/ai/embeddings.py` that calls Voyage's REST endpoint
  through `httpx`. The SDK isn't needed for one endpoint. It batches by Voyage's per-request
  limits, retries a 429 or 5xx with backoff, and has a timeout. Tests use a fake.
- **The caches** are JSON Lines files. Each line is a key (a SHA-256 of the model, the dimensions,
  the input type, and the text) and the vector, as base64 float32. The handbook's is
  `handbook/embeddings/voyage-4-1024.jsonl`, about 1 MB, and the eval's queries are in
  `evals/retrieval/embeddings/voyage-4-1024.jsonl`.
  - `make embed` fills both caches' misses from Voyage and drops entries nothing uses. It's the
    only command that calls Voyage, and it needs `VOYAGE_API_KEY`.
  - **A miss in CI fails** with the message "run `make embed` and commit the cache", like a missing
    replay fixture.
- **At run time** (Phase 4's assistant), the question is embedded through a small in-process cache
  keyed by the same hash. It holds hashes and vectors, never the question's text.
- **If Voyage fails** (no key, a timeout, an error), search runs full-text only, logs a warning
  event with the reason, and reports `mode: "fulltext"` in its result, which Phase 7's console will
  show.
- **Settings:** `VOYAGE_API_KEY`, optional (a `SecretStr`). Without it, ingestion works from the
  cache and search falls back to full-text. CLAUDE.md's empty-shadowing gotcha applies to it as
  well.

---

## Retrieval

`search_handbook(db, *, version_id, asker, query, location_code=None, limit=5)` in
`app/modules/handbook/` is the service Phase 4's tool calls. It's tested now and has no HTTP route
in Phase 3. `asker` is an `Asker` (state, employment type, location code). Routes and tools build
it only with `Asker.from_actor(actor)`, from the session. The eval builds it directly, so it can
ask as people who aren't personas.

### Who a section applies to

A section applies to a person when each `applies_to` list is empty or contains theirs: their
location's state, their employment type, and their location's code. One pure function decides it,
and the SQL filter must agree with it. A test compares the two for every section against every
combination of state, employment type, and location in the seed.

- **The asker comes from the session,** never from input (invariant 1).
- **`location_code`** is the assistant's way to answer "what's the California policy?" for
  someone in Texas. It replaces the asker's state and location for the filter, and keeps their
  employment type. The result says which location it used, so the answer can say whose policy it
  is.
- **Applicability decides relevance, not permission.** The whole handbook is readable by everyone.
  The filter keeps answers correct, not secrets safe.

### Hybrid search

1. **Full-text:** the query's words, joined with OR and ranked with `ts_rank_cd`, top 20 chunks.
   The browser's search, by contrast, requires every word.
2. **Vector:** cosine distance between the query's embedding and each chunk's, top 20 chunks.
3. **Both run only over the sandbox's pinned version and the applicable sections.**
4. **Fuse** with reciprocal-rank fusion: each chunk scores the sum of `1 / (60 + rank)` over the
   lists it appears in. Ties break by section position, then chunk position, so the order never
   varies.
5. **Return the top `limit` chunks,** each with its section ID, title, addendum or chapter name,
   audience label, "Last updated", passage IDs, passage texts, its deep link, and both ranks.

The query is embedded before any database work starts, so a slow Voyage call never holds a
transaction open.

### The shape Phase 4 cites

Each hit maps one to one onto a Claude `search_result` block:

- `source`: the deep link to its first passage, `/handbook/CA-4.3?passage=p2`
- `title`: "CA-4.3 Sick leave · California addendum"
- `content`: one text block per passage

A citation's block index then names a passage, so the answer view can open the passage panel on
exactly the cited passage. Phase 4 writes the mapping. Phase 3 makes sure the hit carries what it
needs.

---

## The handbook API

All routes need a session, read only the sandbox's pinned version, and declare their errors
through the existing problem helper. A sandbox with no pinned version gets a 404 problem.
`appliesToMe` is worked out on the server from the session's person.

| Route | Returns |
|---|---|
| `GET /api/v1/handbook` | The version (label, title, `updatedOn`), then every section in order: ID, title, chapter or addendum, audience, audience label, `appliesToMe`, `lastUpdated`, plus the chapter and addendum names. The browser's list, its counts, and the home page's "Handbook updated" figure all come from this |
| `GET /api/v1/handbook/sections/{sectionId}` | One section: the list fields, plus its blocks, the section it supplements or the addenda that supplement it (each with `appliesToMe`), its sources, and the previous and next sections. A 404 problem if the ID isn't in the version |
| `GET /api/v1/handbook/sections/{sectionId}/passages/{passageId}` | One passage with the passages before and after it and the section's header fields: what the passage panel shows. A 404 problem if either ID is missing |
| `GET /api/v1/handbook/search?q=` | Full-text search, every word required, up to 100 characters. Sections that apply to the person come first, then by rank. Each result has the section's list fields and one excerpt, served as segments (`{text, match}`) so the browser can emphasize the matched words without HTML |

- **Excerpts:** `ts_headline` with private marker characters instead of tags, split into segments
  on the server.
- **The engine sets `hide_parameters=True`,** so a failed statement never logs a search query (or a
  vector) with its bound values.

---

## The handbook browser

The screens, states, and copy are in the [notes](../design/screens/06-handbook/notes.md). The build
adds these rules.

| Route | Shows |
|---|---|
| `/handbook` | The handbook home. The search and the filter live in the URL: `?q=` and `?show=mine` |
| `/handbook/:sectionId` | A section. `?passage=p2` highlights a passage and moves focus to it |

- **The nav's Handbook item** turns on for everyone. The shell test that asserted it was absent
  flips.
- **The assistant home's at-a-glance list** gains its first item: the version's `updatedOn` ("Sep
  12") with "Handbook updated", linking to `/handbook`. The rail shows the list once it has an
  item.
- **Search** updates the URL after a 250 ms pause, replacing the history entry, as in the
  directory.
- **"Ask the assistant"** on no results goes to `/ask` with the search text in the composer's
  draft, not sent.
- **"Clear highlight"** replaces the URL without `passage`.
- **The passage panel** is built and shown in every state in the gallery, with its focus behavior
  tested. It's first docked beside an answer in Phase 4. Its data comes from the passages endpoint.
- **Blocks render as React elements:** headings, paragraphs, lists, and inline runs (bold, italic,
  and in-app links to sections). No HTML string is ever rendered.

---

## Evals

```
evals/
  retrieval/
    dataset.yaml           the labeled questions
    embeddings/            the committed query-embedding cache
    run.py                 the runner
  README.md                what each eval measures, and how to run it
```

**Each question** has an ID, the asker (state, employment type, and location code, or a persona
name that stands for them), the text, and either `expect` (one or more section IDs, any of which is
a hit) or, for a negative, `must_not` (section IDs that must not appear). It may have a
`location_code` to test the "California policy" case.

**The set,** about 60 questions:

- spread across the four personas, plus hourly staff in Colorado and California, who aren't
  personas
- every chapter, and every addendum section
- paraphrases that share few words with the handbook, such as "Can I stay home when my kid has the
  flu?"
- about 15 negatives, such as Mateo's sick-leave question, which must never return CA-4.3 or
  CO-4.3, and Priya's overtime question, which must never return a section for hourly staff
- a few `location_code` questions

The questions are written before any tuning, from the handbook text, in employees' own phrasing,
and the owner reviews them in the pull request.

**The runner** loads the version from the database, embeds each question from the cache, runs
`search_handbook`, and reports:

- hit rate at 5 and mean reciprocal rank, overall and per persona
- each miss, with what came back
- each negative, passed or failed
- the scoreboard fields: the model, the dimensions, the dataset's hash, the commit, and the date

`make eval-retrieval` runs it locally. **CI runs it in the API job after the tests**, failing below
90% or on any negative, with no network.

**Budget:** Phase 3 makes no Anthropic call. Voyage costs a fraction of a cent: the handbook and
the questions together are well under a million tokens, inside the free allowance. No live Claude
eval is needed, because no prompt, tool schema, or guard changes.

---

## Security

The Opus reviewer for the schema-and-ingestion stage is briefed on:

- the API role's exact grants: `SELECT` only on the handbook tables
- the global tables outside row-level security, and why that's safe (company-public content, no
  tenant data, no personal data)
- `tenants.handbook_version_id`: who sets it, and that a sandbox never reads another version
- ingestion as the owner, and that nothing in the API path can write a handbook row
- the markdown subset as the guard against HTML and external links in content

The later stages carry these guarantees, checked by the normal review:

- the search query is bound, never interpolated, and capped: 100 characters for the browser's
  search route, 500 for `search_handbook`, which takes the assistant's sentence-length questions
- `hide_parameters` is set
- the asker always comes from the session
- the excerpt markers can't be forged by the query: they're control characters, stripped from the
  input

---

## Testing

**Pure (pytest, no database):**

- front matter and markdown-subset validation: one test per rejected construct, each naming the
  file and line
- passage numbering and chunking: a passage is never split, and chunks follow headings and the
  size cap
- applicability: every combination of empty and non-empty lists
- reciprocal-rank fusion: hand-worked rankings, ties, and a chunk in one list only
- the cache key, and the base64 round trip
- every holiday in `holidays_for` appears in section 4.2
- the real handbook passes validation (this runs in CI on every handbook change)

**Integration (Postgres, as `od_app_login` unless noted):**

- ingestion, as the owner, inside a transaction that's rolled back, so the published handbook
  stays as it is: a fixture handbook loads, a second run is a no-op, and a changed file with the
  same label fails
- grants: the API role can read the handbook tables and can't write them
- a new sandbox pins the newest published version; a sandbox can't see another version's sections
  through the API; no published version means a 503 problem
- the SQL applicability filter agrees with the pure function
- hybrid search: deterministic order, `location_code`, and the full-text fallback with a failing
  embedder
- the API: each route's fields, `appliesToMe` per persona, the 404 problems, search order and
  segments, a 101-character query gets 422, and anonymous gets 401
- `hide_parameters`: a failing statement's log has no bound values

**The retrieval eval** in CI, as above.

**Web unit and component tests** (Vitest and Testing Library, with MSW): each new component in
every state from the notes, block rendering (no `dangerouslySetInnerHTML` anywhere, checked by a
test that scans `src/`), the URL state, and the panel's focus behavior.

**End to end** (Playwright with axe, as in Phase 2): one test per acceptance criterion, named after
it; the 390 px check on each page; a deep link moving focus; and the capture report for the
owner's side-by-side review.

---

## Docs and housekeeping

- **`docs/DATA-INVENTORY.md`:** the three handbook tables (no personal data, global, kept while a
  sandbox uses their version) and `tenants.handbook_version_id`. Voyage gets a new section under
  "Outside the database": handbook text is sent to it now, questions from Phase 4. The run-time
  query cache holds no text.
- **`docs/BACKLOG.md`:** remove the Phase 3 items this phase closes, plus "pin the pgvector image"
  and "hide SQL parameters". Add to Phase 8 "delete handbook versions no sandbox uses", and to
  Phase 4 "map search hits to `search_result` blocks, and open the panel on a citation's passage".
- **ADR 0008:** handbook retrieval runs hybrid search in Postgres, with embeddings cached in the
  repository. It's written with this spec.
- **`CLAUDE.md`:** add `make ingest`, `make embed`, and `make eval-retrieval` to the commands.
- **`compose.yaml` and CI:** pin `pgvector/pgvector` to a `0.8.x-pg17` tag.

**Owner prerequisites,** needed before the first `make embed` in Stage 2:

1. A Voyage account and API key, created on Voyage's own dashboard (an Atlas key works only
   with MongoDB's `ai.mongodb.com` address), put in `apps/api/.env` as `VOYAGE_API_KEY`.
2. A payment method on file. Without one, Voyage allows 3 requests and 10,000 tokens a minute,
   too few for the first run. The free tokens still apply.
3. A budget alert. It only sends an email: Voyage has no hard spending cap, so a project rate
   limit is the only real ceiling.
4. Model-training data collection turned off for the organization. MongoDB's documentation says
   it *can* use data sent to the API to improve Voyage's models. Opting out needs the payment
   method, and can't be undone from the dashboard.

> Source: Voyage AI pricing, embeddings, and rate-limit documentation, docs.voyageai.com, read on
> 2026-10-06. MongoDB, "Model training data" for Voyage AI, mongodb.com/docs/voyageai, read on
> 2026-10-07. Voyage's 429 message for accounts without a payment method, its FAQ (opting out of
> training), and MongoDB's "Manage Voyage AI Model API Keys", read on 2026-10-12.

---

## Delivery: five stages

Each stage is a pull request into `dev`, sized to the 1,500-line guideline. The
[plan](../plans/2026-10-07-phase-3-handbook-and-retrieval.md) has the tasks.

1. **The handbook:** the sections and addenda, every figure verified and sourced, written to the
   front matter and markdown subset above. The owner's read-through, with no code review. Stage
   2's validator then checks the real handbook, and fixes any format slip it finds.
2. **Schema, ingestion, and embeddings:** migration 0004, the grants, pinning at sandbox creation,
   the parser and chunker, the Voyage client and caches, `make ingest` and `make embed`, the
   pgvector pin, and the data inventory. Plus one Opus security reviewer.
3. **Retrieval, the eval, and the handbook API:** hybrid search and its fallback, the eval set,
   the runner and its CI gate, the four routes, `hide_parameters`, and the regenerated client.
4. **The handbook components,** in every state in the gallery, with their tests.
5. **The handbook pages,** the nav item and the home figure, the browser tests per acceptance
   criterion, and the phase close.

The UI stages (4 and 5) end with `make check`, the e2e job green, and the owner's review of the
capture report. Every stage ends with `/code-review medium` on the whole branch, except Stage 1,
which is content only. The phase closes with `/code-review high` on its application code. Phase 3
gets no phase-wide security review (see `CLAUDE.md`).

---

## Later phases

- **Phase 4:** the `search_handbook` tool and its `search_result` mapping, the source chip, the
  passage panel docked beside an answer, the Q&A eval with unanswerable questions, and the
  run-time query cache in use.
- **Phase 5:** the time-off engine, built from the handbook's PTO and sick-leave figures.
- **Phase 7:** the console shows each search's mode and passages, and the scoreboard shows the
  retrieval eval's history.
- **Phase 8:** delete handbook versions no sandbox uses.

---

## Sources

- **The approved design:** [`../design/screens/06-handbook/notes.md`](../design/screens/06-handbook/notes.md),
  approved on 2026-10-07.
- **The Phase 3 items in [`../BACKLOG.md`](../BACKLOG.md),** and the 2026-10-06 brainstorm's
  decisions in [`../design/BRIEF.md`](../design/BRIEF.md).
- **[The Phase 1 spec](2026-10-03-phase-1-tenancy-identity-permissions.md)** for tenancy, roles,
  and grants, and **[the Phase 2 spec](2026-10-05-phase-2-design-system-shell-sandbox-entry.md)**
  for the web conventions this phase follows.
- **Voyage AI:** https://docs.voyageai.com/docs/pricing, https://docs.voyageai.com/docs/embeddings,
  and https://docs.voyageai.com/docs/rate-limits, read on 2026-10-06; and
  https://www.mongodb.com/docs/voyageai/management/model-training-data/, read on 2026-10-07.
- **Reciprocal-rank fusion:** Cormack, Clarke, and Büttcher, "Reciprocal Rank Fusion outperforms
  Condorcet and individual Rank Learning Methods", SIGIR 2009. The constant 60 is the paper's.
