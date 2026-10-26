import { expect, test, type Page } from '@playwright/test'
import { askAndWaitForAnswer } from './conversation-helpers'
import { MODAL_OVERLAY_RULES, startAs } from './helpers'
import {
  bookOnPage,
  cards,
  factsOf,
  pickDays,
  workdays,
  longDay,
  nav,
  openFromNav,
  railLink,
  rowsOn,
  scrollsSideways,
  settledScan,
  skipUnlessScriptedDayCounts,
  switchPersona,
  toast,
} from './time-off-helpers'

// Screen 09 (Approvals) in the real app, and the flow between an employee and a manager both ways.
// The card, the dialog, and every state are proved one by one in gallery-approvals.spec.ts. These
// tests prove what only the page adds: the queue and lists come from the API, a decision reaches
// the server and the lists, the count and the focus follow, a request that moved on is held with
// its refusal, and only a manager gets the page. The seed has Zara Bautista's PTO (21 to 28 days
// out) waiting for Marcus Bell, so Marcus starts with one request and Priya's makes two.

const dialog = (page: Page) => page.getByRole('alertdialog')
const waitingHeading = (page: Page) =>
  page.getByRole('heading', { level: 2, name: /^Waiting for you/ })
const approvalCards = (page: Page) => page.locator('[data-slot="approval-card"]')
const cardOf = (page: Page, name: string) => approvalCards(page).filter({ hasText: name })
const section = (page: Page, heading: string) =>
  page.locator('section').filter({ has: page.getByRole('heading', { level: 2, name: heading }) })
const approvalsLink = (page: Page, waiting: number) =>
  nav(page).getByRole('link', {
    name: waiting === 0 ? 'Approvals' : `Approvals, ${waiting} waiting`,
    exact: true,
  })

