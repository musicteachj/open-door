# NN · Screen name

**Phase:** N · **Viewport:** desktop · **Personas:** who sees this screen

## Purpose

One or two sentences: what the user comes here to do.

## Layout

The regions, in reading order. Optionally, how they should collapse on a narrow screen.

## Components used

Components from `../../components.md`, with the variant each region uses.

## States

| State | Screenshot | What differs |
|---|---|---|
| Default | `desktop-default.png` | |
| Loading | `desktop-loading.png` | |
| Empty | | |
| Error | | |

## Interactions

What happens on click, submit, keyboard use (Tab order, Enter, Escape), and focus movement.

## Copy

The exact text, in American English. Labels, headings, helper text, empty and error messages.

## Acceptance criteria

The checklist the build must meet. Each item should be checkable by looking at the built screen or
running a test.

- [ ] Matches the screenshots at 1440 px, within the component library's spacing tokens
- [ ] Usable at 390 px: nothing overflows, and the navigation and controls still work
- [ ] Every interactive element is reachable by keyboard and has a visible focus ring
- [ ] Text contrast meets WCAG 2.2 AA; axe reports no violations
- [ ] …
