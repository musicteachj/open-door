export const MIN_HOURS = 1
export const MAX_HOURS = 8

/** The text as a whole number (spaces around it are fine), or null when it is anything else. */
export function wholeNumber(value: string): number | null {
  const text = value.trim()
  return /^\d+$/.test(text) ? Number(text) : null
}

/**
 * The hours in the box as a number, or null when it is not a whole number from 1 to 8. Spaces
 * around it and a leading zero are fine ("08" is 8). The parent owns the text, so it uses this to
 * read it.
 */
export function parseHours(value: string): number | null {
  const hours = wholeNumber(value)
  return hours !== null && hours >= MIN_HOURS && hours <= MAX_HOURS ? hours : null
}
