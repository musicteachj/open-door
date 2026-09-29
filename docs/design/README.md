# Design handoff

The owner designs Open Door's interface in Claude Design. This folder is where those designs land,
and **it is the visual source of truth** for the build. Where a design here disagrees with a palette
or layout written anywhere else, the design wins.

## The loop

1. The owner designs in Claude Design, starting from [`BRIEF.md`](BRIEF.md).
2. The results land here as screenshots plus written guidelines (format below).
3. The build implements them.
4. Playwright captures the built screens.
5. Design and build are compared side by side, and the owner reviews them.
6. Repeat until they match.

The `/design-sync` command, which the owner starts, can optionally keep the repo's component library
in sync with a Claude Design design-system project, one component at a time.

## The gate

**A phase's UI stage does not start until its screens are in `screens/`.** Backend stages do not
wait. Phases 0 and 1 have no UI, which gives the design track a head start.

| Needed by | Screens |
|---|---|
| Phase 2 | The design system (`tokens.md`, `components.md`), landing, app shell, assistant home, directory, global states |
| Phase 3 | Handbook browser |
| Phase 4 | Conversation view, refusal, escalation stub, budget banner |
| Phase 5 | Time off, approvals queue, confirm cards in every state |
| Phase 6 | Escalation panel, confidential-case confirm, HR case queue and detail |
| Phase 7 | AI Ops console, "How it's built", guided-tour overlay |

## Folder format

```
docs/design/
  BRIEF.md            the starting brief for Claude Design
  README.md           this file
  tokens.md           the design tokens (becomes Tailwind v4 @theme variables)
  components.md       the component inventory, with variants and states
  screens/
    01-landing/
      desktop-default.png
      desktop-persona-selected.png
      mobile-default.png
      notes.md
    02-app-shell/
      …
```

- **Screen folders** are numbered in build order: `NN-short-name`.
- **Screenshots** are named `viewport-state.png`, where the viewport is `desktop` (1440 px wide) or
  `mobile` (390 px wide) and the state is a short word: `default`, `loading`, `empty`, `error`,
  `streaming`, `confirmed`, and so on.
- **Each `notes.md`** follows [`screens/_TEMPLATE.md`](screens/_TEMPLATE.md). Its acceptance
  criteria become that screen's definition of done in the build.
