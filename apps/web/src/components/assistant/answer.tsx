import {
  Children,
  createContext,
  useContext,
  useMemo,
  type ComponentProps,
  type ReactNode,
} from 'react'
import ReactMarkdown, { type Components, type ExtraProps } from 'react-markdown'
import { Link } from 'react-router'
import type { CitationOut } from '@/api/generated'
import { cn } from '@/lib/utils'
import { APP_LINK } from './link-class'
import { autolinkSpans, definitionSpans, linkAddressSpans, type Span } from './link-spans'

type AnswerProps = {
  /** The answer's Markdown, as far as it has arrived. Partial text renders fine. */
  text: string
  /** Each citation's `offsetUtf16` says where its marker goes in `text`. */
  citations: CitationOut[]
  /** The marker for a citation, and its index in `citations`. The real one is `CitationMarker`. */
  renderMarker: (citation: CitationOut, index: number) => ReactNode
  /** Shows a text caret at the end of the last paragraph or list item (while text streams). */
  caret?: boolean
  className?: string
}

// A marker goes into the text as one private-use character (U+E000 plus the citation's index in
// the array), and the rehype step below turns it into a marker element. Private use is a range
// nothing writes on purpose, and the model's own are dropped first, so it can't forge a marker.
// That includes a numeric character reference to one ("&#xE000;"), which the Markdown parser would
// turn into the real character after the drop.
const PLACEHOLDER_BASE = 0xe000
const PRIVATE_USE = /[\uE000-\uF8FF]/g
// What the parser decodes: up to six hex digits or seven decimal ones, and the closing ";".
const NUMERIC_REFERENCE = /&#(?:[xX]([0-9a-fA-F]{1,6})|([0-9]{1,7}));/g
const PRIVATE_USE_FIRST = 0xe000
const PRIVATE_USE_LAST = 0xf8ff

/**
 * The text without the model's own private-use characters, written out or as a reference. Repeated
 * until nothing changes, because removing one piece can join its neighbors into a new reference
 * ("&#x&#xE000;E000;" becomes "&#xE000;"). Each pass only shortens the text, so it ends.
 */
function withoutPrivateUse(text: string): string {
  let current = text
  for (;;) {
    const next = current
      .replace(PRIVATE_USE, '')
      .replace(NUMERIC_REFERENCE, (reference, hex, decimal) => {
        const code = hex === undefined ? Number.parseInt(decimal, 10) : Number.parseInt(hex, 16)
        return code >= PRIVATE_USE_FIRST && code <= PRIVATE_USE_LAST ? '' : reference
      })
    if (next === current) return current
    current = next
  }
}
const PLACEHOLDER_PATTERN = /([\uE000-\uF8FF])/

const MARKER_TAG = 'od-marker'
const CARET_TAG = 'od-caret'

const WHITESPACE = /\s/
const EMPHASIS = /[*_]/
const WORD_CHARACTER = /[\p{L}\p{N}]/u
// What a line holds before the space of a list item that has no text yet: "-", "+", "1." or "1)".
const BARE_LIST_MARKER = /^ {0,3}(?:[-+]|\d{1,9}[.)])$/

/**
 * Whether the run of "*" and "_" at `from` to `to` can close an emphasis span. It can when
 * something that is not whitespace comes just before it: a run at the start of a line is a list
 * bullet or an opener, and one after whitespace opens. An underscore after a letter or digit
 * closes only when an underscore earlier on the line could have opened the span ("_form A_"),
 * because inside a word ("form_A_") underscores are just characters.
 */
function closesEmphasis(text: string, from: number, to: number): boolean {
  if (from === 0 || WHITESPACE.test(text[from - 1]!)) return false
  if (!text.slice(from, to).includes('_') || !WORD_CHARACTER.test(text[from - 1]!)) return true
  const lineStart = text.lastIndexOf('\n', from - 1) + 1
  for (let i = from - 1; i >= lineStart; i--) {
    if (text[i] !== '_') continue
    const before = text[i - 1]
    const after = text[i + 1]
    const opens =
      (before === undefined || i === lineStart || !WORD_CHARACTER.test(before)) &&
      after !== undefined &&
      !WHITESPACE.test(after)
    if (opens) return true
  }
  return false
}

