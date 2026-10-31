import { CASE_LIMIT_CHARACTERS } from './validate'

type Edit = {
  value: string
  /** Where the caret goes (a UTF-16 index) when an insertion was cut, so it sits after what stayed. */
  caret: number | null
}

// An edit the browser makes in bulk or for the person's input method, not one key at a time. Cutting
// what it inserted is better than refusing it: a refused composition breaks an IME, and a refused
// autocorrect leaves the misspelling.
const CUT_NOT_REFUSED = new Set([
  'insertFromPaste',
  'insertFromDrop',
  'insertCompositionText',
  'insertReplacementText',
])

/**
 * What the field holds after an edit, or null to refuse it. Counted in code points, as the server
 * counts. Within the limit the edit stands, and so does one that adds nothing (a deletion). Over
 * the limit, a bulk or input-method edit is cut: what the person inserted is found (the text that
 * differs from before, between the common start and the common end), and only that is cut, so the
 * text on either side of it stays whole. Any other edit, a keystroke, is refused.
 */
function afterEdit(previous: string, next: string, inputType: string): Edit | null {
  const before = [...previous]
  const after = [...next]
  if (after.length <= CASE_LIMIT_CHARACTERS) return { value: next, caret: null }
  if (after.length <= before.length) return { value: next, caret: null }
  if (!CUT_NOT_REFUSED.has(inputType)) return null

  const shortest = Math.min(before.length, after.length)
  let start = 0
  while (start < shortest && before[start] === after[start]) start += 1
  let end = 0
  while (
    end < shortest - start &&
    before[before.length - 1 - end] === after[after.length - 1 - end]
  ) {
    end += 1
  }
  const room = Math.max(0, CASE_LIMIT_CHARACTERS - start - end)
  const kept = after.slice(start, after.length - end).slice(0, room)
  const head = after.slice(0, start).join('') + kept.join('')
  return { value: head + after.slice(after.length - end).join(''), caret: head.length }
}

export { afterEdit }
export type { Edit }
