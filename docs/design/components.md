# Component inventory

**Status: waiting for the design system from Claude Design.** Each component lists its variants and
the states it must be designed in. This is a living inventory, not a contract: add or drop
components as each phase's screens need them. A check means the design for it has landed in this folder. The
build then implements it in the component gallery before any screen uses it.

## Standard components

| Component | Variants | States | Designed |
|---|---|---|---|
| Button | primary, secondary, ghost, destructive; sm, md, lg | default, hover, focus, active, disabled, loading | [ ] |
| Text input / textarea | with label, helper, error | default, focus, disabled, error | [ ] |
| Select | | default, open, focus, disabled, error | [ ] |
| Checkbox / radio / switch | | default, checked, focus, disabled | [ ] |
| Date picker | single date, range, half-day option | default, open, disabled days (weekends, holidays) | [ ] |
| Badge / chip | neutral, status, applicability | default | [ ] |
| Card | plain, interactive | default, hover, focus | [ ] |
| Table | dense, comfortable | default, empty, loading | [ ] |
| Tabs | | default, active, focus | [ ] |
| Dialog | | open | [ ] |
| Toast | success, error, info | | [ ] |
| Tooltip | | | [ ] |
| Avatar | image, initials | | [ ] |
| Skeleton loader | | | [ ] |
| Empty state | | | [ ] |
| Page header | with actions | | [ ] |

## Assistant components

| Component | Variants | States | Designed |
|---|---|---|---|
| Composer | home (large), conversation (docked) | empty, typing, sending, streaming (Stop visible), disabled (budget reached) | [ ] |
| Starter chips | per persona | default, hover, focus | [ ] |
| User message | | default | [ ] |
| Assistant message | with citations, with refusal, with not-found | streaming, complete, error | [ ] |
| AI disclosure label | | always visible | [ ] |
| Status line | | active, idle | [ ] |
| Citation marker + source chip | | default, hover, focus, active (panel open) | [ ] |
| Source panel | handbook passage, highlighted quote | open, loading | [ ] |
| "Show your work" trace | | collapsed, expanded | [ ] |
| Confirm card | time-off request, approve/deny, cancel request, open case | pending, executed, canceled, expired, failed | [ ] |
| Escalation panel | sensitive topic | default, case offered, case opened | [ ] |
| Crisis panel | | default (fixed text) | [ ] |
| Feedback control | | default, up selected, down selected (reason form) | [ ] |
| Banner | budget reached (replay mode), sandbox expiring, session expired | | [ ] |
| Persona switcher | | closed, open, switching | [ ] |
