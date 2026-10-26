import { expect, test, type Page } from '@playwright/test'
import {
  greetingHeading,
  HOUR_MS,
  holdRequests,
  MINUTE_MS,
  MODAL_OVERLAY_RULES,
  scan,
  setSandboxLeft,
  startAs,
  themeColor,
} from './helpers'

// One test per acceptance criterion in docs/design/screens/02-app-shell/notes.md. "Matches the
// screenshots at 1440 px" is the capture report's job (make captures). "Sign out ends the session
// and returns to the landing page" is proved by session.spec.ts, which signs out through the real
// persona menu and checks the 204 and the redirect.

const switcher = (page: Page) => page.getByRole('button', { name: /^Switch persona/ })
const navLinks = (page: Page) => page.getByRole('navigation', { name: 'Main' }).getByRole('link')
const TOAST = 'Now viewing as Marcus Bell.'
const toast = (page: Page) => page.locator('[data-slot="toast"]')

test.describe('each persona sees exactly the nav items above, and an item appears only once its page exists', () => {
  // Phases 2, 3, and 5 build Ask, Time off, Directory, Handbook, and Approvals (managers). Cases
  // and Console (HR) arrive in Phase 6, and "How it's built" in Phase 7. Marcus's Approvals item
  // carries his count (the seed has Zara's request waiting), so its text reads "Approvals1".
  for (const name of ['Priya', 'Mateo', 'Marcus', 'Dana'] as const) {
    test(name, async ({ page }) => {
      await startAs(page, name)
      await expect(navLinks(page)).toHaveText(
        name === 'Marcus'
          ? ['Ask', 'Time off', 'Directory', 'Handbook', 'Approvals1']
          : ['Ask', 'Time off', 'Directory', 'Handbook'],
      )
      await expect(page.getByRole('link', { name: "How it's built" })).toHaveCount(0)
      const approvals = page.getByRole('link', { name: /^Approvals/ })
      if (name === 'Marcus') await expect(approvals).toHaveAccessibleName('Approvals, 1 waiting')
      else await expect(approvals).toHaveCount(0)
      for (const absent of ['Cases', 'Console']) {
        await expect(page.getByRole('link', { name: new RegExp(`^${absent}`) })).toHaveCount(0)
      }
      expect((await scan(page)).violations).toEqual([])
    })
  }
})

test('the persona switcher names the full title, and the persona menu works by keyboard: it opens on the current persona, the arrow keys move, and Escape closes it and returns focus to the switcher', async ({
  page,
}) => {
  await startAs(page, 'Priya')
  await expect(switcher(page)).toHaveAccessibleName(
    'Switch persona. Current: Priya Raman, Visual Merchandiser',
  )
  const item = (name: string) => page.getByRole('menuitemradio', { name: new RegExp(`^${name} `) })

  // Tab to the switcher: Ask, Time off, Directory, Handbook, then the switcher.
  for (let i = 0; i < 5; i += 1) await page.keyboard.press('Tab')
  await expect(switcher(page)).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('menu')).toBeVisible()
  await expect(item('Priya')).toBeFocused()
  await expect(item('Priya')).toHaveAttribute('aria-checked', 'true')

  await page.keyboard.press('ArrowDown')
  await expect(item('Mateo')).toBeFocused()
  await page.keyboard.press('ArrowDown')
  await expect(item('Marcus')).toBeFocused()
  await page.keyboard.press('ArrowUp')
  await expect(item('Mateo')).toBeFocused()

  await page.keyboard.press('Escape')
  await expect(page.getByRole('menu')).toBeHidden()
  await expect(switcher(page)).toBeFocused()

  // The keyboard switches too, and the menu then opens on the new current persona.
  await page.keyboard.press('Enter')
  await expect(item('Priya')).toBeFocused()
  await page.keyboard.press('ArrowDown')
  await expect(item('Mateo')).toBeFocused()
  await page.keyboard.press('ArrowDown')
  await expect(item('Marcus')).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(greetingHeading(page, 'Marcus')).toBeVisible()
  await switcher(page).click()
  await expect(item('Marcus')).toBeFocused()
  await expect(item('Marcus')).toHaveAttribute('aria-checked', 'true')
})

