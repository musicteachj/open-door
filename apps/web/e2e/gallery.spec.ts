import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { GALLERY_STATE_IDS } from './gallery-ids'

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

const scan = (page: Page, disabledRules: string[] = []) =>
  new AxeBuilder({ page }).withTags(TAGS).disableRules(disabledRules).analyze()

// With a Radix select or menu open, the page behind it is aria-hidden while its focusable
// elements stay in the tab order. Radix traps focus inside the panel instead, so axe's
// aria-hidden-focus rule is a false alarm there. Those scans turn off that one rule, and the tests
// below check the trap with Tab.
const MODAL_OVERLAY_RULES = ['aria-hidden-focus']

const focusIsIn = (page: Page, selector: string) =>
  page.evaluate((s) => document.activeElement?.closest(s) != null, selector)

test.beforeEach(async ({ page }) => {
  await page.goto('/gallery')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Open Door component gallery' }),
  ).toBeVisible()
})

test('every state has its heading', async ({ page }) => {
  for (const id of GALLERY_STATE_IDS) {
    await expect(page.locator(`h3#${id}`)).toBeVisible()
  }
})

test('the gallery, closed, has no accessibility violations', async ({ page }) => {
  expect((await scan(page)).violations).toEqual([])
})

test('an open select has no violations, and focus stays inside it', async ({ page }) => {
  await page.locator('#select-open-trigger').click()
  const listbox = page.getByRole('listbox')
  await expect(listbox).toBeVisible()
  expect((await scan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])

  for (let i = 0; i < 4; i += 1) {
    await page.keyboard.press('Tab')
    expect(await focusIsIn(page, '[role="listbox"]')).toBe(true)
  }
  await page.keyboard.press('Escape')
  await expect(listbox).toBeHidden()
  await expect(page.locator('#select-open-trigger')).toBeFocused()
})

test('an open menu has no violations, and focus stays inside it', async ({ page }) => {
  await page.locator('#menu-open-trigger').click()
  const menu = page.getByRole('menu')
  await expect(menu).toBeVisible()
  expect((await scan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])

  for (let i = 0; i < 4; i += 1) {
    await page.keyboard.press('Tab')
    expect(await focusIsIn(page, '[role="menu"]')).toBe(true)
  }
  await page.keyboard.press('Escape')
  await expect(menu).toBeHidden()
  await expect(page.locator('#menu-open-trigger')).toBeFocused()
})

test('an open tooltip has no violations', async ({ page }) => {
  // Radix opens a tooltip on keyboard focus but not on locator.focus(), so arrive by keyboard.
  await page.locator('#tooltip-trigger').focus()
  await page.keyboard.press('Shift+Tab')
  await page.keyboard.press('Tab')
  await expect(page.locator('#tooltip-trigger')).toBeFocused()
  await expect(page.getByRole('tooltip')).toBeVisible()
  expect((await scan(page)).violations).toEqual([])
})

test('a toast has no violations', async ({ page }) => {
  await page.locator('#toast-show').click()
  const toast = page.locator('#toast-example')
  await expect(toast).toHaveAttribute('data-state', 'open')
  // Scanning mid-animation would read blended colors, so wait for the entry animation to end.
  await expect
    .poll(() =>
      toast.evaluate((el) =>
        el.getAnimations().every((animation) => animation.playState === 'finished'),
      ),
    )
    .toBe(true)
  expect((await scan(page)).violations).toEqual([])
})

test('an open persona menu has no violations, focus starts on the checked persona, and stays inside', async ({
  page,
}) => {
  await page.locator('[aria-labelledby="persona-menu-open"] button').click()
  const menu = page.getByRole('menu')
  await expect(menu).toBeVisible()
  await expect(page.getByRole('menuitemradio', { name: /Priya Raman/ })).toBeFocused()
  expect((await scan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])

  for (let i = 0; i < 6; i += 1) {
    await page.keyboard.press('Tab')
    expect(await focusIsIn(page, '[role="menu"]')).toBe(true)
  }
  await page.keyboard.press('Escape')
  await expect(menu).toBeHidden()
  await expect(page.locator('[aria-labelledby="persona-menu-open"] button')).toBeFocused()
})

