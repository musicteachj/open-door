# Backlog

Findings from reviews that were deliberately deferred, each with the reason and the phase that
should pick it up. When one is done, delete it here and record it in the changelog.

## Any phase

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
  them. (Phase 5 stage 4 `/code-review medium`, rounds 1 and 3.)
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

## Phase 7: AI Ops console, reviewer experience, model decision

- **`list_cases` shows HR the oldest cases first when the list is cut.** The tool takes the queue's
  first page (new cases by reply-by, then the rest oldest first) and drops HR's own, so for `closed`
  or `in_review` with more than 20 cases the model sees the oldest 20 and none from this week.
  Changing the tool's results changes what the model reads, so do it with Phase 7's next full run.
  (v0.6.0 release review.)
- **Tell HR the right route for a case.** The guard's topic note (`TOPIC_NOTE` in
  `app/ai/guard.py`) and the assistant prompt's case paragraph point everyone to "the My cases
  page", but HR has no My cases page (the owner's rule: HR gets no route to it). The answer's link
  is already plain text for HR. Make the wording role-aware; it changes what the model reads, so
  do it with Phase 7's next full paid run. (Phase 6 phase review.)
- **Rename the bare `amount` key in the time-off tool results.** `timeoff_results.py` sends
  `"amount": label(...)` (and the same key in the draw, check, and card results), against the rule
  that units live in the field name; it holds a label, so `amountLabel` fits. Renaming it changes
  what the model reads, so it needs a full paid eval run: do it with Phase 7's next one. (Phase 5
  phase review.)

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
- **Two eval cost-report gaps.** The scoreboard's "reused recordings" cost is the ledger total
  minus what the live meter saw, and the meter prices only streams that finish, so a billed call
  that kept its reservation (cut by the deadline, a canary, or a transient error) is reported as
  recorded cost, not spent now. And the run's daily cap is its remaining cap plus a baseline read
  at the start, so spend from another sandbox during the run (a `make dev` session) is charged to
  the run and can stop it as if it reached its own cap. Evals run one at a time against the dev
  database, so neither has mattered yet. (Phase 4 phase review.)

## Phase 8: hardening and deploy-readiness

- **A case refusal that can't succeed still offers "Try again".** `use-open-case.ts` maps the
  waiting limit, a repeated submission, personal data, and empty words; any other refusal (a 404
  `case-turn-not-found`, a 422 `case-words-too-long` or `case-invalid`) shows "Your case wasn't
  sent. Please try again.", and every retry fails the same way. Give those a line that points to
  My cases or the HR contacts instead. (v0.6.0 release review.)
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
- **Tie the CSRF header to the audited read itself.** Audited reads require `X-CSRF-Token` through
  a dependency each route opts into (`AuditedReadDep`), so a future audited route that forgets it
  could be started by a plain navigation from an HR partner's browser, and no test would fail.
  Since the web client now sends the header on every `/api/` request, either require it on every
  signed-in `/api/` request, or have the audited-read services check that the request carried it.
  (Phase 6 stage 3, `/code-review medium` round 4.)

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

- **Give the confirm a lock timeout.** A confirm that has passed its expiry check can still wait
  on the person's time-off lock, held only by short time-off writes, so its overrun past the 15
  minutes is small but has no stated bound. A `SET LOCAL lock_timeout` in the confirm would make
  it explicit. (Phase 5 stage 3 security review.)

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
