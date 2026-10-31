# 0017. Scoreboards are generated from committed run boards

Status: Accepted · Date: 2026-10-31

## Context

The README and the app must show eval scoreboards, and Phase 7's done-when says they are
generated. Every live run writes a detailed run file, but `evals/assistant/runs/` is git-ignored,
because the files hold full traces. Nothing is committed, so the figures in the roadmap and the
changelog were copied by hand, and the app has nothing to read.

## Decision

- **Each live run also writes a board** to `evals/scoreboards/`, committed with the run's
  recordings: its metrics (mean and lowest trial), its facts (model, effort, prompt, tool-set,
  guard prompt, and judge versions, dataset hash, commit, trials, date), its cost, and its failures
  by item ID. No answer text and no traces. A free retrieval run writes one with `WRITE=1`.
- **Earlier runs are backfilled once** from the owner's local run files, so the history starts with
  Phase 4.
- **`make scoreboard`** is pure: it reads the boards and writes the README's scoreboard section
  (between markers) and `apps/web/src/generated/scoreboard.json` for the app.
- **CI runs it and fails on a difference,** like the API client's drift check.

## Rejected alternatives

- **Commit the full run files:** they hold every trace, megabytes a run, and model output that
  needn't be in the history twice (the recordings already are).
- **The API serves the scoreboard from the database:** a table to seed in every sandbox, and the
  public "How it's built" page would need a session.
- **Build the scoreboard during CI from the recordings:** CI replays one recorded trial, so it
  can't reproduce a live run's three-trial figures or its cost.

## Consequences

A run's figures appear only after its board is committed and `make scoreboard` is run, and CI
holds the two together. The boards are small, readable JSON, so a reviewer can trace each
published figure to its run and commit. The README's section is generated: hand edits between the
markers are overwritten.
