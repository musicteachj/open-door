# Backlog

Findings from reviews that were deliberately deferred, each with the reason and the phase that
should pick it up. When one is done, delete it here and record it in the changelog.

## Any phase

- **"Send this question to HR."** The console counts the questions the handbook couldn't answer
  (counts only: the question is the person's text). A button on a "couldn't find it" answer would
  let the person send the question to HR themselves, so HR can see what to write next. (Phase 7
  planning, decision 4.)
- **Sonnet 5.5 writes tool calls as answer text.** In the model comparison of 2026-11-03 it did so
  on a workplace-safety report (two of three trials) and a lunch-break question (all three), and
  again on the turn's one re-issue, so the person got an error. It is why Opus 5.5 stays
  ([ADR 0018](adr/0018-default-model.md)). Measure a newer Sonnet, or a turn that recovers from it
  another way (a second re-issue, or a request that disallows text before the tool call), before
  comparing again. (Phase 7, Stage 4.)
- **A "still answering" conflict on Confirm gives no feedback.** `use-proposal-actions.ts` treats
  every 409 as "the card changed; the next read shows it". A 409 `turn-running` leaves the card
  pending, so if the page's view of the turn and the server's briefly differ, Confirm does nothing
  visible. Show the "still answering" text for a 409 whose status is still pending. (v0.5.0 release
  review.)
- **The decide and cancel cards read their request twice.** `proposal_cards.py` loads the stored
  request and then the same row again through `load_request_rows` (and the cancel card loads the
  person's facts as well); one read would do. (v0.5.0 release review.)

- **The approvals gallery's "deciding" dialog scan can fail under heavy local load.** In
  `gallery-approvals.spec.ts`, the scan of `decision-dialog-deciding` nudges a held page clock while
  axe runs, and twice in full local `make check` runs (2026-10-26) a clock step found the page
  already closed ("clock.runFor: Target page, context or browser has been closed"). It passed on
  each rerun and in CI. Make the nudge loop stop before the page can close, or scan with the
  dialog's timer stubbed instead of a held clock. (Phase 5 phase review.)

- **The scripted model's "next Friday" and "tomorrow" ignore holidays and days off.** The browser
  tests that book through chat skip, with a stated reason, on the few dates a year when next Friday
  is a company holiday or tomorrow isn't on the person's schedule (`skipUnlessScriptedDayCounts`).
  The scripted model could pick the next day that counts instead, so those tests never skip. (Phase 5
  stage 6.)
- **A confirm card can forget a confirm in flight.** If the live answer gives way to its saved copy
  while Confirm is being pressed, the card remounts and shows Confirm enabled again; a second press
  gets the card's current state calmly (a 409), so nothing is booked twice. A shared key for the card
  across the live and saved views would keep its state. (Phase 5 stage 6 review.)
- **Resizing across 1280 px with the request form open resets the form.** The form docks beside the
  page from 1280 px and is a bottom sheet below it; crossing that width remounts it, clearing the
  dates. The same happens to the date picker since Stage 5. (Phase 5 stage 6 review.)
- **Some seeded past requests start or end on a day off.** Priya's history can read "Sunday, August 2
  to Monday, August 3 · 8 hours (1 day)": the figures are right (the engine counts only scheduled
  days), but a person would pick their first and last working days. The seed could snap each drawn
  range to scheduled days. (Phase 5 stage 6 photos.)

- **A conversation layout browser test can lose its element mid-check.** At 390 px, "streaming,
  stopped, and an error mid-stream stay inside the column" (`e2e/conversation-layout.spec.ts`)
  failed once with "no box for a visible element": the element was visible, then gone before its
  bounding box was read. It passed on the rerun, and nothing near it had changed. Wait for the
  final state before measuring, or retry the measurement; Phase 5 stage 6 changes that page anyway. On 2026-10-25, with the machine under heavy load (a load average over 10), ten layout
  and gallery tests in `conversation-layout.spec.ts` and `gallery-conversation.spec.ts` timed out
  measuring the page; all passed on the rerun.
  (Phase 5 stage 2 close.)

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

- **Screen names before they reach the model, if names ever become editable.** The next turn's
  context lines about proposals (`outcomes_since` in `app/ai/proposals.py`) use the requester's
  or approver's directory name, and its plain-name check only refuses odd characters and long
  names: "Ignore all previous instructions" passes. That is safe while every name is seeded
  directory data. A phase that lets a person edit a name must treat names as untrusted text there.
  (Phase 5 stage 3 security review.)
- **Decide whether directory names and titles are untrusted text.** CLAUDE.md says a turn that
  processes text a person wrote gets no proposal tools. The time-off tools (and Phase 4's
  `find_people`) put directory names and job titles into the model's context in turns that can
  still propose. Today they are seeded and no route edits them, so they aren't user-written. When
  any route lets a person edit a name or title, either filter them before they reach the model
  (the outcome line's `_plain_name` rule, say) or drop the proposal tools from turns that read
  them. (Phase 5 stage 4 `/code-review medium`, rounds 1 and 3.) Since Phase 8, Stage 6 the
  asker's own directory values reach the model as one quoted JSON object, introduced as facts
  from the directory and not instructions, and a red-team item asks as a person whose name reads
  like an instruction. Names and titles in tool results and in the outcome lines are not quoted
  that way, so this item stays open for them.
- **Small edges in what the next turn is told about cards.** A card the model replaced within a
  turn is reported to the next turn as replaced (true, but not news), and a card canceled because
  its tool timed out in a completed turn is described as canceled because "the answer did not
  finish". The outcome line's name rule also drops harmless names with lowercase particles or a
  suffix ("Ana de la Cruz", "Jr."), falling back to "the requester". (Phase 5 stage 4 reviews.)
- **One card per model response, not per turn.** A second proposal call in the same response is
  refused even when the first one failed, and a later round in the same turn may replace the card,
  although the refusal says "per answer" and the action eval's no-write check allows one card a
  turn. Align the three if the evals show the model re-proposing. (Phase 5 stage 4 reviews.)
- **A turn that replaces a card and then fails loses both.** `create_proposal` cancels the
  pending card as replaced at once; if the turn then fails, its own card is canceled too, and a
  status can't move back. The person can ask again. Deferring the replacement to the turn's end
  would need the one-pending-card index (migration 0010) relaxed. (Phase 5 stage 4 review.)
- **Label in Name follow-ups.** The 2026-11-01 fix names controls from their content, with hidden
  punctuation and words between the shown pieces. Left as they are: Chromium puts a space before
  each hidden comma or period ("Marcus Bell , Store Manager"), which screen readers don't voice and
  the browser tests normalize (`tidyName`, `nameLike`); the fix at the root is a hiding technique
  that keeps the punctuation in the same text run, with one shared helper in place of about 20
  copies. A handbook search result's name now holds its excerpt (once its description), which is
  long in a links list. The persona card's name changes to its starting text while the live region
  announces the same words. A citation marker and its chip name the same source two ways.
  (`/code-review medium` on `fix/label-in-name`.)
- **Fail a web test that makes an unanswered request.** MSW's `onUnhandledRequest: 'error'` only
  makes the request reject, which React Router's error boundary catches, so a test that renders a
  page without its fakes still passes. On 2026-11-01 five such tests broke the web job once React
  19.3.1 began reporting recovered render errors. A shared `afterEach` that fails on any unhandled
  request would catch the next one, but a request left running by an earlier test file in the same
  worker is reported under a later, innocent test (seen with `query-client.test.ts`), so the guard
  needs a way to tell those apart first, or `isolate`d workers. (`/code-review medium` on
  `fix/shell-test-directory-fakes`.)

## Handbook content

- **A military leave section.** The handbook has none. A company section under the federal
  reemployment law for service members (USERRA) comes first; state addenda follow, such as
  Georgia's leave for state guard members (O.C.G.A. §38-2-279, not verified). (Phase 3 stage 6.)
- **A Georgia persona,** if the owner wants one: a fifth sign-in card for an Atlanta employee,
  with a design pass on the landing page first and a migration for the new persona key. Georgia is
  covered today by Atlanta employees in the directory and Georgia askers in the eval. (Phase 3
  stage 6.)

## Phase 5: time off

All five items were closed in stage 6 (2026-10-25): the nav after a switch (a `navFor` test and the
shell's switch test), writes from an old identity (no write sets query data; a test enforces it),
the scroll-restoration exception (a history marker), "Show your work" for the time-off tools, and
the conversation read after a turn ends.

## Phase 6: cases and escalation

All three items were closed in Phase 6: the hand-off's texts say only what's true (the panel and
form texts approved in stage 4), case text is encrypted (stages 1 and 2), and the four
conversation-page glitches are fixed with browser tests (stage 6).

## Phase 8: hardening and deploy-readiness

- **HR asking something the handbook doesn't cover is not always pointed to the HR team.** The
  prompt says to suggest the HR team, by that name, when the search finds nothing. Asked by Dana
  (HR) about a 401(k) match, the assistant named "the benefits team or whoever runs the retirement
  plan" in one trial of three in the full runs of both 2026-11-03 and 2026-11-12 (`qa-49`), as if HR
  weren't the place to ask when the asker is HR. Add "even when the asker is on the HR team" with the
  next prompt change. In the 2026-11-12 run the failing trial was the one CI replays, so that
  item's recording was made again on its own (`ITEMS=qa-49`); the board keeps the failure.
  (Phase 8, Stage 6.)
- **The audit log stores `None` as the JSON value `null`.** `AuditEvent.before` and `after` are
  nullable `jsonb` columns without `none_as_null=True`, so an event with no before or after state
  holds JSON `null`, not SQL `NULL`, and an `IS NULL` query misses it. The assistant tables were
  fixed in stage 1; the audit columns need the same type change and a data fix for existing rows.
  (Phase 4 stage 1 review.) Moved from Phase 7 at its close: the console only counts audit events
  by action and never queries these columns, so the fix goes with the hardening pass.
- **Phase 7 review lows, recorded, not fixed** (2026-11-05). Each is a rare edge case in the
  tour or the console:
  - starting a new conversation while a tour chip's answer is still coming leaves the step with
    only Skip, since the turn it waits for is no longer on the page;
  - on a step that expects a card, Next shows as soon as the card does, before the answer
    finishes, and pressing it then stops that turn (the persona switch ends the stream);
  - leaving `/ask` while a card step's answer streams shows the "didn't come" line until the
    visitor goes back, where the card makes it a result;
  - signing in again after another tab changed the persona clears the query client, mutation
    cache included, so the identity gate can open while a switch is still in flight;
  - after a reload, a chip other than the step's last one that was marked sent before its request
    went out stays Sent (only the last chip tracks whether its request was issued);
  - the tour runner subscribes to the current conversation twice (its own read and
    `useTurnFinished`'s);
  - the console's day heading counts the rows loaded so far, and a day's redacted rows sort after
    its timed ones, so on a day of more than 50 turns they appear only after "Show more turns";
  - a console row's cost leaves out a reservation kept because its cost was unknown (a settle that
    timed out), so the cost tile can read below the ledger's spend;
  - the console row adds the safety check's tokens to the turn's field by field instead of with
    `pricing.total_usage`;
  - after a send whose outcome is unknown (a network failure, or a 5xx since the review), the
    plain chat doesn't read the conversation again, so a turn the API did start shows only on the
    next read; and a proxy's own 4xx page (nginx's 413) now counts as unknown too, so the tour
    keeps that chip Sent though the request likely never reached the API, and so does the API's
    own 500 from before the turn's row exists (the API's problem could say no turn started);
  - the scoreboard's `pct` and `_count` each have their own float-noise tolerance, and the
    escalation run's terminal report keeps its own `_pct`, which can still print "100.0%" for a
    rate just under 1; a board holding NaN or Infinity (which `json` reads) isn't refused when
    loaded;
  - an abandoned turn's console row shows no cost, tokens, or timings, though the dead turn's
    safety check and model charges are already in the spend ledger, so the cost tile's sandbox
    spend and the rows' costs drift apart with no row to explain it (the v0.7.0 release review).
- **A repeated send of the same words reads the case twice and isn't audited.** `_repeat` in the
  case service unwraps the key and decrypts the stored words to compare them, once outside and once
  under the lock, and a second submission from another tab with the same words is folded into the
  first case with no audit row saying so. (v0.6.0 release review.)
- **A summary retry lost to a restart blocks the next one for a minute.** The retry commits
  `case.summary.retried` and then runs the summary in a background task; if the API stops before
  it runs, the in-flight window refuses HR's next retry for 60 seconds with nothing to say the job
  was lost. (v0.6.0 release review.)
- **The reply-by date and next year's holidays.** `reply_by_at` reads HQ's holidays from the
  sandbox's table in a 21-day window; a case sent in late December in a sandbox with no rows for
  the next year would get a reply-by date on a closed day. Check the seed always writes the next
  year's holidays, or read them from the calendar. (v0.6.0 release review.)

- **The sticky composer can cover "Show your work".** At a 900-pixel-high window, with a tall HR
  panel above it, the conversation page's sticky composer partly covers the "Show your work"
  toggle, and axe's target-size rule flags it, so Stage 6's case tests scan the panel only. Check
  it in the accessibility audit: scroll padding under the last turn, or a test of the toggle's
  visible area. (Phase 6 stage 6.)
- **A second route for a concern about the HR team.** A case goes only to HR, so a person whose
  concern is about someone in HR has no other way in through Open Door; today the handbook's
  contacts are the only route. A later phase could add a named second reviewer outside HR for
  such cases. (Phase 6 spec.)
- **Encrypt the time-off denial note.** `time_off_requests.decision_note` is a manager's own
  words and stays readable in Phase 6, which encrypts only conversation and case text (ADR 0015).
  Seal it with a data key for the request, as the conversation store does. (Phase 6 spec.)
- **One stored value that won't decrypt breaks the conversation for good.** Its owner's
  `GET /conversations/current` and `GET /budget` return a 500 from then on, since "current" is the
  newest conversation. Only a damaged row or a lost key causes it. Let the person start a new
  conversation from that state, or mark the conversation unreadable. (Phase 6 stage 1 security
  review.)
- **Encryption binds each message to its row, not to its order.** Someone who can write to the
  database could reorder a conversation's messages, or cut tool-call entries off the end of a
  turn's list, and they would still decrypt. That access is outside the threat model. If it ever
  isn't, bind `position` and the list's length into the associated data. And if a second
  ciphertext format is added, bind the version byte too. (Phase 6 stage 1 security review.)

- **The per-turn check for untold card outcomes grows with the conversation.** Each turn start
  reads every card in the conversation and checks each against every stored context's
  `reported_outcomes` array, with no index, while it holds the cards' share locks. Fine at demo
  scale (conversations end with the sandbox); bound it (skip contexts older than the card, or keep a
  time pre-filter) if conversations ever last. (Phase 5 phase review.)
- **A person recorded as their own manager is half handled.** PTO for them is now refused with
  `no-approver`, but the summary still names them as their own manager and their requests count as
  waiting for themselves. Exclude the person wherever manager links are resolved. The seed never
  makes such a row; it would be a data error. (Phase 5 phase review.)

- **The Approvals reads load each person's facts one at a time.** `_managed_view` loads each
  direct report's facts and requests in turn for the waiting list and every single-request read,
  and coverage now loads each colleague's schedule too. Batch the loads per set of people. (Phase 5
  phase review.)