test('a truncated persona title shows its tooltip in a real browser', async ({ page }) => {
  // Real layout decides truncation. Arrive by keyboard, since Radix opens on keyboard focus.
  const button = page.locator('#persona-switcher-truncated-button')
  // Truncation is measured after layout and again once the web font loads. Under a busy run the
  // focus could land first, so wait for the switcher's own measurement.
  await expect(button).toHaveAttribute('data-truncated', 'true')
  await button.focus()
  await page.keyboard.press('Shift+Tab')
  await page.keyboard.press('Tab')
  await expect(button).toBeFocused()
  await expect(page.getByRole('tooltip')).toContainText('Senior Department Lead')

  // A title that fits shows none.
  await page.locator('[aria-labelledby="persona-switcher-closed"] button').focus()
  await page.keyboard.press('Shift+Tab')
  await page.keyboard.press('Tab')
  await expect(page.locator('[aria-labelledby="persona-switcher-closed"] button')).toBeFocused()
  await expect(page.getByRole('tooltip')).toBeHidden()
})

test('the composer states fill their section, not just their text', async ({ page }) => {
  for (const id of ['composer-empty', 'composer-error', 'composer-busy']) {
    const section = page.locator(`section[aria-labelledby="${id}"]`)
    const composer = section.locator('[data-slot="composer"]')
    const sectionBox = await section.boundingBox()
    const composerBox = await composer.boundingBox()
    expect(composerBox?.width).toBeGreaterThan(600)
    expect(composerBox?.width).toBe(sectionBox?.width)
  }
})

test('a hovered starting persona card keeps its primary border', async ({ page }) => {
  const card = page.locator('section[aria-labelledby="persona-card-starting"] button')
  await card.hover()
  const border = await card.evaluate((el) => getComputedStyle(el).borderTopColor)
  const primary = await page.evaluate(() => {
    const probe = document.createElement('div')
    probe.style.color = 'var(--color-primary)'
    document.body.append(probe)
    const color = getComputedStyle(probe).color
    probe.remove()
    return color
  })
  expect(border).toBe(primary)
})

test('an open filter select has no violations, and keeps its label and counts', async ({
  page,
}) => {
  await page.locator('#filter-select-open-trigger').click()
  const listbox = page.getByRole('listbox')
  await expect(listbox).toBeVisible()
  for (const name of ['All', 'Austin warehouse, 35', 'Denver HQ, 40', 'Oakland store, 0']) {
    await expect(listbox.getByRole('option', { name, exact: true })).toBeVisible()
  }
  // The count sits at the option's right edge, apart from the name.
  const option = listbox.getByRole('option', { name: 'Denver HQ, 40' })
  const [nameBox, countBox, optionBox] = await Promise.all([
    option.locator('[data-slot="select-item-text"]').boundingBox(),
    option.locator('span[aria-hidden="true"].tabular-nums').boundingBox(),
    option.boundingBox(),
  ])
  expect(countBox!.x).toBeGreaterThan(nameBox!.x + nameBox!.width + 16)
  expect(countBox!.x + countBox!.width).toBeGreaterThan(optionBox!.x + optionBox!.width - 20)
  expect((await scan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])
  await page.keyboard.press('Escape')
  await expect(page.locator('#filter-select-open-trigger')).toBeFocused()
})

test('clearing the search puts focus back in the field', async ({ page }) => {
  const section = page.locator('section[aria-labelledby="search-field-typed"]')
  await section.getByRole('button', { name: 'Clear search' }).click()
  await expect(section.getByRole('searchbox')).toBeFocused()
  await expect(section.getByRole('searchbox')).toHaveValue('')
})
