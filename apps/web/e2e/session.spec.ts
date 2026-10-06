import { expect, test } from '@playwright/test'
import { signOut, startAs, switchTo } from './helpers'

test('a visitor starts as Priya, switches to Marcus, and signs out', async ({ page }) => {
  await startAs(page, 'Priya')
  await expect(
    page.getByRole('heading', { level: 1, name: /^Good (morning|afternoon|evening), Priya\.$/ }),
  ).toBeVisible()

  // Switching changes state, so it only succeeds if the browser sent the CSRF token from the
  // __Host- cookies (the server answers 403 without it).
  const switched = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      new URL(response.url()).pathname === '/api/v1/session/persona',
  )
  await switchTo(page, 'Marcus')
  expect((await switched).status()).toBe(200)
  await expect(
    page.getByRole('heading', { level: 1, name: /^Good (morning|afternoon|evening), Marcus\.$/ }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { level: 1, name: /^Good (morning|afternoon|evening), Priya\.$/ }),
  ).toHaveCount(0)
  await expect(page.getByText('Now viewing as Marcus Bell.').first()).toBeVisible()

  // The session lives in cookies, so it survives a reload as the same person.
  await page.reload()
  await expect(
    page.getByRole('heading', { level: 1, name: /^Good (morning|afternoon|evening), Marcus\.$/ }),
  ).toBeVisible()

  const ended = page.waitForResponse(
    (response) =>
      response.request().method() === 'DELETE' &&
      new URL(response.url()).pathname === '/api/v1/session',
  )
  await signOut(page)
  expect((await ended).status()).toBe(204)
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('button', { name: /^Start a sandbox as Priya / })).toBeVisible()

  // Signed out, an app route sends the visitor back to the landing page.
  await page.goto('/ask')
  await expect(page).toHaveURL('/')
})
