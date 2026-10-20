import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import type { CitationOut } from '@/api/generated'
import { citation } from '@/test/assistant-fixtures'
import { Answer } from './answer'
import * as linkSpans from './link-spans'

// A stand-in for the real marker (Task 35): a button named by its marker number.
function renderMarker(c: CitationOut) {
  return (
    <button type="button" data-testid="marker">
      {c.marker}
    </button>
  )
}

function renderAnswer(text: string, citations: CitationOut[] = [], caret = false) {
  return render(
    <MemoryRouter>
      <Answer text={text} citations={citations} renderMarker={renderMarker} caret={caret} />
    </MemoryRouter>,
  )
}

// The text of the answer with each marker as "[n]", so order and position are easy to assert.
function flattened(container: HTMLElement): string {
  return Array.from(container.querySelectorAll('[data-testid="marker"]'))
    .reduce((html, marker) => {
      marker.replaceWith(`[${marker.textContent}]`)
      return html
    }, container)
    .textContent!.trim()
}

describe('Answer: the Markdown subset', () => {
  it('renders paragraphs as paragraphs', () => {
    const { container } = renderAnswer('First.\n\nSecond.')
    expect(container.querySelectorAll('p')).toHaveLength(2)
    expect(screen.getByText('Second.').tagName).toBe('P')
  })

  it('renders bold and italic as elements', () => {
    renderAnswer('A **bold** and an *italic* word.')
    expect(screen.getByText('bold').tagName).toBe('STRONG')
    expect(screen.getByText('italic').tagName).toBe('EM')
  })

  it('renders unordered and ordered lists as lists', () => {
    renderAnswer('- one\n- two\n\n1. first\n2. second')
    expect(screen.getAllByRole('list')).toHaveLength(2)
    expect(screen.getAllByRole('listitem')).toHaveLength(4)
    expect(screen.getByText('first').closest('ol')).not.toBeNull()
  })

  it('renders a line break as a br', () => {
    const { container } = renderAnswer('one  \ntwo')
    expect(container.querySelector('br')).not.toBeNull()
  })

  it('keeps the text of a construct it does not allow, without the element', () => {
    const { container } = renderAnswer('# Heading\n\n> quoted\n\n`code`')
    expect(container.querySelector('h1, blockquote, code')).toBeNull()
    expect(container).toHaveTextContent('Heading')
    expect(container).toHaveTextContent('quoted')
    expect(container).toHaveTextContent('code')
  })

  it('renders an image as nothing, never as an img', () => {
    const { container } = renderAnswer('Look: ![alt](https://evil.example/x.png)')
    expect(container.querySelector('img')).toBeNull()
  })

  it('shows an image as its alt text, and never the image or its address', () => {
    const { container } = renderAnswer(
      'See ![the leave chart](https://evil.example/x.png) for details',
    )
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toBe('See the leave chart for details')
    expect(container.textContent).not.toContain('evil.example')
  })

  it('shows nothing for an image with no alt text', () => {
    const { container } = renderAnswer('See ![](/x.png) now.')
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toBe('See  now.')
  })

  it("shows the alt text of an image inside a handbook link as the link's text", () => {
    renderAnswer('[![the leave chart](/x.png)](/handbook/4.3)')
    expect(screen.getByRole('link', { name: 'the leave chart' })).toHaveAttribute(
      'href',
      '/handbook/4.3',
    )
  })

  it('puts a marker inside alt text where it belongs', () => {
    const text = 'See ![the leave chart](/x.png) now.'
    renderAnswer(text, [citation({ offsetUtf16: 'See ![the leave'.length })])
    expect(screen.getByTestId('marker')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/[\uE000-\uF8FF]/)
  })

  it('renders partial text while it streams', () => {
    const { container, rerender } = renderAnswer('You get **5 da')
    expect(container).toHaveTextContent('You get **5 da')
    rerender(
      <MemoryRouter>
        <Answer text="You get **5 days**." citations={[]} renderMarker={renderMarker} />
      </MemoryRouter>,
    )
    expect(screen.getByText('5 days').tagName).toBe('STRONG')
  })
})

