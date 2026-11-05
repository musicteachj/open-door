import { expect, test, type Page } from '@playwright/test'
import { TOUR, type TourStep } from '../src/features/tour/script'
import { HARASSMENT, openCaseButton, queueRows, sentLine } from './cases-helpers'
import { assistantMessages, composerBox, stopButton, userMessages } from './conversation-helpers'
import { holdRequests, startAs, switchTo } from './helpers'
import {
  cards,
  scrollsSideways,
  settledScan,
  skipUnlessScriptedDayCounts,
  toast,
} from './time-off-helpers'

// The guided tour (screen 15) in the real app, against the scripted model: every step of `TOUR`
// from the landing's button to the end card, the leave, resume, reload, and menu paths, and the
// coach mark docked at 390 px. Every wait is on something visible, never a fixed sleep.

const NAMES = {
  priya: 'Priya Raman',
  mateo: 'Mateo Alvarez',
  marcus: 'Marcus Bell',
  dana: 'Dana Whitfield',
} as const

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const LEFT = 'Tour closed. You can pick it up again from the persona menu.'

const switcher = (page: Page) => page.getByRole('button', { name: /Switch persona$|^Switching/ })
const mark = (page: Page, step: TourStep) =>
  page.getByRole('dialog', { name: new RegExp(escapeRegExp(step.title)) })
const ring = (page: Page) => page.locator('[data-slot="tour-ring"]')
const chip = (card: ReturnType<typeof mark>, text: string) =>
  card.getByRole('button', { name: new RegExp(`^${escapeRegExp(text)}`) })

async function startTour(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: 'Take the 2-minute tour' }).click()
  await expect(page).toHaveURL('/ask')
  await expect(mark(page, TOUR[0]!)).toBeVisible()
}

/**
 * The element the coach mark points at: the last of the step's targets that is on the page. Give
 * `expected` when the step's target is about to change (step 7's panel, then its form), so the
 * read waits for that target instead of taking the earlier one.
 */
async function targetOf(page: Page, step: TourStep, expected?: string) {
  const last = step.targets.at(-1)!
  const name = await (async () => {
    let found: string | null = null
    const poll = expect.poll(async () => {
      found = null
      for (const candidate of [...step.targets].reverse()) {
        if ((await page.locator(`[data-tour="${candidate}"]`).count()) > 0) {
          found = candidate
          return candidate
        }
      }
      return null
    })
    await (expected ? poll.toBe(expected) : poll.not.toBeNull())
    return found ?? last
  })()
  // The chip is the first one under the latest answer.
  return name === 'source-chip'
    ? page.locator('[data-slot="source-chips"]').last().locator('[data-tour="source-chip"]').first()
    : page.locator(`[data-tour="${name}"]`).last()
}

/** The ring is drawn 4 px outside the element the step points at. */
async function expectRingOn(page: Page, step: TourStep) {
  const target = await targetOf(page, step)
  await expect
    .poll(async () => {
      const [t, r] = await Promise.all([target.boundingBox(), ring(page).boundingBox()])
      if (!t || !r) return null
      return [r.x - t.x, r.y - t.y, r.width - t.width, r.height - t.height].map(Math.round)
    })
    .toEqual([-4, -4, 8, 8])
}

/**
 * The coach mark never covers the composer, and what the step points at is on screen (the tour
 * scrolls the conversation to bring it into view).
 */
async function expectClearOfComposer(page: Page, step: TourStep) {
  const target = await targetOf(page, step)
  const viewport = page.viewportSize()!
  await expect
    .poll(async () => {
      const [t, card, composer] = await Promise.all([
        target.boundingBox(),
        mark(page, step).boundingBox(),
        page.locator('[data-tour="composer"]').boundingBox(),
      ])
      if (!t || !card || !composer) return 'missing'
      const apart =
        card.x + card.width <= composer.x ||
        composer.x + composer.width <= card.x ||
        card.y + card.height <= composer.y ||
        composer.y + composer.height <= card.y
      const inView =
        t.x >= 0 && t.y >= 0 && t.x + t.width <= viewport.width && t.y + t.height <= viewport.height
      return { apart, inView }
    })
    .toEqual({ apart: true, inView: true })
}

