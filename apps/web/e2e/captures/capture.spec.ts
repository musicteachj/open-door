import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, test, type Browser, type Page } from '@playwright/test'
import { SPECIMEN_ORIGIN } from '../../playwright.captures.config'
import {
  AREAS,
  buildFile,
  COMPONENT_ROWS,
  designFile,
  SCREEN_ROWS,
  specimenPath,
  type Area,
  type ComponentRow,
} from './manifest'
import { renderReport, type ReportRow } from './report'

// `make captures`. Photographs each gallery state at 1440 px, after the interaction the manifest
// names, and each design specimen page whole, then writes captures/index.html beside them.
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

test('captures the build and the design specimens, then writes the report', async ({
  browser,
  page,
}) => {
  rmSync(OUT, { recursive: true, force: true })
  mkdirSync(resolve(OUT, 'design'), { recursive: true })
  mkdirSync(resolve(OUT, 'build'), { recursive: true })

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

    // Stages 5 and 6 add screen rows here, one per screenshot in docs/design/screens/.
    expect(SCREEN_ROWS).toEqual([])
  } finally {
    // Written even if the run times out or fails, so the pictures taken so far are not lost.
    writeFileSync(resolve(OUT, 'index.html'), renderReport(rows))
    const missing = rows.filter((r) => r.design === null || r.build === null).length
    console.log(
      `Wrote ${resolve(OUT, 'index.html')}: ${rows.length} rows, ${missing} with a missing picture`,
    )
  }
})
