import { expect, test } from './fixtures'
import { openDirectory, openProfileBySearch } from './directory-helpers'
import { greetingHeading, signOut, startAs, switchTo } from './helpers'

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
  await expect(page.getByRole('button', { name: /^Priya / })).toBeVisible()

  // Signed out, an app route sends the visitor back to the landing page.
  await page.goto('/ask')
  await expect(page).toHaveURL('/')
})

// All the tabs of one browser share the session cookie, so a change in one leaves the others
// showing a person who is no longer signed in. Each test waits for the other tab to notice with
// no click, focus, or reload: the BroadcastChannel message refetches /me.

test('signing out in one tab ends HR’s open private details in the other, with no click', async ({
  page,
}) => {
  await openDirectory(page, 'Dana')
  await openProfileBySearch(page, 'Nakamura', /^Leo Nakamura/)
  const privateDetails = page.getByRole('region', { name: 'Private details' })
  await expect(privateDetails.getByText('Home address')).toBeVisible()
  await expect(privateDetails.getByText('Visible to Leo and HR')).toHaveCount(0)

  // A second tab in the same browser, signed in as the same Dana through the shared cookies.
  const second = await page.context().newPage()
  await second.goto('/ask')
  await expect(greetingHeading(second, 'Dana')).toBeVisible()
  await signOut(second)
  await expect(second).toHaveURL('/')

  // The first tab was never touched. It resets on its own: HR's view of Leo is gone.
  await expect(page.getByRole('heading', { name: 'This sandbox has reset.' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Private details' })).toHaveCount(0)
  await expect(page.getByText('Home address')).toHaveCount(0)
  await second.close()
})

test('switching persona in one tab resets the other to the new person, with no click', async ({
  page,
}) => {
  await startAs(page, 'Dana')
  await expect(greetingHeading(page, 'Dana')).toBeVisible()

  const second = await page.context().newPage()
  await second.goto('/ask')
  await expect(greetingHeading(second, 'Dana')).toBeVisible()
  await switchTo(second, 'Marcus')
  await expect(greetingHeading(second, 'Marcus')).toBeVisible()

  await expect(greetingHeading(page, 'Marcus')).toBeVisible()
  await expect(greetingHeading(page, 'Dana')).toHaveCount(0)
  await second.close()
})
