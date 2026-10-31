# Screen 12 · HR case queue and case detail

- Routes: `/cases` (queue) and `/cases/:id` (detail), as Dana Whitfield, HR Business Partner, Human Resources, Denver HQ.
- Source: `HR Cases.dc.html` (one frame per state, then the component card). Components: `components/cases/` (CaseQueueTable, CaseSummaryBlock, CaseWordsReveal, CaseTimeline, `hrcases.css`). Both are in `docs/design/system/`.
- Today is Monday, October 26, 2026 (frames 4 and 12 are Tuesday, October 27). Every time is in Dana's zone, Mountain time, shown as MDT.
- Every frame is live: the filter works, queue rows link to their detail frames, "Show/Hide … words" records reads in the timeline, and "Start review" and "Close case" open their dialogs and change the status.

## What the screens do and don't do

- The queue shows facts only: person, category, sent date, reply line, status. Never any part of a case's words or summary.
- The detail shows the AI summary, labeled as the AI's, and keeps the person's words hidden until Dana reveals them. Every reveal is recorded in the timeline. Hiding isn't recorded.
- The status can't change until Dana has read the person's words at least once on that case. Each view starts with the words hidden again.
- Nothing ranks, scores, prioritizes, or recommends. The only order is: new cases by reply date (soonest first), then the rest oldest first. No column sorting.
- Overdue replies ("Reply was due Mon, Oct 26") and crisis routing are facts in neutral ink and muted type. No red, no warning color, no alert style.
- Confidential treatment from screen 11: the lock (in primary) on the queue heading, the case heading, and the words block; `--confidential-tint` behind the words and the own-case notice.
- No chat or AI composer on `/cases` or `/cases/:id`.

## States

| File | State |
| --- | --- |
| desktop-queue | Open filter: Chloe, Keisha, Priya (new, by reply date), then Aaliyah (in review). "Reply due today" on Chloe. Nav: Cases "3 new" |
| desktop-queue-closed | Closed filter: Lucia Gutierrez, "Closed Fri, Oct 16" |
| desktop-queue-empty | New filter, nothing in it: "No new cases. A case appears here as soon as someone sends one." The nav count is gone at zero |
| desktop-queue-facts | Tuesday, October 27: Chloe "Reply was due Mon, Oct 26", Keisha "Reply due today", Megan added with the crisis fact under the category; "4 new" |
| desktop-detail | Priya's case: header, read-recording line, person card, AI summary, words hidden, status actions disabled with the read-first line, timeline of 3 |
| desktop-detail-revealed | Words shown on the tint, "Hide Priya's words", timeline gains "Dana Whitfield read Priya's words · 10:53 AM MDT", actions enabled |
| desktop-dialog-review | "Start review of this case?" · "Priya will see "HR is reviewing" in My cases." · Cancel (focused), Start review |
| desktop-dialog-close | "Close this case?" · "Priya will see "HR has finished its review". A closed case can't be reopened in Open Door." · Cancel (focused), Close case (standard primary) |
| desktop-detail-in-review | Aaliyah's case: In review badge, words hidden, only "Close case", enabled because the words were read on Oct 20; timeline of 6 |
| desktop-summary-pending | "Writing the summary…" with a static three-bar skeleton; timeline has only "Sent by Priya Raman" |
| desktop-summary-failed | "No AI summary. Read the person's words below." with "Try again" |
| desktop-summary-crisis | Megan's case: "No AI summary for this case. The safety check routed it to crisis text." and the same fact under the header |
| desktop-own-case | Dana's own pay concern: header and dates, then "You opened this case, so you can't act on it or read it here." No person card, summary, words, actions, or timeline |
| desktop-home-hr | Dana's home: rail adds "3 new cases" and "1 reply due today" (both to Cases) above "Sep 12 Handbook updated" |
| desktop-nav-hr | Ask, Time off, Directory, Handbook, Cases "3 new", Console |

## Status badges (new StatusBadge values)

- New: a small filled cinnamon dot (`--marker`), the same "waiting" signal used for pending requests
- In review: primary file-search, matching the employee's "HR is reviewing"
- Closed: ink circle-check, matching the employee's "HR has finished its review". It's neutral, not a success.
- The label always carries the meaning. Color never stands alone.

## Status changes