describe('Answer: raw HTML and links', () => {
  it('shows raw HTML as the literal characters', () => {
    const { container } = renderAnswer('Hello <b>x</b> <script>alert(1)</script> <img src=x>')
    expect(container.querySelector('b, script, img')).toBeNull()
    expect(container).toHaveTextContent('<b>x</b>')
    expect(container).toHaveTextContent('<script>alert(1)</script>')
  })

  it('keeps a bare URL as plain text', () => {
    const { container } = renderAnswer('See https://evil.example/path and www.evil.example now')
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(container).toHaveTextContent('https://evil.example/path')
    expect(container).toHaveTextContent('www.evil.example')
  })

  it('links a handbook path', () => {
    renderAnswer('See [the policy](/handbook/4.3).')
    expect(screen.getByRole('link', { name: 'the policy' })).toHaveAttribute(
      'href',
      '/handbook/4.3',
    )
  })

  it('links a directory path', () => {
    renderAnswer('Ask [Elena](/directory/abc).')
    expect(screen.getByRole('link', { name: 'Elena' })).toHaveAttribute('href', '/directory/abc')
  })

  it.each([
    ['an https link', '[x](https://evil.example)'],
    ['an http link', '[x](http://evil.example)'],
    ['a javascript link', '[x](javascript:alert(1))'],
    ['a mixed-case javascript link', '[x](JaVaScRiPt:alert(1))'],
    ['a data link', '[x](data:text/html,hi)'],
    ['a mailto link', '[x](mailto:a@b.example)'],
    ['a protocol-relative link', '[x](//evil.example)'],
    ['a relative path', '[x](policy/4.3)'],
    ['a root path outside the allowed two', '[x](/admin)'],
    ['a handbook path without the slash', '[x](/handbooks/4.3)'],
    ['an empty link', '[x]()'],
    ['an entity-encoded javascript scheme', '[x](&#x6A;avascript:alert(1))'],
    ['an entity-encoded https scheme', '[x](&#x68;ttps://evil.example)'],
    ['a dot-dot path out of the handbook', '[x](/handbook/../../evil)'],
    ['a dot-dot path in the directory', '[x](/directory/../admin)'],
    ['a dot segment', '[x](/handbook/./4.3)'],
    ['an encoded dot-dot path', '[x](/handbook/%2e%2e/evil)'],
    ['an encoded dot-dot path in capitals', '[x](/handbook/%2E%2E/evil)'],
    ['a path ending in dot-dot', '[x](/handbook/4.3/..)'],
    ['a path with a backslash', '[x](/handbook/a\\b)'],
    ['a path with an encoded backslash', '[x](/handbook/a%5Cb)'],
    ['a path with a bad percent escape', '[x](/handbook/%zz)'],
  ])('shows %s as its plain text, with no anchor', (_name, markdown) => {
    const { container } = renderAnswer(`Before ${markdown} after.`)
    expect(container.querySelector('a')).toBeNull()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(container).toHaveTextContent('Before x after.')
  })

  it('links a directory path with an empty segment, which stays inside the app', () => {
    renderAnswer('Ask [Elena](/directory//x).')
    expect(screen.getByRole('link', { name: 'Elena' })).toHaveAttribute('href', '/directory/x')
  })

  it('keeps a query on a handbook link, and a dot inside a section number', () => {
    renderAnswer('See [it](/handbook/CA-4.3?passage=CA-4.3~p1).')
    expect(screen.getByRole('link', { name: 'it' })).toHaveAttribute(
      'href',
      '/handbook/CA-4.3?passage=CA-4.3~p1',
    )
  })

  it('shows no anchor for a link whose only content was an image with no alt text', () => {
    const { container } = renderAnswer('See [![](https://e.example/i.png)](/handbook/4.3) now.')
    expect(container.querySelector('a')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    expect(container).toHaveTextContent('See now.')
  })

  it('shows a reference-style link to an outside address as plain text too', () => {
    const { container } = renderAnswer('A [ref][1].\n\n[1]: https://evil.example')
    expect(container.querySelector('a')).toBeNull()
    expect(container).toHaveTextContent('A ref.')
  })

  it('never renders a link that is only an angle-bracket autolink', () => {
    const { container } = renderAnswer('<https://evil.example>')
    expect(container.querySelector('a')).toBeNull()
  })
})

describe('Answer: citation markers', () => {
  it('puts each marker at its offset, in order', () => {
    const text = 'Five days. Carryover is not allowed.'
    renderAnswer(text, [
      citation({ marker: 1, offsetUtf16: 'Five days.'.length }),
      citation({ marker: 2, offsetUtf16: text.length }),
    ])
    expect(screen.getAllByTestId('marker').map((m) => m.textContent)).toEqual(['1', '2'])
    expect(flattened(document.body)).toBe('Five days.[1] Carryover is not allowed.[2]')
  })

  it('puts a marker at the very end of the text', () => {
    const { container } = renderAnswer('Done.', [citation({ offsetUtf16: 5 })])
    expect(flattened(container)).toBe('Done.[1]')
  })

  it('puts a marker at the very start of the text', () => {
    const { container } = renderAnswer('Done.', [citation({ offsetUtf16: 0 })])
    expect(flattened(container)).toBe('[1]Done.')
  })

  it('keeps array order for two markers at the same offset', () => {
    const { container } = renderAnswer('Done.', [
      citation({ marker: 2, offsetUtf16: 5 }),
      citation({ marker: 1, offsetUtf16: 5 }),
    ])
    expect(flattened(container)).toBe('Done.[2][1]')
  })

  it('sorts markers by offset whatever their order in the array', () => {
    const { container } = renderAnswer('One. Two.', [
      citation({ marker: 2, offsetUtf16: 9 }),
      citation({ marker: 1, offsetUtf16: 4 }),
    ])
    expect(flattened(container)).toBe('One.[1] Two.[2]')
  })

  it('moves an offset past the end to the end', () => {
    const { container } = renderAnswer('Done.', [citation({ offsetUtf16: 500 })])
    expect(flattened(container)).toBe('Done.[1]')
  })

  it('moves a negative or invalid offset to a safe place', () => {
    const { container } = renderAnswer('Done.', [
      citation({ marker: 1, offsetUtf16: -3 }),
      citation({ marker: 2, offsetUtf16: Number.NaN }),
    ])
    expect(flattened(container)).toBe('[1]Done.[2]')
  })

  it('counts offsets in UTF-16 code units, so an emoji takes two', () => {
    const text = 'Hi 😀 ok.'
    const { container } = renderAnswer(text, [citation({ offsetUtf16: 'Hi 😀'.length })])
    expect(flattened(container)).toBe('Hi 😀[1] ok.')
  })

  it('does not split an emoji when an offset falls inside it', () => {
    const { container } = renderAnswer('Hi 😀 ok.', [citation({ offsetUtf16: 4 })])
    expect(flattened(container)).toBe('Hi 😀[1] ok.')
  })

  it('shows a marker inside a list item', () => {
    const text = '- one thing\n- another thing'
    renderAnswer(text, [citation({ offsetUtf16: '- one thing'.length })])
    const item = screen.getAllByRole('listitem')[0]!
    expect(within(item).getByTestId('marker')).toBeInTheDocument()
    expect(within(screen.getAllByRole('listitem')[1]!).queryByTestId('marker')).toBeNull()
  })

  it('shows a marker inside bold and inside italic', () => {
    const text = 'A **bold claim** and *an italic one*.'
    renderAnswer(text, [
      citation({ marker: 1, offsetUtf16: 'A **bold'.length }),
      citation({ marker: 2, offsetUtf16: 'A **bold claim** and *an italic'.length }),
    ])
    expect(
      within(screen.getByText(/bold/, { selector: 'strong' })).getByTestId('marker'),
    ).toHaveTextContent('1')
    expect(
      within(screen.getByText(/italic/, { selector: 'em' })).getByTestId('marker'),
    ).toHaveTextContent('2')
  })

  it('shows a marker in text an unallowed element would wrap', () => {
    const { container } = renderAnswer('# Title\n\nBody.', [citation({ offsetUtf16: 7 })])
    expect(flattened(container)).toContain('Title[1]')
  })

  it('moves a marker out of a link, so a button is never inside an anchor', () => {
    const text = 'See [the policy](/handbook/4.3) now.'
    const { container } = renderAnswer(text, [citation({ offsetUtf16: 'See [the pol'.length })])
    const link = screen.getByRole('link', { name: 'the policy' })
    expect(within(link).queryByTestId('marker')).toBeNull()
    expect(container.querySelectorAll('[data-testid="marker"]')).toHaveLength(1)
    expect(link.nextElementSibling).toBe(screen.getByTestId('marker'))
  })

  it('drops a private-use character the model wrote, so it cannot forge a marker', () => {
    const { container } = renderAnswer('Real\uE000 text\uE001.', [])
    expect(screen.queryByTestId('marker')).toBeNull()
    expect(container.textContent).toBe('Real text.')
  })

  it('keeps every offset valid after dropping a forged character', () => {
    const text = 'Ab\uE000cd. Ef.'
    // The offset names the position after "cd." in the model's original text.
    const { container } = renderAnswer(text, [citation({ offsetUtf16: 'Ab\uE000cd.'.length })])
    expect(flattened(container)).toBe('Abcd.[1] Ef.')
  })

  it('does not render a marker for a forged character even when citations exist', () => {
    renderAnswer('Hi\uE001 there', [
      citation({ marker: 1, offsetUtf16: 0 }),
      citation({ marker: 2, offsetUtf16: 0 }),
    ])
    expect(screen.getAllByTestId('marker')).toHaveLength(2)
  })

  it('does not let a character reference forge a marker', () => {
    // (Written in two pieces: the raw-color test would read the number after the hash as a color.)
    const decimal = ['&#', '57344;'].join('')
    const text = `Real claim. Forged &#xE000; ${decimal} &#xe000; &#xE001; &#x0E002; here.`
    const { container } = renderAnswer(text, [citation({ marker: 1, offsetUtf16: 11 })])
    expect(screen.getAllByTestId('marker')).toHaveLength(1)
    expect(container.textContent).not.toMatch(/[\uE000-\uF8FF]/)
    expect(flattened(container)).toMatch(/^Real claim\.\[1\] Forged\s+here\.$/)
  })

  it('does not let nested character references forge a marker', () => {
    const nestedHex = '&#x&#xE000;E000;'
    const nestedDecimal = ['&#', '&#', '57344;', '57344;'].join('')
    const text = `Real claim. ${nestedHex} ${nestedDecimal} end.`
    const { container } = renderAnswer(text, [citation({ marker: 1, offsetUtf16: 11 })])
    expect(screen.getAllByTestId('marker')).toHaveLength(1)
    expect(container.textContent).not.toMatch(/[\uE000-\uF8FF]/)
    expect(
      renderAnswer(text, []).container.querySelectorAll('[data-testid="marker"]'),
    ).toHaveLength(0)
  })

  it('does not let a character reference forge a marker when there are no citations', () => {
    renderAnswer(`Forged &#xE000; and ${['&#', '57345;'].join('')} here.`, [])
    expect(screen.queryByTestId('marker')).toBeNull()
  })

  it('does not let a character reference in a link address or a code span forge a marker', () => {
    const { container } = renderAnswer('See [x](/a&#xE000;b) and `&#xE000;` now.', [
      citation({ marker: 1, offsetUtf16: 0 }),
    ])
    expect(container.querySelectorAll('[data-testid="marker"]')).toHaveLength(1)
  })

  it('keeps a character reference to an ordinary character', () => {
    const { container } = renderAnswer('Fish &#38; chips &#x41;.', [])
    expect(container.textContent).toBe('Fish & chips A.')
  })

  it('shows no marker when there are no citations', () => {
    renderAnswer('Plain text.')
    expect(screen.queryByTestId('marker')).toBeNull()
  })

  it('hands renderMarker the citation and its index in the array', () => {
    const seen: [number, number][] = []
    render(
      <MemoryRouter>
        <Answer
          text="Hello."
          citations={[
            citation({ marker: 3, offsetUtf16: 5 }),
            citation({ marker: 1, offsetUtf16: 0 }),
          ]}
          renderMarker={(c, index) => {
            seen.push([c.marker, index])
            return <span>{c.marker}</span>
          }}
        />
      </MemoryRouter>,
    )
    expect(seen.sort()).toEqual([
      [1, 1],
      [3, 0],
    ])
  })
})

describe('Answer: a marker beside emphasis', () => {
  it.each([
    ['bold', '**Five days.** More text.', '**Five days.**', 'strong', 'Five days.[1] More text.'],
    ['italic', '*Five days.* More.', '*Five days.*', 'em', 'Five days.[1] More.'],
    [
      'bold around a quote',
      'It is **"quoted"** text.',
      'It is **"quoted"**',
      'strong',
      'It is "quoted"[1] text.',
    ],
    ['underscore italic', '_Five days._ More.', '_Five days._', 'em', 'Five days.[1] More.'],
    ['bold italic', '***Five days.*** More.', '***Five days.***', 'strong', 'Five days.[1] More.'],
    ['bold at the end of the text', 'A **claim.**', 'A **claim.**', 'strong', 'A claim.[1]'],
  ])(
    'keeps %s emphasis when the offset is just after its closing mark',
    (_name, text, upTo, tag, expected) => {
      const { container } = renderAnswer(text, [citation({ offsetUtf16: upTo.length })])
      expect(container.querySelector(tag)).not.toBeNull()
      expect(screen.getByTestId('marker')).toBeInTheDocument()
      expect(container.textContent).not.toContain('*')
      expect(container.textContent).not.toContain('_')
      expect(flattened(container)).toBe(expected)
    },
  )

  it('keeps emphasis when two markers land after the closing mark', () => {
    const { container } = renderAnswer('**Five days.** More.', [
      citation({ marker: 1, offsetUtf16: 14 }),
      citation({ marker: 2, offsetUtf16: 14 }),
    ])
    expect(container.querySelector('strong')).not.toBeNull()
    expect(flattened(container)).toBe('Five days.[1][2] More.')
  })

  it('keeps emphasis when the offset is between two closing marks', () => {
    const { container } = renderAnswer('**Five days.** More.', [citation({ offsetUtf16: 13 })])
    expect(container.querySelector('strong')).not.toBeNull()
    expect(container.textContent).not.toContain('*')
    expect(screen.getByTestId('marker')).toBeInTheDocument()
  })

  it('keeps emphasis whose text is bold in a list item', () => {
    const text = '- **One thing.** Next.'
    renderAnswer(text, [citation({ offsetUtf16: '- **One thing.**'.length })])
    const item = screen.getByRole('listitem')
    expect(item.querySelector('strong')).not.toBeNull()
    expect(within(item).getByTestId('marker')).toBeInTheDocument()
  })
})

describe('Answer: the work it does for a render', () => {
  it('does not scan the text again when it renders again with the same text and citations', () => {
    const spy = vi.spyOn(linkSpans, 'linkAddressSpans')
    const citations = [citation({ offsetUtf16: 5 })]
    const { rerender } = render(
      <MemoryRouter>
        <Answer text="Five days." citations={citations} renderMarker={renderMarker} />
      </MemoryRouter>,
    )
    expect(spy).toHaveBeenCalledTimes(1)
    rerender(
      <MemoryRouter>
        <Answer text="Five days." citations={citations} renderMarker={renderMarker} caret />
      </MemoryRouter>,
    )
    expect(spy).toHaveBeenCalledTimes(1)
    rerender(
      <MemoryRouter>
        <Answer text="Five days. More." citations={citations} renderMarker={renderMarker} caret />
      </MemoryRouter>,
    )
    expect(spy).toHaveBeenCalledTimes(2)
    spy.mockRestore()
  })

  it('does not look for link addresses when there are no citations', () => {
    const spy = vi.spyOn(linkSpans, 'linkAddressSpans')
    renderAnswer('See [x](/handbook/4.3) now.', [])
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it("still drops the model's own private-use characters when there are no citations", () => {
    const { container } = renderAnswer('Five\uE000 days\uF8FF.', [])
    expect(container.textContent).toBe('Five days.')
    expect(screen.queryByTestId('marker')).not.toBeInTheDocument()
  })

  it('renders a text of 2,000 unclosed link starts in a modest time', () => {
    const text = '[x](a(b '.repeat(2000)
    const start = performance.now()
    renderAnswer(text, [citation({ offsetUtf16: text.length })])
    expect(performance.now() - start).toBeLessThan(2000)
  })
})

describe('Answer: a marker beside "*" and "_" that are not closing a span', () => {
  it("keeps a marker that follows a list bullet on that bullet's item", () => {
    const text = '- Ten days a year\n* Accrues monthly'
    const { container } = renderAnswer(text, [
      citation({ offsetUtf16: '- Ten days a year\n* '.length }),
    ])
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(within(items[0]!).queryByTestId('marker')).not.toBeInTheDocument()
    expect(within(items[1]!).getByTestId('marker')).toBeInTheDocument()
    expect(items[1]).toHaveTextContent('Accrues monthly')
    expect(container.textContent).not.toContain('*')
  })

  it('keeps an underscore that ends a word as it is: "form_A_"', () => {
    const { container } = renderAnswer('See form_A_', [
      citation({ offsetUtf16: 'See form_A_'.length }),
    ])
    expect(flattened(container)).toBe('See form_A_[1]')
  })

  it('still steps back over the "_" that closes an italic word', () => {
    const { container } = renderAnswer('See _form A_ now.', [
      citation({ offsetUtf16: 'See _form A_'.length }),
    ])
    expect(container.querySelector('em')).not.toBeNull()
    expect(container.textContent).not.toContain('_')
    expect(flattened(container)).toBe('See form A[1] now.')
  })

  it('steps back over whitespace and then a closing mark, but not a bullet after more whitespace', () => {
    const { container } = renderAnswer('**Five days.** \n\nMore.', [
      citation({ offsetUtf16: '**Five days.** \n\n'.length }),
    ])
    expect(container.querySelector('strong')).not.toBeNull()
    expect(within(container.querySelector('p')!).getByTestId('marker')).toBeInTheDocument()
  })
})

describe('Answer: a marker after a bare list marker', () => {
  it.each([
    ['a dash', 'Steps:\n- '],
    ['a plus', 'Steps:\n+ '],
    ['a number and a period', 'Steps:\n1. '],
  ])('keeps %s and the space after it, so the marker is in the new item', (_name, text) => {
    const { container } = renderAnswer(text, [citation({ offsetUtf16: text.length })])
    const item = screen.getByRole('listitem')
    expect(within(item).getByTestId('marker')).toBeInTheDocument()
    expect(container.querySelector('p')).toHaveTextContent(/^Steps:$/)
    expect(container.textContent).not.toMatch(/[-+]|1\./)
  })

  it('still steps back over whitespace that follows ordinary text on the line', () => {
    const { container } = renderAnswer('Steps: - not a list \n', [citation({ offsetUtf16: 21 })])
    expect(flattened(container)).toBe('Steps: - not a list[1]')
  })

  it('treats "- " in the middle of a line as text, not a list marker', () => {
    const { container } = renderAnswer('Ten - ', [citation({ offsetUtf16: 6 })])
    expect(flattened(container)).toBe('Ten -[1]')
  })
})

describe('Answer: a marker inside a run of "*" or "_"', () => {
  it('keeps an opening "**" whole when the offset falls between its two asterisks', () => {
    const { container } = renderAnswer('**Note:** text', [citation({ offsetUtf16: 1 })])
    expect(container.querySelector('strong')).toHaveTextContent('Note:')
    expect(container.textContent).not.toContain('*')
    expect(screen.getByTestId('marker')).toBeInTheDocument()
  })

  it('keeps a closing "**" whole when the offset falls between its two asterisks', () => {
    const text = 'It is **ten days**'
    const { container } = renderAnswer(text, [citation({ offsetUtf16: text.length - 1 })])
    expect(container.querySelector('strong')).toHaveTextContent('ten days')
    expect(container.textContent).not.toContain('*')
    expect(flattened(container)).toBe('It is ten days[1]')
  })

  it('keeps an italic "_" run whole too, and a "***" run', () => {
    const { container } = renderAnswer('***Note:*** text', [citation({ offsetUtf16: 2 })])
    expect(container.querySelector('strong')).not.toBeNull()
    expect(container.textContent).not.toContain('*')
    expect(screen.getByTestId('marker')).toBeInTheDocument()
  })

  it('leaves an offset beside a run, not inside it, where it was', () => {
    const { container } = renderAnswer('A **b** c', [citation({ offsetUtf16: 4 })])
    expect(flattened(container)).toBe('A [1]b c')
  })
})

describe('Answer: a marker near a reference definition or an autolink', () => {
  const text = 'See [the policy][1] for the details.\n\n[1]: /handbook/4.3'

  it('puts a marker at the end of a definition line before the definition, so the link keeps its address', () => {
    renderAnswer(text, [citation({ offsetUtf16: text.length })])
    expect(screen.getByTestId('marker')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'the policy' })).toHaveAttribute(
      'href',
      '/handbook/4.3',
    )
    expect(document.body.textContent).not.toMatch(/[\uE000-\uF8FF]/)
  })

  it('does the same for an offset in the middle of a definition line', () => {
    renderAnswer(text, [citation({ offsetUtf16: text.length - 4 })])
    expect(screen.getByTestId('marker')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'the policy' })).toHaveAttribute(
      'href',
      '/handbook/4.3',
    )
  })

  it('puts the marker with the text before the definition, in the paragraph', () => {
    const { container } = renderAnswer(text, [citation({ offsetUtf16: text.length })])
    expect(within(container.querySelector('p')!).getByTestId('marker')).toBeInTheDocument()
  })

  it('moves a marker that follows a definition and its blank line back before the definition', () => {
    const body = 'See [the policy][1] for the details.\n\n[1]: /handbook/4.3\n\nMore.'
    const { container } = renderAnswer(body, [
      citation({ offsetUtf16: body.length - 'More.'.length }),
    ])
    expect(screen.getByRole('link', { name: 'the policy' })).toHaveAttribute(
      'href',
      '/handbook/4.3',
    )
    expect(within(container.querySelector('p')!).getByTestId('marker')).toBeInTheDocument()
  })

  it('keeps an autolink whole and puts the marker just after it', () => {
    const body = 'Read <https://evil.example/x> now.'
    const { container } = renderAnswer(body, [
      citation({ offsetUtf16: 'Read <https://evil'.length }),
    ])
    expect(container.textContent).toContain('https://evil.example/x')
    expect(flattened(container)).toBe('Read https://evil.example/x[1] now.')
  })

  it('leaves an offset just before an autolink where it was', () => {
    const { container } = renderAnswer('Read <https://evil.example/x> now.', [
      citation({ offsetUtf16: 'Read '.length }),
    ])
    expect(flattened(container)).toBe('Read[1] https://evil.example/x now.')
  })
})

