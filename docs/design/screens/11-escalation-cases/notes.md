# Screen 11 · The case button, the confidential-case form, and My cases

- Routes: `/ask` (the HR panel under an answer) and `/my-cases` (new).
- Source: `Escalation Cases.dc.html` (one frame per state, then the component card). The form and sent line in the frames come from `Case Form.dc.html`. Components: `components/cases/` (CaseForm, CaseSent, CaseList, `cases.css`). All three files are in `docs/design/system/`.
- Today is Monday, October 26, 2026. The person is Priya Raman. HR replies within 2 business days, so by Wednesday, October 28.
- Every frame is live: open the form, choose, type, press "Send to HR" (validation, then sending, then sent), or press "Not now".

## What's new

- The sensitive panel's body text changes (verbatim from the brief) and gains a primary "Open a confidential case" with a lock, after "How confidential HR cases work, §7.2".
- The crisis panel is unchanged. It gains a secondary "Open a confidential case" after the contacts. The crisis text always comes first.
- The "Can't answer right now" panel gains a "Write to HR" link (to `/my-cases`) after the contacts. No case button there.
- A new My cases page, and a "My cases" nav item (folder-lock) after Time off.
- The AI never opens a case and never says it will. Its answer says "you can open a confidential case with the button below." Only the person's own press of "Send to HR" sends anything.

## How it looks

