export type LabelParts = {
  /** The part before the parenthesis: "92 hours". */
  hours: string
  /** The part inside it: "11.5 days" or "half a day". Missing when the label has none. */
  days?: string
}

/**
 * Splits an API amount label so a card can show the hours large and the days beneath:
 * "92 hours (11.5 days)" becomes "92 hours" and "11.5 days". This is string handling only. The
 * browser never works out a figure; every number here came from the API's own label.
 */
export function splitLabel(label: string): LabelParts {
  const open = label.indexOf(' (')
  if (open === -1 || !label.endsWith(')')) return { hours: label }
  return { hours: label.slice(0, open), days: label.slice(open + 2, -1) }
}