/**
 * Where a marker lands. It stays inside the text, and it never goes:
 * - in the middle of a link's address, or between "]" and "(": it goes just after the ")"
 * - just after trailing whitespace or a run of "*" or "_" that closes an emphasis span: it goes
 *   back over them, to the end of the claim. A run that is not closing (a list bullet, or the "_"
 *   that ends a word like "form_A_") is left where it is, with the whitespace after it. So is the
 *   space after a bare "-", "+" or "1." at the start of a line. The server puts an offset at the end of a text block, which can be right after the
 *   "\n" that ends it, and a placeholder at the start of the next line would fold a bullet or a
 *   numbered item into the one above, or put the marker on the next paragraph. And a placeholder
 *   just after a closing "**" would not count as space or punctuation, and the bold would stay
 *   literal asterisks
 * - in the middle of an emoji's two code units: it goes after the emoji
 */
/** The stretches of the text a marker must not land in, and which way each one moves it. */
type Protected = { links: Span[]; autolinks: Span[]; definitions: Span[] }

/**
 * Moves an offset out of an address: after an inline link's ")" or an autolink's ">", or before a
 * reference definition line (a marker there would become part of the address).
 */
function outOfAddresses(at: number, protectedSpans: Protected): number {
  const link = protectedSpans.links.find((span) => at >= span.from && at < span.end)
  if (link) return link.end
  const autolink = protectedSpans.autolinks.find((span) => at > span.from && at < span.end)
  if (autolink) return autolink.end
  const definition = protectedSpans.definitions.find((span) => at > span.from && at <= span.end)
  return definition ? definition.from : at
}

function markerOffset(offset: number, text: string, protectedSpans: Protected): number {
  if (!Number.isFinite(offset)) return text.length
  const clamped = Math.min(Math.max(Math.trunc(offset), 0), text.length)
  // Stepping back over whitespace can land in an address (the text after a definition line begins
  // with the line break that ends it), so the two repeat until the offset stops moving.
  let at = clamped
  for (let round = 0; round < 4; round++) {
    const moved = stepToClaimEnd(outOfAddresses(at, protectedSpans), text)
    if (moved === at) break
    at = moved
  }
  const splitsPair =
    at > 0 &&
    at < text.length &&
    /[\uD800-\uDBFF]/.test(text[at - 1]!) &&
    /[\uDC00-\uDFFF]/.test(text[at]!)
  return splitsPair ? at + 1 : at
}

/** Back over trailing whitespace and closing delimiters, to the end of the claim before them. */
function stepToClaimEnd(start: number, text: string): number {
  let at = start
  // An offset strictly inside a run of "*" or "_" (between the two asterisks of "**") would split
  // the delimiter and leave it as literal characters, so it goes to the run's start. A closing run
  // is then stepped back over below, which is where it belongs anyway.
  if (at > 0 && at < text.length && EMPHASIS.test(text[at - 1]!) && EMPHASIS.test(text[at]!)) {
    while (at > 0 && EMPHASIS.test(text[at - 1]!)) at--
  }
  for (;;) {
    let probe = at
    while (probe > 0 && WHITESPACE.test(text[probe - 1]!)) probe--
    let run = probe
    while (run > 0 && EMPHASIS.test(text[run - 1]!)) run--
    if (run === probe) {
      // The space after a bare list marker at the start of a line is what makes it a list item,
      // so it stays, and the marker goes in that item.
      const lineStart = text.lastIndexOf('\n', probe - 1) + 1
      if (probe < at && BARE_LIST_MARKER.test(text.slice(lineStart, probe))) break
      at = probe
      break
    }
    // A run that does not close a span stays as it is, and so does the whitespace after it.
    if (!closesEmphasis(text, run, probe)) break
    at = run
  }
  return at
}

/**
 * The text with a placeholder at each citation's offset. The offsets are indices into the text as
 * the model wrote it, so the walk goes over that original and drops its private-use characters as
 * it goes, which keeps every offset where the server meant it. Two at one offset keep the array's
 * order, and an offset past the end goes at the end.
 */
