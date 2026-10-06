import { expect, test, type Page } from '@playwright/test'
import { startAs } from './helpers'

test.use({ viewport: { width: 390, height: 844 } })

const scrollWidth = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth)

// The landing page's and the home's 390 px checks (stacking, overflow, the nav, the indicator) are
// in landing.spec.ts and home.spec.ts, beside the criteria they prove.

test("the /ask greeting is the kit's 32/40 at 390 px", async ({ page }) => {
  await startAs(page, 'Priya')
  const greeting = page.getByRole('heading', { level: 1 })
  await expect(greeting).toHaveCSS('font-size', '32px')
  await expect(greeting).toHaveCSS('line-height', '40px')
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

test('a directory row stacks its cells below 760 px, and the table drops its column labels', async ({
  page,
}) => {
  await page.goto('/gallery')
  const table = page.locator('section[aria-labelledby="directory-table-default"]')
  await table.scrollIntoViewIfNeeded()
  await expect(table.getByText('Department', { exact: true })).toBeHidden()
  const cells = table.getByRole('link').first().locator(':scope > span')
  const boxes = await Promise.all([0, 1, 2, 3].map((i) => cells.nth(i).boundingBox()))
  for (let i = 1; i < 4; i += 1) {
    // Each cell starts below the previous one's top, not beside it.
    expect(boxes[i]!.y).toBeGreaterThan(boxes[i - 1]!.y)
    expect(boxes[i]!.x).toBeGreaterThanOrEqual(boxes[0]!.x)
  }
  const link = await table.getByRole('link').first().boundingBox()
  expect(link!.height).toBeGreaterThan(60)
})

test('a detail row stacks its label over its value at 390 px', async ({ page }) => {
  await page.goto('/gallery')
  const row = page
    .locator('section[aria-labelledby="detail-list-values"] [data-slot="detail-row"]')
    .first()
  await row.scrollIntoViewIfNeeded()
  const [label, value] = await Promise.all([
    row.locator('dt').boundingBox(),
    row.locator('dd').boundingBox(),
  ])
  expect(value!.y).toBeGreaterThanOrEqual(label!.y + label!.height)
  expect(value!.x).toBeLessThanOrEqual(label!.x + 1)
})

test.describe('at desktop width', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('the landing page picker is 1168 px wide, as the design draws it', async ({ page }) => {
    await page.goto('/')
    const list = page.getByRole('list')
    await expect(list).toBeVisible()
    const box = await list.boundingBox()
    expect(Math.abs((box?.width ?? 0) - 1168)).toBeLessThanOrEqual(1)
  })
})

test.describe('the assistant home at desktop width', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test("matches the kit's content box: a 686 px composer, 213 px under the sheet's top", async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    const composer = page.locator('[data-slot="composer"]')
    await expect(composer).toBeVisible()
    const box = await composer.boundingBox()
    const sheet = await page.locator('[data-slot="shell-sheet"]').boundingBox()
    expect(Math.abs(box!.width - 686)).toBeLessThanOrEqual(1)
    // The kit: 120 px padding, a 56 px greeting, a 36 px gap, and the sheet's 1 px border.
    expect(Math.abs(box!.y - sheet!.y - 213)).toBeLessThanOrEqual(1)
    expect(await scrollWidth(page)).toBeLessThanOrEqual(1440)
  })
})
