import { expect, test } from '../fixtures'
import type { Page } from '@playwright/test'
import { SENSITIVE_QUESTION, sentLine } from '../cases-helpers'
import { QUESTIONS, composerBox, focusPageStart } from '../conversation-helpers'
import { focusedName, startAs } from '../helpers'
import {
  factsOf,
  moveToDay,
  skipUnlessScriptedDayCounts,
  toast,
  workdays,
} from '../time-off-helpers'
import { step, tabTo } from './checks'

// The audit's keyboard walks (Phase 8, Stage 8): each main flow done with the keyboard alone (Tab,
// Shift+Tab, the arrow keys, Enter, Space, and Escape; no clicks). Every stop on the way is checked
// for a visible focus ring and for not being hidden behind the sticky header, the composer, or the
// coach mark (2.4.11); each step asserts where focus is. A stop that shows only in part is noted on
// the test as a "partly covered" annotation, a low finding. The walkthrough page joins in Stage 9.

test.use({ viewport: { width: 1280, height: 800 } })

/** "Answer finished": its "Was this right?" (or its thank-you) count grows by one. */
const FEEDBACK = '[data-slot="feedback"], [data-slot="feedback-thanks"]'

/** Types into the focused composer and sends with Enter, then waits for the saved answer. */
async function askByKeyboard(page: Page, question: string, { feedback = true } = {}) {
  const before = await page.locator(FEEDBACK).count()
  await expect(composerBox(page)).toBeFocused()
  await page.keyboard.type(question)
  await page.keyboard.press('Enter')
  if (feedback) await expect(page.locator(FEEDBACK)).toHaveCount(before + 1)
}

/** From the top of the page, Tab to the composer. */
async function toComposer(page: Page) {
  // Not before the conversation has loaded: until then the composer can't be typed in, so Tab
  // would pass it and reach the rail's links, which the loaded conversation then hides.
  await expect(composerBox(page)).toBeEditable()
  await focusPageStart(page)
  await tabTo(page, 'Ask Open Door')
}

/** Moves through an open menu with the Down arrow until focus is on a row matching `name`. */
async function arrowTo(page: Page, name: RegExp, limit = 10) {
  for (let i = 0; i < limit; i += 1) {
    const now = await focusedName(page)
    if (name.test(now)) return
    await page.keyboard.press('ArrowDown')
    // Wait for focus to move before reading it again.
    await expect.poll(() => focusedName(page)).not.toBe(now)
  }
  expect(await focusedName(page)).toMatch(name)
}

/** Switches persona from the sidebar's switcher by keyboard: Enter, arrows to the person, Enter. */
async function switchByKeyboard(page: Page, firstName: string) {
  await focusPageStart(page)
  await tabTo(page, /Switch persona$/)
  await page.keyboard.press('Enter')
  await arrowTo(page, new RegExp(`^${firstName} `))
  await page.keyboard.press('Enter')
  await expect(page.getByRole('button', { name: /Switch persona$/ })).toHaveAccessibleName(
    new RegExp(`^${firstName} .* Current persona\\. Switch persona$`),
  )
}

/** From the top of the page, Tab to a sidebar link and follow it. */
async function openByKeyboard(page: Page, name: string | RegExp, url: string | RegExp) {
  await focusPageStart(page)
  await tabTo(page, name)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(url)
}

test('start a sandbox from the landing page', async ({ page }) => {
  await page.goto('/')
  await focusPageStart(page)
  await tabTo(page, /^Priya /)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL('/ask')
  // Once the home has loaded (see toComposer), it is reachable from the top: the nav first, then
  // the composer.
  await expect(composerBox(page)).toBeEditable()
  await focusPageStart(page)
  await step(page, 'Tab', 'Ask')
  await tabTo(page, 'Ask Open Door')
})

