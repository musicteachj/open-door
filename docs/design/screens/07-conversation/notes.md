# Screen 07 · Conversation

- Route: `/ask`
- Source: `Conversation.dc.html` (frames 1a to 1x). The source panel is `Passage Panel.dc.html`, shared with screen 06.
- Entry: the first question sent from the assistant home (screen 03). The greeting and "Try asking" go away, the thread fills the column, and the composer docks at the bottom. There's one current conversation and no history list.
- Personas shown: Priya Raman (all frames except one). Mateo Alvarez in `desktop-other-state`.

## States

| File | State |
| --- | --- |
| desktop-cited-answer.png | Cited answer: user message, AI label, inline markers, source chips, "Was this right?", "Show your work" collapsed, retention line, "Start a new conversation", docked composer with disclosure |
| desktop-source-panel.png | Source panel docked beside the conversation, opened from marker 1 |
| desktop-streaming-searching.png | Status line before any text, with Stop |
| desktop-streaming-text.png | Text arriving, with Stop |
| desktop-streaming-progress-note.png | Draft note replaced by a status line while the assistant searches again |
| desktop-stopped.png | Partial text, "Stopped", "Ask again" |
| desktop-show-your-work.png | Expanded: "Safety check: no concerns", tools called, sections retrieved |
| desktop-show-your-work-routed.png | Expanded on a sensitive escalation: "Routed to HR guidance" |
| desktop-feedback-yes.png | Yes, then the thank-you line |
| desktop-feedback-no.png | No, with the optional reason form |
| desktop-feedback-thanks.png | Thank-you line after sending a reason |
| desktop-other-state.png | Another state's policy, as Mateo |
| desktop-not-found.png | Not in the handbook, with HR contacts |
| desktop-refusal.png | Another employee's home address |
| desktop-sensitive.png | Sensitive escalation panel |
| desktop-crisis.png | Crisis panel |
| desktop-error-midstream.png | Error inside the assistant's message |
| desktop-cant-answer.png | "Can't answer right now" panel |
| desktop-send-error.png | Composer send error while an answer is streaming |
| desktop-budget-sandbox.png | Banner: this sandbox's AI budget is used; composer disabled |
| desktop-budget-daily.png | Banner: today's demo budget is reached; composer disabled |
| desktop-length-hint.png | Length hint near 2,000 characters |
| desktop-personal-data.png | Personal-data warning |
| desktop-long-conversation.png | Long-conversation notice |

## Layout (1440 px)

