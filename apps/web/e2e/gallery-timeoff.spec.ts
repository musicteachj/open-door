import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { GALLERY_STATE_IDS } from './gallery-ids'
import {
  AXE_TAGS,
  MODAL_OVERLAY_RULES,
  expectSectionHeadings,
  galleryState as state,
  galleryStateSelector,
  holdKey,
  openGallery,
  statesPastEdge,
} from './helpers'

// The time-off section of the gallery in a real browser: axe on every state, the cancel dialog's
// real box and focus, the date picker by keyboard alone, the radio groups, the request form as a
// phone's bottom sheet, and 390 px.

// From the first time-off state to the last one. The list is in page order, so the slice is
// bounded on both sides.
const TIMEOFF_IDS = GALLERY_STATE_IDS.slice(
  GALLERY_STATE_IDS.indexOf('status-badge-waiting'),
  GALLERY_STATE_IDS.indexOf('request-form-sheet') + 1,
)
// These start closed, behind a button.
const HOSTS: Record<string, string> = {
  'alert-dialog-cancel-request': 'Cancel time off',
  'request-form-sheet': 'Open the request form as a sheet',
}

test.beforeEach(async ({ page }) => {
  await openGallery(page)
})

test('every time-off state has its own heading', async ({ page }) => {
  // The page's own headings, first to last, are exactly the ids the tests below scan.
  await expectSectionHeadings(page, TIMEOFF_IDS)
  for (const id of TIMEOFF_IDS) await expect(page.locator(`h3#${id}`)).toHaveCount(1)
})

for (const id of TIMEOFF_IDS) {
  test(`${id} has no accessibility violations`, async ({ page }) => {
    const open = HOSTS[id]
    if (open) {
      await state(page, id).getByRole('button', { name: open }).click()
      await expect(
        page.getByRole(id === 'request-form-sheet' ? 'dialog' : 'alertdialog'),
      ).toBeVisible()
      const results = await new AxeBuilder({ page })
        .withTags(AXE_TAGS)
        .disableRules(MODAL_OVERLAY_RULES)
        .analyze()
      expect(results.violations).toEqual([])
      return
    }
    const results = await new AxeBuilder({ page })
      .withTags(AXE_TAGS)
      .include(galleryStateSelector(id))
      .analyze()
    expect(results.violations).toEqual([])
  })
}

