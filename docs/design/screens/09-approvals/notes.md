# Screen 09 · Approvals

- Route: `/approvals`, managers only, in the app shell's content sheet. Nav item "Approvals" (clipboard-check, as the NavItem docs already set) with a count badge, after Handbook.
- Source: `Approvals.dc.html` (one frame per state, plus the component card at the bottom). New components: `components/approvals/` and `components/core/Avatar.jsx`. Standalone export: `Approvals.html` in this folder.
- Persona: Marcus Bell, Store Manager, Oakland store. Today is Tuesday, October 20, 2026.
- `desktop-default` is live. You can approve or deny either request, type a note, go back, or retry from the error frame. The nav count, the lists, the toast, and focus all update.
- Full width, no right rail.

## How the figures are worked out

All of this comes from one small engine in the file, so the frames agree with one another.
- Available after this is the person's available PTO as it stands. A waiting request already counts against it (screen 08's "Waiting for approval" line), so the figure already reflects the request: Zara 62 hours (7.75 days), Priya 84 hours (10.5 days), the same 84 Priya sees on screen 08 after sending October 30. Approving doesn't change it. Days are hours ÷ 8, shown to at most two decimals.
- Team coverage: for each waiting request, the engine looks at Marcus's other direct reports. It lists anyone with approved or recorded time off on the request's scheduled workdays, one line per person: "Also off: name, day(s) · type". If no one is off: "No one else on your team is off that day." (or "those days" for a range). Requests that are only waiting don't count as off.
- Waiting for you: requests waiting for Marcus, oldest sent first. The count in the heading and in the nav is the number still waiting.
- Coming up on your team: approved PTO and recorded sick time that ends today or later and starts within 30 days (through November 19), soonest first.
- Recent decisions: requests Marcus approved or denied in the last 90 days (since July 22), newest decision first. A decision made today reads "Approved today" or "Denied today".
- After approving Zara: Zara's request is Approved, dated today. It moves to the top of Recent decisions, and November 9 to 10 joins Coming up between Malik and Vikram. The count drops to 1. On Zara's Time off page the 16 hours move from "Waiting for approval" to "Booked", and the available figure doesn't change.
- After denying: the request is Denied, dated today. It moves to the top of Recent decisions with "Your note", and nothing is added to Coming up. On Zara's Time off page the 16 hours go back to available.
- Sick time never appears as something to decide.

## States

| File | State |
| --- | --- |
| desktop-default.png | Two waiting requests, then the top of Coming up |
| desktop-default-full.png | Full height (1440 × 1507): both cards, Coming up, and every recent decision, including the August 28 denial with "Your note" |
| desktop-approve-confirm.png | Approve dialog, focus on "Go back" |
| desktop-deny-confirm.png | Deny dialog with the typed note, focus in the note, "77 of 300" |
| desktop-deciding.png | "Approving…" with a spinner; Go back disabled |
| desktop-approved.png | Toast, nav count 1, Zara in Coming up, focus on Priya's Approve |
| desktop-denied.png | Toast with the note wording, Zara at the top of Recent decisions with "Your note" |
| desktop-conflict.png | Zara's card muted, Canceled badge, no actions, "Zara canceled this request." (role="alert"); count 1; focus on Priya's Approve |
| desktop-empty.png | "Nothing is waiting for you…", no nav count; Coming up and Recent decisions below |
| desktop-loading.png | Static skeletons for two cards and the rows |
| desktop-error.png | Global error pattern with reference and Retry |
| desktop-nav-manager.png | Approvals current with 2 waiting; hover; keyboard focus with 1 waiting; nothing waiting; Priya's employee nav, which has no Approvals item |
| desktop-home-manager.png | Marcus's home: 72 hours PTO available, 0 requests pending, 2 approvals waiting (cinnamon marker), Sep 12 Handbook updated |

## Layout (1440 px)

- Header: "Approvals" (h1) and the sandbox pill, as on screen 08. Content max width 1040 px.
- "Waiting for you" (h2) with a neutral count chip, and one line under it: who the requests come from, the order, and why sick time isn't here.
- Approval card (one per request, 16 px apart):
  - Head: avatar, name, and title on the left; "Sent October 17" on the right. In a conflict, a Canceled badge takes the place of the sent date.
  - Body, under a hairline: the dates (17 px, 600), "PTO · amount", "available after this", then Team coverage with a people icon.
  - Approve and Deny sit at the bottom right, Approve first. They carry equal weight: both secondary, the same size, neither filled.
  - Coverage is plain ink text. No colors, icons, or wording that would suggest a problem.
- Coming up and Recent decisions use the screen 08 request row with a person column added: avatar and name, then dates over "type · amount", then the status badge with the decision line. Your note sits under the dates. These rows have no actions.
- Dialogs: the screen 08 alert dialog, 480 px, centered on the full-window scrim (sidebar included). Buttons go "Go back" first, then the confirm button on the right. The confirm is the standard primary button in both dialogs: "Approve" or "Deny".
- Toast: bottom right of the sheet, success icon, dismissible, clears after 6 seconds in the live frame.

