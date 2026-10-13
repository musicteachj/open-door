import { expect, test, type Page } from '@playwright/test'
import { hasVisibleFocus } from './directory-helpers'
import { holdRequests, scan, startAs, type FirstName } from './helpers'

// One test per acceptance criterion in docs/design/screens/06-handbook/notes.md, against the real
// API and the ingested handbook. Each test starts its own sandbox.
//
// Mapped elsewhere:
//  - "Matches the screenshots at 1440 px" is the capture report's job (make captures).
//  - The passage panel's criteria (focus, Escape, the inline error, the long passage) belong to the
//    panel, which Phase 4 docks. The gallery specs (gallery-handbook.spec.ts) cover its states.
//  - The cinnamon bar's contrast is a design note; the label and icon carry the meaning.

// The restricted sections in handbook/ (front matter `applies_to`), for the two personas.
// Priya: salaried, California. Mateo: hourly, Austin (Texas).
const PRIYA_MARKED = ['CA-3.4', 'CA-4.3', 'CA-5.1']
const MATEO_MARKED = ['3.2', '3.3', 'TX-3.4', 'TX-4.5']

const rows = (page: Page) => page.locator('[data-slot="section-row"]')
const everyoneRows = (page: Page) =>
  page.locator('[data-slot="section-row"][aria-label*="Applies to Everyone."]')
const rowIds = (page: Page) =>
  rows(page).evaluateAll((links) =>
    links.map((link) => link.querySelector('span')!.textContent!.trim()),
  )
const markedIds = (page: Page) =>
  rows(page)
    .filter({ has: page.getByText('Applies to you', { exact: true }) })
    .evaluateAll((links) => links.map((link) => link.querySelector('span')!.textContent!.trim()))

async function openHandbook(page: Page, name: FirstName, path = '/handbook') {
  await startAs(page, name)
  await page.goto(path)
}
async function openList(page: Page, name: FirstName) {
  await openHandbook(page, name)
  await expect(page.getByRole('heading', { level: 1, name: 'Employee handbook' })).toBeVisible()
  await expect(rows(page).first()).toBeVisible()
}
const cited = (page: Page) => page.getByRole('region', { name: 'Cited passage' })
const noViolations = async (page: Page, rules: string[] = []) =>
  expect((await scan(page, rules)).violations).toEqual([])
const noSidewaysScroll = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)

