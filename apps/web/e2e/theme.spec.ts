import { expect, test, type Locator, type Page } from '@playwright/test'

// What the browser actually paints, read with getComputedStyle after real keyboard and mouse input.

test.beforeEach(async ({ page }) => {
  await page.goto('/gallery')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Open Door component gallery' }),
  ).toBeVisible()
})

/** A theme color as the browser computes it, for comparing with computed outline and fills. */
const themeColor = (page: Page, token: string) =>
  page.evaluate((name) => {
    const probe = document.createElement('div')
    probe.style.color = `var(--color-${name})`
    document.body.append(probe)
    const color = getComputedStyle(probe).color
    probe.remove()
    return color
  }, token)

const outline = (target: Locator) =>
  target.evaluate((el) => {
    const style = getComputedStyle(el)
    return {
      width: style.outlineWidth,
      style: style.outlineStyle,
      offset: style.outlineOffset,
      color: style.outlineColor,
    }
  })

test('a keyboard-focused button shows the 2 px focus ring, offset 2 px', async ({ page }) => {
  // The first control on the page is the first primary button.
  await page.keyboard.press('Tab')
  const first = page.getByRole('button', { name: 'Label' }).first()
  await expect(first).toBeFocused()
  // Read at once, with no polling: the design shows the ring the moment focus arrives.
  expect(await outline(first)).toEqual({
    width: '2px',
    style: 'solid',
    offset: '2px',
    color: await themeColor(page, 'focus-ring'),
  })
})

test('a mouse click does not show the focus ring', async ({ page }) => {
  const first = page.getByRole('button', { name: 'Label' }).first()
  await first.click()
  await expect(first).toBeFocused()
  expect((await outline(first)).style).toBe('none')
})

test('a focused menu row shows the inset ring, offset -2 px', async ({ page }) => {
  await page.locator('#menu-open-trigger').focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('menu')).toBeVisible()
  await page.keyboard.press('ArrowDown')
  const row = page.getByRole('menuitemradio', { name: 'Marcus Bell' })
  await expect(row).toBeFocused()
  const ringColor = await themeColor(page, 'focus-ring')
  await expect
    .poll(() => outline(row))
    .toEqual({ width: '2px', style: 'solid', offset: '-2px', color: ringColor })
})

test('a button fades its colors over 150 ms on hover', async ({ page }) => {
  const button = page.locator('#button-primary-default + div button').first()
  await expect(button).toBeVisible()

  const resting = await button.evaluate((el) => getComputedStyle(el).backgroundColor)
  expect(resting).toBe(await themeColor(page, 'primary'))

  const box = (await button.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  // The hover starts a CSS transition. Without `transition-colors` the color would jump, and no
  // transition would exist to find.
  const transition = await button.evaluate((el) => {
    const running = el.getAnimations().filter((a) => a instanceof CSSTransition)
    return running.map((a) => ({
      property: (a as CSSTransition).transitionProperty,
      durationMs: a.effect?.getTiming().duration,
    }))
  })
  expect(transition).toContainEqual({ property: 'background-color', durationMs: 150 })

  const hover = await themeColor(page, 'primary-hover')
  await expect.poll(() => button.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe(hover)
})
