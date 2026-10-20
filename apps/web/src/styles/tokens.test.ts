// The theme must carry every design token, with the same value.
//
// THE MAPPING RULE. Every custom property in docs/design/system/tokens/*.css has exactly one
// home in theme.css, found by the first row below that matches its name. The value must match
// after lowercasing (Prettier lowercases hex) and collapsing whitespace, with any var(--x)
// inside it renamed the same way.
//
//   --space-N                      no variable of its own: Tailwind's spacing scale is
//                                  `--spacing` (4px) times N, so the value must equal N * 4px
//   --sidebar-width, --rail-width, --panel-width, --content-max, --sheet-inset,
//   --control-height, --control-height-sm, --row-height
//                                  --spacing-sidebar, -rail, -panel, -content, -sheet, -control,
//                                  -control-sm, -row (so w-sidebar, h-control, inset-sheet)
//   --weight-X                     --font-weight-X
//   --leading-X                    --text-X--line-height
//   --tracking-X                   --text-X--letter-spacing
//   --duration-fast                --default-transition-duration
//   --ease-standard                --default-transition-timing-function
//   any name in colors.css or shadcn.css, except --radius
//                                  --color-NAME
//   everything else                the same name (--text-*, --font-*, --radius-*, --shadow-*,
//                                  --focus-ring-*, --radius)
//
// The font weights per type token are not in the export. They come from the table in
// docs/design/tokens.md, and the theme's --text-X--font-weight must sit inside its range.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const designDir = join(import.meta.dirname, '../../../../docs/design')
const tokensDir = join(designDir, 'system/tokens')
const themeCss = readFileSync(join(import.meta.dirname, 'theme.css'), 'utf8')
const tokensMd = readFileSync(join(designDir, 'tokens.md'), 'utf8')

const exportFiles: Record<string, string> = Object.fromEntries(
  readdirSync(tokensDir)
    .filter((f) => f.endsWith('.css'))
    .map((f) => [f, readFileSync(join(tokensDir, f), 'utf8')]),
)

const LAYOUT_NAMES: Record<string, string> = {
  'sidebar-width': 'spacing-sidebar',
  'rail-width': 'spacing-rail',
  'panel-width': 'spacing-panel',
  'content-max': 'spacing-content',
  'sheet-inset': 'spacing-sheet',
  'control-height': 'spacing-control',
  'control-height-sm': 'spacing-control-sm',
  'row-height': 'spacing-row',
}

function parse(css: string): Map<string, string> {
  const props = new Map<string, string>()
  const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, '')
  for (const [, name, value] of withoutComments.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) {
    props.set(name, value.trim())
  }
  return props
}

function themeName(file: string, name: string): string {
  if (LAYOUT_NAMES[name]) return LAYOUT_NAMES[name]
  let m: RegExpMatchArray | null
  if ((m = name.match(/^weight-(.+)$/))) return `font-weight-${m[1]}`
  if ((m = name.match(/^leading-(.+)$/))) return `text-${m[1]}--line-height`
  if ((m = name.match(/^tracking-(.+)$/))) return `text-${m[1]}--letter-spacing`
  if (name === 'duration-fast') return 'default-transition-duration'
  if (name === 'ease-standard') return 'default-transition-timing-function'
  if (/^(colors|shadcn)\.css$/.test(file) && name !== 'radius') return `color-${name}`
  return name
}

function normalize(value: string, rename: (name: string) => string): string {
  return value
    .replace(/var\(--([\w-]+)\)/g, (_, n: string) => `var(--${rename(n)})`)
    .replace(/\s+/g, ' ')
    .toLowerCase()
    .trim()
}

const theme = parse(themeCss)
const SPACE = /^space-(\d+(?:-\d+)?)$/

// Which export file defines each name, so a var(--x) in a value is renamed like its target.
const fileOf = new Map<string, string>()
const tokens: { file: string; name: string; value: string }[] = []
for (const [file, css] of Object.entries(exportFiles)) {
  for (const [name, value] of parse(css)) {
    fileOf.set(name, file)
    tokens.push({ file, name, value })
  }
}
const rename = (name: string) => themeName(fileOf.get(name) ?? '', name)

describe('theme.css matches the design export', () => {
  it('finds the export, so the test cannot pass by checking nothing', () => {
    expect(Object.keys(exportFiles).length).toBeGreaterThanOrEqual(9)
    expect(tokens.length).toBeGreaterThan(100)
  })

  it('reads a 4px spacing base', () => {
    expect(theme.get('spacing')).toBe('4px')
  })

  it.each(tokens.map((t) => [t.name, t] as const))('--%s', (_, { file, name, value }) => {
    const space = name.match(SPACE)
    const target = space ? 'spacing' : themeName(file, name)
    // A spacing step is checked as a multiple of the base, so its value is the multiple in px.
    const expected = space
      ? `${Number(space[1].replace('-', '.')) * 4}px`
      : normalize(value, rename)
    const actual = space
      ? value.toLowerCase()
      : normalize(theme.get(target) ?? `<missing --${target}, from --${name}>`, (n) => n)
    expect(actual, `--${target}`).toBe(expected)
  })
})

describe('type weights match docs/design/tokens.md', () => {
  // Rows look like: | `ui` | 14 / 20 px | 500–600 | | Buttons, nav |
  const rows = [...tokensMd.matchAll(/^\| `([\w-]+)` \| [^|]*px \| (\d+)(?:–(\d+))? \|/gm)]

  it('finds all nine type tokens', () => {
    expect(rows.map((r) => r[1])).toEqual([
      'display',
      'h1',
      'h2',
      'body-lg',
      'body',
      'ui',
      'small',
      'caption',
      'numeric',
    ])
  })

  it.each(rows.map((r) => [r[1], Number(r[2]), Number(r[3] ?? r[2])] as const))(
    '--text-%s--font-weight is within %i and %i',
    (name, low, high) => {
      const weight = theme.get(`text-${name}--font-weight`)
      expect(weight, `theme.css is missing --text-${name}--font-weight`).toBeDefined()
      const resolved = weight!.replace(/var\(--([\w-]+)\)/, (_, n: string) => theme.get(n) ?? '')
      expect(Number(resolved)).toBeGreaterThanOrEqual(low)
      expect(Number(resolved)).toBeLessThanOrEqual(high)
    },
  )
})

describe('theme.css resets the Tailwind defaults the design replaces', () => {
  // Without these, Tailwind's own palette, type scale, radii, and shadows would still exist
  // beside the design's names.
  const RESET_NAMESPACES = [
    'color',
    'text',
    'font',
    'radius',
    'shadow',
    'inset-shadow',
    'drop-shadow',
    'leading',
    'tracking',
  ]

  it.each(RESET_NAMESPACES)('resets --%s-*', (namespace) => {
    expect(themeCss, `theme.css lacks --${namespace}-*: initial`).toMatch(
      new RegExp(`--${namespace}-\\*\\s*:\\s*initial\\s*;`),
    )
  })
})