describe('Answer: a marker inside raw HTML', () => {
  // Raw HTML shows as the characters it was written with, so a marker in it lands in that text.
  it('turns a placeholder inside a raw HTML block into a marker, with no stray glyph', () => {
    const text = '<p>Employees accrue one hour per 30 hours worked.</p>'
    const { container } = renderAnswer(text, [
      citation({ offsetUtf16: '<p>Employees accrue one hour per 30 hours worked.'.length }),
    ])
    expect(screen.getByTestId('marker')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/[\uE000-\uF8FF]/)
    expect(container.querySelector('p')).toBeNull()
    expect(container.textContent).toContain('<p>Employees accrue one hour per 30 hours worked.')
    expect(container.textContent).toContain('</p>')
  })

  it('puts each marker at its place in an inline raw tag too', () => {
    const { container } = renderAnswer('Ten days <b>a year</b> in total.', [
      citation({ marker: 1, offsetUtf16: 'Ten days <b>a year'.length }),
      citation({ marker: 2, offsetUtf16: 'Ten days <b>a year</b> in total.'.length }),
    ])
    expect(container.querySelector('b')).toBeNull()
    expect(container.textContent).not.toMatch(/[\uE000-\uF8FF]/)
    expect(screen.getAllByTestId('marker').map((m) => m.textContent)).toEqual(['1', '2'])
  })
})

