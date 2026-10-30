import { expect, type Page } from '@playwright/test'

// Shared by cases.spec.ts and the capture run: the steps of opening a confidential case and
// reading HR's pages back. Every case goes to the real API, and the scripted model (the browser
// tests pin AI_TRANSPORT=scripted) screens and summarizes it, so nothing here costs a cent.

/** The demo's message: the scripted guard calls it sensitive, so the panel offers a case. */
export const SENSITIVE_QUESTION = 'My manager keeps making comments about my age.'
/** Words the scripted guard routes to crisis text when a case is screened. */
export const CRISIS_WORDS = 'Some days I want to hurt myself and I do not know who to tell.'
/** The fixed fact under a crisis case in the queue and the detail. */
export const CRISIS_FACT = 'The safety check routed this message to crisis text.'

export const HARASSMENT = 'Harassment or discrimination'

export const openCaseButton = (page: Page) =>
  page.getByRole('button', { name: 'Open a confidential case' })
export const formHeading = (page: Page) =>
  page.getByRole('heading', { name: 'Open a confidential case', exact: true })
export const wordsBox = (page: Page) => page.getByRole('textbox', { name: 'Your words' })
export const sendButton = (page: Page) =>
  page.getByRole('button', { name: /^Send to HR$|^Sending/ })
export const categoryRadio = (page: Page, label: string) => page.getByRole('radio', { name: label })
/** The sent or limit line (an `output`, so a status). */
export const sentLine = (page: Page) => page.locator('[data-slot="case-sent"]').getByRole('status')
export const casePanels = (page: Page) => page.locator('[data-slot="escalation-panel"]')

/** The queue's rows (HR). */
export const queueRows = (page: Page) => page.locator('[data-slot="case-queue-row"]')
/** The queue row of a person, by the name its accessible name starts with. */
export const queueRowOf = (page: Page, name: string) =>
  queueRows(page).filter({ has: page.getByText(name, { exact: true }) })
/** The detail's timeline entries. */
export const timelineRows = (page: Page) => page.locator('[data-slot="case-timeline"] li')
/** My cases' rows. */
export const myCaseRows = (page: Page) => page.locator('[data-slot="case-list"] > li')

/** The cases the signed-in person sent, as the API reports them. */
export function myCasesFromApi(page: Page) {
  return page.evaluate(async () => {
    const response = await fetch('/api/v1/cases/mine')
    return ((await response.json()) as { items: { id: string; status: string }[] }).items
  })
}

/** Chooses a category and types words into the open form (leaves the words as they are if null). */
export async function fillForm(page: Page, label: string, words: string | null) {
  await categoryRadio(page, label).click()
  if (words !== null) await wordsBox(page).fill(words)
}

/**
 * Sends a case straight to the API as the signed-in person (the session cookie, and the CSRF
 * header any write needs), for tests that need a case but are not about the form. Returns its ID.
 */
export async function sendCaseByApi(
  page: Page,
  words: string,
  category = 'other',
): Promise<string> {
  const result = await page.evaluate(
    async ({ words: text, category: chosen }) => {
      const token = document.cookie
        .split('; ')
        .find((part) => part.startsWith('__Host-od_csrf='))
        ?.slice('__Host-od_csrf='.length)
      const response = await fetch('/api/v1/cases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token ?? '' },
        body: JSON.stringify({
          submissionId: crypto.randomUUID(),
          category: chosen,
          text,
        }),
      })
      return { status: response.status, body: (await response.json()) as { case: { id: string } } }
    },
    { words, category },
  )
  expect(result.status, 'the case was sent').toBe(201)
  return result.body.case.id
}
