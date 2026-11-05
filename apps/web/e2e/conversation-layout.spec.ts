import { expect, test, type Locator, type Page } from '@playwright/test'
import {
  ask,
  askAndWaitForAnswer,
  askButton,
  assistantMessage,
  BUDGET_DAILY_TEXT,
  BUDGET_SANDBOX_TEXT,
  composerBox,
  composerLine,
  PERSONAL_DATA_TEXT,
  QUESTIONS,
  stopButton,
  stubConversation,
  waitForTurnSaved,
} from './conversation-helpers'
import { MODAL_OVERLAY_RULES, scan, startAs } from './helpers'

// The conversation page's layout in a real browser, measured on the real page (not the gallery's
// frame, whose column is a different width). Two rules keep these from failing on another
// machine: nothing asserts a fit with sub-pixel room to spare (CI's Linux fonts draw wider than
// macOS, which once wrapped a line that fit here by 0.2 px), and a line that may wrap is checked as
// "wraps at most once" or "nothing overflows", never as "one line". Sizes that come from a CSS
// width (the 760 px thread, the 420 px panel) are exact; text is not.
//
// Everything runs against the real API with the scripted model. The budget banner and the
// long-conversation notice are STUBS of the conversation GET (see conversation.spec.ts).

type Box = { x: number; y: number; width: number; height: number }

async function boxOf(locator: Locator): Promise<Box> {
  await expect(locator.first()).toBeVisible()
  const box = await locator.first().boundingBox()
  if (box === null) throw new Error('no box for a visible element')
  return box
}

/** The page does not scroll sideways, and nothing in the conversation sticks out past the window. */
async function expectNothingSideways(page: Page) {
  const width = page.viewportSize()!.width
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
  const stickingOut = await page.evaluate((limit) => {
    const view = document.querySelector('[data-slot="conversation-view"]')
    if (view === null) return ['no conversation view']
    return [...view.querySelectorAll<HTMLElement>('*')]
      .filter((el) => {
        // Text cut off by a truncating ancestor (a chip's label) is not sideways scroll, and a
        // screen-reader-only node is not on screen.
        if (el.closest('.truncate') !== null || el.closest('.sr-only') !== null) return false
        const box = el.getBoundingClientRect()
        return box.width > 0 && box.right > limit + 1
      })
      .map((el) => `${el.tagName.toLowerCase()}[${el.getAttribute('data-slot') ?? ''}]`)
  }, width)
  expect(stickingOut).toEqual([])
}

/** `below` starts under `above`: it sits on a later row, not beside it. */
function expectOnLaterRow(above: Box, below: Box) {
  expect(below.y + below.height / 2).toBeGreaterThan(above.y + above.height)
}

/** The two share a row: their vertical centers are within `slack` px of each other. */
function expectSameRow(a: Box, b: Box, slack = 10) {
  expect(Math.abs(a.y + a.height / 2 - (b.y + b.height / 2))).toBeLessThanOrEqual(slack)
}

