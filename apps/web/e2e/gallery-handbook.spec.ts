import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { GALLERY_STATE_IDS } from './gallery-ids'
import { AXE_TAGS, focusRing, themeColor } from './helpers'

// The handbook section of the gallery in a real browser: axe on every state, what the browser
// paints on hover and focus, the passage panel's focus behavior, and 390 px.

// From the first handbook state to the last one. The list is in page order and grows at its other
// ends, so the slice is bounded on both sides.
const HANDBOOK_IDS = GALLERY_STATE_IDS.slice(
  GALLERY_STATE_IDS.indexOf('applicability-badge-chip'),
  GALLERY_STATE_IDS.indexOf('passage-panel-error') + 1,
)
// These two start closed, behind a button, so that an open panel does not take focus on load.
const HOSTS = {
  'passage-panel-open': 'Open the passage',
  'passage-panel-long': 'Open the long passage',
}

const state = (page: Page, id: string) => page.locator(`section[aria-labelledby="${id}"]`)

test.beforeEach(async ({ page }) => {
  await page.goto('/gallery')
  await expect(
    page.getByRole('heading', { level: 1, name: 'Open Door component gallery' }),
  ).toBeVisible()
})

test('the handbook section has every state under its own heading', async ({ page }) => {
  expect(HANDBOOK_IDS.length).toBeGreaterThan(25)
  for (const id of HANDBOOK_IDS) await expect(page.locator(`h3#${id}`)).toHaveCount(1)
})

for (const id of HANDBOOK_IDS) {
  test(`${id} has no accessibility violations`, async ({ page }) => {
    const section = state(page, id)
    const open = HOSTS[id as keyof typeof HOSTS]
    if (open) {
      await section.getByRole('button', { name: open }).click()
      await expect(section.getByRole('complementary', { name: 'Handbook passage' })).toBeVisible()
    }
    const results = await new AxeBuilder({ page })
      .withTags(AXE_TAGS)
      .include(`section[aria-labelledby="${id}"]`)
      .analyze()
    expect(results.violations).toEqual([])
  })
}

test('the handbook section, as a whole page, has no violations', async ({ page }) => {
  const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze()
  expect(results.violations).toEqual([])
})

test('a hovered section row and search result go to the tint', async ({ page }) => {
  const tint = await themeColor(page, 'primary-tint')
  for (const [id, link] of [
    ['section-row-default', 'a'],
    ['search-result-applies', 'a'],
    ['link-block-state-rules', 'a'],
  ] as const) {
    const target = state(page, id).locator(link).first()
    await target.scrollIntoViewIfNeeded()
    await target.hover()
    await expect
      .poll(() => target.evaluate((el) => getComputedStyle(el).backgroundColor))
      .toBe(tint)
  }
})

test('a keyboard-focused row, result, link, and chapter link show the focus ring', async ({
  page,
}) => {
  for (const id of [
    'section-row-default',
    'search-result-applies',
    'link-block-supplements',
    'chapter-nav-chapter',
  ]) {
    const link = state(page, id).getByRole('link').first()
    await link.scrollIntoViewIfNeeded()
    await link.focus()
    await page.keyboard.press('Shift+Tab')
    await page.keyboard.press('Tab')
    await expect(link).toBeFocused()
    const ring = await focusRing(page)
    expect(ring.style, id).not.toBe('none')
    expect(parseFloat(ring.width), id).toBeGreaterThanOrEqual(2)
  }
})

test('a wide section row keeps its six columns, with the title on one line', async ({ page }) => {
  // The title column must never collapse: the owner's gallery review caught it wrapping word by
  // word under the audience when the fixed columns left it no room.
  for (const id of ['section-row-default', 'section-row-marker', 'section-row-addendum']) {
    const row = state(page, id).locator('[data-slot="section-row"]')
    const columns = await row.evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(' '))
    expect(columns).toHaveLength(6)
    expect(Number.parseFloat(columns[1] ?? '0')).toBeGreaterThan(200)
    const [title, audience] = await row
      .locator(':scope > span:not(.sr-only)')
      .evaluateAll((spans) => spans.slice(1, 3).map((span) => span.getBoundingClientRect()))
    expect(title?.right ?? 0).toBeLessThanOrEqual(audience?.left ?? 0)
    // One line is 48 px with the cell's padding; two would be 72.
    expect(title?.height ?? 0).toBeLessThan(60)
  }
})

test('a section row in a narrow container stacks its columns by its own width', async ({
  page,
}) => {
  const row = state(page, 'section-row-narrow').locator('[data-slot="section-row"]')
  const columns = await row.evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(' '))
  expect(columns).toHaveLength(3)
})

test('the current section row and navigator link are marked, and tinted', async ({ page }) => {
  const tint = await themeColor(page, 'primary-tint')
  for (const id of ['section-row-current', 'chapter-nav-chapter']) {
    const current = state(page, id).locator('[aria-current="page"]')
    await expect(current).toHaveCount(1)
    await expect
      .poll(() => current.evaluate((el) => getComputedStyle(el).backgroundColor))
      .toBe(tint)
  }
})

