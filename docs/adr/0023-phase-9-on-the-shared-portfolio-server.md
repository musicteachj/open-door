# 0023. Phase 9 deploys to the shared portfolio server, and prompt 2026-11.5 ships without a full eval run

Status: Accepted · Date: 2026-11-20

Open Door deploys to one shared portfolio AWS server, not to its own cluster. This record holds the
deployment decisions and, from Phase 9a Task 7, the waiver of the full eval run for prompt 2026-11.5.
The settings and task definitions that follow from it are in [`docs/DEPLOY.md`](../DEPLOY.md).

## Context

The portfolio's apps run on one EC2 instance in us-east-1, as ECS tasks in bridge mode behind one
shared load balancer, with a shared Postgres server on the instance. Open Door is a demo with
fictional data deleted within a day, and its owner wants it cheap and launched without paid runs
("no expensive paid runs", 2026-11-18).

Prompt 2026-11.5 fixes a bug found while recording the walkthrough: after a manager approved a
request, the asker was told it still waited for approval. The change touches what the model reads
(the system prompt and the "Since the last message" line), so the project's rule is a full live eval
run before its pull request (`CLAUDE.md`, "AI development rules"), about $10 to $15. Without a full
run, the committed recordings are 2026-11.4's, every offline replay request would miss, and CI would
stay red.

## Decision

Each decision names what it replaces.

- **ECS on one EC2 instance in bridge mode, not Fargate.** One image runs as three task
  definitions: the API service, the setup (before each deploy), and the cleanup (hourly).
- **One API task at 256 MiB reserved and 512 MiB hard, not two at 1 vCPU and 2 GB.** The measured
  peak was 142 MB, and one instance gives no availability a second task would add.
- **Postgres 17 with pgvector as an ECS service on the instance, not a managed database,** with the
  role layout of Phase 9a Task 9: an init superuser, a non-superuser owner with `CREATEROLE`, the
  roles `od_app` and `od_cleanup`, and `CONNECT` revoked from `PUBLIC`. No TLS (the traffic stays on
  the instance's Docker bridge) and no pooler.
- **SSM Parameter Store SecureStrings under `/portfolio/open-door/`, not Secrets Manager.**
- **The local key provider, with its keyring from SSM, not KMS** (ADR 0015's amendment). A key in
  task memory is accepted for fictional data deleted within a day.
- **No per-task egress limit,** because bridge mode can't set one; the instance blocks the metadata
  service (ADR 0022's amendment).
- **The load balancer checks liveness (`/api/v1/health/live`), not readiness.** The trade-off: a
  database outage does not take the one task out of rotation, so visitors see the API's own errors
  instead of a load balancer 503, and a brief database restart does not get the only task restarted
  or dropped. The deploy's smoke tests check readiness once.
- **A paced monthly AI budget ($20) and $0.50 a sandbox** (ADR 0011's amendment), with a switch that
  turns live AI off and a public availability flag that makes the landing offer the walkthrough.
- **One entrypoint per job:** `/app/entrypoint.sh` serves and refuses any argument, `/app/setup.sh`
  migrates, creates the logins, and loads the handbook, and `/app/cleanup.sh` runs the cleanup. ECS's
  RunTask can't override an entrypoint, so each job is its own task definition.
- **The full eval run for prompt 2026-11.5 is waived for launch** (James, 2026-11-18). The
  walkthrough is recorded again after the deploy, and steps 5 and 6 are the check on the fix.
- **CI replays under the recorded prompt until then.** The offline replay of the smoke, full, and
  effort sets uses an archived copy of the 2026-11.4 prompt as the system prompt, checked against
  its golden hash and named by a pin in the fixtures folder. It tests the plumbing and the graders,
  not the new prompt. The next full `FRESH=1 PRUNE=1` run records 2026-11.5 and deletes the pin; a
  pin that names the current prompt is refused.
- **The published scoreboard stays 2026-11.4's** and is labeled so in `docs/AI-GOVERNANCE.md`.

## Rejected alternatives

- **Fargate:** about $130 a month against about $72 for the shared instance's share.
- **RDS or another managed Postgres:** the cost, for fictional data.
- **Secrets Manager:** a per-secret monthly fee, where SSM SecureStrings are free.
- **Building the KMS provider:** work and cost for data deleted within a day.
- **Re-record the fixtures with the full run now:** the paid run is what the owner declined.
- **Re-record the fixtures with a smoke run:** it re-records only the smoke items, so CI would stay
  red for the rest of the set, and it would still be a paid run.
- **Skip the offline replay in CI until a full run:** the plumbing and the graders would go
  unchecked for as long as the waiver lasts.

## Consequences

- Prompt 2026-11.5's answers are unmeasured by the eval set until the full run after the deploy.
- The pin is temporary: deleting `recorded-under.json` and the archived prompt is part of the same
  change as the next full run's recordings (`docs/BACKLOG.md`).
- A task can reach any host, and the keyring is in its environment. Both are accepted
  (`docs/THREAT-MODEL.md`).
- Open Door shares the server's one Postgres: a superuser login of another app could read it.

Amended 2026-11-24 (Phase 9b, the deploy files): the SSM prefix is `/portfolio/opendoor/`, the
portfolio's slug, not `/portfolio/open-door/`. `AI_MONTHLY_BUDGET_USD` moved into SSM as a String
parameter, read through the task definition's `secrets`, so the off switch is to set it to `0` and
force a new deployment of the service, with no commit. [`docs/DEPLOY.md`](../DEPLOY.md) has the
current settings.