/** Waits for one more question to be answered and the stream to be over. */
async function turnsDone(page: Page, count: number) {
  await expect(userMessages(page)).toHaveCount(count)
  await expect(assistantMessages(page)).toHaveCount(count)
  await expect(stopButton(page)).toHaveCount(0)
  await expect(page.locator('[data-slot="feedback"], [data-slot="feedback-thanks"]')).toHaveCount(
    count,
  )
}

/** Next on a step that changes persona: the switcher is busy, then the toast names the person. */
async function nextAcross(page: Page, step: TourStep, to: keyof typeof NAMES) {
  const release = await holdRequests(page, '**/api/v1/session/persona', 'PUT')
  await mark(page, step).getByRole('button', { name: 'Next', exact: true }).click()
  await expect(
    page.getByRole('button', { name: new RegExp(`^Switching to ${NAMES[to].split(' ')[0]}…`) }),
  ).toBeVisible()
  release()
  await expect(toast(page)).toContainText(`Now viewing as ${NAMES[to]}.`)
}

async function expectChipsUnsent(page: Page, step: TourStep) {
  const card = mark(page, step)
  await expect(card.getByRole('button', { name: 'Skip this step' })).toBeVisible()
  await expect(card.getByRole('button', { name: 'Next', exact: true })).toHaveCount(0)
  await expect(card.getByText('Sent', { exact: true })).toHaveCount(0)
}

async function sendChips(page: Page, step: TourStep, askedBefore: number) {
  const card = mark(page, step)
  let asked = askedBefore
  for (const text of step.chips ?? []) {
    await chip(card, text).click()
    asked += 1
    await expect(chip(card, text)).toHaveAccessibleName(/,\s?sent$/)
    await turnsDone(page, asked)
  }
  await expect(card.getByText('Sent', { exact: true })).toHaveCount(step.chips?.length ?? 0)
  await expect(card.getByRole('button', { name: 'Next', exact: true })).toBeVisible()
  await expect(card.getByRole('button', { name: 'Skip this step' })).toHaveCount(0)
  return asked
}

async function expectStep(page: Page, step: TourStep, number: number) {
  const card = mark(page, step)
  await expect(card).toBeVisible()
  await expect(card.getByText(`Step ${number} of 10`, { exact: true })).toBeVisible()
  await expect(card.getByRole('heading', { level: 2 })).toBeFocused()
  await expect(card).toContainText(step.body)
  if (number === 1) await expect(card.getByRole('button', { name: 'Back' })).toHaveCount(0)
  else await expect(card.getByRole('button', { name: 'Back' })).toBeVisible()
}

async function expectNoViolations(page: Page) {
  const results = await settledScan(page)
  expect(results.violations).toEqual([])
}