describe('Answer: a marker after a line break', () => {
  // The server puts a citation's offset at the end of its text block, which can be right after
  // the newline that ends it. The marker belongs to the claim before it, not the line after.
  it('keeps the next bullet its own item when the offset follows the newline', () => {
    const text = '- Ten days a year\n- Accrues monthly'
    renderAnswer(text, [citation({ offsetUtf16: '- Ten days a year\n'.length })])
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(within(items[0]!).getByTestId('marker')).toBeInTheDocument()
    expect(items[1]).toHaveTextContent('Accrues monthly')
    expect(within(items[1]!).queryByTestId('marker')).not.toBeInTheDocument()
  })

  it('keeps the next numbered item its own after a blank line', () => {
    const text = '1. Ten days a year\n\n2. Accrues monthly'
    const { container } = renderAnswer(text, [
      citation({ offsetUtf16: '1. Ten days a year\n\n'.length }),
    ])
    expect(container.querySelectorAll('ol')).toHaveLength(1)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(within(items[0]!).getByTestId('marker')).toBeInTheDocument()
  })

  it('puts a marker after a blank line at the end of the paragraph before it', () => {
    const { container } = renderAnswer('First claim.\n\nSecond claim.', [
      citation({ offsetUtf16: 'First claim.\n\n'.length }),
    ])
    const paragraphs = container.querySelectorAll('p')
    expect(paragraphs).toHaveLength(2)
    expect(within(paragraphs[0]!).getByTestId('marker')).toBeInTheDocument()
    expect(within(paragraphs[1]!).queryByTestId('marker')).not.toBeInTheDocument()
  })

  it('keeps bold when the offset follows the closing mark and a newline', () => {
    const { container } = renderAnswer('**Five days.**\n', [citation({ offsetUtf16: 15 })])
    expect(container.querySelector('strong')).not.toBeNull()
    expect(container.textContent).not.toContain('*')
    expect(flattened(container)).toBe('Five days.[1]')
  })

  it('keeps bold when the offset follows the closing mark and a blank line', () => {
    const { container } = renderAnswer('**Five days.**\n\nMore.', [
      citation({ offsetUtf16: '**Five days.**\n\n'.length }),
    ])
    expect(container.querySelector('strong')).not.toBeNull()
    expect(container.textContent).not.toContain('*')
    const first = container.querySelector('p')!
    expect(within(first).getByTestId('marker')).toBeInTheDocument()
  })

  it('moves back over spaces and tabs too', () => {
    const { container } = renderAnswer('Five days.  \t More.', [citation({ offsetUtf16: 12 })])
    expect(flattened(container)).toBe('Five days.[1]  \t More.')
  })
})

