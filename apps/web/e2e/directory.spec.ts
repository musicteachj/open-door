import { expect, test, type Locator, type Page } from '@playwright/test'
import {
  hasVisibleFocus,
  holdList,
  isListRequest,
  openDirectory,
  openProfileBySearch,
} from './directory-helpers'
import { MODAL_OVERLAY_RULES, problem, scan, startAs } from './helpers'

// One test per acceptance criterion in docs/design/screens/04-directory/notes.md, for the list.
// The profile's are in profile.spec.ts.
//
// Mapped elsewhere:
//  - "Matches the screenshots at 1440 px" is the capture report's job (make captures).
//  - The toolbar fitting one row at 1440 px is in directory-layout.spec.ts.
//  - Back restoring the scroll position is in directory-scroll.spec.ts.
//  - "The 390 px nav fade" needs more than Phase 2's two nav items; home.spec.ts proves it at
//    150 px until then. Recheck it at 390 px when the nav has more items.

const people = (page: Page) => page.getByRole('list', { name: 'People' })
const rows = (page: Page) => people(page).getByRole('listitem')
const count = (page: Page, text: string) => page.getByText(text, { exact: true })

/** The family names of the rows on screen, in order. A name is "Given Family". */
const familyNames = async (page: Page) =>
  await rows(page)
    .getByRole('link')
    .evaluateAll((links) =>
      links.map((link) => link.querySelector('span')!.textContent!.trim().split(' ').at(-1)!),
    )

/** An option's size, from its accessible name "Oakland store, 40". */
async function optionCount(page: Page, filter: 'Location' | 'Department', name: string) {
  await page.getByRole('combobox', { name: filter }).click()
  const option = page.getByRole('option', { name: new RegExp(`^${name}, \\d+$`) })
  const total = Number((await option.innerText()).match(/(\d+)\s*$/)![1])
  return { option, total }
}

async function choose(page: Page, filter: 'Location' | 'Department', name: string) {
  const { option, total } = await optionCount(page, filter, name)
  await option.click()
  return total
}

test.describe('as Marcus, a manager', () => {
  test('"My team" shows 44, and means everyone under him, directly or through a lead', async ({
    page,
  }) => {
    await openDirectory(page, 'Marcus')
    const myTeam = page.getByRole('button', { name: /^My team/ })
    await expect(myTeam).toHaveAccessibleName(/44/)
    await expect(myTeam).toHaveAttribute('aria-pressed', 'false')
    await myTeam.click()
    await expect(myTeam).toHaveAttribute('aria-pressed', 'true')
    await expect(count(page, '44 of 145 people')).toBeVisible()
    await expect(rows(page)).toHaveCount(44)
    // Marcus has seven direct reports (Priya and Leo among them); the rest report through a lead.
    await expect(people(page).getByRole('link', { name: /^Priya Raman/ })).toBeVisible()
    await expect(people(page).getByRole('link', { name: /^Marcus Bell/ })).toHaveCount(0)
    await expect(page).toHaveURL(/\?team=/)
  })
})

test('as Priya, there is no "My team" toggle, and no disabled one', async ({ page }) => {
  await openDirectory(page, 'Priya')
  await expect(page.getByRole('searchbox')).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Department' })).toBeVisible()
  await expect(page.getByRole('button', { name: /My team/ })).toHaveCount(0)
  await expect(page.locator('[data-slot="filter-toggle"]')).toHaveCount(0)
})

test('the list is sorted by last name, 50 at a time, and Show more appends the next page', async ({
  page,
}) => {
  await openDirectory(page, 'Priya')
  await expect(rows(page)).toHaveCount(50)
  await expect(count(page, 'Showing 50 of 145')).toBeVisible()
  const first = await familyNames(page)
  const sorted = [...first].sort(new Intl.Collator('en').compare)
  expect(first).toEqual(sorted)

  await page.getByRole('button', { name: 'Show more' }).click()
  await expect(rows(page)).toHaveCount(100)
  await expect(count(page, 'Showing 100 of 145')).toBeVisible()
  const second = await familyNames(page)
  expect(second.slice(0, 50)).toEqual(first)
  expect(second).toEqual([...second].sort(new Intl.Collator('en').compare))

  await page.getByRole('button', { name: 'Show more' }).click()
  await expect(rows(page)).toHaveCount(145)
  await expect(page.getByRole('button', { name: 'Show more' })).toHaveCount(0)
  await expect(count(page, 'Showing all 145')).toBeVisible()
  // No page numbers.
  await expect(page.getByRole('navigation', { name: /pag/i })).toHaveCount(0)
})

