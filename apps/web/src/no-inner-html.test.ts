// The handbook's text is rendered as React elements, never as HTML strings. This scan fails on any
// source file under src/ that sets raw HTML, so a future change can't open an injection hole.
import { describe, expect, it } from 'vitest'

const sources = import.meta.glob('./**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

// Split so this file's own source doesn't contain the word it hunts for.
const RAW_HTML = new RegExp('dangerously' + 'SetInnerHTML')

describe('no raw HTML injection', () => {
  it('scans .ts and .tsx files, so it cannot pass by checking nothing', () => {
    const files = Object.keys(sources)
    expect(files.some((f) => f.endsWith('.tsx'))).toBe(true)
    expect(files.some((f) => f.endsWith('.ts'))).toBe(true)
    expect(files).toContain('./components/handbook/labels.ts')
  })

  it('would catch the property in a tsx or ts file', () => {
    expect(RAW_HTML.test('<div dangerouslySetInnerHTML={{ __html: x }} />')).toBe(true)
    expect(RAW_HTML.test('const p = { dangerouslySetInnerHTML: { __html: x } }')).toBe(true)
  })

  it('finds it in no source file', () => {
    const found = Object.entries(sources)
      .filter(([, source]) => RAW_HTML.test(source))
      .map(([file]) => file)
    expect(found).toEqual([])
  })
})
