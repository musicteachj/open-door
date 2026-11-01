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
  SCREEN_ROWS,
  screenGroup,
  specimenPath,
  type Area,
  type ComponentRow,
  type ApprovalsState,
  type CasesState,
  type ConfirmCardState,
  type HrCasesState,
  type ScreenRow,
  type TimeOffState,
} from './manifest'
import { holdRequests, problem, setSandboxLeft, startAs } from '../helpers'
import {
  addDaysTo,
  bookOnPage,
  enterGrid,
  expireProposal,
  factsOf,
  moveToDay,
  newestProposalId,
  openFromNav,
  pickDays,
  railLink,
  nav,
  switchPersona,
  daysPastBalance,
  workdays,
  type Facts,
} from '../time-off-helpers'
import {
  ask,
  askAndWaitForAnswer,
  BUDGET_DAILY_TEXT,
  BUDGET_SANDBOX_TEXT,
  composerBox,
  QUESTIONS,
  stopButton,
  stubConversation,
} from '../conversation-helpers'
import {
  holdNextTurnStream,
  holdTurnCompletion,
  SICK_LEAVE_CITATION,
  SICK_LEAVE_SENTENCE,
} from '../held-stream'
import { holdList, isListRequest, openProfileBySearch } from '../directory-helpers'
import {
  CRISIS_WORDS,
  SENSITIVE_QUESTION,
  casePanels,
  fillForm,
  formHeading,
  HARASSMENT,
  openCaseButton,
  queueRowOf,
  queueRows,
  sendButton,
  sendCaseByApi,
  sentLine,
  wordsBox,
} from '../cases-helpers'
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
  const card = (name: string) => page.getByRole('button', { name: new RegExp(`^${name} `) })
  const switcher = page.getByRole('button', { name: /Switch persona$/ })
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
      // Screens 08 and 09: a request held or failed before the page opens, so its first read is it.
      if (row.setup === 'time-off' && row.state === 'loading') {
        await holdRequests(page, '**/api/v1/time-off/balances', 'GET')
      }
      if (row.setup === 'approvals' && row.state === 'loading') {
        await holdRequests(page, '**/api/v1/time-off/requests*', 'GET')
      }
      const failing =
        row.state === 'error'
          ? row.setup === 'time-off'
            ? '**/api/v1/time-off/balances'
            : row.setup === 'approvals'
              ? '**/api/v1/time-off/requests*'
              : null
          : null
      if (failing !== null) {
        await page.route(failing, (route) =>
          route.fulfill({
            status: 500,
            contentType: 'application/problem+json',
            headers: { 'X-Request-ID': '7f3a9c2e5b1d4a60918c2e4f6a8b0d13' },
            body: problem(500, 'Internal Server Error'),
          }),
        )
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
    case 'conversation':
      await reachConversation(page, row.scenario!)
      break
    case 'time-off':
      await reachTimeOff(page, row.state as TimeOffState)
      break
    case 'approvals':
      await reachApprovals(page, row.state as ApprovalsState)
      break
    case 'confirm-card':
      await reachConfirmCard(page, row.state as ConfirmCardState)
      break
    case 'cases':
      await reachCases(page, row.state as CasesState)
      break
    case 'hr-cases':
      await reachHrCases(page, row.state as HrCasesState)
      break
    case 'home':
    case 'expiry-banner':
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      break
    case 'not-found':
      await expect(page.getByRole('heading', { level: 1, name: "We couldn't find that page." })).toBeVisible()
      break
  }
}


// ---------------------------------------------------------------------------------------------
// Screens 08 to 10: the real Time off, Approvals, and conversation pages, brought to each state
// the way a person (or the browser tests) would. Dates come from the API's own calendar, since the
// seed's dates move with today.

const NOTE_77 = 'Please pick another week, the store needs everyone on the floor for the sale.'

/** The workday nearest `from` going `step` days at a time (-1 back, 1 forward). */
function nearestWorkday(facts: Facts, from: string, step: 1 | -1): string {
  for (let day = addDaysTo(from, step); ; day = addDaysTo(day, step)) {
    const weekday = new Date(Date.parse(day)).getUTCDay() || 7
    if (facts.weekdays.includes(weekday) && !facts.holidays.includes(day)) return day
  }
}

/** The first company holiday after today. */
function nextHoliday(facts: Facts): string {
  const holiday = facts.holidays.filter((day) => day > facts.today).sort()[0]
  if (holiday === undefined) throw new Error('The calendar has no holiday ahead')
  return holiday
}

