# 0021. Starting a sandbox needs a Turnstile check and is limited per address and per day

Status: Accepted · Date: 2026-11-05

## Context

`POST /api/v1/sandboxes` needs no session (it creates one), and each call seeds a company of 145
people with their time off, holidays, and cases. Anyone who can reach the demo can call it in a
loop, filling the database and starting sandboxes whose AI budgets add up. The design spec planned
"a per-IP limit and Cloudflare Turnstile on sandbox creation". The API will run as several tasks
behind a load balancer, so a limit kept in one process's memory wouldn't hold.

## Decision

- **Cloudflare Turnstile, managed mode,** run only when a visitor starts a sandbox, so most
  visitors never see it. The API verifies each token once with Cloudflare (hostname and action
  checked) and fails closed: a failed check is refused, and so is a check that can't reach
  Cloudflare.
- **Limits counted in Postgres,** shared by every task: at most 5 starts an hour and 20 a day from
  one address, and 500 a day in all, each a setting the load test tunes. The check and the insert
  run under one advisory lock, as the AI budget's do (ADR 0011).
- **The address is never stored.** Each start stores an HMAC-SHA256 of it under a secret key, and
  an IPv6 address is reduced to its /64 prefix first, so one connection can't rotate through
  addresses. The rows are deleted after a day by the cleanup job.
- **The address comes from the load balancer only:** uvicorn trusts `X-Forwarded-For` from the
  load balancer's subnets and from nowhere else.
- **Refusals are 429s with `Retry-After`,** worded for a person (the owner approves the texts in the Phase 8 spec).

## Rejected alternatives

- **A limit in each process's memory:** wrong as soon as there are two tasks, and reset by every
  deploy.
- **AWS WAF rate rules:** a standing charge and a rule set outside the repository, and it can't tell
  a sandbox start from any other request without path rules. Phase 9 may add WAF in front anyway.
- **Turnstile's invisible mode:** it requires the site's privacy notice to reference Cloudflare's
  Turnstile privacy addendum, and managed mode already shows nothing to most visitors.
- **Storing addresses in plain text:** a person's IP address is personal data, and a keyed hash
  answers "has this address started too many?" without keeping it.
- **Failing open when Cloudflare is down:** the limits would still hold, but the check would vanish
  exactly when someone could arrange for it to.

## Consequences

- Cloudflare becomes a third outside service: it receives the visitor's address and browser
  signals when a sandbox starts. DATA-INVENTORY and the landing say so.
- The CSP allows Cloudflare's challenge host for scripts and frames (ADR 0020).
- Development, CI, the browser tests, and the load test use Cloudflare's documented test keys;
  production refuses them unless its origin is a loopback one (the local production run).
- A Cloudflare outage stops new sandboxes, not existing ones.
