# Screen 08 · Time off

- Route: `/time-off`, in the app shell's content sheet, for every persona. Nav item "Time off" (calendar) is current.
- Source: `Time Off.dc.html` (one frame per state, plus the component card at the bottom). Components: `components/timeoff/`. Standalone export: `Time Off.html` in this folder.
- Persona: Priya Raman, salaried, Oakland store (California), Monday to Friday. Today is Tuesday, October 20, 2026.
- `desktop-default` is live: open the form, switch type, pick days by mouse or keyboard, submit, cancel the December 23 row. Every figure in every frame comes from one small engine in the file (schedule, holidays, balances, requests), so the frames agree with one another.

## Right rail: not used

The page uses the full sheet. Three reasons:
- The rail's first figure is the PTO balance, which this page already leads with in a larger, fuller form.
- The rail's sample "1 request pending" disagreed with this record (waiting for approval: 0). That was sample data in an earlier screen; see "Data to reconcile".
- The right side is where the request form opens, so the balances stay in view while Priya picks dates.

## How the figures are worked out

- PTO available = earned to date − taken − booked − waiting for approval.
- Taken is approved PTO that has ended. Booked is approved PTO still ahead. Waiting is PTO not yet decided.
- Sick leave available = granted − used − booked. Used is recorded sick time on days up to today. Booked is recorded sick time after today, so 3 hours recorded for October 22 are Booked, not Used. (Changed in the build decisions: today counts as used, and as taken for PTO, as the Phase 5 spec says.)
- The 180-hour PTO limit applies to hours saved before booked time comes off. At the limit, with December 23 still booked, Priya has 212 earned − 32 taken − 8 booked = 172 hours available, and accrual is paused.
- With no requests, nothing is taken or booked: 132 hours PTO (16.5 days) and 40 hours sick leave.
- Canceling December 23 returns its 8 hours, so the canceled frame shows 100 hours (12.5 days).

## States

| File | State |
| --- | --- |
| desktop-default.png | Balances, schedule line, Request time off, My requests |
| desktop-default-full.png | The same page at full height (1440 × 1357), every row visible, including the August 28 denial and Marcus Bell's note |
| desktop-ceiling.png | PTO at the limit: 172 hours, the notice, the full breakdown, "Next: paused at the 180-hour limit" |
| desktop-form-one-day.png | PTO, Friday, October 30, full day |
| desktop-form-half-day.png | PTO, Friday, October 30, half day |
| desktop-form-weekend.png | PTO, October 30 to November 2; Saturday and Sunday skipped |
| desktop-form-holiday.png | PTO, November 25 to 27; Thanksgiving skipped; sources §4.1 and §4.2 |
| desktop-form-sick-hours.png | Sick time, Thursday, October 22, 3 hours; source CA-4.3 |
| desktop-form-short-notice.png | PTO, November 2 to 5, amber warning; button still enabled |
| desktop-form-not-enough.png | PTO, November 30 to December 18 (15 days); refusal, button disabled |
| desktop-form-overlap.png | PTO, Wednesday, December 23 marked "Already booked" with the error icon; refusal, button disabled |
| desktop-form-submitting.png | Button loading state, fields locked |
| desktop-submitted.png | Form closed, toast, new row "Waiting for approval"; PTO card counts it (84 hours) |
| desktop-submitted-sick.png | Sick time recorded at once; toast "Recorded."; sick card Used 8, Booked 3, 29 available |
| desktop-cancel-confirm.png | One confirm step; the scrim covers the whole window, sidebar included |
| desktop-canceled.png | Row moved to Past as Canceled; Upcoming empty; 100 hours available |
| desktop-empty.png | No requests: 132 hours PTO, 40 hours sick leave |
| desktop-loading.png | Static skeletons in the cards and rows |
| desktop-error.png | Global error pattern with reference and Retry |
| desktop-date-picker-open.png | PTO, October: past days struck through and disabled; focus on October 30 |
| desktop-date-picker-sick.png | Sick time, October: the last 30 days are selectable; focus on October 15 |
| desktop-date-picker-range.png | November 25 to 27 selected; Thanksgiving's name showing |

## Layout (1440 px)