async function reachTimeOff(page: Page, state: TimeOffState) {
  const open = page.getByRole('button', { name: 'Request time off' }).first()
  const form = page.locator('#request-form')
  const toast = page.locator('[data-slot="toast"]')
  if (state === 'loading') {
    await expect(page.getByText('Loading your time off')).toBeAttached()
    await expect(page.locator('[data-slot="requests-skeleton"]')).toBeVisible()
    return
  }
  if (state === 'error') {
    await expect(
      page.getByRole('heading', { level: 1, name: 'Something went wrong on our side.' }),
    ).toBeVisible({ timeout: 15_000 })
    return
  }
  await expect(open).toBeVisible()
  if (state === 'default' || state === 'default-full' || state === 'ceiling' || state === 'empty') {
    return
  }
  const facts = await factsOf(page)
  const day = () => workdays(facts, 14, 1)[0]!
  switch (state) {
    case 'form-one-day':
    case 'form-half-day':
      await open.click()
      await pickDays(page, form, day())
      if (state === 'form-half-day') {
        await form.getByRole('radio', { name: /^Half day/ }).click()
      }
      await expect(form.getByRole('region', { name: 'What this uses' })).toContainText('left after')
      break
    case 'form-weekend': {
      // A Friday and the Monday after it, so the weekend between is skipped.
      let friday = day()
      while ((new Date(Date.parse(friday)).getUTCDay() || 7) !== 5) friday = addDaysTo(friday, 1)
      await open.click()
      await pickDays(page, form, friday, addDaysTo(friday, 3))
      await expect(form.getByRole('region', { name: 'What this uses' })).toContainText('left after')
      break
    }
    case 'form-holiday': {
      const holiday = nextHoliday(facts)
      await open.click()
      await pickDays(
        page,
        form,
        nearestWorkday(facts, holiday, -1),
        nearestWorkday(facts, holiday, 1),
      )
      await expect(form.getByRole('region', { name: 'What this uses' })).toContainText('holiday')
      break
    }
    case 'form-sick-hours':
      await open.click()
      await form.getByRole('radio', { name: 'Sick time' }).click()
      await pickDays(page, form, nearestWorkday(facts, facts.today, -1))
      await form.getByRole('radio', { name: 'Some hours' }).click()
      await expect(form.getByRole('region', { name: 'What this uses' })).toContainText('left')
      break
    case 'form-short-notice': {
      const soon = workdays(facts, 1, 4)
      await open.click()
      await pickDays(page, form, soon[0]!, soon[3]!)
      await expect(form.getByText('usually needs 2 weeks')).toBeVisible()
      break
    }
    case 'form-not-enough': {
      const long = await daysPastBalance(page, facts)
      await open.click()
      await pickDays(page, form, long[0]!, long.at(-1)!)
      await expect(form.getByRole('alert')).toContainText('You have')
      break
    }
    case 'form-overlap': {
      const booked = await bookOnPage(page)
      await open.click()
      await pickDays(page, form, booked)
      await expect(form.getByRole('region', { name: 'What this uses' })).toContainText(
        'Already booked',
      )
      break
    }
    case 'form-submitting':
      await holdRequests(page, '**/api/v1/time-off/requests', 'POST')
      await open.click()
      await pickDays(page, form, day())
      await form.getByRole('button', { name: 'Request time off' }).click()
      await expect(form.getByRole('button', { name: 'Requesting…' })).toBeVisible()
      break
    case 'submitted':
      await bookOnPage(page)
      await toast.hover()
      break
    case 'submitted-sick':
      await open.click()
      await form.getByRole('radio', { name: 'Sick time' }).click()
      await pickDays(page, form, workdays(facts, 1, 1)[0]!)
      await form.getByRole('button', { name: 'Record sick time' }).click()
      await expect(toast).toContainText('Recorded.')
      await toast.hover()
      break
    case 'cancel-confirm':
      await bookOnPage(page)
      await page.getByRole('button', { name: /^Cancel PTO on / }).click()
      await expect(page.getByRole('alertdialog')).toBeVisible()
      break
    case 'canceled':
      await bookOnPage(page)
      await page.getByRole('button', { name: /^Cancel PTO on / }).click()
      await page.getByRole('alertdialog').getByRole('button', { name: 'Cancel request' }).click()
      await expect(toast).toContainText('Canceled.')
      await toast.hover()
      break
    case 'date-picker-open':
      await open.click()
      await enterGrid(page, form)
      await expect(form.getByRole('grid')).toBeVisible()
      break
    case 'date-picker-sick':
      await open.click()
      await form.getByRole('radio', { name: 'Sick time' }).click()
      await enterGrid(page, form)
      await expect(form.getByRole('grid')).toBeVisible()
      break
    case 'date-picker-range': {
      const holiday = nextHoliday(facts)
      await open.click()
      await pickDays(
        page,
        form,
        nearestWorkday(facts, holiday, -1),
        nearestWorkday(facts, holiday, 1),
        { close: false },
      )
      await moveToDay(page, holiday)
      await expect(page.getByRole('tooltip')).toBeVisible()
      break
    }
  }
}