- New case: "Start review" (primary) and "Close case" (secondary). In review: "Close case" only (secondary). Closed: no actions, and the line "This case is closed."
- Locked (words not yet read): both buttons are `aria-disabled` and stay focusable, styled as disabled, with `aria-describedby` pointing to "Read Priya's words before changing the status."
- Confirming "Start review" sets the badge to In review, changes the header line to "In review since Mon, Oct 26", and adds "Dana Whitfield started the review" to the timeline.
- Confirming "Close case" sets Closed, changes the header line to "Closed Mon, Oct 26", adds "Dana Whitfield closed the case", hides the words, and removes the actions.
- The employee's My cases badge follows: New → "Sent to HR", In review → "HR is reviewing", Closed → "HR has finished its review".

## Layout (1440 px)

- Sidebar 248 px, sheet as elsewhere, no right rail on `/cases` pages.
- Queue: 40/48 px sheet padding, 1080 px content. Filter row is "Show" plus the segmented radiogroup. Table header 40 px, rows 64 px minimum (taller when the crisis fact or a long title wraps). Columns 2.5fr / 2fr / 1fr / 1.6fr / 120 px / chevron, 24 px gaps.
- Detail: back link, header (lock, h1, badge; dates line; read-recording line), then two columns: main (person card, AI summary, words, actions) and a 360 px timeline column. 40 px gutter.
- Dialog: 480 px, centered on a scrim that covers the whole viewport, sidebar included.

## Phone (390 px)

- Queue: the header row hides. Each case is a stacked link: the person (avatar, name, title · location), then the category (and the crisis fact), then the reply line on the left and the badge on the right. The sent date and chevron drop. The filter scrolls sideways inside its own control if it doesn't fit; the page never does.
- Detail stacks in reading order: header, person card, AI summary, words, status actions (full-width buttons, primary first), timeline.
- Dialogs are full width with 16 px margins; buttons stack full width, the primary on top, Cancel under it. Focus still starts on Cancel.

## Keyboard and focus

- Queue: tab order is the back/sidebar, then the filter (one tab stop; arrow keys move and select), then each row link in reading order. Each row's accessible name reads the facts in order: "Priya Raman, Visual Merchandiser, Oakland store. Harassment or discrimination. Sent Mon, Oct 26. Reply due Wed, Oct 28. New."
- Detail: the back link "Cases", the email link, the summary's "Try again" when shown, "Show Priya's words", then the status actions.
- "Show Priya's words" is a disclosure button (`aria-expanded`, `aria-controls` on the words container). Focus stays on it. The new timeline row is announced through a polite live region ("Added to the timeline: Dana Whitfield read Priya's words").
- Disabled status actions are `aria-disabled`, still focusable, and described by the read-first line.
- Dialogs are `role="alertdialog"` and `aria-modal`, labeled by the title and described by the body. Focus starts on Cancel and is trapped between Cancel and the primary. Escape and Cancel close the dialog and return focus to the action that opened it. Confirming "Start review" moves focus to "Close case"; confirming "Close case" moves focus to the heading.
- The summary block is a `section` labeled "AI summary"; it's `aria-busy` while pending, and its "Writing the summary…" line is `role="status"`.

## Contrast (WCAG 2.x)

- Ink on white 16.4:1; ink-muted (sub-lines, sent date, crisis fact, timeline times) 6.1:1 on white, 5.7:1 on sunken
- Words on confidential tint: ink 15.4:1; lock in primary 10.2:1
- Cinnamon dot in the New badge: 3.5:1, beside the word "New"
- Selected filter: ink on primary-tint 13.0:1, check in primary 9.6:1
- Disabled status actions (exempt): #87939A on #E7EBED, with the read-first line in ink-muted 6.1:1

## Copy not given in the brief

- Filter label "Show". Empty texts for the other filters: "No open cases.", "No cases in review.", "No closed cases.", "No cases yet."
- Person card labels "Department", "Location", "Email"
- Words heading "Priya's words" (the person's first name), and the eye / eye-off icons on the reveal button
- Timeline heading "Timeline"; events "Dana Whitfield started the review", "Dana Whitfield closed the case", "The safety check routed it to crisis text"
- "This case is closed." after closing
- Status group's accessible name "Change the status"
- Aaliyah's words: "The top step of the stockroom ladder is cracked. I was told to keep using it until the new ladder arrives."
- Megan's words (hidden by default): "Nights have been really hard lately and I don't know who else to tell. I'm not sure I can keep doing this."
- Megan's details: Warehouse Operations, megan.coleman@juniperrow.example, sent Tue, Oct 27, 6:12 AM MDT
- Dana's own case: sent Fri, Oct 23, 2:15 PM MDT, reply due Tue, Oct 27. It doesn't appear in Dana's queue; another HR partner handles it.
- Home: Dana's "104 hours PTO available" and "0 requests pending"; "Try asking" questions for Dana.

## Where the data comes from

- **The queue:** `GET /api/v1/cases?status=…`: each row's ID, the person's name, title, and
  location, the category, the sent date, the reply-by date, the status and its date, and the
  safety check's crisis fact. The server orders it (new cases by reply-by, then the rest oldest
  first). No text of any kind.
