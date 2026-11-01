import { expect, test, type Locator, type Page } from '@playwright/test'
import { ask, askAndWaitForAnswer, composerBox } from './conversation-helpers'
import { holdTurnCompletion } from './held-stream'
import { scan, startAs } from './helpers'
import {
  cards,
  expireProposal,
  newestProposalId,
  railLink,
  rowsOn,
  scrollsSideways,
  skipUnlessScriptedDayCounts,
  switchPersona,
} from './time-off-helpers'

// Screen 10 (confirm cards) in the real app: the scripted model asks for a card ("book next
// friday"), the real API stores it, and a person confirms it. The card's variants and states are
// proved one by one in gallery-confirm-card.spec.ts; these tests prove what only the page adds:
// the facts come from the API, the card waits for its turn to be read, a press reaches the server
// and focus lands where the notes say, a reload shows the same state, and the rail follows.

const BOOK = 'book next friday'
const UUID_PATTERN = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i

const card = (page: Page, index = 0) => cards(page).nth(index)
const confirmButton = (host: Locator) => host.getByRole('button', { name: /^Confirm: / })
const dismissButton = (host: Locator) => host.getByRole('button', { name: /^Dismiss, / })
const thread = (page: Page) => page.locator('[data-slot="conversation-thread"]')

/** What a fact row of the card says, such as "Dates". */
const fact = (host: Locator, label: string) =>
  host
    .locator('dt', { hasText: new RegExp(`^${label}$`) })
    .locator('xpath=following-sibling::dd[1]')

test.describe('at 1440 px', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('Priya books in chat: the card waits for its answer, a double click makes one request and one outcome line, and the rail and a reload follow', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await skipUnlessScriptedDayCounts(test, page, BOOK)
    const pending = railLink(page, 'requests? pending')
    const available = railLink(page, 'PTO available')
    await expect(pending).toHaveAccessibleName(/^0 requests pending\s?\. Open Time off$/)
    const availableBefore = await available.ariaSnapshot()
    await askAndWaitForAnswer(page, "what's my balance")

    // The real turn runs, but its closing event is held, so the card exists while the answer is
    // still being written: Confirm waits (disabled), Dismiss works.
    const release = await holdTurnCompletion(page)
    await ask(page, BOOK)
    await expect(card(page)).toBeVisible()
    await expect(card(page).getByRole('heading', { name: 'Book PTO' })).toBeVisible()
    await expect(confirmButton(card(page))).toHaveAttribute('aria-disabled', 'true')
    await expect(card(page).getByText('Wait for the answer to finish')).toBeVisible()
    await expect(dismissButton(card(page))).toBeEnabled()
    await release()
    await expect(confirmButton(card(page))).not.toHaveAttribute('aria-disabled', 'true')
    await expect(card(page).getByText('Wait for the answer to finish')).toHaveCount(0)

    // Every fact is the API's: the card's amount is the label the conversation read carries, and
    // the AI tag and expiry are there while it waits.
    const stored = await page.evaluate(async () => {
      const response = await fetch('/api/v1/assistant/conversations/current')
      const body = (await response.json()) as {
        turns: { proposals: { card: { amountLabel: string; startDate: string } }[] }[]
      }
      return body.turns.flatMap((turn) => turn.proposals).at(-1)!.card
    })
    await expect.soft(card(page).locator('strong')).toHaveText(stored.amountLabel)
    await expect.soft(fact(card(page), 'Type')).toHaveText('PTO')
    await expect
      .soft(card(page).getByText('Proposed by the AI. Nothing happens until you confirm.'))
      .toBeVisible()
    await expect.soft(card(page).getByText(/^Expires at \d{1,2}:\d{2} [AP]M$/)).toBeVisible()
    const dates = (await fact(card(page), 'Dates').textContent())!

    // Show your work names what each turn did in words, and no id shows anywhere in the thread.
    for (const button of await page.getByRole('button', { name: 'Show your work' }).all()) {
      await button.click()
    }
    await expect.soft(page.getByText('Checked your time off')).toBeVisible()
    await expect.soft(page.getByText('Prepared a confirm card')).toBeVisible()
    expect.soft(await thread(page).innerText()).not.toMatch(UUID_PATTERN)
    expect.soft(await thread(page).evaluate((el) => el.innerHTML)).not.toMatch(UUID_PATTERN)

    // A double click on Confirm books once. Focus lands on the outcome line.
    await confirmButton(card(page)).dblclick()
    const outcome = card(page).locator('output')
    await expect(outcome).toContainText('Requested. Marcus Bell will review it.')
    await expect(outcome).toBeFocused()
    await expect(page.locator('[data-slot="confirm-card"] output')).toHaveCount(1)
    await expect(card(page).locator('[data-slot="status-badge"]')).toHaveText(
      'Waiting for approval',
    )
    await expect(confirmButton(card(page))).toHaveCount(0)
    await expect(dismissButton(card(page))).toHaveCount(0)
    await expect(card(page).getByRole('link', { name: 'View in Time off' })).toBeVisible()

    // The rail follows from the summary: one request pending, and PTO available went down.
    await expect(pending).toHaveAccessibleName(/^1 request pending\s?\. Open Time off$/)
    expect(await available.ariaSnapshot()).not.toBe(availableBefore)

    // A reload shows the executed card, not a new one.
    await page.reload()
    await expect(card(page).getByText('Requested. Marcus Bell will review it.')).toBeVisible()
    await expect(cards(page)).toHaveCount(1)
    await expect(confirmButton(card(page))).toHaveCount(0)

    // "View in Time off" opens the page, and the double click made one request, not two.
    await card(page).getByRole('link', { name: 'View in Time off' }).click()
    await expect(page).toHaveURL('/time-off')
    await expect(rowsOn(page, dates)).toHaveCount(1)
    await expect(rowsOn(page, dates)).toContainText('Waiting for approval')
  })

  test('a dismissed card says so and stays dismissed; a newer card replaces an older one', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await skipUnlessScriptedDayCounts(test, page, BOOK)
    // The second "book next friday" proposes the same days. The scripted model's second card is
    // valid (a pending card is not a booking), so the product replaces the first: it reads
    // "Replaced by a newer card." and only the newest can be confirmed.
    await askAndWaitForAnswer(page, BOOK)
    await askAndWaitForAnswer(page, BOOK)
    await expect(cards(page)).toHaveCount(2)
    await expect(card(page, 0)).toContainText('Replaced by a newer card. Nothing was changed.')
    await expect(confirmButton(card(page, 0))).toHaveCount(0)
    await expect(confirmButton(card(page, 1))).toBeVisible()

    await dismissButton(card(page, 1)).click()
    const line = card(page, 1).getByText('You dismissed this. Nothing was changed.')
    await expect(line).toBeVisible()
    await expect(confirmButton(card(page, 1))).toHaveCount(0)
    await expect(dismissButton(card(page, 1))).toHaveCount(0)

    await page.reload()
    await expect(cards(page)).toHaveCount(2)
    await expect(card(page, 0)).toContainText('Replaced by a newer card.')
    await expect(card(page, 1)).toContainText('You dismissed this. Nothing was changed.')
    await expect(page.getByRole('button', { name: /^(Confirm|Dismiss)/ })).toHaveCount(0)
    // Nothing was booked.
    await page.getByRole('link', { name: 'Time off', exact: true }).first().click()
    await expect(page.getByText('No upcoming time off.')).toBeVisible()
  })

  test('a card that expired answers Confirm with the expired state, "Ask again" keeps the question, and a reload still shows it', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await skipUnlessScriptedDayCounts(test, page, BOOK)
    await askAndWaitForAnswer(page, BOOK)
    await expect(card(page)).toBeVisible()
    await expireProposal(await newestProposalId(page))

    // The server refuses (409) and the read marks the card expired. Focus was on Confirm, inside
    // the card, so it moves to "Ask again".
    await confirmButton(card(page)).click()
    await expect(
      card(page).getByText('This card expired after 15 minutes. Nothing was changed.'),
    ).toBeVisible()
    const askAgain = card(page).getByRole('button', { name: 'Ask again' })
    await expect(askAgain).toBeFocused()
    await expect(confirmButton(card(page))).toHaveCount(0)

    // "Ask again" puts the question back in the composer and focuses it, without sending it.
    await askAgain.click()
    await expect(composerBox(page)).toHaveValue(BOOK)
    await expect(composerBox(page)).toBeFocused()
    await expect(cards(page)).toHaveCount(1)

    await page.reload()
    await expect(card(page)).toContainText('This card expired after 15 minutes.')
    await expect(card(page).getByRole('button', { name: 'Ask again' })).toBeVisible()
  })

  test('axe finds nothing on a pending card or on an executed one', async ({ page }) => {
    test.slow()
    // The executed line fades in, and axe would read its colors halfway through.
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await startAs(page, 'Priya')
    await skipUnlessScriptedDayCounts(test, page, BOOK)
    await askAndWaitForAnswer(page, BOOK)
    await expect(confirmButton(card(page))).toBeVisible()
    expect((await scan(page, [], ['[data-slot="conversation-thread"]'])).violations).toEqual([])
    await confirmButton(card(page)).click()
    await expect(card(page).getByText('Requested. Marcus Bell will review it.')).toBeVisible()
    expect((await scan(page, [], ['[data-slot="conversation-thread"]'])).violations).toEqual([])
  })
})

