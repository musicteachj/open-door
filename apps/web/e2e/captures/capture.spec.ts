import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, test, type Browser, type Page } from '@playwright/test'
import { SPECIMEN_ORIGIN } from '../../playwright.captures.config'
import {
  AREAS,
  buildFile,
  buildScreenFile,
  COMPONENT_ROWS,
  designFile,
  designScreenFile,
  galleryFrameSelector,
  SCREEN_ROWS,
  screenGroup,
  specimenPath,
  type Area,
  type ComponentRow,
  type ScreenRow,
} from './manifest'
import { holdRequests, problem, setSandboxLeft, startAs } from '../helpers'
import { holdList, isListRequest, openProfileBySearch } from '../directory-helpers'
import { renderReport, type ReportRow } from './report'

// `make captures`. Photographs each gallery state at 1440 px, after the interaction the manifest
// names, and each design specimen page whole, then each screen the build has beside its design
// screenshot, then writes captures/index.html beside them. The screens need the API on :8100.
// A picture that can't be taken is recorded as "Not captured" and the run goes on.

const OUT = resolve(import.meta.dirname, '../../captures')
const REPO_ROOT = resolve(import.meta.dirname, '../../../..')

/** The specimen's own size comes from the first line of its page: viewport="700x540". */
function specimenViewport(area: Area) {
  const head = readFileSync(resolve(REPO_ROOT, specimenPath(area)), 'utf8').slice(0, 300)
  const match = /viewport="(\d+)x(\d+)"/.exec(head)
  return { width: Number(match?.[1] ?? 700), height: Number(match?.[2] ?? 540) }
}

async function photographSpecimen(browser: Browser, area: Area): Promise<string | null> {
  const context = await browser.newContext({ viewport: specimenViewport(area) })
  try {
    const page = await context.newPage()
    await page.goto(
      `${SPECIMEN_ORIGIN}/${specimenPath(area).replace('docs/design/system/', '')}`,
      { timeout: 10_000 },
    )
    // The specimen renders into #root only after unpkg's React and Babel load and the sketches
    // are fetched. If that never happens the root stays empty.
    await page.locator('#root > *').first().waitFor({ timeout: 10_000 })
    await page.evaluate(() => document.fonts.ready)
    const file = designFile(area)
    await page.screenshot({ path: resolve(OUT, file), fullPage: true })
    return file
  } catch (error) {
    console.warn(`Specimen "${area}" not captured: ${String(error).split('\n')[0]}`)
    return null
  } finally {
    await context.close()
  }
}

async function photographState(page: Page, row: ComponentRow) {
  await page.goto('/gallery')
  const section = page.locator(`section[aria-labelledby="${row.id}"]`)
  // Centered, so a panel that opens above or below the section stays inside the viewport.
  await section.evaluate((el) => el.scrollIntoView({ block: 'center' }))
  if (row.interaction) {
    const target = section.locator(row.interaction.target).first()
    if (row.interaction.action === 'hover') await target.hover()
    else if (row.interaction.action === 'focus') await target.focus()
    else await target.click()
  }
  const path = buildFile(row)
  if (row.overlay) {
    // The panel must really be open, so a row can never silently photograph without it. A tooltip
    // opens after a delay, which this wait covers.
    await expect(page.getByRole(row.overlay).first()).toBeVisible({ timeout: 5_000 })
    await page.waitForTimeout(300)
    await page.screenshot({ path: resolve(OUT, path) })
  } else {
    // Let a focus or hover transition settle.
    await page.waitForTimeout(300)
    await section.screenshot({ path: resolve(OUT, path) })
  }
  return path
}

const HOUR_MS = 3_600_000
const MINUTE_MS = 60_000

/** Sets a screen up in its state, and returns what to photograph. The same tools the browser
 * tests use: page.route holds or fails a request, and page.clock sets the time left. */
