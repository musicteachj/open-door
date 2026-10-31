# Design handoff

The owner designs Open Door's interface in Claude Design. This folder is where those designs land,
and **it is the visual source of truth** for the build. Where a design here disagrees with a palette
or layout written anywhere else, the design wins.

## The loop

The owner works with Claude Design and Claude Code side by side, one screen per round, in phase
order. Each phase's screens are designed shortly before that phase is built, not all up front.

1. **Context, once.** Claude Code condenses [`BRIEF.md`](BRIEF.md) into a short context prompt,
   which the owner gives Claude Design at the start.
2. **Foundations first.** The first round designs one screen, the assistant home, to settle the
   look: colors, type, and core components. The approved look becomes a design-system project in
   Claude Design, which every later screen inherits.
3. **One screen per round.** Claude Code writes a focused prompt for the next screen: its purpose,
   the persona, the content (real names and data from the seed company), the states, and the copy.
4. **Review.** The owner brings back the result as screenshots or, better, Claude Design's HTML
   export, which carries the exact colors, type, and spacing. Claude Code reviews it against the
   brief, the decisions, and accessibility, and writes the follow-up prompt for any changes.
5. **Hand-off.** When the owner approves a screen, Claude Code saves it here and writes its
   `notes.md`, including the acceptance criteria. Approved screens are committed in small batches.
6. **Build and compare.** The build implements the screen, Playwright captures it at 1440 px and
   390 px, and the owner reviews design and build side by side until they match.

The exported HTML is a reference for the build, not code to ship: the app is built with shadcn/ui
and Tailwind. Once Phase 2 builds the real component library, the `/design-sync` command, which the
owner starts, can push it into the Claude Design design-system project. From then on, later phases
are designed with the components that actually ship.

## The gate

**A phase with new screens is designed right after its planning, and no build stage starts until
its screens are in `screens/`,** backend stages included. The planning writes the Claude Design
prompts; the owner designs and approves each screen; Claude Code syncs it here with its
`notes.md`. (Before Phase 7, only a phase's UI stage waited.)

| Needed by | Screens |
|---|---|
| Phase 2 | The design system (`tokens.md`, `components.md`), landing, app shell, assistant home, directory, global states |
| Phase 3 | Handbook browser and the passage panel (designed, in `screens/06-handbook/`) |
| Phase 4 | Conversation view, refusal, escalation stub, budget banner (designed, in `screens/07-conversation/`) |
| Phase 5 | Time off, approvals queue, confirm cards in every state (designed, in `screens/08-time-off/`, `screens/09-approvals/`, and `screens/10-confirm-cards/`) |
| Phase 6 | Escalation panel, confidential-case form, and "My cases"; HR case queue and case detail (designed, in `screens/11-escalation-cases/` and `screens/12-hr-cases/`) |
| Phase 7 | AI Ops console, "How it's built", guided tour (to be designed in `screens/13-ai-ops-console/`, `screens/14-how-its-built/`, and `screens/15-guided-tour/`) |

## Folder format

```
docs/design/
  BRIEF.md            the starting brief for Claude Design
  README.md           this file
  tokens.md           the design tokens (becomes Tailwind v4 @theme variables)
  components.md       the component inventory, with variants and states
  system/             the design system's source, exported from Claude Design: tokens,
                      component sketches, specimen pages, fonts, and the assistant home
  screens/
    01-landing/
      desktop-default.png
      desktop-persona-selected.png
      prototype.html      optional: Claude Design's HTML export, as a reference
      notes.md
    02-app-shell/
      …
```

- **Screen folders** are numbered in build order: `NN-short-name`.
- **Screenshots** are desktop only, 1440 px wide, named `desktop-state.png`, where the state is a
  short word: `default`, `loading`, `empty`, `error`, `streaming`, `confirmed`, and so on. There
  are no mobile mockups; the build adapts each screen to a phone's width on its own (see
  [`BRIEF.md`](BRIEF.md)).
- **Each `notes.md`** follows [`screens/_TEMPLATE.md`](screens/_TEMPLATE.md). Claude Code writes
  it from the approved design and the review, and the owner checks it. Its acceptance criteria
  become that screen's definition of done in the build.
- **`tokens.md`** is filled in from the design-system project's exact values, taken from the HTML
  export or listed by Claude Design as text, never guessed from a screenshot.