- Header: "Time off" (h1) and the sandbox pill.
- Balance cards: two equal columns (`auto-fit, minmax(300px, 1fr)`). Each card has its label, a source chip under it, the figure (40 px, tabular), a ledger that adds up to the figure, and footer lines. At the limit, the notice sits between the figure and the ledger.
- Schedule line on the left, "Request time off" on the right, on one row.
- My requests: "Upcoming" (soonest first), then "Past" (newest first). Row: dates over "type · amount", the status badge with who decided under it, and Cancel where allowed. A manager's note on a denial sits under the row. Rows tint on hover and while anything inside has focus.
- Request form: a side panel `var(--panel-width)` (420 px) wide, the token the passage panel now uses too. It's docked at the right of the sheet, isn't modal, and the page reflows beside it. Fixed header (title, close) and footer (note, buttons); the body scrolls.
- Dates field: short form so a range fits on one line ("Wed, Nov 25 to Fri, Nov 27"). Its accessible name is the full form. "What this uses" keeps full weekday and month names.
- Date picker: opens inline under the Dates field and pushes the rest of the form down, so it never covers the preview.
- "What this uses": counted days (check), skipped days (calendar-minus icon), days already booked (error icon, "Already booked"), the total and what's left, then "Sources" with chips for the rules used: §4.1 for PTO, plus §4.2 when a holiday is skipped; CA-4.3 for Priya's sick time.
- Cancel confirm: a centered alert dialog. The scrim covers the whole window, sidebar included.
- Toast: bottom right of the sheet.

## Phone (390 px)

- The sidebar collapses behind the menu button in the top bar, as on other screens.
- Header: "Time off" and the sandbox pill stay on one row; the pill can drop under the title if needed.
- Balance cards stack, PTO first, full width with 16 px side padding. The ledger keeps label left and value right.
- The schedule line wraps above "Request time off", which becomes full width.
- Request rows wrap: dates and "type · amount" on top, with Cancel at top right; the badge and "Approved by Marcus Bell" go under the dates. The denial note goes full width below. Nothing scrolls sideways.
- The request form opens as a full-width, full-height sheet from the bottom. On a phone it's modal: focus stays inside, the page behind is inert, and the header and footer stay fixed while the body scrolls. Swiping down or Close dismisses it.
- The date picker fills the sheet's width (seven columns of at least 44 px). The legend wraps to two or three lines. The Dates field's short form fits on one line at this width.
- Source chips in "What this uses" wrap; a long label truncates with an ellipsis and keeps its full accessible name.
- "How much" options sit side by side if they fit, otherwise they stack.
- The footer's buttons share the width: primary first, Cancel second.
- The cancel dialog is full width with 16 px margins over a full-screen scrim; its buttons stack, "Cancel request" on top.
- The toast spans the width above the safe area.

## Keyboard and focus

- Tab order: sidebar, persona switcher, source chips, Handbook §3.1, Request time off, then each row's Cancel. When the form is open, the panel comes after the page.
- "Request time off" has `aria-expanded` and `aria-controls`. Opening the form moves focus to its title (h2, `tabindex="-1"`). Close or Cancel returns focus to "Request time off".
- Type and How much are radiogroups with one tab stop each. Arrow keys move and select.
- The Dates field is a button with `aria-expanded`. In the picker, the grid has one tab stop (roving tabindex). Arrow keys move by day, Page Up and Page Down by month (same date, clamped), Home and End to the week's ends. Enter or Space selects. Escape or Done closes the picker and returns focus to the field.
- Each day's accessible name is its date plus any marks: "Thursday, November 26, Thanksgiving, company holiday", "Saturday, October 31, not on your schedule", "Tuesday, October 20, today", "Monday, October 19, not available". Disabled days stay focusable (`aria-disabled`) so arrow keys can pass over them.
- Holidays show their name in a tooltip on hover and on keyboard focus.
- The picker's hint line is `role="status"`. The preview is `aria-live="polite"`. The warning is `role="status"`. Refusals and the hours error are `role="alert"`. In the preview, the hidden prefixes "Counted:", "Skipped:", and "Can't be counted:" go before each line.
- While submitting, the button has `aria-busy` and `aria-disabled`, and the fields are disabled. After submit, focus returns to "Request time off" and the toast (`role="status"`) is announced.
- Cancel buttons are named for their request: "Cancel PTO on Wednesday, December 23". The confirm dialog is `role="alertdialog"`, modal, with focus on "Keep it" and focus kept inside. Escape or "Keep it" returns focus to the row's Cancel. After "Cancel request", focus moves to the "My requests" heading, since the row has moved.

## Date picker marks

