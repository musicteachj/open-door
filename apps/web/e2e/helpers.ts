import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Locator, type Page } from '@playwright/test'

/** The four demo personas, by first name, as the landing page's cards are labeled. */
export type FirstName = 'Priya' | 'Mateo' | 'Marcus' | 'Dana'

/** The same tags as gallery.spec.ts. */
export const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

/** An axe scan of the page as it is now. Pass a rule to turn off only where its reason is given. */
export const scan = (page: Page, disabledRules: string[] = [], include: string[] = []) => {
  const builder = new AxeBuilder({ page }).withTags(AXE_TAGS).disableRules(disabledRules)
  // With no `include`, the whole page. Each one added narrows the scan to those parts.
  for (const selector of include) builder.include(selector)
  return builder.analyze()
}

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

/**
 * Presses a key and holds it until its effect shows, then lets go. Radix moves focus in a radio
 * group on a timer and counts a selection only while the arrow key is down, so
 * `page.keyboard.press`, which releases the key at once, can move focus without selecting. Pass
 * `until` (an assertion on the result) wherever the target is known; without it the key is held
 * for a fixed 60 ms.
 */
export async function holdKey(page: Page, key: string, until?: () => Promise<unknown>) {
  await page.keyboard.down(key)
  try {
    if (until) await until()
    else await page.waitForTimeout(60)
  } finally {
    await page.keyboard.up(key)
  }
}

/**
 * The ids of the gallery's own state headings, in page order. A component's heading carries a
 * generated id such as `_r_1_`; the gallery's are kebab-case.
 */
export const galleryHeadingIds = (page: Page) =>
  page
    .locator('h3[id]')
    .evaluateAll((headings) =>
      headings.map((h) => h.id).filter((id) => /^[a-z][a-z0-9-]*$/.test(id)),
    )

/** The headings from the first id to the last id, which must be exactly `ids`, in order. */
export async function expectSectionHeadings(page: Page, ids: readonly string[]) {
  const all = await galleryHeadingIds(page)
  const first = all.indexOf(ids[0]!)
  expect(first, `${ids[0]} is on the page`).toBeGreaterThanOrEqual(0)
  expect(all.slice(first, first + ids.length)).toEqual(ids)
}

/** The selector for a gallery state, by the id of its heading (for axe's `include`). */
export const galleryStateSelector = (id: string) => `section[aria-labelledby="${id}"]`

/** A gallery state, by the id of its heading. */
export const galleryState = (page: Page, id: string) => page.locator(galleryStateSelector(id))

type Host = {
  /** The opener's name, in the state's own section. */
  button: string
  role: 'dialog' | 'alertdialog'
  /**
   * `timer`: the dialog can't be closed from the page (it is busy) and closes itself on a timer.
   * The gallery holds it open while it is scanned, then releases it.
   */
  closes?: 'timer'
}

/**
 * Scans a section's gallery states with axe, and records a soft failure named for each state with
 * violations, so one failure never hides the others. Motion is reduced first, so no fade is
 * caught half done.
 *
 * The states are scanned closed in one pass over just those states, and each violating element is
 * credited to the nearest ancestor `section` that is one of `ids` (a component's own generated-id
 * `section` is skipped). A violation that no state owns fails as "unattributed", never dropped.
 *
 * A state in `hosts` starts closed behind a button: it is opened, the dialog and the state's own
 * section are scanned together with it open (`MODAL_OVERLAY_RULES` off), and everything found is
 * that state's. It is then closed, and the next one waits for it to be gone.
 */
export async function expectNoViolationsIn(
  page: Page,
  ids: readonly string[],
  hosts: Record<string, Host> = {},
) {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  // A host's own section (its opener) is drawn too, so it is scanned closed with the others.
  const results = await scan(page, [], ids.map(galleryStateSelector))
  const targets = results.violations.flatMap((violation) =>
    violation.nodes.map((node) => ({
      rule: violation.id,
      target: node.target,
      html: node.html,
    })),
  )
  // One round trip: the owner of every violating element, in order.
  const owners = await page.evaluate(
    ([selectors, states]) =>
      selectors!.map((selector) => {
        for (
          let el: Element | null | undefined = document.querySelector(selector);
          el;
          el = el.parentElement
        ) {
          const label = el.matches('section[aria-labelledby]')
            ? el.getAttribute('aria-labelledby')
            : null
          if (label !== null && states!.includes(label)) return label
        }
        return null
      }),
    [targets.map((t) => t.target.join(' ')), ids] as const,
  )
  const found = new Map<string, unknown[]>(ids.map((id) => [id, []]))
  const unattributed: unknown[] = []
  for (const [i, target] of targets.entries()) {
    const owner = owners[i]
    if (owner && found.has(owner)) found.get(owner)!.push(target)
    else unattributed.push(target)
  }
  for (const [id, violations] of found) {
    expect.soft(violations, `${id} has no accessibility violations`).toEqual([])
  }
  // Nothing is dropped: a violation outside every state checked here still fails the test.
  expect.soft(unattributed, 'violations that belong to none of the states checked here').toEqual([])

  for (const id of ids) {
    const host = hosts[id]
    if (host === undefined) continue
    // One host that can't be opened, scanned, or closed is reported, and the others still run.
    await test.step(`scan ${id} with its dialog open`, async () => {
      try {
        const dialog = `[role="${host.role}"]`
        if (host.closes === 'timer') {
          // The gallery's demo then waits to be released instead of closing on its own timer, so
          // the scan runs on the real clock and takes as long as the machine needs.
          await page.evaluate(() => {
            document.documentElement.dataset.galleryHold = ''
          })
        }
        await galleryState(page, id)
          .getByRole('button', { name: host.button })
          .click({ timeout: 5_000 })
        await expect(page.locator(dialog)).toHaveCount(1)
        await expect(page.locator(dialog)).toBeVisible()
        const open = await scan(page, MODAL_OVERLAY_RULES, [dialog, galleryStateSelector(id)])
        expect.soft(open.violations, `${id} has no accessibility violations`).toEqual([])
        if (host.closes === 'timer') {
          await page.evaluate(() => {
            delete document.documentElement.dataset.galleryHold
            window.dispatchEvent(new Event('gallery:release'))
          })
        } else await page.keyboard.press('Escape')
        // Gone from the page, so the next host's dialog is the only one there.
        await expect(page.locator(dialog)).toHaveCount(0)
      } catch (error) {
        expect.soft(String(error), `${id} could not be opened, scanned, and closed`).toBe('')
        await openGallery(page)
      }
    })
  }
}

/** Opens the gallery and waits for its heading. */
export async function openGallery(page: Page) {
  await page.goto('/gallery')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Open Door component gallery' }),
  ).toBeVisible()
}

/**
 * The gallery states whose content reaches past `width` px. Text clipped by a truncating
 * ancestor is not sideways scroll, so those are left out.
 */
export async function statesPastEdge(page: Page, ids: readonly string[], width: number) {
  const past: string[] = []
  for (const id of ids) {
    const wide = await galleryState(page, id).evaluate((el, limit) => {
      // Past the window, or past the section that holds it.
      const edge = Math.min(limit, el.getBoundingClientRect().right)
      return [...el.querySelectorAll<HTMLElement>('*')].filter(
        (child) =>
          child.getBoundingClientRect().right > edge + 1 && child.closest('.truncate') === null,
      ).length
    }, width)
    if (wide > 0) past.push(id)
  }
  return past
}