function withPlaceholders(text: string, citations: CitationOut[]): string {
  // Nothing to place: no scan for link addresses and no rebuild, only the model's own private-use
  // characters dropped, which must happen either way.
  if (citations.length === 0) return withoutPrivateUse(text)
  const protectedSpans: Protected = {
    links: linkAddressSpans(text),
    autolinks: autolinkSpans(text),
    definitions: definitionSpans(text),
  }
  const slots = citations
    .map((citation, index) => ({
      index,
      at: markerOffset(citation.offsetUtf16, text, protectedSpans),
    }))
    .sort((a, b) => a.at - b.at || a.index - b.index)
  // The text between the places, each stretch cleaned once, with a placeholder at each place.
  let out = ''
  let from = 0
  for (const slot of slots) {
    out += withoutPrivateUse(text.slice(from, slot.at))
    out += String.fromCharCode(PLACEHOLDER_BASE + slot.index)
    from = slot.at
  }
  out += withoutPrivateUse(text.slice(from))
  return out
}

// Just the parts of a hast tree this plugin touches. (react-markdown's own types name the node
// type but not the root, and the plugin only needs a tree it can walk.)
type HastNode = {
  type: string
  value?: string
  tagName?: string
  properties?: Record<string, unknown>
  children?: HastNode[]
}

function element(tagName: string, properties: Record<string, unknown> = {}): HastNode {
  return { type: 'element', tagName, properties, children: [] }
}

/**
 * Replaces each placeholder in the text with a marker element, wherever the text is: in a
 * paragraph, a list item, bold, italic, or a raw HTML block. A marker inside a link goes just after the link, so a
 * button is never inside an anchor.
 */
function convert(children: HastNode[], hoisted?: HastNode[]): HastNode[] {
  const out: HastNode[] = []
  for (const child of children) {
    // An image is never rendered, and never loads: it becomes its alt text, as plain text, so a
    // reader still gets the words. It is then split for markers like any other text.
    const node: HastNode =
      child.type === 'element' && child.tagName === 'img'
        ? {
            type: 'text',
            value: typeof child.properties?.alt === 'string' ? child.properties.alt : '',
          }
        : child
    // A raw HTML node is shown as the characters it was written with (there is no raw-HTML
    // plugin), so its text is text like any other, and a marker inside it is split out the same way.
    if (node.type === 'text' || node.type === 'raw') {
      const pieces = (node.value ?? '').split(PLACEHOLDER_PATTERN)
      for (const piece of pieces) {
        if (piece === '') continue
        if (PLACEHOLDER_PATTERN.test(piece)) {
          const marker = element(MARKER_TAG, { dataIndex: piece.charCodeAt(0) - PLACEHOLDER_BASE })
          ;(hoisted ?? out).push(marker)
        } else {
          out.push({ type: 'text', value: piece })
        }
      }
    } else if (node.type === 'element' && node.tagName === 'a') {
      const fromLink: HastNode[] = []
      node.children = convert(node.children ?? [], fromLink)
      out.push(node, ...fromLink)
    } else {
      if (node.children) node.children = convert(node.children, hoisted)
      out.push(node)
    }
  }
  return out
}

const CARET_CONTAINERS = new Set(['p', 'ul', 'ol', 'li'])

/** Puts the caret at the end of the last paragraph or list item, so it sits in the text. */
function appendCaret(root: HastNode) {
  let target = root
  for (;;) {
    const last = (target.children ?? []).findLast(
      (child) => child.type !== 'text' || (child.value ?? '').trim() !== '',
    )
    if (last?.type === 'element' && CARET_CONTAINERS.has(last.tagName ?? '')) target = last
    else break
  }
  // A last block that is not a paragraph or list (a heading or a code block, which render as bare
  // text) has no inline place for a caret, and one at the root would sit on a line of its own.
  const hasContent = (target.children ?? []).some(
    (child) => child.type !== 'text' || (child.value ?? '').trim() !== '',
  )
  if (target === root && hasContent) return
  target.children = [...(target.children ?? []), element(CARET_TAG)]
}