test.describe('the passage panel', () => {
  const host = (page: Page) => state(page, 'passage-panel-open')
  const panel = (page: Page) => host(page).getByRole('complementary', { name: 'Handbook passage' })
  const openButton = (page: Page) => host(page).getByRole('button', { name: 'Open the passage' })

  test.beforeEach(async ({ page }) => {
    await openButton(page).scrollIntoViewIfNeeded()
    await openButton(page).click()
    await expect(panel(page)).toBeVisible()
  })

  test('opening moves focus to the title', async ({ page }) => {
    await expect(panel(page).getByRole('heading', { name: 'Sick leave' })).toBeFocused()
  })

  test('Tab reaches the body and "Open in handbook", then leaves the panel', async ({ page }) => {
    // The close button comes before the title in the page, so Tab from the title goes on to the body.
    await page.keyboard.press('Tab')
    await expect(panel(page).getByLabel('Passage text')).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(panel(page).getByRole('link', { name: 'Open in handbook' })).toBeFocused()
    // No trap: the next Tab leaves the panel.
    await page.keyboard.press('Tab')
    expect(await panel(page).evaluate((el) => el.contains(document.activeElement))).toBe(false)
  })

  test('Escape with focus in the panel closes it and returns focus to the button', async ({
    page,
  }) => {
    await page.keyboard.press('Escape')
    await expect(panel(page)).toBeHidden()
    await expect(openButton(page)).toBeFocused()
  })

  test('the close button closes it and returns focus to the button', async ({ page }) => {
    await panel(page).getByRole('button', { name: 'Close passage' }).click()
    await expect(panel(page)).toBeHidden()
    await expect(openButton(page)).toBeFocused()
  })

  test('Escape in a field outside the panel does not close it', async ({ page }) => {
    const field = host(page).getByRole('textbox', { name: 'A message outside the panel' })
    await field.fill('half a message')
    await field.press('Escape')
    await expect(panel(page)).toBeVisible()
    await expect(field).toHaveValue('half a message')
  })
})

test('a long passage scrolls inside the panel, and the header and footer stay', async ({
  page,
}) => {
  const host = state(page, 'passage-panel-long')
  await host.getByRole('button', { name: 'Open the long passage' }).click()
  const panel = host.getByRole('complementary', { name: 'Handbook passage' })
  const body = panel.getByLabel('Passage text')
  await body.scrollIntoViewIfNeeded()
  await expect(body).toBeVisible()
  expect(await body.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
  const link = panel.getByRole('link', { name: 'Open in handbook' })
  await panel.scrollIntoViewIfNeeded()
  await link.scrollIntoViewIfNeeded()
  await expect(link).toBeInViewport()
  const before = (await link.boundingBox())!.y
  await body.evaluate((el) => el.scrollTo(0, el.scrollHeight))
  expect((await link.boundingBox())!.y).toBe(before)
  await expect(link).toBeInViewport()
})

test('the error state keeps "Open in handbook" and offers Retry', async ({ page }) => {
  const panel = state(page, 'passage-panel-error')
  await expect(panel.getByRole('alert')).toContainText("Couldn't load this passage.")
  await expect(panel.getByRole('button', { name: 'Retry' })).toBeVisible()
  await expect(panel.getByRole('link', { name: 'Open in handbook' })).toBeVisible()
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('nothing in the handbook section scrolls sideways', async ({ page }) => {
    await expect(page.locator('h3#applicability-badge-chip')).toBeAttached()
    for (const id of ['passage-panel-open', 'passage-panel-long']) {
      await state(page, id).getByRole('button').first().click()
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    for (const id of HANDBOOK_IDS) {
      const section = state(page, id)
      const wide = await section.evaluate(
        (el) =>
          // Text clipped by a truncating ancestor (a search excerpt) is not sideways scroll.
          [...el.querySelectorAll<HTMLElement>('*')].filter(
            (child) =>
              child.getBoundingClientRect().right > 390 + 1 && child.closest('.truncate') === null,
          ).length,
      )
      expect(wide, `${id} has content past the right edge`).toBe(0)
    }
  })

  test('a section row stacks its columns under the title', async ({ page }) => {
    const link = state(page, 'section-row-narrow').getByRole('link')
    await link.scrollIntoViewIfNeeded()
    const [id, title, audience] = await Promise.all(
      [0, 1, 2].map((i) => link.locator(':scope > span:not(.sr-only)').nth(i).boundingBox()),
    )
    expect(audience!.y).toBeGreaterThan(title!.y)
    expect(Math.abs(id!.y - title!.y)).toBeLessThanOrEqual(8)
  })

  test('a group heading lines up with the titles of its rows', async ({ page }) => {
    for (const id of ['section-group-chapter', 'section-group-addendum']) {
      const { heading, titles } = await state(page, id).evaluate((section) => ({
        heading: section.querySelector('h2')!.getBoundingClientRect().x,
        titles: [...section.querySelectorAll('[data-slot="section-row"] > span:nth-child(2)')].map(
          (title) => title.getBoundingClientRect().x,
        ),
      }))
      expect(titles.length).toBeGreaterThan(0)
      for (const x of titles) expect(Math.abs(x - heading)).toBeLessThanOrEqual(1)
    }
  })

  test('a State rules row puts the marker under the name', async ({ page }) => {
    const row = state(page, 'link-block-state-rules').getByRole('link').first()
    const name = await row.locator(':scope > span:not(.sr-only)').first().boundingBox()
    const marker = await row.getByText('Applies to you').boundingBox()
    expect(marker!.y).toBeGreaterThan(name!.y + name!.height - 4)
  })
})
