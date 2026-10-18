import { expect, test, type Page } from '@playwright/test'
import { PERSONAS } from '../src/features/personas/personas'
import { focusRing, greetingHeading, scan, startAs, themeColor, type FirstName } from './helpers'

// One test per acceptance criterion in docs/design/screens/03-assistant-home/notes.md.
//
// Not tests, and where each is proved instead:
//  - "Matches the screenshots at 1440 px": the capture report (make captures).
//  - "A failed send keeps the question, shows the error under the box, and announces it": the API
//    (with the scripted model) has no way to fail a send from a browser, so home-page.test.tsx
//    proves it with a failing request, and the gallery's composer-error state shows it (axe-scanned
//    in gallery.spec.ts). The conversation page's own send errors are in conversation.spec.ts.
//  - The first question turns this page into the conversation (screen 07). The home runs against
//    the real API with the scripted model, so a question gets a real, cited answer. What the
//    conversation does is conversation.spec.ts's.
//  - "The cinnamon marker appears only beside text": the one at-a-glance figure so far
//    (Handbook updated) has no marker, so none is on the page. glance-link.test.tsx proves it on the component, and the gallery's
//    glance-link-marker state is scanned and captured.

const scrollWidth = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth)
const AI_DISCLOSURE =
  'Open Door is an AI assistant. It can make mistakes, and it always shows its sources.'
const box = (page: Page) => page.getByRole('textbox', { name: 'Ask Open Door' })
const ASK_FIRST = 'How many sick days do I get?'

/** Asks the first question and waits for the page to become the conversation, with its answer. */
async function askAndWaitForAnswer(page: Page, question = ASK_FIRST) {
  await box(page).fill(question)
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  // Feedback arrives with the saved answer, once the stream is over.
  await expect(page.getByRole('group', { name: 'Was this right?' })).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  await startAs(page, 'Priya')
  await expect(greetingHeading(page, 'Priya')).toBeVisible()
})

test.describe('usable at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('nothing overflows', async ({ page }) => {
    expect(await scrollWidth(page)).toBeLessThanOrEqual(390)
    await askAndWaitForAnswer(page)
    expect(await scrollWidth(page)).toBeLessThanOrEqual(390)
  })

  test('the navigation shows that it scrolls: it is a scroll container, and fades its edge only when there is more to see', async ({
    page,
  }) => {
    // Phase 2 has two items, which fit at 390 px, so nothing needs scrolling yet. The test shows
    // the container and its fade logic anyway, then narrows the window until the real items
    // overflow, and watches the real logic switch on and off with the scroll position.
    const nav = page.getByRole('navigation', { name: 'Main' })
    const fade = () => nav.evaluate((el) => getComputedStyle(el).maskImage)
    await expect(nav).toHaveCSS('overflow-x', 'auto')
    await expect(nav).toHaveAttribute('data-more', 'false')
    expect(await fade()).toBe('none')

    await page.setViewportSize({ width: 150, height: 844 })
    await expect(nav).toHaveAttribute('data-more', 'true')
    expect(await fade()).toContain('linear-gradient')
    expect(await nav.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true)

    await nav.evaluate((el) => el.scrollTo({ left: el.scrollWidth }))
    await expect(nav).toHaveAttribute('data-more', 'false')
    expect(await fade()).toBe('none')
  })

  test('the sandbox indicator is in the top bar, above the navigation, and the rail has none', async ({
    page,
  }) => {
    const indicators = page.locator('[data-slot="sandbox-indicator"]')
    await expect(indicators.locator('visible=true')).toHaveCount(1)
    const topBar = page.getByRole('complementary', { name: 'Sidebar' })
    const indicator = topBar.locator('[data-slot="sandbox-indicator"]')
    await expect(indicator).toBeVisible()
    await expect(indicator).toHaveText(/^Sandbox resets in \d+ h$/)
    const [pill, nav, heading] = await Promise.all([
      indicator.boundingBox(),
      page.getByRole('navigation', { name: 'Main' }).boundingBox(),
      greetingHeading(page, 'Priya').boundingBox(),
    ])
    expect(pill!.y).toBeLessThan(nav!.y)
    expect(pill!.y + pill!.height).toBeLessThan(heading!.y)
    expect(pill!.y).toBeLessThan(120)
    // The rail now holds the glance list, so it stays; only its sandbox indicator is hidden, because
    // the top bar carries it at this width.
    await expect(
      page
        .getByRole('complementary', { name: 'Sandbox status' })
        .locator('[data-slot="sandbox-indicator"]'),
    ).toBeHidden()
  })

  test('axe reports no violations', async ({ page }) => {
    expect((await scan(page)).violations).toEqual([])
  })
})

