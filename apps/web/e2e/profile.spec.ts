import { expect, test, type Locator, type Page } from '@playwright/test'
import {
  auditEventsBy,
  hasVisibleFocus,
  leosPrivateValues,
  myId,
  openDirectory,
  openProfileBySearch,
  type LeoPrivate,
} from './directory-helpers'
import { scan, startAs } from './helpers'

// One test per acceptance criterion in docs/design/screens/04-directory/notes.md, for the profile.
// The list's are in directory.spec.ts. Layout at 1440 px is in directory-layout.spec.ts, and Back
// restoring the scroll position in directory-scroll.spec.ts.

const PRIVATE_LABELS = ['Personal email', 'Phone', 'Home address', 'Date of birth']
const FIELD_NAMES = ['dateOfBirth', 'homeAddress', 'personalEmail', 'phone']

const heading = (page: Page, name: string) => page.getByRole('heading', { level: 1, name })
const privateSection = (page: Page) => page.getByRole('region', { name: 'Private details' })

/** "2000-06-24" as the page writes it, "June 24, 2000". */
const longDate = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', { dateStyle: 'long', timeZone: 'UTC' })

/** The date written the other ways a page might: "24 June 2000", "June 24, 2000", and so on. */
const dateWords = (iso: string) => {
  const date = new Date(`${iso}T00:00:00Z`)
  const part = (options: Intl.DateTimeFormatOptions) =>
    date.toLocaleDateString('en-US', { ...options, timeZone: 'UTC' })
  const [month, day, year] = [
    part({ month: 'long' }),
    part({ day: 'numeric' }),
    part({ year: 'numeric' }),
  ]
  return [`${month} ${day}, ${year}`, `${day} ${month} ${year}`, `${month} ${day} ${year}`]
}

/**
 * What a private value looks like when a page holds it, however it is written. Text is compared
 * in lowercase. The digits-only probes are compared against the text with everything but digits
 * removed, so "(510) 555-0175", "+1 510 555 0175", and "5105550175" all match the phone, and
 * "06/24/2000" matches the date of birth in year-month-day, month-day-year, or day-month-year
 * order. The phone's last seven digits catch a number written without its area code.
 */
const textProbes = (leo: LeoPrivate) =>
  [
    leo.personalEmail,
    leo.personalEmail.split('@')[0]!,
    leo.homeAddress,
    leo.homeAddress.split(',')[0]!,
    leo.dateOfBirth,
    ...dateWords(leo.dateOfBirth),
  ].map((probe) => probe.toLowerCase())

const digitProbes = (leo: LeoPrivate) => {
  const phone = leo.phone.replace(/\D/g, '')
  const [year, month, day] = leo.dateOfBirth.split('-')
  return [
    phone,
    phone.slice(-7),
    `${year}${month}${day}`,
    `${month}${day}${year}`,
    `${day}${month}${year}`,
  ]
}

/** The private values `haystack` holds, in any of the spellings above. Empty is clean. */
function leaks(haystack: string, leo: LeoPrivate): string[] {
  const lower = haystack.toLowerCase()
  const digits = haystack.replace(/\D/g, '')
  return [
    ...textProbes(leo).filter((probe) => lower.includes(probe)),
    ...digitProbes(leo).filter((probe) => digits.includes(probe)),
  ]
}

async function openLeo(page: Page, as: 'Priya' | 'Dana') {
  await openDirectory(page, as)
  await openProfileBySearch(page, 'Nakamura', /^Leo Nakamura/)
  await expect(heading(page, 'Leo Nakamura')).toBeVisible()
}

