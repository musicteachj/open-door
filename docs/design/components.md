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
| Button | primary, secondary, ghost, destructive; 40 px and 32 px | default, hover, focus, active, disabled, loading | partly: the loading state is built, not designed (a spinner before the label; it stays focusable) |
| Text input / textarea | with label, helper, error | default, focus, disabled, error | partly: the search field (see Forms below); labeled form fields come with Phase 5 |
| Select | | default, open, focus, disabled, error | partly: the filter select (see Forms below) |
| Checkbox / radio / switch | | default, checked, focus, disabled | [ ] |
| Date picker | single date, range, half-day option | default, open, disabled days (weekends, holidays) | [ ] |
| Badge / chip | neutral, status, applicability | default | partly: the neutral "You" tag and the applicability badge (see Handbook below); status badges come with Phase 5 |
| Card | plain, interactive | default, hover, focus | [ ] |
| Table | dense, comfortable | default, empty, loading | partly: the directory list (see Directory below) |
| Tabs | | default, active, focus | [ ] |
| Dialog | | open | [ ] |
| Toast | success; errors go inline, not in a toast | default, closing | [x] |
| Tooltip | | default | [x] |
| Avatar | initials | default | [x] |
| Skeleton loader | directory row | default | [x] |
| Empty state | no search results, no filter results | default | partly: the directory's; other pages come with their screens |
| Page header | title with a count, or a back link | default | [x] |

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
| Source panel | handbook passage, highlighted quote | open, loading, error | [x] as the passage panel (see Handbook below); Phase 4 docks it beside the conversation |
| "Show your work" trace | | collapsed, expanded | [ ] |
| Confirm card | time-off request, approve/deny, cancel request, open case | pending, executed, canceled, expired, failed | [ ] |
| Escalation panel | sensitive topic | default, case offered, case opened | [ ] |
| Crisis panel | | default (fixed text) | [ ] |
| Feedback control | | default, up selected, down selected (reason form) | [ ] |
| Banner | budget reached (replay mode), sandbox expiring | default, dismissed | partly: sandbox expiring; the budget banner comes with Phase 4. A session that has expired gets a full page instead (see Feedback below) |
| Persona switcher | | closed, hover, focus, truncated title with tooltip, open, switching | [x] |

## Shell and status components

Added by the design system for the assistant home.

| Component | Variants | States | Designed |
|---|---|---|---|
| Logo | mark with the product and customer names | default | [x] |
| Icon | the Lucide icons in use | default | [x] |
| Nav item | with or without a count badge | current, default, hover (neutral), focus | [x] |
| At-a-glance link and list | figure, label, and named destination | default, hover, focus | [x] |
| Sandbox indicator | pill | default | [x] |
| Inline error | under the composer, with Retry | default | [x] |

## Landing, forms, and directory components

Added by the design system for the landing page and the directory.

| Component | Variants | States | Designed |
|---|---|---|---|
| Persona card | | default, hover, focus, starting, disabled | [x] |
| Search field | | empty, typed (with clear button), focus | [x] |
| Filter select | location, department; options with counts | default, open, active, focus | [x] |
| Filter toggle | "My team" with a count | off, on, focus | [x] |
| Directory list and row | | default, hover, focus, your own row ("You") | [x] |
| Detail list and row | value, link, locked (lock and reason) | default | [x] |

## Shell and feedback components

Added by the design system for the app shell and the global states.

| Component | Variants | States | Designed |
|---|---|---|---|
| Persona menu | | open, current checked, item hover and focus | [x] |
| Full-page message | inside the shell, outside it; with an optional reference | default | [x] |

## Handbook components

Added by the design system for the handbook browser and the passage panel (screen 06, Phase 3).
The source is in [`system/components/handbook/`](system/components/handbook/).

| Component | Variants | States | Designed |
|---|---|---|---|
| Applicability badge | everyone, state, employment type, location, combined ("Hourly staff in California") | default | [x] |
| Applies marker | "Applies to you", "Doesn't apply to you" | default | [x] |
| Last updated | | default | [x] |
| Section row and group | company chapter, state addendum; with or without the marker | default, hover, focus, current | [x] |
| Chapter navigator | chapter, addendum | default, current | [x] |
| Cited passage | on the section page (with "Clear highlight"), in the panel | default | [x] |
| Link block | "State rules", "Supplements" | default, hover, focus | [x] |
| Sources block | | default | [x] |
| Search result row | applies, doesn't apply | default, hover, focus | [x] |
| Passage panel | | open, loading, error, long passage (scrolls inside) | [x] |

**Built but not designed** (Phase 3, stage 4), each derived from the screenshots and
`handbook.css`, and shown in the gallery for the owner's review:
- **Section row at 390 px:** the number stays beside the title, and the audience, the marker,
  and the date stack under it (the notes say there's no mockup).
- **Chapter navigator:** no component sketch; built from `.od-sec-nav` and the section page.
- **Handbook blocks** (the section body: headings, paragraphs, lists, inline links): drawn only in
  the page screenshots.
- **The compact cited passage on its own:** drawn only inside the panel.
- **The panel's loading and error eyebrow without a section name:** "Handbook CA-4.3", when the
  host doesn't pass one.
