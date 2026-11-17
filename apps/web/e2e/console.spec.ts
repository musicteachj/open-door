import { expect, test } from './fixtures'
import type { Page } from '@playwright/test'
import { SENSITIVE_QUESTION } from './cases-helpers'
import { askAndWaitForAnswer, QUESTIONS } from './conversation-helpers'
import { scan, startAs } from './helpers'
import { nav, scrollsSideways, settledScan, switchPersona } from './time-off-helpers'

// Screen 13 (the AI Ops console) in the real app. The parts are proved state by state in
// gallery-console.spec.ts and their unit tests. These tests prove what only the page and the API
// add: only HR gets the page, a person's turns appear as an anonymous row, a sensitive turn is a
// redacted row after the timed ones, nothing on the page carries the person or their words, and
// opening a row asks the server for nothing. The scripted model answers, so nothing costs a cent.

const notFound = (page: Page) => page.getByRole('heading', { name: "We couldn't find that page." })
const consoleLink = (page: Page) => nav(page).getByRole('link', { name: 'Console', exact: true })
// A timed row's button is named "9:31 AM, Employee, Oakland, CA, Answered" (the time first, then
// the asker's role and the location). Chromium puts a space before hidden text, hence `\s?`.
const timedRows = (page: Page) =>
  page.getByRole('button', { name: /^\d{1,2}:\d{2}\s?[AP]M\s?,\s?Employee,\s?Oakland, CA/ })
const REDACTED = 'Flagged by the safety check. Details are hidden to protect the person.'

test.describe('who can open the console', () => {
  for (const name of ['Priya', 'Marcus'] as const) {
    test(`${name} has no Console item, and /console is the not found page`, async ({ page }) => {
      await startAs(page, name)
      await expect(consoleLink(page)).toHaveCount(0)
      await page.goto('/console')
      await expect(notFound(page)).toBeVisible()
      await expect(page.getByRole('heading', { name: 'AI Ops console' })).toHaveCount(0)
    })
  }
})

test.describe('at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('Dana sees anonymous rows for Priya’s turns, and opening one asks for nothing', async ({
    page,
  }) => {
    test.setTimeout(120_000)
    await startAs(page, 'Priya')
    // An ordinary question, then the sensitive one, in the same sandbox.
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await askAndWaitForAnswer(page, SENSITIVE_QUESTION)
    await switchPersona(page, 'Dana')

    await consoleLink(page).click()
    await expect(page).toHaveURL('/console')
    await expect(page.getByRole('heading', { level: 1, name: 'AI Ops console' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: 'Eval scoreboard' })).toBeVisible()

    // One timed row, named by role and place, and one redacted row after it.
    await expect(timedRows(page)).toHaveCount(1)
    const redacted = page.getByText(REDACTED)
    await expect(redacted).toBeVisible()
    const timedBox = (await timedRows(page).boundingBox())!
    const redactedBox = (await redacted.boundingBox())!
    expect(redactedBox.y).toBeGreaterThan(timedBox.y)
    // The redacted row is plain text: no button, not focusable.
    await expect(page.getByRole('button', { name: new RegExp(REDACTED) })).toHaveCount(0)

    // Nothing on the page carries the person or their words. The page's own content is read
    // (`main`): the persona switcher legitimately shows Dana's name, and its open menu lists all
    // four personas, Priya included.
    const read = () => page.locator('main').innerText()
    for (const text of [await read()]) {
      expect(text).not.toMatch(/priya/i)
      expect(text.toLowerCase()).not.toContain(QUESTIONS.cited.toLowerCase())
      expect(text.toLowerCase()).not.toContain(SENSITIVE_QUESTION.toLowerCase())
      expect(text).not.toMatch(/\bcomments\b/i)
    }
    await expect(page.locator('main a[href^="http"]')).toHaveCount(0)

    // Opening the row shows the trace and asks the server for nothing.
    const requests: string[] = []
    page.on('request', (request) => {
      if (request.url().includes('/api/v1/console')) requests.push(request.url())
    })
    await timedRows(page).click()
    await expect(page.locator('[data-slot="trace-panel"]')).toBeVisible()
    await expect(page.getByText('Turn trace')).toBeVisible()
    // The trace is flush against the sheet's right edge and 420 px wide, not inside the padding.
    const panelBox = (await page.locator('[data-slot="trace-panel"]').boundingBox())!
    const sheetBox = (await page.locator('[data-slot="shell-sheet"]').boundingBox())!
    expect(panelBox.width).toBeCloseTo(420, 0)
    expect(panelBox.x + panelBox.width).toBeGreaterThanOrEqual(sheetBox.x + sheetBox.width - 2)
    expect(requests).toEqual([])
    const traced = await page.locator('main').innerText()
    expect(traced).not.toMatch(/priya/i)
    expect(traced.toLowerCase()).not.toContain(QUESTIONS.cited.toLowerCase())

    expect((await settledScan(page)).violations).toEqual([])
  })

  test('the empty sandbox says so, and "Ask a question" goes to /ask', async ({ page }) => {
    await startAs(page, 'Dana')
    await consoleLink(page).click()
    await expect(
      page.getByText('No questions yet in this sandbox. Ask something, or take the tour.'),
    ).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: 'Eval scoreboard' })).toBeVisible()
    expect((await scan(page)).violations).toEqual([])
    await page.getByRole('button', { name: 'Ask a question' }).click()
    await expect(page).toHaveURL('/ask')
  })
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the page does not scroll sideways, and axe is clean with a row and its sheet', async ({
    page,
  }) => {
    test.setTimeout(120_000)
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await askAndWaitForAnswer(page, SENSITIVE_QUESTION)
    await switchPersona(page, 'Dana')
    await page.goto('/console')
    await expect(timedRows(page)).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 2, name: 'Eval scoreboard' })).toBeVisible()
    expect(await scrollsSideways(page)).toBe(false)
    expect((await settledScan(page)).violations).toEqual([])

    await timedRows(page).click()
    await expect(page.locator('[data-slot="trace-panel"]')).toBeVisible()
    expect(await scrollsSideways(page)).toBe(false)
  })
})