test('each row is one link named for the person, with "(you)" on your own', async ({ page }) => {
  await openDirectory(page, 'Priya')
  await expect(rows(page).first().getByRole('link')).toHaveCount(1)
  await page.getByRole('searchbox').fill('Raman')
  await expect(rows(page)).toHaveCount(1)
  await expect(rows(page).getByRole('link')).toHaveAccessibleName(
    'Priya Raman, Visual Merchandiser, Store Operations, Oakland store (you)',
  )
})

test('search and both filters narrow the list and the count, and "Clear filters" resets them', async ({
  page,
}) => {
  await openDirectory(page, 'Priya')

  // Search takes name, title, or email, as you type, with no search button.
  await page.getByRole('searchbox').fill('nakamura')
  await expect(count(page, '1 of 145 people')).toBeVisible()
  await expect(rows(page)).toHaveCount(1)
  await page.getByRole('searchbox').fill('Visual Merchandiser')
  await expect(rows(page).first()).toBeVisible()
  await page.getByRole('searchbox').fill('priya.raman@juniperrow')
  await expect(count(page, '1 of 145 people')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Clear search' })).toBeVisible()
  await page.getByRole('searchbox').fill('')
  await expect(count(page, '145 people')).toBeVisible()

  const oakland = await choose(page, 'Location', 'Oakland store')
  await expect(count(page, `${oakland} of 145 people`)).toBeVisible()
  await expect(rows(page)).toHaveCount(Math.min(oakland, 50))
  await expect(page).toHaveURL(/location=/)

  const stores = await choose(page, 'Department', 'Store Operations')
  await expect(count(page, `${stores} of 145 people`)).toBeVisible()
  expect(stores).toBeLessThanOrEqual(oakland)
  await expect(page).toHaveURL(/department=/)

  await page.getByRole('button', { name: 'Clear filters' }).click()
  await expect(count(page, '145 people')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Clear filters' })).toHaveCount(0)
  await expect(page).toHaveURL(/\/directory$/)
  await expect(page.getByRole('combobox', { name: 'Location' })).toContainText('All')
  await expect(page.getByRole('combobox', { name: 'Department' })).toContainText('All')
})

test.describe('every control and row is reachable by keyboard, with a visible focus ring', () => {
  /** Presses Tab until `target` has focus, so the test also proves nothing else traps focus. */
  async function tabTo(page: Page, target: Locator, within = 12) {
    for (let i = 0; i < within; i += 1) {
      await page.keyboard.press('Tab')
      if (await target.evaluate((el) => el === document.activeElement)) break
    }
    await expect(target).toBeFocused()
    expect(await hasVisibleFocus(page)).toBe(true)
  }

  test('search, filters, My team, Clear filters, a row link, and Show more', async ({ page }) => {
    await openDirectory(page, 'Marcus')
    // Start from the page heading, so Tab goes to the first control after it.
    await page.getByRole('heading', { level: 1, name: 'Directory' }).click()
    await tabTo(page, page.getByRole('searchbox'))
    await tabTo(page, page.getByRole('combobox', { name: 'Location' }), 1)
    await tabTo(page, page.getByRole('combobox', { name: 'Department' }), 1)
    const myTeam = page.getByRole('button', { name: /^My team/ })
    await tabTo(page, myTeam, 1)
    await page.keyboard.press('Space')
    await expect(myTeam).toHaveAttribute('aria-pressed', 'true')
    await tabTo(page, page.getByRole('button', { name: 'Clear filters' }), 1)
    await tabTo(page, rows(page).first().getByRole('link'), 1)
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/\/directory\/[0-9a-f-]{36}$/)
  })

  test('a filter opens, chooses, and closes from the keyboard', async ({ page }) => {
    await openDirectory(page, 'Priya')
    const location = page.getByRole('combobox', { name: 'Location' })
    await location.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('option', { selected: true })).toBeFocused()
    // The menu takes its first arrow key a moment after it opens, so press until focus moves.
    await expect(async () => {
      await page.keyboard.press('ArrowDown')
      // Radix marks only the focused option, if it is the chosen one, as selected.
      await expect(page.getByRole('option', { selected: true })).toHaveCount(0, { timeout: 300 })
    }).toPass()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('listbox')).toHaveCount(0)
    await expect(page).toHaveURL(/location=/)
    await expect(location).toBeFocused()
  })

  test('Show more follows the last row, and the new rows are in the Tab order', async ({
    page,
  }) => {
    await openDirectory(page, 'Priya')
    await rows(page).nth(49).getByRole('link').focus()
    await tabTo(page, page.getByRole('button', { name: 'Show more' }), 1)
    // Hold the next page, so the button is in its loading state for as long as the test looks.
    let release!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    await page.route(
      (url) => isListRequest(url) && url.searchParams.has('cursor'),
      async (route) => {
        await gate
        return route.continue()
      },
    )
    await page.keyboard.press('Enter')
    // Loading must not disable the button, which would drop the keyboard user's focus.
    const showMore = page.getByRole('button', { name: 'Show more' })
    await expect(showMore).toHaveAttribute('aria-busy', 'true')
    await expect(showMore).toBeFocused()
    release()
    await expect(rows(page)).toHaveCount(100)
    await expect(showMore).toBeFocused()
    await page.keyboard.press('Shift+Tab')
    await expect(rows(page).nth(99).getByRole('link')).toBeFocused()
  })
})

