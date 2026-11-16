import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { watchCsp } from '../fixtures'

// The browser half of the live check (Phase 8, Task 46; scripts/prod-local/live_check.py runs it).
// Against the production image with its real Content Security Policy, and Cloudflare's real
// Turnstile script with the always-pass test key: start a sandbox as Priya, ask a policy question
// and wait for its cited answer, book this Friday and confirm the card. Every CSP violation the page
// reports is collected, and there must be none. The questions are live_check.py's PHRASES.

const OUT = process.env.LIVE_OUT ?? '/tmp/od-live-check'
const TURN_TIMEOUT_MS = 120_000

test('the production image, end to end', async ({ context, page }) => {
  // The browser suite's own CSP watch (the event and the console's reports), without its fake
  // Turnstile: this check runs Cloudflare's real script, with the test key.
  const seenViolations = await watchCsp(context)
  const feedback = page.locator('[data-slot="feedback"], [data-slot="feedback-thanks"]')
  const composer = page.getByRole('textbox', { name: 'Ask Open Door' })

  await page.goto('/')
  // Starting a sandbox runs Cloudflare's check (the real script, the test key).
  await page.getByRole('button', { name: /^Priya / }).click()
  await expect(page).toHaveURL('/ask', { timeout: 60_000 })

  await expect(composer).toBeEditable()
  await composer.fill('How many sick days do I get?')
  await composer.press('Enter')
  await expect(feedback).toHaveCount(1, { timeout: TURN_TIMEOUT_MS })
  const source = page.locator('[data-slot="source-chip"]').first()
  await expect(source, 'the answer cites the handbook').toBeVisible()
  const cited = (await source.textContent()) ?? ''

  await composer.fill('Book this Friday off.')
  await composer.press('Enter')
  await expect(feedback).toHaveCount(2, { timeout: TURN_TIMEOUT_MS })
  const confirm = page.getByRole('button', { name: /^Confirm: book PTO on / })
  await expect(confirm, 'the answer offers a confirm card').toBeVisible()
  await confirm.click()
  const outcome = page.locator('[data-slot="confirm-card"] output').first()
  await expect(outcome).toContainText('Requested.')

  // Let a violation queued by the last action reach the binding before it is read.
  await page.waitForTimeout(50)
  const violations = seenViolations()
  writeFileSync(
    join(OUT, 'browser.json'),
    `${JSON.stringify({ cited, outcome: await outcome.textContent(), violations }, null, 2)}\n`,
  )
  expect(violations, 'no Content Security Policy violation').toEqual([])
})
