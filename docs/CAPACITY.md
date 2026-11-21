# Capacity

How many visitors one API task carries, what the assistant costs per visit, and the sizes and limits
recommended for the deploy. `docs/DEPLOY.md` holds the task definition and the settings;
this is the measured starting point.

Everything here was measured locally on 2026-11-13 with the load test (`make load`, see
[`scripts/load/README.md`](../scripts/load/README.md)). No paid call was made: the model was the
scripted stand-in, paced like the real one, and the costs come from runs already paid for.

## How it was measured

- **The production image** (`open-door:prod`) in a container limited with `--cpus` and `--memory`,
  one uvicorn process, the default database pool. It ran with `APP_ENV=test`, because production
  refuses the scripted model.
- **The scripted model at the realistic pace** (`SCRIPTED_DELAY_PROFILE=realistic`): the guard
  takes 1.06 seconds, the first text comes 1.36 seconds after a call starts, and text streams at
  330 characters a second. These are fitted from the timings of the full live run of 2026-11-12
  (see `app/ai/scripted.py`).
- **A throwaway Postgres** (pgvector, limited to 2 vCPU and 4 GB, about a small managed instance),
  fresh for each size, on a private Docker network.
- **Each visitor follows the guided tour** through the real HTTP routes: nine questions across four
  personas, a time-off request previewed and confirmed, an approval, the Approvals and directory
  pages, and the HR pages. Visitors start over 10 seconds and pause 2 to 5 seconds between steps,
  so a tour takes about 100 seconds and the visitors overlap almost completely. Each sends its own
  client address through the trusted proxy header, and the real sandbox start limits apply.
- **A $1,000 daily AI cap for the size runs,** so the cap never stops a run. One extra run kept the
  real caps ($1 a sandbox, $3 a day) to measure what they do.

"Visitors" below means visitors **at the same time**, each partway through a tour. That is a far
heavier load than a portfolio demo should ever see.

## Results

Times are milliseconds. "Started" is the time from sending a question to the stream's
`turn.started` event: everything the server does before the model is called (the admission checks,
the history read, the card check). "Turn" is the whole stream, which the model's pace dominates.

| Size | Visitors | Started p50 / p95 | Turn p50 / p95 | Slowest page read (p95) | Sandbox start p95 | API CPU peak (of limit) | API memory peak | App DB connections peak |
|---|---|---|---|---|---|---|---|---|
| 0.5 vCPU, 1 GB | 10 | 23 / 40 | 4,476 / 5,677 | 122 (Approvals, waiting) | 237 | 62% | 126 MB | 4 |
| 0.5 vCPU, 1 GB | 25 | 21 / 62 | 4,448 / 5,659 | 98 (Approvals, waiting) | 196 | 76% | 137 MB | 7 |
| 0.5 vCPU, 1 GB | 50 | 23 / 371 | 4,556 / 5,646 | 181 (time-off summary) | 542 | **101%** | 142 MB | 11 |
| 1 vCPU, 2 GB | 10 | 23 / 43 | 4,464 / 5,672 | 54 (Approvals, waiting) | 117 | 36% | 133 MB | 4 |
| 1 vCPU, 2 GB | 25 | 20 / 40 | 4,402 / 5,608 | 33 (confirm) | 107 | 42% | 128 MB | 5 |
| 1 vCPU, 2 GB | 50 | 20 / 38 | 4,381 / 5,603 | 36 (Approvals, waiting) | 103 | 58% | 135 MB | 7 |

Every one of these runs completed every tour with no error: no 5xx, no refused turn, no pool wait,
no traceback in the API's log, and every stream ended with exactly one closing event. The time to
the first word was 3.9 to 4.0 seconds at the median in every run (the guard, then the model's first
text; a tool call adds a second model call before the answer).

**Where a task saturates.** At 0.5 vCPU, 50 visitors put the API's CPU at its limit for three
samples in a row, and the time to `turn.started` grew from 62 to 371 ms at p95, with sandbox starts
and page reads slowing too. Nothing failed, but that is the edge. At 1 vCPU, 50 visitors used 58% at
peak and every page read stayed under 40 ms at p95. Memory never passed 142 MB, and the database
login never held more than 11 of its 15 connections.

