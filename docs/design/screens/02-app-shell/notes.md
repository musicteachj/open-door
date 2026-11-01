# 02 · App shell

**Phase:** 2 · **Viewport:** desktop · **Personas:** everyone signed in

Approved on 2026-10-04. The working frames are in
[`../../system/App Shell.dc.html`](../../system/App%20Shell.dc.html), and the components' source
in [`../../system/components/navigation/`](../../system/components/navigation/) and
[`../../system/components/feedback/`](../../system/components/feedback/). The screenshots here were
rendered from that file. The shell's regions (sidebar, content sheet, right rail) are described in
[`../03-assistant-home/notes.md`](../03-assistant-home/notes.md). This screen adds the persona
menu, switching, the navigation for each persona, and the expiry banner.

**"How it's built" was dropped in Phase 7 (2026-10-31).** The screenshots below still show it;
the build leaves it out.

## Purpose

Let a visitor move around the app, see which persona they are exploring as, switch to another one,
sign out, and know when their sandbox is about to reset.

## Layout

- **Navigation, in the sidebar,** in this order: Ask, Time off, Directory, Handbook for everyone.
  Managers add Approvals, with a badge counting the requests waiting for them. HR adds Cases and
  Console. "How it's built" sits at the bottom, above the persona switcher.
- **The persona menu** opens upward from the switcher. It has a small "View as" label, the four
  personas (initials, name, role) with the current one tinted and checked, the note "Switching
  starts a new conversation.", a separator, and "Sign out".
- **The expiry banner** spans the top of the content sheet when 3 hours or less remain. It has a
  neutral background, the warning icon in `warning`, ink text, and a close button.
- **The toast** appears at the bottom right of the content sheet, with a success check and a close
  button.

## Components used

Nav item (with a count), Persona switcher (with a busy state), Persona menu, Banner, Toast, plus
everything on the assistant home.

## States

| State | Screenshot | What differs |
|---|---|---|
| Default | `desktop-default.png` | Priya's home |
| Persona menu | `desktop-persona-menu.png` | The menu open above the switcher, Priya checked |
| Switching | `desktop-switching.png` | The switcher busy after choosing Marcus |
| Switched | `desktop-switched-toast.png` | Marcus's home, with Approvals in the nav and the toast "Now viewing as Marcus Bell." |
| Expiry banner | `desktop-expiry-banner.png` | 2 h 50 min left; the rail's pill shows the same time |
| Employee nav | `desktop-nav-employee.png` | Priya and Mateo |
| Manager nav | `desktop-nav-manager.png` | Marcus, with Approvals and its count |
| HR nav | `desktop-nav-hr.png` | Dana, with Cases and Console |

## Interactions

- **Persona switcher:** opens the menu. Its accessible name always includes the full title, even
  when the visible title is truncated, and starts with what it shows: "Marcus Bell, Store
  Manager. Current persona. Switch persona" (WCAG 2.5.3, Label in Name; changed 2026-11-01).
- **Persona menu:** focus starts on the current persona, and the arrow keys move between items.
  The build adds what the sketch doesn't have: Escape and a click outside close the menu and
  return focus to the switcher (shadcn's dropdown menu does both). The personas are
  `menuitemradio`s, so screen readers hear which one is checked. Choosing the current persona just
  closes the menu.
- **Switching** calls `PUT /api/v1/session/persona`. While it runs, the switcher shows a spinner
  and a busy label on one line, truncated like the persona title ("Switching to Marcus…"; the
  mockup wraps it onto two lines, which the build fixes). Then the page reloads as that persona,
  with an empty composer, and the toast appears. There is no confirmation dialog.
- **Sign out** calls `DELETE /api/v1/session` with no confirmation and returns to the landing page.
- **Toast:** a polite status message, one sentence ending with a period. It closes after 6
  seconds, or with its close button. The build pauses the timer while it is hovered or focused, so
  everyone has time to read it. Errors never go in a toast; they appear inline beside what failed.
- **Expiry banner:** shown when 3 hours or less remain, with the time as "2 h 50 min" under 3 hours
  and hours only above. Dismissing it hides it for the rest of the session (kept in
  `sessionStorage`). It is a polite status message.
- **Navigation:** an item appears only once its page exists. The Approvals badge's accessible name
  includes the number ("Approvals, 1 waiting").

## Copy

- Menu: "View as", the four personas, "Switching starts a new conversation.", "Sign out"
- Busy switcher: "Switching to Marcus…"
- Toast: "Now viewing as Marcus Bell."
- Banner: "This sandbox resets in 2 h 50 min. Everything you've done here will be cleared."
- Nav: "Ask", "Time off", "Directory", "Handbook", "Approvals", "Cases", "Console", "How it's
  built"

**"Try asking" questions for each persona** (decided on 2026-10-04; the mockup shows Priya's and
Marcus's):

- **Priya:** "How many sick days do I get?", "Book next Friday off", "What holidays do we have
  this year?", "Who do I talk to about a concern?"
- **Mateo:** "How many sick days do I get?", "Do I get paid for holidays?", "Book next Friday
  off", "Who do I talk to about a concern?" (mostly the same as Priya's on purpose: the demo shows
  the same question getting a Texas answer)
- **Marcus:** "What's waiting for my approval?", "Who on my team is off this week?", "How many sick
  days do I get?", "Who do I talk to about a concern?"
- **Dana:** "Show me the open cases", "Which cases need a reply soon?", "What does the handbook say
  about reporting harassment?", "How has the assistant been doing this week?"

**At-a-glance figures** in the mockups, such as "14 days PTO available" and "3 open cases", are
placeholders. Balances arrive in Phase 5, with figures from the handbook's policy checked against
official sources, and cases arrive in Phase 6.

## Acceptance criteria

- [ ] Matches the screenshots at 1440 px, within the component library's spacing tokens
- [ ] Each persona sees exactly the nav items above, and an item appears only once its page exists
- [ ] The persona menu works by keyboard: it opens on the current persona, the arrow keys move,
      and Escape closes it and returns focus to the switcher
- [ ] Switching changes persona with no dialog, empties the composer, shows the busy label on
      one line, and then shows the toast
- [ ] The toast is announced, pauses while hovered or focused, and closes after 6 seconds or with
      its button
- [ ] Sign out ends the session and returns to the landing page
- [ ] The banner appears at 3 hours or less, stays dismissed for the session, and pairs the warning
      color with its icon and text
- [ ] axe reports no violations
