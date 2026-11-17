import { expect, test } from '../fixtures'
import type { Page } from '@playwright/test'
import { CRISIS_WORDS, SENSITIVE_QUESTION, openCaseButton, queueRows } from '../cases-helpers'
import {
  BUDGET_DAILY_TEXT,
  QUESTIONS,
  ask,
  askAndWaitForAnswer,
  assistantMessage,
  stubConversation,
} from '../conversation-helpers'
import { startAs } from '../helpers'
import {
  cards,
  factsOf,
  nav,
  pickDays,
  skipUnlessScriptedDayCounts,
  switchPersona,
  workdays,
} from '../time-off-helpers'
import {
  motionFindings,
  reflowFindings,
  settle,
  targetSizeFindings,
  textSpacingFindings,
} from './checks'

// The audit's sweep (Phase 8, Stage 8): every page, and the states a person reaches on the main
// flows (and the recorded walkthrough, added in Stage 9), checked for what axe doesn't measure. Axe itself already scans each of these in its own
// spec. Each test reaches one state with reduced motion on, then checks, at its desktop width and
// again at 320 px: nothing moves, every target is big enough or has room, no text is lost under
// 1.4.12's spacing (apart from the known lows below), and (at 320 px) nothing needs a sideways
// scroll. The findings are soft, so one run lists everything a state fails. docs/ACCESSIBILITY.md
// records the results.

test.use({ viewport: { width: 1280, height: 900 } })

/**
 * The audit's accepted text-spacing findings (lows L1 and L2 in docs/ACCESSIBILITY.md), by the part
 * of the page they are in and how the words go. Anything else fails, so a new truncation or spill
 * is caught. Every one keeps its full words a step away or on screen.
 */
const KNOWN_LOWS: { part: string; how: string; why: string }[] = [
  // L1: a label the design truncates, cut short sooner. Its full words are its accessible name.
  {
    part: 'persona-switcher',
    how: 'cut short',
    why: 'the persona menu shows the full name and title',
  },
  { part: 'directory-row', how: 'cut short', why: 'the profile shows the full title and location' },
  { part: 'source-chip', how: 'cut short', why: 'the chip opens the passage, titled in full' },
  { part: 'rule-chip', how: 'cut short', why: 'the chip links to the section, titled in full' },
  // L2: a few pixels past a box with nothing beside them to overlap; every word stays readable.
  {
    part: 'case-queue-row',
    how: 'spills',
    why: 'the date runs into the Reply column’s empty space',
  },
  { part: 'turn-row', how: 'spills', why: 'the cost runs into the cell’s padding' },
  { part: 'scoreboard', how: 'spills', why: 'the row header runs into the cell’s padding' },
  { part: 'section-row', how: 'spills', why: 'the title runs into the gap before the chevron' },
  { part: 'retention-line', how: 'spills', why: 'beside an open passage it wraps a word a line' },
]

/** The text-spacing findings that aren't on the known list. */
const unexpected = (found: string[]) =>
  found.filter(
    (line) => !KNOWN_LOWS.some(({ part, how }) => line.includes(`[${part}]`) && line.includes(how)),
  )

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
})

/** Runs every check on the page as it is, at 1280 px and at 320 px, as soft expectations. */
async function audit(page: Page) {
  await page.mouse.move(2, 2)
  await settle(page)
  for (const width of [1280, 320]) {
    await page.setViewportSize({ width, height: width === 320 ? 640 : 900 })
    await settle(page)
    expect.soft(await motionFindings(page), `nothing moves at ${width} px`).toEqual([])
    expect.soft(await targetSizeFindings(page), `targets at ${width} px`).toEqual([])
    expect
      .soft(unexpected(await textSpacingFindings(page)), `text spacing at ${width} px`)
      .toEqual([])
    if (width === 320) expect.soft(await reflowFindings(page), 'reflow at 320 px').toEqual([])
  }
  await page.setViewportSize({ width: 1280, height: 900 })
}

const navLink = (page: Page, name: string | RegExp) => nav(page).getByRole('link', { name })

test('the landing page', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Take the 2-minute tour' })).toBeVisible()
  await audit(page)
})

test('the recorded walkthrough', async ({ page }) => {
  await page.goto('/walkthrough')
  await expect(
    page.getByRole('heading', { level: 1, name: 'The recorded walkthrough' }),
  ).toBeVisible()
  await audit(page)
})

test('the daily-limit banner with its walkthrough link (STUB: the conversation GET)', async ({
  page,
}) => {
  await startAs(page, 'Priya')
  await askAndWaitForAnswer(page, QUESTIONS.cited)
  await stubConversation(page, (body) => {
    body.budget = {
      ...body.budget,
      dailyReached: true,
      banner: { kind: 'daily', message: BUDGET_DAILY_TEXT },
    }
  })
  await page.reload()
  await expect(page.getByRole('link', { name: 'Watch the recorded walkthrough' })).toBeVisible()
  await audit(page)
})

