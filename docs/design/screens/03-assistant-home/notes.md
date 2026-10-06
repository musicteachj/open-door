# 03 · Assistant home

**Phase:** 2 · **Viewport:** desktop · **Personas:** everyone; designed for Priya

Approved on 2026-10-04. The live version is
[`../../system/ui_kits/assistant/index.html`](../../system/ui_kits/assistant/index.html), and how
it was chosen (two directions, then eight palettes) is in
[`../../system/Assistant Home.dc.html`](../../system/Assistant%20Home.dc.html). The screenshots
here were rendered from the final export at 1440 px.

## Purpose

The home screen, where a person asks the assistant a question or picks one to start with, and sees
the few figures that matter to them at a glance.

## Layout

Three regions on the porcelain background, left to right:

1. **Sidebar, 248 px.** The logo with "Open Door" and the customer name (Juniper Row); the
   navigation (Ask, Time off, Directory, Handbook); and, pinned to the bottom, "How it's built"
   and the persona switcher.
2. **Content sheet.** White, inset 12 px from the window, 16 px radius. A 760 px measure holds the
   greeting, the composer (with the AI disclosure and the Ask button in its footer), and the
   "Try asking" list in two columns.
3. **Right rail, 340 px,** on `surface-sunken`. The sandbox indicator at the top, then "At a
   glance": up to three figures, each a link that names its destination.

**On a narrow screen** (a first pass, not a reviewed design; see
[`narrow-first-pass.png`](narrow-first-pass.png)): below 760 px the sidebar becomes a top bar,
the "Try asking" list becomes one column, and the rail moves below the content. The build must
fix two things there: the top navigation clips its last item with no sign that it scrolls, and
the sandbox indicator should move up near the persona instead of sitting at the bottom of the
page.

## Components used

From [`../../components.md`](../../components.md): Logo, Nav item, Persona switcher with Tooltip,
Composer (home variant), AI disclosure label, Button (primary "Ask", secondary small "Retry"),
Inline error, "Try asking" list, At-a-glance link and list, Sandbox indicator.

## States

| State | Screenshot | What differs |
|---|---|---|
| Default | `desktop-default.png` | Priya's home, composer empty |
| Composer | `desktop-composer-states.png` | At rest; focused with "How many sick days do I get?" typed (primary border and halo); the inline error after a failed send; a hovered and a focused "Try asking" row |
| At a glance | `desktop-glance-states.png` | A hovered link (tint, underlined destination) and a focused one (ring) |
| Navigation | `desktop-nav-states.png` | Current, default, hovered (neutral gray, never the tint), focused; the persona switcher with a short title, and a truncated title with its tooltip |
| Narrow | `narrow-first-pass.png` | The 390 px first pass described above |

## Interactions

- **Tab order:** logo, nav items, "How it's built", persona switcher, composer, Ask, the "Try
  asking" rows (row by row), the at-a-glance links. Every control shows the 2 px aubergine focus
  ring, offset 2 px, via `:focus-visible`.
- **Composer:** Enter sends, and Shift+Enter adds a line. The Ask button stays enabled when the box
  is empty, and pressing it then moves focus into the box instead of sending.
- **"Try asking" row:** fills the composer with the question, without sending it, so the person
  can edit it first. Ask sends it.
- **Failed send:** the question stays in the box, an inline error appears under the composer, and
  Retry sends it again. The error is announced to screen readers (`role="alert"`).
- **Persona title:** truncates to one line. Hovering or focusing it shows the full title in a
  tooltip, only when it is actually cut off.
- **At-a-glance link:** the whole row is the link, so its accessible name includes the figure and
  the destination.
- **Greeting:** "Good morning", "Good afternoon", or "Good evening", by the location's local time.
- **Until Phase 4,** the assistant gives a canned reply through the fake transport. Each
  at-a-glance figure appears once its data exists: the handbook date in Phase 3, the balance and
  pending requests in Phase 5.

## Copy

- Greeting: "Good morning, Priya."
- Composer placeholder: "Ask about time off, pay, benefits, or policy…"
- AI disclosure: "Open Door is an AI assistant. It can make mistakes, and it always shows its
  sources."
- Button: "Ask"
- "Try asking" label, then the rows: "How many sick days do I get?", "Book next Friday off",
  "What holidays do we have this year?", "Who do I talk to about a concern?"
- "At a glance" label, then: "11.5" "days PTO available" → "Time off"; "1" "request pending" →
  "Time off"; "Sep 12" "Handbook updated" → "Handbook". The figures are sample data.
- Sandbox indicator: "Sandbox resets in 21 h"
- Error: "Something went wrong sending that." Button: "Retry"

## Acceptance criteria

- [ ] Matches the screenshots at 1440 px, within the component library's spacing tokens
- [ ] Usable at 390 px: nothing overflows, the navigation shows that it scrolls, and the sandbox
      indicator is near the top
- [ ] Every interactive element is reachable by keyboard in the order above and shows the focus
      ring, including on the persona switcher and the at-a-glance links
- [ ] Text contrast meets WCAG 2.2 AA, and the composer border meets 3:1; axe reports no
      violations
- [ ] Nav hover uses `neutral-hover`, never `primary-tint`; the current page alone uses the tint
- [ ] The cinnamon marker appears only beside text, never as text and never alone
- [ ] The AI disclosure is always visible in the composer
- [ ] A failed send keeps the question, shows the inline error with Retry, and announces it
- [ ] A long persona title truncates and shows its tooltip only when cut off
- [ ] No transitions under `prefers-reduced-motion`
