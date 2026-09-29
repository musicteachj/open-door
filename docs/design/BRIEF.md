# Open Door: design brief for Claude Design

This brief is self-contained. Paste it, or the sections you need, into Claude Design to start the
design system and screens. Hand the results back as described in [`README.md`](README.md).

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

Visitors switch between these personas inside a private sandbox that lasts 24 hours.

## How it should feel

**Calm and trustworthy: a safe place to ask a sensitive question.** Quiet confidence, not
excitement. Generous whitespace, clear hierarchy, and nothing that shouts. It should feel warm
without being cute, and credible without being cold, like good healthcare or banking software
rather than a social app.

**Starting direction** (a starting point; your design system replaces it):

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
- indigo with gold
- magenta
- forest green on warm paper
- navy or bright blue
- black with lime
- dark safety-orange consoles

Don't use these fonts: Plus Jakarta Sans, Inter, IBM Plex, Newsreader, DM Mono, JetBrains Mono.

## Technical constraints the design should fit

- **Built with React, Tailwind CSS v4, and shadcn/ui** (Radix primitives), restyled to your design
  system. Design components that map to that library: button, input, select, dialog, popover,
  tooltip, tabs, table, toast, and so on.
- **Icons: Lucide.**
- **Design tokens must be semantic** (`surface`, `ink`, `primary`, `accent`, `danger`, `warning`,
  `success`, `border`, `focus`, `muted`) rather than raw colors. They become CSS variables.
- **Desktop-first for managers and HR. Employee screens also need a mobile layout**, because
  store and warehouse staff use phones.

---

## Design system checklist

- **Color:** semantic tokens with light values, a structure ready for dark mode, and a small
  data-visualization palette for console charts.
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
  cancel a request, and open a confidential case (with a consent line).
- **Escalation panel:** shown for a sensitive topic. It explains confidentiality in plain words and
  offers to open a confidential case. It must feel supportive and serious, **never cute**.
- **Crisis panel:** fixed text with the 988 Suicide & Crisis Lifeline and the Employee Assistance
  Program. Clear, calm, and prominent.
- **Refusal message:** when the assistant can't share something ("I can't share Leo's home
  address"). Polite, brief, and not scolding.
- **Feedback:** a thumbs up or down per answer, with an optional reason.
- **Banners:** "Demo budget reached, showing a recorded walkthrough"; "Your sandbox expires in 3
  hours"; "Session expired".

---

## Screens, in the order they are needed

**Phase 2** (needed first):
1. **Landing / "Try Open Door".** The pitch, a persona picker (four cards), a clear AI disclosure,
   a "fictional company, not legal advice, don't enter real personal info" notice, and a "Take the
   2-minute tour" entry.
2. **App shell.** Navigation (Ask, Time off, Team, Handbook, Cases for HR, Console for HR, How it's
   built), the **persona switcher**, and a sandbox-expiry indicator.
3. **Assistant home (mobile too).** A greeting, the ask box, starter chips for the current persona,
   and at-a-glance cards ("11.5 days PTO available", "1 approval waiting", "Handbook updated Sep
   12").
4. **Directory.** A people list and a profile. The profile shows which fields you can and can't see
   for your role.
5. **Global states.** Empty, loading, error, 404, session expired.

**Phase 3:**
6. **Handbook browser.** Section list, applicability badges ("Applies to: California", "Hourly
   staff"), and a deep-linked section with a highlighted cited passage.

**Phase 4:**
7. **Conversation view (mobile too).** Streaming, the status line, inline citations with the source
   panel, "show your work", feedback, a refusal, the escalation stub, and the budget banner.

**Phase 5:**
8. **Time off (mobile too).** Balances by type, my requests, and a request form.
9. **Manager approvals queue.**
10. **Confirm cards** in every variant and state (see above).

**Phase 6:**
11. **Escalation panel and confidential-case confirm.**
12. **HR case queue and case detail.** Confidential styling, with redacted content where
    appropriate.

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
- **Escalation:** "This sounds serious, and you deserve a person's attention, not an AI's. I can
  open a confidential case with HR. Only the HR team will see it."
- **Not found:** "I couldn't find that in the handbook. Want me to send the question to HR?"
- **Disclosure:** "Open Door is an AI assistant. It can make mistakes, and it always shows its
  sources."

## What to hand back

See [`README.md`](README.md) for the folder format. For each screen: PNG screenshots per state and
viewport, plus a `notes.md` with its purpose, layout, components used, states, interactions, exact
copy, and **acceptance criteria**. For the system: `tokens.md` and `components.md`.
