import { expect, test } from '@playwright/test'
import { startAs } from './helpers'

// At 1440 px the directory and a profile take the sheet's full width: the right rail belongs to
// the assistant home alone, so the toolbar fits one row and the profile's panels sit side by side.
test.use({ viewport: { width: 1440, height: 900 } })

test('the directory toolbar fits one row, with the sandbox indicator in the page header', async ({
  page,
}) => {
  await startAs(page, 'Marcus')
  await page.getByRole('link', { name: 'Directory' }).click()
  await expect(page.getByRole('list', { name: 'People' })).toBeVisible()
  await expect(page.getByRole('complementary', { name: 'Sandbox status' })).toHaveCount(0)

  const myTeam = page.getByRole('button', { name: /^My team/ })
  await myTeam.click()
  const clear = page.getByRole('button', { name: 'Clear filters' })
  await expect(clear).toBeVisible()
  const centers = await Promise.all(
    [
      page.getByRole('searchbox'),
      page.getByRole('combobox', { name: 'Department' }),
      myTeam,
      clear,
    ].map(async (control) => {
      const box = (await control.boundingBox())!
      return box.y + box.height / 2
    }),
  )
  for (const y of centers) expect(Math.abs(y - centers[0]!)).toBeLessThan(4)

  const header = page.locator('[data-slot="page-header"]')
  await expect(header.getByText(/^Sandbox resets in/)).toBeVisible()
})

test('a profile puts Work details and Private details side by side', async ({ page }) => {
  await startAs(page, 'Priya')
  await page.getByRole('link', { name: 'Directory' }).click()
  await page.getByRole('list', { name: 'People' }).getByRole('link').first().click()
  const work = page.getByRole('region', { name: 'Work details' })
  const priv = page.getByRole('region', { name: 'Private details' })
  await expect(work).toBeVisible()
  await expect(priv).toBeVisible()
  await expect(page.getByRole('complementary', { name: 'Sandbox status' })).toHaveCount(0)
  const [w, p] = [(await work.boundingBox())!, (await priv.boundingBox())!]
  expect(Math.abs(w.y - p.y)).toBeLessThan(4)
  expect(p.x).toBeGreaterThan(w.x + w.width - 1)
  await expect(
    page.locator('[data-slot="page-header"]').getByText(/^Sandbox resets in/),
  ).toBeVisible()
})