- **The nav badge and the home card:** `GET /api/v1/cases/counts` (`{ new, replyDue }`).
- **The detail:** `GET /api/v1/cases/{id}`: the directory card (department, location, work
  email), status and dates, the screening, the summary's state, and the timeline. No text, and not
  an audited read. For HR's own case, the metadata only.
- **The summary:** `GET /api/v1/cases/{id}/summary`, an audited read (`no-store`), fetched once per
  view and held in the page's component state.
- **The words:** `GET /api/v1/cases/{id}/text`, an audited read (`no-store`), fetched on "Show …
  words" and held only in component state, never in the query cache.
- **Changing the status:** `POST /api/v1/cases/{id}/status` with `{ to }`; refused with
  `words-not-read` until this HR person has read the words on this case. **Retrying the summary:**
  `POST /api/v1/cases/{id}/summary`.
- **Times** come as UTC and show in the viewer's location's time zone, with its abbreviation.

## Components

- New, under `components/cases/`: `CaseQueueTable`, `CaseSummaryBlock`, `CaseWordsReveal`, `CaseTimeline`, with `hrcases.css` (imported in `styles.css`), `.d.ts`, and `.prompt.md`. Library card: `components/cases/hrcases.card.html` (embedded at the bottom of the DC).
- StatusBadge gains `case-new`, `case-in-review`, `case-closed`. New icons: `eye-off`, `shield`, `history`.
- Reused: the directory table's density and row links, DetailList rows, Avatar (initials), the SegmentedControl pattern for the filter, the 480 px DecisionDialog, NavItem with a count, GlanceList, the AI tag, and screen 11's lock and tint.

## Build decisions (owner, 2026-10-26)

These were decided after the handoff. Where they differ from a screenshot or the notes above, the
build follows this section, and the screenshots are not redrawn.

- **HR's own case appears in the queue, read-only,** linking to the own-case view in
  `desktop-own-case`, as the spec says. The notes above leave it out on the assumption that
  another HR partner handles it, but Dana is the only HR person in the seed, and HR has no
  My cases page.
- **The close dialog's quote takes the period inside:** "{First name} will see "HR has finished
  its review." A closed case can't be reopened in Open Door."
- **Megan Coleman's department is Distribution,** as in the seed. Her case is a sample state the
  seed doesn't have.
- **Dana's home:** the "Try asking" list follows screen 02's, with "Which cases need a reply soon?"
  in place of "Summarize the newest case". The figures come from the API; "104 hours" is a sample.
- **The timeline also shows a failed summary** ("AI summary couldn't be written"). "The safety
  check routed it to crisis text" comes from the case's screening, not a stored event.
- **The status actions unlock once this HR person has read the words on this case,** on any
  earlier view, as the server enforces.
- **The summary and the words are fetched once per view,** outside the query cache, so switching
  windows adds no timeline row.

## Acceptance criteria

- [ ] Every state matches its screenshot at 1440 px within the spacing tokens, with the build
      decisions applied
- [ ] Usable at 390 px as "Phone (390 px)" describes; nothing scrolls sideways
- [ ] The queue never shows any part of a case's words or summary; its order and filters are as
      the notes say, with each filter's empty text
- [ ] An overdue reply and the crisis fact use neutral styling, never red or a warning style
- [ ] The Cases badge and the home card's figures come from `GET /cases/counts`; the badge hides
      at zero
- [ ] The summary is plain text under the "AI summary" label with its time and model; its pending,
      failed, and crisis states match their frames, and "Try again" retries
- [ ] Every view starts with the words hidden; showing them adds one timeline row, announced
      politely; hiding adds nothing; a window refocus adds nothing
- [ ] The status actions are `aria-disabled`, focusable, and described by the read-first line until
      the words are read; the server refuses an early change too
- [ ] The dialogs are alert dialogs that start on Cancel, close on Escape, and return focus;
      confirming updates the badge, the header line, and the timeline
- [ ] HR's own case shows its metadata only, in the queue and the detail, with no actions
- [ ] Anyone who isn't HR gets the not-found page at `/cases` and `/cases/:id`, and no Cases item
- [ ] No pronouns in any copy; axe reports no violations in any state
