# Design tokens

**Status: approved on 2026-10-04.** The palette is "aubergine and cinnamon", from Wada Sanzo's *A
Dictionary of Color Combinations* (1933), combination 172. It was chosen in Claude Design from
eight palettes compared on the same assistant home. Type is Instrument Sans throughout.

**The exact values live in [`system/tokens/`](system/tokens/)**, as CSS custom properties with a
one-line comment each. This page summarizes them and records the contrast checks. The build turns
them into Tailwind v4 `@theme` variables, and components use tokens, never raw hex values.

The token names are semantic, so a dark theme can override the values later without renaming
anything. [`system/tokens/shadcn.css`](system/tokens/shadcn.css) maps shadcn/ui's variable names
onto these tokens. One name differs on purpose: shadcn's `--accent` is its hover fill and points
at `primary-tint`, so the brand's cinnamon accent is called `marker`.

## Color

| Token | Value | Use |
|---|---|---|
| `surface` | `#F5F7F8` | App background behind the content sheet |
| `surface-raised` | `#FFFFFF` | Content sheet, composer, cards, popovers |
| `surface-sunken` | `#F9FAFB` | Right rail and other recessed panels |
| `surface-hover` | `#F0F3F5` | Hover fill for secondary buttons |
| `neutral-hover` | `#ECEFF1` | Nav and persona switcher hover; never means selected |
| `ink` | `#14212A` | Primary text and icons |
| `ink-nav` | `#3A4A54` | Unselected nav labels |
| `ink-muted` | `#55646E` | Secondary text, captions, the AI disclosure |
| `ink-placeholder` | `#66737B` | Input placeholder |
| `on-primary`, `on-danger` | `#FFFFFF` | Text on primary and danger fills |
| `primary` | `#59256A` | Actions, links, selection, and focus |
| `primary-hover` | `#461B54` | Hovered primary fills and ghost text |
| `primary-tint` | `#ECE2F0` | Selected nav item, hovered rows and links, avatar |
| `marker` | `#C27544` | The cinnamon accent: markers only, never text, always beside a label |
| `border` | `#DDE3E6` | Sheet and card edges (decorative) |
| `border-subtle` | `#E8ECEE` | Row dividers (decorative) |
| `border-strong`, `-hover` | `#C9D2D7`, `#B9C5CB` | Secondary button edge; the label identifies the control |
| `input-border`, `-hover` | `#7F8C93`, `#5E6B73` | The composer and every text field |
| `focus-ring` | = `primary` | 2 px ring, 2 px offset, on every control, including destructive ones |
| `success` | `#2E6B4E` | Approved, saved |
| `warning` | `#8A5300` | Needs attention |
| `danger`, `danger-hover` | `#B42318`, `#931C13` | Errors only, never a denied request |
| `warning-tint`, `warning-border` | `#FCF4E8`, `#E6C79A` | A warning message's fill and edge (the short-notice warning); added for Phase 5 |
| `danger-tint`, `danger-border` | `#FDEFEE`, `#EFBDB8` | A refusal or error message's fill and edge; added for Phase 5 |
| `apricot-tint`, `apricot-border` | `#FBEFE5`, `#EBC6A8` | The confirmed moment on a confirm card only, a wash from the cinnamon family; added for Phase 5 |
| `scrim` | `rgba(20, 33, 42, 0.32)` | Behind an alert dialog, over the whole window; added for Phase 5 |
| `confidential-tint`, `confidential-border` | `#F7F3F9`, `#E4DAE9` | Behind the confidential-case form, the sent line, a case's hidden words, and HR's own-case notice: a quiet aubergine wash, never an alert; added for Phase 6 |
| `disabled-bg`, `disabled-fg` | `#E7EBED`, `#87939A` | Disabled controls (exempt from contrast minimums) |
| `tooltip-bg`, `tooltip-fg` | = `ink`, `#FFFFFF` | Tooltips |

**Contrast checks** (WCAG 2.2 AA), recomputed independently on 2026-10-04 from the values above:

| Pair | Ratio | Needs |
|---|---|---|
| `ink` on white | 16.4:1 | 4.5:1 |
| `ink-muted` on `surface` / on `surface-sunken` | 5.7:1 / 5.9:1 | 4.5:1 |
| `ink-nav` on `surface` | 8.5:1 | 4.5:1 |
| `ink-placeholder` on white | 4.9:1 | 4.5:1 |
| `primary` on white / on `surface-sunken` / on `primary-tint` | 11.1:1 / 10.6:1 / 8.8:1 | 4.5:1 |
| `ink` on `primary-tint` / on `neutral-hover` | 13.0:1 / 14.2:1 | 4.5:1 |
| White on `primary` / on `primary-hover` | 11.1:1 / 13.6:1 | 4.5:1 |
| `danger`, `success`, `warning` on white | 6.6:1, 6.3:1, 6.3:1 | 4.5:1 |
| White on `danger` | 6.6:1 | 4.5:1 |
| `input-border` on white / on `surface` | 3.5:1 / 3.2:1 | 3:1 (non-text, 1.4.11) |
| `marker` on white | 3.5:1 | 3:1 (non-text; never used for text) |
| `focus-ring` on white | 11.1:1 | 3:1 |
| `ink` on `warning-tint` / `warning` icon on it | 15.0:1 / 5.8:1 | 4.5:1 / 3:1 |
| `ink` on `danger-tint` / `danger` icon on it | 14.7:1 / 5.9:1 | 4.5:1 / 3:1 |
| `ink` on `apricot-tint` / `success` icon / `primary` link on it | 14.5:1 / 5.6:1 / 9.8:1 | 4.5:1 |
| `ink` / `ink-muted` / `primary` / `danger` on `confidential-tint` | 14.9:1 / 5.6:1 / 10.1:1 / 6.0:1 | 4.5:1 |
| `marker` clock on white ("Waiting for approval") | 3.6:1 | 3:1 (an icon beside its word) |
| The `-border` tokens on white | 1.35:1 to 1.7:1 | decorative: the icon and the words carry the meaning |

`border`, `border-subtle`, and `border-strong` are below 3:1 on purpose. They are decorative, or
the control they edge is identified by its label, so they never carry meaning alone.

## Type

Instrument Sans for everything, Geist Mono only for code and token values. Every number uses
tabular figures (`font-variant-numeric: tabular-nums`).

| Token | Size / line height | Weight | Tracking | Use |
|---|---|---|---|---|
| `display` | 48 / 56 px | 600 | −2.5% | The greeting |
| `h1` | 28 / 36 px | 600 | −1% | Page titles |
| `h2` | 20 / 28 px | 600 | | Section titles |
| `body-lg` | 18 / 28 px | 400 | | Composer input |
| `body` | 15 / 24 px | 400 | | Answers, "Try asking" rows |
| `ui` | 14 / 20 px | 500–600 | | Buttons, nav |
| `small` | 13 / 20 px | 400 | | Disclosure, sources, rail labels |
| `caption` | 12 / 16 px | 400 | | Persona title, sandbox pill, tooltips |
| `numeric` | 32 / 40 px | 600 | −1% | At-a-glance figures |

The fonts are self-hosted from [`system/assets/fonts/`](system/assets/fonts/), under the SIL Open
Font License (both license texts sit beside the files).

## Spacing, shape, depth, motion

- **Spacing:** a 4 px base: 2, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 48, 64, 72, 80, and 120 px.
- **Layout:** a 248 px sidebar, a 340 px right rail, a 420 px docked side panel (`panel-width`:
  the passage panel and the time-off request form), a 760 px content measure, the content sheet
  inset 12 px from the window, 40 px controls (32 px small), and 52 px "Try asking" rows.
- **Radius:** 6 px tooltips, 8 px small buttons, 10 px buttons, nav and rows, 14 px composer,
  16 px content sheet, full for avatars, the sandbox pill, and markers. No pill-shaped buttons.
- **Depth:** borders over shadows. Only three shadows: a 1 px composer shadow at rest, a soft
  shadow for tooltips, popovers, and menus, and a 3 px primary halo around the focused composer.
- **Motion:** color and border transitions only, 150 ms with `cubic-bezier(0.2, 0, 0, 1)`.
  Nothing moves, shrinks, or bounces, and transitions are turned off under
  `prefers-reduced-motion`.

## Data visualization

Not designed yet. The Phase 7 console needs a categorical palette for its charts, checked for
contrast and color-vision deficiency. Wada Sanzo's combinations are a good source.