const thread = (page: Page) => page.locator('[data-slot="conversation-thread"]')
const composerForm = (page: Page) => page.locator('[data-slot="composer"]')
const retentionLines = (page: Page) => page.locator('[data-slot="retention-line"]')
const passage = (page: Page) => page.getByRole('complementary', { name: 'Handbook passage' })

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('a cited answer: nothing sideways, the user message at most 85% wide, the footer on two rows, and the sheet-free page', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(
      page,
      'A long question about how many sick days an employee gets each year, and whether they carry over',
    )
    await expectNothingSideways(page)

    const threadBox = await boxOf(thread(page))
    const user = await boxOf(page.locator('[data-slot="user-message"]'))
    expect(user.width).toBeLessThanOrEqual(threadBox.width * 0.85 + 1)
    // The user message is on the right.
    expect(Math.abs(user.x + user.width - (threadBox.x + threadBox.width))).toBeLessThanOrEqual(1)
    const answer = await boxOf(assistantMessage(page))
    expect(answer.width).toBeLessThanOrEqual(threadBox.width + 1)
    expect(answer.x).toBeGreaterThanOrEqual(threadBox.x - 1)

    // "Was this right?" and "Show your work" are on two rows.
    const feedback = await boxOf(page.getByRole('group', { name: 'Was this right?' }))
    const work = await boxOf(page.getByRole('button', { name: 'Show your work' }))
    expectOnLaterRow(feedback, work)

    expect((await scan(page)).violations).toEqual([])

    // The chips wrap, and a label too long for the row is cut off with an ellipsis while the
    // chip's accessible name keeps all of it. (The squeeze is the test's own, so no axe scan after.)
    const chips = page.locator('[data-slot="source-chips"] ul')
    await expect(chips).toHaveCSS('flex-wrap', 'wrap')
    await page.addStyleTag({
      content: '[data-slot="source-chips"] ul { width: 130px !important; }',
    })
    const chip = page.locator('[data-slot="source-chip"]')
    expect((await boxOf(chip)).width).toBeLessThanOrEqual(131)
    const label = chip.locator('.truncate')
    expect(await label.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true)
    await expect(label).toHaveCSS('text-overflow', 'ellipsis')
    await expect(chip).toHaveAccessibleName(/^Handbook \S+ · .+\s?, source 1$/)
    await page.reload()

    // The expanded work and the open reason form stay inside the column too.
    await page.getByRole('button', { name: 'Show your work' }).click()
    await page.getByRole('button', { name: 'No' }).click()
    await expectNothingSideways(page)
    expect((await scan(page)).violations).toEqual([])
  })

  // The page scrolls itself: when the saved answer replaces the streamed one, it adds the chips and
  // the feedback row (about 140 px on a phone), which used to land under the sticky composer. This
  // is the repro: nothing here scrolls the page.
  test('after the answer settles, its source chip and "Was this right?" are fully above the composer, with no scrolling by the test', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(
      page,
      'A long question about how many sick days an employee gets each year, and whether they carry over',
    )
    // Wait for the page to finish moving: the scroll position holds still for a moment.
    await expect
      .poll(async () => {
        const before = await page.evaluate(() => window.scrollY)
        await page.waitForTimeout(150)
        return before === (await page.evaluate(() => window.scrollY))
      })
      .toBe(true)
    expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0)
    const composer = await boxOf(composerForm(page))
    const chip = await boxOf(page.locator('[data-slot="source-chip"]'))
    const feedback = await boxOf(page.getByRole('group', { name: 'Was this right?' }))
    expect(chip.y).toBeGreaterThanOrEqual(0)
    expect(chip.y + chip.height).toBeLessThanOrEqual(composer.y)
    expect(feedback.y + feedback.height).toBeLessThanOrEqual(composer.y)
    expect((await scan(page)).violations).toEqual([])
  })

  test('the header: the icon button sits beside the sandbox pill, and the retention line sits under the composer', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const header = page.locator('[data-slot="conversation-header"]')
    const button = await boxOf(header.getByRole('button', { name: 'Start a new conversation' }))
    const pill = await boxOf(header.locator('[data-slot="sandbox-indicator"]'))
    expect(button.width).toBeLessThan(48)
    expectSameRow(button, pill)
    expect(pill.x).toBeGreaterThan(button.x + button.width - 1)
    // The shell's own pills step aside: this is the only sandbox pill on the screen.
    await expect(
      page.locator('[data-slot="sandbox-indicator"]').locator('visible=true'),
    ).toHaveCount(1)

    // The header's copy of the retention line is hidden, and the one under the composer shows.
    const line = retentionLines(page).locator('visible=true')
    await expect(line).toHaveCount(1)
    await expect(line).toHaveText('Conversations are deleted with your sandbox after 24 hours.')
    const composer = await boxOf(composerForm(page))
    expect((await boxOf(line)).y).toBeGreaterThanOrEqual(composer.y + composer.height - 1)
    expect((await scan(page)).violations).toEqual([])
  })

  test('the composer footer puts the disclosure above Ask, with Ask at the end of its row', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const disclosure = await boxOf(page.getByText(/Open Door is an AI assistant\./).first())
    const submit = await boxOf(askButton(page))
    const form = await boxOf(composerForm(page))
    expect(disclosure.y + disclosure.height).toBeLessThanOrEqual(submit.y + 1)
    expect(form.x + form.width - (submit.x + submit.width)).toBeLessThanOrEqual(20)
    await expectNothingSideways(page)
  })

  test('the panels are full width, and their contact rows stack with the email under the name', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await ask(page, QUESTIONS.crisis)
    await expect(page.getByRole('region', { name: 'Reach a person right now' })).toBeVisible()
    await askAndWaitForAnswer(page, QUESTIONS.sensitive)
    await ask(page, QUESTIONS.guardFailure)
    await expect(page.getByRole('region', { name: "Can't answer right now" })).toBeVisible()
    await expectNothingSideways(page)

    const threadBox = await boxOf(thread(page))
    for (const panel of await page.locator('[data-slot="escalation-panel"]').all()) {
      await panel.scrollIntoViewIfNeeded()
      const box = await boxOf(panel)
      // Full width of the column, not a card narrower than the text above it.
      expect(box.width).toBeGreaterThanOrEqual(threadBox.width - 2)
      for (const row of await panel.locator('[data-slot="hr-contacts"] li').all()) {
        const name = await boxOf(row.locator('span.font-semibold'))
        const email = await boxOf(row.getByRole('link'))
        expectOnLaterRow(name, email)
      }
    }
    // The crisis numbers are links people can press.
    const crisis = page.getByRole('region', { name: 'Reach a person right now' })
    await expect(crisis.getByRole('link', { name: 'Call or text 988' })).toHaveAttribute(
      'href',
      'tel:988',
    )
    expect((await scan(page)).violations).toEqual([])
  })

  test('a not-found answer: the HR contacts card stacks its rows, with the email under the name', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.notFound)
    await expectNothingSideways(page)
    for (const row of await page.locator('[data-slot="hr-contacts"] li').all()) {
      expectOnLaterRow(
        await boxOf(row.locator('span.font-semibold')),
        await boxOf(row.getByRole('link')),
      )
    }
    expect((await scan(page)).violations).toEqual([])
  })

  test('streaming, stopped, and an error mid-stream stay inside the column', async ({ page }) => {
    await startAs(page, 'Priya')
    await ask(page, QUESTIONS.silence)
    await expect(stopButton(page)).toBeVisible()
    await expectNothingSideways(page)
    // Stop takes Ask's place, at the end of its row.
    const form = await boxOf(composerForm(page))
    const stop = await boxOf(stopButton(page))
    expect(form.x + form.width - (stop.x + stop.width)).toBeLessThanOrEqual(20)
    expect((await scan(page)).violations).toEqual([])
    await stopButton(page).click()
    await expect(page.getByText('Stopped', { exact: true })).toBeVisible()
    await expectNothingSideways(page)
    // The server saves the stopped turn a moment later, and a question sent before is refused.
    await waitForTurnSaved(page, 0)

    await ask(page, QUESTIONS.midStreamError)
    await expect(page.getByRole('alert')).toBeVisible()
    await expectNothingSideways(page)
    // The alert wraps inside the message, with Retry in it.
    const alert = await boxOf(page.getByRole('alert'))
    const message = await boxOf(assistantMessage(page, 1))
    expect(alert.x).toBeGreaterThanOrEqual(message.x - 1)
    expect(alert.x + alert.width).toBeLessThanOrEqual(message.x + message.width + 1)
    await expect(page.getByRole('alert').getByRole('button', { name: 'Retry' })).toBeVisible()
    expect((await scan(page)).violations).toEqual([])
  })

  test("the composer's warning, hint, and limit lines wrap inside the column", async ({ page }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await composerBox(page).fill('a'.repeat(1962))
    await expect(composerLine(page)).toHaveText('1,962 of 2,000 characters')
    await expectNothingSideways(page)
    await composerBox(page).fill('a'.repeat(2001))
    await expect(composerLine(page)).toContainText('Shorten your question to send it.')
    await expectNothingSideways(page)
    expect((await scan(page)).violations).toEqual([])
    await composerBox(page).fill('123-45-6789')
    await composerBox(page).press('Enter')
    await expect(composerLine(page)).toHaveText(PERSONAL_DATA_TEXT)
    await expectNothingSideways(page)
    expect((await scan(page)).violations).toEqual([])
  })

  for (const kind of ['sandbox', 'daily'] as const) {
    test(`the ${kind} banner wraps to several lines, and the composer is off (STUB: the conversation GET)`, async ({
      page,
    }) => {
      await startAs(page, 'Priya')
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      await stubConversation(page, (body) => {
        const message = kind === 'sandbox' ? BUDGET_SANDBOX_TEXT : BUDGET_DAILY_TEXT
        body.budget = { ...body.budget, banner: { kind, message } }
      })
      await page.reload()
      const banner = page.locator('[data-slot="banner"]').filter({ hasText: 'Lifeline' })
      await expect(banner).toBeVisible()
      await expectNothingSideways(page)
      const bannerBox = await boxOf(banner)
      expect(bannerBox.x + bannerBox.width).toBeLessThanOrEqual(390 + 1)
      // Several lines of text (the message is about 190 characters).
      const text = await boxOf(banner.getByRole('link', { name: 'call 911' }).locator('xpath=..'))
      expect(text.height).toBeGreaterThan(40)
      if (kind === 'sandbox') {
        // "Start a new sandbox" moves under the text.
        const action = await boxOf(banner.getByRole('button', { name: 'Start a new sandbox' }))
        expectOnLaterRow(text, action)
      }
      await expect(composerBox(page)).toBeDisabled()
      expect((await scan(page)).violations).toEqual([])
    })
  }

  test('the long-conversation notice wraps above the box, with its button inside it (STUB: the conversation GET)', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await stubConversation(page, (body) => {
      body.longHistory = true
    })
    await page.reload()
    const notice = page.locator('[data-slot="composer-notice"]')
    await expect(notice).toBeVisible()
    await expectNothingSideways(page)
    const noticeBox = await boxOf(notice)
    const button = await boxOf(notice.getByRole('button', { name: 'Start a new conversation' }))
    expect(button.x + button.width).toBeLessThanOrEqual(noticeBox.x + noticeBox.width + 1)
    expect(button.y + button.height).toBeLessThanOrEqual(noticeBox.y + noticeBox.height + 1)
    expect((await scan(page)).violations).toEqual([])
  })

  test('a citation opens a modal bottom sheet: focus inside, the page behind inert, Close and Escape dismiss it and return focus to the marker', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const marker = assistantMessage(page).locator('[data-slot="citation-marker"]').first()

    await marker.click()
    const sheet = page.getByRole('dialog', { name: 'Sick leave' })
    await expect(sheet).toBeVisible()
    await expect(page).toHaveURL(/source=4\.3/)
    // It covers the page from near the top to the bottom edge, the full width.
    const box = await boxOf(sheet)
    expect(box.width).toBeGreaterThanOrEqual(389)
    expect(box.y).toBeLessThanOrEqual(24)
    expect(Math.abs(box.y + box.height - 844)).toBeLessThanOrEqual(1)
    // Focus is inside it, on the title, and the page behind is hidden from assistive technology.
    await expect(sheet.getByRole('heading', { level: 2, name: 'Sick leave' })).toBeFocused()
    await expect(composerBox(page)).toHaveCount(0)
    await expect(page.getByRole('navigation', { name: 'Main' })).toHaveCount(0)
    await expect(sheet.getByRole('link', { name: /Open in handbook/ })).toBeVisible()
    expect((await scan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])
    // Tab stays in the sheet.
    for (let i = 0; i < 6; i += 1) {
      await page.keyboard.press('Tab')
      expect(
        await page.evaluate(() => document.activeElement?.closest('[role="dialog"]') != null),
      ).toBe(true)
    }

    await sheet.getByRole('button', { name: 'Close passage' }).click()
    await expect(sheet).toHaveCount(0)
    await expect(page).toHaveURL('/ask')
    await expect(marker).toBeFocused()
    await expect(composerBox(page)).toBeVisible()

    await marker.click()
    await expect(sheet).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(sheet).toHaveCount(0)
    await expect(marker).toBeFocused()
  })

  test("a swipe down on the sheet's header dismisses it", async ({ page }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const marker = assistantMessage(page).locator('[data-slot="citation-marker"]').first()
    await marker.click()
    const sheet = page.getByRole('dialog', { name: 'Sick leave' })
    await expect(sheet).toBeVisible()
    const handle = await boxOf(page.locator('[data-slot="bottom-sheet-handle"]'))
    const x = handle.x + handle.width / 2
    const y = handle.y + handle.height / 2
    await page.mouse.move(x, y)
    await page.mouse.down()
    for (let step = 1; step <= 10; step += 1) await page.mouse.move(x, y + step * 20)
    await page.mouse.up()
    await expect(sheet).toHaveCount(0)
    await expect(page).toHaveURL('/ask')
    await expect(marker).toBeFocused()
  })
})