test.describe('the walk, at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('every step, from the landing button to the end card', async ({ page }) => {
    test.setTimeout(240_000)
    await page.goto('/')
    await page.getByRole('button', { name: 'Take the 2-minute tour' }).click()
    await expect(page).toHaveURL('/ask')
    await skipUnlessScriptedDayCounts(test, page, 'book next friday')

    // 1: Priya asks about sick days, and the answer cites CA-4.3.
    let step = TOUR[0]!
    await expectStep(page, step, 1)
    await expect(switcher(page)).toHaveAccessibleName(/^Priya Raman/)
    await expectRingOn(page, step)
    await expectChipsUnsent(page, step)
    await expectNoViolations(page)
    // Each person's conversation is kept when the tour switches away and back.
    const asked = { priya: 0, mateo: 0, marcus: 0 }
    asked.priya = await sendChips(page, step, asked.priya)
    await expect(page.locator('[data-tour="source-chip"]').first()).toContainText('CA-4.3')
    await expectRingOn(page, step)
    await expectNoViolations(page)

    // 2: Mateo, the same question, section 4.3.
    await nextAcross(page, step, 'mateo')
    step = TOUR[1]!
    await expectStep(page, step, 2)
    await expect(switcher(page)).toHaveAccessibleName(/^Mateo Alvarez/)
    await expectRingOn(page, step)
    await expectChipsUnsent(page, step)
    asked.mateo = await sendChips(page, step, asked.mateo)
    await expect(page.locator('[data-tour="source-chip"]').first()).not.toContainText('CA-')

    // 3: Priya books next Friday, and the test confirms the card.
    await nextAcross(page, step, 'priya')
    step = TOUR[2]!
    await expectStep(page, step, 3)
    await expectChipsUnsent(page, step)
    asked.priya = await sendChips(page, step, asked.priya)
    await expect(cards(page)).toHaveCount(1)
    await expect(mark(page, step).getByRole('status')).toHaveCount(0)
    await expectRingOn(page, step)
    await expectClearOfComposer(page, step)
    await expectNoViolations(page)
    await page.getByRole('button', { name: /^Confirm: book PTO on / }).click()
    await expect(cards(page).first().locator('output')).toContainText(
      'Requested. Marcus Bell will review it.',
    )

    // 4: Marcus sees both requests, then approves Priya's on its card.
    await nextAcross(page, step, 'marcus')
    step = TOUR[3]!
    await expectStep(page, step, 4)
    await expectChipsUnsent(page, step)
    asked.marcus = await sendChips(page, step, asked.marcus)
    await expect(assistantMessages(page).first()).toContainText('2 requests are waiting')
    await expectRingOn(page, step)
    const decision = cards(page).first()
    await expect(decision).toContainText('Priya Raman')
    await decision.getByRole('button', { name: /^Confirm: approve Priya Raman’s PTO, / }).click()
    await expect(decision.locator('output')).toContainText('Approved. Priya will see it')

    // 5: still Marcus, in the same conversation, with no switch.
    await mark(page, step).getByRole('button', { name: 'Next', exact: true }).click()
    step = TOUR[4]!
    await expectStep(page, step, 5)
    await expect(switcher(page)).toHaveAccessibleName(/^Marcus Bell/)
    await expect(userMessages(page)).toHaveCount(asked.marcus)
    await expectChipsUnsent(page, step)
    asked.marcus = await sendChips(page, step, asked.marcus)
    await expect(assistantMessages(page).last()).toContainText('approved time off')

    // 6: Priya tries to get past the rules.
    await nextAcross(page, step, 'priya')
    step = TOUR[5]!
    await expectStep(page, step, 6)
    await expectChipsUnsent(page, step)
    asked.priya = await sendChips(page, step, asked.priya)
    await expect(assistantMessages(page).last()).toContainText('I can only share what you')

    // 7: the sensitive message, the HR panel, the case form, and Send.
    await mark(page, step).getByRole('button', { name: 'Next', exact: true }).click()
    step = TOUR[6]!
    await expectStep(page, step, 7)
    await expectChipsUnsent(page, step)
    asked.priya = await sendChips(page, step, asked.priya)
    await expect(mark(page, step).getByRole('status')).toHaveCount(0)
    await expectRingOn(page, step)
    await expect(await targetOf(page, step, 'open-case')).toHaveText(/Open a confidential case/)
    await openCaseButton(page).click()
    // The form opens below the fold: the tour scrolls Send to HR into view, clear of the card and
    // the composer, before the visitor does anything else.
    await expect(await targetOf(page, step, 'case-send')).toHaveText(/Send to HR/)
    await expectClearOfComposer(page, step)
    await expectRingOn(page, step)
    await page.getByRole('radio', { name: HARASSMENT }).click()
    await expectRingOn(page, step)
    await expectNoViolations(page)
    await page.getByRole('button', { name: /^Send to HR$/ }).click()
    await expect(sentLine(page)).toContainText('Sent to HR. HR replies by')

    // 8: Dana opens Priya's new case, and the summary.
    await nextAcross(page, step, 'dana')
    step = TOUR[7]!
    await expectStep(page, step, 8)
    await expect(page).toHaveURL('/cases')
    for (const name of ['Priya Raman', 'Keisha Zhang', 'Chloe Foster']) {
      await expect(queueRows(page).filter({ hasText: name })).toHaveCount(1)
    }
    const row = page.locator('[data-tour="case-row"]')
    await expect(row).toHaveCount(1)
    await expect(row).toContainText('Priya Raman')
    await expectRingOn(page, step)
    await expect(mark(page, step).getByRole('button', { name: 'Skip this step' })).toHaveCount(0)
    await row.click()
    await expect(page.locator('[data-tour="case-summary"]')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Show Priya’s words' })).toBeVisible()
    await expectRingOn(page, step)

    // 9: the console, and the flagged row.
    await mark(page, step).getByRole('button', { name: 'Next', exact: true }).click()
    step = TOUR[8]!
    await expectStep(page, step, 9)
    await expect(page).toHaveURL('/console')
    await expect(page.locator('[data-tour="flagged-row"]')).toBeVisible()
    await expectRingOn(page, step)
    await expectNoViolations(page)

    // 10: the end card.
    await mark(page, step).getByRole('button', { name: 'Next', exact: true }).click()
    const end = page.getByRole('dialog', { name: /That’s the tour/ })
    await expect(end).toBeVisible()
    await expect(end.getByText('Step 10 of 10', { exact: true })).toBeVisible()
    await expect(end.getByRole('heading', { level: 2 })).toBeFocused()
    await expect(ring(page)).toHaveCount(0)
    await expectNoViolations(page)
    await end.getByRole('button', { name: 'Keep exploring as Dana' }).click()
    await expect(end).toHaveCount(0)
    await expect(page).toHaveURL('/console')
    await switcher(page).click()
    await expect(page.getByRole('menuitem', { name: 'Take the tour' })).toBeVisible()
  })

  test('"Choose who to be" on the end card ends the tour and opens the persona menu', async ({
    page,
  }) => {
    await startAs(page, 'Dana')
    await page.goto('/console')
    await page.evaluate(() =>
      sessionStorage.setItem(
        'od.tour',
        JSON.stringify({
          state: {
            started: true,
            active: true,
            step: 9,
            sent: [],
            turnId: null,
            lost: false,
            outcome: null,
            entering: false,
          },
          version: 3,
        }),
      ),
    )
    await page.reload()
    const end = page.getByRole('dialog', { name: /That’s the tour/ })
    await end.getByRole('button', { name: 'Choose who to be' }).click()
    await expect(end).toHaveCount(0)
    await expect(page.getByRole('menu')).toBeVisible()
    await expect(page.getByRole('menuitemradio', { name: /^Priya / })).toBeVisible()
  })
})