async function reachScreen(page: Page, row: ScreenRow) {
  const card = (name: string) => page.getByRole('button', { name: new RegExp(`^Start a sandbox as ${name} `) })
  const switcher = page.getByRole('button', { name: /^Switch persona/ })
  const reach = async () => {
    if (row.persona) {
      await startAs(page, row.persona)
      if (row.setup === 'expiry-banner') await setSandboxLeft(page, 2 * HOUR_MS + 50 * MINUTE_MS)
      else if (row.setup !== 'session-expired') {
        await setSandboxLeft(page, 21 * HOUR_MS + 30 * MINUTE_MS)
      }
      // Held before the page opens, so the list's first request is the one that waits.
      if (row.setup === 'directory-loading') await holdList(page)
      // The in-shell error: the directory's list request fails with a request ID.
      if (row.setup === 'server-error') {
        await page.route(isListRequest, (route) =>
          route.fulfill({
            status: 500,
            contentType: 'application/problem+json',
            headers: { 'X-Request-ID': '7f3a9c2e5b1d4a60918c2e4f6a8b0d13' },
            body: problem(500, 'Internal Server Error'),
          }),
        )
      }
      if (row.setup === 'handbook-loading') await holdRequests(page, '**/api/v1/handbook', 'GET')
      if (row.setup === 'section-loading') {
        await holdRequests(page, '**/api/v1/handbook/sections/4.3', 'GET')
      }
      if (row.route !== '/ask') await page.goto(row.route)
    } else {
      await page.goto(row.route)
    }
  }
  await reach()

  switch (row.setup) {
    case 'landing':
      await expect(card('Priya')).toBeVisible()
      break
    case 'landing-hover-focus':
      await expect(card('Priya')).toBeVisible()
      await page.keyboard.press('Tab')
      await page.keyboard.press('Tab')
      await expect(card('Mateo')).toBeFocused()
      await card('Priya').hover()
      break
    case 'landing-starting':
      await holdRequests(page, '**/api/v1/sandboxes', 'POST')
      await card('Priya').click()
      await expect(card('Priya')).toHaveAttribute('aria-busy', 'true')
      break
    case 'landing-error':
      await page.route('**/api/v1/sandboxes', (route) =>
        route.request().method() === 'POST'
          ? route.fulfill({
              status: 500,
              contentType: 'application/problem+json',
              body: problem(500, 'Internal Server Error'),
            })
          : route.fallback(),
      )
      await card('Priya').click()
      await expect(page.getByRole('alert')).toBeVisible()
      break
    case 'persona-menu':
      await switcher.click()
      await expect(page.getByRole('menu')).toBeVisible()
      break
    case 'switching':
      await holdRequests(page, '**/api/v1/session/persona', 'PUT')
      await switcher.click()
      await page.getByRole('menuitemradio', { name: /^Marcus / }).click()
      await expect(page.getByRole('button', { name: 'Switching to Marcus…' })).toBeVisible()
      break
    case 'switched':
      await switcher.click()
      await page.getByRole('menuitemradio', { name: /^Marcus / }).click()
      await expect(page.locator('[data-slot="toast"]')).toBeVisible()
      // The pointer on the toast holds it open for the photograph.
      await page.locator('[data-slot="toast"]').hover()
      break
    case 'composer-states': {
      await page.getByRole('textbox', { name: 'Ask Open Door' }).fill('How many sick days do I get?')
      const rows = page.locator('[data-slot="try-asking-row"]')
      await rows.nth(1).hover()
      for (let i = 0; i < 6; i += 1) await page.keyboard.press('Tab')
      await rows.nth(2).focus()
      break
    }
    case 'directory':
      await expect(page.getByText('145 people', { exact: true })).toBeVisible()
      await expect(page.getByRole('list', { name: 'People' }).getByRole('listitem')).toHaveCount(50)
      break
    case 'directory-loading':
      await expect(page.getByText('Loading the directory')).toBeAttached()
      await expect(page.locator('[aria-busy="true"]')).toBeVisible()
      break
    case 'directory-my-team':
      await page.getByRole('button', { name: /^My team/ }).click()
      await expect(page.getByText('44 of 145 people', { exact: true })).toBeVisible()
      break
    case 'directory-empty':
      await page.getByRole('searchbox').fill('Jordn')
      await expect(page.getByText('No one matches “Jordn”.')).toBeVisible()
      break
    case 'directory-show-more': {
      await expect(page.getByText('Showing 50 of 145')).toBeVisible()
      await page.getByRole('button', { name: 'Show more' }).evaluate((el) => el.scrollIntoView({ block: 'end' }))
      break
    }
    case 'profile-locked':
    case 'profile-hr':
      await openProfileBySearch(page, 'Nakamura', /^Leo Nakamura/)
      await expect(page.getByRole('heading', { level: 1, name: 'Leo Nakamura' })).toBeVisible()
      if (row.setup === 'profile-hr') {
        await expect(page.getByText('Viewing private details is recorded in the audit log.')).toBeVisible()
      } else {
        await expect(page.getByText('Visible to Leo and HR')).toHaveCount(4)
      }
      break
    case 'profile-self':
      await openProfileBySearch(page, 'Raman', /^Priya Raman/)
      await expect(page.getByText('Only you and HR can see these.')).toBeVisible()
      break
    case 'nav-states':
      await page.getByRole('link', { name: 'Directory' }).hover()
      break
    case 'session-expired':
      await page.route('**/api/v1/me', (route) =>
        route.fulfill({
          status: 401,
          contentType: 'application/problem+json',
          body: problem(401, 'Unauthorized'),
        }),
      )
      // A /me already in flight takes the first nudge, so nudge until the page has seen the 401.
      await expect(async () => {
        await page.evaluate(() => window.dispatchEvent(new Event('visibilitychange')))
        await expect(page.getByRole('heading', { level: 1, name: 'This sandbox has reset.' })).toBeVisible({ timeout: 500 })
      }).toPass()
      break
    case 'server-error':
      await expect(
        page.getByRole('heading', { level: 1, name: 'Something went wrong on our side.' }),
      ).toBeVisible({ timeout: 15_000 })
      await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
      break
    case 'handbook':
      await expect(page.locator('[data-slot="section-row"]').first()).toBeVisible()
      break
    case 'handbook-search':
      await page.getByRole('searchbox', { name: 'Search the handbook' }).fill('overtime')
      await expect(page.getByText(/sections? match/)).toBeVisible()
      break
    case 'handbook-no-results':
      await page.getByRole('searchbox', { name: 'Search the handbook' }).fill('dental plan')
      await expect(page.getByText('No sections match “dental plan.”')).toBeVisible()
      break
    case 'handbook-loading':
      await expect(page.getByText('Loading the handbook')).toBeAttached()
      await expect(page.locator('[aria-busy="true"]')).toBeVisible()
      break
    case 'section':
      await expect(page.getByRole('heading', { level: 1, name: 'Sick leave' })).toBeVisible()
      break
    case 'section-loading':
      await expect(page.getByText('Loading section')).toBeAttached()
      break
    case 'cited-passage':
      await expect(page.getByRole('region', { name: 'Cited passage' })).toBeFocused()
      break
    case 'not-applicable':
      await expect(page.getByRole('note')).toBeVisible()
      break
    case 'missing-section':
      await expect(
        page.getByRole('heading', { level: 1, name: "This section isn't in your handbook version." }),
      ).toBeVisible()
      break
    case 'panel-gallery':
      await page
        .locator('section[aria-labelledby="passage-panel-open"]')
        .evaluate((el) => el.scrollIntoView({ block: 'center' }))
      break
    case 'gallery-state': {
      // A conversation state in the gallery, centered, then the interaction a person would make.
      const section = page.locator(`section[aria-labelledby="${row.galleryId}"]`)
      await section.evaluate((el) => el.scrollIntoView({ block: 'center' }))
      if (row.interaction) {
        const target = section.locator(row.interaction.target).first()
        if (row.interaction.action === 'hover') await target.hover()
        else if (row.interaction.action === 'focus') await target.focus()
        else await target.click()
      }
      break
    }
    case 'home':
    case 'expiry-banner':
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      break
    case 'not-found':
      await expect(page.getByRole('heading', { level: 1, name: "We couldn't find that page." })).toBeVisible()
      break
  }
}

