import type { Category } from '@/api/generated'
import { trimLikePython } from '@/components/assistant/text-count'
import { kindOfPersonalData } from '@/lib/personal-data'

/** The most characters of words the form lets a person send. */
export const CASE_LIMIT_CHARACTERS = 4000

/** What Send to HR found wrong, in the order the notes give. */
export type CaseProblem = 'category' | 'empty' | 'personal-data' | 'limit'

/**
 * The words' length as the server counts it: Python's `len()` counts code points, so an emoji is
 * one. Not trimmed: the server checks the length of the words as sent.
 */
export function characterCountOf(text: string): number {
  return [...text].length
}

/**
 * Every problem with the form, in order: no category; empty words (Python's `strip()` leaves
 * nothing); a Social Security or card number; the limit. The server repeats each check. Empty
 * words and a number never come together, since a number is words.
 *
 * The limit differs from the server on purpose: the server accepts exactly 4,000 characters, but
 * the design blocks sending there ("4,000 of 4,000 characters. Shorten it to send."), so the form
 * can never send a case the person could not tell was cut.
 */
export function validateCase(form: { category: Category | null; text: string }): CaseProblem[] {
  const problems: CaseProblem[] = []
  if (form.category === null) problems.push('category')
  if (trimLikePython(form.text) === '') problems.push('empty')
  else if (kindOfPersonalData(form.text) !== null) problems.push('personal-data')
  if (characterCountOf(form.text) >= CASE_LIMIT_CHARACTERS) problems.push('limit')
  return problems
}