test('the assistant home', async ({ page }) => {
  await startAs(page, 'Priya')
  await audit(page)
})

test('a cited answer with its source open', async ({ page }) => {
  await startAs(page, 'Priya')
  await askAndWaitForAnswer(page, QUESTIONS.cited)
  await assistantMessage(page, 0).locator('[data-slot="citation-marker"]').first().click()
  await expect(page.getByRole('button', { name: 'Close passage' })).toBeVisible()
  await audit(page)
})

test('the sensitive panel and the case form', async ({ page }) => {
  await startAs(page, 'Priya')
  await askAndWaitForAnswer(page, SENSITIVE_QUESTION)
  await openCaseButton(page).click()
  await expect(page.getByRole('button', { name: 'Send to HR' })).toBeVisible()
  await audit(page)
})

test('the crisis panel', async ({ page }) => {
  await startAs(page, 'Priya')
  // The crisis panel has no "Was this right?", so wait for the panel itself.
  await ask(page, CRISIS_WORDS)
  await expect(page.locator('[data-slot="escalation-panel"]')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeVisible()
  await audit(page)
})

test('a confirm card in the conversation', async ({ page }) => {
  await startAs(page, 'Priya')
  await skipUnlessScriptedDayCounts(test, page, 'book next friday')
  await askAndWaitForAnswer(page, 'book next friday')
  await expect(cards(page)).toHaveCount(1)
  await audit(page)
})

test('Time off with the request form open', async ({ page }) => {
  await startAs(page, 'Priya')
  await navLink(page, 'Time off').click()
  await expect(page).toHaveURL('/time-off')
  const [day] = workdays(await factsOf(page), 14, 1) as [string]
  await page.getByRole('button', { name: 'Request time off' }).first().click()
  const form = page.locator('#request-form')
  await pickDays(page, form, day)
  await expect(form.getByText(/What this uses/i)).toBeVisible()
  await audit(page)
})

test('Approvals with a decision dialog open', async ({ page }) => {
  await startAs(page, 'Marcus')
  await navLink(page, /^Approvals/).click()
  await expect(page).toHaveURL('/approvals')
  await page.getByRole('button', { name: /^Approve Zara Bautista’s PTO, / }).click()
  await expect(page.getByRole('alertdialog')).toBeVisible()
  await audit(page)
})

test('My cases with the case form open', async ({ page }) => {
  await startAs(page, 'Priya')
  await navLink(page, 'My cases').click()
  await expect(page).toHaveURL('/my-cases')
  await openCaseButton(page).click()
  await expect(page.getByRole('button', { name: 'Send to HR' })).toBeVisible()
  await audit(page)
})

test('the HR case queue', async ({ page }) => {
  await startAs(page, 'Dana')
  await navLink(page, /^Cases/).click()
  await expect(page).toHaveURL('/cases')
  await expect(queueRows(page).first()).toBeVisible()
  await audit(page)
})

test('a case with the person’s words shown', async ({ page }) => {
  await startAs(page, 'Dana')
  await navLink(page, /^Cases/).click()
  await queueRows(page).first().click()
  await expect(page).toHaveURL(/\/cases\/.+/)
  await page.getByRole('button', { name: /^Show .+ words$/ }).click()
  await expect(page.getByRole('button', { name: /^Hide .+ words$/ })).toBeVisible()
  await audit(page)
})

test('the console with a turn’s trace open', async ({ page }) => {
  await startAs(page, 'Priya')
  await askAndWaitForAnswer(page, QUESTIONS.cited)
  await switchPersona(page, 'Dana')
  await navLink(page, 'Console').click()
  await expect(page).toHaveURL('/console')
  await page
    .getByRole('button', { name: /^\d{1,2}:\d{2}\s?[AP]M\s?,\s?Employee,\s?Oakland, CA/ })
    .click()
  await expect(page.locator('[data-slot="trace-panel"]')).toBeVisible()
  await audit(page)
})

test('the directory and a profile', async ({ page }) => {
  await startAs(page, 'Priya')
  await navLink(page, 'Directory').click()
  await expect(page).toHaveURL('/directory')
  await audit(page)
  await page.locator('main').getByRole('link').first().click()
  await expect(page).toHaveURL(/\/directory\/.+/)
  await audit(page)
})

test('the handbook and a section', async ({ page }) => {
  await startAs(page, 'Priya')
  await navLink(page, 'Handbook').click()
  await expect(page).toHaveURL('/handbook')
  await audit(page)
  await page.locator('main').getByRole('link').first().click()
  await expect(page).toHaveURL(/\/handbook\/.+/)
  await audit(page)
})

test('the not found page', async ({ page }) => {
  await startAs(page, 'Priya')
  await page.goto('/no-such-page')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await audit(page)
})

test('the tour’s first step', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Take the 2-minute tour' }).click()
  await expect(page).toHaveURL('/ask')
  await expect(page.locator('[data-slot="tour-ring"]')).toBeVisible()
  await audit(page)
})
