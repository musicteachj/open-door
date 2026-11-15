# Accessibility

What Open Door does to meet WCAG 2.2 at level AA, how it is checked, what the audit of 2026-11-14
found, and what is still open. The audit is Phase 8, stage 8 (Tasks 41 and 42 of the Phase 8 plan).

Everything here runs in the browser suite (`make e2e`, and `make e2e-image` against the production
image with its real Content Security Policy), so it runs in `make check` and in CI on every pull
request. The browser is Chromium only. A real screen reader is not automated: the owner's
VoiceOver checklist at the end covers that.

## How it is checked

### axe, on every page and every gallery state

[axe](https://github.com/dequelabs/axe-core) scans the real pages in each flow's own browser test,
and every state of the component gallery, with the tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`,
and `wcag22aa` (`AXE_TAGS` in `apps/web/e2e/helpers.ts`). A rule is turned off only where its reason
is written beside it.

### The audit's own checks, for what axe doesn't measure

They live in `apps/web/e2e/accessibility/`. `checks.ts` holds the checks; `checks.spec.ts` proves
each one on a small page of its own, once clean and once with a planted failure, so a check that
stops catching anything fails there.

| Check | WCAG | How |
|---|---|---|
| Reflow | 1.4.10 | At 320 px wide (1280 px at 400% zoom), the page doesn't scroll sideways and nothing reaches past the window, except inside a region that scrolls on its own (the scoreboard's tables) or text the design truncates with an ellipsis or a line clamp. A wrapper that only clips doesn't excuse anything: what it cuts off is lost. |
| Text spacing | 1.4.12 | Applies the criterion's spacing (line height 1.5, paragraphs 2em apart, letters 0.12em, words 0.16em) and reports any text that overflows its box with it but didn't without it: cut short with an ellipsis, clipped, or spilling out. |
| Reduced motion | 2.3.3 | With `prefers-reduced-motion: reduce`, nothing on the page is animating. |
| Target size | 2.5.8 | Every control is at least 24 by 24 px, or has room for a 24 px circle that touches no other target and no other small target's circle. A link or marker inside a sentence is exempt, as the criterion allows. |
| Focus not obscured | 2.4.11 | At each Tab stop of a keyboard walk, the focused element is not entirely behind the sticky header, the composer, or the coach mark. A stop that shows only in part is noted on the test. |
| Focus visible | 2.4.7 | At each Tab stop, the element or a close ancestor draws a focus ring, once any transition has finished: a 2 px outline, or a shadow in the focus ring's color at any opacity (a text box's halo). A shadow a card has at rest doesn't count. |

`pages.spec.ts` runs the first four on every page and on the states a person reaches on the main
flows, at 1280 px and again at 320 px: the landing page, the assistant's home, a cited answer with
its source open, the HR panel and the case form, the crisis panel, a confirm card, Time off with
the request form, Approvals with a decision dialog, My cases, the HR case queue, a case with the
person's words shown, the console with a turn's trace, the directory and a profile, the handbook
and a section, the not-found page, and the tour's first step. `narrow.spec.ts` also checks every
gallery state at 320 px.

### Keyboard walks

`keyboard.spec.ts` does each main flow with the keyboard alone (Tab, Shift+Tab, the arrow keys,
Enter, Space, and Escape; no clicks), and asserts where focus is at each step:

1. Start a sandbox from the landing page.
2. Ask a question, open its source, read it (title, Close, the passage, "Open in handbook"), and
   close it with Escape, back to the source.
3. At 390 px, the source sheet keeps focus inside it until it closes.
4. Book a day off in chat and confirm the card.
5. Book a day off on the Time off page, picking the day with the arrow keys.
6. Approve a request as the manager, in the confirm dialog.
7. Send a confidential case from the HR panel.
8. Review a case as HR: open it, show the person's words, and a status dialog.
9. Open a turn's trace in the console, and Escape back to its row.
10. The tour: start it, send a step's question, Next across a persona switch, leave, and resume.

### Contrast

`apps/web/src/styles/contrast.test.ts` reads the colors from `theme.css` and checks every pair in
the contrast table of [`design/tokens.md`](design/tokens.md), plus the pairs the components use
that the table leaves out: 4.5:1 for text, 3:1 for large text and for the parts of a control or an
icon that carry meaning. It also fails if the table's stated ratios drift from the tokens, row by
row and in order.

### Running them

```
cd apps/web
npx playwright test e2e/accessibility                      # the audit's browser checks
E2E_TARGET=image npx playwright test e2e/accessibility     # the same against the test image
npx vitest run src/styles/contrast.test.ts                 # the contrast pairs
```

The browser checks take about a minute on one worker locally (about 50 tests, the gallery's 320 px
sweep included), and about 20 seconds with the default workers. They use the scripted model, so
they cost nothing.

## What the audit found

Severity: **high** means a main flow can't be finished with the keyboard or a screen reader, or a
focused control is entirely hidden. **Medium** is any other AA failure. **Low** is best practice,
a partly covered control, or cosmetic.

Clean: reflow at 320 px on every page and gallery state, reduced motion, target size, every
contrast pair, and the keyboard walks for starting a sandbox, the source sheet's focus, the Time
off form, approvals, reviewing a case, and the console.

| | Finding | Severity | Status |
|---|---|---|---|
| H1 | On the conversation page, Tab could land on a control entirely behind the sticky composer: the HR panel's contact links, the "How confidential HR cases work" link, a confirm card's Confirm, the case form's "Your words". At a 900 px high window, "Show your work" under the HR panel stayed behind the composer even at rest. | High | Fixed: everything in the thread has a scroll margin of the header's and the composer's heights, so the browser scrolls a focused control clear of them, and a text box focused from the keyboard is brought clear as well. A reader following the answer is taken to the end again when the last turn grows after it ended. A focused control the page pushes behind the composer (an error appearing above "Send feedback") is brought clear. (Scroll padding on the whole page was tried first and dropped: focusing the composer or the header's button then scrolled the page.) |
| M1 | "Resume the tour" in the persona menu moved focus to the step's title, then the closing menu took it back to the persona switcher, so a screen reader didn't read the step. | Medium | Fixed: the menu returns focus to the switcher only when nothing else has taken it. |
| M2 | The passage panel's Tab order was title, passage, Close; screen 07's notes say title, Close, the passage, "Open in handbook". | Medium | Fixed: Close comes after the title in the page, in the same place on screen. |
| L1 | With 1.4.12's spacing, labels the design already truncates are cut short sooner: the persona switcher's name and title, the directory's titles and locations, source chips and rule chips at 320 px. The full words are each one's accessible name and a step away (the persona menu, the profile, the passage). | Low | Accepted. `pages.spec.ts` lists it, so a new truncation still fails. |
| L2 | With the spacing, a few words spill a few pixels past their box, readable and touching nothing: the case queue's "Sent" date, the console's cost cell, a scoreboard row header, a handbook section title at 320 px, and the retention line beside an open passage, which wraps a word a line. | Low | Accepted, listed in `pages.spec.ts` like L1. |
| L3 | At 390 px, the phone nav's "Directory" link shows about 58% when focused, inside the nav's own sideways scroll. | Low | Open, in the backlog. |
| L4 | `marker` on `primary-tint` is 2.8:1. It is used only to decorate: the cited passage's edge bar, and the rail's dot on hover. | Low | Accepted: decoration needs no contrast. |
| L5 | `tokens.md` gave the marker clock 3.6:1; it is 3.5:1. | Low | Fixed in the table. |
| L6 | At 320 px, Time off's balance cards reach 329 px: the grid keeps a 300 px column, so the sheet cuts off each card's right padding and border. Every word and figure still shows. | Low | Fixed with the owner's OK: the column is at most the space there is, so the cards fit at 320 px; nothing changes at 390 px or wider. |

## Known gaps

- **The walkthrough page** (Phase 8, stage 9) doesn't exist yet. Stage 9 adds it to
  `pages.spec.ts` and gives it a keyboard walk of its own.
- **Only Chromium runs.** Safari and Firefox are not automated. The VoiceOver checklist below is
  in Safari.
- **No screen reader is automated.** The checks assert names, roles, focus, and live regions, which
  is what a screen reader reads, but how it is spoken is checked by hand.
- The open and accepted lows above: L1 to L4.

## VoiceOver checklist (about 15 minutes)

For the owner, in Safari on a Mac, with VoiceOver on (Command+F5). VO means Control+Option. Start
from the landing page in a fresh window.

1. **Landmarks and headings.** Open the rotor (VO+U), and look at Landmarks, then Headings. The
   landing page has a main landmark and a first-level heading. After starting as Priya, each page
   has a navigation landmark, a main landmark, and a first-level heading.
2. **Starting a sandbox.** Tab to a persona and press Enter. VoiceOver says the new page's title,
   and focus is in the composer, which is read as "Ask Open Door".
3. **A streamed answer.** Ask "How many sick days do I get?". The answer is read once when it
   finishes, not word by word, and the source chips and "Was this right?" follow it.
4. **A source.** Tab to "Source 1" and press Enter. VoiceOver reads the panel's title ("Sick
   leave"). Tab reaches Close, then the passage text, then "Open in handbook". Escape closes the
   panel and VoiceOver is back on the source.
5. **The HR panel.** Ask "My manager keeps commenting on how I look and it's making me
   uncomfortable." VoiceOver announces the panel's heading. Tab through it: each contact link and
   "Show your work" are visible on screen as VoiceOver reads them.
6. **The case form.** Choose "Open a confidential case": the form's heading is read, and the box
   holds your question. Send it without choosing what it's about: VoiceOver reads "Choose what this
   is about." and focus moves to the choices. Choose one and send: "Sent to HR." is read.
7. **A confirm card.** Ask "book next friday". VoiceOver reads the card. Confirm it: the outcome
   ("Requested.") is read and focus is on it.
8. **The crisis panel.** Ask something with "hurt myself" in it. The panel's fixed words (the 988
   Lifeline, the EAP) are read in full, and 988 and 911 are read as links.
9. **The console.** Switch to Dana in the persona menu (the menu reads each persona and which is
   current), open Console, Tab to a turn's row, and press Enter: the trace's heading is read.
   Escape returns to the row.
10. **The tour.** Start the 2-minute tour from the persona menu. Each step's title is read when it
    shows. Press Escape to leave, then "Resume the tour" in the persona menu: the step's title is
    read again.

Note anything VoiceOver reads wrongly, twice, or not at all, with the step's number.
