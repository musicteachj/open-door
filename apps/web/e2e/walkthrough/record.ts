import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test, type Locator, type Page } from '@playwright/test'
import { TOUR_END_SUMMARY } from '../../src/components/tour/end-card-copy'
import { TOUR, type TourStep } from '../../src/features/tour/script'
import type { Walkthrough, WalkthroughStep } from '../../src/features/walkthrough/types'
import { modelDisplayName } from '../../src/lib/models'
import { watchCsp } from '../fixtures'
import { exchangesOf, holdMs, localIsoDate, NOTES, summaryNote, type RecordedTurn } from './build'

// The recording (Phase 8, Task 45): the guided tour's own steps, at a reading pace, with a cursor
// that moves like a person's, recorded at 1440 by 900. It writes, into WALKTHROUGH_OUT:
//   raw.webm          the video, for scripts/walkthrough/encode.sh
//   poster.png        a frame for the poster: step 3's confirm card, with nothing important at the center
//   walkthrough.json  the transcript, from the API's stored turns (what the page showed)
//   take.json         where the tour starts in the video, and any CSP violation seen
// It fails, and the take is not used, if the model doesn't do what a step needs (no card, no HR
// panel). Run only through scripts/walkthrough/record.py, which starts the image and caps the cost.

const OUT = process.env.WALKTHROUGH_OUT ?? '/tmp/od-walkthrough/take'
const MODEL_ID = process.env.WALKTHROUGH_MODEL_ID ?? 'scripted'
const ANSWER_HOLD_MAX_MS = 5000
const TURN_TIMEOUT_MS = 120_000
const HARASSMENT = 'Harassment or discrimination'

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const mark = (page: Page, step: TourStep) =>
  page.getByRole('dialog', { name: new RegExp(escapeRegExp(step.title)) })
const nextButton = (page: Page, step: TourStep) =>
  mark(page, step).getByRole('button', { name: 'Next', exact: true })
const pause = (page: Page, ms: number) => page.waitForTimeout(ms)

/** A visible cursor: the headless browser's video has none. Drawn through the CSSOM, which the
 * page's Content Security Policy allows (no style attribute, no style element). */