test('every interactive element is reachable by keyboard in the order above and shows the focus ring', async ({
  page,
}) => {
  // The notes list the logo first, but the logo is not a control in the kit (the plan's Task 36
  // note), so the first stop is the navigation. "How it's built" is hidden until Phase 7. The rail
  // follows the page, so the "Handbook updated" link is the last stop (the Phase 5 figures will
  // join it).
  await page.reload()
  await expect(greetingHeading(page, 'Priya')).toBeVisible()
  // The glance link arrives with its own request, after the greeting.
  await expect(page.getByRole('link', { name: /Handbook updated/ })).toBeVisible()
  const stops: { name: string; ring: unknown }[] = []
  const priya = PERSONAS[0]!
  for (let i = 0; i < 11; i += 1) {
    await page.keyboard.press('Tab')
    stops.push({
      name: await page.evaluate(() => {
        const el = document.activeElement as HTMLElement
        return el.getAttribute('aria-label') ?? el.textContent?.trim() ?? ''
      }),
      ring: await focusRing(page),
    })
  }
  expect(stops.map((stop) => stop.name)).toEqual([
    'Ask',
    'Directory',
    'Handbook',
    `Switch persona. Current: ${priya.name}, ${priya.title}`,
    'Ask Open Door',
    'Ask',
    ...priya.tryAsking,
    // The date is the published handbook's, so it changes with each edition.
    expect.stringMatching(/^[A-Z][a-z]{2} \d{1,2} Handbook updated\. Open Handbook$/),
  ])
  // The ring is 2 px, offset 2 px. The composer's box shows its own primary border and halo
  // instead (components.spec.ts), so its stop is checked there.
  for (const [index, stop] of stops.entries()) {
    if (index === 4) continue
    expect(stop.ring).toEqual({ width: '2px', style: 'solid', offset: '2px' })
  }
  // Focus then leaves the page's controls: nothing after the last row takes it.
  await page.keyboard.press('Tab')
  expect(await page.evaluate(() => document.activeElement?.closest('main') != null)).toBe(false)
})

test('the composer shows its primary border and halo when the keyboard reaches it, and its border is 3:1 against the sheet', async ({
  page,
}) => {
  const wrapper = page.locator('[data-slot="composer"] > div').first()
  const read = () =>
    wrapper.evaluate((el) => {
      const style = getComputedStyle(el)
      return { border: style.borderTopColor, shadow: style.boxShadow }
    })
  const resting = await read()

  // Contrast of the resting border against the sheet's white, by the WCAG formula.
  const luminance = (rgb: string) => {
    const channels = (rgb.match(/\d+(\.\d+)?/g) ?? []).slice(0, 3).map(Number)
    const [r, g, b] = channels.map((value) => {
      const c = value / 255
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
    })
    return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!
  }
  const sheet = await page
    .locator('[data-slot="shell-sheet"]')
    .evaluate((el) => getComputedStyle(el).backgroundColor)
  const [light, dark] = [luminance(sheet), luminance(resting.border)].sort((a, b) => b - a)
  expect((light! + 0.05) / (dark! + 0.05)).toBeGreaterThanOrEqual(3)

  for (let i = 0; i < 5; i += 1) await page.keyboard.press('Tab')
  await expect(box(page)).toBeFocused()
  await expect.poll(async () => (await read()).border).toBe(await themeColor(page, 'primary'))
  // The halo transitions in with the border, so wait for it too.
  await expect.poll(async () => (await read()).shadow).toMatch(/rgba?\(.*\) 0px 0px 0px 3px/)
})

test('text contrast meets WCAG 2.2 AA, and axe reports no violations, on the home, with a typed question, and with the reply', async ({
  page,
}) => {
  // axe's color-contrast rule is in the wcag2aa tag, so this is the text-contrast check.
  expect((await scan(page)).violations).toEqual([])
  await box(page).fill(ASK_FIRST)
  expect((await scan(page)).violations).toEqual([])
  // A row hovered and the Ask button busy are brief; hover a row for its state.
  await page.getByRole('button', { name: 'Book next Friday off' }).hover()
  expect((await scan(page)).violations).toEqual([])
  // The reply is the conversation now: the question, the cited answer, and its feedback.
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.getByRole('group', { name: 'Was this right?' })).toBeVisible()
  expect((await scan(page)).violations).toEqual([])
})

test('nav hover uses neutral-hover, never primary-tint; the current page alone uses the tint', async ({
  page,
}) => {
  const [tint, hover] = await Promise.all([
    themeColor(page, 'primary-tint'),
    themeColor(page, 'neutral-hover'),
  ])
  const ask = page.getByRole('link', { name: 'Ask', exact: true })
  const directory = page.getByRole('link', { name: 'Directory' })
  const background = (link: typeof ask) =>
    link.evaluate((el) => getComputedStyle(el).backgroundColor)

  await expect(ask).toHaveAttribute('aria-current', 'page')
  expect(await background(ask)).toBe(tint)
  expect(await background(directory)).not.toBe(tint)

  await directory.hover()
  await expect.poll(() => background(directory)).toBe(hover)
  expect(await background(directory)).not.toBe(tint)
  // The current item stays tinted, and nothing else is.
  expect(await background(ask)).toBe(tint)

  // On the Directory page the tint moves with the current page.
  await directory.click()
  await expect(page).toHaveURL('/directory')
  await page.mouse.move(700, 500)
  await expect(directory).toHaveAttribute('aria-current', 'page')
  await expect.poll(() => background(directory)).toBe(tint)
  await expect.poll(() => background(ask)).not.toBe(tint)
})

