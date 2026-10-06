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

test('a full-page message keeps its 32-character reference inside its box at 390 px', async ({
  page,
}) => {
  await page.goto('/gallery')
  const id = page.locator('#full-page-message-error')
  await id.scrollIntoViewIfNeeded()
  const message = page.locator(
    '[aria-labelledby="full-page-message-error"] [data-slot="full-page-message"]',
  )
  const code = message.locator('code')
  await expect(code).toHaveText(/^[0-9a-f]{32}$/)
  const [codeBox, messageBox] = await Promise.all([code.boundingBox(), message.boundingBox()])
  // The frame clips overflow, so compare the code's own box with the message's.
  expect(codeBox!.x).toBeGreaterThanOrEqual(messageBox!.x)
  expect(codeBox!.x + codeBox!.width).toBeLessThanOrEqual(messageBox!.x + messageBox!.width)
  // This checks the message's own box. The page as a whole is checked by the next test.
  expect(await message.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
})

test('the component gallery fits a 390 px screen', async ({ page }) => {
  await page.goto('/gallery')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Open Door component gallery' }),
  ).toBeVisible()
  expect(await scrollWidth(page)).toBeLessThanOrEqual(390)
})