test.describe('at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('the thread is 760 px, assistant messages 680, and the header holds the retention line, the button, and the pill on one row', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await expectNothingSideways(page)
    // The measure is 760 px. The sheet's two 1px borders take 2 px of the 840 px beside the rail,
    // so the page's thread is 758 (the design draws it without the borders). Assistant messages
    // are capped at 680 and fill it.
    const measure = (await boxOf(thread(page))).width
    expect(measure).toBeGreaterThanOrEqual(756)
    expect(measure).toBeLessThanOrEqual(760)
    expect(Math.round((await boxOf(assistantMessage(page))).width)).toBe(680)

    // The retention line is in the header here, not under the composer.
    await expect(retentionLines(page).locator('visible=true')).toHaveCount(1)
    const header = page.locator('[data-slot="conversation-header"]')
    await expect(header.locator('[data-slot="retention-line"]')).toBeVisible()
    const pill = await boxOf(header.locator('[data-slot="sandbox-indicator"]'))
    const button = await boxOf(header.getByRole('button', { name: 'Start a new conversation' }))
    // The button keeps its text here, and the pill is beside it.
    expect(button.width).toBeGreaterThan(100)
    expectSameRow(button, pill, 14)
    // The header row never overflows, and the retention line wraps at most once (the fit is a
    // fraction of a pixel on macOS, and a few pixels short on Linux's wider fonts).
    expect(await header.evaluate((row) => row.scrollWidth - row.clientWidth)).toBeLessThanOrEqual(0)
    expect((await boxOf(header.locator('[data-slot="retention-line"]'))).height).toBeLessThan(44)

    // The disclosure sits beside Ask on one row, and the right rail shows.
    const disclosure = await boxOf(page.getByText(/Open Door is an AI assistant\./).first())
    expectSameRow(disclosure, await boxOf(askButton(page)), 14)
    await expect(page.getByRole('complementary', { name: 'Sandbox status' })).toBeVisible()
    expect((await scan(page)).violations).toEqual([])
  })

  test("the docked panel is 420 px beside the thread, in the rail's place, and the rail hides while it is open", async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const rail = page.getByRole('complementary', { name: 'Sandbox status' })
    expect((await boxOf(rail)).width).toBeGreaterThanOrEqual(339)
    const railBox = await boxOf(rail)

    await assistantMessage(page).locator('[data-slot="citation-marker"]').first().click()
    await expect(passage(page)).toBeVisible()
    await expect(rail).toHaveCount(0)
    const panel = await boxOf(page.locator('[data-slot="source-panel"]'))
    expect(Math.round(panel.width)).toBe(420)
    // Beside the thread, to its right, both inside the window.
    const threadBox = await boxOf(thread(page))
    expect(panel.x).toBeGreaterThanOrEqual(threadBox.x + threadBox.width - 1)
    expect(panel.x + panel.width).toBeLessThanOrEqual(1440)
    // It ends where the rail ended, at the sheet's right edge, and is wider than the rail.
    expect(Math.abs(panel.x + panel.width - (railBox.x + railBox.width))).toBeLessThanOrEqual(1)
    // The panel is 80 px wider than the rail, so the thread gives up 80 px of its 758 (about
    // 678), and the assistant's messages fill it.
    expect(threadBox.width).toBeGreaterThanOrEqual(660)
    expect(threadBox.width).toBeLessThanOrEqual(680)
    expect((await boxOf(assistantMessage(page))).width).toBeLessThanOrEqual(threadBox.width + 1)
    await expectNothingSideways(page)
    expect((await scan(page)).violations).toEqual([])
  })

  test('the docked panel stays a column down to 1280 px, and below it the passage is a modal sheet', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const marker = assistantMessage(page).locator('[data-slot="citation-marker"]').first()

    await page.setViewportSize({ width: 1280, height: 800 })
    await marker.click()
    await expect(passage(page)).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    expect(Math.round((await boxOf(page.locator('[data-slot="source-panel"]'))).width)).toBe(420)
    await expectNothingSideways(page)

    // Crossing the line with the passage open swaps the column for the sheet, same passage.
    await page.setViewportSize({ width: 1279, height: 800 })
    await expect(page.getByRole('dialog', { name: 'Sick leave' })).toBeVisible()
    await expect(passage(page)).toHaveCount(0)
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })
})

test.describe('at 1200 px, below the docking point', () => {
  test.use({ viewport: { width: 1200, height: 800 } })

  test('a citation opens the modal bottom sheet, not a column, and the thread keeps its width', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await expectNothingSideways(page)
    const before = await boxOf(thread(page))
    const marker = assistantMessage(page).locator('[data-slot="citation-marker"]').first()
    await marker.click()
    const sheet = page.getByRole('dialog', { name: 'Sick leave' })
    await expect(sheet).toBeVisible()
    await expect(sheet.getByRole('heading', { level: 2, name: 'Sick leave' })).toBeFocused()
    await expect(passage(page)).toHaveCount(0)
    expect((await boxOf(thread(page))).width).toBe(before.width)
    await expect(composerBox(page)).toHaveCount(0)
    expect((await scan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])

    await sheet.getByRole('button', { name: 'Close passage' }).click()
    await expect(sheet).toHaveCount(0)
    await expect(marker).toBeFocused()
  })
})
