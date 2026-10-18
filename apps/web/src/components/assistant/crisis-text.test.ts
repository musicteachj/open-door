import { describe, expect, it } from 'vitest'
import {
  linkifyCrisis,
  linkifyEmergency,
  parseCrisisText,
  type CrisisBlock,
  type CrisisSegment,
} from './crisis-text'

// A copy of CRISIS_TEXT in apps/api/app/ai/fixed_texts.py, for these tests only. The app never
// holds its own copy: the text arrives in the stream's `escalation` event.
const CRISIS_TEXT = `I'm an AI assistant, and what you wrote sounds serious, so I want to make sure you can reach a person right now.

- If you or someone else is in immediate danger, call 911.
- Call or text 988 to reach the 988 Suicide & Crisis Lifeline, or chat at chat.988lifeline.org. It's free, confidential, and available 24/7.
- The Juniper Row Employee Assistance Program (EAP) offers free, confidential counseling, 24 hours a day: 1-800-555-0137.
- You can also talk to someone on the HR team. Their contact details are below.

You don't have to go through this alone.`

const words = (segments: CrisisSegment[]) => segments.map((s) => s.text).join('')
const links = (segments: CrisisSegment[]) => segments.filter((s) => s.href !== undefined)

describe('linkifyCrisis', () => {
  it('links "call 911" to tel:911, leaving the sentence as it was', () => {
    const segments = linkifyCrisis('If you are in danger, call 911.')
    expect(links(segments)).toEqual([{ text: 'call 911', href: 'tel:911' }])
    expect(words(segments)).toBe('If you are in danger, call 911.')
  })

  it('links "Call or text 988" to tel:988', () => {
    const segments = linkifyCrisis('Call or text 988 to reach the Lifeline.')
    expect(links(segments)).toEqual([{ text: 'Call or text 988', href: 'tel:988' }])
  })

  it('links the chat address to https, as an external link', () => {
    const segments = linkifyCrisis('or chat at chat.988lifeline.org. It is free.')
    expect(links(segments)).toEqual([
      { text: 'chat.988lifeline.org', href: 'https://chat.988lifeline.org', external: true },
    ])
    expect(words(segments)).toBe('or chat at chat.988lifeline.org. It is free.')
  })

  it('links a phone number to a tel: link with the country code and no dashes', () => {
    const segments = linkifyCrisis('a day: 1-800-555-0137.')
    expect(links(segments)).toEqual([
      { text: '1-800-555-0137', href: 'tel:+18005550137', phone: true },
    ])
  })

  it('flags only the phone number, so the panel can set its digits apart', () => {
    const segments = linkifyCrisis(
      'call 911 or Call or text 988 or chat.988lifeline.org or 1-800-555-0137',
    )
    expect(links(segments).map((s) => [s.text, s.phone === true])).toEqual([
      ['call 911', false],
      ['Call or text 988', false],
      ['chat.988lifeline.org', false],
      ['1-800-555-0137', true],
    ])
  })

  it('finds several in one line, in order', () => {
    const segments = linkifyCrisis('call 911 or Call or text 988 or 1-800-555-0137')
    expect(links(segments).map((s) => s.href)).toEqual(['tel:911', 'tel:988', 'tel:+18005550137'])
  })

  it('leaves text that matches nothing as one plain segment', () => {
    expect(linkifyCrisis('Please reach out to someone you trust.')).toEqual([
      { text: 'Please reach out to someone you trust.' },
    ])
  })

  it('leaves a changed wording plain, so a rewrite can never break the panel', () => {
    const segments = linkifyCrisis('Dial 911 now, or ring 988 for the Lifeline at 800 555 0137.')
    expect(links(segments)).toEqual([])
    expect(words(segments)).toBe('Dial 911 now, or ring 988 for the Lifeline at 800 555 0137.')
  })

  it('does not link a bare number inside a longer one', () => {
    expect(links(linkifyCrisis('Case 29118 and 9889 are not phone numbers.'))).toEqual([])
  })

  it('has no segment with an empty text', () => {
    for (const line of ['call 911', 'x call 911', 'call 911 x', '']) {
      expect(linkifyCrisis(line).every((s) => s.text !== '')).toBe(true)
    }
  })
})