## Phone (390 px)

- The sidebar collapses behind the menu button, as on other screens. The Approvals count shows on the menu button too ("Menu, 2 approvals waiting"), so it isn't hidden.
- Header: "Approvals" and the sandbox pill on one row; the pill drops under the title if needed.
- Each waiting request is a stacked card with 16 px padding:
  - person (avatar, name, title)
  - "Sent October 17" under the title
  - dates, wrapping as needed
  - "PTO · amount", then "available after this"
  - Team coverage, wrapping under them
  - Approve and Deny side by side at the bottom, each half the width
- Coming up and Recent decisions rows stack: avatar and name, then dates and "type · amount", then the badge and decision line. The note goes full width below. Nothing scrolls sideways.
- Dialogs are full width with 16 px margins over a full-screen scrim. Buttons stack full width, confirm on top and Go back below. The note field keeps 4 rows and the counter stays on the same line as the helper, wrapping under it if needed.
- The toast spans the width above the safe area.

## Wording

- No pronouns anywhere. Open Door has no pronoun data and never guesses one from a name, so lines name the person or the page: "Zara will see it on the Time off page.", "Approved. Zara will see it on the Time off page.", "Denied. Zara will see your note on the Time off page." (no note: "Denied. Zara will see it on the Time off page.")
- Open Door never favors a decision: Approve and Deny look the same on the card, and both dialogs confirm with the standard primary button. Red appears only for real errors (the conflict refusal and the page error).

## Keyboard and focus

