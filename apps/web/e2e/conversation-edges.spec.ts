import { expect, test } from '@playwright/test'
import {
  askAndWaitForAnswer,
  askButton,
  assistantMessages,
  composerBox,
  composerLine,
  countTurnRequests,
  currentConversation,
  QUESTIONS,
  userMessages,
} from './conversation-helpers'
import { holdNextTurnStream, pushSearchSteps } from './held-stream'
import { greetingHeading, holdRequests, problem, startAs } from './helpers'

// The conversation page's four edge cases that the v0.4.0 release review parked (docs/BACKLOG.md,
// Phase 6): a send to a conversation that is gone, "Start a new conversation" with a source panel
// open, a send racing that click, and a second Enter while a send waits for the new conversation.
// The page is the real one against the real API with the scripted model. The 404 and the held
// requests are the only stubs, named in each test.

const SEND_FAILED = 'Something went wrong sending that.'
const TURNS = '**/api/v1/assistant/conversations/*/turns'
const CONVERSATIONS = '**/api/v1/assistant/conversations'

test.describe('a send to a conversation that is gone (STUB: one 404 on the turn POST)', () => {
  test('keeps the page up and the focus in the composer, says the send failed, and the next question works', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    // Records whether the page ever dropped to its "Loading…" line.
    await page.evaluate(() => {
      const seen = { loading: false }
      ;(window as unknown as { __seen: typeof seen }).__seen = seen
      new MutationObserver(() => {
        if (document.body.textContent?.includes('Loading…')) seen.loading = true
      }).observe(document.body, { subtree: true, childList: true, characterData: true })
    })
    let refused = 0
    await page.route(TURNS, (route) => {
      if (route.request().method() !== 'POST' || refused > 0) return route.fallback()
      refused++
      return route.fulfill({
        status: 404,
        contentType: 'application/problem+json',
        body: problem(404, 'Not Found'),
      })
    })

    await composerBox(page).fill(QUESTIONS.otherSection)
    await composerBox(page).press('Enter')
    await expect(composerLine(page)).toHaveText(SEND_FAILED)
    await expect(composerBox(page)).toBeFocused()
    // The conversation stays on the page, and the draft stays in the box.
    await expect(userMessages(page)).toHaveCount(1)
    await expect(composerBox(page)).toHaveValue(QUESTIONS.otherSection)
    expect(
      await page.evaluate(() => (window as unknown as { __seen: { loading: boolean } }).__seen),
    ).toEqual({ loading: false })

    // The next question goes through, to the conversation the server has.
    const sent = countTurnRequests(page)
    await composerBox(page).press('Enter')
    await expect(userMessages(page)).toHaveCount(2)
    await expect(assistantMessages(page)).toHaveCount(2)
    expect(sent).toHaveLength(1)
    expect(refused).toBe(1)
  })
})

test.describe('"Start a new conversation" with a source panel open (1440 px)', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  const panel = (page: import('@playwright/test').Page) =>
    page.getByRole('complementary', { name: 'Handbook passage' })

  /** The history entries from the first to the current one, as paths (Chromium's Navigation API). */
  const historyUpToHere = (page: import('@playwright/test').Page) =>
    page.evaluate(() => {
      const nav = (
        window as unknown as {
          navigation: { entries(): { url: string }[]; currentEntry: { index: number } }
        }
      ).navigation
      return nav
        .entries()
        .slice(0, nav.currentEntry.index + 1)
        .map((entry) => entry.url.replace(location.origin, ''))
    })

  async function openSourceThenStartOver(page: import('@playwright/test').Page) {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await assistantMessages(page).first().locator('[data-slot="citation-marker"]').first().click()
    await expect(panel(page)).toBeVisible()
    await expect(page).toHaveURL(/\?source=/)
    await page.getByRole('button', { name: 'Start a new conversation' }).click()
    await expect(greetingHeading(page, 'Priya')).toBeVisible()
    await expect(page).toHaveURL('/ask')
  }

  test('Back goes to the page before the assistant: no step is left that changes nothing', async ({
    page,
  }) => {
    await openSourceThenStartOver(page)
    // The history up to here is the landing page and the assistant. The old behavior replaced the
    // panel's entry instead of going back over it, which left a second "/ask" for Back to stop at.
    expect(await historyUpToHere(page)).toEqual(['/', '/ask'])
  })

  test('Forward does not reopen the panel on the new conversation', async ({ page }) => {
    await openSourceThenStartOver(page)
    await page.goForward()
    await expect(page).not.toHaveURL(/source=/)
    await expect(panel(page)).toHaveCount(0)
    // A question on the new conversation shows no panel either.
    await askAndWaitForAnswer(page, QUESTIONS.decline)
    await expect(panel(page)).toHaveCount(0)
    await expect(page).not.toHaveURL(/source=/)
  })
})

