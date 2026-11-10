import { expect, test } from './fixtures'
import type { Page } from '@playwright/test'
import { GALLERY_STATE_IDS } from './gallery-ids'
import {
  MODAL_OVERLAY_RULES,
  expectNoViolationsIn,
  expectSectionHeadings,
  galleryState as state,
  openGallery,
  scan,
  statesPastEdge,
} from './helpers'

// The guided tour's parts (screen 15) in a real browser: axe on every state, the live coach mark
// by keyboard (focus in, Tab through, Escape out and focus back), where it sits against the fake
// composer and card, the sheet at 390 px, and no motion at all.

const TOUR_IDS = GALLERY_STATE_IDS.slice(
  GALLERY_STATE_IDS.indexOf('tour-coach-step-1'),
  GALLERY_STATE_IDS.indexOf('tour-live') + 1,
)

type Box = { x: number; y: number; width: number; height: number }
const overlaps = (a: Box, b: Box) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height

const live = (page: Page) => state(page, 'tour-live')
const coachMark = (page: Page) => live(page).getByRole('dialog')

async function startDemo(page: Page) {
  const start = live(page).getByRole('button', { name: 'Start the demo' })
  await start.scrollIntoViewIfNeeded()
  await start.click()
  await expect(coachMark(page)).toBeVisible()
  return start
}

const composerBox = (page: Page) =>
  live(page).getByRole('textbox', { name: 'Message (sample composer)' }).boundingBox()

test.beforeEach(async ({ page }) => {
  await openGallery(page)
})

test('every tour state has its own heading', async ({ page }) => {
  await expectSectionHeadings(page, TOUR_IDS)
  for (const id of TOUR_IDS) await expect(page.locator(`h3#${id}`)).toHaveCount(1)
})

test('no tour state has accessibility violations', async ({ page }) => {
  test.setTimeout(120_000)
  await expectNoViolationsIn(page, TOUR_IDS, {
    'tour-start-dialog': { button: 'Show the start dialog', role: 'alertdialog' },
  })
})

for (const [id, row] of [
  ['tour-menu-idle', /^Take the tour$/],
  // Chromium puts a space before a visually hidden part of a name, as in approvals.spec.ts.
  ['tour-menu-progress', /^Resume the tour\s?, Step 5 of 10$/],
] as const) {
  test(`the ${id} persona menu has no violations when open`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await state(page, id)
      .getByRole('button', { name: /Switch persona$/ })
      .click()
    const menu = page.getByRole('menu')
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: row })).toBeVisible()
    await expect(menu.getByRole('menuitem').last()).toHaveText('Sign out')
    const results = await scan(page, MODAL_OVERLAY_RULES, ['[role="menu"]'])
    expect(results.violations).toEqual([])
  })
}

test('the live coach mark has no violations open, with Next and with the missing line', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await live(page).getByRole('button', { name: 'Show the missing line' }).click()
  await startDemo(page)
  const selector = 'section[aria-labelledby="tour-live"]'
  expect((await scan(page, [], [selector])).violations).toEqual([])
  await coachMark(page).getByRole('button', { name: 'Book next Friday off.' }).click()
  await expect(coachMark(page).getByRole('status')).toBeVisible()
  await expect(coachMark(page).getByRole('button', { name: 'Next', exact: true })).toBeVisible()
  expect((await scan(page, [], [selector])).violations).toEqual([])
})

