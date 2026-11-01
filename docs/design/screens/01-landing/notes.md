# 01 · Landing: "Try Open Door"

**Phase:** 2 · **Viewport:** desktop · **Personas:** a visitor who isn't signed in yet

Approved on 2026-10-04. The working frames are in
[`../../system/Landing.dc.html`](../../system/Landing.dc.html), and the persona card's source in
[`../../system/components/landing/`](../../system/components/landing/). The screenshots here were
rendered from that file.

## Purpose

Explain the product in a few seconds to a recruiter or hiring manager, then get them into a
private sandbox as one of the four personas with a single click.

**"How it's built" was dropped in Phase 7 (2026-10-31).** The screenshots below still show it;
the build leaves it out.

## Layout

One 1168 px column on the porcelain background, top to bottom:

1. **Header:** the logo with "Open Door" (no customer name before sign-in), and "How it's built"
   on the right.
2. **Pitch:** the tagline as the display heading, and one paragraph in `body-lg` and `ink-muted`.
3. **Persona picker:** "Choose who to be", then four persona cards in a row. Each card has
   initials, the name, the role, the location with a map-pin icon, a rule, one line on what to
   try, and "Start as Priya →".
4. **Under the picker,** in one quiet row: the sandbox note on the left, and "Take the 2-minute
   tour" as a secondary button on the right.
5. **Footer,** above a rule: the AI disclosure, and the fictional-company notice.

## Components used

Logo, Persona card (new), Inline error, Button (secondary for the tour and for Retry), Icon.

## States

| State | Screenshot | What differs |
|---|---|---|
| Default | `desktop-default.png` | The full page |
| Hover and focus | `desktop-hover-focus.png` | Priya's card hovered (its border darkens to `input-border-hover`), Mateo's focused (the ring) |
| Starting | `desktop-starting.png` | Priya's card has the primary border, a spinner, and "Setting up Juniper Row…"; the other cards are disabled |
| Error | `desktop-error.png` | Cards enabled again, and "We couldn't start a sandbox." with Retry under the grid |

## Interactions

- **Each persona card is one button.** Its accessible name is "Priya Raman, Visual Merchandiser,
  Oakland store." followed by the card's prompt and "Start as Priya". It is named from the card's
  own text, so it starts with what the card shows (WCAG 2.5.3, Label in Name; changed
  2026-11-01, when axe-core 4.14 began checking it).
- **Selecting a card** calls `POST /api/v1/sandboxes` with that persona. The card shows the
  starting state (`aria-busy`), announced in a polite live region, and the other cards are
  disabled. On success the visitor lands on the assistant home as that persona. It usually
  takes under two seconds.
- **On failure** every card is enabled again, the inline error appears under the grid, and Retry
  starts the same persona again.
- **The spinner** is the design system's only motion, and it stops under
  `prefers-reduced-motion`.
- **"How it's built" and the tour button** are designed now but hidden until Phase 7 builds
  their destinations.
- **On a narrow screen** the cards wrap, at about 240 px each, down to one column.

## Copy

- Header link: "How it's built"
- Heading: "Your open-door policy, now always open."
- Pitch: "An AI help desk for HR questions. It answers with citations to the company handbook,
  proposes actions for a person to confirm, and sends sensitive topics like harassment or
  medical leave to a human HR partner."
- Picker heading: "Choose who to be"
- Cards:
  - Priya Raman, Visual Merchandiser, Oakland store: "Ask about California sick leave and book
    a day off." "Start as Priya"
  - Mateo Alvarez, Warehouse Associate, Austin warehouse: "Ask the same questions and get Texas
    answers." "Start as Mateo"
  - Marcus Bell, Store Manager, Oakland store: "Approve a request and check on your team."
    "Start as Marcus"
  - Dana Whitfield, HR Business Partner, Denver HQ: "See the confidential case queue." "Start as
    Dana"
- Starting: "Setting up Juniper Row…"
- Error: "We couldn't start a sandbox." Button: "Retry"
- Sandbox note: "Each visit gets its own private copy of Juniper Row, a fictional company. It
  resets after 24 hours."
- Tour: "Take the 2-minute tour"
- AI disclosure: "Open Door is an AI assistant. It can make mistakes, and it always shows its
  sources."
- Notice: "Juniper Row and everyone in it are fictional. This is a demo, not legal advice. Don't
  enter real personal information."

## Acceptance criteria

- [ ] Matches the screenshots at 1440 px, within the component library's spacing tokens
- [ ] Usable at 390 px: the cards stack, and nothing overflows
- [ ] Each persona card is a single button with the accessible name above, reachable by keyboard
      and showing the focus ring
- [ ] Selecting a card starts that persona's sandbox and lands on the assistant home
- [ ] While starting, the card is busy and announced, and the other cards are disabled
- [ ] A failed start re-enables the cards and shows the inline error with a working Retry
- [ ] The AI disclosure and the fictional-company notice are always visible
- [ ] The spinner stops under `prefers-reduced-motion`; axe reports no violations

## Later

Once the conversation view is designed (Phase 4), consider a small, real preview of a cited answer
in the empty space beside the pitch, so a visitor sees the product before choosing a persona.