test.describe('leaving, resuming, and reloading, at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  for (const how of ['Escape', 'the X'] as const) {
    test(`leaving with ${how} closes the coach mark with its toast and puts focus in the composer`, async ({
      page,
    }) => {
      await startTour(page)
      await expect(composerBox(page)).toBeVisible()
      if (how === 'Escape') await page.keyboard.press('Escape')
      else await page.getByRole('button', { name: 'Leave the tour' }).click()
      await expect(page.getByRole('dialog', { name: /Ask a policy question/ })).toHaveCount(0)
      await expect(ring(page)).toHaveCount(0)
      await expect(toast(page)).toHaveText(LEFT)
      await expect(composerBox(page)).toBeFocused()
      await expect(page).toHaveURL('/ask')
    })
  }

  test('the menu offers Resume with the step, and Resume returns to it as its persona', async ({
    page,
  }) => {
    await startTour(page)
    await mark(page, TOUR[0]!).getByRole('button', { name: 'Skip this step' }).click()
    await expectStep(page, TOUR[1]!, 2)
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: /Same question/ })).toHaveCount(0)
    // Someone else's persona for a while: the tour stays where it was.
    await switchTo(page, 'Marcus')
    await expect(switcher(page)).toHaveAccessibleName(/^Marcus Bell/)
    await switcher(page).click()
    // Chromium puts a space before hidden text in a name.
    await expect(
      page.getByRole('menuitem', { name: /^Resume the tour\s?, Step 2 of 10$/ }),
    ).toBeVisible()
    await expect(page.getByRole('menuitem', { name: 'Start the tour over' })).toBeVisible()
    await page.getByRole('menuitem', { name: /^Resume the tour/ }).click()
    await expectStep(page, TOUR[1]!, 2)
    await expect(switcher(page)).toHaveAccessibleName(/^Mateo Alvarez/)
  })

  test('a reload resumes the current step as its persona', async ({ page }) => {
    await startTour(page)
    await mark(page, TOUR[0]!).getByRole('button', { name: 'Skip this step' }).click()
    await expectStep(page, TOUR[1]!, 2)
    await page.reload()
    await expect(mark(page, TOUR[1]!)).toBeVisible()
    await expect(mark(page, TOUR[1]!).getByText('Step 2 of 10', { exact: true })).toBeVisible()
    await expect(switcher(page)).toHaveAccessibleName(/^Mateo Alvarez/)
  })
})