test('ask, open a source, read it, and close it', async ({ page }) => {
  await startAs(page, 'Priya')
  await toComposer(page)
  await askByKeyboard(page, QUESTIONS.cited)
  const source = 'Source 1: Handbook §4.3, Time off'
  await focusPageStart(page)
  await tabTo(page, source)
  await page.keyboard.press('Enter')
  // Screen 07: focus moves to the panel's title, then Tab goes to Close, the passage, and "Open in
  // handbook".
  const panel = page.getByRole('complementary', { name: 'Handbook passage' })
  await expect(panel.getByRole('heading', { level: 2, name: 'Sick leave' })).toBeFocused()
  await step(page, 'Tab', 'Close passage')
  await step(page, 'Tab', 'Passage text')
  await step(page, 'Tab', /^Open in handbook/)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: source }).first()).toBeFocused()
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the source sheet keeps focus inside it until it closes', async ({ page }) => {
    await startAs(page, 'Priya')
    await toComposer(page)
    await askByKeyboard(page, QUESTIONS.cited)
    const source = 'Source 1: Handbook §4.3, Time off'
    await focusPageStart(page)
    await tabTo(page, source)
    await page.keyboard.press('Enter')
    const sheet = page.getByRole('dialog')
    await expect(sheet).toBeVisible()
    for (let i = 0; i < 6; i += 1) {
      await page.keyboard.press('Tab')
      expect(await sheet.evaluate((el) => el.contains(document.activeElement))).toBe(true)
    }
    await page.keyboard.press('Escape')
    await expect(sheet).toBeHidden()
    await expect(page.getByRole('button', { name: source }).first()).toBeFocused()
  })
})

test('book a day off in chat and confirm it', async ({ page }) => {
  await startAs(page, 'Priya')
  await skipUnlessScriptedDayCounts(test, page, 'book next friday')
  await toComposer(page)
  await askByKeyboard(page, 'book next friday')
  await focusPageStart(page)
  await tabTo(page, /^Confirm: /)
  await page.keyboard.press('Enter')
  const outcome = page.locator('[data-slot="confirm-card"] output')
  await expect(outcome).toContainText('Requested.')
  await expect(outcome).toBeFocused()
})

test('book a day off on the Time off page', async ({ page }) => {
  await startAs(page, 'Priya')
  await openByKeyboard(page, 'Time off', '/time-off')
  const [day] = workdays(await factsOf(page), 14, 1) as [string]
  await expect(page.getByRole('button', { name: 'Request time off' }).first()).toBeVisible()
  await tabTo(page, 'Request time off')
  await page.keyboard.press('Enter')
  const form = page.locator('#request-form')
  await expect(form.getByRole('heading', { name: 'Request time off' })).toBeFocused()
  await tabTo(page, /^Dates/)
  await page.keyboard.press('Enter')
  await tabTo(page, 'Next month')
  await page.keyboard.press('Tab')
  expect(await page.evaluate(() => document.activeElement?.getAttribute('data-day'))).toBeTruthy()
  await moveToDay(page, day)
  await page.keyboard.press('Enter')
  await tabTo(page, 'Done')
  await page.keyboard.press('Enter')
  await expect(form.getByRole('button', { name: /^Dates/ })).toBeFocused()
  // The form's own submit button has the same name as the page's. It waits for the day's check.
  await expect(form.getByRole('button', { name: 'Request time off' })).toBeEnabled()
  await tabTo(page, 'Request time off')
  await page.keyboard.press('Enter')
  await expect(toast(page)).toContainText('Requested.')
})

test('approve a request as the manager', async ({ page }) => {
  await startAs(page, 'Marcus')
  await openByKeyboard(page, /^Approvals/, '/approvals')
  await expect(page.getByRole('button', { name: /^Approve Zara Bautista’s PTO, / })).toBeVisible()
  await tabTo(page, /^Approve Zara Bautista’s PTO, /)
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('alertdialog')
  await expect(dialog.getByRole('button', { name: 'Go back' })).toBeFocused()
  await tabTo(page, 'Approve', { limit: 4 })
  await page.keyboard.press('Enter')
  await expect(toast(page)).toContainText('Approved.')
  await expect(dialog).toBeHidden()
  // Focus goes on somewhere useful, not to the page's start.
  expect(await focusedName(page)).not.toBe('')
})