**Under the 512 MiB limit (Phase 9a, 2026-11-20).** The same load test at 0.5 vCPU with the hard
limit the deploy uses (`make load LOAD_ARGS="--sizes 0.5:512m --visitors 10 --no-real-caps-run"`):
all 10 tours completed with no non-2xx answer, turn p50 / p95 4,457 / 5,646 ms, `turn.started`
p95 53 ms, API CPU at most 61% of its limit, and the API's memory peak 135 MB (mean 124 MB). The
scripted live check (`make live-check DRY_RUN=1`) peaked at 123 MiB under the same limit.

**The long conversation.** The tour's conversations are at most three questions, so one extra run
(0.5 vCPU, 25 tour visitors repeating their tours for 7.7 minutes) added one visitor asking
alternately about sick days and booking a Friday off, in one conversation, never confirming, so its
history and its cards grew every turn. The conversation reached the history limit (80,000 tokens)
at question 48, which the API refused with `history-too-long` as designed. The time to
`turn.started` grew from 23 ms (median of questions 2 to 11) to 46 ms (median of questions 38 to
47), and the conversation's `GET /assistant/conversations/current` stayed at 70 ms p95. The
repeated run (after the fix below) gave 31 ms and 39 ms, with one question at 254 ms while the
API's CPU was at its limit. A conversation can't get longer than that, so the history read and the
card check cost a few tens of milliseconds at most, not hundreds.

**What the test found: idle connections closed too soon.** The long run's 125 tours made about
8,000 requests, and 3 of them failed in the client with the connection closed before any answer
(`RemoteProtocolError`). uvicorn closes an idle keep-alive connection after 5 seconds by default,
and the tour pauses 2 to 5 seconds between steps, so now and then a request went out on a
connection just as uvicorn closed it. A small local test reproduced it (1 failure in 120 requests
sent right at a 1-second keep-alive; none at 130 seconds). Behind a load balancer the same race
turns into 502s, because the load balancer keeps its connections to a task open for its idle
timeout, far longer than 5 seconds. AWS's rule is that the target's keep-alive must outlast the
load balancer's idle timeout. The image now runs uvicorn with `--timeout-keep-alive 130`, and the
repeated long run made all 7,750 of its requests with no error of any kind.

## The performance items the spec named

None of them matters at these loads, so none was changed. Each is in
[`BACKLOG.md`](BACKLOG.md) with these numbers.

| Item | What it's read from | Measured | Verdict |
|---|---|---|---|
| Reading a conversation's history once per request | Time to `turn.started`; `conversations/current`; `GET /assistant/budget` | Started 23 ms, rising to 46 ms by the 47th question; `current` 70 ms p95 at the longest; budget 37 ms p95 | Doesn't matter |
| The per-turn card check | Time to `turn.started` by question number | The same growth, with a card added every other turn | Doesn't matter |
| The directory's counts | `GET /people/facets` | 16 ms p95 at 0.5 vCPU, 25 visitors; below `GET /people` itself | Doesn't matter |
| The Approvals reads, one person at a time | `GET /time-off/requests?scope=waiting` | 98 ms p95 at 0.5 vCPU, 25 visitors; 36 ms at 1 vCPU, 50 visitors | Doesn't matter |
| Re-parsing a streaming answer on every word | The API's CPU per turn; the browser's work | The API side is cheap (58% of 1 vCPU at 50 visitors). The browser's re-parsing can't be measured by a server load test | Not measured in the browser; stays in the backlog with that note |

The bars were 500 ms at p95 for a page read and 300 ms added to the time to `turn.started`, at 25
visitors on the recommended size, or being what saturates a task first.

## Recommendations

**One task, 256 MiB reserved and 512 MiB hard, no CPU reservation** (Phase 9a, for the shared
portfolio server, ADR 0023). Memory needs are small (142 MB at peak). The earlier runs of 50
visitors at once on 1 vCPU, and 25 on 0.5 vCPU, show what a dedicated CPU carries; on the shared
instance the task takes the CPU it needs and the other apps' idle time covers it.

**One uvicorn process per task.** The CPU, not the process, was the limit at 0.5 vCPU, and one
process at 1 vCPU had half its CPU spare at 50 visitors. A second process would double the
database connections and the memory for no measured gain.

**The default database pool (5, plus 10 overflow).** The most connections in use at once was 11,
at the saturated size; at 1 vCPU it was 7. One task holds at most 15, well inside the shared
Postgres server's limit. A turn does not hold a connection while the model streams: at most 5
connections were ever idle inside a transaction, while far more turns were in flight.