/** Marcus's page with Priya's request waiting beside Zara's, as the frames show two. */
async function twoWaiting(page: Page) {
  await switchPersona(page, 'Priya')
  await bookOnPage(page)
  await switchPersona(page, 'Marcus')
  await openFromNav(page, /^Approvals, 2 waiting$/, '/approvals')
  await expect(page.locator('[data-slot="approval-card"]')).toHaveCount(2)
}

async function reachApprovals(page: Page, state: ApprovalsState) {
  const cards = page.locator('[data-slot="approval-card"]')
  const zara = cards.filter({ hasText: 'Zara Bautista' })
  const dialog = page.getByRole('alertdialog')
  const toast = page.locator('[data-slot="toast"]')
  if (state === 'loading') {
    await expect(page.getByText('Loading approvals')).toBeAttached()
    await expect(page.locator('[data-slot="approvals-skeleton"]')).toBeVisible()
    return
  }
  if (state === 'error') {
    await expect(
      page.getByRole('heading', { level: 1, name: 'Something went wrong on our side.' }),
    ).toBeVisible({ timeout: 15_000 })
    return
  }
  if (state === 'empty') {
    await zara.getByRole('button', { name: /^Approve / }).click()
    await dialog.getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(toast).toContainText('Approved.')
    await page.reload()
    await expect(page.getByText('Nothing is waiting for you.')).toBeVisible()
    return
  }
  if (state === 'home-manager') {
    await twoWaiting(page)
    await openFromNav(page, 'Ask', '/ask')
    await expect(railLink(page, 'approvals? waiting')).toBeVisible()
    return
  }
  if (state === 'conflict') {
    // See the browser test of the same name: Priya cancels for real, Marcus's read stays out of date.
    await switchPersona(page, 'Priya')
    await bookOnPage(page)
    const listed = await page.evaluate(async () => {
      const response = await fetch(
        '/api/v1/time-off/requests?scope=mine&from=2000-01-01&to=2100-01-01',
      )
      const { items } = (await response.json()) as { items: { status: string }[] }
      return items.find((item) => item.status === 'pending')!
    })
    await page.getByRole('button', { name: /^Cancel PTO on / }).click()
    await page.getByRole('alertdialog').getByRole('button', { name: 'Cancel request' }).click()
    await expect(page.locator('[data-slot="toast"]')).toContainText('Canceled.')
    let stale = true
    await page.route('**/api/v1/time-off/requests?*scope=waiting*', async (route) => {
      const response = await route.fetch()
      const body = (await response.json()) as { items: unknown[] }
      if (stale) body.items.push(listed)
      await route.fulfill({ response, json: body })
    })
    page.on('response', (response) => {
      if (response.url().endsWith('/decision')) stale = false
    })
    await switchPersona(page, 'Marcus')
    await openFromNav(page, /^Approvals, 1 waiting$/, '/approvals')
    await expect(cards).toHaveCount(2)
    const priya = cards.filter({ hasText: 'Priya Raman' })
    await priya.getByRole('button', { name: /^Approve / }).click()
    await dialog.getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(priya.getByRole('alert')).toContainText('canceled this request')
    return
  }
  await twoWaiting(page)
  switch (state) {
    case 'default':
    case 'default-full':
    case 'nav-manager':
      break
    case 'approve-confirm':
      await zara.getByRole('button', { name: /^Approve / }).click()
      await expect(dialog.getByRole('button', { name: 'Go back' })).toBeFocused()
      break
    case 'deny-confirm':
      await zara.getByRole('button', { name: /^Deny / }).click()
      await dialog.getByRole('textbox').fill(NOTE_77)
      await expect(dialog).toContainText('77 of 300')
      break
    case 'deciding':
      await holdRequests(page, '**/api/v1/time-off/requests/*/decision', 'POST')
      await zara.getByRole('button', { name: /^Approve / }).click()
      await dialog.getByRole('button', { name: 'Approve', exact: true }).click()
      await expect(dialog.getByRole('button', { name: 'Approving…' })).toBeVisible()
      break
    case 'approved':
      await zara.getByRole('button', { name: /^Approve / }).click()
      await dialog.getByRole('button', { name: 'Approve', exact: true }).click()
      await expect(toast).toContainText('Approved.')
      await toast.hover()
      break
    case 'denied':
      await zara.getByRole('button', { name: /^Deny / }).click()
      await dialog.getByRole('textbox').fill(NOTE_77)
      await dialog.getByRole('button', { name: 'Deny', exact: true }).click()
      await expect(toast).toContainText('Denied.')
      await toast.hover()
      break
  }
}

