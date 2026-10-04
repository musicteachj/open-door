# Design tokens

**Status: waiting for the design system from Claude Design.** The owner fills this in (or the build
transcribes it from the handoff). The build then turns it into Tailwind v4 `@theme` CSS variables.
Components use these tokens, never raw hex values.

The starting direction in [`BRIEF.md`](BRIEF.md) is only a brief. The values that land here replace
it.

## Color

| Token | Light value | Dark value (later) | Use |
|---|---|---|---|
| `surface` | | | App background |
| `surface-raised` | | | Cards, panels |
| `ink` | | | Body text |
| `ink-muted` | | | Secondary text |
| `primary` | | | Primary actions, links, citation marks |
| `primary-ink` | | | Text on primary |
| `accent` | | | Moments that matter, used sparingly |
| `success` / `warning` / `danger` | | | Status, always paired with an icon or text |
| `border` | | | Dividers, inputs |
| `focus` | | | Focus rings |

**Contrast checks** (text on its background, WCAG 2.2 AA): record each pair and its ratio here.

## Type

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| `display` | | | |
| `h1`, `h2`, `h3` | | | |
| `body` | | | |
| `small` | | | |
| `caption` | | | |

Font families, and whether numbers use tabular figures:

## Spacing, shape, depth, motion

- Spacing scale (4 px base):
- Radius scale:
- Elevation / shadow scale:
- Border widths:
- Motion durations and easing, with reduced-motion behavior:

## Data visualization

A categorical palette for console charts, checked for contrast and color-vision deficiency:
