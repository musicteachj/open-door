import { expect, test, type Locator } from '@playwright/test'
import { focusRing, galleryState, themeColor } from './helpers'

// What the browser paints for the Stage 3 and 4 components, read with getComputedStyle after real
// mouse and keyboard input. The axe scans, the truncated tooltip, and the 390 px stacking are in
// gallery.spec.ts and narrow.spec.ts.

test.beforeEach(async ({ page }) => {
  await page.goto('/gallery')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Open Door component gallery' }),
  ).toBeVisible()
})

const background = (target: Locator) =>
  target.evaluate((el) => getComputedStyle(el).backgroundColor)

test('a hovered nav item goes neutral, never to the current item tint', async ({ page }) => {
  const item = page.locator('section[aria-labelledby="nav-item-default"] a')
  await item.scrollIntoViewIfNeeded()
  await item.hover()
  // The fill transitions, so wait for it to arrive.
  await expect.poll(() => background(item)).toBe(await themeColor(page, 'neutral-hover'))
  expect(await background(item)).not.toBe(await themeColor(page, 'primary-tint'))
})

test('a hovered directory row and "Try asking" row go to the tint', async ({ page }) => {
  const tint = await themeColor(page, 'primary-tint')
  const row = page
    .locator('section[aria-labelledby="directory-row-default"]')
    .getByRole('link')
    .first()
  await row.scrollIntoViewIfNeeded()
  await row.hover()
  await expect.poll(() => background(row)).toBe(tint)

  const ask = page
    .locator('section[aria-labelledby="try-asking-default"] [data-slot="try-asking-row"]')
    .first()
  await ask.scrollIntoViewIfNeeded()
  await ask.hover()
  await expect.poll(() => background(ask)).toBe(tint)
})

test('the composer shows the primary border and the focus halo when the box has keyboard focus', async ({
  page,
}) => {
  const section = page.locator('section[aria-labelledby="composer-empty"]')
  const box = section.getByRole('textbox', { name: 'Ask Open Door' })
  const wrapper = section.locator('[data-slot="composer"] > div').first()
  const read = () =>
    wrapper.evaluate((el) => {
      const style = getComputedStyle(el)
      return { border: style.borderTopColor, shadow: style.boxShadow }
    })

  // At rest the wrapper has neither.
  const resting = await read()
  expect(resting.border).toBe(await themeColor(page, 'input-border'))
  expect(resting.shadow).not.toContain('0px 0px 0px 3px')

  // Arrive by keyboard: the textarea is the first control after the one before it.
  await box.focus()
  await page.keyboard.press('Shift+Tab')
  await page.keyboard.press('Tab')
  await expect(box).toBeFocused()

  const primary = await themeColor(page, 'primary')
  // The halo is the primary at 18%: three pixels, spread only.
  // Both fade in over 150 ms, so wait for each to settle rather than reading mid-transition.
  await expect.poll(async () => (await read()).border).toBe(primary)
  await expect.poll(async () => (await read()).shadow).toMatch(/rgba?\(.*\) 0px 0px 0px 3px/)
})

// Stage 5: the time-off, approvals, and confirm-card parts.

test('a hovered day cell goes to a light fill, and today keeps its ring', async ({ page }) => {
  const picker = galleryState(page, 'date-picker-pto')
  const ordinary = picker.locator('button[data-day="2026-10-22"]')
  const today = picker.locator('button[data-day="2026-10-20"]')
  await ordinary.scrollIntoViewIfNeeded()
  await expect.poll(() => background(ordinary)).toBe('rgba(0, 0, 0, 0)')
  await ordinary.hover()
  const fill = await themeColor(page, 'neutral-hover')
  await expect.poll(() => background(ordinary)).toBe(fill)

  const ring = () => today.evaluate((el) => getComputedStyle(el).boxShadow)
  expect(await ring()).toMatch(/inset/)
  await today.hover()
  await expect.poll(() => background(today)).toBe(fill)
  // The ring is still there, one pixel and inset, in the field-border color.
  const shadow = await ring()
  expect(shadow).toContain(await themeColor(page, 'input-border'))
  expect(shadow).toMatch(/0px 0px 0px 1px inset/)
})

test('a request row tints on hover and while its Cancel has focus', async ({ page }) => {
  const row = galleryState(page, 'request-row-approved').locator('[data-slot="request-row"]')
  const tint = await themeColor(page, 'surface-sunken')
  await row.scrollIntoViewIfNeeded()
  await page.mouse.move(0, 0)
  await expect.poll(() => background(row)).not.toBe(tint)
  await row.hover()
  await expect.poll(() => background(row)).toBe(tint)

  await page.mouse.move(0, 0)
  const cancel = row.getByRole('button', { name: /^Cancel PTO on / })
  await expect.poll(() => background(row)).not.toBe(tint)
  await cancel.focus()
  await page.keyboard.press('Shift+Tab')
  await page.keyboard.press('Tab')
  await expect(cancel).toBeFocused()
  await expect.poll(() => background(row)).toBe(tint)
})

test('keyboard focus shows the ring on Confirm, Approve, a source chip, and a day cell', async ({
  page,
}) => {
  const targets = [
    galleryState(page, 'confirm-card-book-pending').getByRole('button', { name: /^Confirm: / }),
    galleryState(page, 'approval-card-default').getByRole('button', { name: /^Approve / }),
    galleryState(page, 'confirm-card-approve-pending').locator('[data-slot="rule-chip"]').first(),
    galleryState(page, 'date-picker-pto').locator('button[data-day="2026-10-22"]'),
  ]
  for (const [i, target] of targets.entries()) {
    await target.scrollIntoViewIfNeeded()
    await target.focus()
    // A day cell is the grid's tab stop only when it is today, so move off and back by key.
    if (i === 3) {
      await page.keyboard.press('ArrowLeft')
      await page.keyboard.press('ArrowRight')
    } else {
      await page.keyboard.press('Shift+Tab')
      await page.keyboard.press('Tab')
    }
    await expect(target).toBeFocused()
    const ring = await focusRing(page)
    expect(ring.style, `target ${i}`).toBe('solid')
    expect(parseFloat(ring.width), `target ${i}`).toBeGreaterThanOrEqual(2)
    // The color fades in with the other transitions, so wait for it to arrive.
    const ringColor = await themeColor(page, 'focus-ring')
    await expect
      .poll(() => page.evaluate(() => getComputedStyle(document.activeElement!).outlineColor), {
        message: `target ${i}`,
      })
      .toBe(ringColor)
  }
})
