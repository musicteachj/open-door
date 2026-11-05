import { expect, test } from '@playwright/test'
import { GALLERY_STATE_IDS } from './gallery-ids'
import {
  expectNoViolationsIn,
  expectSectionHeadings,
  focusRing,
  galleryState as state,
  keyboardFocus,
  openGallery,
  scan,
  statesPastEdge,
} from './helpers'

// The AI Ops console's parts (screen 13) and the eval scoreboard in a real browser: axe on every
// state, the live console by keyboard (open, swap, close, focus), and the layout at 1440 and 390.

const CONSOLE_IDS = GALLERY_STATE_IDS.slice(
  GALLERY_STATE_IDS.indexOf('console-outcome-badges'),
  GALLERY_STATE_IDS.indexOf('console-scoreboard-rows') + 1,
)
// The scoreboard's tables scroll inside their own container on purpose (640 px minimum).
const SCROLLING = ['console-scoreboard', 'console-scoreboard-rows']

const rowButton = (page: import('@playwright/test').Page, time: string) =>
  state(page, 'console-live').getByRole('button', { name: new RegExp(`^${time}`) })

test.beforeEach(async ({ page }) => {
  await openGallery(page)
})

test('every console state has its own heading', async ({ page }) => {
  await expectSectionHeadings(page, CONSOLE_IDS)
  for (const id of CONSOLE_IDS) await expect(page.locator(`h3#${id}`)).toHaveCount(1)
})

test('no console state has accessibility violations', async ({ page }) => {
  test.setTimeout(120_000)
  await expectNoViolationsIn(page, CONSOLE_IDS)
})

test('the live console has no violations with a trace open', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await rowButton(page, '10:38 AM').first().click()
  await expect(state(page, 'console-live').getByRole('complementary')).toBeVisible()
  const results = await scan(page, [], ['section[aria-labelledby="console-live"]'])
  expect(results.violations).toEqual([])
})

test('Enter opens a row and focuses the trace heading; Escape returns focus to the row', async ({
  page,
}) => {
  const live = state(page, 'console-live')
  const button = rowButton(page, '10:33 AM')
  await keyboardFocus(page, button)
  // The focus ring goes around the whole row, not the button.
  const ring = await page.evaluate(() => {
    const row = document.activeElement!.closest('[role="row"]')!
    const style = getComputedStyle(row)
    return { width: style.outlineWidth, style: style.outlineStyle }
  })
  expect(ring).toEqual({ width: '2px', style: 'solid' })
  expect((await focusRing(page)).style).toBe('none')

  await page.keyboard.press('Enter')
  const heading = live.getByRole('heading', { level: 2, name: '10:33 AM · Employee · Oakland, CA' })
  await expect(heading).toBeFocused()
  await expect(button).toHaveAttribute('aria-expanded', 'true')

  await page.keyboard.press('Escape')
  await expect(live.getByRole('complementary')).toHaveCount(0)
  await expect(button).toBeFocused()
})

test('another row swaps the trace, and the X closes it and returns focus', async ({ page }) => {
  const live = state(page, 'console-live')
  await rowButton(page, '10:33 AM').click()
  await rowButton(page, '10:31 AM').click()
  await expect(live.getByRole('complementary')).toHaveCount(1)
  await expect(live.getByRole('heading', { level: 2 })).toHaveText(
    '10:31 AM · Employee · Oakland, CA',
  )
  await expect(live.getByRole('heading', { level: 2 })).toBeFocused()
  await live.getByRole('button', { name: 'Close trace' }).click()
  await expect(rowButton(page, '10:31 AM')).toBeFocused()
})

test('a click anywhere in a row opens it', async ({ page }) => {
  const live = state(page, 'console-live')
  await live.getByText('$0.028').click()
  await expect(live.getByRole('heading', { level: 2 })).toHaveText(/^10:33 AM/)
})

test('the flagged and abandoned rows are not focusable and open nothing', async ({ page }) => {
  for (const id of ['console-table-flagged', 'console-live']) {
    const rows = state(page, id).locator('[data-slot="redacted-row"]')
    expect(await rows.count()).toBeGreaterThan(0)
    for (const row of await rows.all()) {
      await expect(row.locator('button, a, [tabindex]')).toHaveCount(0)
    }
  }
  const live = state(page, 'console-live')
  await live.getByText(/^Flagged by the safety check/).click()
  await expect(live.getByRole('complementary')).toHaveCount(0)
})

test('at 1440 px the trace docks beside the table, 420 px wide', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const live = state(page, 'console-live')
  await rowButton(page, '10:31 AM').click()
  const panel = await live.getByRole('complementary').boundingBox()
  const tableBox = await live.locator('[data-slot="turn-table"]').boundingBox()
  expect(panel!.width).toBeCloseTo(420, 0)
  expect(panel!.x).toBeGreaterThanOrEqual(tableBox!.x + tableBox!.width - 1)
  // The tiles reflow beside the panel.
  const tiles = await live
    .locator('[data-slot="console-tile"]')
    .evaluateAll(
      (els) => new Set(els.map((el) => Math.round(el.getBoundingClientRect().left))).size,
    )
  expect(tiles).toBe(2)
})

test('at desktop widths the cells are named by the column headers, not read twice', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const live = state(page, 'console-live')
  await expect(live.getByRole('cell', { name: /^\$0\.021/ }).first()).toBeVisible()
  await expect(live.getByRole('cell', { name: /^Cost/ })).toHaveCount(0)
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('a cell without a visible name still says what it is', async ({ page }) => {
    const live = state(page, 'console-live')
    await expect(live.getByRole('cell', { name: /^Cost \$0\.021/ }).first()).toBeAttached()
    await expect(live.getByRole('cell', { name: /^First token 1\.4 s/ }).first()).toBeAttached()
    await expect(live.getByRole('cell', { name: /^Tools 1/ }).first()).toBeAttached()
  })

  test('nothing scrolls sideways, and the scoreboard scrolls inside its own container', async ({
    page,
  }) => {
    test.setTimeout(60_000)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    expect(
      await statesPastEdge(
        page,
        CONSOLE_IDS.filter((id) => !SCROLLING.includes(id)),
        390,
      ),
      'states with content past the edge',
    ).toEqual([])
    for (const id of SCROLLING) {
      const scrollers = state(page, id).locator('section[aria-label]')
      for (const scroller of await scrollers.all()) {
        expect(await scroller.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true)
        await expect(scroller).toHaveAttribute('tabindex', '0')
      }
    }
  })

  test('the tiles take one row each', async ({ page }) => {
    const lefts = await state(page, 'console-tiles-day')
      .locator('[data-slot="console-tile"]')
      .evaluateAll(
        (els) => new Set(els.map((el) => Math.round(el.getBoundingClientRect().left))).size,
      )
    expect(lefts).toBe(1)
  })

  test('the trace opens as a full-screen sheet, and Escape returns focus to the row', async ({
    page,
  }) => {
    const button = rowButton(page, '10:33 AM')
    await button.scrollIntoViewIfNeeded()
    await button.click()
    const dialog = page.getByRole('dialog', { name: '10:33 AM · Employee · Oakland, CA' })
    await expect(dialog).toBeVisible()
    const box = await dialog.boundingBox()
    expect(box).toMatchObject({ x: 0, y: 0, width: 390, height: 844 })
    await expect(page.getByRole('heading', { level: 2 })).toBeFocused()
    const results = await scan(page, ['aria-hidden-focus'], ['[role="dialog"]'])
    expect(results.violations).toEqual([])
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(button).toBeFocused()
  })
})
