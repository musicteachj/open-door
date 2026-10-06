// Components use theme tokens, never raw color values. Hex, rgb(), and hsl() are all banned in
// src/**/*.tsx. Colors belong in docs/design/system/tokens/ and src/styles/theme.css.
import { describe, expect, it } from 'vitest'

const components = import.meta.glob('../**/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const RAW_COLOR = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/g

describe('no raw colors in components', () => {
  it('scans some components, so it cannot pass by checking nothing', () => {
    expect(Object.keys(components).length).toBeGreaterThan(0)
  })

  it('finds no hex, rgb(), or hsl() value in any .tsx file', () => {
    const found = Object.entries(components).flatMap(([file, source]) =>
      [...source.matchAll(RAW_COLOR)].map((m) => `${file}: ${m[0]}`),
    )
    expect(found).toEqual([])
  })
})
