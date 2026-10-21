# Backlog

Findings from reviews that were deliberately deferred, each with the reason and the phase that
should pick it up. When one is done, delete it here and record it in the changelog.

## Any phase

- **Some web unit tests are timing-flaky under full-suite load:** the directory page's "footer when
  an update has failed" and a few handbook-page searches time out now and then when the whole
  Vitest suite runs, on a clean `dev` too, and pass alone. Raise their waits or find the slow
  path. (Phase 4 stage 6.)

- **Small conversation-page glitches the v0.4.0 release review left alone.** When a
  remembered conversation turns out to be gone (a 404 on send), the page drops to "Loading…" while
  it reloads, and the composer loses focus. And "Start a new conversation" with a source panel open
  replaces the panel's history entry, leaving a Back step that changes nothing. The release review
  tried fixes for both, and each brought new edge cases (a stale Forward step, a conversation id
  missed on a send that created it), so they were reverted. Also: "Start a new conversation"
  clicked after a send has already begun still lets that send go to the old conversation, and a
  second Enter while a send waits for the new conversation is dropped without a word. Fix them with
  the page's next real change, with browser tests. (v0.4.0 release review.)
- **Tie the gallery's fixed texts and the running lines to the API's.** The conversation gallery
  keeps word-for-word copies of the owner-approved fixed texts (crisis, "can't answer right now",
  both budget texts, "still answering", the personal-data warning), and the chat store merges a
  tool's "Searching the handbook…" step only when the API's status text matches the web's running
  line exactly. Nothing fails if either side is reworded. Share the texts the way the
  personal-data cases are shared (one file both sides read), or add a check. (v0.4.0 release
  review.)
- **Locally, the browser tests can reuse a stale server.** `playwright.config.ts` sets
  `reuseExistingServer` off CI, so a preview already on 4173, or an older API on 8100, is tested
  without a rebuild, and `make check` can pass or fail against old code. CI always starts fresh
  servers. Stop old servers before `make e2e`, or run with `CI=1`. (Phase 2 close-out review.)
- **Local development in Safari-family browsers.** WebKit drops every `Secure` cookie on
  `http://localhost`, so the `__Host-` session cookies never stick and sign-in ends at "This
  sandbox has reset." Chromium and Firefox keep them: the session round trip passed in both. Every
  deployed origin is HTTPS, so this is a note for local development, not a defect. Develop and run
  the browser tests in Chromium or Firefox. (Phase 2 stage 2b, checked in WebKit.)
- **Decide whether loading skeletons animate.** The design draws them static, with no shimmer or
  pulse, and the build matches (the skeleton and skeleton-row tests assert it). The owner noticed
  the stillness in the Stage 4a gallery review and may want motion. That's a design change first,
  in Claude Design, then the build. Any animation must stop under `prefers-reduced-motion`, which
  `base.css` already handles. (Phase 2 stage 4a gallery review.)
- **Don't run Alembic inside an async test.** `env.py` calls `asyncio.run`, which fails inside a
  running event loop, and `fileConfig` resets the root log handlers. Test setup should run
  `alembic upgrade head` as a subprocess, or from a synchronous session fixture. Phase 1's tests
  never needed to, because CI runs the migration round trip as plain commands, but a later test
  that runs migrations will.

- **Stop a person from managing themselves, directly or in a loop.** `people.manager_id` has no
  `CHECK (manager_id <> id)` and nothing prevents a reporting loop. Phase 1 is safe: the API can't
  update people, the seed has no loops, and `load_actor` drops the actor from their own reports.
  Whichever phase first grants `UPDATE` on `people` must add the check, and refuse an update that
  would create a loop. Otherwise approval rules could let someone approve their own request.
  (Stage 3 security review.)

- **Check `Origin` on any WebSocket endpoint.** The same-origin middleware passes WebSocket
  connections through untouched, because none exist. Whichever phase adds one must refuse a
  cross-site `Origin` on the handshake, against cross-site WebSocket hijacking. (Stage 3 security
  review.)

- **Guard writes to private details as well as reads.** The database rule that limits
  `person_private` to the person and HR covers `SELECT` only, because the API can't yet update or
  delete those rows. Whichever phase first grants `UPDATE` or `DELETE` on `person_private` must
  add restrictive policies for them in the same migration. (Stage 1 security review.)

