import { execFile } from 'node:child_process'
import { resolve } from 'node:path'
import { promisify } from 'node:util'
import { expect, type Locator, type Page } from '@playwright/test'
import { scan, switchTo } from './helpers'

// Shared by proposals.spec.ts, time-off.spec.ts, and approvals.spec.ts: the confirm card, the
// rail and the nav as the browser sees them, and the one test-only door into the database.

const run = promisify(execFile)
const API_DIR = resolve(import.meta.dirname, '../../api')

export const toast = (page: Page) => page.locator('[data-slot="toast"]')
export const cards = (page: Page) => page.locator('[data-slot="confirm-card"]')
export const nav = (page: Page) => page.getByRole('navigation', { name: 'Main' })

/** A rail figure, such as "requests pending", by the words after its number. */
export const railLink = (page: Page, words: RegExp | string) =>
  page.locator('[data-slot="glance-list"]').getByRole('link', {
    name:
      typeof words === 'string'
        ? new RegExp(`${words}\\s?\\. Open (Time off|Cases|Approvals|Handbook)$`)
        : words,
  })

/** The id of the newest confirm card in the person's conversation, as the API reports it. */
export async function newestProposalId(page: Page): Promise<string> {
  const id = await page.evaluate(async () => {
    const response = await fetch('/api/v1/assistant/conversations/current')
    const body = (await response.json()) as { turns: { proposals: { id: string }[] }[] } | null
    return body?.turns.flatMap((turn) => turn.proposals).at(-1)?.id ?? null
  })
  expect(id, 'a confirm card exists in the conversation').not.toBeNull()
  return id!
}

/**
 * Makes a pending card 16 minutes old, through the API's test-only script (a local test database
 * only: the script refuses any other host). On CI the job's MIGRATION_DATABASE_URL reaches it, as
 * it does the ledger cleanup.
 */
export async function expireProposal(id: string) {
  // An agent shell may export ANTHROPIC_API_KEY as an empty string, which the API's settings
  // ignore, but leave it out all the same, as the API's own server command does.
  const { ANTHROPIC_API_KEY: _empty, ...env } = process.env
  const { stdout } = await run(
    'uv',
    ['run', 'python', 'scripts/expire_proposal_for_tests.py', id],
    { cwd: API_DIR, env },
  )
  expect(stdout).toContain('Expired proposal')
}

/** Counts a page's requests by the dates its rows show, such as "Friday, November 6". */
export function rowsOn(within: Page | Locator, dates: string): Locator {
  return within.locator('[data-slot="request-row"]').filter({ hasText: dates })
}

/** True when the page scrolls sideways. */
export const scrollsSideways = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)

// Days. The seed's dates move with today, so a test asks the API for today, the person's schedule,
// and the company holidays, then picks days from those. Dates are plain "YYYY-MM-DD" strings and
// the arithmetic is in UTC, as the app's own (components/timeoff/dates.ts).

const DAY_MS = 86_400_000
export const addDaysTo = (day: string, days: number) =>
  new Date(Date.parse(day) + days * DAY_MS).toISOString().slice(0, 10)
export const daysBetween = (from: string, to: string) =>
  Math.round((Date.parse(to) - Date.parse(from)) / DAY_MS)

export type Facts = { today: string; weekdays: number[]; holidays: string[] }

/** Today at the person's location, their scheduled weekdays (1 is Monday), and the holidays. */
export function factsOf(page: Page): Promise<Facts> {
  return page.evaluate(async () => {
    const get = async (url: string) => (await fetch(url)).json()
    const { today } = (await get('/api/v1/time-off/summary')) as { today: string }
    const calendar = (await get(
      `/api/v1/time-off/calendar?from=${today}&to=${Number(today.slice(0, 4)) + 1}-12-31`,
    )) as { scheduledWeekdays: number[]; holidays: { day: string }[] }
    return {
      today,
      weekdays: calendar.scheduledWeekdays,
      holidays: calendar.holidays.map((holiday) => holiday.day),
    }
  })
}

/** The days a person can take off from `fromOffset` days after today: scheduled, not a holiday. */
export function workdays(facts: Facts, fromOffset: number, count: number): string[] {
  const days: string[] = []
  for (let offset = fromOffset; days.length < count; offset += 1) {
    const day = addDaysTo(facts.today, offset)
    const weekday = new Date(Date.parse(day)).getUTCDay() || 7
    if (facts.weekdays.includes(weekday) && !facts.holidays.includes(day)) days.push(day)
  }
  return days
}

// A request spans at most this many calendar days (the API's MAX_REQUEST_DAYS).
const MAX_REQUEST_DAYS = 31

/**
 * Working days, starting 15 days out or later, that together cost more PTO than the person has
 * now. The seed's balances change with the date, so the count comes from the API: one day more
 * than the available minutes cover at the calendar's day length. The first run of days that fits
 * in one request (at most 31 calendar days, inside one year, so one year's balance pays for it)
 * is used. A fixed start broke once the balance grew and the run crossed Thanksgiving.
 */
export async function daysPastBalance(page: Page, facts: Facts): Promise<string[]> {
  const { availableMinutes, dayMinutes } = await page.evaluate(async (today) => {
    const get = async (url: string) => (await fetch(url)).json()
    const summary = (await get('/api/v1/time-off/summary')) as { ptoAvailableMinutes: number }
    const calendar = (await get(`/api/v1/time-off/calendar?to=${today}`)) as { dayMinutes: number }
    return { availableMinutes: summary.ptoAvailableMinutes, dayMinutes: calendar.dayMinutes }
  }, facts.today)
  const count = Math.floor(availableMinutes / dayMinutes) + 1
  for (let start = 15; start < 15 + 120; start += 1) {
    const days = workdays(facts, start, count)
    const first = days[0]!
    const last = days.at(-1)!
    if (
      daysBetween(first, last) + 1 <= MAX_REQUEST_DAYS &&
      first.slice(0, 4) === last.slice(0, 4)
    ) {
      return days
    }
  }
  throw new Error(`no ${count} working days fit in one request within the next 4 months`)
}