async function reachConfirmCard(page: Page, state: ConfirmCardState) {
  const BOOK = 'book next friday'
  const card = (index = 0) => page.locator('[data-slot="confirm-card"]').nth(index)
  const confirm = (index = 0) => card(index).getByRole('button', { name: /^(Confirm|Deny): / })
  const dismiss = (index = 0) => card(index).getByRole('button', { name: /^Dismiss, / })
  const executed = (index = 0) => card(index).locator('output')
  const ledger = page.locator('[data-slot="glance-list"]')
  switch (state) {
    case 'pending':
    case 'holiday':
      await askAndWaitForAnswer(page, BOOK)
      await expect(confirm()).toBeVisible()
      break
    case 'pending-streaming': {
      await holdTurnCompletion(page)
      await ask(page, BOOK)
      await expect(card().getByText('Wait for the answer to finish')).toBeVisible()
      await expect(stopButton(page)).toBeVisible()
      break
    }
    case 'confirming':
      await askAndWaitForAnswer(page, BOOK)
      await holdRequests(page, '**/api/v1/assistant/proposals/*/confirm', 'POST')
      await confirm().click()
      await expect(card().getByRole('button', { name: 'Confirming…' })).toBeVisible()
      break
    case 'executed':
      await askAndWaitForAnswer(page, BOOK)
      await confirm().click()
      await expect(executed()).toContainText('Requested.')
      await expect(ledger.getByRole('link', { name: /1 request pending/ })).toBeVisible()
      break
    case 'failed': {
      await askAndWaitForAnswer(page, BOOK)
      // The same day is booked behind the card's back, so Confirm is refused for real.
      const taken = await page.evaluate(async () => {
        const read = await fetch('/api/v1/assistant/conversations/current')
        const body = (await read.json()) as {
          turns: { proposals: { card: { startDate: string; endDate: string } }[] }[]
        }
        const { startDate, endDate } = body.turns.flatMap((turn) => turn.proposals).at(-1)!.card
        const token = /(?:^|; )__Host-od_csrf=([^;]*)/.exec(document.cookie)![1]!
        const response = await fetch('/api/v1/time-off/requests', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
          body: JSON.stringify({ type: 'pto', startDate, endDate, partialMinutes: null }),
        })
        return response.status
      })
      expect(taken).toBeLessThan(300)
      await confirm().click()
      await expect(card().getByRole('alert')).toContainText('Nothing was changed.')
      break
    }
    case 'dismissed':
      await askAndWaitForAnswer(page, BOOK)
      await dismiss().click()
      await expect(card()).toContainText('You dismissed this.')
      break
    case 'replaced':
      await askAndWaitForAnswer(page, BOOK)
      await askAndWaitForAnswer(page, BOOK)
      await expect(card(0)).toContainText('Replaced by a newer card.')
      break
    case 'expired':
      await askAndWaitForAnswer(page, BOOK)
      await expireProposal(await newestProposalId(page))
      await confirm().click()
      await expect(card()).toContainText('This card expired after 15 minutes.')
      break
    case 'sick':
      await askAndWaitForAnswer(page, "I'm sick tomorrow")
      await expect(confirm()).toBeVisible()
      break
    case 'approve':
      await askAndWaitForAnswer(page, 'approve it')
      await expect(confirm()).toBeVisible()
      break
    case 'deny':
      await askAndWaitForAnswer(page, 'deny it')
      await card().getByRole('textbox').fill(NOTE_77)
      await expect(card()).toContainText('77 of 300')
      break
    case 'cancel':
      await bookOnPage(page)
      await openFromNav(page, 'Ask', '/ask')
      await askAndWaitForAnswer(page, 'cancel my request')
      await expect(confirm()).toBeVisible()
      break
    case 'executed-variants':
      await askAndWaitForAnswer(page, BOOK)
      await confirm(0).click()
      await expect(executed(0)).toContainText('Requested.')
      await askAndWaitForAnswer(page, "I'm sick tomorrow")
      await confirm(1).click()
      await expect(executed(1)).toContainText('Recorded.')
      await askAndWaitForAnswer(page, 'cancel my request')
      await confirm(2).click()
      await expect(executed(2)).toContainText('Canceled.')
      break
    case 'conversation':
      await askAndWaitForAnswer(page, BOOK)
      await page.getByRole('button', { name: 'Show your work' }).click()
      break
    case 'conversation-executed':
      await askAndWaitForAnswer(page, BOOK)
      await confirm().click()
      await expect(executed()).toContainText('Requested.')
      await page.getByRole('button', { name: 'Show your work' }).click()
      break
    case 'sensitive':
    case 'sensitive-work': {
      // STUB: the scripted model answers one trigger per message, so a real sick-time card (turn
      // 1) is moved under the sensitive turn (turn 2) in the conversation GET.
      await askAndWaitForAnswer(page, "I'm sick tomorrow")
      await askAndWaitForAnswer(page, QUESTIONS.sensitive)
      await stubConversation(page, (body) => {
        const turns = body.turns as unknown as { proposals: unknown[] }[]
        turns[1]!.proposals = turns[0]!.proposals
        body.turns = [turns[1]!] as unknown as typeof body.turns
      })
      await page.reload()
      await expect(confirm()).toBeVisible()
      await expect(page.locator('[data-slot="escalation-panel"]')).toBeVisible()
      await expect(railLink(page, 'PTO available')).toBeVisible()
      if (state === 'sensitive-work') {
        await page.getByRole('button', { name: 'Show your work' }).click()
      }
      break
    }
  }
}

