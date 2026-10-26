# Screen 10 · Confirm cards in the conversation

- Route: `/ask`, inside the 680 px assistant column of the screen 07 conversation, with the composer docked below and "At a glance" on the right.
- Source: `Confirm Cards.dc.html` (one frame per state, then the component card). Component: `components/assistant/ConfirmCard.jsx` with `confirm.css`. Standalone export: `Confirm Cards.html` in this folder.
- Today is Tuesday, October 20, 2026, about 3:27 PM. Cards expire 15 minutes after they're made, so every pending card reads "Expires at 3:42 PM".
- `desktop-pending` is live. You can Confirm (it shows the loading state, then the executed record, and the rail updates) or Dismiss. Every other frame's Confirm, Dismiss, note field, and "Ask again" also work.

## What the card is

The assistant never acts. It answers in one line, and Open Door shows a card that names the action, lists the facts from the time-off engine, and waits.
- Header: an icon tile and the action ("Book PTO", "Record sick time", "Approve a request", "Deny a request", "Cancel time off"). On the right is a status slot: "Expires at 3:42 PM" while pending, the status badge once it's a record.
- Body:
  - who (decisions only, with the avatar)
  - a short facts list (Type, Dates with weekdays, then Amount and Balance where the variant has them)
  - for bookings, the screen 08 "What this uses" block: counted days with checks, skipped days with the calendar-minus icon and the reason, the total and what's left, and the source chips inside it
  - team coverage (decisions), an info line, the short-notice warning when it applies, the note field (deny), and source chips for cards without a "What this uses" block
- Footer while pending, on a sunken band: the AI tag and "Proposed by the AI. Nothing happens until you confirm.", then Confirm (primary, on every variant including deny) and Dismiss (secondary). The secondary button is "Dismiss", not "Cancel", so on the "Cancel time off" card it can't be read as the action itself.
- Final states replace the footer. The buttons never come back, and the card stays in the thread as a record.

## How the figures are worked out

The engine computes every figure, not the AI.
- Bookings: what's left = available now − hours counted. Priya has 92 hours, so October 30 leaves 84 hours (10.5 days). November 25 to 27 counts Wednesday and Friday (16 hours) and skips Thanksgiving, leaving 76 hours (9.5 days). The half day in the replaced frame leaves 88 hours (11 days).
- Sick time: 32 hours available this year − 3 = 29 hours of sick leave left this year.
- Approve and deny: "available after this" is the person's available PTO as it stands, since a waiting request already counts against it (Priya 84 hours, Zara 62 hours). Deciding doesn't change it.
- Cancel: the 8 approved hours on December 23 go back, so 92 + 8 = 100 hours (12.5 days).
- Rail, as Priya: 92 hours, 0 requests pending, Sep 12. After Priya confirms variant 1: 84 hours and 1 request pending (with the cinnamon marker).
- Rail, as Marcus: 72 hours, 0 requests pending, 2 approvals waiting, Sep 12. After Marcus confirms a decision: 1 approval waiting, and the nav count drops to 1.

## States

| File | State |
| --- | --- |
| desktop-pending | Variant 1 pending; live |
| desktop-pending-streaming | The line is still arriving (caret). Confirm disabled with "Wait for the answer to finish"; Dismiss works; the composer shows Stop |
| desktop-confirming | "Confirming…" with a spinner; Dismiss disabled |
| desktop-executed | Apricot line "Requested. Marcus Bell will review it." with "View in Time off"; Waiting for approval badge; rail at 84 hours and 1 pending |
| desktop-failed | "Couldn't book this: you already have time off on Friday, October 30. Nothing was changed." (role="alert"); facts muted |
| desktop-dismissed | "You dismissed this. Nothing was changed."; facts muted |
| desktop-replaced | First card: "Replaced by a newer card. Nothing was changed." A follow-up ("Actually, make it a half day.") made a new pending card |
| desktop-expired | "This card expired after 15 minutes. Nothing was changed." with "Ask again", which puts "Can I take Friday the 30th off?" back in the composer |
| desktop-holiday | Variant 2 pending: Thanksgiving skipped; sources §4.1 and §4.2 |
| desktop-sick | Variant 3 pending: recorded at once, no approval; source CA-4.3 |
| desktop-approve | Variant 4 pending, as Marcus: Priya, the facts, team coverage |
| desktop-deny | Variant 5 pending, as Marcus: note field inside the card with the typed note, "77 of 300"; the confirm button reads "Deny" and is primary |
| desktop-cancel | Variant 6 pending: current status Approved, what goes back, the balance after |
| desktop-executed-variants | Executed state for variants 2 to 6, deny with and without a note |
| desktop-conversation | Full conversation with "Show your work" expanded: "Safety check: no concerns", "Checked your time off", "Prepared a confirm card", "Sections retrieved: None" |
| desktop-conversation-executed | The same after Priya confirms; rail at 84 hours and 1 request pending |
| desktop-sensitive | The sick-time card, then the escalation panel, as two separate things; "Show your work" collapsed under the panel |
| desktop-sensitive-work | The same with "Show your work" expanded: "Routed to HR guidance", "Questions like this also go to a person on the HR team.", the two tools, "Sections retrieved: None" |