test.describe('the handbook home', () => {
  test('lists every section of the pinned version, grouped by chapter and then by addendum', async ({
    page,
  }) => {
    await openList(page, 'Priya')
    const ids = await rowIds(page)
    const company = ids.filter((id) => !id.includes('-'))
    expect(company.length).toBeGreaterThanOrEqual(20)
    expect(ids.indexOf('1.1')).toBe(0)
    // Addenda follow every company section, in the order California, Colorado, Texas.
    const firstAddendum = ids.findIndex((id) => id.includes('-'))
    expect(firstAddendum).toBe(company.length)
    const states = ids.slice(firstAddendum).map((id) => id.split('-')[0])
    expect(states).toEqual(
      [...states].sort((a, b) => ['CA', 'CO', 'TX'].indexOf(a!) - ['CA', 'CO', 'TX'].indexOf(b!)),
    )
    await expect(page.getByRole('heading', { level: 2, name: 'State addenda' })).toBeVisible()
    await expect(page.getByText('Juniper Row · Version')).toBeVisible()
    // Each row says who it applies to and when it changed.
    await expect(rows(page).first()).toHaveAccessibleName(
      /^1\.1 About this handbook\. Applies to Everyone\. Last updated [A-Z][a-z]{2} \d+, \d{4}$/,
    )
    await expect(
      page.getByText(/is a fictional company\. This handbook is demo content/),
    ).toBeVisible()
  })

  test('marks, in the list, only the restricted sections that cover Priya, never an Everyone row', async ({
    page,
  }) => {
    await openList(page, 'Priya')
    expect(await markedIds(page)).toEqual(PRIYA_MARKED)
    await expect(everyoneRows(page).getByText('Applies to you')).toHaveCount(0)
    await expect(page.getByText("Doesn't apply to you")).toHaveCount(0)
  })

  test('marks the restricted sections that cover Mateo, an hourly Texas employee', async ({
    page,
  }) => {
    await openList(page, 'Mateo')
    expect(await markedIds(page)).toEqual(MATEO_MARKED)
  })

  test('"Applies to me" keeps exactly the sections that cover the person, and the counts match', async ({
    page,
  }) => {
    await openList(page, 'Priya')
    const total = (await rows(page).count()).toString()
    const everyone = await everyoneRows(page).count()
    await page.getByRole('combobox', { name: 'Show' }).click()
    const allOption = page.getByRole('option', { name: new RegExp(`^All sections, ${total}$`) })
    await expect(allOption).toBeVisible()
    const mine = page.getByRole('option', { name: /^Applies to me, \d+$/ })
    const count = Number((await mine.innerText()).match(/(\d+)\s*$/)![1])
    expect(count).toBe(everyone + PRIYA_MARKED.length)
    await mine.click()
    await expect(page).toHaveURL(/show=mine/)
    await expect(rows(page)).toHaveCount(count)
    const ids = await rowIds(page)
    expect(ids.filter((id) => id.includes('-'))).toEqual(PRIYA_MARKED)
    expect(ids).not.toContain('CO-4.3')
    expect(ids).not.toContain('3.2') // hourly staff only; Priya is salaried
  })

  test('puts the sections that apply first in search, then by relevance, with the matched words emphasized', async ({
    page,
  }) => {
    await openList(page, 'Mateo')
    await page.getByRole('searchbox', { name: 'Search the handbook' }).fill('overtime')
    await expect(page).toHaveURL(/q=overtime/)
    const results = page.getByRole('list', { name: 'Search results' }).getByRole('link')
    await expect(results.first()).toHaveAccessibleName(/^3\.2 Overtime/)
    await expect(page.getByText(/sections? match/)).toBeVisible()
    const states = await results.evaluateAll((links) =>
      links.map((link) => /Doesn.t apply to you/.test(link.textContent ?? '')),
    )
    expect(states.length).toBeGreaterThanOrEqual(2)
    // Every result that applies comes before every one that doesn't.
    expect(states).toEqual([...states].sort((a, b) => Number(a) - Number(b)))
    expect(states[0]).toBe(false)
    expect(states.at(-1)).toBe(true)
    await expect(results.first().locator('mark').first()).toHaveText(/overtime/i)
    // The marker and its icon show on every result.
    await expect(results.first().getByText('Applies to you')).toBeVisible()
    await expect(results.last().getByText("Doesn't apply to you")).toBeVisible()
    await noViolations(page)
  })

  test('offers "Clear search" and "Ask the assistant" when nothing matches, which opens Ask unsent', async ({
    page,
  }) => {
    await openList(page, 'Priya')
    const box = page.getByRole('searchbox', { name: 'Search the handbook' })
    await box.fill('dental plan')
    await expect(page.getByText('No sections match “dental plan.”')).toBeVisible()
    await noViolations(page)
    await page.getByRole('button', { name: 'Clear search' }).first().click()
    await expect(box).toHaveValue('')
    await expect(rows(page).first()).toBeVisible()
    await box.fill('dental plan')
    await page.getByRole('button', { name: 'Ask the assistant' }).click()
    await expect(page).toHaveURL('/ask')
    await expect(page.getByRole('textbox', { name: 'Ask Open Door' })).toHaveValue('dental plan')
    // Not sent: no conversation started.
    await expect(
      page.getByRole('heading', { level: 1, name: /^Good (morning|afternoon|evening), Priya\.$/ }),
    ).toBeVisible()
  })

  test('reaches every row by keyboard with a visible focus ring', async ({ page }) => {
    await openList(page, 'Priya')
    await rows(page).first().focus()
    await page.keyboard.press('Shift+Tab')
    await page.keyboard.press('Tab')
    await expect(rows(page).first()).toBeFocused()
    expect(await hasVisibleFocus(page)).toBe(true)
    await page.keyboard.press('Tab')
    await expect(rows(page).nth(1)).toBeFocused()
    expect(await hasVisibleFocus(page)).toBe(true)
  })

  test('has no axe violations in the list, "Applies to me", and loading states', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    const release = await holdRequests(page, '**/api/v1/handbook', 'GET')
    await page.goto('/handbook')
    await expect(page.getByText('Loading the handbook')).toBeAttached()
    await expect(page.locator('[aria-busy="true"]')).toBeVisible()
    await noViolations(page)
    release()
    await expect(rows(page).first()).toBeVisible()
    await noViolations(page)
    await page.goto('/handbook?show=mine')
    await expect(rows(page)).toHaveCount(PRIYA_MARKED.length + (await countEveryone(page)))
    await noViolations(page)
  })

  test('stacks the list at 390 px with nothing scrolling sideways', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await openList(page, 'Priya')
    expect(await noSidewaysScroll(page)).toBe(true)
    const row = rows(page).first()
    const box = (await row.locator('span').nth(1).boundingBox())!
    const badge = (await row.getByText('Everyone', { exact: true }).boundingBox())!
    // The audience sits under the title, not beside it.
    expect(badge.y).toBeGreaterThan(box.y + box.height - 2)
    await expect(row).toContainText(/[A-Z][a-z]{2} \d+, \d{4}/)
    await noViolations(page)
    await page.getByRole('searchbox', { name: 'Search the handbook' }).fill('overtime')
    await expect(page.getByRole('list', { name: 'Search results' })).toBeVisible()
    expect(await noSidewaysScroll(page)).toBe(true)
  })
})