- Confidential, not alarming: the form and the sent line sit on `--confidential-tint` (#F7F3F9, a quiet aubergine wash) with a `--confidential-border` edge and a lock icon in primary. No warning colors, no alert style.
- In the conversation, the form is a band at the foot of the HR panel, full panel width, below the contacts and §7.2 link. It replaces the button.
- On My cases, the same form sits in a card (same tint, 16 px radius) where the "Open a confidential case" button was.
- Sent: one line with the lock. No apricot, no check, no celebration. A reload renders exactly the same.
- Red only for real errors: the field errors and the failed send.

## States

| File | State |
| --- | --- |
| desktop-sensitive-offer | Answer (AI label, two sources), then the HR panel with the new text, contacts, §7.2 link, primary "Open a confidential case". "Show your work" collapsed under the panel |
| desktop-form | Form open in the panel. Nothing chosen. Words prefilled: "My manager keeps making comments about my age.", "46 of 4,000 characters" |
| desktop-form-ready | "Harassment or discrimination" chosen; focus ring on "Send to HR" |
| desktop-form-short | Earlier turn, then "yes, that's what happened" flagged. Prefilled with it, "25 of 4,000 characters", hint "Add what happened, when, where, and who was involved, as much as you know." |
| desktop-form-errors | "Choose what this is about." under the choices; "That looks like a Social Security or card number. Please take it out before sending." under the textarea, which gets the danger border |
| desktop-form-limit | 4,000 characters: "4,000 of 4,000 characters. Shorten it to send." in ink, semibold |
| desktop-sending | Spinner and "Sending…" (aria-busy); choices, textarea, and "Not now" disabled |
| desktop-sent | "Sent to HR. HR replies by Wednesday, October 28. You can see its status in My cases." and "View in My cases". Case button gone |
| desktop-send-error | "Your case wasn't sent. Please try again." (refusal message, role="alert") above the buttons; the primary reads "Try again". Category and words kept |
| desktop-waiting-limit | In place of the case button: "You have 5 cases waiting for HR. To add to one, contact the HR team directly." The panel's HR contacts sit directly above it |
| desktop-crisis-offer | Screen 07 crisis panel unchanged, secondary "Open a confidential case" after the contacts |
| desktop-cant-answer-link | Screen 07 "Can't answer right now" panel, "Write to HR" after the contacts |
| desktop-my-cases-empty | Heading, intro, "You haven't sent HR a case." and a primary "Open a confidential case" |
| desktop-my-cases | Button above three rows, newest first |
| desktop-my-cases-form | The form open on My cases, empty words with the "Say what happened…" hint, "0 of 4,000 characters" |
| desktop-sent-crisis | The sent line, then screen 07's crisis panel in full, then the list |
| desktop-nav | Priya: Ask, Time off, My cases, Directory, Handbook. Marcus adds Approvals (with its count) after Handbook |

## Form rules

- Category: a ChoiceGroup (radiogroup), nothing preselected, two columns of 44 px options.
- Words: prefilled from the message that raised the panel. Short-reply rule: if that message is a reply under 40 characters, the hint becomes "Add what happened…" instead of "Say what happened…". On My cases the field starts empty.
- Counter: "N of 4,000 characters", ink-muted. At 4,000, "4,000 of 4,000 characters. Shorten it to send." in ink, semibold. The field stops at 4,000 and never silently cuts pasted text beyond what's shown. If "Send to HR" is pressed at the limit, the counter turns to the error color and is announced.
- Validation on "Send to HR", in order: no category; empty words; a Social Security or card number pattern (3-2-4 digits, or 13 to 19 digits); at the limit. The server repeats every check.
- "Send to HR" is never disabled before sending, so errors can be shown and announced.
- Send failure keeps the category and the words. "Try again" sends again.
- Five waiting cases is the limit. When it's reached the panel shows the limit line instead of the button, and the form never opens. On My cases, the line replaces the button and carries the HR contacts with it, since there's no panel above.
- After sending on My cases, the new row appears at the top of the list ("Sent to HR", "HR replies by Wed, Oct 28"). If the safety check routes the words to crisis, the crisis panel appears right after the sent line, unchanged and never shortened.

## My cases

- Heading "My cases", intro "Cases you've sent to HR. Only the HR team can open them in Open Door, and they're stored encrypted."
- Rows: category (600) with "Sent Mon, Oct 26" under it; a status badge; the date line right-aligned.
- Statuses (StatusBadge, new values): "Sent to HR" (cinnamon clock), "HR is reviewing" (primary file-search), "HR has finished its review" (ink circle-check; neutral, since a finished review isn't a success or a failure).
- Rows aren't links. No row shows the words, and there's no way into a case from here.
- No right rail, as on Time off.

## Layout (1440 px)

- Conversation: the 760 px column and 680 px answer width from screen 07; the panel is 680 px; "At a glance" rail stays (92 hours, 0 requests pending, Sep 12).
- Form band padding 22/24/24 px; 22 px between groups; "Before you send" set off by a hairline in the confidential border color.
- My cases: 40/48 px sheet padding, 760 px content column; the list grid is 1fr, 248 px (badge), 176 px (date line).
- Frames grow to fit their content (900 px minimum).

## Phone (390 px)

- The panel and form are full width with 16 px side padding; the band keeps its tint edge to edge.
- The category choices stack in one column.
- The buttons stack full width, "Send to HR" first, then "Not now".
- The counter stays under the textarea, right-aligned; a field error wraps on its own line above it.
- My cases: the header chip drops under the heading. Each row puts the category and badge on the first line and the date line under the category. "Open a confidential case" is full width.
- Nothing scrolls sideways.

## Keyboard and focus

- "Open a confidential case" opens the form and moves focus to its heading ("Open a confidential case", `tabindex="-1"`, h3 in the panel, h2 on My cases).
- Tab order in the form: the category group (one tab stop; arrow keys move and select), the textarea, the links in "Before you send", "Send to HR", "Not now".
- "Not now" closes the form, keeps nothing, and returns focus to the button that opened it.
- On "Send to HR" with errors: each error is `role="alert"` and linked to its field with `aria-describedby`; the field gets `aria-invalid="true"`. Focus moves to the first invalid field (the chosen or first category option, otherwise the textarea).
- While sending: "Send to HR" is `aria-busy` and `aria-disabled`; the fields and "Not now" are disabled.
- Sent: the line is `role="status"` with `tabindex="-1"`, and focus moves to it. "View in My cases" is the next tab stop.
- Send failure: the message is `role="alert"`; focus moves to it, then "Try again".
- The panel stays a `section` labeled by its header (h2). Nothing here is a modal, and nothing traps focus.

## Contrast (WCAG 2.x)

- Ink #14212A on confidential tint #F7F3F9: 15.4:1
- Ink-muted #55646E on the tint (hint, counter): 5.7:1
- Primary #59256A on the tint (lock, links): 10.2:1
- Danger #B42318 on the tint (field errors): 6.1:1
- Confidential border #E4DAE9: decorative; the lock and the heading carry the meaning
- Selected choice: ink on primary-tint 13.0:1, primary edge 11.1:1 on white
- Error border on the textarea: danger on white 6.6:1
- Crisis band: white on ink 16.4:1 (unchanged)

## Copy not given in the brief

- Frame 4's earlier turn: "Is a manager allowed to joke about someone's age at work?" and the answer "No. Juniper Row doesn't allow harassment based on age, and that includes jokes and repeated comments.¹ Did something like this happen to you at work?"
- The sample words in the errors frame: "My manager keeps making comments about my age. My employee number is 123-45-6789."
- The limit frame's words: a longer account, repeated to 4,000 characters.
- Empty words error: "Add your words before sending."
- Sent line on My cases (where the link would point to the same page): "Sent to HR. HR replies by Wednesday, October 28."
- "Before you send" as a heading; "Your cases" as the list's accessible name.
- Case status labels: "Sent to HR", "HR is reviewing", "HR has finished its review"; sent dates as "Sent Mon, Oct 26".
- "Show your work" expanded: "Routed to HR guidance", "Searched the handbook", "§2.2 Harassment and discrimination · §7.2 How confidential HR cases work".
- The can't-answer frame's question: "My manager keeps making comments about my age."

## Where the data comes from

- **The panel:** the `escalation` event's `offerCase` (true for sensitive and crisis turns) and its
  HR contacts. After a reload, the turn's `EscalationOut.offerCase` and `caseOpened`
  (`{ status, replyBy }`) when a case was sent from that turn.
- **The form's texts and today's reply-by date:** `GET /api/v1/cases/texts`. The web app holds no
  copy of the panel text, the five lines, or the sent line.
- **The prefill:** the client's own copy of the turn's question. The short-reply prompt is decided
  in the browser (a prefill under 40 characters).
- **Sending:** `POST /api/v1/cases` with `{ submissionId, category, text, turnId? }`. It returns
  the status view and the reply-by date, plus the fixed crisis text when the safety check routes
  the words to crisis. Its problems: the personal-data check, the length limit, the waiting
  limit, and a turn that isn't the person's own.
- **The waiting limit and "My cases":** `GET /api/v1/cases/mine`: each case's category, sent
  date, status (`new`, `in_review`, `closed`), status date, and reply-by date. Never the words.

## Components

- New, under `components/cases/`: `CaseForm`, `CaseSent` (sent and limit variants), `CaseList`, with `cases.css` (imported in `styles.css`), `.d.ts`, and `.prompt.md`. Library card: `components/cases/cases.card.html` (embedded at the bottom of the DC).
- New tokens: `--confidential-tint`, `--confidential-border` in `tokens/colors.css`.
- New icon: `file-search`. StatusBadge gains `case-sent`, `case-reviewing`, `case-finished`.
- NavItem: "My cases" (folder-lock, `/my-cases`) after Time off for everyone.
- Reused: Button, Avatar (initials), ChoiceGroup, FormMessage (refusal), the NoteField textarea with the composer's counter, StatusBadge, NavItem, the source chips, "Show your work", and screen 07's sensitive, crisis, and "Can't answer right now" panels.

## Build decisions (owner, 2026-10-26)

These were decided after the handoff. Where they differ from a screenshot, the build follows this
section, and the screenshot is not redrawn.

- **The sample answer in `desktop-form-short` is not a target for the model's wording.** The frame
  is there to show the short-reply prompt. Its earlier answer opens with a flat "No.", which
  overstates handbook §2.2 (a joke is harassment when it makes work hostile), and it asks
  "Did something like this happen to you at work?", which the assistant isn't steered to ask.
- **The waiting-limit line links to My cases:** "You have 5 cases waiting for HR. To add to one,
  contact the HR team directly." followed by the link "View your cases".
- **Statuses in the data are `new`, `in_review`, and `closed`.** The labels are as designed:
  "Sent to HR", "HR is reviewing", "HR has finished its review".
- **The fixed texts come from the API,** word for word, approved by the owner and tied to their
  hashes in Phase 6, Stage 4. The empty-words error "Add your words before sending." joins the
  spec's copy.
- **The panel offers a case only when `offerCase` is true.** The "Can't answer right now" panel,
  a budget stop, and the not-found answer's contacts show the "Write to HR" link instead.

## Acceptance criteria

- [ ] Every state matches its screenshot at 1440 px within the spacing tokens, with the build
      decisions applied
- [ ] Usable at 390 px as "Phone (390 px)" describes; nothing scrolls sideways
- [ ] "Open a confidential case" appears on the sensitive and crisis panels only when `offerCase`
      is true; the other panels show "Write to HR"
- [ ] The panel text, the form's five lines, and the sent line are the API's texts, word for word,
      with the reply date from the API
- [ ] The form opens prefilled with the turn's own question, verbatim; a prefill under 40
      characters shows the short-reply prompt
- [ ] "Send to HR" validates in the order the notes give; each error is `role="alert"` with
      `aria-invalid` on its field, and focus moves to the first
- [ ] A double click on "Send to HR" opens one case, and a turn opens at most one case, in this
      tab, after a reload, and in another tab
- [ ] Sending shows "Sending…" with `aria-busy`; the sent line is `role="status"` and takes
      focus; a failed send keeps the category and the words
- [ ] The waiting-limit line replaces the button and links to My cases
- [ ] A crisis verdict shows the fixed crisis text right after the sent line, unchanged
- [ ] My cases shows status only: no words and no link into a case; the badges and date lines
      follow the spec
- [ ] "My cases" sits after "Time off" for everyone but HR
- [ ] No pronouns in any copy; red only for real errors; axe reports no violations in any state
