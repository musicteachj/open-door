# 0023. Phase 9 deploys to the shared portfolio server, and prompt 2026-11.5 ships without a full eval run

Status: Proposed · Date: 2026-11-20

This record is started in Phase 9a, Task 7, with its first decision. The deployment decisions are
added to it as Phase 9a makes them (Task 11 completes it).

## Context

Prompt 2026-11.5 fixes a bug found while recording the walkthrough: after a manager approved a
request, the asker was told it still waited for approval. The change touches what the model reads
(the system prompt and the "Since the last message" line), so the project's rule is a full live eval
run before its pull request (`CLAUDE.md`, "AI development rules"), about $10 to $15.

The owner wants the app launched without paid runs ("no expensive paid runs", 2026-11-18). Without a
full run, the committed recordings are 2026-11.4's, every offline replay request would miss, and CI
would stay red.

## Decision

- **The full eval run for prompt 2026-11.5 is waived for launch** (James, 2026-11-18). The
  walkthrough is recorded again after the deploy, and steps 5 and 6 are the check on the fix.
- **CI replays under the recorded prompt until then.** The offline replay of the smoke, full, and
  effort sets uses an archived copy of the 2026-11.4 prompt as the system prompt, checked against
  its golden hash and named by a pin in the fixtures folder. It tests the plumbing and the graders,
  not the new prompt. The next full `FRESH=1 PRUNE=1` run records 2026-11.5 and deletes the pin; a
  pin that names the current prompt is refused.
- **The published scoreboard stays 2026-11.4's** and is labeled so in `docs/AI-GOVERNANCE.md`.

## Rejected alternatives

- **Re-record the fixtures with the full run now:** the paid run is what the owner declined.
- **Re-record the fixtures with a smoke run:** it re-records only the smoke items, so CI would stay
  red for the rest of the set, and it would still be a paid run.
- **Skip the offline replay in CI until a full run:** the plumbing and the graders would go
  unchecked for as long as the waiver lasts.

## Consequences

- Prompt 2026-11.5's answers are unmeasured by the eval set until the full run after the deploy.
- The pin is temporary: deleting `recorded-under.json` and the archived prompt is part of the same
  change as the next full run's recordings (`docs/BACKLOG.md`).
