import type { CitationOut } from '@/api/generated'

/**
 * The citations with each `marker` replaced by its section's number: 1, 2, and so on in the
 * order each section first appears in the text (by `offsetUtf16`), returned in the order given. The API numbers every
 * distinct passage (two passages of one section are markers 1 and 2), and the design numbers every
 * source: "chip 1 and every marker 1 point to the same section", and a chip opens the first
 * passage cited from its section. Each citation still names the passage it cites, so a marker
 * still opens that passage.
 *
 * Stage 6 passes the API's raw citations. The three places a message's citations enter the
 * components apply this themselves (`AssistantMessage` for its markers, `SourceChips`, and
 * `WorkTrace`), so the numbers agree everywhere. It is safe to apply twice: numbering by section
 * again changes nothing.
 */
function numberBySection(citations: CitationOut[]): CitationOut[] {
  // Numbered by where each section first appears in the text, not by array position: the array
  // is the API's, and its order is not promised to be the text's. A stable sort keeps array order
  // for citations at the same offset.
  const inTextOrder = [...citations].sort((a, b) => a.offsetUtf16 - b.offsetUtf16)
  const numbers = new Map<string, number>()
  for (const citation of inTextOrder) {
    if (!numbers.has(citation.sectionId)) numbers.set(citation.sectionId, numbers.size + 1)
  }
  return citations.map((citation) => ({ ...citation, marker: numbers.get(citation.sectionId)! }))
}

/**
 * One citation per section, in section-number order (the order they first appear in the text),
 * each the first citation of its section in the text and numbered by section. A chip opens the
 * first passage cited from its section.
 */
function distinctSources(citations: CitationOut[]): CitationOut[] {
  return firstPerSection(numberBySection(citations))
}

/**
 * `distinctSources` for citations already numbered by `numberBySection`, so a component that needs
 * both the numbered list and the chips numbers once.
 */
function firstPerSection(numbered: CitationOut[]): CitationOut[] {
  // The numbers already follow the text, so a chip's place is its number. Its citation is the
  // earliest in the text for its section (array order breaks a tie).
  const chips: CitationOut[] = []
  for (const citation of numbered) {
    const chip = chips[citation.marker - 1]
    if (chip === undefined || citation.offsetUtf16 < chip.offsetUtf16) {
      chips[citation.marker - 1] = citation
    }
  }
  return chips
}

export { distinctSources, firstPerSection, numberBySection }