test('the open persona menu has the design copy, no axe violations, and traps focus', async ({
  page,
}) => {
  await startAs(page, 'Priya')
  await switcher(page).click()
  const menu = page.getByRole('menu')
  await expect(menu).toBeVisible()
  await expect(menu).toContainText('View as')
  await expect(menu).toContainText('Switching starts a new conversation.')
  await expect(page.getByRole('menuitemradio')).toHaveCount(4)
  await expect(page.getByRole('menuitem', { name: 'Sign out' })).toBeVisible()
  expect((await scan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])
  for (let i = 0; i < 8; i += 1) {
    await page.keyboard.press('Tab')
    expect(
      await page.evaluate(() => document.activeElement?.closest('[role="menu"]') != null),
    ).toBe(true)
  }
})

test('choosing the current persona just closes the menu', async ({ page }) => {
  await startAs(page, 'Priya')
  let puts = 0
  page.on('request', (request) => {
    if (request.method() === 'PUT') puts += 1
  })
  await switcher(page).click()
  await page.getByRole('menuitemradio', { name: /^Priya / }).click()
  await expect(page.getByRole('menu')).toBeHidden()
  expect(puts).toBe(0)
})

test('switching changes persona with no dialog, empties the composer, shows the busy label on one line, and then shows the toast', async ({
  page,
}) => {
  await startAs(page, 'Priya')
  let dialogs = 0
  page.on('dialog', () => (dialogs += 1))
  const box = page.getByRole('textbox', { name: 'Ask Open Door' })
  await box.fill('How many sick days do I get?')

  const release = await holdRequests(page, '**/api/v1/session/persona', 'PUT')
  await page.addStyleTag({ content: '[data-slot="persona-switcher"] { width: 120px !important; }' })
  await switcher(page).click()
  await page.getByRole('menuitemradio', { name: /^Marcus / }).click()

  const busy = page.getByRole('button', { name: 'Switching to Marcus…' })
  await expect(busy).toBeVisible()
  await expect(busy).toHaveAttribute('aria-busy', 'true')
  // One line, even when squeezed: the switcher is narrowed until this label can't fit (a longer
  // name would be), so a wrapping label would be taller than one line. It truncates instead.
  const label = busy.getByText('Switching to Marcus…')
  const lineHeight = await label.evaluate((el) => parseFloat(getComputedStyle(el).lineHeight))
  expect((await label.boundingBox())!.height).toBeLessThanOrEqual(lineHeight + 1)
  expect(
    await label.evaluate((el) => ({
      cutOff: el.scrollWidth > el.clientWidth,
      overflow: getComputedStyle(el).textOverflow,
      wrap: getComputedStyle(el).whiteSpace,
    })),
  ).toEqual({ cutOff: true, overflow: 'ellipsis', wrap: 'nowrap' })
  // The menu won't open on top of a switch in flight, and there is no dialog of any kind.
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('alertdialog')).toHaveCount(0)
  expect((await scan(page)).violations).toEqual([])

  release()
  await expect(greetingHeading(page, 'Marcus')).toBeVisible()
  await expect(toast(page)).toContainText(TOAST)
  await expect(box).toHaveValue('')
  await expect(switcher(page)).toHaveAccessibleName(/Marcus Bell, Store Manager/)
  expect(dialogs).toBe(0)
})

test.describe('the toast', () => {
  async function switchToMarcus(page: Page) {
    await startAs(page, 'Priya')
    await switcher(page).click()
    await page.getByRole('menuitemradio', { name: /^Marcus / }).click()
    await expect(toast(page)).toContainText(TOAST)
  }

  test('is announced politely, with a success check and a close button, and closes after 6 seconds', async ({
    page,
  }) => {
    await page.clock.install()
    await switchToMarcus(page)
    // Radix announces a background toast through a polite status region.
    await expect(
      page.locator('[role="status"][aria-live="polite"]', { hasText: TOAST }),
    ).toHaveCount(1)
    await expect(toast(page).locator('[data-slot="toast-icon"]')).toBeVisible()
    await page.clock.fastForward(3_000)
    await expect(toast(page)).toBeVisible()
    await page.clock.fastForward(3_500)
    await expect(toast(page)).toBeHidden()
  })

  test('has no axe violations while showing', async ({ page }) => {
    await switchToMarcus(page)
    // Hovering holds it open for the scan.
    await toast(page).hover()
    expect((await scan(page)).violations).toEqual([])
  })

  test('closes with its button', async ({ page }) => {
    await switchToMarcus(page)
    await toast(page).getByRole('button', { name: 'Dismiss' }).click()
    await expect(toast(page)).toBeHidden()
  })

  test('pauses while hovered, and closes once the pointer leaves', async ({ page }) => {
    await page.clock.install()
    await switchToMarcus(page)
    await toast(page).hover()
    await page.clock.fastForward(20_000)
    await expect(toast(page)).toBeVisible()
    await page.mouse.move(5, 5)
    await page.clock.fastForward(7_000)
    await expect(toast(page)).toBeHidden()
  })

  test('pauses while focused, and closes once focus leaves', async ({ page }) => {
    await page.clock.install()
    await switchToMarcus(page)
    await toast(page).getByRole('button', { name: 'Dismiss' }).focus()
    await page.clock.fastForward(20_000)
    await expect(toast(page)).toBeVisible()
    await page.getByRole('button', { name: /^Switch persona/ }).focus()
    await page.clock.fastForward(7_000)
    await expect(toast(page)).toBeHidden()
  })
})

