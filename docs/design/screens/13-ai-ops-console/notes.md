# Screen 13 · AI Ops console

- Route: `/console`, HR only. As Dana Whitfield, HR Business Partner, Human Resources, Denver HQ.
- Source: `AI Ops Console.dc.html` (one frame per state, then the component card). Shared scoreboard: `Scoreboard.dc.html` (`<dc-import name="Scoreboard" uid="…">`). Components: `components/console/`. All three are in `docs/design/system/`.
- Sample day: Monday, October 26, 2026, about 10:41 AM MDT, in a fresh sandbox right after the guided tour. Nine turns, nothing else. Every time is Mountain time.
- Frames are live: open a row to dock its trace, open another to swap it, Escape or X to close.

**"How it's built" was dropped in Phase 7 (2026-10-31).** The screenshots below still show it;
the build leaves it out.

## What the screen shows and doesn't

- Per turn: time, the asker's role and the location's city and state, outcome, safety check verdict, tool count, cited sections, cost, first-token time. In the trace: tools in order, sections retrieved, the card offered, model and versions, tokens, cost, timings.
- Never a name, avatar, initials, question text, answer text, or tool input. A refusal shows its category only.
- The flagged turn: one row after every timed row of the day, so its position can't reveal its time. Only the date, tokens, cost, and timings. Plain text on `--confidential-tint` with screen 11's lock. Not a button, not focusable, no trace.
- No red, amber, or warning styling on any figure. Safety check time (980 ms against an 800 ms target) is the same ink as everything else, and the target line states it. The only red on the page is the danger icon on a Failed outcome or a failed tool, because those are errors.
- No ranking, scoring, or sorting of turns or people, and no column sorting. Order is newest first.
- No links to code, repositories, ADRs, or documents. No composer.

## States

| File | State |
| --- | --- |
| desktop-default | Top of the page: heading, subhead, eight tiles four across, then "Monday, October 26 · 9 turns": eight timed rows newest first and the flagged row last. Cases "3 new" |
| desktop-trace-answered | Trace (a), 10:31 AM. Panel docked at 420 px; tiles reflow to two columns; the list is scrolled into view and the row shows selected |
| desktop-trace-card | Trace (b), 10:33 AM: check_time_off then propose_time_off_request, card "Book PTO" |
| desktop-trace-injection | Trace (c), 10:38 AM: Ordinary, 980 ms, the "Possible prompt injection" tag; tools, sections, and card all "None" |
| desktop-scoreboard | Scrolled to "Eval scoreboard": eight set rows, "History of full runs", the footnote, and the two plain lines |
| desktop-empty | New sandbox: every tile "No turns yet" (cost tile keeps "Sandbox spend $0.00 of $1.00 cap"), the list says "No questions yet in this sandbox. Ask something, or take the tour." with "Ask a question" (primary, to /ask) and "Take the tour" (secondary). Cases "2 new". Sandbox resets in 24 h |
| desktop-loading | Tile titles with static skeleton bars, the table header with six skeleton rows, `aria-busy` on the section and a hidden status line. Scoreboard shown |
| desktop-error | Global States' pattern inside "This sandbox": "Something went wrong on our side.", "The sandbox figures didn't load. Try again in a moment. If it keeps happening, this reference helps us find it:", reference `c41e8b07`, Retry. Scoreboard shown |
| component-card | Every part and state of the console components (see below) |

## Layout (1440 px)

