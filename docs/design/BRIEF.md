# Open Door: design brief for Claude Design

This brief is the full reference for the design. Claude Design gets it in pieces rather than all at
once: a short context prompt first, then one focused prompt per screen, as described in
[`README.md`](README.md).

---

## The product in one paragraph

**Open Door** is an AI-first HR help desk. Its tagline is *"Your open-door policy, now always
open."* Employees ask questions in plain language, such as "How many sick days do I get?" or "Book
next Friday off", and get answers that **cite the company handbook**. The assistant **proposes**
actions, and nothing changes until a person confirms. Sensitive topics like harassment or medical
issues go to a human HR partner, never to the AI. Managers approve requests, and HR works a queue of
confidential cases. The assistant is the home screen; the other pages exist for browsing and
hand-offs.

It is a portfolio piece, so the design should read as a **real, professional product** that a
company would buy, not a hackathon demo. Recruiters and hiring managers will click through it in
about two minutes.

## Who uses it

| Persona | Role | What they do |
|---|---|---|
| Priya | Employee, salaried, Oakland CA store | Asks policy questions, books time off, raises a sensitive concern |
| Mateo | Employee, hourly, Austin TX warehouse | Asks the same questions and gets different, correctly cited answers |
| Marcus | Store manager | Approves requests, checks on his team |
| Dana | HR partner, Denver HQ | Works confidential cases, reviews how the AI is behaving |

Their employer is **Juniper Row**, a fictional 120-person apparel and home retailer with a Denver
headquarters, an Oakland store, and an Austin warehouse. Visitors switch between these personas
inside a private sandbox that lasts 24 hours.

## How it should feel

**Calm and trustworthy: a safe place to ask a sensitive question.** Quiet confidence, not
excitement. Generous whitespace, clear hierarchy, and nothing that shouts. It should feel warm
without being cute, and credible without being cold, like good healthcare or banking software
rather than a social app.

**The design system is chosen** (2026-10-04): "aubergine and cinnamon", from Wada Sanzo's
combination 172, set in Instrument Sans. Its values are in [`tokens.md`](tokens.md) and its source
in [`system/`](system/). The starting direction below is kept as the record of where it began.

**Starting direction** (a starting point; the design system replaced it):

| Token idea | Value | Use |
|---|---|---|
| Surface | `#F5F7F8` porcelain | App background |
| Ink | `#14212A` deep slate | Body text |
| Primary | `#0F5E6E` petrol teal | Primary actions, links, focus, citation marks |
| Accent | `#F29E6D` apricot | Used sparingly: a moment that matters, such as a confirmed action or a highlighted passage |

- **Type:** a clean modern sans such as Instrument Sans or Geist, with tabular figures for numbers
  like balances and dates.
- **Shape:** soft 10 to 12 px radius, airy spacing.
- **Theme:** light-first, with tokens structured so a dark theme can come later.

**Must look distinct from the owner's other apps.** Avoid:
- magenta
- forest green on warm paper
- navy or bright blue
- black with lime
- dark safety-orange consoles

"Indigo with gold" was on this list until 2026-10-04. It belonged to the owner's old employee
management app, which Open Door replaces and which is leaving the portfolio, so a purple lineage
is welcome.

Don't use these fonts: Plus Jakarta Sans, Inter, IBM Plex, Newsreader, DM Mono, JetBrains Mono.

## Technical constraints the design should fit

- **Built with React, Tailwind CSS v4, and shadcn/ui** (Radix primitives), restyled to your design
  system. Design components that map to that library: button, input, select, dialog, popover,
  tooltip, tabs, table, toast, and so on.
- **Icons: Lucide.**
- **Design tokens must be semantic** (`surface`, `ink`, `primary`, `accent`, `danger`, `warning`,
  `success`, `border`, `focus`, `muted`) rather than raw colors. They become CSS variables.
- **Design for desktop only (1440 px).** No mobile mockups are needed. The build still adapts
  every screen to a phone's width (a single column, a collapsible navigation, a composer that
  fits), and one automated check at 390 px confirms nothing overflows. Many visitors open a
  portfolio link on a phone first, so the app must work there, but it doesn't need its own design.

---

## Starting points and genre

**Design our own system; don't adopt Material, Carbon, or another branded system.** Each has a
strong visual identity of its own: an app built on Material reads as Google's, one built on Carbon
as IBM's. The build already uses shadcn/ui on Radix, which provides structure and accessibility
(keyboard use, focus, screen readers) with a deliberately neutral look. The design restyles it.