test.describe('a send racing "Start a new conversation"', () => {
  test('an answer already streaming is dropped, and the next question goes to the new conversation (STUB: held stream)', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const stream = await holdNextTurnStream(page)
    await composerBox(page).fill(QUESTIONS.otherSection)
    await composerBox(page).press('Enter')
    await pushSearchSteps(stream)
    await expect(assistantMessages(page)).toHaveCount(2)
    await page.getByRole('button', { name: 'Start a new conversation' }).click()
    await expect(greetingHeading(page, 'Priya')).toBeVisible()
    await expect(userMessages(page)).toHaveCount(0)
    // A late event from the dropped stream shows nothing.
    await stream.push('text.delta', { text: 'A late word.' })
    await expect(page.getByText('A late word.')).toHaveCount(0)

    await askAndWaitForAnswer(page, QUESTIONS.decline)
    const current = await currentConversation(page)
    expect(current?.turns).toHaveLength(1)
  })

  test('a question typed while the new conversation is being created goes to it, not the old one (STUB: held create)', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const oldTurns = (await currentConversation(page))?.turns.length
    expect(oldTurns).toBe(1)
    const release = await holdRequests(page, CONVERSATIONS, 'POST')
    await page.getByRole('button', { name: 'Start a new conversation' }).first().click()
    await composerBox(page).fill(QUESTIONS.decline)
    await composerBox(page).press('Enter')
    const sent = countTurnRequests(page)
    await page.waitForTimeout(200)
    expect(sent).toEqual([])
    release()
    await expect(userMessages(page)).toHaveCount(1)
    await expect(userMessages(page)).toContainText(QUESTIONS.decline)
    // The new conversation holds the one question, and the old one is untouched.
    await expect.poll(async () => (await currentConversation(page))?.turns.length).toBe(1)
    expect(sent).toHaveLength(1)
  })
})

test.describe('a second Enter while a send waits for the new conversation (STUB: held create)', () => {
  test('shows Ask busy from the first Enter, ignores the second, and sends one question', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const release = await holdRequests(page, CONVERSATIONS, 'POST')
    await page.getByRole('button', { name: 'Start a new conversation' }).first().click()
    await composerBox(page).fill(QUESTIONS.decline)
    const sent = countTurnRequests(page)
    await composerBox(page).press('Enter')
    await expect(askButton(page)).toHaveAttribute('aria-busy', 'true')
    await composerBox(page).press('Enter')
    await expect(askButton(page)).toHaveAttribute('aria-busy', 'true')
    // Nothing else changed: the draft is there, and nothing was sent.
    await expect(composerBox(page)).toHaveValue(QUESTIONS.decline)
    await expect(composerLine(page)).toHaveCount(0)
    expect(sent).toEqual([])
    release()
    await expect(userMessages(page)).toHaveCount(1)
    await expect(assistantMessages(page)).toHaveCount(1)
    await expect(askButton(page)).not.toHaveAttribute('aria-busy', 'true')
    expect(sent).toHaveLength(1)
  })
})
