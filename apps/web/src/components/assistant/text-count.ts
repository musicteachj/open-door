// How the API measures a typed text. It strips the text with Python's str.strip() and counts it
// with len(), which counts code points. JavaScript's trim() strips a slightly different set, so
// the composer and the feedback box use these, to agree with the server on where the limit is.

// The characters Python's str.isspace() accepts: the Unicode White_Space characters, minus
// U+FEFF (which JavaScript's trim() strips and Python does not), plus U+001C to U+001F and
// U+0085 (which Python strips and trim() does not). Checked against Python on 2026-10-17.
const SPACE =
  '[\\t-\\r\\u001c-\\u0020\\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]'
const EDGES = new RegExp(`^${SPACE}+|${SPACE}+$`, 'g')

/** The text with Python's str.strip() applied. */
function trimLikePython(text: string): string {
  return text.replace(EDGES, '')
}

/** The trimmed text's length in code points, which is what the API's limits count. */
function characterCount(text: string): number {
  return [...trimLikePython(text)].length
}

export { characterCount, trimLikePython }
