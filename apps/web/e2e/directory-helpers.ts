import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { expect, type Browser, type Page } from '@playwright/test'
import { startAs, type FirstName } from './helpers'

// Shared by directory.spec.ts and profile.spec.ts.

/** The list request, `GET /api/v1/people?...`, and not the facets or a profile. */
export const isListRequest = (url: URL) => url.pathname === '/api/v1/people'

/** Holds the directory's list request until `release()`, then lets it through to the real API. */
export async function holdList(page: Page) {
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route(isListRequest, async (route) => {
    await gate
    return route.continue()
  })
  return release
}

/** Starts a sandbox as `name` and opens the directory through the nav, as a visitor would. */
export async function openDirectory(page: Page, name: FirstName) {
  await startAs(page, name)
  await page.getByRole('link', { name: 'Directory' }).click()
  await expect(page.getByRole('list', { name: 'People' })).toBeVisible()
  await expect(page.getByText(/^120 people$/)).toBeVisible()
}

/** Searches for someone and opens their profile from the one matching row. */
export async function openProfileBySearch(page: Page, search: string, rowName: RegExp) {
  await page.getByRole('searchbox').fill(search)
  await expect(page).toHaveURL(/\?q=/)
  const row = page.getByRole('list', { name: 'People' }).getByRole('link', { name: rowName })
  await expect(row).toHaveCount(1)
  await row.click()
  await expect(page).toHaveURL(/\/directory\/[0-9a-f-]{36}$/)
}

/** Leo's private details, from the API, as someone who may read them. */
export type LeoPrivate = {
  personalEmail: string
  phone: string
  homeAddress: string
  dateOfBirth: string
}

/**
 * Leo's real private values, read through the API as Dana in a second browser context (a sandbox
 * of its own). Every sandbox is the same seeded company (seed_data.py's SEED), so these are the
 * values Priya's sandbox holds for Leo too. Dana's sandbox is separate, so reading them here
 * writes no audit event in the sandbox under test.
 */
export async function leosPrivateValues(browser: Browser, baseURL: string): Promise<LeoPrivate> {
  const context = await browser.newContext({ baseURL })
  try {
    const page = await context.newPage()
    await startAs(page, 'Dana')
    const values = await page.evaluate(async () => {
      const people = (await (await fetch('/api/v1/people?q=Nakamura')).json()) as {
        items: { id: string }[]
      }
      const response = await fetch(`/api/v1/people/${people.items[0]!.id}/private`)
      return (await response.json()) as LeoPrivate
    })
    for (const value of Object.values(values)) expect(value.length).toBeGreaterThan(3)
    return values
  } finally {
    await context.close()
  }
}

/** The person's ID as the API reports it for the signed-in person. */
export const myId = (page: Page) =>
  page.evaluate(async () => ((await (await fetch('/api/v1/me')).json()) as { id: string }).id)

export type AuditEvent = {
  action: string
  via: string
  target_type: string | null
  target_id: string | null
  actor: string
  after: Record<string, unknown> | null
}

/**
 * The audit events a person wrote, read straight from the database as its owner by
 * apps/api/scripts/read_audit_events.py (the same DATABASE URLs as the API). The browser has no
 * route to the audit log, so this is how a test sees what was really stored.
 */
export function auditEventsBy(actorId: string): AuditEvent[] {
  const { ANTHROPIC_API_KEY: _empty, ...env } = process.env
  const out = execFileSync('uv', ['run', 'python', 'scripts/read_audit_events.py', actorId], {
    cwd: resolve(import.meta.dirname, '../../api'),
    env,
    encoding: 'utf8',
  })
  return JSON.parse(out) as AuditEvent[]
}

/**
 * Whether the focused element shows where focus is: the 2 px outline the buttons and links draw,
 * or the halo (a box shadow) the search field draws instead.
 */
export const hasVisibleFocus = (page: Page) =>
  page.evaluate(() => {
    const style = getComputedStyle(document.activeElement!)
    const outline = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2
    return outline || style.boxShadow !== 'none'
  })