- Sidebar 248 px and the content sheet as on screen 12. Frames are 1440 × 1420 viewports; the sheet scrolls.
- Sheet padding 40/48 px, content 1080 px. Sections: "This sandbox" (h2), then "Eval scoreboard" (h2, the Scoreboard's own heading) 64 px below, over a subtle rule.
- Tiles: `repeat(auto-fill, minmax(220px, 1fr))`, 16 px gap. Four across at 1080 px, two beside the docked panel.
- Turn table columns: 96 / 1.3fr / 1.4fr / 1.6fr / 56 / 80 / 72 / 88, 12 px gaps; with the panel open 64 / 0.9fr / 1.1fr / 1.4fr / 40 / 56 / 52 / 52, and the injection tag stacks on two lines. Rows 56 px minimum. Tools, Cost, and First token are right-aligned.
- Trace panel: `--panel-width` (420 px), border-left, header like the passage panel (eyebrow "Turn trace", X), then sections divided by `--border-subtle`.

## Tiles

1. Time to first token: "Median" / 1.6 s / 95th percentile 2.2 s / Target 3 s / "9 turns · Small sample"
2. Safety check time: "95th percentile" / 980 ms / Target 800 ms / "9 turns · Small sample". Same ink as every other figure
3. Cost per answered question: $0.021 / 8 answered questions / Sandbox spend $0.21 of $1.00 cap / "Small sample"
4. Escalation rate: 11% / 1 of 9 turns flagged by the safety check / "Small sample"
5. Refusals and fallbacks: 0% / 0 of 9 turns / "Small sample"
6. Said the handbook doesn't cover it: 0 / of 9 turns / "Search came closest with:" None yet / "Small sample"
7. Cards confirmed by a person: Time-off requests 1, Decisions 1, Cancellations 0 / "From the audit log"
8. Possible prompt injections: 1 / of 9 turns / "Small sample"

## Trace panel

- Order: Outcome, Safety check, Tools called, Sections retrieved, Card offered, Model, Tokens, Cost, Timings.
- Tools: icon, plain label, tool name in mono, duration, then OK (check, ink-muted) or Failed (circle-alert in danger).
- Sections: number, title, then "Cited" (ink, semibold) or "Not cited" (ink-muted), as in "Show your work".
- Model: model ID, effort, prompt version, tools version; a fallback adds "Served by claude-sonnet-5-5 after a fallback".
- Tokens: "Input 12,400 (10,200 from cache)", Output, Cache writes. Cost with "Includes the safety check".

## Interactions and accessibility

- The turn list is an ARIA table (`role="table"`, `row`, `columnheader`, `cell`) with real headers. Each timed row has one button in its Time cell, named "10:31 AM, Employee, Oakland, CA, Answered", with `aria-expanded` and `aria-controls` pointing at the trace. Clicking anywhere on the row opens it; the keyboard ring draws around the whole row.
- Opening moves focus to the panel heading (`tabIndex=-1`). Escape or X closes and returns focus to the row's button. Opening another row swaps the content and focus goes to the heading again.
- The panel is an `aside` labeled by its heading. Selected row: `--primary-tint` with a 3 px primary inset bar, plus `aria-expanded="true"` on its button.
- The flagged row is plain text in a single cell, not focusable; its sentence and facts are read in full.
- "Small sample", targets, and "None" are words. Empty cells show "–" with a visually hidden "None" ("Not in the set" in the history).
- Contrast (recomputed at sync from the tokens): ink 16.4:1 and ink-muted 6.1:1 on white; ink-muted on the injection tag's sunken fill 5.9:1; on the selected row's primary-tint, ink 13.0:1 and ink-muted 4.9:1; on the flagged row's confidential tint, ink 14.9:1, ink-muted 5.6:1, and the lock in primary 10.1:1. Focus ring 2 px primary.

## Phone (390 px, notes only)

- Tiles one per row.
- The table header hides. Each turn becomes a stacked card of the same facts: time and cost on the first line, asker and first token on the second, then the outcome badge, the safety check (with the tag), then "Tools 1" and "Cited CA-4.3". The cell labels appear as inline prefixes.
- The flagged row stays last, full width, same text.
- The trace opens as a full-screen sheet with the same header and X; Escape and the X return focus to the row.
- Scoreboard tables scroll sideways inside their own container (640 px minimum); the page never does.

## Copy not given in the brief

- Trace eyebrow "Turn trace"; close button "Close trace".
- "Offered a card" under the outcome badge for 10:35 and 10:33.
- Tile 3 foot "Small sample" (8 answered questions is under 20).
- Scoreboard: "Three trials per set unless noted."; column headers Set, Result, Lowest trial, Other figures; captions "Hit rate at 5", "Program checks", "Judge pass rate", "In every trial", "Pass rate" (Actions), "Crisis recall", "Passed every check".
- Error body "The sandbox figures didn't load." and reference `c41e8b07`.
- Sandbox indicator "Sandbox resets in 23 h" (24 h in the empty state).
- Traces for the five rows the brief didn't detail: 10:38 (1 tool, $0.022) "Looked up the directory" find_people, 60 ms; 10:36 "Checked time off" list_time_off_requests, 95 ms; 10:35 card row "Checked time off" list_time_off_requests, 90 ms, then "Prepared a confirm card" propose_time_off_decision, 110 ms (card "Approve a request", 4.1 cited, output 620); 10:35 "Checked time off" list_time_off_requests, 70 ms; 10:32 Austin search_handbook, sections 4.3 Sick leave (cited) and 4.1 Paid time off (not cited), output 500. Only the app's real tool names; a Texas employee never gets a California section. Their tokens and timings are consistent with the tiles (median first token 1.6 s, safety p95 980 ms).
- Component card samples: refused turn at 9:14 AM (safety 610 ms); fallback at 10:02 AM (input 12,900 with 10,400 from cache, output 480, cache writes 0, $0.011); failed check_time_off at 9:48 AM (3.0 s; 9,100 with 8,200 from cache, output 0, $0.006).

## Where the data comes from

- **The turn list:** `GET /api/v1/console/turns?cursor=`, 50 rows a page, from
  `ai_console_turns` only (the spec's "The console"). Per row: its own ID, the date and time (UTC),
  the asker's role and location label, the outcome, the refusal category when refused, the safety
  check's category and the injection flag, the tools (`name`, `ok`, `durationMs`), the sections
  retrieved and cited (IDs; the titles come from the published handbook), the card's action, the
  model, effort, and versions, the token counts, the cost, and the three timings. Never a person
  ID, a conversation ID, a name, or any text.
- **A flagged row** carries only `occurred_on`, the token counts, the cost, and the timings. The
  database refuses anything more (the check constraint in ADR 0016). The route returns each day's
  flagged rows after that day's timed rows.
- **The tiles:** `GET /api/v1/console/metrics`, over the sandbox's life, each with its sample size.
  Sandbox spend comes from the ledger (`ai_spend`), so the safety check, case screening, and case
  summaries count. "Cards confirmed by a person" counts `proposal.confirmed` audit events by
  action.
- **The scoreboard:** `apps/web/src/generated/scoreboard.json`, written by `make scoreboard` from
  the committed run boards (ADR 0017). Bundled with the app, never fetched.
- **Times** come as UTC and show in the viewer's location's time zone, with its abbreviation. The
  day heading uses `occurred_on`, the date in the sandbox's HQ time zone.

## Components

- New, in `components/console/`: `ConsoleTile`, `TurnTable` (with `SafetyLabel`, `InjectionTag`), `TracePanel`, `Scoreboard` (with `ScoreboardSetRow`), `console.css` (imported in `styles.css`), `.d.ts`, `.prompt.md`. Card: `components/console/console.card.html` (embedded at the bottom of the DC). Added to `preview/loader.js`.
- `Scoreboard.dc.html`: the same scoreboard as a self-contained Design Component (it was made for screen 14, since dropped). Prop `uid` only keeps ids unique.
- StatusBadge gains `outcome-answered`, `outcome-not-covered`, `outcome-refused`, `outcome-stopped`, `outcome-failed`, `outcome-cap`, `outcome-safety-unavailable`.

## New tokens and icons

- Tokens: none. Uses existing `--confidential-tint`, `--primary-tint`, `--surface-sunken`, `--border-strong`, `--ink-muted`, `--danger` (Failed only), `--panel-width`.
- New icons (Lucide, added to `Icon.jsx`): `shield-check` (safety check), `shield-off` (Safety check unavailable), `circle-stop` (Stopped by the person), `gauge` (Spending cap reached), `search-x` (Said the handbook doesn't cover it). Reused: `message-circle` (Answered), `ban` (Refused), `circle-alert` (Failed), `layout-dashboard` (Console, trace eyebrow), `search`, `calendar`, `users`, `clipboard-check` (tools), `lock` (flagged row), `check`.

## Build note: accessible names (2026-11-01)

**Accessible names start with the visible text** (WCAG 2.5.3, Label in Name, which axe-core
4.14 checks from 2026-11-01). Name a control from its own content, with any extra words as
visually hidden text after what it shows, rather than an `aria-label` that replaces it. This
covers the row button's "10:31 AM, Employee, Oakland, CA, Answered".

## Build decisions (owner, 2026-10-31)

These were decided after the handoff. Where they differ from a screenshot or the notes above, the
build follows this section, and the screenshots are not redrawn.

- **"Card offered" names the card's action, not its variant,** because a console row stores only
  the action (`timeoff.request`, `timeoff.decide`, `timeoff.cancel`): "Time-off request",
  "Time-off decision", or "Time-off cancellation". So trace (b) reads "Time-off request", not
  "Book PTO", and the 10:35 card reads "Time-off decision", not "Approve a request". The same
  words name the rows of the "Cards confirmed by a person" tile.
- **"Refused by the model" means the model service refused the turn** (the API's `refusal` stop,
  with its category only). A question the assistant declines, such as Leo's home address or the
  injection attempt, is "Answered", because the assistant answered it by declining.
- **Tool labels are neutral, not "your":** time-off reads (`get_time_off_balance`,
  `list_time_off_requests`, `check_time_off`) are "Checked time off", the three proposal tools are
  "Prepared a confirm card", `find_people` is "Looked up the directory", `search_handbook` is
  "Searched the handbook", `get_my_profile` is "Read the profile", the case tools are "Checked
  cases", and any other tool is "Used a tool". The tool's own name always shows beside the label.
- **Flagged rows sit after their day's timed rows,** in the API's order as well as on screen, so
  a flagged row's position never hints at its time. The day heading's count includes them.
- **"Small sample"** shows on every tile whose sample is under 20: turns for the turn-based tiles,
  answered questions for the cost tile.
- **Sample data:** the turns, tiles, and traces are the tour's sample day; the five traces Claude
  Design wrote are consistent with them and with the token prices. The scoreboard's figures are the
  committed runs of October 27, 29, and 30, and the history's rows are whichever full-run boards
  Stage 2 commits. Fairness stays a placeholder until Stage 3's run.
- **Empty table cells** show "–" with a visually hidden "None", as Claude Design drew them.

## Acceptance criteria

- [ ] Matches the screenshots at 1440 px, within the component library's spacing tokens
- [ ] Usable at 390 px: tiles one per row, the turn list as stacked cards, the trace as a
      full-screen sheet, the scoreboard's tables scrolling inside their own container, and the
      page never scrolling sideways
- [ ] Only HR reaches `/console`; anyone else gets the same 404 as any page they may not open
- [ ] No name, avatar, initials, question or answer text, tool input, or refusal explanation
      appears anywhere on the page, in the trace, or in the routes' responses
- [ ] A flagged row shows only its date, tokens, cost, and timings, with "Flagged by the safety
      check. Details are hidden to protect the person."; it is not focusable, opens no trace, and
      sits after its day's timed rows
- [ ] Every tile shows its sample size, and "Small sample" under 20; a figure above its target is
      in normal ink with the target stated in words
- [ ] A row opens the trace without a new request; focus moves to the panel heading, Escape or X
      closes it and returns focus to the row, and another row swaps the content
- [ ] The trace shows the tools in order with durations and OK or Failed, the sections retrieved
      with "Cited" or "Not cited", the card offered by its action, the model line, the token
      breakdown with cache reads, the cost with "Includes the safety check", and the three timings
- [ ] The outcome badges and the "Possible prompt injection" tag carry their meaning in words; red
      appears only on a Failed outcome or a failed tool
- [ ] The empty state shows "No questions yet in this sandbox. Ask something, or take the tour."
      with "Ask a question" and "Take the tour"; the loading and error states keep the scoreboard
- [ ] The scoreboard is one component: each set's headline
      with its lowest trial, the history of full runs, and both plain lines, always visible
- [ ] No link to code, a repository, an ADR, or any document
- [ ] Every interactive element is reachable by keyboard and has a visible focus ring
- [ ] Text contrast meets WCAG 2.2 AA; axe reports no violations