- App shell: 248 px sidebar. The white content sheet is inset 12 px.
- Conversation column: the header row holds the retention line, "Start a new conversation", and the sandbox pill. The thread scrolls under it, and the composer sits at the bottom. The thread and composer use the 760 px measure, and assistant messages are capped at 680 px.
- Right rail: 340 px, "At a glance", same as the home. While the source panel is open (420 px), it takes the rail's place.
- User messages sit on the right on surface-hover. Assistant messages have no bubble. They start with an "AI" label and "Open Door".
- Markers are numbered by source, in order of first use. Chip 1 and every marker 1 point to the same section. Each marker opens the passage it cites. A chip opens the first passage cited from that section.
- Escalation panels (sensitive, crisis, can't answer) are bordered cards with a header band. They have no "AI" label, sources, or "Was this right?". Each one ends with the HR contacts. The sensitive panel keeps "Show your work". The crisis band is ink, the only dark band in the product. The other two are surface-sunken. Red appears only on the can't-answer icon, because that one is an error.
- Source chips and feedback appear only after an answer finishes. Markers appear while text streams, as each claim completes.

## Narrow screens (390 px)

- The sidebar collapses behind a menu button in a top bar. The right rail is hidden, and "At a glance" stays on the home only.
- The header row stacks. "Start a new conversation" becomes an icon button labeled "Start a new conversation", next to the sandbox pill. The retention line moves under the composer, below the disclosure.
- The thread is full width with 16 px side padding. User messages are capped at 85% width.
- The source panel opens as a full-height sheet from the bottom, over the conversation. On a phone it's modal: focus stays inside it, the page behind it is inert, and it has the same header (eyebrow, title, close) and footer ("Open in handbook"). Swiping down or tapping close dismisses it.
- Source chips wrap. A long label truncates with an ellipsis, and the full label is in the chip's accessible name.
- "Was this right?" and "Show your work" sit on two rows.
- Escalation panels are full width. Contact rows stack, with the email under the name. In the crisis panel, phone numbers are `tel:` links and the chat address is a link.
- The composer stays docked above the keyboard. Its footer wraps, so the disclosure sits above the Ask or Stop button. Banners wrap to several lines, and "Start a new sandbox" moves under the text.

## Keyboard and focus

- Tab order, top to bottom: sidebar nav, persona switcher, banner action (if any), "Start a new conversation", then the thread in reading order. Within the thread: links and markers inside the text, then source chips, Yes, No, "Show your work", and the work details. After the thread comes the composer, then Ask or Stop. The rail or the open panel comes last.
- Markers and chips are buttons with `aria-expanded`. A marker's accessible name is "Source 1: Handbook CA-4.3, California addendum"; a chip's starts with what it shows: "Handbook CA-4.3 · California addendum, source 1" (WCAG 2.5.3, Label in Name; changed 2026-11-01).
- Opening the panel moves focus to the panel title (h2, `tabindex="-1"`). The panel isn't modal on desktop. Tab continues from the title to Close, the passage text, and "Open in handbook".
- Escape anywhere in the conversation view, or the close button, closes the panel. Focus returns to the marker or chip that opened it. Pressing the same marker again also closes the panel.
- Opening a different marker while the panel is open replaces the passage and moves focus to the title again. Focus later returns to the newest opener.
- "Show your work" is a disclosure button (`aria-expanded`, `aria-controls`). Focus stays on the button.
- Pressing No moves focus into the reason box. Cancel returns focus to No. After Send or Yes, focus moves to the thank-you line, which is `role="status"`.
- In the composer, Enter sends and Shift+Enter adds a new line. While an answer streams, Stop takes Ask's place, and Enter shows the send error. Stop moves focus back to the composer.
- Status lines are `role="status"` with `aria-live="polite"`. The streaming message is `aria-busy="true"` until it finishes, then the full answer is announced once. Errors and the personal-data warning are `role="alert"`.
- Escalation panels are regions labeled by their header. When one arrives, it's announced once and focus stays in the composer.
- Under a budget banner, the composer and Ask are disabled and skipped by Tab. The Handbook and Directory links below the composer stay in the Tab order.

## Copy not given in the brief

Header and composer
- Composer placeholder in a conversation: "Ask a follow-up question"
- Disabled composer placeholder (sandbox budget): "The assistant isn't available in this sandbox."
- Disabled composer placeholder (daily budget): "The assistant isn't available until tomorrow."
- Under a disabled composer: "You can still use the Handbook and the Directory."
- Sandbox banner action: "Start a new sandbox"
- Length hint (from 1,800 characters): "1,962 of 2,000 characters"
- At the limit: "2,000 of 2,000 characters. Shorten your question to send it."
- Long-conversation notice: "This conversation is getting long, so answers may miss details from earlier messages. A new conversation starts clean." Button: "Start a new conversation"

Assistant message
- Label: "AI", followed by "Open Door"
- Sources label: "Sources"
- Status lines: "Searching the handbook…", "Searching the handbook again…". Finished steps use past tense, for example "Searched the handbook: sick leave" and "Read §4.3 Sick leave".
- Stop button: "Stop"
- Stopped: "Stopped". Button: "Ask again"
- Mid-stream error: "Something went wrong partway through this answer, so it's incomplete." Button: "Retry"

Show your work
- Button: "Show your work"
- Headings: "Tools called", "Sections retrieved"
- Empty list: "None"
- Section status: "Cited as 1", "Not cited"
- Profile tool: "Read your profile: Oakland store, California, salaried"
- Routed note: "Questions like this go to a person on the HR team. The assistant didn't search the handbook or write an answer."

Feedback
- Thank-you after Yes: "Thanks for the feedback."
- Reason label: "What was wrong?" with "Optional"
- Reason placeholder: "For example, it cited the wrong state"
- Counter: "45 of 500 characters"
- Buttons: "Cancel", "Send feedback"
- Thank-you after a reason: "Thanks for the feedback. The HR team reviews every note."

Panels
- Sensitive header: "A person in HR handles this, not the AI"
- Sensitive link: "How confidential HR cases work, §7.2"
- Crisis header: "Reach a person right now"
- Can't-answer header: "Can't answer right now". Button: "Try again"
- Contacts heading: "HR contacts", with "A person on the HR team reads and answers these, not the AI."
- Contacts: Dana Whitfield, HR Business Partner · Denver HQ, dana.whitfield@juniperrow.example. HR team, Shared inbox, hr@juniperrow.example.

Sample answers (demo content)
- Not found: "I couldn't find that in the handbook. I searched for tuition reimbursement and education benefits, and no section covers them. The HR team can tell you whether Juniper Row offers anything like this."
- Refusal: "I can't share another employee's home address. Home addresses are private, and only the employee and HR can see them. If you'd like to send Elena a card, you could give it to her at work or ask HR to pass it along. Her work email and location are in the Directory."
- Another state: "Here's the California policy. … It doesn't apply to you, because you work at the Austin warehouse in Texas. For you, the company policy applies: …"

## Build decisions (owner, 2026-10-17)

These were decided after the handoff. Where they differ from a screenshot, the build follows this
section, and the screenshot is not redrawn.

- **A sensitive question gets an answer, then the HR panel.** The API has the assistant answer a
  sensitive question (with a note not to counsel or judge) and then sends the fixed sensitive
  panel, as the Phase 4 spec says. So `desktop-sensitive.png` gains the assistant's message, with
  its "AI" label, sources, and "Was this right?", above the panel. In
  `desktop-show-your-work-routed.png`, "Show your work" lists what the assistant really did: the
  safety check reads "Routed to HR guidance", and the tools and sections are listed as usual. The
  routed note becomes "Questions like this also go to a person on the HR team." The crisis and
  "can't answer right now" panels are unchanged: those turns never reach the model.
- **The thank-you after a reason is "Thanks for the feedback."**, the same as after Yes. No one
  reviews feedback in Phase 4, so the screenshot's "The HR team reviews every note." is not used.
- **The shared HR inbox stays.** "HR team, Shared inbox, hr@juniperrow.example" is a fixed
  constant shown after the HR people from the directory in every panel's contacts.
- **Error messages come from the API.** An `error` event carries its own fixed text, so the
  mid-stream error shows that text in the place `desktop-error-midstream.png` shows "Something
  went wrong partway through this answer, so it's incomplete." Only the "Retry" button is the
  design's.
- **A source chip names the section's group** from the data ("Handbook §4.3 · Company handbook"),
  where a mockup shows a chapter name.