/** The question each scripted state asks, and what the capture does after the answer. */
async function reachConversation(page: Page, scenario: NonNullable<ScreenRow['scenario']>) {
  const feedbackNo = () => page.getByRole('button', { name: 'No' })
  switch (scenario) {
    case 'cited-answer':
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      break
    case 'source-panel':
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      await page.locator('[data-slot="citation-marker"]').first().click()
      await expect(page.getByRole('complementary', { name: 'Handbook passage' })).toBeVisible()
      await expect(page.getByRole('heading', { level: 2, name: 'Sick leave' })).toBeFocused()
      break
    case 'streaming-searching': {
      const stream = await holdNextTurnStream(page)
      await ask(page, QUESTIONS.cited)
      await stream.push('turn.started', { turnId: '00000000-0000-4000-8000-000000000001' })
      await stream.push('status', { text: 'Searching the handbook…' })
      await expect(stopButton(page)).toBeVisible()
      await expect(page.getByText('Searching the handbook…')).toBeVisible()
      break
    }
    case 'streaming-text': {
      const stream = await holdNextTurnStream(page)
      await ask(page, QUESTIONS.cited)
      await stream.push('turn.started', { turnId: '00000000-0000-4000-8000-000000000001' })
      await stream.push('status', { text: 'Searching the handbook…' })
      await stream.push('tool.started', { id: 't1', name: 'search_handbook', summary: "query='sick leave'" })
      await stream.push('tool.finished', { id: 't1', ok: true, summary: 'done', durationMs: 12 })
      await stream.push('text.delta', { text: SICK_LEAVE_SENTENCE })
      await stream.push('citation', { ...SICK_LEAVE_CITATION, offsetUtf16: SICK_LEAVE_SENTENCE.length })
      await stream.push('text.delta', { text: ' This is the company rule for any state that has no sick' })
      await expect(page.getByText('This is the company rule')).toBeVisible()
      break
    }
    case 'streaming-progress-note': {
      const stream = await holdNextTurnStream(page)
      await ask(page, QUESTIONS.cited)
      await stream.push('turn.started', { turnId: '00000000-0000-4000-8000-000000000001' })
      await stream.push('status', { text: 'Searching the handbook…' })
      await stream.push('tool.started', { id: 't1', name: 'search_handbook', summary: "query='sick leave'" })
      await stream.push('tool.finished', { id: 't1', ok: true, summary: 'done', durationMs: 12 })
      await stream.push('text.delta', { text: 'Let me check one more thing in the handbook first.' })
      await stream.push('text.retracted', {})
      await stream.push('status', { text: 'Searching the handbook again…' })
      await expect(page.getByText('Searching the handbook again…')).toBeVisible()
      break
    }
    case 'stopped':
    case 'send-error': {
      const stream = await holdNextTurnStream(page)
      await ask(page, QUESTIONS.cited)
      await stream.push('turn.started', { turnId: '00000000-0000-4000-8000-000000000001' })
      await stream.push('status', { text: 'Searching the handbook…' })
      await stream.push('tool.started', { id: 't1', name: 'search_handbook', summary: "query='sick leave'" })
      await stream.push('tool.finished', { id: 't1', ok: true, summary: 'done', durationMs: 12 })
      await stream.push('text.delta', { text: SICK_LEAVE_SENTENCE })
      await stream.push('citation', { ...SICK_LEAVE_CITATION, offsetUtf16: SICK_LEAVE_SENTENCE.length })
      await stream.push('text.delta', { text: ' This is the company rule for any state that has no' })
      await expect(stopButton(page)).toBeVisible()
      if (scenario === 'stopped') {
        await stopButton(page).click()
        await expect(page.getByText('Stopped', { exact: true })).toBeVisible()
      } else {
        await composerBox(page).fill('What about carrying unused sick days over?')
        await composerBox(page).press('Enter')
        await expect(page.getByRole('alert')).toBeVisible()
      }
      break
    }
    case 'show-your-work':
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      await page.getByRole('button', { name: 'Show your work' }).click()
      break
    case 'show-your-work-routed':
      await askAndWaitForAnswer(page, QUESTIONS.sensitive)
      await page.getByRole('button', { name: 'Show your work' }).click()
      break
    case 'feedback-yes':
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      await page.getByRole('button', { name: 'Yes' }).click()
      await expect(page.getByText('Thanks for the feedback.')).toBeVisible()
      break
    case 'feedback-no':
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      await feedbackNo().click()
      await expect(page.getByRole('textbox', { name: /What was wrong/ })).toBeFocused()
      await page.getByRole('textbox', { name: /What was wrong/ }).fill('It cited the wrong state')
      break
    case 'feedback-thanks':
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      await feedbackNo().click()
      await page.getByRole('textbox', { name: /What was wrong/ }).fill('It cited the wrong state')
      await page.getByRole('button', { name: 'Send feedback' }).click()
      await expect(page.getByText('Thanks for the feedback.')).toBeVisible()
      break
    case 'other-state':
      // As in conversation.spec.ts: this question keeps CA-4.3 in the full-text results.
      await askAndWaitForAnswer(page, 'how much sick leave do I get')
      await page.getByRole('button', { name: 'Show your work' }).click()
      break
    case 'not-found':
      await askAndWaitForAnswer(page, QUESTIONS.notFound)
      break
    case 'refusal':
      await askAndWaitForAnswer(page, QUESTIONS.decline)
      break
    case 'sensitive':
      await askAndWaitForAnswer(page, QUESTIONS.sensitive)
      break
    case 'crisis':
      await ask(page, QUESTIONS.crisis)
      await expect(page.getByRole('region', { name: 'Reach a person right now' })).toBeVisible()
      break
    case 'error-midstream':
      await ask(page, QUESTIONS.midStreamError)
      await expect(page.getByRole('alert')).toBeVisible()
      break
    case 'cant-answer':
      await ask(page, QUESTIONS.guardFailure)
      await expect(page.getByRole('region', { name: "Can't answer right now" })).toBeVisible()
      break
    case 'budget-sandbox':
    case 'budget-daily': {
      const kind = scenario === 'budget-sandbox' ? 'sandbox' : 'daily'
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      await stubConversation(page, (body) => {
        const message = kind === 'sandbox' ? BUDGET_SANDBOX_TEXT : BUDGET_DAILY_TEXT
        body.budget = { ...body.budget, banner: { kind, message } }
      })
      await page.reload()
      await expect(page.locator('[data-slot="banner"]').filter({ hasText: 'Lifeline' })).toBeVisible()
      await expect(composerBox(page)).toBeDisabled()
      break
    }
    case 'length-hint':
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      await composerBox(page).fill('a'.repeat(1962))
      await expect(page.locator('[data-slot="composer-line"]')).toHaveText('1,962 of 2,000 characters')
      break
    case 'personal-data':
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      await composerBox(page).fill('My number is 123-45-6789')
      await composerBox(page).press('Enter')
      await expect(page.locator('[data-slot="composer-line"]')).toContainText('Social Security')
      break
    case 'long-conversation':
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      await stubConversation(page, (body) => {
        body.longHistory = true
      })
      await page.reload()
      await expect(page.locator('[data-slot="composer-notice"]')).toBeVisible()
      break
  }
  // The pointer is away from everything, and the page has stopped moving.
  await page.mouse.move(1000, 600)
}

