import { expect, test } from '@playwright/test'
import { startAs } from './helpers'

test('a visitor starts as Priya, switches to Marcus, and signs out', async ({ page }) => {
  await startAs(page, 'Priya')
  await expect(page.getByText('Signed in as Priya Raman')).toBeVisible()

  // Switching changes state, so it only succeeds if the browser sent the CSRF token from the
  // __Host- cookies (the server answers 403 without it).
  const switched = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      new URL(response.url()).pathname === '/api/v1/session/persona',
  )
  await page.getByRole('button', { name: 'Switch to Marcus' }).click()
  expect((await switched).status()).toBe(200)
  await expect(page.getByText('Signed in as Marcus Bell')).toBeVisible()
  await expect(page.getByText('Signed in as Priya Raman')).toHaveCount(0)

  // The session lives in cookies, so it survives a reload as the same person.
  await page.reload()
  await expect(page.getByText('Signed in as Marcus Bell')).toBeVisible()

  const ended = page.waitForResponse(
    (response) =>
      response.request().method() === 'DELETE' &&
      new URL(response.url()).pathname === '/api/v1/session',
  )
  await page.getByRole('button', { name: 'Sign out' }).click()
  expect((await ended).status()).toBe(204)
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('button', { name: 'Start as Priya' })).toBeVisible()

  // Signed out, an app route sends the visitor back to the landing page.
  await page.goto('/ask')
  await expect(page).toHaveURL('/')
})