test('as Priya on Leo’s profile, the page holds no private value, and none was requested', async ({
  page,
  browser,
  baseURL,
}) => {
  const leo = await leosPrivateValues(browser, baseURL!)

  // The network log, from before the first request: every API request, and every API body.
  const requested: string[] = []
  const bodies: Promise<string>[] = []
  const unreadable: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/')) requested.push(request.url())
  })
  page.on('response', (response) => {
    if (!response.url().includes('/api/')) return
    bodies.push(
      response.text().then(
        (text) => text,
        () => {
          // A body that can't be read can't be checked, so it fails the test below.
          unreadable.push(`${response.status()} ${response.url()}`)
          return ''
        },
      ),
    )
  })

  await openLeo(page, 'Priya')

  // Four locked rows, each named by its field and "Visible to Leo and HR", with no value.
  const section = privateSection(page)
  await expect(section).toBeVisible()
  for (const label of PRIVATE_LABELS)
    await expect(section.getByText(label, { exact: true })).toBeVisible()
  await expect(section.getByText('Visible to Leo and HR')).toHaveCount(4)
  await expect(page.getByText('Viewing private details is recorded in the audit log.')).toHaveCount(
    0,
  )
  await expect(page.getByText(/Only (you|Leo) and HR can see these/)).toHaveCount(0)

  // The DOM: text, markup, and attributes hold none of Leo's values, however they are written.
  const dom = await page.evaluate(() => document.documentElement.outerHTML)
  const text = await page.evaluate(() => document.body.innerText)
  expect(leaks(dom, leo), 'the markup holds a private value').toEqual([])
  expect(leaks(text, leo), 'the text holds a private value').toEqual([])

  // The network log: no request to /private, and no response that carries a value. Priya reached
  // the profile through the real list and a real profile request, so there is something to check.
  expect(requested.some((url) => /\/api\/v1\/people\/[^/]+$/.test(url.split('?')[0]!))).toBe(true)
  expect(requested.filter((url) => url.includes('/private'))).toEqual([])
  const logged = await Promise.all(bodies)
  expect(unreadable, 'responses whose body could not be read').toEqual([])
  // The log really holds Leo's card, so a clean result is not an empty one.
  expect(logged.some((body) => body.includes('leo.nakamura@juniperrow.example'))).toBe(true)
  for (const body of logged)
    expect(leaks(body, leo), 'a response holds a private value').toEqual([])

  // No read, so no audit event.
  expect(auditEventsBy(await myId(page)).filter((e) => e.action === 'person_private.read')).toEqual(
    [],
  )
  expect((await scan(page)).violations).toEqual([])
})

test('as Dana on Leo’s profile, the values show, and one audit event names the fields only', async ({
  page,
  browser,
  baseURL,
}) => {
  const leo = await leosPrivateValues(browser, baseURL!)
  await openLeo(page, 'Dana')

  const section = privateSection(page)
  await expect(section.getByText('Only Leo and HR can see these.')).toBeVisible()
  await expect(
    section.getByText('Viewing private details is recorded in the audit log.'),
  ).toBeVisible()
  await expect(section.getByText(leo.personalEmail, { exact: true })).toBeVisible()
  await expect(section.getByText(leo.phone, { exact: true })).toBeVisible()
  await expect(section.getByText(leo.homeAddress, { exact: true })).toBeVisible()
  await expect(section.getByText(longDate(leo.dateOfBirth), { exact: true })).toBeVisible()
  await expect(section.getByText('Visible to Leo and HR')).toHaveCount(0)
  expect((await scan(page)).violations).toEqual([])

  // The audit event, read from the database. One visit, one event: Dana, about Leo, field names.
  const leoId = page.url().split('/').at(-1)!
  const events = auditEventsBy(await myId(page))
  const reads = events.filter((e) => e.action === 'person_private.read')
  expect(reads).toHaveLength(1)
  expect(reads[0]).toMatchObject({
    action: 'person_private.read',
    via: 'ui',
    target_type: 'person',
    target_id: leoId,
    actor: await myId(page),
    after: { fields: FIELD_NAMES },
  })
  // Never a value, in any spelling, anywhere in the stored event.
  const stored = JSON.stringify(reads[0])
  expect(leaks(stored, leo)).toEqual([])
})

test('on her own profile, Priya sees the "You" tag and her values, and her own read is audited', async ({
  page,
}) => {
  await openDirectory(page, 'Priya')
  await openProfileBySearch(page, 'Raman', /^Priya Raman/)
  await expect(heading(page, 'Priya Raman')).toBeVisible()
  await expect(page.getByRole('main').getByText('You', { exact: true })).toBeVisible()
  const section = privateSection(page)
  await expect(section.getByText('Only you and HR can see these.')).toBeVisible()
  await expect(
    section.getByText('Viewing private details is recorded in the audit log.'),
  ).toBeVisible()
  await expect(section.getByText(/@example\.com$/)).toBeVisible()
  await expect(section.getByText('Visible to Priya and HR')).toHaveCount(0)
  expect((await scan(page)).violations).toEqual([])

  const me = await myId(page)
  const reads = auditEventsBy(me).filter((e) => e.action === 'person_private.read')
  expect(reads).toHaveLength(1)
  expect(reads[0]).toMatchObject({ actor: me, target_id: me, after: { fields: FIELD_NAMES } })
})

