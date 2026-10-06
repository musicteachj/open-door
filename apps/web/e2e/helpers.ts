import AxeBuilder from '@axe-core/playwright'
import { expect, type Locator, type Page } from '@playwright/test'

/** The four demo personas, by first name, as the landing page's cards are labeled. */
export type FirstName = 'Priya' | 'Mateo' | 'Marcus' | 'Dana'

/** The same tags as gallery.spec.ts. */
export const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

/** An axe scan of the page as it is now. Pass a rule to turn off only where its reason is given. */
export const scan = (page: Page, disabledRules: string[] = []) =>
  new AxeBuilder({ page }).withTags(AXE_TAGS).disableRules(disabledRules).analyze()

/** With a Radix menu open, the page behind it is aria-hidden while its controls stay in the tab
 * order. Radix traps focus in the menu instead, so axe's rule is a false alarm; the test that
 * scans checks the trap with Tab. */
export const MODAL_OVERLAY_RULES = ['aria-hidden-focus']

/** The assistant home's heading for a person, such as "Good morning, Priya." */
export const greetingHeading = (page: Page, name: FirstName) =>
  page.getByRole('heading', {
    level: 1,
    name: new RegExp(`^Good (morning|afternoon|evening), ${name}\\.$`),
  })

/** Starts a sandbox from the landing page and waits for /ask. */
export async function startAs(page: Page, name: FirstName) {
  await page.goto('/')
  await page.getByRole('button', { name: new RegExp(`^Start a sandbox as ${name} `) }).click()
  await expect(page).toHaveURL('/ask')
}

/** A theme color as the browser computes it, for comparing with computed fills and borders. */
export const themeColor = (page: Page, token: string) =>
  page.evaluate((name) => {
    const probe = document.createElement('div')
    probe.style.color = `var(--color-${name})`
    document.body.append(probe)
    const color = getComputedStyle(probe).color
    probe.remove()
    return color
  }, token)

/** Opens the persona menu from the sidebar's switcher and chooses a person, such as "Marcus". */
export async function switchTo(page: Page, firstName: string) {
  await page.getByRole('button', { name: /^Switch persona/ }).click()
  await page.getByRole('menuitemradio', { name: new RegExp(`^${firstName} `) }).click()
}

/** Opens the persona menu and chooses Sign out. */
export async function signOut(page: Page) {
  await page.getByRole('button', { name: /^Switch persona/ }).click()
  await page.getByRole('menuitem', { name: 'Sign out' }).click()
}

/**
 * Holds every request to the API that matches until `release()`, then lets it through to the real
 * server. For seeing a state that is over in milliseconds, such as a sandbox starting.
 */
export async function holdRequests(page: Page, url: string, method: string) {
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route(url, async (route) => {
    if (route.request().method() !== method) return route.fallback()
    await gate
    return route.continue()
  })
  return release
}

/** A problem-details body, as the API sends for every error. */
export const problem = (status: number, title: string) =>
  JSON.stringify({ type: 'about:blank', title, status, instance: '/' })

/** The sandbox's expiry, as /me reports it, in milliseconds since the epoch. */
export async function sandboxExpiry(page: Page): Promise<number> {
  const expires = await page.evaluate(async () => {
    const response = await fetch('/api/v1/me')
    return ((await response.json()) as { tenantExpiresAt: string }).tenantExpiresAt
  })
  return Date.parse(expires)
}

/**
 * Makes the browser's clock say the sandbox has `msLeft` to go, then reloads so the page starts
 * from it. The server keeps its own clock, so the session stays valid.
 */
export async function setSandboxLeft(page: Page, msLeft: number) {
  const expiry = await sandboxExpiry(page)
  await page.clock.setFixedTime(new Date(expiry - msLeft))
  await page.reload()
}

export const HOUR_MS = 3_600_000
export const MINUTE_MS = 60_000

/** The focus ring as the browser paints it on the focused element. */
export const focusRing = (page: Page) =>
  page.evaluate(() => {
    const style = getComputedStyle(document.activeElement!)
    return { width: style.outlineWidth, style: style.outlineStyle, offset: style.outlineOffset }
  })

/**
 * Moves focus to `target` by keyboard, the way Radix needs to open a tooltip, without scrolling.
 *
 * Radix closes a tooltip when the page scrolls. If Tab has to scroll the trigger into view, that
 * scroll can land just after the tooltip opens and close it, which under a busy run made tooltip
 * tests flaky. So: center the trigger (its neighbors are then on screen too), wait for the fonts and
 * the scroll position to settle, then Shift+Tab and Tab back onto it.
 */
export async function keyboardFocus(page: Page, target: Locator) {
  await target.evaluate((el) => el.scrollIntoView({ block: 'center' }))
  await page.evaluate(() => document.fonts.ready)
  await expect
    .poll(async () => {
      const before = await page.evaluate(() => window.scrollY)
      await page.evaluate(
        () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
      )
      return before === (await page.evaluate(() => window.scrollY))
    })
    .toBe(true)
  await target.focus()
  await page.keyboard.press('Shift+Tab')
  await page.keyboard.press('Tab')
  await expect(target).toBeFocused()
}