// ---------------------------------------------------------------------------------------------
// Screens 11 and 12: the case form in the conversation, My cases, and HR's queue and detail. The
// cases are real (sent through the form or the API), screened and summarized by the scripted
// model. A frame for HR that shows Priya's case starts as Priya, who sends it, and the steps switch
// to Dana. The sample people and dates in the frames (Megan, "Tuesday, October 27") can't be had in
// the real app, so those rows photograph the nearest real state and say so in the manifest.

/** As Dana, reads a case's words and moves its status: the read is what unlocks the change. */
async function danaMoves(page: Page, caseId: string, to: 'in_review' | 'closed') {
  await page.evaluate(
    async ({ id, status }) => {
      const token = document.cookie
        .split('; ')
        .find((part) => part.startsWith('__Host-od_csrf='))
        ?.slice('__Host-od_csrf='.length)
      const headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': token ?? '' }
      await fetch(`/api/v1/cases/${id}/text`, { headers })
      const response = await fetch(`/api/v1/cases/${id}/status`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ to: status }),
      })
      if (!response.ok) throw new Error(`the status change was refused: ${response.status}`)
    },
    { id: caseId, status: to },
  )
}

/** The open cases a filter lists, as Dana's queue reports them. */
function caseIdsIn(page: Page, status: string): Promise<string[]> {
  return page.evaluate(async (filter) => {
    const response = await fetch(`/api/v1/cases?status=${filter}`)
    return ((await response.json()) as { items: { id: string }[] }).items.map((item) => item.id)
  }, status)
}

/** Priya's chat after the sensitive message: the saved turn with the case offered. */
async function askSensitive(page: Page, question = SENSITIVE_QUESTION) {
  await askAndWaitForAnswer(page, question)
  await expect(casePanels(page).last()).toBeVisible()
}

/** The form's heading at the top of the window, so the photograph shows the form, not the answer. */
const formToTop = (page: Page) => formHeading(page).evaluate((el) => el.scrollIntoView({ block: 'start' }))