async function photographScreen(browser: Browser, row: ScreenRow): Promise<string | null> {
  const context = await browser.newContext({
    baseURL: 'http://localhost:4173',
    viewport: row.viewport ?? { width: 1440, height: 900 },
  })
  try {
    const page = await context.newPage()
    await reachScreen(page, row)
    // Let a hover or focus transition settle, and a held request's spinner draw.
    await page.waitForTimeout(400)
    const file = buildScreenFile(row)
    const path = resolve(OUT, file)
    const region = {
      sidebar: () => page.getByRole('complementary', { name: 'Sidebar' }),
      main: () => page.getByRole('main'),
      rail: () => page.getByRole('complementary', { name: 'Sandbox status' }),
    }
    if (row.target === 'sidebar' || row.target === 'main' || row.target === 'rail') {
      await region[row.target]().screenshot({ path })
    } else if (row.target === 'section') {
      await page.locator(galleryFrameSelector(row.galleryId!)).screenshot({ path })
    } else {
      await page.screenshot({ path, fullPage: row.target === 'page' })
    }
    return file
  } catch (error) {
    console.warn(`Screen "${row.title}" not captured: ${String(error).split('\n')[0]}`)
    return null
  } finally {
    await context.close()
  }
}

/** The design screenshot is copied beside the report, so the report is self-contained. */
function copyScreenDesign(row: ScreenRow): string | null {
  const source = resolve(REPO_ROOT, row.designImage)
  if (!existsSync(source)) return null
  const file = designScreenFile(row)
  copyFileSync(source, resolve(OUT, file))
  return file
}