test.describe('the cancel-request alert dialog', () => {
  const host = (page: Page) => state(page, 'alert-dialog-cancel-request')
  const opener = (page: Page) => host(page).getByRole('button', { name: 'Cancel time off' })
  const dialog = (page: Page) => page.getByRole('alertdialog')

  test.describe('at 1440 px', () => {
    test.use({ viewport: { width: 1440, height: 900 } })

    test('the box is 480 px wide and centered in the window', async ({ page }) => {
      await opener(page).click()
      const box = (await dialog(page).boundingBox())!
      expect(box.width).toBe(480)
      expect(Math.abs(box.x + box.width / 2 - 720)).toBeLessThanOrEqual(1)
      expect(Math.abs(box.y + box.height / 2 - 450)).toBeLessThanOrEqual(1)
    })

    test('the scrim covers the whole window', async ({ page }) => {
      await opener(page).click()
      const scrim = (await page.locator('[data-slot="alert-dialog-overlay"]').boundingBox())!
      expect(scrim).toEqual({ x: 0, y: 0, width: 1440, height: 900 })
    })

    test('the buttons sit at the right, "Keep it" before "Cancel request"', async ({ page }) => {
      await opener(page).click()
      const keep = (await dialog(page).getByRole('button', { name: 'Keep it' }).boundingBox())!
      const cancel = (await dialog(page)
        .getByRole('button', { name: 'Cancel request' })
        .boundingBox())!
      const box = (await dialog(page).boundingBox())!
      expect(keep.x).toBeLessThan(cancel.x)
      expect(Math.abs(keep.y - cancel.y)).toBeLessThanOrEqual(1)
      // 24 px of padding at the right edge.
      expect(Math.abs(cancel.x + cancel.width - (box.x + box.width - 24))).toBeLessThanOrEqual(1)
    })
  })

  test('focus starts on "Keep it"', async ({ page }) => {
    await opener(page).click()
    await expect(dialog(page).getByRole('button', { name: 'Keep it' })).toBeFocused()
  })

  test('Tab and Shift+Tab stay inside the dialog', async ({ page }) => {
    await opener(page).click()
    for (const key of ['Tab', 'Tab', 'Tab', 'Shift+Tab', 'Shift+Tab', 'Shift+Tab']) {
      await page.keyboard.press(key)
      expect(
        await page.evaluate(() => document.activeElement?.closest('[role="alertdialog"]') != null),
      ).toBe(true)
    }
  })

  test('Escape closes it and returns focus to the button that opened it', async ({ page }) => {
    await opener(page).click()
    await expect(dialog(page)).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog(page)).toBeHidden()
    await expect(opener(page)).toBeFocused()
  })

  test('"Keep it" closes it and returns focus to the button that opened it', async ({ page }) => {
    await opener(page).click()
    await dialog(page).getByRole('button', { name: 'Keep it' }).click()
    await expect(dialog(page)).toBeHidden()
    await expect(opener(page)).toBeFocused()
  })

  test('a press on the scrim does not close it', async ({ page }) => {
    await opener(page).click()
    await page.mouse.click(5, 5)
    await expect(dialog(page)).toBeVisible()
  })

  test.describe('at 390 px', () => {
    test.use({ viewport: { width: 390, height: 844 } })

    test('the box keeps 16 px from each side, with the buttons stacked full width', async ({
      page,
    }) => {
      await opener(page).click()
      const box = (await dialog(page).boundingBox())!
      expect(box.x).toBe(16)
      expect(box.width).toBe(390 - 32)
      const cancel = (await dialog(page)
        .getByRole('button', { name: 'Cancel request' })
        .boundingBox())!
      const keep = (await dialog(page).getByRole('button', { name: 'Keep it' }).boundingBox())!
      // The confirm is on top, and both fill the box inside its 24 px of padding.
      expect(cancel.y + cancel.height).toBeLessThanOrEqual(keep.y)
      for (const button of [cancel, keep]) {
        expect(button.x).toBeCloseTo(box.x + 24, 0)
        expect(button.width).toBeCloseTo(box.width - 48, 0)
      }
    })

    test('the scrim covers the whole window', async ({ page }) => {
      await opener(page).click()
      const scrim = (await page.locator('[data-slot="alert-dialog-overlay"]').boundingBox())!
      expect(scrim).toEqual({ x: 0, y: 0, width: 390, height: 844 })
    })
  })
})