test.describe('the expiry banner', () => {
  const banner = (page: Page) => page.locator('[data-slot="banner"]')
  const indicator = (page: Page) => page.locator('[data-slot="sandbox-indicator"]:visible')

  test('appears at 3 hours or less, with the time as "2 h 50 min", and the rail shows the same time', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    // A fresh sandbox has about 24 hours, so there is no banner, and the pill shows whole hours.
    await expect(banner(page)).toHaveCount(0)
    await expect(indicator(page)).toHaveText(/^Sandbox resets in 2[34] h$/)

    await setSandboxLeft(page, 2 * HOUR_MS + 50 * MINUTE_MS)
    await expect(banner(page)).toContainText(
      "This sandbox resets in 2 h 50 min. Everything you've done here will be cleared.",
    )
    await expect(indicator(page)).toHaveText('Sandbox resets in 2 h 50 min')
    // The announcement region says it once.
    await expect(page.locator('[data-slot="shell-announcement"]')).toHaveText(
      /This sandbox resets in 2 h 50 min/,
    )
    expect((await scan(page)).violations).toEqual([])
  })

  test('appears at exactly 3 hours, and not a minute above', async ({ page }) => {
    await startAs(page, 'Priya')
    await setSandboxLeft(page, 3 * HOUR_MS + MINUTE_MS)
    await expect(indicator(page)).toHaveText('Sandbox resets in 3 h')
    await expect(banner(page)).toHaveCount(0)
    await setSandboxLeft(page, 3 * HOUR_MS)
    await expect(banner(page)).toContainText('This sandbox resets in 3 h.')
  })

  test('stays dismissed for the session', async ({ page }) => {
    await startAs(page, 'Priya')
    await setSandboxLeft(page, 2 * HOUR_MS + 50 * MINUTE_MS)
    await expect(banner(page)).toBeVisible()
    await banner(page).getByRole('button', { name: 'Dismiss for this session' }).click()
    await expect(banner(page)).toHaveCount(0)
    await page.reload()
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
    await expect(banner(page)).toHaveCount(0)
    // The pill is not the banner: it stays.
    await expect(indicator(page)).toHaveText('Sandbox resets in 2 h 50 min')
    // The dismissal lives in sessionStorage only, not localStorage and not a cookie.
    expect(
      await page.evaluate(() => ({
        session: Object.keys(sessionStorage).filter((key) => key.startsWith('od.expiryBanner')),
        local: localStorage.length,
      })),
    ).toEqual({ session: [expect.stringMatching(/^od\.expiryBannerDismissed\./)], local: 0 })
  })

  test('pairs the warning color with its icon and text', async ({ page }) => {
    await startAs(page, 'Priya')
    await setSandboxLeft(page, 2 * HOUR_MS + 50 * MINUTE_MS)
    await expect(banner(page)).toBeVisible()
    const icon = banner(page).locator('[data-slot="banner-icon"]')
    await expect(icon).toBeVisible()
    expect(await icon.evaluate((el) => getComputedStyle(el).color)).toBe(
      await themeColor(page, 'warning'),
    )
    // The text is ink, not the warning color.
    const text = banner(page).getByText(/This sandbox resets in/)
    expect(await text.evaluate((el) => getComputedStyle(el).color)).toBe(
      await themeColor(page, 'ink'),
    )
    await expect(icon).toHaveAttribute('aria-hidden', 'true')
  })
})
