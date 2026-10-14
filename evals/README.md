# Evals

How we know the assistant's building blocks work. Each eval has its own folder here.

## Retrieval eval (`evals/retrieval/`)

**What it measures.** When an employee asks a question in plain words, does handbook search put
the right section in the top 5? `dataset.yaml` holds 67 labeled questions, written the way
people actually type into a help desk. Each one names an asker (a persona such as `mateo`, or a
state, employment type, and location), because search only returns sections that apply to that
person. A question has either:

- `expect`: section IDs that genuinely answer it for that asker. Any chunk of any of them in the
  top 5 is a hit.
- `must_not`: section IDs that must never come back for that asker (a negative), such as
  California sick leave for someone in Texas, or the hourly overtime sections for a salaried
  employee.

A few questions add `location_code`, which asks about another location's policy ("what's the
sick leave rule in California?").

**What it reports.**

- hit rate at 5 and mean reciprocal rank (MRR, the average of 1 / the place of the first right
  chunk), overall and per asker
- every miss, with the sections that came back instead
- every negative, passed or failed
- the search mode of each question. Any full-text-only fallback is a failure, because it means a
  query embedding was missing and search quietly stopped being hybrid.

**How to run it.**

```
make db               # once: Postgres, migrations, the handbook
make embed            # after adding or changing a question (needs VOYAGE_API_KEY); commit the cache
make eval-retrieval   # run the eval and print the report
```

`make embed` is the only step that calls Voyage. It writes the questions' vectors to
`evals/retrieval/embeddings/voyage-4-1024.jsonl`, and the eval reads them from there, so the eval
itself needs no key and no network. Direct use, from `apps/api`:

```
uv run python ../../evals/retrieval/run.py [--check] [--json PATH]
```

**What `--check` enforces.** It exits 1 when the hit rate is below 0.90, when any negative fails,
or when any search fell back to full-text only. It exits 2 when the eval can't run at all: an
invalid dataset (duplicate IDs, an unknown section, a question that changes under search's
cleanup), no published handbook in the database, or a question with no cached embedding, which
says "run `make embed` and commit the cache".

**What `--json PATH` writes.** The scoreboard: the model, the dimensions, the dataset's SHA-256,
the git commit, the date (UTC), the handbook version label, and the results (overall, per asker,
misses, negatives). Paste the change into a PR description when search, the chunking, or the
handbook changes.

**In CI.** The API job runs `run.py --check` after the tests, against the Postgres service and
the committed cache. It makes no network call and needs no Voyage key.

**Changing the dataset.** The questions are written from the handbook, before looking at what
search returns, and they don't change to raise the score. A wrong label can be fixed, with the owner's OK
and a note in the plan. The database login is the API's own (`DATABASE_URL`). The run opens one throwaway
tenant inside a transaction, because search reads the locations table through row-level security,
and rolls it back at the end, so nothing is left in the database.
