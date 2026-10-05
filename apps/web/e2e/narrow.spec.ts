import { expect, test, type Page } from '@playwright/test'
import { startAs } from './helpers'

test.use({ viewport: { width: 390, height: 844 } })

const scrollWidth = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth)

test('the landing page fits a 390 px screen', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'Open Door' })).toBeVisible()
  expect(await scrollWidth(page)).toBeLessThanOrEqual(390)
})

test('/ask fits a 390 px screen', async ({ page }) => {
  await startAs(page, 'Priya')
  await expect(page.getByRole('heading', { level: 1, name: 'Ask' })).toBeVisible()
  expect(await scrollWidth(page)).toBeLessThanOrEqual(390)
})