The executed texts:
- 1 and 2: "Requested. Marcus Bell will review it." with "View in Time off"
- 3: "Recorded." with "View in Time off"
- 4: "Approved. Priya will see it on the Time off page." with "View in Approvals"
- 5: "Denied. Zara will see your note on the Time off page." or, with no note, "Denied. Zara will see it on the Time off page.", with "View in Approvals"
- 6: "Canceled. 8 hours are back in your balance." with "View in Time off"

## The executed moment

- The footer becomes a line on `--apricot-tint`, a new token in the cinnamon family, with a success check icon and ink text. It fades in over 200 ms (no motion with reduced motion). No confetti, scale, or bounce.
- The header's expiry becomes the status badge (Waiting for approval, Recorded, Approved, Denied, Canceled). The facts stay at full strength, because the card is now the record.
- On a cancellation, the facts list drops the old "Status: Approved" row once executed, so it never contradicts the Canceled badge.
- Every ending other than executed says "Nothing was changed.", mutes the facts and the icon tile, and uses a neutral sunken footer. Failed uses the refusal colors because it's a real error.

## The sensitive turn

- Priya's message mixes a routine request with a sensitive one. The assistant's line covers only the routine part. The card follows, then screen 07's escalation panel "A person in HR handles this, not the AI".
- They read as two separate things:
  - The card is a white box with a primary-tint icon tile and a sunken action footer.
  - The panel has a sunken header strip with the people icon, a stronger border, a larger radius, larger body text, and the HR contacts.
  - There's a wider gap between the two.
- The card never mentions the comments. The panel never mentions the sick time.
- "Show your work" sits under the escalation panel, collapsed, as on screen 07. Expanded, it reads "Routed to HR guidance" and "Questions like this also go to a person on the HR team.", then the tools ("Checked your time off", "Prepared a confirm card") and "Sections retrieved: None". The safety check labels the whole message, so nothing says which part was routed.

## Layout (1440 px)

- The assistant column is 680 px, as on screen 07. The card fills it.
- Facts: 96 px label column, value column; Dates in 600.
- Button order: Confirm, then Dismiss, left-aligned, so the tab order matches the reading order.
- "Show your work" sits under the card, right-aligned, as on screen 07.
- Frames grow to fit their thread (900 px minimum), so nothing is cut off.

## Phone (390 px)

- The card is full width with 16 px side padding.
- The facts stack: each label above its value.
- Source chips wrap; a long label truncates with an ellipsis and keeps its full accessible name.
- The "What this uses" block, coverage line, info line, and note field stack at full width.
- The footer line wraps. Confirm and Dismiss sit side by side at the bottom, each half the width. "Wait for the answer to finish" goes on its own line under them.
- The header keeps the title on the left. The expiry or badge drops under it if they don't fit on one line.
- Final-state lines wrap, with "View in Time off", "View in Approvals", or "Ask again" under the text.
- Nothing scrolls sideways.

## Keyboard and focus

- Tab order inside a card: the source chips, the note field when present, Confirm, Dismiss. On executed cards: "View in Time off", or "View in Approvals" on decisions. On expired cards: "Ask again".
- Confirm and Dismiss are named for the action:
  - "Confirm: book PTO on Friday, October 30" and "Dismiss, don't book PTO on Friday, October 30"
  - "Confirm: deny Zara Bautista's PTO, Monday, November 9 to Tuesday, November 10"
  - "Dismiss, keep PTO on Wednesday, December 23"
- The card is a `section` labeled by its header (h3). The facts are a `dl`.
- While the line is streaming, Confirm is `aria-disabled` and described by "Wait for the answer to finish".
- While confirming, Confirm is `aria-busy`, and Dismiss and the note field are disabled.
- After Confirm or Dismiss, focus moves to the outcome line (`tabindex="-1"`). Executed and the neutral endings are `role="status"` and announced once. Failed is `role="alert"`.
- Expiry: the visible time is static text, never a ticking timer. When the card expires, the expired line is announced once (`role="status"`). If focus was inside the card, it moves to "Ask again".
- "Ask again" puts the original question in the composer and moves focus there.

## Contrast (WCAG 2.x)

New pairs:
- Ink #14212A on apricot tint #FBEFE5: 14.5:1
- Success check #2E6B4E on apricot tint: 5.6:1
- "View in Time off", primary #59256A on apricot tint: 9.8:1
- Apricot border #EBC6A8 on white: 1.6:1 (decorative; the icon and words carry the meaning)
- Muted facts, ink-muted #55646E on white: 6.1:1
- The AI tag, ink on white with a border-strong edge: 16.4:1

Reused from screens 08 and 09:
- Refusal message: 14.7:1 text, 5.9:1 icon
- Primary button: 11.1:1
- Disabled Confirm (exempt): #87939A on #E7EBED