describe('parseCrisisText: the approved crisis text', () => {
  const blocks = parseCrisisText(CRISIS_TEXT)
  const paragraphs = blocks.filter((b) => b.kind === 'paragraph')
  const lists = blocks.filter((b): b is Extract<CrisisBlock, { kind: 'list' }> => b.kind === 'list')

  it('has two paragraphs around one list of four items', () => {
    expect(blocks.map((b) => b.kind)).toEqual(['paragraph', 'list', 'paragraph'])
    expect(paragraphs).toHaveLength(2)
    expect(lists[0]!.items).toHaveLength(4)
  })

  it('links 911, 988, the chat address, and the EAP number, and nothing else', () => {
    const all = lists[0]!.items.flatMap(links)
    expect(all.map((s) => [s.text, s.href])).toEqual([
      ['call 911', 'tel:911'],
      ['Call or text 988', 'tel:988'],
      ['chat.988lifeline.org', 'https://chat.988lifeline.org'],
      ['1-800-555-0137', 'tel:+18005550137'],
    ])
    expect(paragraphs.flatMap((p) => links(p.segments))).toEqual([])
  })

  it('keeps every word: the text is the same once the "- " markers and line breaks go', () => {
    const rebuilt = blocks
      .map((b) => (b.kind === 'paragraph' ? words(b.segments) : b.items.map(words).join(' ')))
      .join(' ')
    const original = CRISIS_TEXT.replace(/^- /gm, '').replace(/\s+/g, ' ')
    expect(rebuilt).toBe(original)
  })

  it('opens the chat link in a new tab, and no other', () => {
    const all = lists[0]!.items.flatMap(links)
    expect(all.filter((s) => s.external).map((s) => s.text)).toEqual(['chat.988lifeline.org'])
  })
})

describe('parseCrisisText: line endings', () => {
  it('reads the approved text the same with CRLF line endings', () => {
    const crlf = CRISIS_TEXT.replace(/\n/g, '\r\n')
    expect(parseCrisisText(crlf)).toEqual(parseCrisisText(CRISIS_TEXT))
  })

  it('leaves no carriage return in any segment', () => {
    const blocks = parseCrisisText('First.\r\n\r\n- one\r\n- two\r\n\r\nLast.')
    expect(blocks.map((b) => b.kind)).toEqual(['paragraph', 'list', 'paragraph'])
    const text = JSON.stringify(blocks)
    expect(text).not.toContain('\\r')
  })
})

describe('parseCrisisText: paragraphs apart by a CRLF blank line', () => {
  it('makes two paragraphs, not one', () => {
    expect(parseCrisisText('One.\r\n\r\nTwo.')).toEqual([
      { kind: 'paragraph', segments: [{ text: 'One.' }] },
      { kind: 'paragraph', segments: [{ text: 'Two.' }] },
    ])
  })
})

describe('parseCrisisText: other shapes', () => {
  it('makes a paragraph of plain text with no blank line or bullet', () => {
    expect(parseCrisisText('Just one line.')).toEqual([
      { kind: 'paragraph', segments: [{ text: 'Just one line.' }] },
    ])
  })

  it('splits a list from a line above it with no blank line between', () => {
    const blocks = parseCrisisText('Reach out:\n- first\n- second')
    expect(blocks.map((b) => b.kind)).toEqual(['paragraph', 'list'])
  })

  it('treats a dash without a space as text, not a bullet', () => {
    expect(parseCrisisText('-not a bullet')).toEqual([
      { kind: 'paragraph', segments: [{ text: '-not a bullet' }] },
    ])
  })

  it('has no blocks for empty text', () => {
    expect(parseCrisisText('')).toEqual([])
    expect(parseCrisisText('\n\n  \n')).toEqual([])
  })
})

describe('linkifyEmergency: the 911 and 988 calls in the other fixed texts', () => {
  const UNAVAILABLE =
    "I'm an AI assistant, and I can't answer right now. If you or someone else is in danger, call 911, or call or text 988 to reach the 988 Suicide & Crisis Lifeline. Chat at chat.988lifeline.org or call 1-800-555-0137."

  it('links "call 911" and "call or text 988", and reads back as the same text', () => {
    const segments = linkifyEmergency(UNAVAILABLE)
    expect(links(segments)).toEqual([
      { text: 'call 911', href: 'tel:911' },
      { text: 'call or text 988', href: 'tel:988' },
    ])
    expect(words(segments)).toBe(UNAVAILABLE)
  })

  it('matches a capital first letter, and only the first letter', () => {
    expect(
      links(linkifyEmergency('Call or text 988 now. Call 911 now.')).map((s) => s.href),
    ).toEqual(['tel:988', 'tel:911'])
    expect(links(linkifyEmergency('CALL 911 or CALL OR TEXT 988'))).toEqual([])
  })

  it('links nothing else: not the chat address, not a phone number, not a bare 988', () => {
    const text = 'Chat at chat.988lifeline.org, dial 1-800-555-0137, or ring 988 or 911.'
    expect(links(linkifyEmergency(text))).toEqual([])
    expect(words(linkifyEmergency(text))).toBe(text)
  })

  it('has no segment with an empty text', () => {
    for (const line of ['call 911', 'x call 911', 'call 911 x', '']) {
      expect(linkifyEmergency(line).every((s) => s.text !== '')).toBe(true)
    }
  })
})