test.describe('starting from inside the app, at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('the menu asks first: Cancel changes nothing, and Start opens a new sandbox as Priya at step 1', async ({
    page,
  }) => {
    await startAs(page, 'Marcus')
    const sandboxes: string[] = []
    page.on('request', (request) => {
      if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/sandboxes') {
        sandboxes.push(request.url())
      }
    })
    await switcher(page).click()
    await page.getByRole('menuitem', { name: 'Take the tour' }).click()
    const dialog = page.getByRole('alertdialog', { name: 'Start the tour?' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused()
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).toHaveCount(0)
    expect(sandboxes).toEqual([])
    await expect(switcher(page)).toHaveAccessibleName(/^Marcus Bell/)

    await switcher(page).click()
    await page.getByRole('menuitem', { name: 'Take the tour' }).click()
    await dialog.getByRole('button', { name: 'Start the tour' }).click()
    await expectStep(page, TOUR[0]!, 1)
    expect(sandboxes).toHaveLength(1)
    await expect(switcher(page)).toHaveAccessibleName(/^Priya Raman/)
    await expect(page).toHaveURL('/ask')
  })

  test('the console’s empty state opens the same dialog', async ({ page }) => {
    await startAs(page, 'Dana')
    await page.goto('/console')
    await page.getByRole('button', { name: 'Take the tour' }).click()
    const dialog = page.getByRole('alertdialog', { name: 'Start the tour?' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
  })
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the coach mark docks as a bottom sheet, the target stays above it, and nothing scrolls sideways', async ({
    page,
  }) => {
    test.setTimeout(90_000)
    await startTour(page)
    let step = TOUR[0]!
    const sheet = mark(page, step)
    const dock = async () => {
      const box = (await sheet.boundingBox())!
      expect(Math.round(box.x)).toBe(0)
      expect(Math.round(box.width)).toBe(390)
      expect(Math.round(box.y + box.height)).toBe(844)
    }
    await dock()
    const composer = await targetOf(page, step)
    await expect
      .poll(async () => {
        const [c, s] = await Promise.all([composer.boundingBox(), sheet.boundingBox()])
        return c!.y + c!.height <= s!.y + 1
      })
      .toBe(true)
    expect(await scrollsSideways(page)).toBe(false)

    await chip(sheet, step.chips![0]!).click()
    await expect(sheet.getByRole('button', { name: 'Next', exact: true })).toBeVisible()
    await dock()
    const source = await targetOf(page, step)
    await expect(source).toContainText('CA-4.3')
    await expect
      .poll(async () => {
        const [c, s] = await Promise.all([source.boundingBox(), sheet.boundingBox()])
        return c!.y >= 0 && c!.y + c!.height <= s!.y + 1
      })
      .toBe(true)
    await expectRingOn(page, step)
    expect(await scrollsSideways(page)).toBe(false)
    await expectNoViolations(page)

    // The next step's sheet too, after the switch.
    await sheet.getByRole('button', { name: 'Next', exact: true }).click()
    step = TOUR[1]!
    await expectStep(page, step, 2)
    await expect(mark(page, step)).toBeVisible()
    const box = (await mark(page, step).boundingBox())!
    expect(Math.round(box.y + box.height)).toBe(844)
    expect(await scrollsSideways(page)).toBe(false)
  })
})