**One task,** not two: the shared server is one instance, so a second task would add no
availability, and one task carries everything measured here. A deploy updates it rolling, with a
minimum of 100% and a maximum of 200% healthy.

**The load balancer's idle timeout: 120 seconds, below the image's keep-alive of 130.** Streams send
a keep-alive comment every 15 seconds, so 120 is plenty for them. If the deploy ever needs a longer
idle timeout, raise `--timeout-keep-alive` in `scripts/image/entrypoint.sh` above it first.

**The AI limits.** The costs, from the runs already paid for (Opus 5.5 answering, Haiku 5.5
guarding):

| What | Cost |
|---|---|
| One question, guard included (the 2026-11-12 full run, 621 traces) | $0.019 mean, $0.036 at p95 |
| A question that answers without a tool / with a search / with a card | $0.008 / $0.023 / $0.014 |
| The guard alone, per question | $0.0002 |
| One case summary, when a visitor sends a case to HR (the 2026-10-30 run) | $0.012 |
| One guided tour (nine questions) | about $0.16 to $0.18 |
| A typical visit (three to five questions) | about $0.06 to $0.10 |

- **Per sandbox: $0.50** (production's value; the code default stays $1.00). That is one full tour
  plus several follow-up questions, because each question needs about $0.21 of room before it
  starts (the guard's reservation plus the first model call's, `app/ai/admission.py`
  `room_needed_usd`, used by the stream route in `app/ai/turn.py`). It stops one visitor from using
  the day's budget alone.
- **Per month and per day: a paced $20 month** (Phase 9a, ADR 0011). The monthly budget is the
  limit; each day may spend the larger of a multiple (3x) of an even share of what is left and a
  $1.00 floor, never more than what is left. At about $0.17 a tour, $20 buys about 115 tours. A
  30-day month's even share is about $0.67 a day, a busy day can use up to $2.00, and the $1.00
  floor lets about four first questions start at once ($0.21 each). Unspent days raise the later
  days' share. `AI_DAILY_BUDGET_USD` is set equal to the month in production, so pacing alone
  governs.
  - The ledger reserves the most a call could cost before making it (about $0.16 to $0.30 for an
    answer, at the full output limit) and settles to the real cost afterward, so a day's room must
    cover the reservations of the questions running at that moment as well as the real spend. With
    25 visitors at once and no real spend at all, 7 of an earlier run's 225 questions were refused
    with `budget-daily` from reservations alone.
  - When the month or the day has no room for a first question, the landing offers the recorded
    walkthrough instead of the tour (`GET /api/v1/assistant/availability`).
- **Sandbox starts: 15 an hour and 50 a day per address, and 1,000 a day in all** (Phase 9a,
  raised from 5, 20, and 500). The per-address numbers are sized for a hiring team behind one
  office address, where several people try the demo in the same hour. The AI budget, not the start
  limit, is what ends a busy day: the assistant stops answering long before 1,000 sandboxes have
  started. Size on disk, measured on 2026-11-19 after compacting the
  development database (`VACUUM FULL`), with 278 seeded sandboxes: about 353 kB a sandbox, so 1,000
  sandboxes come to about 350 MB, under 2% of the 20 GB data volume. Sandboxes deleted every day
  leave dead rows, which autovacuum makes reusable but does not return to the disk, so the volume
  should hold the peak (about 1,000 sandboxes alive at once) plus headroom. Every start
  seeds 145 people (about 100 ms at p95 at 1 vCPU), which the run measured as cheap.

## Caveats

- **Local Postgres isn't the managed one.** The database ran in a container on the same machine,
  with no network between it and the API and no TLS. A managed instance adds a millisecond or so to
  each query; the times here are lower bounds for the reads.
- **The scripted model skips the Anthropic SDK.** Its pace matches the real model's, but the real
  transport also parses the SDK's stream and holds a TLS connection per call. That CPU isn't in
  these numbers, so leave the 1 vCPU's headroom in place.
- **The image ran with `APP_ENV=test`,** because production refuses the scripted model. The
  differences are the transport and the test Turnstile keys; the middleware, the headers, and the
  limits were production's.
- **The load came from one machine,** through Docker's network, so the client and the server
  shared the CPU. The API's container limits kept its share fixed.
- **Real visitors pause longer.** The tour paused 2 to 5 seconds between steps, and a person
  reading an answer takes longer, so the same visitors at once would load a task less than this.