- **Keep the directory cursor and the facet counts from naming a hidden person.** The next cursor is
  the sort key of the last row read, so paging continues past cards the policy layer hides. The
  directory's facet counts (Phase 2) skip the per-card check altogether. Every card is visible in
  Phase 1, so it reveals nothing. Whichever phase first makes the `directory.read` rule refuse
  anyone must encrypt the cursor, or move the filter into the query, and count only the cards it
  shows. Taking the cursor from the last card returned instead is wrong: a page whose rows are all
  hidden would end the directory early. (Stage 4 security review.)

- **Make the HR flag part of the tenant context, and reapply it after a persona switch.**
  `app.is_hr` isn't in `TenantContext`: the transaction hook clears it, and only `signed_in` turns
  it back on. A persona switch also keeps the old persona's `app.person_id` and `app.is_hr` for
  the rest of its request. Neither matters today, since nothing after the switch reads
  `person_private`, and no other tenant session acts for HR. The security reviewer proved the
  switch returns the right `/me` both ways. Whichever phase first reads private details outside
  `signed_in`, or after `rotate_session`, must fold `is_hr` into `TenantContext` and reapply the
  context for the new actor. (Phase 1 close-out review.)
- **`route_path` copies a private Starlette helper.** `app/core/api_paths.py` repeats
  `starlette._utils.get_route_path`, so the no-store and same-origin rules match the path the
  router routes. On a Starlette upgrade, check that the two still agree. (Phase 1 close-out
  review.)
- **Search rebuilds passage text on its own.** `passage_texts` in the handbook search module
  repeats `Passage.text` from the handbook domain over the stored JSON. They agree today; if one
  changes how a list item reads, the excerpt and the hit's passages drift from the indexed chunk
  text. Build both from one helper. (Phase 3 close-out review.)
- **The profile page sends its URL's person ID unencoded.** `/directory/..%2Fme` asks
  `/api/v1/people/../me`, which the URL parser resolves to `/api/v1/me`, and `/directory/facets`
  asks the facets route; either way the page renders the wrong response. It's the session's own data, so nothing leaks, but the page breaks. Encode the
  ID and refuse "." and ".." as the handbook hooks now do, ideally in one shared helper for every
  ID taken from a URL. (Phase 3 close-out review, in Phase 2 code.)
- **The directory's filters can lose a search typed just before them.** Picking a location,
  department, or "My team" within 250 ms of typing pushes an entry without the search, so Back
  loses it. The handbook's Show filter had the same bug; it now writes the pending search first
  (`flushSearch`), and the directory's filters should do the same. (Phase 3 close-out review, in
  Phase 2 code.)
- **The error page doesn't retry a cached error after navigating away and back.** A query that
  throws to the route's error page doesn't retry its cached error on mount, and the page resets
  only from its Retry button. Coming back within the cache time shows the error again with no new
  request. Resetting on navigation would fix it for every page, and let the handbook's overview
  use one cache entry. (Phase 3 close-out review, in Phase 2 code.)
- **Two small copies to fold together.** The passage panel works out a section's number with its
  own pattern instead of `sectionNumber()` from the handbook labels, and `formatMonthDay` repeats
  `formatShortDate`'s date parsing. (v0.3.0 release review.)
- **State names live in two places.** The API's applicability code and the web's handbook labels
  each keep a state-code-to-name table, so a new state needs both (Georgia did). Have the API send
  the names, and drop the web's copy. (Phase 3 close-out review.)

## Handbook content

- **A military leave section.** The handbook has none. A company section under the federal
  reemployment law for service members (USERRA) comes first; state addenda follow, such as
  Georgia's leave for state guard members (O.C.G.A. §38-2-279, not verified). (Phase 3 stage 6.)
- **A Georgia persona,** if the owner wants one: a fifth sign-in card for an Atlanta employee,
  with a design pass on the landing page first and a migration for the new persona key. Georgia is
  covered today by Atlanta employees in the directory and Georgia askers in the eval. (Phase 3
  stage 6.)

## Phase 5: time off

- **Show team coverage beside a manager's approval.** When Marcus reviews a request, show who else
  on his team is off on those dates. It's context only: the assistant never recommends approving
  or denying (invariant 5). (2026-10-06 design brainstorm.)
- **Check the nav after a switch from a manager to an employee.** `navFor` builds the nav from the
  fresh `/me` inside a remounted shell, but in Phase 2 everyone sees only Ask and Directory, so the
  manager's items disappearing after a switch can't be observed. When Approvals becomes available,
  add a `navFor` test and extend the shell's switch test to prove the employee never sees it.
  (Phase 2 stage 5 security re-check.)