test('send a case from the sensitive panel', async ({ page }) => {
  await startAs(page, 'Priya')
  await toComposer(page)
  await askByKeyboard(page, SENSITIVE_QUESTION)
  await focusPageStart(page)
  await tabTo(page, 'Open a confidential case')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: /confidential case/i }).last()).toBeFocused()
  // The category: Tab into the group, then the arrow keys choose.
  await tabTo(page, /Harassment or discrimination|Pay concern|Workplace safety|Something else/)
  await page.keyboard.press('Space')
  await tabTo(page, 'Send to HR')
  await page.keyboard.press('Enter')
  await expect(sentLine(page)).toContainText('Sent to HR.')
  await expect(sentLine(page)).toBeFocused()
})

test('review a case as HR', async ({ page }) => {
  await startAs(page, 'Dana')
  await openByKeyboard(page, /^Cases/, '/cases')
  await expect(page.locator('[data-slot="case-queue-row"]').first()).toBeVisible()
  await tabTo(page, /Chloe Foster|Keisha Zhang|Aaliyah Edwards/)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/cases\/.+/)
  await expect(page.getByRole('button', { name: /^Show .+ words$/ })).toBeVisible()
  await tabTo(page, /^Show .+ words$/)
  await page.keyboard.press('Enter')
  await expect(page.getByRole('button', { name: /^Hide .+ words$/ })).toBeFocused()
  await tabTo(page, /^(Start review|Close case)$/)
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('alertdialog')
  await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect.poll(() => focusedName(page)).toMatch(/^(Start review|Close case)$/)
})

test('open a turn in the console', async ({ page }) => {
  await startAs(page, 'Priya')
  await toComposer(page)
  await askByKeyboard(page, QUESTIONS.cited)
  await switchByKeyboard(page, 'Dana')
  await openByKeyboard(page, 'Console', '/console')
  const row = /^\d{1,2}:\d{2}\s?[AP]M\s?,\s?Employee,\s?Oakland, CA/
  await expect(page.getByRole('button', { name: row })).toBeVisible()
  await tabTo(page, row, { limit: 60 })
  await page.keyboard.press('Enter')
  await expect(page.locator('[data-slot="trace-panel"]')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('[data-slot="trace-panel"]')).toBeHidden()
  await expect.poll(() => focusedName(page)).toMatch(row)
})

test('the tour: start, a step across personas, leave, and resume', async ({ page }) => {
  test.setTimeout(120_000)
  await page.goto('/')
  await focusPageStart(page)
  await tabTo(page, 'Take the 2-minute tour')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL('/ask')
  const card = page.locator('[data-slot="coach-mark"]')
  await expect(card.getByRole('heading', { level: 2 })).toBeFocused()
  // Step 1: send its chip, then Next.
  await tabTo(page, /^How many sick days do I get\?/, { limit: 6 })
  await page.keyboard.press('Enter')
  await expect(card.getByRole('button', { name: 'Next', exact: true })).toBeVisible()
  await tabTo(page, 'Next', { limit: 8 })
  await page.keyboard.press('Enter')
  // Step 2 is Mateo's: the tour switches persona and focus is on the new step's title.
  await expect(card.getByText('Step 2 of 10', { exact: true })).toBeVisible()
  await expect(card.getByRole('heading', { level: 2 })).toBeFocused()
  // Leave with Escape; the coach mark goes, and the persona menu offers to resume.
  await page.keyboard.press('Escape')
  await expect(card).toHaveCount(0)
  await focusPageStart(page)
  await tabTo(page, /Switch persona$/)
  await page.keyboard.press('Enter')
  await arrowTo(page, /^Resume/)
  await page.keyboard.press('Enter')
  await expect(card.getByText('Step 2 of 10', { exact: true })).toBeVisible()
  const title = card.getByRole('heading', { level: 2 })
  await expect(title).toBeFocused()
  // And it stays there: the closing menu must not take it back to the switcher a moment later.
  await page.waitForTimeout(250)
  expect(await title.evaluate((el) => el === document.activeElement)).toBe(true)
})
