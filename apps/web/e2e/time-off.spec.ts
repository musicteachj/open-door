import { expect, test, type Page } from '@playwright/test'
import { MODAL_OVERLAY_RULES, startAs } from './helpers'
import {
  factsOf,
  hoursIn,
  longDay,
  pickDays,
  rowsOn,
  scrollsSideways,
  settledScan,
  toast,
  daysPastBalance,
  workdays,
} from './time-off-helpers'

// Screen 08 (Time off) in the real app. The states and components are proved one by one in
// gallery-timeoff.spec.ts (the radio groups, every picker key, the dialog's box and scrim, the
// bottom sheet's geometry). These tests prove what only the page adds: the figures and rows come
// from the API, a check runs on each change, a send reaches the server, focus lands where the
// notes say after each write, and the page follows the write. Several states share one page load.

const requestButton = (page: Page) => page.getByRole('button', { name: 'Request time off' }).first()
const form = (page: Page) => page.locator('#request-form')
const sheet = (page: Page) => page.getByRole('dialog', { name: 'Request time off' })
const dialog = (page: Page) => page.getByRole('alertdialog')
const myRequests = (page: Page) => page.getByRole('heading', { level: 2, name: 'My requests' })
const card = (page: Page, name: RegExp) =>
  page.locator('[data-slot="balance-card"]').filter({ has: page.getByRole('heading', { name }) })
/** The ledger rows of a balance card as hours, by their label, read off the page. */
async function ledger(page: Page, name: RegExp): Promise<Record<string, number>> {
  const rows = await card(page, name).locator('dl > div').allInnerTexts()
  return Object.fromEntries(
    rows.map((row) => {
      const [label, value] = row
        .split('\n')
        .map((part) => part.trim())
        .filter(Boolean) as [string, string]
      return [label, hoursIn(value)]
    }),
  )
}

/** Each card's ledger adds up to its figure: PTO and sick time, as the design's notes say. */
async function expectLedgersAdd(page: Page) {
  const pto = await ledger(page, /^PTO available$/)
  const figure = async (name: RegExp) =>
    hoursIn(await card(page, name).locator('[data-slot="balance-figure"]').innerText())
  expect
    .soft(await figure(/^PTO available$/))
    .toBe(pto['Earned to date']! - pto['Taken']! - pto['Booked']! - pto['Waiting for approval']!)
  const sick = await ledger(page, /^Sick leave available this year$/)
  expect
    .soft(await figure(/^Sick leave available this year$/))
    .toBe(sick['Granted on January 1']! - sick['Used']! - sick['Booked']!)
}

async function openTimeOff(page: Page) {
  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'Time off' })
    .click()
  await expect(page).toHaveURL('/time-off')
  await expect(page.getByRole('heading', { level: 1, name: 'Time off' })).toBeVisible()
  await expect(requestButton(page)).toBeVisible()
}

