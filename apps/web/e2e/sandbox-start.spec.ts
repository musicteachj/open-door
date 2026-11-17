import type { Page } from '@playwright/test'
import { expect, setTurnstile, test, turnstileScriptRequests } from './fixtures'
import { askAndWaitForAnswer, QUESTIONS, stubConversation } from './conversation-helpers'
import { scan, startAs } from './helpers'

// Starting a sandbox: the Turnstile check and the four refusals the API can make before it starts one
// (apps/api/app/modules/sandbox/texts.py). The page gets its Turnstile script from a local fake
// (fixtures.ts), so nothing here reaches Cloudflare. The real widget's iframe is not run: the live
// check through the production image covers it (Phase 8, Stage 9).

// The API's texts, written out here so a change to a word fails here. The web app holds no copy.
const TEXTS = {
  'turnstile-failed': "We couldn't confirm you're a person. Please try again.",
  'turnstile-unavailable':
    "We couldn't reach the check that keeps this demo safe. Please try again in a minute.",
  'sandbox-start-limit':
    "You've started several sandboxes in a short time. Please try again in 12 minutes, or keep using the one you have.",
  'sandbox-day-limit':
    'Open Door has started as many sandboxes as it can today. Please come back tomorrow, or watch the recorded walkthrough.',
} as const
type Refusal = keyof typeof TEXTS
const STATUS: Record<Refusal, number> = {
  'turnstile-failed': 403,
  'turnstile-unavailable': 503,
  'sandbox-start-limit': 429,
  'sandbox-day-limit': 429,
}
const RETRY: Record<Refusal, boolean> = {
  'turnstile-failed': true,
  'turnstile-unavailable': true,
  'sandbox-start-limit': false,
  'sandbox-day-limit': false,
}
const REFUSALS = Object.keys(TEXTS) as Refusal[]

const priya = (page: Page) => page.getByRole('button', { name: /^Priya / })
const retryButton = (page: Page) => page.getByRole('button', { name: 'Retry' })

/** Answers the next start with the API's problem for `type`, as the API words it. */
async function refuseStart(page: Page, type: Refusal) {
  await page.route('**/api/v1/sandboxes', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({
          status: STATUS[type],
          contentType: 'application/problem+json',
          body: JSON.stringify({
            type,
            title: 'Refused',
            status: STATUS[type],
            instance: '/api/v1/sandboxes',
            detail: TEXTS[type],
          }),
        })
      : route.fallback(),
  )
}

async function gotoLanding(page: Page) {
  await page.goto('/')
  await expect(priya(page)).toBeVisible()
}

test('a normal start gets a token and opens the assistant', async ({ page }) => {
  await gotoLanding(page)
  await priya(page).click()
  await expect(page).toHaveURL('/ask')
})

test('the Turnstile script is requested only after a start is pressed, and once', async ({
  page,
  context,
}) => {
  const requests: string[] = []
  page.on('request', (request) => {
    if (request.url().startsWith('https://challenges.cloudflare.com/')) {
      requests.push(request.url())
    }
  })
  await gotoLanding(page)
  // Let anything the page loads on its own come in.
  await page.waitForLoadState('networkidle')
  expect(turnstileScriptRequests(context)).toBe(0)
  expect(requests).toEqual([])

  await priya(page).click()
  await expect(page).toHaveURL('/ask')
  expect(requests).toEqual([
    'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit',
  ])
  expect(turnstileScriptRequests(context)).toBe(1)
})

test('a check that fails shows the API text with Retry, and Retry starts the sandbox', async ({
  page,
}) => {
  await gotoLanding(page)
  // The fake widget answers with an error, as the always-fail test key does; the app sends no
  // token and the real API refuses it.
  await setTurnstile(page, { fail: true })
  await priya(page).click()
  const alert = page.getByRole('alert')
  await expect(alert).toContainText(TEXTS['turnstile-failed'])
  await expect(alert).not.toContainText("We couldn't start a sandbox.")

  await setTurnstile(page, {})
  await retryButton(page).click()
  await expect(page).toHaveURL('/ask')
})

