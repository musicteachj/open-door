import { expect, test, type Page } from '@playwright/test'
import { askAndWaitForAnswer } from './conversation-helpers'
import {
  CRISIS_FACT,
  CRISIS_WORDS,
  HARASSMENT,
  SENSITIVE_QUESTION,
  casePanels,
  categoryRadio,
  fillForm,
  formHeading,
  myCaseRows,
  myCasesFromApi,
  openCaseButton,
  queueRowOf,
  queueRows,
  sendButton,
  sendCaseByApi,
  sentLine,
  timelineRows,
  wordsBox,
} from './cases-helpers'
import { auditEventsBy, myId } from './directory-helpers'
import { MODAL_OVERLAY_RULES, startAs } from './helpers'
import { nav, scrollsSideways, settledScan, switchPersona } from './time-off-helpers'

// Screens 11 and 12 in the real app: a sensitive message becomes a confidential case the person
// sends, it lands in HR's queue, and HR's reads are audited with the person's words hidden until
// revealed. The components are proved state by state in gallery-cases.spec.ts and their unit
// tests. These tests prove what only the pages and the API add. The scripted model screens and
// summarizes each case (words with "hurt myself" screen as crisis), so nothing costs a cent. A
// sandbox seeds four cases (Keisha new, Chloe new, Aaliyah in review, Lucia closed), and no
// persona has a case of their own to start.

// The conversation's sticky composer can cover the "Show your work" toggle under a panel in a short
// window, which axe reads as a small target. That belongs to the conversation page, so the scans
// of the chat states look at the panel itself.
const PANEL = ['[data-slot="escalation-panel"]']
const dialog = (page: Page) => page.getByRole('alertdialog')
const casesLink = (page: Page, news: number) =>
  nav(page).getByRole('link', { name: news === 0 ? 'Cases' : `Cases, ${news} new`, exact: true })
const myCasesLink = (page: Page) => nav(page).getByRole('link', { name: 'My cases', exact: true })
const notFound = (page: Page) => page.getByRole('heading', { name: "We couldn't find that page." })
const showWords = (page: Page) => page.getByRole('button', { name: 'Show Priya’s words' })
const hideWords = (page: Page) => page.getByRole('button', { name: 'Hide Priya’s words' })
const startReview = (page: Page) => page.getByRole('button', { name: 'Start review' })
const closeCase = (page: Page) => page.getByRole('button', { name: 'Close case' })

const auditCount = (actorId: string, action: string) =>
  auditEventsBy(actorId).filter((event) => event.action === action).length

/** Priya's message, answered: the saved turn with the sensitive panel. */
async function askSensitive(page: Page) {
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Ask' }).click()
  await askAndWaitForAnswer(page, SENSITIVE_QUESTION)
  await expect(casePanels(page)).toHaveCount(1)
}