- Not on the schedule: shaded fill, muted number; still selectable, since those days are skipped.
- Company holiday: a small dot under the number; the name on hover and focus.
- Today: a thin ring and a 600 number.
- Disabled: the number struck through in disabled gray, with no fill even on weekends, so a past day never reads like a future one. The legend explains it: "Past days can't be picked for PTO", or for sick time "Sick time can go back 30 days, to September 20".
- Selected: primary fill, white number. In range: primary tint band behind the days, skipped days included.

## Contrast (WCAG 2.x)

Warning message
- Ink text #14212A on warning tint #FCF4E8: 15.0:1
- Warning icon #8A5300 on warning tint: 5.8:1
- Warning border #E6C79A: 1.6:1 on white (decorative; the icon and words carry the meaning)

Refusal message
- Ink text #14212A on danger tint #FDEFEE: 14.7:1
- Danger icon #B42318 on danger tint: 5.9:1
- Danger border #EFBDB8: 1.7:1 on white (decorative)

Other new pairs
- "Waiting for approval" clock, marker #C27544 on white: 3.6:1 (icon, needs 3:1)
- "Already booked" error icon, danger #B42318 on white: 6.6:1
- Skipped day number, ink-muted #55646E on surface-hover #F0F3F5: 5.5:1
- In-range day, ink on primary tint #ECE2F0: 13.0:1
- Selected day, white on primary #59256A: 11.1:1
- Disabled day, #87939A on white: 3.2:1 (exempt as disabled; the strike-through and the legend also say it)

## Copy not given in the brief

- Card labels: "PTO available", "Sick leave available this year"
- Sick ledger rows: "Granted on January 1", "Used", "Booked"
- Form title: "Request time off". Field labels: "Type", "Dates", "How much", "Hours"
- Sick time's second option: "Some hours". Stepper hint: "1 to 8 hours". Error: "Enter a whole number from 1 to 8."
- Dates placeholder: "Pick a day or a range"
- Picker: "Previous month", "Next month", "Done"; legend "Not on your schedule", "Company holiday", "Today", "Sick time can go back 30 days, to September 20"; hints "Pick a day, or a first and last day.", "Now pick the last day. For one day, choose Done.", "Selected: …"
- Preview: "What this uses", "Sources", "Already booked". Empty: "Pick dates to see what this uses."
- Skipped, more than two weekend days: "Saturdays and Sundays in these dates aren't on your schedule"
- No counted days: "None of these days are on your schedule, so there's nothing to request."
- Sick refusal: "You have 32 hours of sick leave left this year. This request needs 40 hours."
- Footer notes: "Marcus Bell, your manager, reviews PTO requests." and "Sick time is recorded right away, with no approval."
- Loading button labels: "Requesting…", "Recording…"
- Canceled toast: "Canceled. 8 hours went back to your balance."
- Empty Upcoming: "No upcoming time off."
- Error page body: "Your time off didn't load. Try again in a moment. If it keeps happening, this reference helps us find it:"
- Denial note label: "Marcus Bell's note"
- "left" lines read "left after this" in every PTO state ("88 hours (11 days) left after this", "76 hours (9.5 days) left after this"). The figures are as given.

## Data the API needs to supply

- The person's schedule (workdays and hours per day) and the company holiday calendar for their location, with names. Denver HQ also closes the day after Thanksgiving; Oakland doesn't, so November 27 counts for Priya.
- Who manages the person (for the footer note and the toast).
- For each balance: earned or granted, taken or used, booked, waiting, the cap, whether accrual is paused, the next accrual date and amount, and the handbook section that sets it.
- For each rule the preview applies (accrual, holidays, notice, sick leave), the handbook section, so the source chips come from data.
- The notice rule (more than 3 days, 2 weeks ahead) and the sick look-back window (30 days), so the form and the assistant apply the same rules.
- Who canceled a request and when, if Past should say "Canceled by you" (not shown now).

## Data to reconcile

- Resolved: the home and conversation rails' "1 request pending" for Priya was sample data in screens designed before Phase 5. The build reads every rail figure from `GET /time-off/summary`, so the rail and this page always agree. No design change.

## Components

