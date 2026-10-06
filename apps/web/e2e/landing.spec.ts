import { expect, test, type Page } from '@playwright/test'
import { PERSONAS } from '../src/features/personas/personas'
import {
  focusRing,
  greetingHeading,
  holdRequests,
  problem,
  scan,
  themeColor,
  type FirstName,
} from './helpers'

// One test per acceptance criterion in docs/design/screens/01-landing/notes.md. "Matches the
// screenshots at 1440 px" is the capture report's job (make captures), not a test's.

// The cards' names, written out from the notes' Copy section rather than built by the app's own
// function, so a change to the wording fails here.
const CARD_NAMES: Record<FirstName, string> = {
  Priya:
    'Start a sandbox as Priya Raman, Visual Merchandiser, Oakland store. Ask about California sick leave and book a day off.',
  Mateo:
    'Start a sandbox as Mateo Alvarez, Warehouse Associate, Austin warehouse. Ask the same questions and get Texas answers.',
  Marcus:
    'Start a sandbox as Marcus Bell, Store Manager, Oakland store. Approve a request and check on your team.',
  Dana: 'Start a sandbox as Dana Whitfield, HR Business Partner, Denver HQ. See the confidential case queue.',
}
const FIRST_NAMES = Object.keys(CARD_NAMES) as FirstName[]

const card = (page: Page, name: FirstName) =>
  page.getByRole('button', { name: CARD_NAMES[name], exact: true })
const startError = (page: Page) => page.getByText("We couldn't start a sandbox.")
const AI_DISCLOSURE =
  'Open Door is an AI assistant. It can make mistakes, and it always shows its sources.'
const NOTICE =
  "Juniper Row and everyone in it are fictional. This is a demo, not legal advice. Don't enter real personal information."

test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Your open-door policy, now always open.' }),
  ).toBeVisible()
})

test('usable at 390 px: the cards stack, and nothing overflows', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const boxes = await Promise.all(FIRST_NAMES.map((name) => card(page, name).boundingBox()))
  for (let i = 1; i < boxes.length; i += 1) {
    // One column: each card starts below the one before it, at the same left edge.
    expect(boxes[i]!.y).toBeGreaterThanOrEqual(boxes[i - 1]!.y + boxes[i - 1]!.height)
    expect(boxes[i]!.x).toBeCloseTo(boxes[0]!.x, 0)
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})

test('each persona card is a single button with the accessible name above, reachable by keyboard and showing the focus ring', async ({
  page,
}) => {
  // Four buttons and nothing else to tab to (the tour and "How it's built" are hidden until Phase 7).
  await expect(page.getByRole('button')).toHaveCount(4)
  await expect(page.getByRole('link')).toHaveCount(0)
  for (const name of FIRST_NAMES) {
    await page.keyboard.press('Tab')
    await expect(card(page, name)).toBeFocused()
    // The ring is a :focus-visible outline: 2 px, offset 2 px, in the focus-ring color.
    expect(await focusRing(page)).toEqual({ width: '2px', style: 'solid', offset: '2px' })
    // Polled: a color transition on the card would otherwise be read mid-fade.
    const ring = await themeColor(page, 'focus-ring')
    await expect
      .poll(() => card(page, name).evaluate((el) => getComputedStyle(el).outlineColor))
      .toBe(ring)
    // Its visible text is the whole card, and it holds no other control.
    await expect(card(page, name).locator('a, button, input')).toHaveCount(0)
    await expect(card(page, name)).toContainText(`Start as ${name}`)
  }
})

for (const persona of PERSONAS) {
  test(`selecting ${persona.firstName}'s card starts that persona's sandbox and lands on the assistant home, and /me agrees with the personas constant`, async ({
    page,
  }) => {
    const created = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === '/api/v1/sandboxes',
    )
    await card(page, persona.firstName as FirstName).click()
    expect((await created).status()).toBe(201)
    await expect(page).toHaveURL('/ask')
    await expect(greetingHeading(page, persona.firstName as FirstName)).toBeVisible()

    const me = await page.evaluate(async () => {
      const response = await fetch('/api/v1/me')
      return (await response.json()) as {
        givenName: string
        familyName: string
        title: string
        personaKey: string
        location: { name: string }
      }
    })
    expect(`${me.givenName} ${me.familyName}`).toBe(persona.name)
    expect(me.title).toBe(persona.title)
    expect(me.location.name).toBe(persona.location)
    expect(me.personaKey).toBe(persona.key)
  })
}