test.describe('the demo, from the panel and from My cases, at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })
  test.describe.configure({ mode: 'serial' })

  let page: Page
  let priyaCaseId: string

  test.beforeAll(async ({ browser }) => {
    page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage()
  })
  test.afterAll(async () => {
    await page.context().close()
  })

  test('Priya opens a case from the panel: prefilled form, validation order, the sent line', async () => {
    test.setTimeout(120_000)
    await startAs(page, 'Priya')
    // No persona has a case at the start, and My cases says so.
    await expect(myCasesLink(page)).toBeVisible()
    await askAndWaitForAnswer(page, SENSITIVE_QUESTION)
    await expect(casePanels(page)).toHaveCount(1)
    await expect(openCaseButton(page)).toBeVisible()
    expect.soft((await settledScan(page, [], PANEL)).violations).toEqual([])

    await openCaseButton(page).click()
    // The form opens prefilled with the turn's own question, verbatim, and focus is on its heading.
    await expect(formHeading(page)).toBeFocused()
    await expect(wordsBox(page)).toHaveValue(SENSITIVE_QUESTION)
    await expect(page.getByText('46 of 4,000 characters')).toBeVisible()
    expect.soft((await settledScan(page)).violations).toEqual([])

    // Validation runs in order: no category, then empty words, then a card number.
    await sendButton(page).click()
    await expect(
      page.getByRole('alert').filter({ hasText: 'Choose what this is about.' }),
    ).toBeVisible()
    await expect(categoryRadio(page, HARASSMENT)).toBeFocused()
    await categoryRadio(page, HARASSMENT).click()
    await wordsBox(page).fill('')
    await sendButton(page).click()
    await expect(
      page.getByRole('alert').filter({ hasText: 'Add your words before sending.' }),
    ).toBeVisible()
    await expect(wordsBox(page)).toHaveAttribute('aria-invalid', 'true')
    await expect(wordsBox(page)).toBeFocused()
    await wordsBox(page).fill('My employee number is 123-45-6789.')
    await sendButton(page).click()
    await expect(
      page
        .getByRole('alert')
        .filter({ hasText: 'That looks like a Social Security or card number.' }),
    ).toBeVisible()
    expect.soft((await settledScan(page, [], PANEL)).violations).toEqual([])
    await wordsBox(page).fill(SENSITIVE_QUESTION)

    // A double click on Send makes one case.
    await sendButton(page).dblclick()
    const sent = sentLine(page)
    await expect(sent).toContainText('Sent to HR. HR replies by')
    await expect(sent).toContainText('You can see its status in My cases.')
    await expect(sent).toBeFocused()
    await expect(
      page.locator('[data-slot="case-sent"]').getByRole('link', { name: 'View in My cases' }),
    ).toBeVisible()
    await expect(openCaseButton(page)).toHaveCount(0)
    expect(await myCasesFromApi(page)).toHaveLength(1)
    priyaCaseId = (await myCasesFromApi(page))[0]!.id
    expect.soft((await settledScan(page, [], PANEL)).violations).toEqual([])
  })

  test('a reload and a second tab show the sent case, with no button', async () => {
    await page.reload()
    await expect(sentLine(page)).toContainText('Sent to HR. HR replies by')
    await expect(openCaseButton(page)).toHaveCount(0)

    const second = await page.context().newPage()
    await second.goto('/ask')
    await expect(sentLine(second)).toContainText('Sent to HR. HR replies by')
    await expect(openCaseButton(second)).toHaveCount(0)
    await second.close()
    expect(await myCasesFromApi(page)).toHaveLength(1)
  })

  test('Dana sees the case in the queue and opens it: summary shown, words hidden, actions locked', async () => {
    test.setTimeout(120_000)
    await switchPersona(page, 'Dana')
    // Priya's case, and the seed's Keisha and Chloe.
    await expect(casesLink(page, 3)).toBeVisible()
    // HR gets no way to My cases.
    await expect(myCasesLink(page)).toHaveCount(0)
    await casesLink(page, 3).click()
    await expect(page).toHaveURL('/cases')
    await expect(queueRows(page)).toHaveCount(4)
    // The queue shows facts only, never any of the words.
    await expect(queueRowOf(page, 'Priya Raman')).toContainText('Harassment or discrimination')
    await expect(page.getByText(SENSITIVE_QUESTION)).toHaveCount(0)
    expect.soft((await settledScan(page)).violations).toEqual([])

    await queueRowOf(page, 'Priya Raman').click()
    await expect(page).toHaveURL(`/cases/${priyaCaseId}`)
    await expect(page.getByRole('heading', { level: 1, name: HARASSMENT })).toBeVisible()
    await expect(page.locator('[data-slot="case-summary"]')).toContainText('The person wrote about')
    // The words stay hidden, and the actions are aria-disabled but focusable, with the reason.
    await expect(showWords(page)).toHaveAttribute('aria-expanded', 'false')
    await expect(page.getByText(SENSITIVE_QUESTION)).toHaveCount(0)
    for (const button of [startReview(page), closeCase(page)]) {
      await expect(button).toHaveAttribute('aria-disabled', 'true')
      await button.focus()
      await expect(button).toBeFocused()
      await expect(button).toHaveAccessibleDescription(
        'Read Priya’s words before changing the status.',
      )
    }
    expect.soft((await settledScan(page)).violations).toEqual([])
  })

  test('Dana shows the words: one timeline row, one audit event, and a window refocus adds none', async () => {
    test.setTimeout(120_000)
    const danaId = await myId(page)
    const rowsBefore = await timelineRows(page).count()
    const readsBefore = auditCount(danaId, 'case.text.read')
    expect(readsBefore).toBe(0)

    await showWords(page).click()
    await expect(page.getByText(SENSITIVE_QUESTION)).toBeVisible()
    await expect(hideWords(page)).toBeFocused()
    await expect(timelineRows(page)).toHaveCount(rowsBefore + 1)
    await expect(timelineRows(page).last()).toContainText('Dana Whitfield read Priya’s words')
    expect(auditCount(danaId, 'case.text.read')).toBe(1)
    // The actions unlock.
    await expect(startReview(page)).not.toHaveAttribute('aria-disabled', 'true')
    expect.soft((await settledScan(page)).violations).toEqual([])

    // A refocus of the window refetches what the page may refetch, and reads nothing again.
    await page.evaluate(() => {
      window.dispatchEvent(new Event('blur'))
      window.dispatchEvent(new Event('focus'))
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await page.waitForTimeout(800)
    await expect(timelineRows(page)).toHaveCount(rowsBefore + 1)
    expect(auditCount(danaId, 'case.text.read')).toBe(1)
    await expect(page.getByText(SENSITIVE_QUESTION)).toBeVisible()

    // Hiding adds no row and no event.
    await hideWords(page).click()
    await expect(showWords(page)).toBeVisible()
    await expect(page.getByText(SENSITIVE_QUESTION)).toHaveCount(0)
    await expect(timelineRows(page)).toHaveCount(rowsBefore + 1)
    expect(auditCount(danaId, 'case.text.read')).toBe(1)
  })

  test('Dana starts the review and closes the case, and Priya sees each step', async () => {
    test.setTimeout(150_000)
    // Start review: an alert dialog that starts on Cancel, closes on Escape, returns focus.
    await startReview(page).click()
    await expect(dialog(page)).toBeVisible()
    await expect(dialog(page).getByRole('button', { name: 'Cancel' })).toBeFocused()
    expect.soft((await settledScan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])
    await page.keyboard.press('Escape')
    await expect(dialog(page)).toHaveCount(0)
    await expect(startReview(page)).toBeFocused()

    const rows = await timelineRows(page).count()
    await startReview(page).click()
    await dialog(page).getByRole('button', { name: 'Start review' }).click()
    await expect(dialog(page)).toHaveCount(0)
    await expect(page.locator('[data-slot="case-detail-header"]')).toContainText('In review')
    await expect(page.locator('[data-slot="case-dates"]')).toContainText('In review since')
    await expect(timelineRows(page)).toHaveCount(rows + 1)
    await expect(timelineRows(page).last()).toContainText('Dana Whitfield started the review')
    await expect(closeCase(page)).toBeFocused()
    await expect(startReview(page)).toHaveCount(0)

    // Priya's My cases follows.
    await switchPersona(page, 'Priya')
    await myCasesLink(page).click()
    await expect(page).toHaveURL('/my-cases')
    await expect(myCaseRows(page)).toHaveCount(1)
    await expect(myCaseRows(page).first()).toContainText('HR is reviewing')
    // No words and no link into a case.
    await expect(page.getByText(SENSITIVE_QUESTION)).toHaveCount(0)
    await expect(myCaseRows(page).first().getByRole('link')).toHaveCount(0)

    // Dana closes it. The words were read on an earlier view, so the action is open at once.
    await switchPersona(page, 'Dana')
    await page.goto(`/cases/${priyaCaseId}`)
    await expect(hideWords(page)).toHaveCount(0)
    await expect(showWords(page)).toBeVisible()
    await expect(closeCase(page)).not.toHaveAttribute('aria-disabled', 'true')
    await closeCase(page).click()
    await expect(dialog(page).getByRole('button', { name: 'Cancel' })).toBeFocused()
    expect.soft((await settledScan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])
    await dialog(page).getByRole('button', { name: 'Close case' }).click()
    await expect(dialog(page)).toHaveCount(0)
    await expect(page.locator('[data-slot="case-detail-header"]')).toContainText('Closed')
    await expect(page.getByText('This case is closed.')).toBeVisible()
    await expect(page.getByRole('heading', { level: 1, name: HARASSMENT })).toBeFocused()
    await expect(timelineRows(page).last()).toContainText('Dana Whitfield closed the case')
    expect.soft((await settledScan(page)).violations).toEqual([])

    await switchPersona(page, 'Priya')
    await myCasesLink(page).click()
    await expect(myCaseRows(page).first()).toContainText('HR has finished its review')
  })
})

test.describe('My cases, at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('Priya opens a case from the empty list: the new row first, the sent line without a link', async ({
    page,
  }) => {
    test.setTimeout(120_000)
    await startAs(page, 'Priya')
    await myCasesLink(page).click()
    await expect(page).toHaveURL('/my-cases')
    await expect(page.getByText('You haven’t sent HR a case.')).toBeVisible()
    expect.soft((await settledScan(page)).violations).toEqual([])

    await openCaseButton(page).click()
    await expect(formHeading(page)).toBeFocused()
    // On My cases the words start empty.
    await expect(wordsBox(page)).toHaveValue('')
    await expect(page.getByText('0 of 4,000 characters')).toBeVisible()
    expect.soft((await settledScan(page)).violations).toEqual([])
    await fillForm(page, 'Pay concern', 'My last two paychecks were short.')
    await sendButton(page).click()

    await expect(sentLine(page)).toContainText('Sent to HR. HR replies by')
    await expect(sentLine(page)).toBeFocused()
    // The link would point at this page, so there is none.
    await expect(page.locator('[data-slot="case-sent"]').getByRole('link')).toHaveCount(0)
    await expect(myCaseRows(page)).toHaveCount(1)
    await expect(myCaseRows(page).first()).toContainText('Pay concern')
    await expect(myCaseRows(page).first()).toContainText('Sent to HR')
    expect.soft((await settledScan(page)).violations).toEqual([])

    // A second case goes to the top. The sent line holds the top of the page until a reload.
    await page.reload()
    await openCaseButton(page).click()
    await fillForm(page, 'Workplace safety', 'The loading dock door sticks.')
    await sendButton(page).click()
    await expect(myCaseRows(page)).toHaveCount(2)
    await expect(myCaseRows(page).first()).toContainText('Workplace safety')
  })

  test('crisis words show the crisis text right after the sent line, and HR sees the crisis state', async ({
    page,
  }) => {
    test.setTimeout(150_000)
    await startAs(page, 'Priya')
    await myCasesLink(page).click()
    await openCaseButton(page).click()
    await fillForm(page, 'Something else, or not sure', CRISIS_WORDS)
    await sendButton(page).click()
    await expect(sentLine(page)).toContainText('Sent to HR.')
    const crisis = page.locator('[data-slot="case-sent"] + [data-slot="escalation-panel"]')
    await expect(crisis).toBeVisible()
    await expect(crisis).toContainText('988')
    expect.soft((await settledScan(page)).violations).toEqual([])

    await switchPersona(page, 'Dana')
    await casesLink(page, 3).click()
    const row = queueRowOf(page, 'Priya Raman')
    await expect(row).toContainText(CRISIS_FACT)
    await row.click()
    await expect(page.getByText(CRISIS_FACT).first()).toBeVisible()
    await expect(page.locator('[data-slot="case-summary"]')).toContainText(
      'No AI summary for this case. The safety check routed it to crisis text.',
    )
    await expect(timelineRows(page).filter({ hasText: 'Sent by Priya Raman' })).toHaveCount(1)
    await expect(
      timelineRows(page).filter({ hasText: 'The safety check routed it to crisis text' }),
    ).toHaveCount(1)
    await expect(page.getByText('AI summary couldn’t be written')).toHaveCount(0)
    expect.soft((await settledScan(page)).violations).toEqual([])
  })

  test('five waiting cases replace the button with the limit line, on My cases and in chat', async ({
    page,
  }) => {
    test.setTimeout(150_000)
    await startAs(page, 'Priya')
    for (let i = 1; i <= 5; i += 1) await sendCaseByApi(page, `Concern number ${i}.`)
    await myCasesLink(page).click()
    await expect(myCaseRows(page)).toHaveCount(5)
    const limit = page.locator('[data-slot="case-sent"]')
    await expect(limit).toContainText(
      'You have 5 cases waiting for HR. To add to one, contact the HR team directly.',
    )
    await expect(openCaseButton(page)).toHaveCount(0)
    expect.soft((await settledScan(page)).violations).toEqual([])

    await askSensitive(page)
    await expect(page.locator('[data-slot="case-sent"]')).toContainText('You have 5 cases waiting')
    await expect(page.getByRole('link', { name: 'View your cases' })).toBeVisible()
    await expect(openCaseButton(page)).toHaveCount(0)
    expect.soft((await settledScan(page, [], PANEL)).violations).toEqual([])
  })
})