test('the title takes focus on open; Tab reaches the chip, Back, then Skip and Next, and Shift+Tab the X', async ({
  page,
}) => {
  await startDemo(page)
  const card = coachMark(page)
  await expect(card).toHaveAccessibleName(/^Step 3 of 10:\s?Book a day off$/)
  await expect(card.getByRole('heading', { level: 2 })).toBeFocused()
  // The X comes before the title in the page, so it is one Shift+Tab back, and Tab goes on to the chip.
  await page.keyboard.press('Shift+Tab')
  await expect(card.getByRole('button', { name: 'Leave the tour' })).toBeFocused()
  await page.keyboard.press('Tab')
  const chip = card.getByRole('button', { name: 'Book next Friday off.' })
  await expect(chip).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(card.getByRole('button', { name: 'Back' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(card.getByRole('button', { name: 'Skip this step' })).toBeFocused()

  await chip.focus()
  await page.keyboard.press('Enter')
  // Sent: still focusable, named "…, sent", and pressing it again does nothing.
  const sent = card.getByRole('button', { name: /^Book next Friday off\.\s?, sent$/ })
  await expect(sent).toHaveAttribute('aria-disabled', 'true')
  await expect(sent).toBeFocused()
  await expect(card.getByRole('button', { name: 'Next', exact: true })).toBeVisible()
  await expect(card.getByRole('button', { name: 'Skip this step' })).toHaveCount(0)
  await page.keyboard.press('Enter')
  await expect(sent).toBeFocused()
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await expect(card.getByRole('button', { name: 'Next', exact: true })).toBeFocused()
})

test('Escape leaves, and focus returns to what had it', async ({ page }) => {
  const start = await startDemo(page)
  await page.keyboard.press('Escape')
  await expect(coachMark(page)).toHaveCount(0)
  await expect(start).toBeFocused()
})

test('the X leaves too, and focus returns', async ({ page }) => {
  const start = await startDemo(page)
  await coachMark(page).getByRole('button', { name: 'Leave the tour' }).click()
  await expect(coachMark(page)).toHaveCount(0)
  await expect(start).toBeFocused()
})

test('Escape from the page, not just from inside the card, leaves', async ({ page }) => {
  await startDemo(page)
  await live(page).getByRole('textbox').focus()
  await page.keyboard.press('Escape')
  await expect(coachMark(page)).toHaveCount(0)
})

test('the card sits clear of the fake composer, and the ring is around its target', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await startDemo(page)
  const composer = (await composerBox(page))!
  const card = (await coachMark(page).boundingBox())!
  expect(card.width).toBeCloseTo(360, 0)
  // The target itself is never covered.
  expect(overlaps(card, composer)).toBe(false)
  const ring = (await live(page).locator('[data-slot="tour-ring"]').boundingBox())!
  expect(ring.x).toBeCloseTo(composer.x - 4, 0)
  expect(ring.y).toBeCloseTo(composer.y - 4, 0)

  await coachMark(page).getByRole('button', { name: 'Book next Friday off.' }).click()
  const confirm = live(page).getByRole('button', { name: 'Confirm' })
  await expect(confirm).toBeVisible()
  await expect(coachMark(page).getByRole('button', { name: 'Next', exact: true })).toBeVisible()
  await expect
    .poll(async () => {
      const next = (await coachMark(page).boundingBox())!
      const target = (await confirm.boundingBox())!
      const ringNow = (await live(page).locator('[data-slot="tour-ring"]').boundingBox())!
      return {
        coversComposer: overlaps(next, (await composerBox(page))!),
        coversConfirm: overlaps(next, target),
        coversResult: overlaps(
          next,
          (await live(page).getByTestId('tour-live-card').boundingBox())!,
        ),
        ringOnConfirm: Math.abs(ringNow.x - (target.x - 4)) < 1,
      }
    })
    .toEqual({
      coversComposer: false,
      coversConfirm: false,
      coversResult: false,
      ringOnConfirm: true,
    })
})

test('with the missing line on, the card shows it as a status and goes on to Next', async ({
  page,
}) => {
  await live(page).getByRole('button', { name: 'Show the missing line' }).click()
  await startDemo(page)
  await coachMark(page).getByRole('button', { name: 'Book next Friday off.' }).click()
  await expect(coachMark(page).getByRole('status')).toContainText('It didn’t this time')
  await expect(live(page).getByRole('button', { name: 'Confirm' })).toHaveCount(0)
  await expect(coachMark(page).getByRole('button', { name: 'Next', exact: true })).toBeVisible()
})

test('with reduced motion, nothing in the tour has a transition or animation', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await startDemo(page)
  await coachMark(page).getByRole('button', { name: 'Book next Friday off.' }).click()
  await expect(coachMark(page).getByRole('button', { name: 'Next', exact: true })).toBeVisible()
  const moving = await page.evaluate(() => {
    const seconds = (value: string) =>
      Math.max(...value.split(',').map((part) => parseFloat(part) || 0))
    const roots = [...document.querySelectorAll('section')].filter((section) =>
      /^tour-/.test(section.getAttribute('aria-labelledby') ?? ''),
    )
    const coach = document.querySelector('[data-slot="tour-ring"]')
    const all = [
      ...roots.flatMap((root) => [root, ...root.querySelectorAll('*')]),
      ...(coach ? [coach] : []),
    ]
    return all
      .filter((el) => {
        const style = getComputedStyle(el)
        return seconds(style.transitionDuration) > 0 || seconds(style.animationDuration) > 0
      })
      .map((el) => el.outerHTML.slice(0, 80))
  })
  expect(moving).toEqual([])
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the coach mark docks as a sheet at the bottom, and its target sits above it', async ({
    page,
  }) => {
    await startDemo(page)
    const sheet = (await coachMark(page).boundingBox())!
    expect(sheet.x).toBe(0)
    expect(sheet.width).toBe(390)
    expect(sheet.y + sheet.height).toBeCloseTo(844, 0)
    await expect
      .poll(async () => {
        const now = (await coachMark(page).boundingBox())!
        const composer = (await composerBox(page))!
        return composer.y + composer.height <= now.y
      })
      .toBe(true)
    // The ring stays on the target.
    await expect(live(page).locator('[data-slot="tour-ring"]')).toBeVisible()

    await coachMark(page).getByRole('button', { name: 'Book next Friday off.' }).click()
    const confirm = live(page).getByRole('button', { name: 'Confirm' })
    await expect(confirm).toBeVisible()
    await expect
      .poll(async () => {
        const target = (await confirm.boundingBox())!
        const now = (await coachMark(page).boundingBox())!
        return target.y + target.height <= now.y
      })
      .toBe(true)
    const radius = await coachMark(page).evaluate((el) => getComputedStyle(el).borderTopLeftRadius)
    expect(radius).toBe('16px')
  })

  test('the end card, drawn in flow here, fits the window', async ({ page }) => {
    const box = await state(page, 'tour-end-card').getByRole('dialog').boundingBox()
    // In the gallery it draws in flow at its 520 px, shrunk to the window; nothing sticks out.
    expect(box!.x + box!.width).toBeLessThanOrEqual(390)
  })

  test('nothing scrolls sideways', async ({ page }) => {
    test.setTimeout(60_000)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    expect(await statesPastEdge(page, TOUR_IDS, 390), 'states with content past the edge').toEqual(
      [],
    )
  })

  test('the start dialog has 16 px margins, stacked buttons, primary on top, Cancel focused', async ({
    page,
  }) => {
    await state(page, 'tour-start-dialog')
      .getByRole('button', { name: 'Show the start dialog' })
      .click()
    const dialog = page.getByRole('alertdialog', { name: 'Start the tour?' })
    const box = (await dialog.boundingBox())!
    expect(box.x).toBeCloseTo(16, 0)
    expect(box.width).toBeCloseTo(358, 0)
    const cancel = dialog.getByRole('button', { name: 'Cancel' })
    await expect(cancel).toBeFocused()
    const start = dialog.getByRole('button', { name: 'Start the tour' })
    expect((await start.boundingBox())!.y).toBeLessThan((await cancel.boundingBox())!.y)
  })
})