async function reachCases(page: Page, state: CasesState) {
  const jsonProblem = (status: number, title: string) =>
    ({ status, contentType: 'application/problem+json', body: problem(status, title) }) as const
  switch (state) {
    case 'sensitive-offer':
      await askSensitive(page)
      await expect(openCaseButton(page)).toBeVisible()
      break
    case 'form':
      await askSensitive(page)
      await openCaseButton(page).click()
      await expect(formHeading(page)).toBeFocused()
      await formToTop(page)
      break
    case 'form-ready':
      await askSensitive(page)
      await openCaseButton(page).click()
      await fillForm(page, HARASSMENT, null)
      await sendButton(page).focus()
      break
    case 'form-short':
      await askSensitive(page)
      await askSensitive(page, 'yes, I was harassed')
      await openCaseButton(page).last().click()
      await expect(page.getByText('19 of 4,000 characters')).toBeVisible()
      await formToTop(page)
      break
    case 'form-errors':
      await askSensitive(page)
      await openCaseButton(page).click()
      await wordsBox(page).fill(`${SENSITIVE_QUESTION} My employee number is 123-45-6789.`)
      await sendButton(page).click()
      await expect(page.getByRole('alert').first()).toBeVisible()
      await formToTop(page)
      break
    case 'form-limit':
      await askSensitive(page)
      await openCaseButton(page).click()
      await wordsBox(page).fill('My manager keeps making comments about my age. '.repeat(100).slice(0, 4000))
      await expect(page.getByText(/4,000 of 4,000 characters/).first()).toBeVisible()
      await formToTop(page)
      break
    case 'sending':
      await askSensitive(page)
      await openCaseButton(page).click()
      await fillForm(page, HARASSMENT, null)
      await holdRequests(page, '**/api/v1/cases', 'POST')
      await sendButton(page).click()
      await expect(page.getByRole('button', { name: 'Sending…' })).toBeVisible()
      // The button, not the form's heading, is what this frame shows; centered, the sticky
      // composer can't cover it.
      await page
        .getByRole('button', { name: 'Sending…' })
        .evaluate((el) => el.scrollIntoView({ block: 'center' }))
      break
    case 'sent':
      await askSensitive(page)
      await openCaseButton(page).click()
      await fillForm(page, HARASSMENT, null)
      await sendButton(page).click()
      await expect(sentLine(page)).toBeVisible()
      break
    case 'send-error':
      await askSensitive(page)
      await openCaseButton(page).click()
      await fillForm(page, HARASSMENT, null)
      await page.route('**/api/v1/cases', (route) =>
        route.request().method() === 'POST'
          ? route.fulfill(jsonProblem(500, 'Internal Server Error'))
          : route.fallback(),
      )
      await sendButton(page).click()
      await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible()
      break
    case 'waiting-limit':
      for (let i = 1; i <= 5; i += 1) await sendCaseByApi(page, `Concern number ${i}.`)
      await askSensitive(page)
      await expect(page.locator('[data-slot="case-sent"]')).toContainText('You have 5 cases')
      await page
        .locator('[data-slot="case-sent"]')
        .evaluate((el) => el.scrollIntoView({ block: 'center' }))
      break
    case 'crisis-offer':
      await ask(page, QUESTIONS.crisis)
      await expect(openCaseButton(page)).toBeVisible()
      break
    case 'cant-answer-link':
      await ask(page, QUESTIONS.guardFailure)
      await expect(page.getByRole('region', { name: "Can't answer right now" })).toBeVisible()
      await expect(page.getByRole('link', { name: 'Write to HR' })).toBeVisible()
      break
    case 'my-cases-empty':
      await expect(page.getByText('You haven’t sent HR a case.')).toBeVisible()
      break
    case 'my-cases': {
      const ids = [
        await sendCaseByApi(page, 'My last two paychecks were short.', 'pay'),
        await sendCaseByApi(page, 'The loading dock door sticks.', 'safety'),
        await sendCaseByApi(page, 'I need a different chair for my back.', 'medical_accommodation'),
      ]
      await switchPersona(page, 'Dana')
      await danaMoves(page, ids[0]!, 'closed')
      await danaMoves(page, ids[1]!, 'in_review')
      await switchPersona(page, 'Priya')
      await page.goto('/my-cases')
      await expect(page.locator('[data-slot="case-list"] > li')).toHaveCount(3)
      break
    }
    case 'my-cases-form':
      await openCaseButton(page).click()
      await expect(formHeading(page)).toBeFocused()
      break
    case 'sent-crisis':
      await openCaseButton(page).click()
      await fillForm(page, 'Something else, or not sure', CRISIS_WORDS)
      await sendButton(page).click()
      await expect(page.locator('[data-slot="case-sent"] + [data-slot="escalation-panel"]')).toBeVisible()
      break
    case 'nav':
      await expect(page.getByRole('heading', { level: 1, name: 'My cases' })).toBeVisible()
      break
  }
}

