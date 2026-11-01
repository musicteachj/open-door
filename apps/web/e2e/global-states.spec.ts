import { expect, test, type Page } from '@playwright/test'
import { problem, scan, startAs } from './helpers'

// One test per acceptance criterion in docs/design/screens/05-global-states/notes.md. "Matches the
// screenshots at 1440 px" is the capture report's job (make captures).
//
// Phase 2 has no signed-in page that loads data, so the in-shell "Something went wrong" (a page's
// failed query reaching the route's error boundary) can't be reached from a browser yet. The
// unit tests in global-states.test.tsx prove it, and Stage 6's directory adds the browser test.
// What a browser can reach is the same page outside the shell, when the first /me fails.

const REQUEST_ID = '0123456789abcdef0123456789abcdef'
const WRONG = 'Something went wrong on our side.'

/**
 * Answers every /me from now on with a 401, as after the sandbox's 24 hours, and makes the browser
 * ask again, as it does when the tab comes back into view. A /me already in flight takes the first
 * nudge, so the nudge repeats until the page has seen the 401.
 */
async function expireSession(page: Page) {
  await page.route('**/api/v1/me', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/problem+json',
      body: problem(401, 'Unauthorized'),
    }),
  )
  await expect(async () => {
    await page.evaluate(() => window.dispatchEvent(new Event('visibilitychange')))
    await expect(heading(page, 'This sandbox has reset.')).toBeVisible({ timeout: 500 })
  }).toPass()
}

/** Answers /me with a 500 carrying a request ID, counting the requests. */
async function failMe(page: Page) {
  const seen = { requests: 0 }
  await page.route('**/api/v1/me', (route) => {
    seen.requests += 1
    return route.fulfill({
      status: 500,
      contentType: 'application/problem+json',
      headers: { 'X-Request-ID': REQUEST_ID },
      body: problem(500, 'Internal Server Error'),
    })
  })
  return seen
}

const heading = (page: Page, name: string) => page.getByRole('heading', { level: 1, name })

test.describe('a 401 shows session expired outside the shell, and its button reaches the landing page', () => {
  test('outside the shell, with the title as the one h1, focused, and no axe violations', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await expireSession(page)

    await expect(heading(page, 'This sandbox has reset.')).toBeFocused()
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    await expect(
      page.getByText('Sandboxes last 24 hours. Start a new one to keep exploring.'),
    ).toBeVisible()
    // Outside the shell: only the logo, with no navigation, sidebar, or switcher.
    await expect(page.getByText('Open Door', { exact: true })).toBeVisible()
    await expect(page.getByRole('navigation')).toHaveCount(0)
    await expect(page.getByRole('complementary')).toHaveCount(0)
    await expect(page.getByRole('button', { name: /Switch persona$/ })).toHaveCount(0)
    expect((await scan(page)).violations).toEqual([])
  })

  test('matches the design outside the shell at 1440 px: the logo at the landing inset in a 72 px header, and an arrow after the button label', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await startAs(page, 'Priya')
    await expireSession(page)
    const logo = (await page.locator('[data-slot="logo"]').boundingBox())!
    // 05's frame: padding 0 136px (the landing page's inset), and a 72 px header.
    expect(Math.abs(logo.x - 136)).toBeLessThanOrEqual(2)
    const header = (await page.locator('[data-slot="full-page-message"] header').boundingBox())!
    expect(header.height).toBe(72)
    const button = page.getByRole('button', { name: 'Choose who to be' })
    const icon = button.locator('svg')
    await expect(icon).toHaveCount(1)
    await expect(icon).toHaveAttribute('aria-hidden', 'true')
    const [labelBox, iconBox] = await Promise.all([
      button.evaluate((el) => {
        const range = document.createRange()
        range.selectNodeContents(el.lastChild === el.querySelector('svg') ? el.firstChild! : el)
        return range.getBoundingClientRect().right
      }),
      icon.boundingBox(),
    ])
    expect(iconBox!.x).toBeGreaterThanOrEqual(labelBox - 1)
  })

  test('"Choose who to be" goes to the landing page', async ({ page }) => {
    await startAs(page, 'Priya')
    await expireSession(page)
    await page.getByRole('button', { name: 'Choose who to be' }).click()
    await expect(page).toHaveURL('/')
    await expect(page.getByRole('button', { name: /^Priya / })).toBeVisible()
  })
})