/** Opens a form's date picker and Tabs into its grid, onto today or the chosen day. */
export async function enterGrid(page: Page, form: Locator) {
  await form.getByRole('button', { name: /^Dates/ }).click()
  const next = form.getByRole('button', { name: 'Next month' })
  await next.focus()
  await page.keyboard.press('Tab')
}

/** Arrow keys from the focused day to `day`: whole weeks with Down and Up, then single days. */
export async function moveToDay(page: Page, day: string) {
  const at = () => page.evaluate(() => document.activeElement?.getAttribute('data-day') ?? '')
  const from = await at()
  expect(from, 'focus is on a day in the grid').not.toBe('')
  let gap = daysBetween(from, day)
  while (Math.abs(gap) >= 7) {
    await page.keyboard.press(gap > 0 ? 'ArrowDown' : 'ArrowUp')
    gap += gap > 0 ? -7 : 7
  }
  for (; gap !== 0; gap += gap > 0 ? -1 : 1) {
    await page.keyboard.press(gap > 0 ? 'ArrowRight' : 'ArrowLeft')
  }
  expect(await at()).toBe(day)
}

/**
 * Picks days with the keyboard alone: into the grid, arrow keys to each day, Enter to choose. One
 * day is a first Enter and then "Done"; a range is a second Enter on its last day. With
 * `close: false` the picker stays open on the last day picked.
 */
export async function pickDays(
  page: Page,
  form: Locator,
  first: string,
  last?: string,
  { close = true }: { close?: boolean } = {},
) {
  await enterGrid(page, form)
  await moveToDay(page, first)
  await page.keyboard.press('Enter')
  if (last !== undefined) {
    await moveToDay(page, last)
    await page.keyboard.press('Enter')
  }
  if (!close) return
  await form.getByRole('button', { name: 'Done' }).click()
  await expect(form.getByRole('button', { name: /^Dates/ })).toBeFocused()
}

/** Opens a page from the sidebar by its name, such as "Time off" or "Approvals, 1 waiting". */
export async function openFromNav(page: Page, name: string | RegExp, url: string) {
  await nav(page).getByRole('link', { name }).click()
  await expect(page).toHaveURL(url)
}

/**
 * As the person on the page, asks for one PTO day on /time-off, `fromOffset` days after today or
 * later (the first scheduled day that is not a holiday), and returns the day. Leaves the page on
 * /time-off with the request waiting.
 */
export async function bookOnPage(page: Page, fromOffset = 14): Promise<string> {
  await openFromNav(page, 'Time off', '/time-off')
  const [day] = workdays(await factsOf(page), fromOffset, 1) as [string]
  const open = page.getByRole('button', { name: 'Request time off' }).first()
  await expect(open).toBeVisible()
  await open.click()
  const form = page.locator('#request-form')
  await pickDays(page, form, day)
  await form.getByRole('button', { name: 'Request time off' }).click()
  await expect(toast(page)).toContainText('Requested.')
  await expect(form).toHaveCount(0)
  return day
}

/** "Friday, November 6": how the pages write a day. */
export const longDay = (day: string) =>
  new Intl.DateTimeFormat('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.parse(day)))

/** Switches persona and waits until the shell shows the new person, so the next step is theirs. */
export async function switchPersona(page: Page, firstName: string) {
  await switchTo(page, firstName)
  await expect(page.getByRole('button', { name: /Switch persona$/ })).toHaveAccessibleName(
    new RegExp(`^${firstName} .* Current persona\\. Switch persona$`),
  )
}

/**
 * An axe scan taken after the pointer has left and the colors have stopped moving. A button the
 * pointer just pressed is still easing between its hover and resting colors, and axe would read
 * the contrast halfway through.
 */
export async function settledScan(
  page: Page,
  disabledRules: string[] = [],
  include: string[] = [],
) {
  await page.mouse.move(2, 2)
  await page.waitForTimeout(400)
  return scan(page, disabledRules, include)
}

/**
 * The scripted model's two date-dependent turns work out their day from today, and a day that does
 * not count (a company holiday, or off the person's schedule) makes a refusal instead of a card.
 * "book next friday" is the Friday of the following Monday-to-Sunday week; "I'm sick tomorrow" is
 * the day after today. A test that needs a card calls this and skips, with the reason, on a date
 * when the day does not count. The model is not changed.
 */
export async function skipUnlessScriptedDayCounts(
  test: { skip: (condition: boolean, description: string) => void },
  page: Page,
  turn: 'book next friday' | "I'm sick tomorrow",
) {
  const facts = await factsOf(page)
  const weekday = new Date(Date.parse(facts.today)).getUTCDay() || 7
  const day =
    turn === 'book next friday'
      ? addDaysTo(facts.today, 8 - weekday + 4)
      : addDaysTo(facts.today, 1)
  const dayOfWeek = new Date(Date.parse(day)).getUTCDay() || 7
  const counts = facts.weekdays.includes(dayOfWeek) && !facts.holidays.includes(day)
  test.skip(
    !counts,
    `"${turn}" is ${day} today, a company holiday or a day off the schedule, so the scripted model makes no card`,
  )
}

/** The hours in a label such as "80 hours (10 days)" or "0 hours". */
export const hoursIn = (label: string) => Number(/^([\d.]+) hours?/.exec(label)![1])