test.describe('who can see what, at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('Marcus sees nothing of anyone’s cases', async ({ page }) => {
    test.setTimeout(120_000)
    await startAs(page, 'Priya')
    const caseId = await sendCaseByApi(page, 'A private concern.')
    await switchPersona(page, 'Marcus')
    await expect(nav(page).getByRole('link', { name: /^Cases/ })).toHaveCount(0)
    await page.goto('/cases')
    await expect(notFound(page)).toBeVisible()
    await page.goto(`/cases/${caseId}`)
    await expect(notFound(page)).toBeVisible()
    await page.goto('/my-cases')
    await expect(page.getByText('You haven’t sent HR a case.')).toBeVisible()
    expect(await myCasesFromApi(page)).toHaveLength(0)
    await expect(page.getByText('Priya')).toHaveCount(0)
  })

  test('HR has no My cases and gets no link to it; its own case is read-only', async ({ page }) => {
    test.setTimeout(150_000)
    await startAs(page, 'Dana')
    await expect(myCasesLink(page)).toHaveCount(0)
    await page.goto('/my-cases')
    await expect(notFound(page)).toBeVisible()
    await page.goto('/ask')

    await askAndWaitForAnswer(page, SENSITIVE_QUESTION)
    await openCaseButton(page).click()
    await fillForm(page, 'Pay concern', 'My own pay concern.')
    await sendButton(page).click()
    await expect(sentLine(page)).toContainText('Sent to HR. HR replies by')
    // No link at all on the sent line, and no way to My cases anywhere in the panel.
    await expect(page.locator('[data-slot="case-sent"]').getByRole('link')).toHaveCount(0)
    await expect(
      page.getByRole('link', { name: /My cases|Write to HR|View your cases/ }),
    ).toHaveCount(0)

    // Her case is in her queue, read-only: the header and one line, nothing to act on or read.
    await casesLink(page, 2).click()
    const own = queueRows(page).filter({ has: page.locator('xpath=self::*[@data-own]') })
    await expect(own).toHaveCount(1)
    await own.click()
    await expect(page.getByRole('heading', { level: 1, name: 'Pay concern' })).toBeVisible()
    await expect(
      page.getByText('You opened this case, so you can’t act on it or read it here.'),
    ).toBeVisible()
    await expect(page.getByRole('button', { name: /^Show / })).toHaveCount(0)
    await expect(startReview(page)).toHaveCount(0)
    await expect(closeCase(page)).toHaveCount(0)
    await expect(page.locator('[data-slot="case-summary"]')).toHaveCount(0)
    await expect(page.locator('[data-slot="case-timeline"]')).toHaveCount(0)
    expect.soft((await settledScan(page)).violations).toEqual([])
    // Nothing of hers was read: no audited read of her own case.
    const danaId = await myId(page)
    expect(auditCount(danaId, 'case.text.read')).toBe(0)
  })
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the chat form, My cases, the queue, and the detail fit and pass axe', async ({ page }) => {
    test.setTimeout(180_000)
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, SENSITIVE_QUESTION)
    await openCaseButton(page).click()
    await expect(formHeading(page)).toBeFocused()
    expect(await scrollsSideways(page)).toBe(false)
    expect.soft((await settledScan(page, [], PANEL)).violations).toEqual([])
    await fillForm(page, HARASSMENT, null)
    await sendButton(page).click()
    await expect(sentLine(page)).toBeVisible()
    expect(await scrollsSideways(page)).toBe(false)

    // My cases: empty states are covered at 1440; here, a list, the form, and the limit.
    await page.goto('/my-cases')
    await expect(myCaseRows(page)).toHaveCount(1)
    expect(await scrollsSideways(page)).toBe(false)
    expect.soft((await settledScan(page)).violations).toEqual([])
    await openCaseButton(page).click()
    await expect(formHeading(page)).toBeFocused()
    expect(await scrollsSideways(page)).toBe(false)
    expect.soft((await settledScan(page)).violations).toEqual([])
  })

  test('HR’s queue and a case detail fit and pass axe', async ({ page }) => {
    test.setTimeout(150_000)
    await startAs(page, 'Dana')
    await page.goto('/cases')
    // The seed's Keisha, Chloe, and Aaliyah are open.
    await expect(queueRows(page)).toHaveCount(3)
    expect(await scrollsSideways(page)).toBe(false)
    expect.soft((await settledScan(page)).violations).toEqual([])
    await queueRowOf(page, 'Keisha Zhang').click()
    await expect(page.locator('[data-slot="case-summary"]')).toBeVisible()
    expect(await scrollsSideways(page)).toBe(false)
    await page.getByRole('button', { name: /^Show .+ words$/ }).click()
    await expect(page.getByRole('button', { name: /^Hide .+ words$/ })).toBeVisible()
    expect(await scrollsSideways(page)).toBe(false)
    expect.soft((await settledScan(page)).violations).toEqual([])
    await startReview(page).click()
    await expect(dialog(page)).toBeVisible()
    expect(await scrollsSideways(page)).toBe(false)
    expect.soft((await settledScan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])
  })
})