function rehypeMarkers({ caret }: { caret: boolean }) {
  return (tree: HastNode) => {
    tree.children = convert(tree.children ?? [])
    if (caret) appendCaret(tree)
  }
}

// The components below are the same functions on every render, so a marker keeps its state (its
// focus, an open popover) while the text streams. What varies comes through this context.
const MarkerContext = createContext<Pick<AnswerProps, 'citations' | 'renderMarker'>>({
  citations: [],
  renderMarker: () => null,
})

function MarkerSlot({ node }: ExtraProps) {
  const { citations, renderMarker } = useContext(MarkerContext)
  const index = Number(node?.properties.dataIndex)
  const citation = citations[index]
  return citation === undefined ? null : renderMarker(citation, index)
}

function CaretSlot() {
  return (
    <span
      data-slot="caret"
      aria-hidden="true"
      className="ml-[3px] inline-block h-[18px] w-0.5 rounded-[1px] bg-ink-muted align-[-4px]"
    />
  )
}

/**
 * Only a path inside the app is a link: under /handbook/ or /directory/, with no "." or ".."
 * segment (written plainly or percent-encoded, since the router would resolve it to a page
 * outside those two) and no backslash. Anything else shows as its text.
 */
function isAppPath(href: string): boolean {
  if (!href.startsWith('/handbook/') && !href.startsWith('/directory/')) return false
  const path = href.split(/[?#]/, 1)[0]!
  let decoded: string
  try {
    decoded = decodeURIComponent(path)
  } catch {
    return false
  }
  if (decoded.includes('\\')) return false
  return !decoded.split('/').some((segment) => segment === '.' || segment === '..')
}

function AnswerLink({ href, children }: ComponentProps<'a'> & ExtraProps) {
  // react-markdown has already blanked the schemes it distrusts. This allow-list is the real check.
  // A link with nothing left inside (it held only an image with no alt text) would be an anchor with
  // no name.
  if (!isAppPath(href ?? '') || Children.toArray(children).length === 0) return <>{children}</>
  return (
    <Link to={href!} className={APP_LINK}>
      {children}
    </Link>
  )
}

const components = {
  a: AnswerLink,
  [MARKER_TAG]: MarkerSlot,
  [CARET_TAG]: CaretSlot,
} as Components

// Only these elements render. Anything else (a heading, code, a quote) keeps its text and loses
// its element. An image has no text of its own, so the rehype step above turns it into its alt
// text first, and the image itself is never rendered. There is no raw-HTML plugin, so the model's HTML shows as characters.
const ALLOWED_ELEMENTS = ['p', 'strong', 'em', 'ul', 'ol', 'li', 'a', 'br', MARKER_TAG, CARET_TAG]

/**
 * The assistant's answer: a Markdown subset (paragraphs, bold, italic, lists, links to the
 * handbook and the directory) and its citation markers, as React elements. Never HTML strings,
 * and no remark-gfm, so a bare URL stays text. Raw HTML shows as the characters it was written
 * with, and a link that isn't a handbook or directory path shows as its text, so the model can't
 * send a reader off the site (the Review focus, item 3 of the Phase 4 plan).
 */
function Answer({ text, citations, renderMarker, caret = false, className }: AnswerProps) {
  // The text with its placeholders, worked out again only when the text or the citations change.
  const marked = useMemo(() => withPlaceholders(text, citations), [text, citations])
  const context = useMemo(() => ({ citations, renderMarker }), [citations, renderMarker])
  return (
    <MarkerContext.Provider value={context}>
      <div
        data-slot="answer"
        className={cn(
          'flex flex-col gap-3 text-body text-pretty text-ink [&_li]:my-1 [&_ol]:m-0 [&_ol]:list-decimal [&_ol]:pl-6 [&_p]:m-0 [&_ul]:m-0 [&_ul]:list-disc [&_ul]:pl-6',
          className,
        )}
      >
        <ReactMarkdown
          allowedElements={ALLOWED_ELEMENTS}
          unwrapDisallowed
          rehypePlugins={[[rehypeMarkers, { caret }]]}
          components={components}
        >
          {marked}
        </ReactMarkdown>
      </div>
    </MarkerContext.Provider>
  )
}

export { Answer }
export type { AnswerProps }
