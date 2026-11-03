# 0018. Claude Opus 5.5 stays the assistant's default model

Status: Accepted · Date: 2026-11-03

## Context

The assistant has run on Claude Opus 5.5 at low effort since Phase 4. Claude Sonnet 5.5 costs
half as much per token, so Phase 7 measured it against Opus 5.5 on one commit. Both arms used the
same prompt, tool set, judge, and datasets: the full set with fairness, 206 items, three trials
each, low effort. The safety check stays on Haiku 5.5, so the escalation set wasn't rerun.

- **The baseline:** the Opus 5.5 full run of 2026-11-03 (`20261103T140018Z-full`, $15.20), from
  Phase 7, Stage 3.
- **The Sonnet arm:** the Sonnet 5.5 full run of 2026-11-03 (`20261103T184543Z-full`, $9.44, cap
  $13), on `dev` at `02ec9c8`. Its only change was the comparison harness, which nothing the model
  reads depends on. The Opus recordings replay on that commit, so both runs saw the same requests.

The decision rule was written in the [Phase 7 spec](../specs/2026-10-31-phase-7-ai-ops-reviewer-model.md)
before either run. Sonnet 5.5 becomes the default if, on the same commit:
- the red team is at 100% in every trial;
- on every other program-graded set (Q&A checks, unanswerable, actions, numbers, case summary),
  its mean is no more than one item's worth below Opus's;
- it meets every fairness bar; and
- its judge pass rate is within 3 points of Opus's (no more than 3 points below it).

**One reading was settled before the Sonnet run.** The Opus baseline fails the fairness bars
itself: Good Friday never gets the religious-accommodation route, there is one age remark, and
judge equivalence is 85% against a 90% bar. On 2026-11-03 the owner chose to read "meets every
fairness bar" as "no worse than Opus on every fairness measure": groups consistent, identity
assumptions, and judge equivalence.

## Decision

**Opus 5.5 stays the default** for the assistant and the case summarizer. Sonnet 5.5 fails two of
the rule's bars, and the owner picked Opus on that result.

| Measure | Opus 5.5 | Sonnet 5.5 | Sonnet needs | Result |
|---|---|---|---|---|
| Red team | 100% (lowest trial 100%) | 98.9% (lowest trial 98.4%) | 100% in every trial | Fail |
| Q&A checks | 99.1% | 98.1% | at least 97.7% | Pass |
| Unanswerable | 96.7% | 100% | at least 86.7% | Pass |
| Actions | 100% | 97.1% | at least 97.1% | Pass, at the bar |
| Numbers | 100% | 99.0% | at least 97.1% | Pass |
| Fairness: groups consistent | 91.7% | 91.7% | at least 91.7% | Pass |
| Fairness: identity assumptions | 0.33 a trial | 0 | at most 0.33 | Pass |
| Fairness: judge equivalence | 84.5% | 83.3% | at least 84.5% | Fail, by one pair of 84 |
| Judge (Sonnet 5.5 grading) | 73.2% | 83.3% | at least 70.2% | Pass |
| Uncited claims a trial | 16.3 | 8.0 | - | - |
| Case summary | 22 of 22 | not run | within one note | - |
| Assistant cost per item | $0.018 | $0.009 | - | - |
| Run cost (assistant and judge) | $15.20 | $9.44 | - | - |
| Time per item, median (95th percentile) | 7.4 s (12.6 s) | 5.2 s (7.8 s) | - | - |
| Model calls answered by a fallback | 0 | 3 (one red-team item, every trial) | - | - |
| Refusals | 0 | 0 | - | - |

- **Why the red team failed:** Sonnet 5.5 sometimes writes a tool call as plain answer text.
  Open Door rejects that and asks again once, and Sonnet did it again on the second try. The
  person then gets an error instead of an answer. This happened on a workplace-safety report ("the
  back loading dock door is broken ... somebody is going to get crushed") in two of three trials.
  It also happened on a plain lunch-break question in all three trials. Opus had none.
- **The judge figure favors Sonnet with a caveat:** the judge is Sonnet 5.5 too, grading its own
  model. Sonnet's fairness religion group reads as consistent only because all four variants miss
  the accommodation route, not just Good Friday.
- **Times are whole-call times.** The recorder times each call from start to end of its stream. It
  records no time to the first token, and the Opus baseline couldn't be timed again, so the table
  gives the time per item instead.

## Rejected alternatives

- **The Opus 5.5 judge spot check** (about $1.50, cap $3) re-judges the items the two arms' judge
  results differ on, to check the judge's bias. It wasn't run: the red team bar fails on program
  grading, and a judge result can't change that. The command (`run.py --rejudge`) is built and
  tested for the next comparison.
- **The Sonnet 5.5 case-summary set** (about $0.35, cap $3) wasn't run, for the same reason. It
  would only matter if Sonnet were picked.
- **A Sonnet 5.5 medium-effort arm** (about $11, cap $15) wasn't run. The misses come from a
  formatting habit (tool calls written as text), not from too little reasoning, and Phase 4's
  effort comparison found medium fixed none of low's misses.
- **Pick Sonnet 5.5 anyway for its cost and speed:** it would halve the assistant's cost and cut
  answer time by about a third, but it would ship a model that leaves a safety report unanswered.

## Consequences

- Nothing switches: `CURRENT_PINS` and `SUMMARY_MODEL` stay on `claude-opus-5-5`, and the
  committed fixtures stay Opus's. The Sonnet run's board is committed as a comparison board, and
  the scoreboard's history lists it with its model. Its recordings stay in the git-ignored
  `fixtures-sonnet/`.
- The fairness findings (Good Friday, the age remark) are fixed on Opus 5.5, with a prompt line
  and a full run before the release.
- **A later comparison** reuses this harness: `MODEL=` on a full run with its own estimate and cap,
  `--compare` with the timing, fallback, refusal, and cost rows and the rule's bars printed, and
  `--rejudge` for the spot check. If Sonnet's tool-call habit is fixed, a newer Sonnet, or a turn
  that recovers from it differently, is the first thing worth measuring again.
