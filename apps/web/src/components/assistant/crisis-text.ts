// Turns the crisis panel's fixed text into paragraphs, a bullet list, and a few links. The text
// is plain: paragraphs apart by a blank line, and a block of "- " lines. It is written and
// approved by a person (apps/api/app/ai/fixed_texts.py) and arrives in the stream, so this only
// adds structure. It never changes, adds, or drops a word, and a line that matches no pattern
// stays plain text, so a rewording of the text can't break the panel.

/** A run of text, and the address it links to when it is a link. */
type CrisisSegment = {
  text: string
  href?: string
  external?: boolean
  /** A phone number written out (1-800-555-0137), which the panel keeps on one line. */
  phone?: boolean
}

type CrisisBlock =
  { kind: 'paragraph'; segments: CrisisSegment[] } | { kind: 'list'; items: CrisisSegment[][] }

// The only things that become links: the 911 and 988 calls, the Lifeline's chat address, and a
// phone number written 1-800-555-0137. A new wording is plain text until it is added here.
const LINKABLE =
  /\bcall 911\b|\bcall or text 988\b|\bchat\.988lifeline\.org\b|(?<![\d-])\b1-\d{3}-\d{3}-\d{4}\b/gi

function segmentFor(match: string): CrisisSegment {
  const lower = match.toLowerCase()
  if (lower === 'call 911') return { text: match, href: 'tel:911' }
  if (lower === 'call or text 988') return { text: match, href: 'tel:988' }
  if (lower === 'chat.988lifeline.org') {
    return { text: match, href: 'https://chat.988lifeline.org', external: true }
  }
  return { text: match, href: `tel:+${match.replace(/\D/g, '')}`, phone: true }
}

/**
 * `text` as plain segments and a link segment for each match of `pattern` (which must be global),
 * which read back as the same text, word for word.
 */
function linkify(text: string, pattern: RegExp): CrisisSegment[] {
  const segments: CrisisSegment[] = []
  let from = 0
  for (const match of text.matchAll(pattern)) {
    if (match.index > from) segments.push({ text: text.slice(from, match.index) })
    segments.push(segmentFor(match[0]))
    from = match.index + match[0].length
  }
  if (from < text.length) segments.push({ text: text.slice(from) })
  return segments
}

/** One line of the crisis text, with its fixed set of links. */
function linkifyCrisis(line: string): CrisisSegment[] {
  return linkify(line, LINKABLE)
}

// The 911 and 988 calls alone, for the fixed texts that have no list: "can't answer right now" and
// the two budget banners. Only the first letter may be a capital, as the texts are written.
const EMERGENCY = /\b(?:[Cc]all 911|[Cc]all or text 988)\b/g

/**
 * One fixed text as plain segments and a `tel:` link for each "call 911" and "call or text 988".
 * Nothing else links, and the segments read back as the same text, word for word.
 */
function linkifyEmergency(text: string): CrisisSegment[] {
  return linkify(text, EMERGENCY)
}

const BULLET = /^- /

/**
 * The text as blocks: a paragraph for each run of plain lines, and a list for each run of "- "
 * lines. A blank line ends a block, and a bullet line starts a list even with no blank line above.
 */
function parseCrisisText(text: string): CrisisBlock[] {
  const blocks: CrisisBlock[] = []
  for (const chunk of text.split(/\r?\n[ \t]*\r?\n/)) {
    let paragraph: string[] = []
    let items: CrisisSegment[][] = []
    const flush = () => {
      if (paragraph.length > 0) {
        blocks.push({ kind: 'paragraph', segments: linkifyCrisis(paragraph.join('\n')) })
      }
      if (items.length > 0) blocks.push({ kind: 'list', items })
      paragraph = []
      items = []
    }
    for (const line of chunk.split(/\r?\n/)) {
      if (line.trim() === '') continue
      if (BULLET.test(line)) {
        if (paragraph.length > 0) flush()
        items.push(linkifyCrisis(line.replace(BULLET, '')))
      } else {
        if (items.length > 0) flush()
        paragraph.push(line)
      }
    }
    flush()
  }
  return blocks
}

export { linkifyCrisis, linkifyEmergency, parseCrisisText }
export type { CrisisBlock, CrisisSegment }