- **The request form checks the preview on every change.** Each hours keystroke, stepper press, and
  the first click of a range sends `POST /time-off/check`; stale answers are dropped, so it's only
  wasted requests. A short debounce, or no check while a range is half picked, would cut them.
  (Phase 5 phase review.)
- **Small duplications the phase review left.** Weekday and month names and the long-date format
  live in `proposals.py`, `scripted.py`, and `context.py`; the confirm card's executed lines repeat
  the pages' toast texts; `balances`, `pto_available_minutes`, and `_evaluate_own` gather the same
  inputs three times; the eval graders check ISO dates the tool's own input model already checks;
  the eval runner builds the seed company twice. Share each when that code next changes. (Phase 5
  phase review.)

- **Recent decisions leave out two kinds of past decision.** The `decided` scope lists requests
  the manager approved or denied that are still approved or denied, among the manager's current
  reports. An approval the employee later canceled, and a decision about someone who has since moved
  to another manager, drop out of "Your decisions from the last 90 days", though the request still
  records who decided it. Showing them needs a line such as "Approved October 20, later canceled".
  Reporting lines can't change in the demo yet. (Phase 5 stage 6 review.)

- **Time-off lists stop silently at 200 rows.** `GET /time-off/requests` caps every scope at 200,
  ordered by start date (newest decision first for `decided`). A person with very many short sick
  entries would lose the newest rows of My requests, and a manager of a large organization the end
  of Coming up, with nothing saying the list is incomplete. Add paging or say when a list was cut.
  (Phase 5 stage 6 review.)
