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

## Documentation

| Document | What it covers |
|---|---|
| [Roadmap](docs/ROADMAP.md) | The living plan and the status of every phase |
| [Design spec](docs/specs/2026-09-29-open-door-design.md) | The product and system design, with the reasoning behind each decision |
| [What this is not](docs/WHAT-THIS-IS-NOT.md) | Scope limits, what the assistant will never do, and what the evidence does not prove |
| [Decision records](docs/adr/README.md) | The big architecture decisions and what was rejected |
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