test.describe('each refusal, on the landing page', () => {
  for (const type of REFUSALS) {
    test(`${type} shows its text${RETRY[type] ? ' with Retry' : ' and no Retry'}`, async ({
      page,
    }) => {
      await gotoLanding(page)
      await refuseStart(page, type)
      await priya(page).click()
      const alert = page.getByRole('alert')
      await expect(alert).toHaveText(new RegExp(TEXTS[type].slice(0, 30)))
      await expect(alert).toContainText(TEXTS[type])
      await expect(retryButton(page)).toHaveCount(RETRY[type] ? 1 : 0)
      // The card is usable again, and the visitor is still on the landing page.
      await expect(priya(page)).toBeEnabled()
      await expect(page).toHaveURL('/')
    })
  }

  test('the tour button shows a refusal too', async ({ page }) => {
    await gotoLanding(page)
    await refuseStart(page, 'sandbox-day-limit')
    await page.getByRole('button', { name: 'Take the 2-minute tour' }).click()
    await expect(page.getByRole('alert')).toContainText(TEXTS['sandbox-day-limit'])
    await expect(retryButton(page)).toHaveCount(0)
  })
})

test.describe("each refusal, from the budget banner's Start a new sandbox", () => {
  for (const type of REFUSALS) {
    test(`${type} shows its text${RETRY[type] ? ' with Retry' : ' and no Retry'}`, async ({
      page,
    }) => {
      await startAs(page, 'Priya')
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      await stubConversation(page, (body) => {
        body.budget = {
          ...body.budget,
          sandboxReached: true,
          banner: { kind: 'sandbox', message: 'This sandbox has used its assistant budget.' },
        }
      })
      await page.reload()
      await refuseStart(page, type)
      await page.getByRole('button', { name: 'Start a new sandbox' }).click()
      const alert = page.getByRole('alert').filter({ hasText: TEXTS[type].slice(0, 30) })
      await expect(alert).toContainText(TEXTS[type])
      await expect(alert.getByRole('button', { name: 'Retry' })).toHaveCount(RETRY[type] ? 1 : 0)
    })
  }
})

test('the check goes in the empty place directly under the pressed card, and nothing moves while it is empty', async ({
  page,
}) => {
  await gotoLanding(page)
  // Measured from the top of the page, since pressing a card may scroll it into view.
  const pageTop = (target: ReturnType<typeof priya>) =>
    target.evaluate((el) => el.getBoundingClientRect().top + window.scrollY)
  const before = await pageTop(priya(page))
  const cards = await page
    .locator('[data-slot="turnstile-slot"]')
    .evaluateAll((els) => els.map((el) => el.getBoundingClientRect().height))
  // One empty place per card and one under the tour button: none takes any room.
  expect(cards).toEqual([0, 0, 0, 0, 0])

  // The fake draws a stand-in box where Cloudflare's checkbox would be, and never answers.
  await setTurnstile(page, { standIn: true, hold: true })
  await priya(page).click()
  const box = page.locator('[data-fake-turnstile]')
  await expect(box).toBeVisible()
  const cardBox = await priya(page).boundingBox()
  const stand = await box.boundingBox()
  expect(await pageTop(priya(page))).toBeCloseTo(before, 0)
  // Directly below the card, left-aligned with it.
  expect(stand!.y).toBeGreaterThanOrEqual(cardBox!.y + cardBox!.height)
  expect(stand!.y - (cardBox!.y + cardBox!.height)).toBeLessThan(24)
  expect(stand!.x).toBeCloseTo(cardBox!.x, 0)
})

for (const width of [1440, 390]) {
  test(`axe is clean at ${width} px with a refusal, and with the check showing`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 })
    await gotoLanding(page)

    await setTurnstile(page, { standIn: true, hold: true })
    await priya(page).click()
    await expect(page.locator('[data-fake-turnstile]')).toBeVisible()
    expect((await scan(page)).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )

    await page.reload()
    await expect(priya(page)).toBeVisible()
    await refuseStart(page, 'sandbox-start-limit')
    await priya(page).click()
    await expect(page.getByRole('alert')).toContainText(TEXTS['sandbox-start-limit'])
    expect((await scan(page)).violations).toEqual([])
    await refuseStart(page, 'turnstile-failed')
    await expect(priya(page)).toBeEnabled()
    await priya(page).click()
    await expect(retryButton(page)).toBeVisible()
    expect((await scan(page)).violations).toEqual([])
  })
}