test.describe('at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('rows stack and the toolbar wraps, with nothing to scroll sideways', async ({ page }) => {
    await startAs(page, 'Marcus')
    await page.goto('/directory')
    await expect(rows(page).first()).toBeVisible()
    await expect(count(page, '145 people')).toBeVisible()
    await page.getByRole('button', { name: /^My team/ }).click()
    await expect(page.getByRole('button', { name: 'Clear filters' })).toBeVisible()

    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)

    // The toolbar wraps onto more than one line, and every control stays on screen.
    const controls = [
      page.getByRole('searchbox'),
      page.getByRole('combobox', { name: 'Location' }),
      page.getByRole('combobox', { name: 'Department' }),
      page.getByRole('button', { name: /^My team/ }),
      page.getByRole('button', { name: 'Clear filters' }),
    ]
    const boxes = await Promise.all(controls.map(async (control) => (await control.boundingBox())!))
    expect(new Set(boxes.map((box) => Math.round(box.y))).size).toBeGreaterThan(1)
    for (const box of boxes) {
      expect(box.x).toBeGreaterThanOrEqual(0)
      expect(box.x + box.width).toBeLessThanOrEqual(390)
    }

    // A row's cells stack, and the column labels are gone.
    await expect(
      page.locator('[data-slot="directory-table"] [aria-hidden="true"]').getByText('Department'),
    ).toBeHidden()
    const cells = rows(page).first().getByRole('link').locator(':scope > span')
    const cellBoxes = await Promise.all([0, 1, 2, 3].map((i) => cells.nth(i).boundingBox()))
    for (let i = 1; i < 4; i += 1) {
      expect(cellBoxes[i]!.y).toBeGreaterThan(cellBoxes[i - 1]!.y)
      expect(cellBoxes[i]!.x).toBeLessThanOrEqual(cellBoxes[0]!.x + cellBoxes[0]!.width)
    }
    expect((await rows(page).first().boundingBox())!.height).toBeGreaterThan(60)
  })
})