**Borrow ideas, not visuals:**
- **GOV.UK Design System:** calm, plain, accessible forms, error messages, and serious content.
  The closest reference for the escalation and confidential-case tone.
- **Atlassian and Shopify Polaris:** dense admin tables, queues, and status, for the manager and
  HR screens.
- **Radix Colors:** 12-step color scales with steps meant for backgrounds, borders, and text. Pick
  the brand hues; the scales make accessible contrast easier to get right.

**Look at the genre, and copy none of it:** Rippling, Gusto, BambooHR, HiBob, Lattice, and Deel
for HR; Mercury and One Medical for "trustworthy" outside HR.

**What makes it read as a professional HR product:**
- **Restraint.** Neutrals do most of the work. The primary color is for actions; other colors
  appear only when they mean something. Hierarchy comes from type and spacing, not boxes and
  color.
- **Two densities.** Employee screens are roomy and calm. Manager and HR screens are denser:
  tables and queues.
- **Status that doesn't alarm.** Red is for errors only. A denied request is a decision, not an
  error: neutral styling with an icon and a label.
- **Confidential without being scary.** Case views get a quiet, distinct treatment, such as a lock
  icon and a slightly tinted surface, never an alert style.
- **Visible trust cues.** The AI label, citations, and "show your work" are part of the design,
  not fine print.
- **Unambiguous data.** Dates like "Fri, Oct 9", tabular figures for balances, and time zones
  shown where they matter.

**Avoid the genre's clichés:** flat cartoon-people illustrations, confetti or emoji celebrations,
anything cute near sensitive topics, and imagery or avatars that assume anyone's gender.

---

## Design system checklist

- **Color:** semantic tokens with light values, built from 12-step scales (see Radix Colors
  above), a structure ready for dark mode, and a small data-visualization palette for console
  charts.
- **Type:** a type scale (display, headings, body, small, caption), weights, line heights, and
  tabular numerals.
- **Spacing:** a 4 px-based scale.
- **Shape and depth:** radius scale, elevation or shadow scale, borders.
- **Motion:** durations and easing, plus reduced-motion variants.
- **Accessibility (WCAG 2.2 AA):**
  - Text contrast of at least 4.5:1, and 3:1 for large text and UI parts.
  - A visible focus ring on everything interactive.
  - Color never carries meaning alone; pair it with an icon or text.
- **Every component in every state:** default, hover, focus, active, disabled, loading, error, and
  empty where it applies.

### Standard components

These lists are a starting inventory, not a contract. Components are added or dropped as each
phase's screens need them.

Button (primary, secondary, ghost, destructive; sizes), text input, textarea, select, checkbox,
radio, switch, date picker (for time off), badge or chip, card, table, tabs, dialog, toast, tooltip,
avatar, skeleton loader, empty state, and page header.

### Assistant components (the heart of the product)

- **Composer:** the ask box, with send and **Stop** (while streaming), an input length hint, and
  starter chips.
- **Message:** a user message and an assistant message. The assistant message has a persistent
  **"AI" disclosure label**.
- **Streaming and status line:** "Searching the handbook…" or "Checking your balance…". It must feel
  alive during pauses of several seconds.
- **Citations:** an inline marker (like a superscript number), a **source chip** under the answer
  ("Handbook §4.3 · California addendum"), and a **source panel** that opens the cited passage with
  the quoted text highlighted.
- **"Show your work":** a collapsible trace under an answer listing the tools called, the sections
  retrieved, and the safety check result.
- **Confirm card:** the proposal the user must approve. It has these states:
  - pending: Confirm and Cancel buttons, and an expiry hint
  - confirmed or executed: an apricot success moment
  - canceled
  - expired
  - failed, with a reason

  Variants: a time-off request (dates, weekday, days, balance after), an approve or deny decision,
  and cancel a request. A confidential case is not a confirm card: the person sends it from the
  confidential-case form below (decided on 2026-10-26).
- **Escalation panel:** shown for a sensitive topic. It explains confidentiality in plain words and
  offers "Open a confidential case". It must feel supportive and serious, **never cute**.
- **Confidential-case form:** opens in the thread under the escalation or crisis panel, and on the
  "My cases" page. A category, the person's own words (prefilled from the message that raised the
  panel, editable), what is true about a case, and "Send to HR". The person sends it; the AI
  never opens a case.
- **Crisis panel:** fixed text with the 988 Suicide & Crisis Lifeline and the Employee Assistance
  Program. Clear, calm, and prominent.