test.describe('the date picker by keyboard alone', () => {
  const picker = (page: Page, id = 'date-picker-pto') => state(page, id)
  const day = (page: Page, date: string, id = 'date-picker-pto') =>
    picker(page, id).locator(`button[data-day="${date}"]`)
  const cell = (page: Page, date: string, id = 'date-picker-pto') =>
    picker(page, id).locator('td', { has: page.locator(`button[data-day="${date}"]`) })

  /** Tab from the "Next month" button onto the grid's one tab stop. */
  async function enterGrid(page: Page, id = 'date-picker-pto') {
    const next = picker(page, id).getByRole('button', { name: 'Next month' })
    await next.scrollIntoViewIfNeeded()
    await next.focus()
    await page.keyboard.press('Tab')
  }

  test('the grid is one tab stop, and Tab from the month buttons lands on today', async ({
    page,
  }) => {
    expect(await picker(page).locator('[role="grid"] button[tabindex="0"]').count()).toBe(1)
    await enterGrid(page)
    await expect(day(page, '2026-10-20')).toBeFocused()
    // The next Tab leaves the grid: the 30 other days are not tab stops.
    await page.keyboard.press('Tab')
    expect(
      await page.evaluate(() => document.activeElement?.closest('[role="grid"]') == null),
    ).toBe(true)
  })

  test('the arrow keys move by day and by week', async ({ page }) => {
    await enterGrid(page)
    await page.keyboard.press('ArrowRight')
    await expect(day(page, '2026-10-21')).toBeFocused()
    await page.keyboard.press('ArrowLeft')
    await expect(day(page, '2026-10-20')).toBeFocused()
    await page.keyboard.press('ArrowDown')
    await expect(day(page, '2026-10-27')).toBeFocused()
    await page.keyboard.press('ArrowUp')
    await expect(day(page, '2026-10-20')).toBeFocused()
  })

  test('Page Down moves to the same date next month, clamped to the last day', async ({ page }) => {
    await enterGrid(page)
    await page.keyboard.press('PageDown')
    await expect(day(page, '2026-11-20')).toBeFocused()
    await expect(picker(page).getByText('November 2026', { exact: true })).toBeVisible()
    await page.keyboard.press('PageUp')
    await expect(day(page, '2026-10-20')).toBeFocused()
    // October 31 has no match in November, so the move stops on its last day.
    for (const key of ['ArrowDown', 'ArrowRight', 'ArrowRight', 'ArrowRight', 'ArrowRight']) {
      await page.keyboard.press(key)
    }
    await expect(day(page, '2026-10-31')).toBeFocused()
    await page.keyboard.press('PageDown')
    await expect(day(page, '2026-11-30')).toBeFocused()
  })

  test("Home and End go to the week's ends", async ({ page }) => {
    await enterGrid(page)
    await page.keyboard.press('End')
    await expect(day(page, '2026-10-24')).toBeFocused()
    await page.keyboard.press('Home')
    await expect(day(page, '2026-10-18')).toBeFocused()
  })

  test('Enter picks a day, and a second Enter ends the range', async ({ page }) => {
    await enterGrid(page)
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('Enter')
    await expect(cell(page, '2026-10-27')).toHaveAttribute('aria-selected', 'true')
    await expect(picker(page).getByRole('status')).toHaveText(
      'Now pick the last day. For one day, choose Done.',
    )
    await page.keyboard.press('ArrowRight')
    await page.keyboard.press('ArrowRight')
    await page.keyboard.press('Enter')
    await expect(cell(page, '2026-10-29')).toHaveAttribute('aria-selected', 'true')
    await expect(cell(page, '2026-10-28')).toHaveAttribute('aria-selected', 'true')
    await expect(picker(page).getByRole('status')).toHaveText(
      'Selected: Tue, Oct 27 to Thu, Oct 29',
    )
  })

  test('a past day takes focus, and Enter on it picks nothing', async ({ page }) => {
    await enterGrid(page)
    await page.keyboard.press('Home')
    const past = day(page, '2026-10-18')
    await expect(past).toBeFocused()
    await expect(past).toHaveAttribute('aria-disabled', 'true')
    const hint = await picker(page).getByRole('status').textContent()
    await page.keyboard.press('Enter')
    await page.keyboard.press('Space')
    await expect(cell(page, '2026-10-18')).not.toHaveAttribute('aria-selected', 'true')
    await expect(picker(page).getByRole('status')).toHaveText(hint!)
    // The arrow keys cross it.
    await page.keyboard.press('ArrowRight')
    await expect(day(page, '2026-10-19')).toBeFocused()
  })

  test("a holiday's tooltip shows its name on keyboard focus", async ({ page }) => {
    const id = 'date-picker-range'
    await enterGrid(page, id)
    // The tab stop is the range's first day, Wednesday, November 25.
    await expect(day(page, '2026-11-25', id)).toBeFocused()
    await page.keyboard.press('ArrowRight')
    await expect(day(page, '2026-11-26', id)).toBeFocused()
    await expect(day(page, '2026-11-26', id)).toHaveAccessibleName(
      /^Thursday, November 26, Thanksgiving, company holiday/,
    )
    await expect(page.getByRole('tooltip')).toHaveText('Thanksgiving, company holiday')
  })

  test('Escape inside the picker in a request form closes it and returns focus to Dates', async ({
    page,
  }) => {
    const form = state(page, 'request-form-pto-one-day')
    const dates = form.getByRole('button', { name: /^Dates/ })
    await dates.scrollIntoViewIfNeeded()
    await dates.click()
    await expect(form.getByRole('grid')).toBeVisible()
    await expect(dates).toHaveAttribute('aria-expanded', 'true')
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')
    // Focus is in the grid, so this Escape is pressed from inside the picker.
    expect(
      await page.evaluate(() => document.activeElement?.closest('[role="grid"]') != null),
    ).toBe(true)
    await page.keyboard.press('Escape')
    await expect(form.getByRole('grid')).toBeHidden()
    await expect(dates).toBeFocused()
    await expect(dates).toHaveAttribute('aria-expanded', 'false')
  })
})

