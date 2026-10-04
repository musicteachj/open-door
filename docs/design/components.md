# Component inventory

**Status: the first components are designed (2026-10-04).** Each component lists its variants and
the states it must be designed in. This is a living inventory, not a contract: add or drop
components as each phase's screens need them.

The designed components' source is in [`system/components/`](system/components/). Each one has
a React sketch (`Name.jsx`), its props (`Name.d.ts`), and a usage note (`Name.prompt.md`), and
each folder has a specimen page (`*.card.html`). They are a reference for the build, which
implements them with shadcn/ui and Tailwind, not code to ship.

In the "Designed" column, a check means every listed state is designed, and "partly" names what
is still missing. A check means the design for it has landed in this folder. The
build then implements it in the component gallery before any screen uses it.

## Standard components

| Component | Variants | States | Designed |
|---|---|---|---|
| Button | primary, secondary, ghost, destructive; 40 px and 32 px | default, hover, focus, active, disabled, loading | partly: no loading state yet |
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
| Tooltip | | default | [x] |
| Avatar | image, initials | | [ ] |
| Skeleton loader | | | [ ] |
| Empty state | | | [ ] |
| Page header | with actions | | [ ] |

## Assistant components

| Component | Variants | States | Designed |
|---|---|---|---|
| Composer | home (large), conversation (docked) | empty, hover, focus, typing, error, sending, streaming (Stop visible), disabled (budget reached) | partly: home variant at rest, hover, focus, typed, and with an error; the docked variant and the sending, streaming, and disabled states come with Phase 4 |
| "Try asking" list (was starter chips) | per persona | default, hover, focus | [x] |
| User message | | default | [ ] |
| Assistant message | with citations, with refusal, with not-found | streaming, complete, error | [ ] |
| AI disclosure label | in the composer; on each assistant message | always visible | partly: the composer line; the per-message label comes with Phase 4 |
| Status line | | active, idle | [ ] |
| Citation marker + source chip | | default, hover, focus, active (panel open) | [ ] |
| Source panel | handbook passage, highlighted quote | open, loading | [ ] |
| "Show your work" trace | | collapsed, expanded | [ ] |
| Confirm card | time-off request, approve/deny, cancel request, open case | pending, executed, canceled, expired, failed | [ ] |
| Escalation panel | sensitive topic | default, case offered, case opened | [ ] |
| Crisis panel | | default (fixed text) | [ ] |
| Feedback control | | default, up selected, down selected (reason form) | [ ] |
| Banner | budget reached (replay mode), sandbox expiring, session expired | | [ ] |
| Persona switcher | | closed, hover, focus, truncated title with tooltip, open, switching | partly: the closed states; the open menu and switching come with the app shell |

## Shell and status components

Added by the design system for the assistant home.

| Component | Variants | States | Designed |
|---|---|---|---|
| Logo | mark with the product and customer names | default | [x] |
| Icon | the Lucide icons in use | default | [x] |
| Nav item | | current, default, hover (neutral), focus | [x] |
| At-a-glance link and list | figure, label, and named destination | default, hover, focus | [x] |
| Sandbox indicator | pill | default | [x] |
| Inline error | under the composer, with Retry | default | [x] |