function drawCursor() {
  const place = () => {
    if (document.getElementById('od-recording-cursor')) return
    const dot = document.createElement('div')
    dot.id = 'od-recording-cursor'
    Object.assign(dot.style, {
      position: 'fixed',
      left: '0px',
      top: '0px',
      width: '18px',
      height: '18px',
      marginLeft: '-9px',
      marginTop: '-9px',
      borderRadius: '9999px',
      background: 'rgba(23, 27, 31, 0.55)',
      border: '2px solid rgba(255, 255, 255, 0.95)',
      boxShadow: '0 1px 4px rgba(0, 0, 0, 0.35)',
      pointerEvents: 'none',
      zIndex: '2147483647',
      transition: 'transform 120ms ease-out',
    })
    document.documentElement.append(dot)
    document.addEventListener(
      'mousemove',
      (event) => {
        dot.style.left = `${event.clientX}px`
        dot.style.top = `${event.clientY}px`
      },
      { capture: true, passive: true },
    )
    document.addEventListener('mousedown', () => (dot.style.transform = 'scale(0.75)'), true)
    document.addEventListener('mouseup', () => (dot.style.transform = 'scale(1)'), true)
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', place)
  else place()
}

let mouse = { x: 720, y: 450 }

/** Moves the cursor to the middle of `target` in a smooth glide, as a person's hand would. */
async function glideTo(page: Page, target: Locator) {
  await target.scrollIntoViewIfNeeded()
  const box = (await target.boundingBox())!
  await glideToPoint(page, { x: box.x + box.width / 2, y: box.y + box.height / 2 })
}

async function glideToPoint(page: Page, to: { x: number; y: number }) {
  const distance = Math.hypot(to.x - mouse.x, to.y - mouse.y)
  await page.mouse.move(to.x, to.y, { steps: Math.max(12, Math.round(distance / 18)) })
  mouse = to
}

/**
 * Where the cursor waits while a step is read: the empty end of the card's "Step N of 10" row,
 * clear of every word and of Close (on the title, it hid a letter).
 */
async function restOn(page: Page, card: Locator) {
  const box = (await card.boundingBox())!
  const title = (await card.getByRole('heading', { level: 2 }).boundingBox())!
  await glideToPoint(page, { x: box.x + box.width * 0.62, y: title.y - 16 })
}

/** Glides to `target`, pauses, then clicks it. */
async function glideAndClick(page: Page, target: Locator) {
  await glideTo(page, target)
  await pause(page, 250)
  await target.click()
}

/** The poster: this moment with the recording's cursor hidden. */
async function posterShot(page: Page, path: string) {
  const cursor = page.locator('#od-recording-cursor')
  await cursor.evaluate((dot: HTMLElement) => (dot.style.visibility = 'hidden'))
  await page.screenshot({ path })
  await cursor.evaluate((dot: HTMLElement) => (dot.style.visibility = 'visible'))
}

/** The person's conversation as the API stores it: the same turns the page shows. */
async function storedTurns(page: Page): Promise<RecordedTurn[]> {
  const body = await page.evaluate(async () => {
    const token = /(?:^|; )__Host-od_csrf=([^;]*)/.exec(document.cookie)?.[1] ?? ''
    const response = await fetch('/api/v1/assistant/conversations/current', {
      headers: { 'X-CSRF-Token': token },
    })
    return (await response.json()) as { turns: RecordedTurn[] } | null
  })
  return body?.turns ?? []
}

/** Sends each of the step's chips, waits for each answer, and holds it on screen to be read. */
async function sendChips(page: Page, step: TourStep): Promise<RecordedTurn[]> {
  const before = (await storedTurns(page)).length
  for (const [index, text] of (step.chips ?? []).entries()) {
    const chip = mark(page, step).getByRole('button', {
      name: new RegExp(`^${escapeRegExp(text)}`),
    })
    await glideAndClick(page, chip)
    await expect(chip).toHaveAccessibleName(/,\s?sent$/, { timeout: 10_000 })
    // One counter, the API's: this chip's turn is stored and has ended. (The page's feedback rows
    // would miss a turn that shows none, such as an HR panel, in a persona's earlier turns.)
    await expect
      .poll(
        async () => {
          const stored = await storedTurns(page)
          return stored.length > before + index && stored.at(-1)!.status !== 'running'
        },
        { timeout: TURN_TIMEOUT_MS, intervals: [500] },
      )
      .toBe(true)
    const turns = await storedTurns(page)
    const last = turns.at(-1)!
    // A turn the take can't use stops it here, before the step's next question is paid for.
    exchangesOf([last])
    await pause(
      page,
      Math.min(holdMs(last.escalation?.message ?? last.answerText), ANSWER_HOLD_MAX_MS),
    )
  }
  const turns = await storedTurns(page)
  return turns.slice(before)
}

/**
 * Next, and on a step that changes persona, the toast that names the new person. Then the cursor
 * comes to rest on the new step's title, as a reader's would, instead of over its buttons.
 */
async function next(page: Page, step: TourStep, nextStep: TourStep | undefined) {
  await glideAndClick(page, nextButton(page, step))
  if (!nextStep) return
  if (nextStep.persona !== step.persona) {
    await expect(page.locator('[data-slot="toast"]')).toContainText('Now viewing as', {
      timeout: 30_000,
    })
  }
  const card =
    nextStep.id === 'end'
      ? page.getByRole('dialog', { name: /That’s the tour/ })
      : mark(page, nextStep)
  await expect(card).toBeVisible({ timeout: 30_000 })
  await restOn(page, card)
}

test('record the walkthrough', async ({ browser }) => {
  mkdirSync(OUT, { recursive: true })
  const context = await browser.newContext({
    recordVideo: { dir: join(OUT, 'video'), size: { width: 1440, height: 900 } },
    viewport: { width: 1440, height: 900 },
  })
  await context.addInitScript(drawCursor)
  // The browser suite's own CSP watch (the event and the console's reports), without its fake
  // Turnstile: the recording shows Cloudflare's real widget, with the test key.
  const seenViolations = await watchCsp(context)
  const page = await context.newPage()
  const videoStartedAt = Date.now()

  await page.goto('/')
  const tourButton = page.getByRole('button', { name: 'Take the 2-minute tour' })
  await expect(tourButton).toBeVisible()
  await page.mouse.move(mouse.x, mouse.y)
  const tourStartsAt = (Date.now() - videoStartedAt) / 1000
  await pause(page, 2500)
  await glideAndClick(page, tourButton)
  await expect(page).toHaveURL('/ask', { timeout: 30_000 })

  const steps: WalkthroughStep[] = []
  for (const [index, step] of TOUR.entries()) {
    const nextStep = TOUR[index + 1]
    if (step.id === 'end') {
      const end = page.getByRole('dialog', { name: /That’s the tour/ })
      await expect(end).toBeVisible()
      await pause(page, holdMs(TOUR_END_SUMMARY) + 1000)
      steps.push({
        id: step.id,
        title: step.title,
        persona: null,
        words: TOUR_END_SUMMARY,
        exchanges: [],
      })
      break
    }
    await expect(mark(page, step)).toBeVisible({ timeout: 30_000 })
    await pause(page, holdMs(step.body))
    const turns = await sendChips(page, step)
    // Built now, not when the step ends: a turn the take can't use (one that didn't complete, a
    // crisis or "can't answer" panel, or no answer) stops the take before this step's actions and
    // any later step's paid turns. sendChips has already checked each turn as it ended.
    const exchanges = exchangesOf(turns)
    let note = NOTES[step.id]

    if (step.id === 'book-day-off') {
      const confirm = page.getByRole('button', { name: /^Confirm: book PTO on / })
      await expect(confirm, 'step 3 needs the confirm card').toBeVisible()
      // The poster (screen 16 calls step 3 the poster): the card ready to confirm, once the answer
      // has finished and the page has stopped scrolling.
      await expect(confirm).toBeEnabled({ timeout: TURN_TIMEOUT_MS })
      await pause(page, 1000)
      await posterShot(page, join(OUT, 'poster.png'))
      await glideAndClick(page, confirm)
      await expect(page.locator('[data-slot="confirm-card"] output').first()).toContainText(
        'Requested.',
      )
      await pause(page, 2000)
    }
    if (step.id === 'decide-as-manager') {
      const approve = page.getByRole('button', { name: /^Confirm: approve Priya Raman’s PTO, / })
      await expect(approve, 'step 4 needs the decision card').toBeVisible()
      await glideAndClick(page, approve)
      await expect(page.locator('[data-slot="confirm-card"] output').first()).toContainText(
        'Approved.',
      )
      await pause(page, 2000)
    }
    if (step.id === 'sensitive') {
      const open = page.getByRole('button', { name: 'Open a confidential case' })
      await expect(open, 'step 7 needs the HR panel').toBeVisible()
      await glideAndClick(page, open)
      await glideAndClick(page, page.getByRole('radio', { name: HARASSMENT }))
      await glideAndClick(page, page.getByRole('button', { name: /^Send to HR$/ }))
      await expect(page.locator('[data-slot="case-sent"]').getByRole('status')).toContainText(
        'Sent to HR.',
      )
      await pause(page, 2500)
    }
    if (step.id === 'hr-receives') {
      await glideAndClick(page, page.locator('[data-tour="case-row"]'))
      const summary = page.locator('[data-slot="case-summary"] p.whitespace-pre-wrap')
      await expect(summary, 'step 8 needs the case summary').toBeVisible({
        timeout: TURN_TIMEOUT_MS,
      })
      const text = (await summary.textContent()) ?? ''
      note = summaryNote(text)
      await pause(page, holdMs(text))
    }
    if (step.id === 'see-console') {
      // The live safety check flags both of step 6's questions, so there can be two flagged rows.
      // The tour rings the first, the newest; so does the recording.
      await expect(page.locator('[data-tour="flagged-row"]').first()).toBeVisible()
      await pause(page, 2500)
    }

    steps.push({
      id: step.id,
      title: step.title,
      persona: step.persona,
      words: step.body,
      exchanges,
      ...(note ? { note } : {}),
    })
    await next(page, step, nextStep)
  }

  const walkthrough: Walkthrough = {
    // The day where it was recorded, not in UTC (an evening take in the US is already tomorrow).
    recordedOn: localIsoDate(new Date()),
    model: MODEL_ID === 'scripted' ? 'Scripted model (dry run)' : modelDisplayName(MODEL_ID),
    // record.py replaces it with the encoded video's length.
    durationSeconds: Math.round((Date.now() - videoStartedAt) / 1000 - tourStartsAt),
    steps,
  }
  const video = page.video()!
  // Let a violation queued by the last action reach the binding before it is read.
  await pause(page, 50)
  const violations = seenViolations()
  await context.close()
  await video.saveAs(join(OUT, 'raw.webm'))
  writeFileSync(join(OUT, 'walkthrough.json'), `${JSON.stringify(walkthrough, null, 2)}\n`)
  writeFileSync(
    join(OUT, 'take.json'),
    `${JSON.stringify({ startSeconds: Math.max(0, tourStartsAt - 0.5), violations }, null, 2)}\n`,
  )
  expect(violations, 'no Content Security Policy violation while recording').toEqual([])
})
