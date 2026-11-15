// The design tokens' color pairs meet WCAG 2.2 AA (Phase 8, Stage 8, the accessibility audit).
//
// Each pair is read from theme.css, so a changed token is checked at once. The first list is the
// contrast table in docs/design/tokens.md, with the ratio the table states: the test also fails if
// the table and the tokens drift apart. The second list is pairs the components use that the table
// leaves out (muted text on a hovered row, a placeholder in a sunken field, and so on).
//
// Needs: 4.5:1 for text (1.4.3), 3:1 for large text and for the parts of a control or an icon that
// carry meaning (1.4.11). Disabled controls are exempt (1.4.3's "inactive user interface
// component"), and the `-border` tokens are decorative, so neither is listed.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const themeCss = readFileSync(join(import.meta.dirname, 'theme.css'), 'utf8')
const tokensMd = readFileSync(
  join(import.meta.dirname, '../../../../docs/design/tokens.md'),
  'utf8',
)

/** The theme's colors by name (`ink`, not `--color-ink`), with `var(--color-x)` followed. */
function colors(): Map<string, string> {
  const raw = new Map<string, string>()
  for (const [, name, value] of themeCss.matchAll(/--color-([\w-]+)\s*:\s*([^;]+);/g)) {
    // The first definition wins: the theme's own block comes before the shadcn aliases.
    if (!raw.has(name!)) raw.set(name!, value!.trim())
  }
  const resolve = (value: string, depth = 0): string => {
    const ref = /^var\(--color-([\w-]+)\)$/.exec(value)
    if (!ref) return value
    if (depth > 5) throw new Error(`a var() loop at ${value}`)
    return resolve(raw.get(ref[1]!) ?? '', depth + 1)
  }
  return new Map([...raw].map(([name, value]) => [name, resolve(value)]))
}

const THEME = colors()

function hex(name: string): string {
  if (name === 'white') return '#ffffff'
  const value = THEME.get(name)
  if (!value || !/^#[0-9a-f]{6}$/i.test(value)) {
    throw new Error(`--color-${name} is not a six-digit hex color (${value})`)
  }
  return value
}

/** WCAG 2.2's relative luminance of a six-digit hex color. */
function luminance(color: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(color.slice(i, i + 2), 16) / 255
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }) as [number, number, number]
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

/** `row`: how the pair's row in tokens.md's table starts; a row can hold several pairs, in order. */
type Pair = { fg: string; bg: string; need: 4.5 | 3; stated?: number; row?: string }

/** docs/design/tokens.md's "Contrast checks" table, one row per pair. */
const TABLE: Pair[] = [
  { fg: 'ink', bg: 'white', need: 4.5, stated: 16.4, row: '`ink` on white' },
  { fg: 'ink-muted', bg: 'surface', need: 4.5, stated: 5.7, row: '`ink-muted` on `surface`' },
  {
    fg: 'ink-muted',
    bg: 'surface-sunken',
    need: 4.5,
    stated: 5.9,
    row: '`ink-muted` on `surface`',
  },
  { fg: 'ink-nav', bg: 'surface', need: 4.5, stated: 8.5, row: '`ink-nav` on `surface`' },
  { fg: 'ink-placeholder', bg: 'white', need: 4.5, stated: 4.9, row: '`ink-placeholder` on white' },
  { fg: 'primary', bg: 'white', need: 4.5, stated: 11.1, row: '`primary` on white' },
  { fg: 'primary', bg: 'surface-sunken', need: 4.5, stated: 10.6, row: '`primary` on white' },
  { fg: 'primary', bg: 'primary-tint', need: 4.5, stated: 8.8, row: '`primary` on white' },
  { fg: 'ink', bg: 'primary-tint', need: 4.5, stated: 13.0, row: '`ink` on `primary-tint`' },
  { fg: 'ink', bg: 'neutral-hover', need: 4.5, stated: 14.2, row: '`ink` on `primary-tint`' },
  { fg: 'on-primary', bg: 'primary', need: 4.5, stated: 11.1, row: 'White on `primary`' },
  { fg: 'on-primary', bg: 'primary-hover', need: 4.5, stated: 13.6, row: 'White on `primary`' },
  {
    fg: 'danger',
    bg: 'white',
    need: 4.5,
    stated: 6.6,
    row: '`danger`, `success`, `warning` on white',
  },
  {
    fg: 'success',
    bg: 'white',
    need: 4.5,
    stated: 6.3,
    row: '`danger`, `success`, `warning` on white',
  },
  {
    fg: 'warning',
    bg: 'white',
    need: 4.5,
    stated: 6.3,
    row: '`danger`, `success`, `warning` on white',
  },
  { fg: 'on-danger', bg: 'danger', need: 4.5, stated: 6.6, row: 'White on `danger`' },
  { fg: 'input-border', bg: 'white', need: 3, stated: 3.5, row: '`input-border` on white' },
  { fg: 'input-border', bg: 'surface', need: 3, stated: 3.2, row: '`input-border` on white' },
  { fg: 'marker', bg: 'white', need: 3, stated: 3.5, row: '`marker` on white' },
  { fg: 'focus-ring', bg: 'white', need: 3, stated: 11.1, row: '`focus-ring` on white' },
  { fg: 'ink', bg: 'warning-tint', need: 4.5, stated: 15.0, row: '`ink` on `warning-tint`' },
  { fg: 'warning', bg: 'warning-tint', need: 3, stated: 5.8, row: '`ink` on `warning-tint`' },
  { fg: 'ink', bg: 'danger-tint', need: 4.5, stated: 14.7, row: '`ink` on `danger-tint`' },
  { fg: 'danger', bg: 'danger-tint', need: 3, stated: 5.9, row: '`ink` on `danger-tint`' },
  { fg: 'ink', bg: 'apricot-tint', need: 4.5, stated: 14.5, row: '`ink` on `apricot-tint`' },
  { fg: 'success', bg: 'apricot-tint', need: 4.5, stated: 5.6, row: '`ink` on `apricot-tint`' },
  { fg: 'primary', bg: 'apricot-tint', need: 4.5, stated: 9.8, row: '`ink` on `apricot-tint`' },
  { fg: 'ink', bg: 'confidential-tint', need: 4.5, stated: 14.9, row: '`ink` / `ink-muted`' },
  { fg: 'ink-muted', bg: 'confidential-tint', need: 4.5, stated: 5.6, row: '`ink` / `ink-muted`' },
  { fg: 'primary', bg: 'confidential-tint', need: 4.5, stated: 10.1, row: '`ink` / `ink-muted`' },
  { fg: 'danger', bg: 'confidential-tint', need: 4.5, stated: 6.0, row: '`ink` / `ink-muted`' },
]