test('while starting, the card is busy and announced, and the other cards are disabled', async ({
  page,
}) => {
  const release = await holdRequests(page, '**/api/v1/sandboxes', 'POST')
  try {
    await card(page, 'Priya').click()
    await expect(card(page, 'Priya')).toHaveAttribute('aria-busy', 'true')
    // Announced: a polite live region (<output>) says it, and the card shows it too.
    await expect(page.locator('output', { hasText: 'Setting up Juniper Row…' })).toHaveCount(1)
    await expect(card(page, 'Priya')).toContainText('Setting up Juniper Row…')
    for (const other of ['Mateo', 'Marcus', 'Dana'] as const) {
      await expect(card(page, other)).toBeDisabled()
    }
    await expect(card(page, 'Priya')).toBeEnabled()
    // axe on the starting state.
    expect((await scan(page)).violations).toEqual([])
  } finally {
    release()
  }
  await expect(page).toHaveURL('/ask')
})

test('a second click on the starting card does not start a second sandbox', async ({ page }) => {
  let posts = 0
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/v1/sandboxes')) posts += 1
  })
  const release = await holdRequests(page, '**/api/v1/sandboxes', 'POST')
  try {
    await card(page, 'Priya').click()
    await expect(card(page, 'Priya')).toHaveAttribute('aria-busy', 'true')
    await card(page, 'Priya').click({ force: true })
  } finally {
    release()
  }
  await expect(page).toHaveURL('/ask')
  expect(posts).toBe(1)
})

test('a failed start re-enables the cards and shows the inline error with a working Retry', async ({
  page,
}) => {
  let attempts = 0
  const bodies: string[] = []
  await page.route('**/api/v1/sandboxes', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    attempts += 1
    bodies.push(route.request().postData() ?? '')
    if (attempts === 1) {
      return route.fulfill({
        status: 500,
        contentType: 'application/problem+json',
        body: problem(500, 'Internal Server Error'),
      })
    }
    return route.continue()
  })

  await card(page, 'Mateo').click()
  const error = page.getByRole('alert')
  await expect(error).toContainText("We couldn't start a sandbox.")
  for (const name of FIRST_NAMES) {
    await expect(card(page, name)).toBeEnabled()
    await expect(card(page, name)).not.toHaveAttribute('aria-busy')
  }
  expect((await scan(page)).violations).toEqual([])

  // Retry starts the same persona again, not the first card.
  await error.getByRole('button', { name: 'Retry' }).click()
  await expect(page).toHaveURL('/ask')
  await expect(greetingHeading(page, 'Mateo')).toBeVisible()
  expect(attempts).toBe(2)
  expect(JSON.parse(bodies[1]!)).toEqual({ persona: 'mateo' })
})

test('the AI disclosure and the fictional-company notice are always visible', async ({ page }) => {
  const visible = async () => {
    await expect(page.getByText(AI_DISCLOSURE)).toBeVisible()
    await expect(page.getByText(NOTICE)).toBeVisible()
  }
  await visible()
  // While starting, and after a failure: one route that waits, then fails.
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/v1/sandboxes', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    await gate
    return route.fulfill({
      status: 500,
      contentType: 'application/problem+json',
      body: problem(500, 'Internal Server Error'),
    })
  })
  await card(page, 'Priya').click()
  await expect(card(page, 'Priya')).toHaveAttribute('aria-busy', 'true')
  await visible()
  release()
  await expect(startError(page)).toBeVisible()
  await visible()
  // And on a narrow screen.
  await page.setViewportSize({ width: 390, height: 844 })
  await visible()
})

test('the spinner stops under prefers-reduced-motion', async ({ page }) => {
  const release = await holdRequests(page, '**/api/v1/sandboxes', 'POST')
  try {
    await card(page, 'Priya').click()
    const spinner = card(page, 'Priya').locator('svg.animate-spin')
    await expect(spinner).toBeVisible()
    const running = () => spinner.evaluate((el) => el.getAnimations().length)
    // Control: with motion allowed, the spinner really turns, so the check below can fail.
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    expect(await running()).toBeGreaterThan(0)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    expect(await running()).toBe(0)
    await expect(spinner).toHaveCSS('animation-name', 'none')
  } finally {
    release()
  }
})

test('axe reports no violations on the default and the hover and focus states', async ({
  page,
}) => {
  expect((await scan(page)).violations).toEqual([])
  await card(page, 'Priya').hover()
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await expect(card(page, 'Mateo')).toBeFocused()
  expect((await scan(page)).violations).toEqual([])
})