test.describe('the radio groups', () => {
  for (const [id, first, second] of [
    ['segmented-control-default', 'PTO', 'Sick time'],
    ['choice-group-default', 'Full day', 'Half day'],
  ] as const) {
    test(`${id} is one tab stop, and the arrow keys move and select`, async ({ page }) => {
      const group = state(page, id).getByRole('radiogroup')
      const one = group.getByRole('radio', { name: first })
      const two = group.getByRole('radio', { name: second })
      await one.scrollIntoViewIfNeeded()
      await expect(one).toBeChecked()
      // One tab stop: Tab leaves the group, and Shift+Tab comes back to the checked option.
      await one.focus()
      await page.keyboard.press('Tab')
      await expect(two).not.toBeFocused()
      await expect(one).not.toBeFocused()
      await page.keyboard.press('Shift+Tab')
      await expect(one).toBeFocused()
      await holdKey(page, 'ArrowRight', () => expect(two).toBeChecked())
      await expect(two).toBeFocused()
      await expect(two).toBeChecked()
      await expect(one).not.toBeChecked()
      await holdKey(page, 'ArrowLeft', () => expect(one).toBeChecked())
      await expect(one).toBeFocused()
      await expect(one).toBeChecked()
    })
  }

  test('a disabled group has two disabled options, and neither takes focus', async ({ page }) => {
    const radios = state(page, 'segmented-control-disabled')
      .getByRole('radiogroup')
      .getByRole('radio')
    await expect(radios).toHaveCount(2)
    for (const radio of await radios.all()) {
      await expect(radio).toBeDisabled()
      await radio.focus()
      await expect(radio).not.toBeFocused()
    }
  })
})

