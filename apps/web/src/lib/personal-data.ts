// A check for Social Security and card numbers in a person's message, run before a question is
// sent so the number never leaves the browser. It is a port of apps/api/app/ai/personal_data.py,
// and both read evals/assistant/personal-data-cases.json, so they cannot drift. Pure: it never
// records the text it reads.

export type PersonalDataKind = 'ssn' | 'card'

// Three digits, two, then four, joined by dashes or spaces, not part of a longer digit run.
const SSN = /(?<![0-9])[0-9]{3}[- ][0-9]{2}[- ][0-9]{4}(?![0-9])/

// A card number: a plausible issuer digit first (2 to 6), then either 13 to 19 digits in one run,
// or digits grouped the way cards are printed, joined by single spaces or dashes: groups of 4 (and
// a last group of 1 to 4 for 17 to 19 digits), or 4-6-5, or 4-6-4. Loose grouping would flag
// dates: "2026-10-19 2026-10-23" is 16 digits and passes the Luhn check one time in ten.
const SEP = '[ -]'
const CARD_CANDIDATE = new RegExp(
  '(?<![0-9])(?:' +
    '[2-6][0-9]{12,18}' +
    `|[2-6][0-9]{3}(?:${SEP}[0-9]{4}){2,3}(?:${SEP}[0-9]{1,4})?` +
    `|[2-6][0-9]{3}${SEP}[0-9]{6}${SEP}[0-9]{4,5}` +
    ')(?![0-9])',
  'g',
)

const FORMAT = /^\p{Cf}$/u
const SPACE_SEPARATOR = /^\p{Zs}$/u
const DASH = /^\p{Pd}$/u

/**
 * The text as the check reads it, in the steps the shared vectors' `about` lists: NFKC, drop
 * format characters (Cf), space separators (Zs) to an ASCII space, and dashes (Pd) to an ASCII
 * hyphen. Digits are then matched as ASCII only.
 */
export function normalized(text: string): string {
  let out = ''
  // Iterating a string yields whole code points, so an astral character is one step.
  for (const char of text.normalize('NFKC')) {
    if (FORMAT.test(char)) continue
    out += SPACE_SEPARATOR.test(char) ? ' ' : DASH.test(char) ? '-' : char
  }
  return out
}

function passesLuhn(digits: string): boolean {
  let total = 0
  const reversed = [...digits].reverse()
  for (const [index, character] of reversed.entries()) {
    let value = Number(character)
    if (index % 2 === 1) {
      value *= 2
      if (value > 9) value -= 9
    }
    total += value
  }
  return total % 10 === 0
}

/** What kind of personal number `text` holds, or null. A Social Security number wins a tie. */
export function kindOfPersonalData(text: string): PersonalDataKind | null {
  const read = normalized(text)
  if (SSN.test(read)) return 'ssn'
  for (const match of read.matchAll(CARD_CANDIDATE)) {
    const digits = match[0].replace(/[^0-9]/g, '')
    if (digits.length >= 13 && digits.length <= 19 && passesLuhn(digits)) return 'card'
  }
  return null
}