test('the AI disclosure is always visible in the composer', async ({ page }) => {
  const disclosure = page.locator('[data-slot="composer"]').getByText(AI_DISCLOSURE)
  await expect(disclosure).toBeVisible()
  await box(page).fill(ASK_FIRST)
  await expect(disclosure).toBeVisible()
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.getByRole('group', { name: 'Was this right?' })).toBeVisible()
  await expect(disclosure).toBeVisible()
  // It describes the box, so a screen reader reads it with the field.
  await expect(box(page)).toHaveAccessibleDescription(AI_DISCLOSURE)
})

test('a long persona title truncates and shows its tooltip only when cut off', async ({ page }) => {
  const switcher = page.getByRole('button', { name: /^Switch persona/ })
  // "Visual Merchandiser" fits the sidebar: hovering shows no tooltip.
  await switcher.hover()
  await page.waitForTimeout(800)
  await expect(page.getByRole('tooltip')).toHaveCount(0)

  // Squeeze the switcher until the real title is cut off, as a longer title would be.
  await page.mouse.move(700, 400)
  await page.addStyleTag({ content: '[data-slot="persona-switcher"] { width: 120px !important; }' })
  const title = switcher.getByText('Visual Merchandiser')
  await expect.poll(() => title.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true)
  await switcher.hover()
  await expect(page.getByRole('tooltip').first()).toContainText('Visual Merchandiser')
  // The switcher's name always carries the whole title, cut off or not.
  await expect(switcher).toHaveAccessibleName(
    'Switch persona. Current: Priya Raman, Visual Merchandiser',
  )
})

test.describe('under prefers-reduced-motion', () => {
  test('there are no transitions', async ({ page }) => {
    const directory = page.getByRole('link', { name: 'Directory' })
    const duration = () => directory.evaluate((el) => getComputedStyle(el).transitionDuration)
    // Control: with motion allowed, the item really transitions, so the check below can fail.
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    expect(await duration()).not.toBe('0s')
    await page.emulateMedia({ reducedMotion: 'reduce' })
    expect(await duration()).toBe('0s')
    for (const selector of [
      '[data-slot="composer"] > div',
      '[data-slot="try-asking-row"]',
      '[data-slot="persona-switcher"]',
    ]) {
      const element = page.locator(selector).first()
      expect(await element.evaluate((el) => getComputedStyle(el).transitionDuration)).toBe('0s')
    }
  })
})

test.describe("the greeting follows the location's local time, not the browser's", () => {
  // The browser is in London. At 11:00 UTC it is noon there (BST), 04:00 in Oakland and Los
  // Angeles (PDT), and 06:00 in Austin (CDT).
  test.use({ timezoneId: 'Europe/London' })
  const INSTANT = new Date('2026-10-06T11:00:00Z')

  const greeting = async (page: Page, name: FirstName, at: Date) => {
    await page.clock.setFixedTime(at)
    await page.goto('/')
    // Signed in already, the landing page sends the visitor to the home.
    await expect(page).toHaveURL('/ask')
    return greetingHeading(page, name)
  }

  test('Priya, in Oakland, is greeted for 4 am', async ({ page }) => {
    await expect(await greeting(page, 'Priya', INSTANT)).toHaveText('Good evening, Priya.')
  })

  test('the greeting changes with the hour: morning, afternoon, evening', async ({ page }) => {
    await expect(await greeting(page, 'Priya', new Date('2026-10-06T15:00:00Z'))).toHaveText(
      'Good morning, Priya.',
    )
    await expect(await greeting(page, 'Priya', new Date('2026-10-06T20:00:00Z'))).toHaveText(
      'Good afternoon, Priya.',
    )
    await expect(await greeting(page, 'Priya', new Date('2026-10-07T02:00:00Z'))).toHaveText(
      'Good evening, Priya.',
    )
  })
})

test('Mateo, in Austin, is greeted for 6 am at the same instant', async ({ browser }) => {
  const context = await browser.newContext({ timezoneId: 'Europe/London' })
  const page = await context.newPage()
  try {
    await page.clock.setFixedTime(new Date('2026-10-06T11:00:00Z'))
    await startAs(page, 'Mateo')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Good morning, Mateo.')
  } finally {
    await context.close()
  }
})
