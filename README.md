# Open Door

**Your open-door policy, now always open.**

Open Door is an AI-first HR help desk. Employees, managers, and HR ask questions in plain language
and get answers that cite the company handbook. The assistant proposes actions like booking time
off, and nothing changes until a person confirms. Sensitive topics go to a human, never to the
model.

> **Status:** planning is complete and the build has not started. See the roadmap for the phase
> status.

## The rules the assistant never breaks

1. The model never decides who can see what. Permissions are enforced in code and in the database.
2. The model never calculates balances or durations. A tested engine does.
3. The model never writes. It proposes, and a person confirms.
4. Every policy claim cites the handbook, or the assistant says it could not find one.
5. The model never makes or recommends employment decisions.
6. Sensitive topics go to humans.
7. Every AI action is audited, and the assistant always says it is an AI.

## How we know it works

The assistant is scored against fixed question sets, and every figure below is generated from the
committed run boards in `evals/scoreboards/` (run `make scoreboard`, and don't edit it by hand).

<!-- scoreboard:start -->
Assistant `claude-opus-5-5`, safety check `claude-haiku-5-5`, judge `claude-sonnet-5-5`.

Three trials per set unless noted.

| Set | Result | Lowest trial | Other figures |
|---|---|---|---|
| Retrieval (Handbook 2026.11.3) | **100%** Hit rate at 5 | No trials: retrieval is exact. | Every negative passed. |
| Policy Q&A (Full run, Nov 12, 2026) | **99%** Program checks | 99% | Unanswerable 97%, lowest 90% |
| Answer quality (Nov 12, 2026) | **80%** Judge pass rate | 76% | Target 85%<br>11.7 uncited claims<br>Judge agreement with the hand grades 91.2% |
| Red team (Nov 12, 2026) | **100%** In every trial | 100% | All six groups at 100%: actions, cases, injection, private details, prompt extraction, routing. |
| Actions (Nov 12, 2026) | **100%** Pass rate | 100% | Numbers match the engine 100% |
| Fairness (Nov 12, 2026) | **12 of 12** Groups consistent | Groups are judged across all trials. | No identity assumption in any trial<br>Judge equivalence 87% (lowest trial 82%)<br>Groups consistent by attribute: name 100%, parent 100%, religion 100%, age 100%, origin 100%, spouse 100%. |
| Escalation (Oct 27, 2026) | **100%** Crisis recall | 100% | Sensitive recall 100%<br>Ordinary questions offered no case 100% |
| Case summary (Oct 30, 2026) | **22 of 22** Passed every check | 22 of 22 | By the judge: 22 of 22 |

### History of full runs

| Date | Model | Q&A | Unanswerable | Red team | Actions | Judge | Cost |
|---|---|---|---|---|---|---|---|
| Oct 19, 2026, 15:22 UTC | `claude-opus-5-5` | 100% | 100% | 100% | - | 74% | $8.02 |
| Oct 25, 2026, 16:04 UTC | `claude-opus-5-5` | 100% | 100% | 97% | 96% | 72% | $10.39 |
| Oct 29, 2026, 14:23 UTC | `claude-opus-5-5` | 97% | 93% | 100% | 99% | 68% | $10.93 |
| Nov 3, 2026, 14:00 UTC | `claude-opus-5-5` | 99% | 97% | 100% | 100% | 73% | $15.20 |
| Nov 3, 2026, 18:45 UTC | `claude-sonnet-5-5` | 98% | 100% | 99% | 97% | 83% | $9.44 |
| Nov 12, 2026, 22:36 UTC | `claude-opus-5-5` | 99% | 97% | 100% | 100% | 80% | $15.73 |

Actions joined the full set on Oct 25, 2026.

These figures come from recorded eval runs. CI replays the recordings on every change, so it checks the app's handling, not the model.

The sets are small (207 items in the full set), so a single item can move a figure by more than a point.
<!-- scoreboard:end -->

## Documentation

| Document | What it covers |
|---|---|
| [Roadmap](docs/ROADMAP.md) | The living plan and the status of every phase |
| [Design spec](docs/specs/2026-09-29-open-door-design.md) | The product and system design, with the reasoning behind each decision |
| [What this is not](docs/WHAT-THIS-IS-NOT.md) | Scope limits, what the assistant will never do, and what the evidence does not prove |
| [Decision records](docs/adr/README.md) | The big architecture decisions and what was rejected |
| [Data inventory](docs/DATA-INVENTORY.md) | Every piece of data stored, why, who can see it, and how long it's kept |
| [Threat model](docs/THREAT-MODEL.md) | What is protected, who might attack, and the control and test behind each threat |
| [Design handoff](docs/design/README.md) | How designs from Claude Design become screens |
| [Initial plan](docs/plans/2026-09-29-open-door-initial-plan.md) | The frozen record of the original planning decisions |
| [Project rules](CLAUDE.md) | How work is done in this repository |
| [Changelog](CHANGELOG.md) | Every notable change |

## Stack

React 19, TypeScript, Vite, Tailwind CSS v4, and shadcn/ui on the frontend. FastAPI, SQLAlchemy 2,
and Postgres with pgvector on the backend. Claude through the Anthropic SDK for the assistant, and
Voyage AI for handbook embeddings.

## Run it locally

You need Node 24, [uv](https://docs.astral.sh/uv/), and Docker Desktop.

```
make setup   # install dependencies and create apps/api/.env
make dev     # start Postgres, migrate, and run the API (:8000) and web app (:5173)
make check   # run everything CI runs
```

`make` on its own lists every command.

---

Open Door's company, people, and handbook are fictional. Nothing here is legal advice.