async function reachHrCases(page: Page, state: HrCasesState) {
  const showWords = page.getByRole('button', { name: /^Show .+ words$/ })
  const summaryUrl = '**/api/v1/cases/*/summary'
  // Priya sends a case, and the page switches to Dana.
  const priyaSends = async (words = SENSITIVE_QUESTION) => {
    const id = await sendCaseByApi(page, words, 'harassment_discrimination')
    await switchPersona(page, 'Dana')
    return id
  }
  const detailOf = async (id: string) => {
    await page.goto(`/cases/${id}`)
    await expect(page.getByRole('heading', { level: 1, name: HARASSMENT })).toBeVisible()
  }
  switch (state) {
    case 'queue':
      await priyaSends()
      await page.goto('/cases')
      await expect(queueRows(page)).toHaveCount(4)
      break
    case 'queue-closed':
      await page.goto('/cases?status=closed')
      await expect(queueRows(page)).toHaveCount(1)
      break
    case 'queue-empty':
      for (const id of await caseIdsIn(page, 'new')) await danaMoves(page, id, 'closed')
      await page.goto('/cases?status=new')
      await expect(page.getByText(/^No new cases\./)).toBeVisible()
      break
    case 'queue-facts':
      await priyaSends(CRISIS_WORDS)
      await page.goto('/cases')
      await expect(page.getByText('The safety check routed this message to crisis text.')).toBeVisible()
      break
    case 'detail':
      await detailOf(await priyaSends())
      await expect(page.locator('[data-slot="case-summary"]')).toContainText('The person wrote about')
      break
    case 'detail-revealed':
    case 'dialog-review':
    case 'dialog-close':
      await detailOf(await priyaSends())
      await expect(page.locator('[data-slot="case-summary"]')).toContainText('The person wrote about')
      await showWords.click()
      await expect(page.getByText(SENSITIVE_QUESTION)).toBeVisible()
      if (state === 'dialog-review') {
        await page.getByRole('button', { name: 'Start review' }).click()
        await expect(page.getByRole('alertdialog')).toBeVisible()
      } else if (state === 'dialog-close') {
        await page.getByRole('button', { name: 'Close case' }).click()
        await expect(page.getByRole('alertdialog')).toBeVisible()
      }
      break
    case 'detail-in-review':
      await page.goto('/cases')
      await queueRowOf(page, 'Aaliyah Edwards').click()
      await expect(page.getByRole('heading', { level: 1, name: 'Workplace safety' })).toBeVisible()
      await expect(page.locator('[data-slot="case-summary"]')).toBeVisible()
      break
    case 'summary-pending': {
      const id = await priyaSends()
      await holdRequests(page, summaryUrl, 'GET')
      await detailOf(id)
      await expect(page.getByText('Writing the summary…')).toBeVisible()
      break
    }
    case 'summary-failed': {
      const id = await priyaSends()
      await page.route(summaryUrl, (route) =>
        route.request().method() === 'GET'
          ? route.fulfill({
              status: 500,
              contentType: 'application/problem+json',
              body: problem(500, 'Internal Server Error'),
            })
          : route.fallback(),
      )
      await detailOf(id)
      await expect(page.getByText('No AI summary. Read the person’s words below.')).toBeVisible()
      break
    }
    case 'summary-crisis':
      await detailOf(await priyaSends(CRISIS_WORDS))
      await expect(
        page.getByText('No AI summary for this case. The safety check routed it to crisis text.'),
      ).toBeVisible()
      break
    case 'own-case': {
      await page.goto('/ask')
      const id = await sendCaseByApi(page, 'My own pay concern.', 'pay')
      await page.goto(`/cases/${id}`)
      await expect(
        page.getByText('You opened this case, so you can’t act on it or read it here.'),
      ).toBeVisible()
      break
    }
    case 'home-hr':
      await priyaSends()
      await page.goto('/ask')
      await expect(page.getByRole('link', { name: /new cases? Cases$/ })).toBeVisible()
      break
    case 'nav-hr':
      await priyaSends()
      await page.goto('/cases')
      await expect(nav(page).getByRole('link', { name: 'Cases, 3 new', exact: true })).toBeVisible()
      break
  }
}

async function photographScreen(browser: Browser, row: ScreenRow): Promise<string | null> {
  console.log(`Photographing ${row.title}`)
  const context = await browser.newContext({
    baseURL: 'http://localhost:4173',
    viewport: row.viewport ?? { width: 1440, height: 900 },
  })
  try {
    const page = await context.newPage()
    // A step that can't be done, such as a click on a state the date makes unreachable (a card for
    // "I'm sick tomorrow" on a Friday), fails the row in 30 seconds instead of hanging the run.
    page.setDefaultTimeout(30_000)
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
        build = await test.step(`state row: ${row.id}`, () => photographState(page, row))
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
      // A step per row, so a timeout of the run names the row that was stuck.
      const build = await test.step(`screen row: ${row.title}`, () => photographScreen(browser, row))
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