- **Back across several panel entries can keep the wrong scroll position.** The scroll hook keeps
  the position on a Back or Forward when either entry is marked as a panel move. A jump of several
  steps between same-page entries that aren't an open-and-close pair then skips restoring that
  entry's saved position. Rare: it needs history steps, not the panel's own close. (Phase 5 stage 6
  review.)

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
- **Small API polish from stage 4's reviews:** problem
  `type` values are bare codes (`turn-running`), a relative URI reference that RFC 9457 allows but
  that a full URI would make unambiguous; there's no limit on how many conversations one person
  starts (sandbox expiry cleans them up). (Phase 4 stage 4 reviews.) Moved from Phase 4 at its close: for the hardening pass.
- **Small web polish from Phase 4 stage 6:** the shared passage panel puts Close before its title in
  the DOM, so Tab goes from the title to the passage text rather than to Close as screen 07's notes
  say; a second tab that starts a new conversation leaves this tab asking in the old one; and a
  malformed stored search source would fail the conversation `GET` (only the API writes them).
  For the accessibility audit and the hardening pass. (Phase 4 stage 6 reviews.)

- **One exit for the canary check, and a cheaper fold.** `turn.py` checks the canary at about seven
  places (held text, status notes, the take-back, the restore, closing events), each keeping its
  own tail, so every new event path has needed its own patch. Holding and checking every outgoing
  string at the one exit in `events()` would cover future paths with one rule. Its `_keep_from`
  also NFKC-normalizes one character at a time, twice per text delta, on up to 512 characters;
  measure it in the load test. (Phase 4 phase review.)