- Tab order: sidebar (Ask, Time off, Directory, Handbook, Approvals, How it's built), persona switcher, then each waiting request's Approve and Deny in list order, then the lists. Rows in Coming up and Recent decisions have no controls, so Tab skips past them.
- Approve and Deny are each named for the request: "Approve Zara Bautista's PTO, November 9 to 10", "Deny Priya Raman's PTO, October 30".
- The nav item's accessible name includes the count: "Approvals, 2 waiting". With nothing waiting it's "Approvals". The heading reads "Waiting for you, 2".
- The dialog is `role="alertdialog"`, modal, labeled by its title and described by its facts.
  - Approve: focus starts on "Go back".
  - Deny: focus starts in the note field, so Marcus can type or tab on. It's optional, and the next two stops are Go back and Deny.
  - Tab and Shift+Tab stay inside the dialog. Escape goes back, except while deciding.
- Note field: label "Note to Zara (optional)". The helper and counter are its description. Typing stops at 300 characters, and in the last 20 a polite live region says "N characters left".
- While deciding: the confirm button has `aria-busy` and `aria-disabled` and stays focused, and Go back and the note are disabled.
- After a decision, focus moves to the next waiting request's Approve. When none are left, it moves to the "Waiting for you" heading (`tabindex="-1"`). The toast (`role="status"`) is announced.
- Go back or Escape returns focus to the button that opened the dialog.
- Conflict: the dialog closes, the refusal on the card is `role="alert"`, and focus moves to the next waiting request's Approve (or the heading).

## Contrast (WCAG 2.x)

The page has no new colors; these are the pairs it uses for the first time.
- Conflict card text, ink-muted #55646E on surface-sunken #F9FAFB: 5.9:1
- Refusal message ink on danger tint: 14.7:1; danger icon on it: 5.9:1 (from screen 08)
- Approve and Deny on the card (secondary), ink on white: 16.4:1; hovered, ink on surface-hover #F0F3F5: 14.7:1
- Dialog confirm (primary), white on primary #59256A: 11.1:1
- Nav count, white on primary #59256A: 11.1:1. The badge on the current item's primary-tint fill, primary against tint: 8.8:1
- Muted avatar, ink on surface-hover #F0F3F5: 14.7:1
- Note field border, input-border #7F8C93 on white: 3.5:1 (meets 3:1 for controls); focused, primary: 11.1:1
- Heading count chip edge, border-strong #C9D2D7 on white: 1.5:1 (decorative; the number is ink, 16.4:1)
- Dialog against the scrim (scrim over white is about #B4B8BB): 2.0:1 (decorative; the dialog also has a shadow and is modal)

## Copy not given in the brief

- Waiting subtitle: "PTO requests from your direct reports, oldest first. Sick time is recorded, not approved, so it appears only under Coming up."
- Card label: "Team coverage"
- Coverage, for a range with no overlap: "No one else on your team is off those days."
- Coming up subtitle: "Approved and recorded time off in the next 30 days, soonest first." Empty: "No time off on your team in the next 30 days."
- Recent decisions subtitle: "Your decisions from the last 90 days, newest first." Empty: "No decisions in the last 90 days."
- Decision line: "Approved today", "Denied today"
- Note counter, screen readers only: "N characters left"
- Error page body: "Your approvals didn't load. Try again in a moment. If it keeps happening, this reference helps us find it:"
- Loading, screen readers only: "Loading approvals"
- Phone menu button: "Menu, 2 approvals waiting"

## Data the API needs to supply

- Each direct report's name, title, and initials.
- For each waiting request: when it was sent, the person's PTO available now, and the hours. Available after this can come from the engine directly.
- Team coverage per request: the other direct reports' approved and recorded time off on the request's scheduled workdays, with type. That means a scheduled-days list per person.
- For decisions: who decided, when, and the note. The request's current version, so a decision on a stale request (canceled or already decided) can be refused with the reason ("Zara canceled this request.").
- The manager's own figures for the home: PTO available, requests pending, approvals waiting.
- Vikram Morales's November 10 PTO is approved but isn't in Recent decisions. The sample data treats it as decided more than 90 days ago. Recent decisions lists only the viewer's own decisions, and only the direct manager decides, so a decision by someone else can't appear there.

## Things to confirm (resolved)

- Marcus's home figures: the App Shell file's earlier figures ("14 days PTO available", "1 request waiting") were sample data. The build reads the rail from `GET /time-off/summary`, so these frames' figures (72 hours, 0 pending, 2 waiting) are the shape it follows. No change to the App Shell file.
- Approve and Deny: decided by the owner on 2026-10-20 and recorded under "Wording": equal weight on the card, the standard primary button in both dialogs, no red.

## Components

- New: `Avatar` (core), `ApprovalCard`, `NoteField`, `DecisionDialog` in `components/approvals/`, with `approvals.css` (imported in `styles.css`) and their `.d.ts` and `.prompt.md`.
- Changed: `RequestRow` adds `person` (avatar and name column, no Cancel column), `decidedLine` ("Approved October 5"), and `noteLabel` ("Your note").
- Reused unchanged: StatusBadge, FormMessage (refusal), Button (secondary, primary, loading), NavItem (count), GlanceLink (marker), toast, the alert dialog pattern, and `--scrim`.
- The library card `components/approvals/approvals.card.html` is embedded at the bottom of `Approvals.dc.html`. It covers:
  - Approve and Deny: default, hover, focus, loading, and disabled, both secondary on the card, plus the dialog's primary confirm
  - the approval card: default, focus, hover on Deny, conflict, loading
  - the note field: empty, hover, focus, at the limit, disabled
  - the dialog: approve, approving, deny with a note, denying, plus a live one
  - team request rows, including hover
  - the nav count: current, default, hover, focus, none
  - Marcus's glance list and the avatar sizes

## Build decisions (owner, 2026-10-20)

- **Approve and Deny carry equal weight** on the card, and both dialogs confirm with the
  standard primary button, because Open Door never recommends a decision (invariant 5). Red is
  for real errors only.
- **No pronouns anywhere.** The data has none, and Open Door never guesses one from a name.
- **Team coverage counts approved and recorded time off only;** a request still waiting doesn't
  count as off. It's plain text, never a warning or a score.
- **"Available after this" is the person's available PTO as it stands,** since a waiting request
  already counts against it. The API sends it with its label.
- **Only the direct manager decides,** so the page lists only Marcus's direct reports' requests,
  and Recent decisions lists only Marcus's own.

## Where the data comes from

| The design needs | The API gives it |
|---|---|
| Waiting for you: person, dates, amount, sent date, available after, coverage | `GET /time-off/requests?scope=waiting` (coverage per request) |
| Coming up on your team (the next 30 days) | `GET /time-off/requests?scope=team` with a 30-day window |
| Recent decisions (the last 90 days) | `GET /time-off/requests?scope=team`, filtered to the viewer's decisions |
| The nav count and the home's glance figures | `GET /time-off/summary` |
| Approve, deny with a note | `POST /time-off/requests/{id}/decision` (409 with the current status on a stale request) |

## Acceptance criteria

- [ ] Every state matches its screenshot at 1440 px within the spacing tokens, with the build
      decisions applied
- [ ] Usable at 390 px as "Phone (390 px)" describes; nothing scrolls sideways
- [ ] Only managers see the Approvals nav item, with the count in its accessible name
      ("Approvals, 2 waiting"); a switch from Marcus to Priya removes it
- [ ] Approve and Deny look the same on every card, and are named for their request
- [ ] The approve dialog starts focus on "Go back"; the deny dialog starts focus in the note
      field; Tab stays inside; Escape goes back except while deciding
- [ ] The note field stops at 300 characters, shows "N of 300", and announces the last 20 politely
- [ ] After a decision, the toast is announced, the request moves to Recent decisions, the counts
      drop, and focus moves to the next request's Approve, or to the heading when none are left
- [ ] A stale request (canceled or already decided) shows its refusal on the card as
      `role="alert"`, muted, with no actions
- [ ] Coverage is plain text with no color, icon, or wording that suggests a problem
- [ ] No sick time ever appears as something to decide
- [ ] No pronouns in any copy
- [ ] axe reports no violations in any state