- **Refusal message:** when the assistant can't share something ("I can't share Leo's home
  address"). Polite, brief, and not scolding.
- **Feedback:** a thumbs up or down per answer, with an optional reason.
- **Banners:** "Demo budget reached, showing a recorded walkthrough"; "Your sandbox expires in 3
  hours"; "Session expired".

---

## Screens, in the order they are needed

Design each screen in its **final** form. Nothing is deployed until the last phase, so the build
handles the in-between states (pages and data that don't exist yet) as cheaply as possible, and
the design never needs a temporary version.

**Phase 2** (needed first):
1. **Landing / "Try Open Door".** The pitch, a persona picker (four cards), a clear AI disclosure,
   a "fictional company, not legal advice, don't enter real personal info" notice, and a "Take the
   2-minute tour" entry. The tour arrives in Phase 7; the build hides its button until then.
2. **App shell.** Navigation (Ask, Time off, Directory, Handbook, Cases for HR, Console for HR,
   How it's built), the **persona switcher**, and a sandbox-expiry indicator. Design the full
   navigation; the build shows each item once its page exists.
   - **Switching persona** needs no confirmation, since it is the demo's main move. A short notice
     ("Now viewing as Marcus") confirms it, and the switcher says a switch starts a new
     conversation.
   - **Expiry:** a banner when 3 hours remain. When the sandbox expires, a "session expired"
     screen offers to start a new one.
3. **Assistant home.** A greeting, the ask box, starter chips for the current persona, and
   at-a-glance cards ("11.5 days PTO available", "1 approval waiting", "Handbook updated Sep 12").
   Until the assistant arrives in Phase 4, the build answers with a canned reply, and each card
   appears when its data does (Phase 3 for the handbook, Phase 5 for balances and approvals).
4. **Directory.** One people list for everyone, and a profile. Managers also get a "My team"
   filter, built with approvals in Phase 5. The profile shows the fields your role can't see as
   **locked rows with a short reason**, such as "Home address · Visible to Leo and HR": the field's
   name only, never its value.
5. **Global states.** Empty, loading, error, 404, session expired.

**Phase 3:**
6. **Handbook browser.** Section list, applicability badges ("Applies to: California", "Hourly
   staff"), and a deep-linked section with a highlighted cited passage.

**Phase 4:**
7. **Conversation view.** Streaming, the status line, inline citations with the source
   panel, "show your work", feedback, a refusal, the escalation stub, and the budget banner.

**Phase 5:**
8. **Time off.** Balances by type, my requests, and a request form.
9. **Manager approvals queue.**
10. **Confirm cards** in every variant and state (see above).

**Phase 6:**
11. **Escalation panel, confidential-case form, and "My cases".** The panel's case button, the form
    in every state, the sent state, and the person's own list of cases with their status.
12. **HR case queue and case detail.** Confidential styling: the queue shows no text, and the
    detail shows the AI summary with the person's own words hidden until HR reveals them.

**Phase 7:**
13. **AI Ops console.** A turn list, trace detail (guard verdict, tools, passages, citations,
    tokens, cost, latency), metric tiles (time to first token, cost per conversation, escalation
    rate), and the eval scoreboard.
14. **"How it's built".** Architecture diagram, the seven rules the AI never breaks, the live eval
    scoreboard, the standards followed, and a "request code access" link.
15. **Guided-tour overlay.** Step-by-step coach marks with one-click prompts.

**Brand assets (any time):** logo (an open-door motif is an obvious start, but keep it subtle),
favicon, and a social-share image.

---

## Decisions from the 2026-10-06 brainstorm

Claude Design proposed enhancements after the Phase 2 screens. These are settled with the owner:

- **Order of design work** follows the build order:
  1. the logo now;
  2. the handbook browser and passage panel before Phase 3's UI stage;
  3. the conversation view before Phase 4;
  4. then the time-off, escalation, and console screens before Phases 5, 6, and 7.

  The conversation view's source panel reuses the handbook passage view, so they're designed
  together.
- **Logo:** one round, with "door ajar" (a slim wedge of an open door) as the lead concept. It must
  be legible as a 16 px favicon, work in the lockup "Open Door · Juniper Row", use the token
  colors, and pass contrast on `surface` and `surface-raised`.
- **Passage panel:** show the section's "Applies to" label (for example "Applies to: California
  employees") and its "Last updated" date.
- **Feedback:** "Was this right?" per answer, with no thumb icons. It still feeds the eval backlog.
- **The sensitive hand-off says only what's true.** Before the person writes anything, it says:
  - only HR sees it, never managers;
  - it's stored encrypted;
  - when to expect a reply;
  - the AI writes HR a neutral summary with no recommendation.

  It must **not** say "the AI won't read it": the safety check reads every message, and HR's case
  summary is AI-written. A route that doesn't involve a manager is real, since managers never see
  cases.
- **No "delete this conversation."** Conversations are append-only and every AI action is audited.
  Show retention instead ("This sandbox and its conversations are deleted in 21 h"), and offer
  "Start a new conversation".
- **No "this policy changed since you last asked."** The assistant doesn't remember you between
  conversations, and the handbook is pinned for a sandbox's 24 hours. The "Last updated" date
  carries that information.
- **Hourly staff:** overtime and meal-break questions get cited handbook answers. The assistant
  never calculates overtime, and there's no shift-swap feature. Statutory figures are verified in
  Phase 3.
- **Spanish answers stay a stretch goal.**
- **New screens, in their phases:**
  - in Phase 5, team coverage beside a manager's approval: context only, never advice;
  - in Phase 7, the console's report of questions the handbook couldn't answer;
  - in Phase 7, the "design notes" idea, folded into the tour and the "How it's built" page.
- **Keyboard shortcuts** (`/` to focus the composer, ⌘K to jump to a page) are backlogged for
  Phase 8.

---

## Decisions from the Phase 6 planning (2026-10-26)

The [Phase 6 spec](../specs/2026-10-26-phase-6-cases-and-escalation.md) has the detail. For the
design of screens 11 and 12:

- **The person opens a case, not the AI.** The escalation panel's "Open a confidential case"
  button opens a form in the thread. The person picks a category, reviews their own words
  (prefilled from the message that raised the panel), reads what's true about a case, and presses
  "Send to HR". The crisis panel offers the same button below its fixed text. Nothing says "I can
  open a case for you".
- **The form says only what's true,** in fixed, owner-approved text: HR sees your name and your
  words; managers never see a case; it's stored encrypted; when HR replies; that Open Door's AI
  writes HR a short summary meant to be neutral, which Anthropic processes; that a person in HR
  reads your words before deciding anything; and 911, 988, and the EAP.
- **"My cases"** is a new nav item for everyone but HR: the person's cases with their status
  ("Sent to HR", "HR is reviewing", "HR has finished its review") and when HR replies, never the
  words. The same form opens from it.
- **HR's queue shows no text:** category, the person, location, sent date, reply-by, and status,
  with neutral labels for a reply that's due and for a case the safety check routed to crisis
  text. The Cases nav item counts new cases, and HR's home gains a cases card.
- **HR's case detail** shows the AI summary, labeled as the AI's, and hides the person's words
  behind "Show {first name}'s words". Each read is recorded and listed in the case's timeline.
  The status actions stay disabled until HR has read the words.
- **Confidential without being scary,** as above: a lock and a quiet tint, never an alert style.
  An overdue reply and the crisis fact are facts in neutral styling, not warnings.

---

## Voice and tone

Calm, plain, and specific. American English. No exclamation points, and no jokes about sensitive
topics.

Sample copy to design with. The policy figures here are placeholders for layout. The real handbook
figures are written and verified against official sources in Phase 3.

- **Answer:** "You get 40 hours (5 days) of paid sick leave each year, available from January 1.
  Unused hours don't carry over. ¹"
  - Source chip: "Handbook §4.3 · California addendum"
- **Confirm card:** "Book Friday, October 9 off? · 1 day of PTO · 10.5 days left after this" with
  the buttons **Confirm** and **Cancel**.
- **Refusal:** "I can't share another employee's home address. If you need to reach Leo, his work
  email is in the directory."
- **Escalation:** "This sounds like something a person on the HR team should help with. You can
  open a confidential case below. Only the HR team can open it in Open Door, never your manager,
  and it's stored encrypted. HR replies within 2 business days." (The owner approves the final
  text in Phase 6.)
- **Not found:** "I couldn't find that in the handbook. Want me to send the question to HR?"
- **Disclosure:** "Open Door is an AI assistant. It can make mistakes, and it always shows its
  sources."

## What to hand back

See [`README.md`](README.md) for the loop and the folder format. For each screen: desktop
screenshots per state, ideally with Claude Design's HTML export. Claude Code writes each screen's
`notes.md` and fills in `tokens.md` and `components.md` from the approved designs.