- **Keep a write from the old identity out of the new cache.** `resetIdentity` clears the query
  cache, but a mutation already in flight still runs its callbacks when it finishes. If its
  `onSuccess` calls `setQueryData`, the old person's data lands in the new person's cache. Phase
  2's only writes start or end a session, so nothing does this yet. Write hooks should invalidate
  queries rather than set their data. Where one must set data, `resetIdentity` should count
  identities and the write should check the count first. (Phase 2 stage 2 security review.)
- **Seed last year's holidays too.** A sandbox stores the holiday calendar for its anchor year and
  the next. One created in early January therefore lacks the previous December's closures, so a
  question about leave taken over the holidays just before it would miss them. If the time-off
  engine answers past-dated questions, seed the prior year as well. (Stage 2 review.)
- **Never treat the anchor date as today.** `create_sandbox` sets `tenants.anchor_date` to
  today's date in UTC, not in any location's timezone. Every seeded location is in the US, so a
  sandbox created in the US evening is anchored to the location's tomorrow. Seed dates are only
  shifted by a day, which is harmless, but invariant 2 needs today's date in the location's
  timezone. The time-off engine must compute today from the location's `timezone`, never from
  `anchor_date`. A test should create a sandbox at, say, 03:00 UTC and check that a Pacific-time
  employee's "tomorrow" is the right date. The assistant's per-turn context already does this
  (Phase 4 stage 2). (`/code-review medium` on the `v0.1.0` release.) The engine's half is done:
  `today_at` in `app/domain/timeoff/today.py` (Phase 5 stage 1). The sandbox test at 03:00 UTC
  needs the service, in stage 2.

- **Record who confirms a proposal as an audit event of its own,** separate from the action it
  executes, so the log shows both who proposed and who decided.
- **Grant `UPDATE` only where requests and approvals need it.** Phase 1 grants the API no
  `UPDATE` anywhere, and the exact-grants test fails on any grant it doesn't expect.

Source for both: [the Phase 1 spec](specs/2026-10-03-phase-1-tenancy-identity-permissions.md#later-phases).

- **Make the scroll-restoration exception general.** `use-scroll-restoration.ts` special-cases the
  source panel's `?source=` parameter (an import from the chat feature into the app shell), while
  the panel's navigations already pass `preventScrollReset`. Phase 5's first panel that lives in
  the URL (a confirm card, say) would jump to the top until another parameter is hard-coded. Mark
  such navigations in history state and honor that for push, replace, and back instead. (v0.4.0
  release review.)
- **Keep trial 1's recordings when a fresh run stops in a later trial.** With `FRESH=1` (and
  `PRUNE=1`), `evals/assistant/run.py` saves recordings only when every item ran and was judged in
  every trial, but only trial 1 is ever recorded. A run stopped by its cap, or a judge call with no
  room, in trial 2 or 3 throws away trial 1's complete, already paid recordings. Gate the save (and
  the prune) on trial 1 alone. The last full run used $8.02 of a $16 cap, so it hasn't bitten;
  Phase 5's new tools will need a full run, so fix it first. (Phase 4 phase review.)
- **Put the existing overlays and panels on the new tokens** (Stage 5). The bottom sheet's backdrop
  is `bg-ink/40`, darker than the design's `scrim` (0.32) that the confirm dialog will use; check
  the design and move it onto `bg-scrim` if they should match. The gallery's handbook and
  conversation sections size their docked panels with `w-[420px]` in four places; use `w-panel`.
  (Theme-token fix review, 2026-10-20.)

## Phase 6: cases and escalation

- **The hand-off says only what's true.** Before the person writes anything, say:
  - only HR sees it, never managers;
  - it's encrypted;
  - when to expect a reply;
  - the AI writes HR a neutral summary.

  Never say "the AI won't read it": the guard reads every message, and `summarize_case` is
  AI-written. (2026-10-06 design brainstorm.)