test.describe('an unknown route shows not found inside the shell, with no nav item current', () => {
  test('inside the shell, with the title as the one h1, focused, and no axe violations', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await page.goto('/no/such/page')

    await expect(heading(page, "We couldn't find that page.")).toBeFocused()
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    // Inside the shell: the navigation and the switcher are still there, and the sheet holds the
    // page's one <main>.
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Switch persona$/ })).toBeVisible()
    await expect(page.getByRole('main')).toContainText("We couldn't find that page.")
    // No nav item is marked current, and none carries the tint.
    await expect(page.locator('[data-slot="nav-item"][aria-current]')).toHaveCount(0)
    const tint = await page.evaluate(() => {
      const probe = document.createElement('div')
      probe.style.color = 'var(--color-primary-tint)'
      document.body.append(probe)
      const color = getComputedStyle(probe).color
      probe.remove()
      return color
    })
    for (const link of await page
      .getByRole('navigation', { name: 'Main' })
      .getByRole('link')
      .all()) {
      expect(await link.evaluate((el) => getComputedStyle(el).backgroundColor)).not.toBe(tint)
    }
    expect((await scan(page)).violations).toEqual([])
  })

  test('"Go to Ask" goes to the assistant home', async ({ page }) => {
    await startAs(page, 'Priya')
    await page.goto('/no/such/page')
    await page.getByRole('link', { name: 'Go to Ask' }).click()
    await expect(page).toHaveURL('/ask')
    await expect(page.getByRole('link', { name: 'Ask', exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })
})

test.describe('an unexpected API failure shows the full request ID from X-Request-ID, and Retry repeats the failed request', () => {
  test('the full 32-character reference, selected with one click, and Retry asks again', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    const seen = await failMe(page)
    await page.goto('/ask')

    await expect(heading(page, WRONG)).toBeFocused()
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    await expect(
      page.getByText(
        'Try again in a moment. If it keeps happening, this reference helps us find it:',
      ),
    ).toBeVisible()
    const reference = page.locator('[data-slot="full-page-message"] code')
    await expect(reference).toHaveText(REQUEST_ID)
    expect(await reference.evaluate((el) => getComputedStyle(el).fontFamily)).toContain(
      'Geist Mono',
    )
    expect((await scan(page)).violations).toEqual([])

    // One click selects the whole reference, ready to copy.
    await reference.click()
    expect(await page.evaluate(() => window.getSelection()?.toString())).toBe(REQUEST_ID)

    // Retry repeats /me, the request that failed. Still failing, it asks again and shows the page.
    const before = seen.requests
    await page.getByRole('button', { name: 'Retry' }).click()
    await expect.poll(() => seen.requests).toBeGreaterThan(before)
    // The request fails again (after its one automatic retry), and the page comes back.
    await expect(heading(page, WRONG)).toBeFocused()
    await expect(reference).toHaveText(REQUEST_ID)

    // Once the API answers, Retry gets through to the page the visitor asked for.
    await page.unroute('**/api/v1/me')
    await page.getByRole('button', { name: 'Retry' }).click()
    await expect(
      page.getByRole('heading', { level: 1, name: /^Good (morning|afternoon|evening), Priya\.$/ }),
    ).toBeVisible()
  })
})

test("if the shell can't load, the error page renders outside it", async ({ page }) => {
  await startAs(page, 'Priya')
  await failMe(page)
  await page.goto('/ask')
  await expect(heading(page, WRONG)).toBeVisible()
  await expect(page.getByText('Open Door', { exact: true })).toBeVisible()
  await expect(page.getByRole('navigation')).toHaveCount(0)
  await expect(page.getByRole('complementary')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Switch persona$/ })).toHaveCount(0)
  // The page fills the window, as a message with no shell around it does.
  const message = await page.locator('[data-slot="full-page-message"]').boundingBox()
  const viewport = page.viewportSize()!
  expect(message!.height).toBeGreaterThanOrEqual(viewport.height - 2)
})

test('a network failure shows the error page without a reference', async ({ page }) => {
  await startAs(page, 'Priya')
  await page.route('**/api/v1/me', (route) => route.abort('connectionrefused'))
  await page.goto('/ask')
  await expect(heading(page, WRONG)).toBeFocused()
  await expect(page.getByText('Try again in a moment.', { exact: true })).toBeVisible()
  await expect(page.getByText('Reference')).toHaveCount(0)
  expect((await scan(page)).violations).toEqual([])
})
