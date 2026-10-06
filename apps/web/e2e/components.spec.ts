import { expect, test, type Locator } from '@playwright/test'
import { themeColor } from './helpers'

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