test.describe('axe reports no violations in every state of the list', () => {
  test('the list, as Priya', async ({ page }) => {
    await openDirectory(page, 'Priya')
    expect((await scan(page)).violations).toEqual([])
  })

  test('the list with "My team" on, as Marcus', async ({ page }) => {
    await openDirectory(page, 'Marcus')
    await page.getByRole('button', { name: /^My team/ }).click()
    await expect(count(page, '44 of 145 people')).toBeVisible()
    expect((await scan(page)).violations).toEqual([])
  })

  test('loading, with the list request held', async ({ page }) => {
    await startAs(page, 'Priya')
    const release = await holdList(page)
    await page.getByRole('link', { name: 'Directory' }).click()
    await expect(page.getByText('Loading the directory')).toBeAttached()
    await expect(page.locator('[aria-busy="true"]')).toBeVisible()
    await expect(rows(page)).toHaveCount(0)
    // The toolbar and the column labels are kept while the rows load.
    await expect(page.getByRole('searchbox')).toBeVisible()
    await expect(page.getByText('Name', { exact: true })).toBeVisible()
    expect((await scan(page)).violations).toEqual([])
    release()
    await expect(rows(page)).toHaveCount(50)
  })

  test('a filter open, with focus held inside it by Tab', async ({ page }) => {
    await openDirectory(page, 'Priya')
    await page.getByRole('combobox', { name: 'Location' }).click()
    const listbox = page.getByRole('listbox')
    await expect(listbox).toBeVisible()
    // Radix hides the page behind a menu, though its controls stay in the tab order, so axe's
    // aria-hidden-focus is a false alarm here. The Tab presses prove the trap instead.
    expect((await scan(page, MODAL_OVERLAY_RULES)).violations).toEqual([])
    for (const key of ['Tab', 'Tab', 'Shift+Tab']) {
      await page.keyboard.press(key)
      expect(
        await page.evaluate(() => document.activeElement?.closest('[role="listbox"]') !== null),
      ).toBe(true)
    }
    await page.keyboard.press('Escape')
    await expect(listbox).toHaveCount(0)
    await expect(page.getByRole('combobox', { name: 'Location' })).toBeFocused()
  })

  test('no results for a search', async ({ page }) => {
    await openDirectory(page, 'Priya')
    await page.getByRole('searchbox').fill('Jordn')
    await expect(page.getByText('No one matches “Jordn”.')).toBeVisible()
    await expect(count(page, '0 of 145 people')).toBeVisible()
    expect((await scan(page)).violations).toEqual([])
    await page.getByRole('button', { name: 'Clear search' }).last().click()
    await expect(rows(page)).toHaveCount(50)
  })

  test('no results for the filters', async ({ page }) => {
    await openDirectory(page, 'Priya')
    // No one in Distribution works at Denver HQ.
    await choose(page, 'Location', 'Denver HQ')
    await choose(page, 'Department', 'Distribution')
    await expect(page.getByText('No one matches these filters.')).toBeVisible()
    await expect(count(page, '0 of 145 people')).toBeVisible()
    expect((await scan(page)).violations).toEqual([])
    await page.getByRole('button', { name: 'Clear filters' }).last().click()
    await expect(rows(page)).toHaveCount(50)
  })

  test('Show more loaded', async ({ page }) => {
    await openDirectory(page, 'Priya')
    await page.getByRole('button', { name: 'Show more' }).click()
    await expect(rows(page)).toHaveCount(100)
    expect((await scan(page)).violations).toEqual([])
  })
})

test.describe('a failed list request shows "something went wrong" inside the shell', () => {
  const REQUEST_ID = '7f3a9c2e5b1d4a60918c2e4f6a8b0d13'

  test('with the full reference and a Retry that asks again, then shows the list', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    let failed = 0
    await page.route(isListRequest, (route) => {
      failed += 1
      return route.fulfill({
        status: 500,
        contentType: 'application/problem+json',
        headers: { 'X-Request-ID': REQUEST_ID },
        body: problem(500, 'Internal Server Error'),
      })
    })
    await page.getByRole('link', { name: 'Directory' }).click()

    const wrong = page.getByRole('heading', { level: 1, name: 'Something went wrong on our side.' })
    await expect(wrong).toBeVisible()
    await expect(wrong).toBeFocused()
    // Inside the shell: the sidebar, the persona switcher, and the one <main> are still there.
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
    await expect(page.getByRole('button', { name: /^Switch persona/ })).toBeVisible()
    await expect(page.getByRole('main').getByRole('heading', { level: 1 })).toHaveCount(1)
    await expect(page.getByRole('main').locator('code')).toHaveText(REQUEST_ID)
    await expect(page.getByRole('link', { name: 'Directory' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect((await scan(page)).violations).toEqual([])

    // Retry asks again. Still failing, it shows the page again.
    const before = failed
    await page.getByRole('button', { name: 'Retry' }).click()
    await expect.poll(() => failed).toBeGreaterThan(before)
    await expect(wrong).toBeVisible()

    // Once the API answers, Retry gets the list.
    await page.unroute(isListRequest)
    await page.getByRole('button', { name: 'Retry' }).click()
    await expect(rows(page)).toHaveCount(50)
    await expect(count(page, '145 people')).toBeVisible()
  })
})

test('opening a row opens that person’s profile', async ({ page }) => {
  await openDirectory(page, 'Priya')
  await openProfileBySearch(page, 'Nakamura', /^Leo Nakamura/)
  await expect(page.getByRole('heading', { level: 1, name: 'Leo Nakamura' })).toBeVisible()
})
