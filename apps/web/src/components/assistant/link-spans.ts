/**
 * The span of each inline link's address, from its "(" to just after its closing ")", found by
 * balancing parentheses. A marker in one of these spans would split the link, so it goes after the
 * ")". An address that never closes (the link is still streaming) has no span, and neither does
 * one that a blank line ends.
 *
 * One pass over the text matches every "(" with its ")" (a backslash escapes the next character,
 * and a blank line forgets the parentheses still open), so the work grows with the text. Scanning
 * on from each "](" would rescan the same text for every address that never closes.
 */
/** Whether the line starting at `from` is blank: only spaces and tabs before its line break. */
function blankLineFollows(text: string, from: number): boolean {
  let at = from
  while (text[at] === ' ' || text[at] === '\t') at++
  return text[at] === '\n' || (text[at] === '\r' && text[at + 1] === '\n')
}

type Span = { from: number; end: number }

/** The span of each inline link's address (see below). */
function linkAddressSpans(text: string): { from: number; end: number }[] {
  const closeOf = new Map<number, number>()
  const open: number[] = []
  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    if (char === '\\') i++
    else if (char === '\n' && blankLineFollows(text, i + 1)) open.length = 0
    else if (char === '(') open.push(i)
    else if (char === ')' && open.length > 0) closeOf.set(open.pop()!, i)
  }
  const spans: { from: number; end: number }[] = []
  for (let at = text.indexOf(']('); at !== -1; at = text.indexOf('](', at + 2)) {
    const close = closeOf.get(at + 1)
    if (close !== undefined) spans.push({ from: at + 1, end: close + 1 })
  }
  return spans
}

// A reference definition: "[1]: /handbook/4.3", up to three spaces in, with an address after it.
const DEFINITION = /^ {0,3}\[[^\]\n]+\]:[ \t]*\S[^\n]*/gm

/**
 * Each reference-link definition line, from its start to its end (not its line break). The line is
 * an address, so a marker in or at the end of one would become part of that address and vanish.
 * It goes before the line, with the text it follows.
 */
function definitionSpans(text: string): Span[] {
  return [...text.matchAll(DEFINITION)].map((match) => ({
    from: match.index,
    end: match.index + match[0].length,
  }))
}

// An autolink: "<https://example.org>" or "<mailto:a@b.example>". A scheme and a colon tell it from
// an HTML tag, and it holds no space or angle bracket.
const AUTOLINK = /<[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*>/g

/** Each autolink, from its "<" to just after its ">". A marker inside it goes just after. */
function autolinkSpans(text: string): Span[] {
  return [...text.matchAll(AUTOLINK)].map((match) => ({
    from: match.index,
    end: match.index + match[0].length,
  }))
}

export { autolinkSpans, definitionSpans, linkAddressSpans }
export type { Span }