describe('Answer: a marker near a link', () => {
  const text = 'See [x](/handbook/4.3) now.'

  it.each([
    ['inside the link address', 'See [x](/handb'.length],
    ['between the bracket and the parenthesis', 'See [x]'.length],
    ['just before the closing parenthesis', 'See [x](/handbook/4.3'.length],
    ['just after the closing parenthesis', 'See [x](/handbook/4.3)'.length],
  ])('keeps the link and puts the marker right after it, for an offset %s', (_name, offset) => {
    const { container } = renderAnswer(text, [citation({ offsetUtf16: offset })])
    const link = screen.getByRole('link', { name: 'x' })
    expect(link).toHaveAttribute('href', '/handbook/4.3')
    expect(within(link).queryByTestId('marker')).toBeNull()
    expect(link.nextElementSibling).toBe(screen.getByTestId('marker'))
    expect(flattened(container)).toBe('See x[1] now.')
  })

  it('keeps the link when the address has nested parentheses', () => {
    const nested = 'A [x](/handbook/a_(b)) end.'
    renderAnswer(nested, [citation({ offsetUtf16: 'A [x](/handbook/a_(b'.length })])
    const link = screen.getByRole('link', { name: 'x' })
    expect(link).toHaveAttribute('href', '/handbook/a_(b)')
    expect(link.nextElementSibling).toBe(screen.getByTestId('marker'))
  })

  it('keeps a link whose address held a private-use character the model wrote', () => {
    renderAnswer('See [x](/handbook/4.3\uE000) now.')
    expect(screen.getByRole('link', { name: 'x' })).toHaveAttribute('href', '/handbook/4.3')
  })

  it('leaves an offset inside link text alone, moving its marker after the link', () => {
    renderAnswer(text, [citation({ offsetUtf16: 'See [x'.length })])
    const link = screen.getByRole('link', { name: 'x' })
    expect(link.nextElementSibling).toBe(screen.getByTestId('marker'))
  })
})

