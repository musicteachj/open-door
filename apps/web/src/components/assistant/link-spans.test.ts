import { describe, expect, it } from 'vitest'
import { autolinkSpans, definitionSpans, linkAddressSpans } from './link-spans'

// The first version of `linkAddressSpans`, which scanned on from every "](" and so did work that
// grew with the square of the text. It is the reference the linear one must agree with.
function reference(text: string): { from: number; end: number }[] {
  const spans: { from: number; end: number }[] = []
  for (let at = text.indexOf(']('); at !== -1; at = text.indexOf('](', at + 2)) {
    let depth = 1
    for (let i = at + 2; i < text.length; i++) {
      const char = text[i]
      if (char === '\\') i++
      else if (char === '\n' && text[i + 1] === '\n') break
      else if (char === '(') depth++
      else if (char === ')' && --depth === 0) {
        spans.push({ from: at + 1, end: i + 1 })
        break
      }
    }
  }
  return spans
}

describe('linkAddressSpans', () => {
  it.each([
    ['no link', 'Just words.'],
    ['one link', 'See [x](/handbook/4.3) now.'],
    ['two links', '[a](/handbook/1) and [b](/handbook/2)'],
    ['nested parentheses', 'See [x](/handbook/4.3_(draft)) now.'],
    ['an address that never closes', 'See [x](/handbook/4.3 and keep going'],
    ['an unclosed link, then a closed one', '[a](/h/1 and [b](/handbook/2) end'],
    ['an unclosed open inside a closed link', '[a](/h(1 and [b](/handbook/2) end'],
    ['an escaped parenthesis', 'See [x](/handbook/4\\)3) now.'],
    ['a blank line inside an address', '[a](/handbook/1\n\nmore) and [b](/h/2)'],
    ['a blank line, then a link', '[a](/h/1\n\n[b](/h/2)'],
    ['a stray close', 'a) b [x](/h/1) c)'],
    ['adjacent links', '[a](/h/1)[b](/h/2)'],
    ['a text that ends on a backslash', '[a](/h/1\\'],
    ['parentheses in plain text', 'words (like this) and [x](/h/1) (more)'],
  ])('agrees with the first version for %s', (_name, text) => {
    expect(linkAddressSpans(text)).toEqual(reference(text))
  })

  it('finds the span of a link: from its "(" to just after its ")"', () => {
    const text = 'See [x](/handbook/4.3) now.'
    expect(linkAddressSpans(text)).toEqual([
      { from: text.indexOf('('), end: text.indexOf(')') + 1 },
    ])
  })

  it.each([
    ['spaces and tabs', '[a](/h/1\n \t \nmore) and [b](/handbook/2)'],
    ['an empty CRLF line', '[a](/h/1\r\n\r\nmore) and [b](/handbook/2)'],
    ['a CRLF line of spaces', '[a](/h/1\r\n  \r\nmore) and [b](/handbook/2)'],
  ])('forgets an open address at a blank line made of %s', (_name, text) => {
    const spans = linkAddressSpans(text)
    expect(spans).toHaveLength(1)
    expect(text.slice(spans[0]!.from, spans[0]!.end)).toBe('(/handbook/2)')
  })

  it('does not take a line break followed by text as a blank line', () => {
    const text = '[a](/h/1\n  more) end'
    expect(linkAddressSpans(text)).toHaveLength(1)
  })

  it('does work that grows in step with the text when many addresses never close', () => {
    const text = '[x](a(b '.repeat(20_000)
    const start = performance.now()
    const spans = linkAddressSpans(text)
    const took = performance.now() - start
    expect(spans).toEqual([])
    // The first version took seconds here. A loose bound, so a slow machine does not fail it.
    expect(took).toBeLessThan(500)
  })
})

describe('definitionSpans', () => {
  it('finds a reference-link definition line, without its line break', () => {
    const text = 'See [a][1].\n\n[1]: /handbook/4.3\n\nMore.'
    const spans = definitionSpans(text)
    expect(spans.map((s) => text.slice(s.from, s.end))).toEqual(['[1]: /handbook/4.3'])
  })

  it('finds several, and one indented by up to three spaces, with a title', () => {
    const text = '[1]: /a\n   [two]: /b "Title"\n[3]: <https://x.example>'
    expect(definitionSpans(text).map((s) => text.slice(s.from, s.end))).toEqual([
      '[1]: /a',
      '   [two]: /b "Title"',
      '[3]: <https://x.example>',
    ])
  })

  it('does not take a bracket with no address, or one in the middle of a line, as a definition', () => {
    expect(definitionSpans('[1]:\nSee [x]: here')).toEqual([])
    expect(definitionSpans('Words [1]: /handbook/4.3')).toEqual([])
  })
})

describe('autolinkSpans', () => {
  it('finds an address in angle brackets, from the "<" to just after the ">"', () => {
    const text = 'Read <https://evil.example/x> now'
    const spans = autolinkSpans(text)
    expect(spans.map((s) => text.slice(s.from, s.end))).toEqual(['<https://evil.example/x>'])
  })

  it('finds a mailto address, and not an HTML tag or a bare comparison', () => {
    expect(autolinkSpans('<mailto:a@b.example>')).toHaveLength(1)
    expect(autolinkSpans('Use <b>this</b> and 3 < 4 > 2')).toEqual([])
  })
})