test("a card belongs to the person who asked: Marcus never sees Priya's, and she finds it still pending", async ({
  page,
}) => {
  await startAs(page, 'Priya')
  await skipUnlessScriptedDayCounts(test, page, BOOK)
  await askAndWaitForAnswer(page, BOOK)
  await expect(confirmButton(card(page))).toBeVisible()

  await switchPersona(page, 'Marcus')
  await expect(page.getByRole('textbox', { name: 'Ask Open Door' })).toBeVisible()
  await expect(cards(page)).toHaveCount(0)
  await expect(page.getByText('Book PTO')).toHaveCount(0)

  await switchPersona(page, 'Priya')
  await expect(card(page).getByRole('heading', { name: 'Book PTO' })).toBeVisible()
  await expect(card(page)).toHaveAttribute('data-state', 'pending')
  await expect(confirmButton(card(page))).toBeEnabled()
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('a card does not scroll the page sideways, and Confirm and Dismiss sit side by side', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await skipUnlessScriptedDayCounts(test, page, BOOK)
    await askAndWaitForAnswer(page, BOOK)
    await expect(confirmButton(card(page))).toBeVisible()
    expect(await scrollsSideways(page)).toBe(false)
    const confirm = (await confirmButton(card(page)).boundingBox())!
    const dismiss = (await dismissButton(card(page)).boundingBox())!
    expect(Math.abs(confirm.y - dismiss.y)).toBeLessThanOrEqual(1)
    expect(confirm.x + confirm.width).toBeLessThanOrEqual(dismiss.x)
    await confirmButton(card(page)).click()
    await expect(card(page).getByText('Requested. Marcus Bell will review it.')).toBeVisible()
    expect(await scrollsSideways(page)).toBe(false)
  })
})
