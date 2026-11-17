import { readFileSync } from 'node:fs'
import type { Page } from '@playwright/test'
import type { Walkthrough } from '../src/features/walkthrough/types'
import { expect, test } from './fixtures'
import {
  askAndWaitForAnswer,
  BUDGET_DAILY_TEXT,
  BUDGET_SANDBOX_TEXT,
  QUESTIONS,
  stubConversation,
} from './conversation-helpers'
import { scan, startAs } from './helpers'

// Screen 16 (docs/design/screens/16-walkthrough/notes.md), against the real API with the scripted
// model. "Matches the screenshots at 1440 px" is the capture report's job (make captures).
// Chromium as Playwright ships it can't decode H.264, so no test presses play: the video's
// attributes, its file, and the server's range answers are checked instead.

const walkthrough = JSON.parse(
  readFileSync(new URL('../src/features/walkthrough/walkthrough.json', import.meta.url), 'utf8'),
) as Walkthrough

const HEADING = 'The recorded walkthrough'
const LINK = 'Watch the recorded walkthrough'
const VIDEO = '/media/walkthrough.mp4'
const POSTER = '/media/walkthrough-poster.jpg'

/**
 * An answer's lines as the page shows them: the recording keeps the model's Markdown, and the
 * page renders it, so list markers, heading marks, and emphasis are not in the page's text.
 */