test.describe('at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('the page shows the API figures, a request goes through the form and back out through the cancel dialog, with focus where the notes say', async ({
    page,
  }) => {
    test.setTimeout(90_000)
    await startAs(page, 'Priya')
    await openTimeOff(page)
    const facts = await factsOf(page)
    const [day] = workdays(facts, 14, 1) as [string]

    // The balance cards and the schedule line are the API's labels and nothing else.
    const balances = await page.evaluate(async () => {
      const response = await fetch('/api/v1/time-off/balances')
      return (await response.json()) as {
        pto: { availableLabel: string }
        sick: { availableLabel: string }[]
      }
    })
    const hours = (label: string) => label.replace(/ \(.*\)$/, '')
    await expect
      .soft(card(page, /^PTO available$/).locator('[data-slot="balance-figure"]'))
      .toContainText(hours(balances.pto.availableLabel))
    await expect
      .soft(card(page, /^Sick leave available this year$/).locator('[data-slot="balance-figure"]'))
      .toContainText(hours(balances.sick[0]!.availableLabel))
    await expect
      .soft(page.getByText('Your schedule: Monday to Friday, 8 hours a day'))
      .toBeVisible()
    await expect.soft(page.getByRole('link', { name: 'Handbook §3.1' })).toBeVisible()
    // My requests lists the seed's history as Past, and nothing is upcoming.
    await expect.soft(page.getByText('No upcoming time off.')).toBeVisible()
    await expect.soft(page.locator('[data-slot="request-row"]').first()).toContainText('Approved')
    await expect.soft(page.getByRole('button', { name: /^Cancel PTO on / })).toHaveCount(0)
    await expectLedgersAdd(page)
    expect.soft((await settledScan(page)).violations).toEqual([])

    // The form opens beside the page with focus on its title, and the button says so.
    await expect(requestButton(page)).toHaveAttribute('aria-expanded', 'false')
    await requestButton(page).click()
    await expect(requestButton(page)).toHaveAttribute('aria-expanded', 'true')
    await expect(requestButton(page)).toHaveAttribute('aria-controls', 'request-form')
    await expect(form(page).getByRole('heading', { name: 'Request time off' })).toBeFocused()
    await expect(form(page).getByText('Pick dates to see what this uses.')).toBeVisible()

    // A day picked by keyboard is checked by the API: the preview lists it and what is left.
    await pickDays(page, form(page), day)
    const preview = form(page).getByRole('region', { name: 'What this uses' })
    await expect(preview).toContainText(longDay(day))
    await expect(preview).toContainText('8 hours (1 day)')
    await expect(preview).toContainText('left after this')
    await expect(preview.getByRole('link', { name: /Handbook §4\.1/ })).toBeVisible()
    await expect(
      form(page).getByText('Marcus Bell, your manager, reviews PTO requests.'),
    ).toBeVisible()
    expect.soft((await settledScan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])

    // Submit sends it. The toast is announced, focus returns to the button, the form is gone.
    await form(page).getByRole('button', { name: 'Request time off' }).click()
    await expect(toast(page)).toHaveText('Requested. Marcus Bell will review it.')
    await expect(form(page)).toHaveCount(0)
    await expect(requestButton(page)).toBeFocused()
    await expect(requestButton(page)).toHaveAttribute('aria-expanded', 'false')
    const row = rowsOn(page, longDay(day))
    await expect(row).toHaveCount(1)
    await expect(row).toContainText('Waiting for approval')
    await expect(row).toContainText('PTO · 8 hours (1 day)')
    await expect(card(page, /^PTO available$/).locator('dl')).toContainText(
      /Waiting for approval\s*8 hours/,
    )
    await expect(
      card(page, /^PTO available$/).locator('[data-slot="balance-figure"]'),
    ).not.toContainText(hours(balances.pto.availableLabel))

    // The same day again is refused in the form ("Already booked"), and Submit stays off.
    await requestButton(page).click()
    await pickDays(page, form(page), day)
    await expect(form(page).getByRole('region', { name: 'What this uses' })).toContainText(
      'Already booked',
    )
    await expect(form(page).getByRole('alert')).toContainText(
      `You already have time off on ${longDay(day)}.`,
    )
    await expect(form(page).getByRole('button', { name: 'Request time off' })).toBeDisabled()
    // Cancel closes the form and focus goes back to the button.
    await form(page).getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(form(page)).toHaveCount(0)
    await expect(requestButton(page)).toBeFocused()

    // Cancel the request: the dialog starts on "Keep it", and Escape returns to the row's Cancel.
    const cancel = row.getByRole('button', { name: /^Cancel PTO on / })
    await cancel.click()
    await expect(dialog(page)).toBeVisible()
    await expect(dialog(page).getByRole('button', { name: 'Keep it' })).toBeFocused()
    expect.soft((await settledScan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])
    await page.keyboard.press('Escape')
    await expect(dialog(page)).toBeHidden()
    await expect(cancel).toBeFocused()
    await cancel.click()
    await dialog(page).getByRole('button', { name: 'Cancel request' }).click()
    await expect(toast(page)).toHaveText('Canceled. 8 hours went back to your balance.')
    await expect(myRequests(page)).toBeFocused()
    await expect(row).toContainText('Canceled')
    await expect(row.getByRole('button', { name: /^Cancel PTO/ })).toHaveCount(0)
    await expect(
      card(page, /^PTO available$/).locator('[data-slot="balance-figure"]'),
    ).toContainText(hours(balances.pto.availableLabel))
  })

  test('sick time is recorded at once, with no approval', async ({ page }) => {
    await startAs(page, 'Priya')
    await openTimeOff(page)
    const facts = await factsOf(page)
    const [day] = workdays(facts, 1, 1) as [string]
    const sickBefore = await card(page, /^Sick leave available this year$/)
      .locator('[data-slot="balance-figure"]')
      .innerText()

    await requestButton(page).click()
    await form(page).getByRole('radio', { name: 'Sick time' }).click()
    await expect(
      form(page).getByText('Sick time is recorded right away, with no approval.'),
    ).toBeVisible()
    await pickDays(page, form(page), day)
    await expect(form(page).getByRole('region', { name: 'What this uses' })).toContainText(
      longDay(day),
    )
    expect.soft((await settledScan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])
    await form(page).getByRole('button', { name: 'Record sick time' }).click()
    await expect(toast(page)).toHaveText('Recorded.')
    await expect(requestButton(page)).toBeFocused()
    const row = rowsOn(page, longDay(day))
    await expect(row).toContainText('Recorded')
    await expect(row).toContainText('Sick time · 8 hours (1 day)')
    // It uses sick leave, not PTO.
    await expect(
      card(page, /^Sick leave available this year$/).locator('[data-slot="balance-figure"]'),
    ).not.toHaveText(sickBefore)
    await expectLedgersAdd(page)
  })

  test("another person's page adds up and is accessible (Dana, who has history in the seed)", async ({
    page,
  }) => {
    await startAs(page, 'Dana')
    await openTimeOff(page)
    await expect(page.locator('[data-slot="request-row"]').first()).toBeVisible()
    await expectLedgersAdd(page)
    expect((await settledScan(page)).violations).toEqual([])
  })

  test('a long request near today shows the short-notice advice, and one that costs more than the balance is refused', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await openTimeOff(page)
    const facts = await factsOf(page)
    const soon = workdays(facts, 1, 4)
    const long = await daysPastBalance(page, facts)
    // The last answer the check route gave, so the refusal is compared with the API's own label.
    let lastCheck: { draws: { availableBeforeLabel: string }[] } | undefined
    page.on('response', async (response) => {
      if (response.url().endsWith('/time-off/check')) {
        lastCheck = (await response.json().catch(() => undefined)) as typeof lastCheck
      }
    })
    await requestButton(page).click()

    // More than three days with under two weeks' notice: advice that never blocks the button.
    await pickDays(page, form(page), soon[0]!, soon[3]!)
    const advice = form(page).getByRole('status').filter({ hasText: 'usually needs 2 weeks' })
    await expect(advice).toHaveText(
      'More than 3 days usually needs 2 weeks’ notice. You can still request it.',
    )
    await expect(form(page).getByRole('button', { name: 'Request time off' })).toBeEnabled()

    // One working day more than the balance covers: a refusal that turns Submit off.
    await pickDays(page, form(page), long[0]!, long.at(-1)!)
    await expect(form(page).getByRole('alert')).toContainText('You have')
    expect(lastCheck?.draws[0]).toBeDefined()
    await expect(form(page).getByRole('alert')).toContainText(
      `You have ${lastCheck!.draws[0]!.availableBeforeLabel} available`,
    )
    expect.soft((await settledScan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])
    await expect(form(page).getByRole('button', { name: 'Request time off' })).toBeDisabled()
  })
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the form is a bottom sheet, nothing scrolls sideways, and axe finds nothing', async ({
    page,
  }) => {
    test.slow()
    await startAs(page, 'Priya')
    await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link', { name: 'Time off' })
      .click()
    await expect(requestButton(page)).toBeVisible()
    expect(await scrollsSideways(page)).toBe(false)
    expect.soft((await settledScan(page)).violations).toEqual([])

    await requestButton(page).click()
    await expect(sheet(page)).toBeVisible()
    await expect(form(page)).toHaveCount(0)
    const box = (await sheet(page).boundingBox())!
    expect(box.x + box.width).toBeLessThanOrEqual(390)
    expect(box.y + box.height).toBeGreaterThanOrEqual(843)
    expect(await scrollsSideways(page)).toBe(false)
    expect.soft((await settledScan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])

    // Close puts focus back on the button, as the docked panel does.
    await sheet(page).getByRole('button', { name: 'Close' }).click()
    await expect(sheet(page)).toBeHidden()
    await expect(requestButton(page)).toBeFocused()
  })
})