/** Pairs the components use that the table doesn't list. */
const USED: Pair[] = [
  { fg: 'ink-muted', bg: 'white', need: 4.5 },
  { fg: 'ink-muted', bg: 'surface-hover', need: 4.5 },
  { fg: 'ink-muted', bg: 'neutral-hover', need: 4.5 },
  { fg: 'ink-muted', bg: 'primary-tint', need: 4.5 },
  { fg: 'ink-muted', bg: 'warning-tint', need: 4.5 },
  { fg: 'ink-muted', bg: 'danger-tint', need: 4.5 },
  { fg: 'ink-muted', bg: 'apricot-tint', need: 4.5 },
  { fg: 'ink-placeholder', bg: 'surface', need: 4.5 },
  { fg: 'ink-placeholder', bg: 'surface-sunken', need: 4.5 },
  { fg: 'ink-nav', bg: 'primary-tint', need: 4.5 },
  { fg: 'ink-nav', bg: 'surface-hover', need: 4.5 },
  { fg: 'primary', bg: 'surface', need: 4.5 },
  { fg: 'primary', bg: 'surface-hover', need: 4.5 },
  { fg: 'primary', bg: 'neutral-hover', need: 4.5 },
  { fg: 'danger', bg: 'surface-sunken', need: 4.5 },
  { fg: 'success', bg: 'surface', need: 4.5 },
  { fg: 'warning', bg: 'surface', need: 4.5 },
  { fg: 'input-border', bg: 'surface-sunken', need: 3 },
  { fg: 'marker', bg: 'surface', need: 3 },
  { fg: 'focus-ring', bg: 'surface', need: 3 },
  { fg: 'focus-ring', bg: 'primary-tint', need: 3 },
  { fg: 'tooltip-fg', bg: 'tooltip-bg', need: 4.5 },
]

const label = ({ fg, bg }: Pair) => `${fg} on ${bg}`

describe('the design tokens’ contrast pairs', () => {
  it.each([...TABLE, ...USED].map((p) => [label(p), p] as const))('%s meets its bar', (_, p) => {
    expect(contrast(hex(p.fg), hex(p.bg))).toBeGreaterThanOrEqual(p.need)
  })

  it.each(TABLE.map((p) => [label(p), p] as const))(
    '%s matches the ratio tokens.md states',
    (_, p) => {
      const ratio = contrast(hex(p.fg), hex(p.bg))
      expect(Math.abs(ratio - p.stated!)).toBeLessThanOrEqual(0.1)
    },
  )

  const table = tokensMd.slice(tokensMd.indexOf('**Contrast checks**'))
  const rows = new Map<string, number[]>()
  for (const { row, stated } of TABLE) rows.set(row!, [...(rows.get(row!) ?? []), stated!])
  it.each([...rows])('tokens.md’s row "%s" states its pairs’ ratios, in order', (row, ratios) => {
    const line = table.split('\n').find((l) => l.startsWith(`| ${row}`))
    // The Ratio cell is the second; the first may hold a ratio of its own in words.
    const cell = line?.split('|')[2] ?? ''
    const written = [...cell.matchAll(/(\d+\.\d):1/g)].map((m) => Number(m[1]))
    expect(written).toEqual(ratios)
  })

  it('works out WCAG’s own examples', () => {
    expect(contrast('#000000', '#ffffff')).toBeCloseTo(21, 5)
    expect(contrast('#777777', '#ffffff')).toBeCloseTo(4.48, 2)
    expect(contrast('#ffffff', '#ffffff')).toBe(1)
  })
})