test('captures the build and the design specimens, then writes the report', async ({
  browser,
  page,
}) => {
  rmSync(OUT, { recursive: true, force: true })
  mkdirSync(resolve(OUT, 'design'), { recursive: true })
  mkdirSync(resolve(OUT, 'build/screens'), { recursive: true })
  mkdirSync(resolve(OUT, 'design/screens'), { recursive: true })

  await page.goto('/gallery')
  // A production build, which a stale `vite preview` on :4173 may be serving, has no gallery.
  const gallery = page.getByRole('heading', { level: 1, name: 'Open Door component gallery' })
  if (!(await gallery.waitFor({ timeout: 10_000 }).then(() => true, () => false))) {
    throw new Error(
      'The web server on :4173 has no gallery. Stop the other `vite preview`, or run ' +
        '`make captures`, which rebuilds dist-e2e/ with the gallery first.',
    )
  }

  const rows: ReportRow[] = []
  try {
    const designs = new Map<Area, string | null>()
    for (const area of AREAS) designs.set(area, await photographSpecimen(browser, area))

    for (const row of COMPONENT_ROWS) {
      let build: string | null = null
      try {
        build = await photographState(page, row)
      } catch (error) {
        console.warn(`State "${row.id}" not captured: ${String(error).split('\n')[0]}`)
      }
      rows.push({
        group: row.area,
        title: row.variant ? `${row.id} (${row.variant})` : row.id,
        note: row.note,
        design: designs.get(row.area) ?? null,
        build,
      })
    }

    for (const row of SCREEN_ROWS) {
      const build = await photographScreen(browser, row)
      rows.push({
        group: screenGroup(row),
        title: row.title,
        note: [row.note, row.differsUntil && `Differs by design until ${row.differsUntil}.`]
          .filter(Boolean)
          .join(' '),
        design: copyScreenDesign(row),
        build,
      })
    }
  } finally {
    // Written even if the run times out or fails, so the pictures taken so far are not lost.
    writeFileSync(resolve(OUT, 'index.html'), renderReport(rows))
    const missing = rows.filter((r) => r.design === null || r.build === null).length
    console.log(
      `Wrote ${resolve(OUT, 'index.html')}: ${rows.length} rows, ${missing} with a missing picture`,
    )
  }
})
