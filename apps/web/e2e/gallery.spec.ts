import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

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
  for (const id of [
    'button-primary-default',
    'button-primary-disabled',
    'button-primary-loading',
    'button-destructive-loading',
    'input-invalid',
    'select-open',
    'menu-open',
    'avatar-sm',
    'skeleton-default',
  ]) {
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