describe('Answer: the caret', () => {
  it('shows no caret after a block it cannot sit inside, so it never lands on its own line', () => {
    const { container } = renderAnswer('x\n\n# Heading', [], true)
    expect(container.querySelector('[data-slot="caret"]')).toBeNull()
  })

  it('shows no caret after a trailing fenced block', () => {
    const { container } = renderAnswer('x\n\n```\ncode\n```', [], true)
    expect(container.querySelector('[data-slot="caret"]')).toBeNull()
  })

  it('still shows the caret when only the start of the answer has arrived', () => {
    const { container } = renderAnswer('x', [], true)
    expect(container.querySelector('p [data-slot="caret"]')).not.toBeNull()
  })

  it('shows a hidden caret at the end of the last paragraph while it streams', () => {
    const { container } = renderAnswer('One.\n\nTwo', [], true)
    const paragraphs = container.querySelectorAll('p')
    expect(paragraphs[0]!.querySelector('[data-slot="caret"]')).toBeNull()
    const caret = paragraphs[1]!.querySelector('[data-slot="caret"]')
    expect(caret).toHaveAttribute('aria-hidden', 'true')
    expect(paragraphs[1]!.lastElementChild).toBe(caret)
  })

  it('shows the caret at the end of the last list item', () => {
    renderAnswer('- one\n- two', [], true)
    const items = screen.getAllByRole('listitem')
    expect(items[0]!.querySelector('[data-slot="caret"]')).toBeNull()
    expect(items[1]!.querySelector('[data-slot="caret"]')).not.toBeNull()
  })

  it('shows no caret by default', () => {
    const { container } = renderAnswer('Done.')
    expect(container.querySelector('[data-slot="caret"]')).toBeNull()
  })
})