## Copy not given in the brief

- Fact labels: "Type", "Dates", "Amount", "Balance", "Status", "How much"
- User questions:
  - variant 2: "Can I take November 25 to 27 off?"
  - variant 3: "I need to record 3 hours of sick time on Thursday."
  - variant 4: "Approve Priya's request for October 30."
  - variant 5: "Deny Zara's request for November 9 and 10."
  - variant 6: "Cancel my day off on December 23."
  - the replaced follow-up: "Actually, make it a half day."
- Variant 2's line reuses variant 1's: "Here's the request. Confirm it and Marcus Bell will review it."
- Dismiss's accessible names: "Dismiss, don't [action]"; for variant 6, "Dismiss, keep PTO on Wednesday, December 23"
- The variant 6 executed card's "View in Time off" link
- Sources on variants 4 to 6: "Handbook §4.1 · Paid time off"
- Composer placeholder in a thread: "Ask a follow-up…"

## Data the API needs to supply

- The `proposal` stream event and each turn's proposals in `GET /assistant/conversations/current` carry the card as structured data from the engine: the action, the person (for decisions), type, dates, counted and skipped days with reasons, amounts and balances with their labels, the warnings, the team coverage (decisions), the source sections, the status, and `expiresAt`. The web app writes the titles, buttons, accessible names, and outcome lines from it, so no copy comes from the model or the server's prose.
- Status: pending, executed, failed (with the engine's problem code and its plain text), canceled (shown as "dismissed", or "replaced" when a newer card replaced it), and expired. Confirming twice or after expiry is refused on the server (409); the UI only reflects it.
- The failed message's dates come with the engine's overlap problem.
- "Ask again" uses the turn's own question, which the conversation already has.
- "Confirmed at 3:28 PM" isn't shown, so the API doesn't need to send when a card was confirmed.

## Components

- New: `ConfirmCard` (`components/assistant/`), with `confirm.css` (imported in `styles.css`), `.d.ts`, and `.prompt.md`.
- New icons: `calendar-plus`, `calendar-x`.
- New tokens: `--apricot-tint` and `--apricot-border` in `tokens/colors.css`.
- Reused: Button, StatusBadge, Avatar, NoteField, PreviewBlock, FormMessage (warning and refusal), the source chip, the team coverage line, the AI tag, "Show your work", and the escalation panel.
- The library card `components/assistant/confirm.card.html` (embedded at the bottom of the DC) shows:
  - two live cards (book, and deny with a note)
  - pending with Confirm and Dismiss in hover and focus
  - streaming, confirming, and pending with the short-notice warning
  - every final state
  - every variant, pending and executed, including deny with no note

## Build decisions (owner, 2026-10-20)

- **"Dismiss", not "Cancel",** is the secondary button on every card, so the "Cancel time off"
  card never has a Cancel button that means "keep it". The outcome reads "You dismissed this.
  Nothing was changed."
- **Confirm is the primary button on every variant,** deny included: it confirms the action the
  person already chose. No red except real errors.
- **No pronouns anywhere,** as on screen 09.
- **A card can't be confirmed while the turn that made it is still running** ("Wait for the
  answer to finish"), and the server refuses it too (409 `turn-running`).
- **The card appears when the proposal tool finishes, under the assistant's message,** and the
  assistant's one line streams above it. The line never claims the action is done.
- **"Show your work" on a sensitive turn** reads "Routed to HR guidance" with "Questions like
  this also go to a person on the HR team.", then the tools, as on screen 07. The safety check
  labels the whole message.
- **Team coverage on a decision card** is shown only on the card, never sent to the model.

## Acceptance criteria

- [ ] Every state and variant matches its screenshot at 1440 px within the spacing tokens, with
      the build decisions applied
- [ ] Usable at 390 px as "Phone (390 px)" describes; nothing scrolls sideways
- [ ] Every figure on a card equals the API's label; the card never shows the model's numbers
- [ ] A pending card always shows "Proposed by the AI. Nothing happens until you confirm." and
      "Expires at" with the time
- [ ] Confirm is disabled with "Wait for the answer to finish" while its turn streams; Dismiss
      works then
- [ ] Confirming shows "Confirming…" with `aria-busy`; afterward focus moves to the outcome line,
      announced once (`role="status"`); a failure is `role="alert"`
- [ ] Executed cards keep their facts, show the status badge, the apricot line, and "View in Time
      off" or "View in Approvals"
- [ ] Dismissed, replaced, failed, and expired cards say "Nothing was changed." and mute their
      facts; expired offers "Ask again", which puts the question in the composer and focuses it
- [ ] After any final state the buttons are gone, and a reload shows the same state
- [ ] The rail's figures update after a confirm (from `GET /time-off/summary`)
- [ ] On a sensitive turn, the card and the HR panel read as separate things, and "Show your work"
      sits under the panel
- [ ] Confirm and Dismiss are named for the action; Tab order is the source chips, the note
      field, Confirm, Dismiss
- [ ] No pronouns in any copy; axe reports no violations in any state