test.describe('at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('Marcus decides the queue: the count, the dialogs, the lists, the focus, and what Priya then sees', async ({
    page,
  }) => {
    test.setTimeout(120_000)
    await startAs(page, 'Priya')
    const day = await bookOnPage(page)
    // Priya also records sick time. It is recorded, never decided, so Marcus's queue must not grow.
    const [sickDay] = workdays(await factsOf(page), 1, 1) as [string]
    await page.getByRole('button', { name: 'Request time off' }).first().click()
    const sickForm = page.locator('#request-form')
    await sickForm.getByRole('radio', { name: 'Sick time' }).click()
    await pickDays(page, sickForm, sickDay)
    await sickForm.getByRole('button', { name: 'Record sick time' }).click()
    await expect(toast(page)).toHaveText('Recorded.')
    await switchPersona(page, 'Marcus')

    // The nav item carries the waiting count in its name: Zara's, and Priya's.
    await expect(approvalsLink(page, 2)).toBeVisible()
    await approvalsLink(page, 2).click()
    await expect(page).toHaveURL('/approvals')
    await expect(waitingHeading(page)).toHaveAccessibleName('Waiting for you, 2')
    await expect(approvalCards(page)).toHaveCount(2)
    const zara = cardOf(page, 'Zara Bautista')
    const priya = cardOf(page, 'Priya Raman')
    await expect(zara).toContainText('Team coverage')
    await expect(priya).toContainText(longDay(day).replace(/^\w+, /, ''))
    // The sick day is recorded, not approved: no card mentions it, and the count stayed at two
    // (Zara's PTO and Priya's PTO). It shows under Coming up, which is right.
    await expect(approvalCards(page).filter({ hasText: 'Sick time' })).toHaveCount(0)
    await expect(approvalCards(page).filter({ hasText: longDay(sickDay) })).toHaveCount(0)
    await expect(section(page, 'Coming up on your team')).toContainText(longDay(sickDay))
    expect.soft((await settledScan(page)).violations).toEqual([])

    // The approve dialog starts on "Go back", and Escape returns to the button that opened it.
    const approveZara = zara.getByRole('button', { name: /^Approve Zara Bautista’s PTO, / })
    await approveZara.click()
    await expect(dialog(page).getByRole('button', { name: 'Go back' })).toBeFocused()
    expect.soft((await settledScan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])
    await page.keyboard.press('Escape')
    await expect(dialog(page)).toBeHidden()
    await expect(approveZara).toBeFocused()

    // Approving: the toast, the lists, the count, and focus on the next request's Approve.
    await approveZara.click()
    await dialog(page).getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(toast(page)).toHaveText('Approved. Zara will see it on the Time off page.')
    await expect(approvalCards(page)).toHaveCount(1)
    await expect(approvalsLink(page, 1)).toBeVisible()
    await expect(waitingHeading(page)).toHaveAccessibleName('Waiting for you, 1')
    await expect(priya.getByRole('button', { name: /^Approve Priya Raman’s PTO, / })).toBeFocused()
    await expect(section(page, 'Recent decisions')).toContainText('Zara Bautista')
    await expect(section(page, 'Recent decisions')).toContainText('Approved today')
    await expect(section(page, 'Coming up on your team')).toContainText('Zara Bautista')

    // Denying with a note: the dialog starts in the note field, the toast names the note, "Your
    // note" shows in Recent decisions, nothing is left waiting, and focus goes to the heading.
    await priya.getByRole('button', { name: /^Deny Priya Raman’s PTO, / }).click()
    const note = dialog(page).getByRole('textbox', { name: 'Note to Priya (optional)' })
    await expect(note).toBeFocused()
    await note.fill('Please pick another week.')
    await expect(dialog(page)).toContainText('25 of 300')
    await dialog(page).getByRole('button', { name: 'Deny', exact: true }).click()
    await expect(toast(page)).toHaveText('Denied. Priya will see your note on the Time off page.')
    await expect(approvalCards(page)).toHaveCount(0)
    await expect(approvalsLink(page, 0)).toBeVisible()
    await expect(waitingHeading(page)).toBeFocused()
    await expect(page.getByText('Nothing is waiting for you.')).toBeVisible()
    const denied = rowsOn(section(page, 'Recent decisions'), longDay(day))
    await expect(denied).toContainText('Denied today')
    await expect(denied).toContainText('Your note')
    await expect(denied).toContainText('“Please pick another week.”')

    // Priya sees the denial and the note on her Time off page, and the hours are back.
    await switchPersona(page, 'Priya')
    await openFromNav(page, 'Time off', '/time-off')
    const row = rowsOn(page, longDay(day))
    await expect(row).toContainText('Denied')
    await expect(row).toContainText('Denied by Marcus Bell')
    await expect(row).toContainText('Marcus Bell’s note')
    await expect(row).toContainText('“Please pick another week.”')
    await expect(page.getByRole('button', { name: /^Cancel PTO on / })).toHaveCount(0)
  })

  test('a request that was canceled while Marcus had the page open is held, muted, with the refusal', async ({
    page,
  }) => {
    // A second browser cannot be Priya in the same sandbox: a persona switch ends her session. So
    // Priya cancels for real first, and the only thing staged is Marcus's page being out of date:
    // his queue read keeps listing her request (as it did before she canceled) until he decides.
    // His decision then goes to the real API, which refuses it, and the card is held.
    await startAs(page, 'Priya')
    await bookOnPage(page)
    const listed = await page.evaluate(async () => {
      const response = await fetch(
        '/api/v1/time-off/requests?scope=mine&from=2000-01-01&to=2100-01-01',
      )
      const { items } = (await response.json()) as { items: { id: string; status: string }[] }
      return items.find((item) => item.status === 'pending')!
    })
    await page.getByRole('button', { name: /^Cancel PTO on / }).click()
    await dialog(page).getByRole('button', { name: 'Cancel request' }).click()
    await expect(toast(page)).toContainText('Canceled.')

    let stale = true
    await page.route('**/api/v1/time-off/requests?*scope=waiting*', async (route) => {
      const response = await route.fetch()
      const body = (await response.json()) as { items: unknown[] }
      if (stale) body.items.push(listed)
      await route.fulfill({ response, json: body })
    })
    page.on('response', (response) => {
      if (response.url().endsWith('/decision')) stale = false
    })
    await switchPersona(page, 'Marcus')
    await openFromNav(page, /^Approvals, 1 waiting$/, '/approvals')
    await expect(approvalCards(page)).toHaveCount(2)

    const priya = cardOf(page, 'Priya Raman')
    await priya.getByRole('button', { name: /^Approve Priya Raman’s PTO, / }).click()
    await dialog(page).getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(dialog(page)).toBeHidden()
    await expect(priya.getByRole('alert')).toHaveText('Priya canceled this request.')
    await expect(priya.locator('[data-slot="status-badge"]')).toHaveText('Canceled')
    await expect(priya.getByRole('button', { name: /^(Approve|Deny)/ })).toHaveCount(0)
    // Zara's card is still live, and the count never included Priya's.
    await expect(approvalCards(page)).toHaveCount(2)
    await expect(approvalsLink(page, 1)).toBeVisible()
  })

  test('only a manager has Approvals: the item goes when Marcus switches to Priya, and the page is Not found for her', async ({
    page,
  }) => {
    await startAs(page, 'Marcus')
    await expect(approvalsLink(page, 1)).toBeVisible()
    await switchPersona(page, 'Priya')
    await expect(
      page.getByRole('button', { name: /^Switch persona. Current: Priya/ }),
    ).toBeVisible()
    await expect(nav(page).getByRole('link', { name: /^Approvals/ })).toHaveCount(0)
    await page.goto('/approvals')
    await expect(page.getByRole('heading', { name: "We couldn't find that page." })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Waiting for you' })).toHaveCount(0)
  })

  test('Priya books in chat and confirms, Marcus approves on the page, and Priya sees it approved', async ({
    page,
  }) => {
    test.setTimeout(90_000)
    await startAs(page, 'Priya')
    await skipUnlessScriptedDayCounts(test, page, 'book next friday')
    await askAndWaitForAnswer(page, 'book next friday')
    await page.getByRole('button', { name: /^Confirm: book PTO on / }).click()
    await expect(cards(page).first().locator('output')).toContainText(
      'Requested. Marcus Bell will review it.',
    )
    await expect(railLink(page, 'requests? pending')).toHaveAccessibleName(
      /^1 request pending\. Open Time off$/,
    )
    const bookedDay = (await cards(page)
      .first()
      .locator('dd', { hasText: /^\w+day, / })
      .first()
      .textContent())!

    await switchPersona(page, 'Marcus')
    await openFromNav(page, /^Approvals, 2 waiting$/, '/approvals')
    const priya = cardOf(page, 'Priya Raman')
    await expect(priya).toBeVisible()
    await priya.getByRole('button', { name: /^Approve Priya Raman’s PTO, / }).click()
    await dialog(page).getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(toast(page)).toHaveText('Approved. Priya will see it on the Time off page.')

    await switchPersona(page, 'Priya')
    await openFromNav(page, 'Time off', '/time-off')
    await expect(rowsOn(page, bookedDay)).toContainText('Approved')
    await openFromNav(page, 'Ask', '/ask')
    // The rail keeps PTO available and shows no request pending now that it is decided.
    await expect(railLink(page, 'requests? pending')).toHaveAccessibleName(
      /^0 requests pending\. Open Time off$/,
    )
  })

  test('Priya books on the page, Marcus decides Zara on the page, then approves Priya in chat', async ({
    page,
  }) => {
    test.setTimeout(90_000)
    await startAs(page, 'Priya')
    const day = await bookOnPage(page)
    await switchPersona(page, 'Marcus')
    await openFromNav(page, /^Approvals, 2 waiting$/, '/approvals')
    // "Approve it" takes the first request waiting, which is Zara's from the seed, so she is
    // decided here first and the assistant reaches Priya's.
    await cardOf(page, 'Zara Bautista')
      .getByRole('button', { name: /^Approve Zara/ })
      .click()
    await dialog(page).getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(toast(page)).toHaveText('Approved. Zara will see it on the Time off page.')
    await expect(approvalsLink(page, 1)).toBeVisible()

    await openFromNav(page, 'Ask', '/ask')
    await askAndWaitForAnswer(page, 'approve it')
    const card = cards(page).first()
    await expect(card.getByRole('heading', { name: 'Approve a request' })).toBeVisible()
    await expect(card).toContainText('Priya Raman')
    await expect(card).toContainText(longDay(day))
    await card.getByRole('button', { name: /^Confirm: approve Priya Raman’s PTO, / }).click()
    await expect(card.locator('output')).toContainText(
      'Approved. Priya will see it on the Time off page.',
    )
    await expect(card.getByRole('link', { name: 'View in Approvals' })).toBeVisible()
    await expect(approvalsLink(page, 0)).toBeVisible()
    await expect(railLink(page, 'approvals? waiting')).toHaveAccessibleName(
      /^0 approvals waiting\. Open Approvals$/,
    )

    await switchPersona(page, 'Priya')
    await openFromNav(page, 'Time off', '/time-off')
    await expect(rowsOn(page, longDay(day))).toContainText('Approved')
    await expect(rowsOn(page, longDay(day))).toContainText('Approved by Marcus Bell')
  })
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the cards stack, nothing scrolls sideways, and axe finds nothing', async ({ page }) => {
    test.slow()
    await startAs(page, 'Marcus')
    await openFromNav(page, /^Approvals, 1 waiting$/, '/approvals')
    await expect(approvalCards(page)).toHaveCount(1)
    expect(await scrollsSideways(page)).toBe(false)
    const approve = (await approvalCards(page)
      .getByRole('button', { name: /^Approve / })
      .boundingBox())!
    const deny = (await approvalCards(page)
      .getByRole('button', { name: /^Deny / })
      .boundingBox())!
    // Approve and Deny share the row, half the card each.
    expect(Math.abs(approve.y - deny.y)).toBeLessThanOrEqual(1)
    expect(approve.width).toBeCloseTo(deny.width, 0)
    expect.soft((await settledScan(page)).violations).toEqual([])

    await approvalCards(page)
      .getByRole('button', { name: /^Approve / })
      .click()
    const box = (await dialog(page).boundingBox())!
    expect(box.x).toBeCloseTo(16, 0)
    expect(box.width).toBeCloseTo(390 - 32, 0)
    expect(await scrollsSideways(page)).toBe(false)
    expect.soft((await settledScan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])
  })
})