- **Don't re-parse the whole answer on every streamed word.** Each `text.delta` re-runs the
  marker placement and react-markdown over the full text, and the thread follows the end each
  time, so the work grows with the square of the answer's length. Batch deltas per animation frame
  in the store, or memoize finished blocks; measure on a low-end phone first. (v0.4.0 release
  review.)
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


- **Set `FORWARDED_ALLOW_IPS` in the task definition.** The image's entrypoint passes it to
  uvicorn's `--forwarded-allow-ips`, and empty trusts no proxy (Phase 8 stage 2). The Phase 9 task
  definition must set it to the load balancer's addresses only, never `*`, or the limits and the
  security log see the load balancer's address for every visitor.

- **Data migrations can't see tenant rows on AWS.** With row-level security forced, a table
  owner that isn't a superuser sees no rows. That is the managed-Postgres case, unlike
  development and CI, where the owner is a superuser. A migration that changes data must set the
  tenant context for each tenant, or run under a role made for it. (Stage 1 security review.)
- **Postgres 16 or later.** The bootstrap script grants roles `WITH INHERIT TRUE`, which needs
  Postgres 16. Development and CI run 17. The managed Postgres chosen in Phase 9 must be 16 or
  later.


- **`ping()` has no hard wall-clock bound.** If canceling the query stalls on the network,
  closing the connection can take longer than the timeout, because SQLAlchemy shields the close.
  The orchestrator's own probe timeout covers it; revisit only if health checks need a strict
  bound.
- **Keep probe traffic out of traces.** Phase 8 stage 1 filters both health paths from
  `uvicorn.access`; if OpenTelemetry is enabled, filter them there too.

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

- **Point the probes at the right health path.** Phase 8 stage 1 added `GET /api/v1/health/live`
  (never touches the database) and kept `GET /api/v1/health` (readiness, with a 2-second ping).
  The ECS container check must use `/live`, or an RDS failover would restart every task; the load
  balancer uses `/health` with a probe timeout above 2 seconds.

- **Line up the shutdown timeouts.** uvicorn runs with `--timeout-graceful-shutdown 15`, and the
  app then waits up to 12 seconds for open streams to save, so a container needs about 27
  seconds after SIGTERM. That fits ECS's default `stopTimeout` of 30. If Phase 9 raises the
  graceful timeout (to let long answers finish during a deploy), raise `stopTimeout` (at most
  120) and the load balancer's deregistration delay with it, and keep the 12-second drain inside
  the gap. (Phase 4 stage 4.)