In `components/timeoff/`: StatusBadge, SegmentedControl, ChoiceGroup, HoursStepper, DateField, DatePicker (with CalendarDay, longDate, shortDate), BalanceCard (and `.od-source-chip`), RequestRow and RequestGroup, PreviewBlock, FormMessage. Button has a `loading` prop. Icon added plus, chevron-left, chevron-up, circle-x, ban, calendar-minus. Tokens added `--warning-tint`, `--warning-border`, `--danger-tint`, `--danger-border`, `--scrim`, and `--panel-width` (now also used by the passage panel's containers in Handbook and Conversation).

The card `components/timeoff/timeoff.card.html` (embedded at the bottom of `Time Off.dc.html`) shows every state: each status badge; the two-option control and the day choice (default, hover, focus, selected, active, disabled); the hours stepper (default, hover, focus, at 1, at 8, error, disabled); the date field; each day-cell state (default, hover, focus, active, selected, range start, in range, range end, skipped, skipped in range, holiday, today, disabled, disabled weekend); full pickers for PTO and sick time; balance cards; request rows (default, hover, focus); preview blocks; the warning and refusal messages; and the form buttons.

The source chip here is a link to the handbook section. When the conversation parts are extracted, the conversation's source chip and this one should become one component.

## Build decisions (owner, 2026-10-20)

Decided in review. Where they differ from a screenshot, the build follows this section, and the
screenshot is not redrawn.

- **Today counts as taken (PTO) and used (sick leave),** as the Phase 5 spec's engine rules say.
  Booked is time after today.
- **A day cell's hover is a light fill.** In the specimens, "hover" and "today" are both thin
  outlines; the build keeps the outline for today and the focus ring, and uses a fill for hover.
- **The overlap preview shows a total only when every day can be counted.** With a day marked
  "Already booked", the preview lists the days and the refusal, and leaves out "8 hours (1 day)".
- **Every figure and label comes from the API,** made by the engine's shared label function
  ("90 hours (11.25 days)"), never computed in the browser. The form's preview calls
  `POST /time-off/check` as the dates change.
- **The date picker's marks come from `GET /time-off/calendar`:** the person's scheduled weekdays,
  the location's holidays with their names, and the earliest day each type allows (today for PTO,
  30 days back for sick time).
- **No pronouns anywhere** (see screen 09's "Wording"). A line names the person or the page.

## Where the data comes from

| The design needs | The API gives it |
|---|---|
| Balances, ledger rows, the cap, "Next", the source section | `GET /time-off/balances` |
| My requests, with who decided and the note | `GET /time-off/requests?scope=mine` |
| The schedule, holidays with names, earliest days | `GET /time-off/calendar` |
| The live preview, warnings, refusals, sources | `POST /time-off/check` |
| The manager named in the footer and the toast | `GET /time-off/summary` (the approver) |
| Submit, cancel | `POST /time-off/requests`, `POST /time-off/requests/{id}/cancel` |

"Canceled by you" in Past is not shown, so the API doesn't need to say who canceled.

## Acceptance criteria

- [ ] Every state matches its screenshot at 1440 px within the spacing tokens, with the build
      decisions applied
- [ ] Usable at 390 px as "Phone (390 px)" describes: cards stack, the form is a modal sheet,
      the picker fills the width, nothing scrolls sideways
- [ ] Every figure equals the API's label for it; nothing on the page computes hours or days
- [ ] The PTO and sick cards' ledgers add up to their figures in every state, including the
      ceiling and empty states
- [ ] The request form is a 420 px (`--panel-width`) side panel that isn't modal on desktop;
      opening it moves focus to its title, and Close or Cancel returns focus to "Request time off"
- [ ] Type and How much are radiogroups with one tab stop each; the hours stepper accepts 1 to 8
      and shows "Enter a whole number from 1 to 8." otherwise
- [ ] The date picker works by keyboard alone as "Keyboard and focus" describes, and every day's
      accessible name carries its marks (holiday name, "not on your schedule", "today", "not
      available")
- [ ] Past days can't be picked for PTO; sick time goes back exactly 30 days
- [ ] "What this uses" lists counted days, skipped days with their reason, and an already-booked
      day with the error icon, and ends with the source chips the API names
- [ ] The short-notice warning is amber with its icon and never disables the button; a refusal
      disables it and is `role="alert"`
- [ ] Submitting shows "Requesting…" or "Recording…" with `aria-busy`; afterward the toast is
      announced and focus returns to "Request time off"
- [ ] Cancel opens the alert dialog with focus on "Keep it"; the scrim covers the whole window;
      after "Cancel request", focus moves to the "My requests" heading
- [ ] Status badges pair an icon with their word; a denial shows the manager's note under its row
- [ ] Text and icon contrast meet WCAG 2.2 AA as listed; axe reports no violations in any state
