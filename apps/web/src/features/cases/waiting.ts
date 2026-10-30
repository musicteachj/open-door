import type { CaseStatusOut } from '@/api/generated'

/** Five cases waiting for HR is the most a person may have (the server enforces it too). */
export const WAITING_CASE_LIMIT = 5

/** A case HR has not finished: new, or in review. */
export function isWaiting(c: Pick<CaseStatusOut, 'status'>): boolean {
  return c.status === 'new' || c.status === 'in_review'
}