test('the work details show the manager as a link and the work email as a mail link', async ({
  page,
}) => {
  await openDirectory(page, 'Priya')
  await openProfileBySearch(page, 'Nakamura', /^Leo Nakamura/)
  const work = page.getByRole('region', { name: 'Work details' })
  await expect(work.getByText('Sales Associate', { exact: true })).toBeVisible()
  await expect(work.getByRole('link', { name: 'leo.nakamura@juniperrow.example' })).toHaveAttribute(
    'href',
    'mailto:leo.nakamura@juniperrow.example',
  )
  await work.getByRole('link', { name: 'Marcus Bell' }).click()
  await expect(heading(page, 'Marcus Bell')).toBeVisible()
  await expect(page).toHaveURL(/\/directory\/[0-9a-f-]{36}$/)
})

test('"← Directory" returns to the list with its search kept', async ({ page }) => {
  await openDirectory(page, 'Priya')
  await openProfileBySearch(page, 'Nakamura', /^Leo Nakamura/)
  await page.getByRole('link', { name: 'Back to Directory' }).click()
  await expect(page).toHaveURL(/\/directory\?q=Nakamura$/)
  await expect(page.getByRole('searchbox')).toHaveValue('Nakamura')
  await expect(page.getByRole('list', { name: 'People' }).getByRole('listitem')).toHaveCount(1)
})

test.describe('every link on a profile is reachable by keyboard, with a visible focus ring', () => {
  test('the back link, the manager link, and the mail link', async ({ page }) => {
    await openDirectory(page, 'Priya')
    await openProfileBySearch(page, 'Nakamura', /^Leo Nakamura/)
    await expect(heading(page, 'Leo Nakamura')).toBeVisible()
    const ordered: [Locator, string][] = [
      [page.getByRole('link', { name: 'Back to Directory' }), 'back'],
      [page.getByRole('link', { name: 'Marcus Bell' }), 'manager'],
      [page.getByRole('link', { name: 'leo.nakamura@juniperrow.example' }), 'mail'],
    ]
    // From the persona switcher, the last control before the page, walk forward in order.
    await page.getByRole('button', { name: /^Switch persona/ }).focus()
    await page.keyboard.press('Tab')
    for (const [link, name] of ordered) {
      await expect(link, `${name} link`).toBeFocused()
      expect(await hasVisibleFocus(page), `${name} link ring`).toBe(true)
      await page.keyboard.press('Tab')
    }
  })
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the profile stacks its panels and rows, with nothing to scroll sideways', async ({
    page,
  }) => {
    await startAs(page, 'Dana')
    await page.goto('/directory')
    await openProfileBySearch(page, 'Nakamura', /^Leo Nakamura/)
    const work = page.getByRole('region', { name: 'Work details' })
    const priv = privateSection(page)
    await expect(priv.getByText('Only Leo and HR can see these.')).toBeVisible()
    const [w, p] = [(await work.boundingBox())!, (await priv.boundingBox())!]
    expect(p.y).toBeGreaterThanOrEqual(w.y + w.height - 1)
    expect(Math.abs(p.x - w.x)).toBeLessThan(4)
    const row = work.locator('[data-slot="detail-row"]').first()
    const [label, value] = await Promise.all([
      row.locator('dt').boundingBox(),
      row.locator('dd').boundingBox(),
    ])
    expect(value!.y).toBeGreaterThanOrEqual(label!.y + label!.height)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    for (const b of [w, p]) expect(b.x + b.width).toBeLessThanOrEqual(390)
  })
})

// Axe on the profile's states runs inside the test that shows each one: locked (Priya on Leo), HR
// (Dana on Leo), and self (Priya on herself), each with every rule on. The last is a person who
// doesn't exist.
test('a profile that does not exist shows not found inside the shell, with no axe violations', async ({
  page,
}) => {
  await startAs(page, 'Priya')
  await page.goto('/directory/00000000-0000-4000-8000-000000000000')
  await expect(
    page.getByRole('heading', { level: 1, name: "We couldn't find that page." }),
  ).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
  expect((await scan(page)).violations).toEqual([])
})