async function countEveryone(page: Page) {
  // From the full list: the rows that apply to everyone.
  return await page.evaluate(async () => {
    const body = (await (await fetch('/api/v1/handbook')).json()) as {
      sections: { appliesToMe: boolean; kind: string; audienceLabel: string }[]
    }
    return body.sections.filter((s) => s.appliesToMe && s.audienceLabel === 'Everyone').length
  })
}

test.describe('a section page', () => {
  test('shows its eyebrow, title, badge, marker, date, notice, "State rules", and neighbors', async ({
    page,
  }) => {
    await openHandbook(page, 'Priya', '/handbook/4.3')
    await expect(page.getByText('§4.3 · Time off')).toBeVisible()
    await expect(page.getByRole('heading', { level: 1, name: 'Sick leave' })).toBeVisible()
    await expect(page.getByRole('article').getByText('Applies to:')).toBeVisible()
    await expect(page.getByRole('article').getByText('Everyone', { exact: true })).toBeVisible()
    await expect(
      page.getByRole('article').getByText('Applies to you', { exact: true }).first(),
    ).toBeVisible()
    await expect(page.getByText(/^Last updated/).first()).toBeVisible()
    await expect(
      page.getByText(/is a fictional company\. This handbook is demo content/),
    ).toBeVisible()
    const stateRules = page.getByRole('link', { name: /CA-4\.3/ }).first()
    await expect(stateRules).toBeVisible()
    await expect(page.getByRole('link', { name: /CO-4\.3/ }).first()).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Previous and next' })).toBeVisible()
    await noViolations(page)
  })

  test('shows "Supplements" and Sources on an addendum', async ({ page }) => {
    await openHandbook(page, 'Priya', '/handbook/CA-4.3')
    await expect(page.getByText('CA-4.3 · California addendum')).toBeVisible()
    await expect(page.getByText('Supplements', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Sources' })).toBeVisible()
    const sources = page.getByRole('region', { name: 'Sources' })
    await expect(sources.getByText(/^California Labor Code §§245–249/)).toBeVisible()
    await expect(page.getByText('Applies to you', { exact: true })).toBeVisible()
    await noViolations(page)
  })

  test('shows Mateo on CA-4.3 the neutral note linking to the company section', async ({
    page,
  }) => {
    await openHandbook(page, 'Mateo', '/handbook/CA-4.3')
    await expect(page.getByText("Doesn't apply to you", { exact: true })).toBeVisible()
    const note = page.getByRole('note')
    await expect(note).toContainText('This section is for California employees.')
    await expect(note).toContainText('Austin warehouse in Texas')
    const link = note.getByRole('link', { name: 'See what applies to you: §4.3 Sick leave' })
    await noViolations(page)
    await link.click()
    await expect(page).toHaveURL('/handbook/4.3')
    await expect(page.getByRole('heading', { level: 1, name: 'Sick leave' })).toBeVisible()
  })

  test('moves focus to the cited passage on a deep link, and "Cited passage" is heard first', async ({
    page,
  }) => {
    await openHandbook(page, 'Priya', '/handbook/CA-4.3?passage=p2')
    const region = cited(page)
    await expect(region).toBeVisible()
    await expect(region).toBeFocused()
    await expect(region).toBeInViewport()
    // The region's name is the label, which a screen reader reads before the text.
    await expect(region).toHaveAccessibleName('Cited passage')
    await expect(region.getByRole('button', { name: 'Clear highlight' })).toBeVisible()
    await noViolations(page)
  })

  test('"Clear highlight" removes the passage without a new history entry and keeps focus there', async ({
    page,
  }) => {
    await openHandbook(page, 'Priya', '/handbook/CA-4.3?passage=p2')
    await expect(cited(page)).toBeFocused()
    const before = await page.evaluate(() => history.length)
    await cited(page).getByRole('button', { name: 'Clear highlight' }).click()
    await expect(page).toHaveURL('/handbook/CA-4.3')
    await expect(cited(page)).toHaveCount(0)
    expect(await page.evaluate(() => history.length)).toBe(before)
    await expect(page.locator('#passage-p2')).toBeFocused()
    await noViolations(page)
  })

  test('shows a section that is not in the pinned version as the missing-section page, inside the shell', async ({
    page,
  }) => {
    await openHandbook(page, 'Priya', '/handbook/8.2')
    await expect(
      page.getByRole('heading', { level: 1, name: "This section isn't in your handbook version." }),
    ).toBeVisible()
    await expect(
      page.getByText(/There.s no §8\.2 in version [\d.]+ of the Juniper Row handbook\./),
    ).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
    await noViolations(page)
    await page.getByRole('link', { name: 'Back to the handbook' }).click()
    await expect(page).toHaveURL('/handbook')
  })

  test('marks the current section in the chapter navigator with aria-current="page"', async ({
    page,
  }) => {
    await openHandbook(page, 'Priya', '/handbook/4.3')
    const nav = page.getByRole('navigation', { name: /^Chapter 4/ })
    const current = nav.locator('[aria-current="page"]')
    await expect(current).toHaveCount(1)
    await expect(current).toContainText('4.3')
    await nav.getByRole('link', { name: /4\.1/ }).click()
    await expect(page).toHaveURL('/handbook/4.1')
    await expect(nav.locator('[aria-current="page"]')).toContainText('4.1')
  })

  test('draws a visible focus ring on its links', async ({ page }) => {
    await openHandbook(page, 'Priya', '/handbook/4.3')
    const link = page
      .getByRole('navigation', { name: /^Chapter 4/ })
      .getByRole('link')
      .first()
    await link.focus()
    await page.keyboard.press('Shift+Tab')
    await page.keyboard.press('Tab')
    await expect(link).toBeFocused()
    expect(await hasVisibleFocus(page)).toBe(true)
  })

  test('has no axe violations while loading', async ({ page }) => {
    await startAs(page, 'Priya')
    const release = await holdRequests(page, '**/api/v1/handbook/sections/4.3', 'GET')
    await page.goto('/handbook/4.3')
    await expect(page.getByText('Loading section')).toBeAttached()
    await noViolations(page)
    release()
    await expect(page.getByRole('heading', { level: 1, name: 'Sick leave' })).toBeVisible()
  })

  test('moves the navigator below the article at 390 px with nothing scrolling sideways', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await openHandbook(page, 'Priya', '/handbook/CA-4.3?passage=p2')
    await expect(cited(page)).toBeVisible()
    expect(await noSidewaysScroll(page)).toBe(true)
    const article = (await page.getByRole('article').boundingBox())!
    const nav = (await page.getByRole('navigation', { name: /addendum/i }).boundingBox())!
    expect(nav.y).toBeGreaterThanOrEqual(article.y + article.height - 2)
    await noViolations(page)
  })
})