test.describe('the request form as a phone sheet', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  const opener = (page: Page) =>
    state(page, 'request-form-sheet').getByRole('button', {
      name: 'Open the request form as a sheet',
    })
  const sheet = (page: Page) => page.getByRole('dialog', { name: 'Request time off' })

  test.beforeEach(async ({ page }) => {
    await opener(page).scrollIntoViewIfNeeded()
    await opener(page).click()
    await expect(sheet(page)).toBeVisible()
  })

  test('opening moves focus to the title', async ({ page }) => {
    await expect(sheet(page).getByRole('heading', { name: 'Request time off' })).toBeFocused()
  })

  test('the sheet is full height and full width', async ({ page }) => {
    const box = (await sheet(page).boundingBox())!
    // 12 px of the page shows above it, as the bottom sheet is drawn everywhere.
    expect(box).toMatchObject({ x: 0, y: 12, width: 390, height: 844 - 12 })
  })

  test('focus stays inside the sheet, and the page behind is inert', async ({ page }) => {
    for (let i = 0; i < 14; i += 1) {
      await page.keyboard.press('Tab')
      expect(
        await page.evaluate(
          () => document.activeElement?.closest('[data-slot="bottom-sheet"]') != null,
        ),
      ).toBe(true)
    }
    // The page is hidden from assistive technology, and cannot be pressed.
    await expect(opener(page)).toHaveCount(0)
    expect(await page.evaluate(() => getComputedStyle(document.body).pointerEvents)).toBe('none')
  })

  test('Escape in an open picker closes only the picker, and a second Escape closes the sheet', async ({
    page,
  }) => {
    const dates = sheet(page).getByRole('button', { name: /^Dates/ })
    await dates.click()
    const grid = sheet(page).getByRole('grid')
    await expect(grid).toBeVisible()
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')
    expect(
      await page.evaluate(() => document.activeElement?.closest('[role="grid"]') != null),
    ).toBe(true)
    await page.keyboard.press('Escape')
    await expect(grid).toBeHidden()
    await expect(sheet(page)).toBeVisible()
    await expect(dates).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(sheet(page)).toBeHidden()
    await expect(opener(page)).toBeFocused()
  })

  test('the picker fills the width with cells of at least 44 px, and nothing scrolls sideways', async ({
    page,
  }) => {
    await sheet(page)
      .getByRole('button', { name: /^Dates/ })
      .click()
    const cells = sheet(page).locator('[role="grid"] td button')
    await expect(cells.first()).toBeVisible()
    const widths = await sheet(page)
      .locator('[role="grid"] td')
      .evaluateAll((tds) => tds.map((td) => td.getBoundingClientRect().width))
    expect(Math.min(...widths.filter((w) => w > 0))).toBeGreaterThanOrEqual(44)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    const wide = await sheet(page).evaluate(
      (el) =>
        [...el.querySelectorAll<HTMLElement>('*')].filter(
          (child) =>
            child.getBoundingClientRect().right > 391 && child.closest('.truncate') === null,
        ).length,
    )
    expect(wide).toBe(0)
  })

  test('Close shuts the sheet and returns focus to the button that opened it', async ({ page }) => {
    await sheet(page).getByRole('button', { name: 'Close', exact: true }).click()
    await expect(sheet(page)).toBeHidden()
    await expect(opener(page)).toBeFocused()
  })

  test('dragging the handle down past 80 px closes the sheet, and a short drag does not', async ({
    page,
  }) => {
    const handle = (await sheet(page).locator('[data-slot="bottom-sheet-handle"]').boundingBox())!
    const x = handle.x + handle.width / 2
    const y = handle.y + handle.height / 2
    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.mouse.move(x, y + 40, { steps: 4 })
    await page.mouse.up()
    await expect(sheet(page)).toBeVisible()
    // The sheet slides back; a press while it still does would land on the scrim and close it.
    await expect.poll(async () => (await sheet(page).boundingBox())!.y).toBe(12)
    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.mouse.move(x, y + 140, { steps: 8 })
    await page.mouse.up()
    await expect(sheet(page)).toBeHidden()
  })

  test('the footer buttons share the width, with the primary first', async ({ page }) => {
    const submit = (await sheet(page)
      .getByRole('button', { name: 'Request time off' })
      .boundingBox())!
    const cancel = (await sheet(page)
      .getByRole('button', { name: 'Cancel', exact: true })
      .boundingBox())!
    expect(submit.x).toBeLessThan(cancel.x)
    expect(Math.abs(submit.width - cancel.width)).toBeLessThanOrEqual(1)
  })
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('nothing in the time-off section scrolls sideways', async ({ page }) => {
    await expect(page.locator('h3#status-badge-waiting')).toBeAttached()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    expect(await statesPastEdge(page, TIMEOFF_IDS, 390)).toEqual([])
  })

  test('the balance cards stack, and a request row keeps Cancel at the top right', async ({
    page,
  }) => {
    const empty = state(page, 'balance-card-empty').locator('[data-slot="balance-card"]')
    const [one, two] = await Promise.all([0, 1].map((i) => empty.nth(i).boundingBox()))
    expect(two!.y).toBeGreaterThan(one!.y + one!.height - 1)
    const row = state(page, 'request-row-approved').locator('[data-slot="request-row"]')
    const cancel = (await row.getByRole('button', { name: /^Cancel/ }).boundingBox())!
    const dates = (await row.getByText('Wednesday, December 23').boundingBox())!
    const badge = (await row.getByText('Approved', { exact: true }).first().boundingBox())!
    const box = (await row.boundingBox())!
    expect(cancel.x + cancel.width).toBeGreaterThan(box.x + box.width - 16)
    expect(Math.abs(cancel.y - dates.y)).toBeLessThanOrEqual(12)
    // The badge is under the dates.
    expect(badge.y).toBeGreaterThan(dates.y + dates.height - 1)
  })
})
