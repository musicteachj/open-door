import type { ConversationOut } from '../src/api/generated'
import { expect, test } from './fixtures'
import { ask, QUESTIONS, stubConversation } from './conversation-helpers'
import { scan, startAs } from './helpers'

// Phase 8's review: a conversation whose words no longer open still shows the crisis panel one of
// its turns had (invariant 6). Damaging a stored value takes the database owner, so the read is
// stubbed: the real crisis turn's panel moves to the response's `escalation`, as the API sends it
// for an unreadable conversation, and the turns go.

const PANEL = 'Reach a person right now'

test.describe('an unreadable conversation that had a crisis panel (STUB: GET)', () => {
  // The page can still be refetching the stubbed read when a test ends.
  test.afterEach(async ({ page }) => {
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  })

  for (const width of [1440, 390]) {
    test(`keeps the panel with the "can't be shown" line at ${width} px, axe clean`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 })
      await startAs(page, 'Priya')
      await ask(page, QUESTIONS.crisis)
      await expect(page.getByRole('region', { name: PANEL })).toBeVisible({ timeout: 30_000 })
      await stubConversation(page, (stored) => {
        const body = stored as unknown as ConversationOut
        const escalation = body.turns.find(
          (turn) => turn.escalation?.kind === 'crisis',
        )!.escalation!
        body.escalation = { ...escalation, offerCase: false }
        body.turns = []
        body.unreadable = true
        body.historyTooLong = true
        body.longHistory = true
      })
      await page.reload()

      await expect(page.getByText("This conversation can't be shown.")).toBeVisible()
      const panel = page.getByRole('region', { name: PANEL })
      await expect(panel).toBeVisible()
      await expect(panel).toContainText('988')
      await expect(page.locator('[data-slot="user-message"]')).toHaveCount(0)
      expect((await scan(page)).violations).toEqual([])
      await page.screenshot({ path: test.info().outputPath(`unreadable-crisis-${width}.png`) })
    })
  }
})
