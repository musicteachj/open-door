# The load test (`make load`)

A free, local test of how many visitors one API task can carry. It uses the production image
(`open-door:prod`) with the scripted model, paced like the real one, so no paid call is made.

## What it does

For each container size (default 0.5 vCPU / 1 GB, then 1 vCPU / 2 GB) and each visitor count
(default 10, 25, 50), smallest first, it:

1. starts a fresh throwaway Postgres on a private Docker network (never published to the host,
   never the development database; 2 vCPU, 4 GB) and runs the deploy's setup on it (migrations,
   the login users, the handbook), so no run sees what an earlier one left;
2. starts the API container (`--cpus`, `--memory`, `APP_ENV=test`, the scripted model with
   `SCRIPTED_DELAY_PROFILE=realistic`, the real sandbox start limits of 5 an hour, 20 a day, and
   500 a day in all, and $1,000 AI caps a sandbox and a day, so neither ends a run) and starts that
   many visitors over 10 seconds.

After the matrix, one more run (25 visitors, 1 vCPU / 2 GB, a fresh database) uses the real AI
caps ($1 a sandbox, $3 a day). The scripted model is priced at $0, so the caps can only refuse a
question because of the reservations of the questions in flight at that moment (each call reserves
at the real model's rates, then settles to $0), never because a sandbox or the day ran out of
spend. Its 429s and budget errors are expected and reported.

Each visitor follows the guided tour through the real HTTP routes: Priya starts a sandbox, asks
about sick days, books next Friday off (one preview check, then a confirm after the stream closes),
Mateo asks the same, Marcus opens Approvals and the directory, asks what waits, approves, and asks
about Leo, Priya tries the rules (an address, an injection, a sensitive message), and Dana opens
cases and the console. Every visitor sends its own `X-Forwarded-For` from the benchmarking range
198.18.0.0/15; the launcher finds its own address as the API sees it and trusts only that one,
the way a load balancer would be trusted.

## Running it

```
make load                                                       # the whole matrix, about 35 minutes
make load LOAD_ARGS="--sizes 1:2g --visitors 3 --no-real-caps-run --out /tmp/od-p8/s7/smoke"
make load SKIP_BUILD=1 LOAD_ARGS="--sizes 1:2g --visitors 10"   # reuse the built image
```

Needs Docker running; it does not need `make db`, a key, or a network beyond pulling images. Run
it under `caffeinate -i` and detached for the full matrix. Options (`drive.py --help`): `--sizes`,
`--visitors`, `--real-caps-run` / `--no-real-caps-run`, `--out`, `--seed`, `--port` (default 8400),
`--reading-seconds`, `--ramp-seconds`, `--long-conversation N`.

**The long conversation.** The tour's conversations are at most three questions long, so it can't
show what grows with a conversation: the history read before each turn and the per-turn card check.
`--long-conversation 50` adds one visitor who asks 50 questions in one conversation, alternating
the sick-days question and the Friday booking without confirming, so its history and its cards grow
every turn. Meanwhile each tour visitor starts a new tour (a new sandbox and address) until that
conversation ends, so the load lasts as long as it does. A slot whose tour fails stops. Since the
tours repeat for as long as the conversation lasts, a long-conversation run lifts the day's
500-start total (each tour still has its own address and the per-address limits). Its numbers go
in the report's
`longConversation` section, turn by turn, apart from the tour's, and the report's name ends in
`-long50`.

```
make load SKIP_BUILD=1 LOAD_ARGS="--sizes 0.5:1g --visitors 25 --no-real-caps-run --long-conversation 50 --out /tmp/od-p8/s7/load-long"
```

Ctrl-C (or a kill) removes every container and the network it started.

## What it measures

One JSON report per run, named like `1cpu-2g-25v.json` (`-realcaps` for the extra run), and one
`LOAD RUN END` summary line per run on stdout. A report holds:

- p50, p95, max, and count of: sandbox creation; the time from the question to `turn.started`; the
  time to the first `text.delta`; the whole turn; and every other request by method and route
  (the `scope` of the time-off list stays in the name);
- the time to `turn.started` by the question's position in its conversation (1st, 2nd, 3rd);
- HTTP statuses and error codes (problem types and stream `error` codes) with counts, plus notes
  such as a card that never came;
- every 2 seconds: the API's and the database's CPU (also as a fraction of the container's limit)
  and memory, and the app login's connections by state, as max and mean;
- pool or timeout lines in the API's log (`QueuePool limit`, `TimeoutError`, `database-busy`,
  `Traceback`);
- the wall time, the tours begun and how many completed (a tour that never got a sandbox, or
  crashed, failed), and whether the run saturated: the API's CPU at 95 percent of its limit for
  three samples in a row, or the turn's p95 more than 50 percent above the same size's smallest
  run (each size runs its counts smallest first), or any 5xx, pool timeout, request that got no
  answer or was cut partway, or failed tour. A cut stream is counted as a client error, not as a
  finished turn.

## What it costs

Nothing. The scripted model makes no call. It is not part of `make check` or CI.

## Caveats

The database is a local Postgres, not a managed one. The scripted model skips the Anthropic SDK's
streaming and TLS. The image runs with `APP_ENV=test` (production refuses the scripted model).
The web app does not poll the budget route on a timer, so neither does the visitor: it reads it
when a person has no conversation yet, as the web app does.