- **Encrypt case narratives.** They are the most sensitive text the app will hold.
  Source: [the Phase 1 spec](specs/2026-10-03-phase-1-tenancy-identity-permissions.md#later-phases).

- **Require a header no navigation can send on audited reads.** A read of `/api/` whose
  `Sec-Fetch-Site` says it came from another site is refused, so another site can't make an HR
  partner's browser perform an audited read. Two cases still pass: a browser too old to send the
  header (Safari before 16.4, for example), and a navigation the user starts themselves, which
  sends `none`. Before case reads are audited, require the `X-CSRF-Token` header on audited reads
  too, since no navigation can send it. Today an attacker would also need a person's ID. Seeded
  IDs are derived from the sandbox's random tenant ID, which is shown only inside that sandbox.
  (Stage 4 security review.)

## Phase 7: AI Ops console, reviewer experience, model decision

- **The audit log stores `None` as the JSON value `null`.** `AuditEvent.before` and `after` are
  nullable `jsonb` columns without `none_as_null=True`, so an event with no before or after state
  holds JSON `null`, not SQL `NULL`, and an `IS NULL` query misses it. The assistant tables were
  fixed in stage 1; the audit columns need the same type change and a data fix for existing rows.
  Phase 7's console is the first to query them. (Phase 4 stage 1 review.) Moved from Phase 4 at its close: the console is the first to query these columns.
- **Pass structured search results to the judge.** The eval judge reads each cited section's text
  back out of the flattened "source | title | passages" tool-result text. It holds for today's
  handbook (no title contains " | " and no passage starts a line with "/handbook/"), but keeping
  the source, title, and passages as fields on the trace would remove the round trip. (Phase 4
  stage 3 `/code-review medium`.) Moved from Phase 4 at its close: it belongs with the scoreboard generator.

- **Store why a turn was refused.** The Anthropic transport builds `Finished.stop_details` (the
  refusal's category and explanation) and documents it as information for the audit trail, but
  nothing stores it: a refused turn records only that it was refused. The console is the first to
  need the reason; store it on the turn (and in the data inventory) or drop the field. (v0.4.0
  release review.)

- **Report the questions the handbook couldn't answer.** The console lists them, so HR can see
  what to write next. The question text is user-written, so it's untrusted data, and it's redacted
  for guard-flagged turns. Fold the "design notes" idea into the tour and the "How it's built" page
  rather than adding a third explainer. (2026-10-06 design brainstorm.)

- **Reach the judge's 85% bar.** Phase 4's fresh full run (2026-10-19,
  `evals/assistant/runs/20261019T152212Z-full.json`) passed the judge at 74% (66% to 80% over three
  trials), up from 67%; the owner accepted it for Phase 4 and kept the bar. What still fails: a
  comparison of two offices written as one uncited sentence (qa-44, qa-45), facts in the reference
  answer the question didn't ask for (qa-23's 48 hours, qa-38's 6 sessions), qa-43's retrieval miss
  below, qa-33's eligibility timing, and "you" used for another state's rule (qa-42). Settle the
  judge's strictness first (below), then decide whether the rest is the prompt, the rubric, or the
  reference answers. The next prompt change also needs a full run, since CI now replays the full
  set. One more for that pass, from the follow-up's review: "start every paragraph with a cited
  sentence" and "don't state what the handbook leaves out for a place" could crowd out a
  refusal, the AI disclosure, or an honest "the handbook doesn't say" for another state. The full
  run's refusals, disclosures, and unanswerable items all passed, so it isn't biting yet; carve
  those out explicitly when the prompt next changes. (Phase 4 answer-quality follow-up.)
- **Search misses Colorado's sick-leave carryover passage.** Asked from Denver, "Colorado sick
  leave carry over unused payout" returns other passages of CO-4.3 but never its "Unused hours
  carry over" one, so qa-43 ("how many sick days in Denver?") leaves out a key fact in every
  trial. Add the query to the retrieval eval's labeled questions and find out why the short
  passage loses (its length, or the "Carryover" heading alone). (Phase 4 answer-quality
  follow-up, smoke run B2.)
- **The judge is stricter about citations than the grades it was validated against.** In the
  agreement run of 2026-10-19 (189 of 204 lines, 92.6%), all 10 disagreements on
  `no_uncited_claims` were the judge saying no where the independent grader said yes. Its reasons
  sometimes contradict themselves ("sits before marker [2] ... which is fine; however ..."). Before
  Phase 7's model comparison leans on the judge, look at those 10 and decide whether the rubric's
  "at or before a marker" wording needs tightening. (Phase 4 answer-quality follow-up.)
- **The judge can't see tool facts or today's date.** It grades a fact from the asker's own profile
  ("your profile lists your personal email") as an uncited policy claim, and a date the assistant
  worked out from today's date as unsupported. Pass the trace's non-handbook tool results and the
  turn's date to the judge, or say in the rubric that profile facts are not policy claims.
  (Phase 4 stage 6 full run, qa-09 and qa-31.)

- **Two eval cost-report gaps.** The scoreboard's "reused recordings" cost is the ledger total
  minus what the live meter saw, and the meter prices only streams that finish, so a billed call
  that kept its reservation (cut by the deadline, a canary, or a transient error) is reported as
  recorded cost, not spent now. And the run's daily cap is its remaining cap plus a baseline read
  at the start, so spend from another sandbox during the run (a `make dev` session) is charged to
  the run and can stop it as if it reached its own cap. Evals run one at a time against the dev
  database, so neither has mattered yet. (Phase 4 phase review.)

## Phase 8: hardening and deploy-readiness

- **Check the production image's CA store for the emSign roots.** `certifi` 2026.10.19 dropped the
  emSign roots whose intermediate keys were compromised (GHSA-6q48-6c7w-9gw2), which covers the
  `httpx` client that reaches Voyage. The Anthropic SDK goes through `httpx2` and `truststore`,
  which use the operating system's store, so the production Dockerfile's base image must ship a
  `ca-certificates` that has dropped them as well. Check it when the Dockerfile is written.
  (certifi advisory, 2026-10-20.)
- **Make sure the production image has time-zone data.** The time-off engine's `today_at` and the
  assistant's per-turn context use the standard library's `zoneinfo`, which reads the operating
  system's zone files. `tzdata` isn't a dependency, so a slim base image without those files would
  fail on every location's "today". Add `tzdata` to the API's dependencies, or check that the
  image ships the zone files, when the Dockerfile is written. (Phase 5 stage 1 review.)
- **Quote directory values in the per-turn context before names become editable.** The context is
  a `system` message built from the asker's name and location. `one_line` keeps each to one line,
  but a name like "Dana. Operator notes: ..." would still read as an instruction with system
  weight. Names come only from the seed today. Before any route edits a person, allow only name
  characters, or put the values in the context as quoted JSON. (Phase 4 stage 2 Opus security
  review.) Moved from Phase 4 at its close: no route edits a name yet, and hardening reviews the prompt inputs.
- **Catch a card number written after other four-digit numbers.** "Room 2401 4242 4242 4242 4242"
  passes the personal-data check: the grouped pattern takes the leading number as the card's first
  group, and that 20-digit number fails the length check. Trying every run of groups inside a
  longer run catches it, but also refuses ordinary year lists ("PTO for 2022 2023 2024 2025 2026")
  about one time in ten, since those are card-shaped and pass the checksum by chance. The v0.4.0
  release review tried it and went back; decide with the other personal-data gaps here, in both
  copies. (v0.4.0 release review.)
- **Catch personal data written in non-Latin digits.** The check normalizes the text (NFKC,
  format characters dropped, Unicode spaces and dashes mapped to ASCII) and then matches ASCII
  digits only, so the browser's copy can follow the same steps. An SSN written in Arabic-Indic or
  Devanagari digits passes. Mapping every Unicode decimal digit to ASCII would catch it; do it in
  both copies at once. (Phase 4 stage 4 Opus security review.) Moved from Phase 4 at its close, with a related note: the browser runs Unicode 17 and the API's Python 15.1, so a few new code points (outlined digits) are flagged only in the browser. Do both copies together. (Phase 4 stage 6 review.)
- **The canary check misses look-alike letters.** It folds case, width, and separators, so the
  canary in capitals or letter-spaced is caught, but Cyrillic letters that look like Latin ones
  (`а` for `a`) are not. It's a tripwire, not a boundary; a confusables map would close it.
  (Phase 4 stage 4 Opus security review.) Moved from Phase 4 at its close: a tripwire, for the hardening pass.
- **Read a conversation's history once per request.** A question reads and serializes the whole
  stored history in the admission checks and again in `TurnRun.begin`, and every
  `GET /assistant/conversations/current` serializes it to size the budget banner. Near the
  80,000-token limit that's about 160 KB read and encoded two or three times before the first
  event. Keep a running size on the conversation, or pass the admitted history into `begin`
  (which also closes the small window in which a recovered turn could carry the history past the
  limit after the check). (Phase 4 stage 4 `/code-review medium`.) Moved from Phase 4 at its close: it fits the cost and load test.
- **Small API polish from stage 4's reviews:** a `Retry-After` header on the budget 429s; problem
  `type` values are bare codes (`turn-running`), a relative URI reference that RFC 9457 allows but
  that a full URI would make unambiguous; there's no limit on how many conversations one person
  starts (sandbox expiry cleans them up). (Phase 4 stage 4 reviews.) Moved from Phase 4 at its close: for the hardening pass.
- **Small web polish from Phase 4 stage 6:** the shared passage panel puts Close before its title in
  the DOM, so Tab goes from the title to the passage text rather than to Close as screen 07's notes
  say; a second tab that starts a new conversation leaves this tab asking in the old one; and a
  malformed stored search source would fail the conversation `GET` (only the API writes them).
  For the accessibility audit and the hardening pass. (Phase 4 stage 6 reviews.)

- **Keep the crisis panel when a crisis turn's end-of-turn write fails.** The crisis text goes out
  live, but if `finish_turn` then times out, the stream adds an `internal` error, the row stays
  `running`, and a reload shows it as abandoned with no escalation, so the 988 and EAP text is gone
  from the page. It needs the database to fail at that moment. Store the crisis verdict before the
  escalation goes out, or have the display show a crisis panel for an abandoned turn whose guard
  said crisis. Do it with the `statement_timeout` item below. (Phase 4 phase review.)
- **One exit for the canary check, and a cheaper fold.** `turn.py` checks the canary at about seven
  places (held text, status notes, the take-back, the restore, closing events), each keeping its
  own tail, so every new event path has needed its own patch. Holding and checking every outgoing
  string at the one exit in `events()` would cover future paths with one rule. Its `_keep_from`
  also NFKC-normalizes one character at a time, twice per text delta, on up to 512 characters;
  measure it in the load test. (Phase 4 phase review.)
- **End crisis and "can't answer right now" turns with a closing event.** They end with no
  `turn.completed` and no `error` (a Stage 6 decision), so the web store infers the end from the
  escalation's kind, and a connection lost right after a crisis panel reads as finished, not
  stopped. One terminal event for every turn would remove the special case. It changes the stream
  protocol, so do it with the hardening pass. (Phase 4 phase review.)
- **Announce the HR panel that appears after a stopped sensitive answer.** Since the Phase 4 phase
  review, a sensitive question the person stops gets the HR contact panel, but only once the saved
  turn replaces the live one (the stream is already closed when they press Stop), and a saved
  panel doesn't announce itself, so a screen-reader user isn't told it appeared. Announce a panel
  that a settling turn adds. For the accessibility audit. (Phase 4 phase review.)
- **Say "start a new conversation" when only the conversation is too big for the budget.** The
  room a question needs is sized with the conversation's whole history, so near the 80,000-token
  limit (or in an outdated conversation) the banner and the 429 say the sandbox has reached its
  limit and suggest a new sandbox, when a new conversation would fit. The right message is new
  fixed text, so it needs the owner's wording and approval first. (v0.4.0 release review.)
- **Don't re-parse the whole answer on every streamed word.** Each `text.delta` re-runs the
  marker placement and react-markdown over the full text, and the thread follows the end each
  time, so the work grows with the square of the answer's length. Batch deltas per animation frame
  in the store, or memoize finished blocks; measure on a low-end phone first. (v0.4.0 release
  review.)
- **Give the app's database login a `statement_timeout`.** The engine sets none, so a hung query
  waits forever. The assistant's end-of-turn writes are bounded in code (10 seconds), but other
  requests aren't. A role-level `statement_timeout` (and `idle_in_transaction_session_timeout`)
  bounds them all. (Phase 4 stage 2 review.)
- **Delete handbook versions no sandbox uses.** Each `make ingest` of changed text adds a version,
  and nothing removes old ones. A cleanup step can delete unpublished versions and published ones
  that are neither the newest nor pinned by any sandbox; the foreign key already refuses to delete
  a version in use. (Phase 3 spec, Data model.)
- **Make the directory's counts cheaper.** `GET /people/facets` runs up to five queries one after
  another (total, matching, the location and department menus, and "My team") on every debounced
  search. Total and matching can be one `count(*) FILTER (WHERE …)`, and the total doesn't change
  with the filters. Measure in the load test first. (Phase 2 close-out review.)
- **Keyboard shortcuts.** Add `/` to focus the composer (never while typing in a field) and ⌘K to
  jump to a page. Both need screen-reader and conflict checks. (2026-10-06 design brainstorm.)
- **Notice another tab's session change at once.** If another tab switches persona or signs out,
  this tab keeps showing what it had loaded, such as HR's view of someone's private details, until
  it next refetches `/me`: on focus, on navigation, or after a 401. It's the same visitor, and every
  new read goes out with the new cookie and is refused, so nothing new leaks. Listen for the
  change and refetch `/me` straight away, for example with a `BroadcastChannel` message from the
  tab that changed it. (Phase 2 stage 6 security check.)
- **Make sign-out end a session's replacements too.** If one tab switches persona while another
  signs out, the switch replaces the session first. The sign-out then finds nothing to end and
  answers 204, but the new persona's session stays valid until the sandbox expires. Give each
  session a `family_id` that rotation carries over, and have sign-out delete the whole family.
  The race needs two tabs acting within milliseconds, in a 24-hour sandbox, and exposes nothing
  across users. (`/code-review medium` on Phase 1, stage 3.)

- **Cap request body size.** Nothing limits it: a 40 MiB JSON body to `POST /sandboxes` was read
  and parsed in full, using about 120 MiB of memory. Phase 1 already reads the body before any
  session check. Cap bodies at about 64 KiB in the ASGI layer or at the proxy, so a few large
  requests can't exhaust a task's memory. (Stage 3 security review.)

- **Require `APP_ORIGIN` in production.** It defaults to `http://localhost:5173`, so a production
  deploy that forgets it refuses every state-changing request. That fails closed, but silently.
  Make settings refuse to start when `APP_ENV=production` and `APP_ORIGIN` is still the default.
  (Stage 3 security review.)
- **Trust forwarded client IPs only from the load balancer.** Security events log the client IP
  that uvicorn reports. Behind the load balancer that depends on `--forwarded-allow-ips`. Setting it
  to `*` would let a client spoof the logged IP, so list only the load balancer's addresses.
  (Stage 3 security review.)

- **Data migrations can't see tenant rows on AWS.** With row-level security forced, a table
  owner that isn't a superuser sees no rows. That is the managed-Postgres case, unlike
  development and CI, where the owner is a superuser. A migration that changes data must set the
  tenant context for each tenant, or run under a role made for it. (Stage 1 security review.)
- **Look up sessions without granting the table.** `od_app` can read every tenant's `sessions`
  rows, because a session is looked up before the tenant is known. The spec accepts this. A
  `SECURITY DEFINER` function that returns one session by its token hash would let `od_app` drop
  its `SELECT` on the table. (Stage 1 security review.) `od_app` can also insert and delete any
  tenant's sessions, with any expiry: the Phase 1 close-out security review forged an HR session in
  another tenant from `psql`. No route can do this, since `start_session` builds the row through a
  tenant-scoped select, but SQL access as `od_app` would become a working login anywhere. Enable
  row-level security on `sessions`, with an insert policy that requires the current tenant and
  person, keep the expiry within the tenant's, and test that an insert for another tenant fails.
- **Keep the owner's database URL out of the API.** The API's settings load
  `MIGRATION_DATABASE_URL` and `CLEANUP_DATABASE_URL` though it uses neither, so the API process
  holds the owner's credentials, which bypass row-level security. Give Alembic and the bootstrap
  script their own settings class, and give the API task only `DATABASE_URL` in the AWS secrets
  contract. (Phase 1 close-out review.)
- **One transaction per signed-in request.** `signed_in` looks the session up in one transaction
  and does the tenant's work in a second, so each request pays two round trips and two pool
  checkouts, and a session can end between them. Set the tenant context in the lookup's own
  transaction. (Phase 1 close-out review.)
- **Postgres 16 or later.** The bootstrap script grants roles `WITH INHERIT TRUE`, which needs
  Postgres 16. Development and CI run 17. The managed Postgres chosen in Phase 9 must be 16 or
  later.

- **One source for tool versions.** The gitleaks version is written in three places: the Security
  workflow, the `Makefile`, and the pre-commit config. The ruff hook's version separately follows
  `uv.lock`. Dependabot has a `pre-commit` ecosystem that could keep the hook versions current.
  Add it with the same 7-day cooldown, and make the `Makefile`'s hand-bumped versions the only
  manual ones.
- **The pre-commit hook lives in uv's cache.** `uvx pre-commit install` points the git hook at a
  cached Python, so `uv cache clean` breaks commits until `make setup` runs again. Installing it
  with `uv tool install pre-commit` would make the hook durable.
- **Audit only the app's dependencies.** `uv run --with pip-audit` also audits pip-audit's own
  dependencies, so an advisory in one of those would fail the Security workflow for a reason
  unrelated to the app. The lockfile-only form is
  `uv export --locked --no-emit-project | uvx pip-audit -r - --no-deps --disable-pip`.

- **`ping()` has no hard wall-clock bound.** If canceling the query stalls on the network,
  closing the connection can take longer than the timeout, because SQLAlchemy shields the close.
  The orchestrator's own probe timeout covers it; revisit only if health checks need a strict
  bound.
- **Hide the API docs in production.** Set `docs_url`, `redoc_url` and `openapi_url` to `None`
  when `APP_ENV=production`, and keep `app.openapi()` working for the schema export. Also drop
  the `server: uvicorn` header (`--no-server-header`) and send `Cache-Control: no-store` on
  health.
- **Keep probe traffic out of logs and traces.** Filter `/api/v1/health` from `uvicorn.access`,
  and from OpenTelemetry if it's enabled.

From the Phase 1 review ([the spec's Later phases](specs/2026-10-03-phase-1-tenancy-identity-permissions.md#later-phases)):

- **Rate limits and Turnstile on sandbox creation.** `POST /api/v1/sandboxes` needs no session,
  and each call seeds 120 people.
- **The scheduled cleanup job.** The `od_cleanup` role can already delete only expired
  sandboxes. Nothing runs it on a schedule yet.
- **Re-test `set_config` under RDS Proxy or PgBouncer.** Row-level security depends on settings
  scoped to one transaction, and a pooler in transaction mode must not carry them between
  clients. The reused-connection tests are the model. Background: the pgsql-bugs thread on local
  settings,
  https://www.postgresql.org/message-id/CA+Q86ij0KDCB0G45G509-8q0DNR611gcKG-sSM83GA1EBL7boA@mail.gmail.com.
- **Database TLS with certificate checks, and secret rotation** for the three database URLs.
- **Deletion from backups.** A sandbox deleted from the database still exists in backups until
  they expire. Document how long, or exclude sandbox data from them.
- **Check CI's path filters automatically.** Each CI job runs only when its filter's paths change,
  and the filters list by hand the files outside each app that its tests read (`docs/design/`,
  the handbook, the personal-data cases, the seed, the `Makefile`). A test that reads would
  otherwise not run on the PR that breaks it, as happened after #63. A small check could find
  every path a test reads outside its app and fail if no filter covers it. The theme tokens'
  test could also check the other way, that every theme token has a source in the design export.
  (Theme-token fix review, 2026-10-20.)

## Phase 9: deploy to AWS

- **Don't share a Postgres server between environments that reuse these role names.** Roles
  belong to the whole server, and Postgres lets every role connect to every database by default.
  If staging and production lived on one server, a login made for one could connect to the other,
  inherit `od_app`, and read any tenant. Both bootstrap runs would also reset the shared login's
  password. Either give each environment its own server, or revoke `CONNECT` on the database from
  `PUBLIC` and grant it only to that database's own logins in the bootstrap script.
  (`/code-review medium` on Phase 1, stage 1.) Migration 0002 also reuses an existing `od_app` or
  `od_cleanup` after checking what that role is a member of, but not which roles are members of
  it, so another database's login granted `od_app` would inherit Open Door's access. Check
  `pg_auth_members` in both directions. (Phase 1 close-out review.)

- **Separate liveness from readiness.** ECS container health checks must not depend on the
  database, or an RDS failover would restart every task. Add `GET /api/v1/health/live`, which
  never touches the database, for the container check, and keep `/api/v1/health` as the load
  balancer's readiness check.
- **Align the ping and probe timeouts.** The ping and asyncpg connect timeouts are both 5 s, the
  same as the default load balancer and ECS probe timeouts, so a blackholed database times the
  probe out instead of returning a clean 503. Use about 2 s for the health ping, or a probe
  timeout of 6 s or more.
- **Protect the health endpoint from abuse.** Every call is an unauthenticated database round
  trip. Cache the result for 1–2 s with a single in-flight check, or rate-limit the path at the
  load balancer.

- **Line up the shutdown timeouts.** uvicorn runs with `--timeout-graceful-shutdown 15`, and the
  app then waits up to 12 seconds for open streams to save, so a container needs about 27
  seconds after SIGTERM. That fits ECS's default `stopTimeout` of 30. If Phase 9 raises the
  graceful timeout (to let long answers finish during a deploy), raise `stopTimeout` (at most
  120) and the load balancer's deregistration delay with it, and keep the 12-second drain inside
  the gap. (Phase 4 stage 4.)