const shownLines = (markdown: string) =>
  markdown
    .split('\n')
    .map((line) =>
      line
        .replace(/^\s*(?:[-*+]|\d+\.|#+)\s+/, '')
        .replaceAll(/\*\*|__|`/g, '')
        .trim(),
    )
    .filter(Boolean)

const heading = (page: Page) => page.getByRole('heading', { level: 1, name: HEADING })
const back = (page: Page) => page.getByRole('link', { name: 'Back to the demo' })

/** Priya's conversation with the day's limit reached (STUB: the conversation GET). */
async function atTheDailyLimit(page: Page, kind: 'daily' | 'sandbox' = 'daily') {
  await startAs(page, 'Priya')
  await askAndWaitForAnswer(page, QUESTIONS.cited)
  await stubConversation(page, (body) => {
    const reached = kind === 'sandbox' ? 'sandboxReached' : 'dailyReached'
    const message = kind === 'sandbox' ? BUDGET_SANDBOX_TEXT : BUDGET_DAILY_TEXT
    body.budget = { ...body.budget, [reached]: true, banner: { kind, message } }
  })
  await page.reload()
  const message = kind === 'sandbox' ? BUDGET_SANDBOX_TEXT : BUDGET_DAILY_TEXT
  const banner = page.locator('[data-slot="banner"]').filter({ hasText: message.slice(0, 40) })
  await expect(banner).toBeVisible()
  return banner
}

test.describe('the walkthrough page', () => {
  test('opens without a session, with no app navigation or persona', async ({ page }) => {
    await page.goto('/walkthrough')
    await expect(heading(page)).toBeVisible()
    await expect(page.getByRole('navigation')).toHaveCount(0)
    await expect(page.getByRole('button', { name: /Switch persona$/ })).toHaveCount(0)
    await expect(page).toHaveURL('/walkthrough')
  })

  test('the video: native controls, the poster, no autoplay, preload none, 16:10', async ({
    page,
  }) => {
    await page.goto('/walkthrough')
    const video = page.locator('video')
    await expect(video).toHaveAttribute('controls', '')
    await expect(video).toHaveAttribute('preload', 'none')
    await expect(video).toHaveAttribute('poster', POSTER)
    await expect(video).not.toHaveAttribute('autoplay')
    expect(await video.evaluate((v: HTMLVideoElement) => [v.paused, v.autoplay])).toEqual([
      true,
      false,
    ])
    const box = (await video.boundingBox())!
    expect(box.width / box.height).toBeCloseTo(1.6, 1)
    const column = (await page.locator('main').boundingBox())!
    expect(Math.abs(box.width - column.width)).toBeLessThanOrEqual(2)
  })

  test('downloads nothing but the poster until play is pressed', async ({ page }) => {
    const asked: string[] = []
    page.on('request', (request) => asked.push(new URL(request.url()).pathname))
    await page.goto('/walkthrough')
    await expect(heading(page)).toBeVisible()
    await page.waitForLoadState('networkidle')
    expect(asked).not.toContain(VIDEO)
    expect(asked).toContain(POSTER)
  })

  test('the transcript: every step in order, as recorded', async ({ page }) => {
    await page.goto('/walkthrough')
    const articles = page.getByRole('region', { name: 'Transcript' }).getByRole('article')
    await expect(articles).toHaveCount(walkthrough.steps.length)
    for (const [index, step] of walkthrough.steps.entries()) {
      const article = articles.nth(index)
      await expect(article).toHaveAttribute('id', `step-${index + 1}`)
      await expect(article.getByRole('heading', { level: 3 })).toHaveText(step.title)
      await expect(article).toContainText(step.words)
      for (const exchange of step.exchanges) {
        for (const line of shownLines(exchange.text)) await expect(article).toContainText(line)
      }
    }
  })

  test('a step can be linked by its id', async ({ page }) => {
    await page.goto('/walkthrough#step-7')
    await expect(page.locator('#step-7')).toBeInViewport()
  })

  test('Back to the demo goes to the landing when opened directly', async ({ page }) => {
    await page.goto('/walkthrough')
    await back(page).click()
    await expect(page).toHaveURL('/')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(
      'Your open-door policy, now always open.',
    )
  })

  test('has no axe violations at 1440 and 390 px', async ({ page }) => {
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 })
      await page.goto('/walkthrough')
      await expect(heading(page)).toBeVisible()
      expect((await scan(page)).violations, `at ${width} px`).toEqual([])
    }
  })

  test('at 390 px the exchange rows stack, the speaker above the words', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/walkthrough')
    const row = page.locator('#step-1 dl > div').first()
    const speaker = (await row.locator('dt').boundingBox())!
    const words = (await row.locator('dd').boundingBox())!
    expect(words.y).toBeGreaterThanOrEqual(speaker.y + speaker.height)
    expect(Math.abs(words.x - speaker.x)).toBeLessThanOrEqual(1)
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
    expect(scrollWidth).toBeLessThanOrEqual(390)
  })
})

test.describe('the video file', () => {
  test('is served with ranges: 206 for a piece, which Safari needs', async ({ request }) => {
    const whole = await request.get(VIDEO)
    expect(whole.status()).toBe(200)
    expect(whole.headers()['content-type']).toBe('video/mp4')
    const size = (await whole.body()).length
    const piece = await request.get(VIDEO, { headers: { Range: 'bytes=0-1023' } })
    expect(piece.status()).toBe(206)
    expect(piece.headers()['content-range']).toBe(`bytes 0-1023/${size}`)
    expect((await piece.body()).length).toBe(1024)
    // An MP4 file: its first box is `ftyp`.
    expect((await piece.body()).subarray(4, 8).toString('latin1')).toBe('ftyp')
  })

  test('the poster is a JPEG', async ({ request }) => {
    const poster = await request.get(POSTER)
    expect(poster.status()).toBe(200)
    expect(poster.headers()['content-type']).toBe('image/jpeg')
  })
})

test.describe('where the walkthrough is offered', () => {
  // The banner tests stub the conversation's GET, and the page can still be refetching it when a
  // test ends; a stub left fetching then fails the run outside any test.
  test.afterEach(async ({ page }) => {
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  test('the landing: the link left of the tour button and the Cloudflare line', async ({
    page,
  }) => {
    await page.goto('/')
    const link = page.getByRole('link', { name: LINK })
    const tour = page.getByRole('button', { name: 'Take the 2-minute tour' })
    const linkBox = (await link.boundingBox())!
    const tourBox = (await tour.boundingBox())!
    expect(linkBox.x + linkBox.width).toBeLessThan(tourBox.x)
    expect(
      Math.abs(linkBox.y + linkBox.height / 2 - (tourBox.y + tourBox.height / 2)),
    ).toBeLessThan(2)
    await expect(
      page.getByText('Starting a sandbox runs a quick Cloudflare check to keep the demo safe.'),
    ).toBeVisible()
    await link.click()
    await expect(heading(page)).toBeVisible()
    await back(page).click()
    await expect(page).toHaveURL('/')
  })

  test('at 390 px the landing’s row stacks: the notes, then the link and the button', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/')
    const check = (await page
      .getByText('Starting a sandbox runs a quick Cloudflare check to keep the demo safe.')
      .boundingBox())!
    const link = (await page.getByRole('link', { name: LINK }).boundingBox())!
    expect(link.y).toBeGreaterThan(check.y + check.height)
    expect(Math.abs(link.x - check.x)).toBeLessThanOrEqual(1)
  })

  test('the daily-limit banner links it, and Back returns to the conversation (STUB: GET)', async ({
    page,
  }) => {
    const banner = await atTheDailyLimit(page)
    const before = new URL(page.url())
    await banner.getByRole('link', { name: LINK }).click()
    await expect(heading(page)).toBeVisible()
    await back(page).click()
    await expect(page).toHaveURL(`${before.pathname}${before.search}`)
    await expect(page.locator('[data-slot="banner"]').filter({ hasText: LINK })).toBeVisible()
  })

  test('the sandbox-limit banner doesn’t (STUB: GET)', async ({ page }) => {
    const banner = await atTheDailyLimit(page, 'sandbox')
    await expect(banner.getByRole('link', { name: LINK })).toHaveCount(0)
  })

  test('the daily banner with its link has no axe violations (STUB: GET)', async ({ page }) => {
    await atTheDailyLimit(page)
    expect((await scan(page)).violations).toEqual([])
  })
})
