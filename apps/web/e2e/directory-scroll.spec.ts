import { expect, test } from '@playwright/test'
import { startAs } from './helpers'

// jsdom has no layout, so scroll position can only be proved in a browser. The page (the window)
// is what scrolls: the shell's sheet grows with its content. useScrollRestoration (in Root) restores
// the window on Back, keyed by location.key. A filter change takes the same path as opening a
// profile (a push), and is covered by the unit test; a filter menu can't be opened with its
// trigger scrolled out of view.
test('Back from a profile returns to where the list was scrolled', async ({ page }) => {
  await startAs(page, 'Priya')
  await page.getByRole('link', { name: 'Directory' }).click()
  const list = page.getByRole('list', { name: 'People' })
  await expect(list).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 500))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(500)

  // A row in view, so the click does not scroll.
  await list.getByRole('listitem').nth(12).getByRole('link').click()
  await expect(page).toHaveURL(/\/directory\/.+/)
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)

  await page.goBack()
  await expect(page).toHaveURL(/\/directory$/)
  await expect(list.getByRole('listitem')).toHaveCount(50)
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(500)
})

test('a search keeps the scroll position while it replaces the URL', async ({ page }) => {
  await startAs(page, 'Priya')
  await page.getByRole('link', { name: 'Directory' }).click()
  await expect(page.getByRole('list', { name: 'People' })).toBeVisible()
  await page.getByRole('searchbox').focus()
  await page.evaluate(() => window.scrollTo(0, 80))
  await page.keyboard.type('a')
  await expect(page).toHaveURL(/\?q=a$/)
  await expect(page.getByText(/ of 145 people$/)).toBeVisible()
  expect(await page.evaluate(() => window.scrollY)).toBe(80)
})
