import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { installFakeApi } from '@/test/fake-api'
import {
  DEPARTMENT_OPTIONS,
  DIRECTORY_PEOPLE,
  DIRECTORY_SIZE,
  fullNameOf,
  installFakeDirectory,
  LOCATION_OPTIONS,
} from '@/test/fake-directory'
import { renderApp } from '@/test/render-app'

// The directory at /directory, from docs/design/screens/04-directory, against a fake API.
async function openDirectory(persona: 'priya' | 'marcus' = 'priya') {
  installFakeApi(persona)
  const api = installFakeDirectory(persona)
  const app = renderApp({ at: '/directory' })
  await screen.findByRole('list', { name: 'People' })
  return { ...app, api }
}

const rows = () => within(screen.getByRole('list', { name: 'People' })).getAllByRole('listitem')
const rowNames = () => rows().map((li) => within(li).getByRole('link').getAttribute('aria-label')!)
const heading = () => screen.getByRole('heading', { level: 1, name: 'Directory' })
const countText = () => heading().parentElement!.textContent
const location = (r: { router: { state: { location: { search: string } } } }) =>
  r.router.state.location.search

describe('the list', () => {
  it('shows the first 50 people sorted by last name, then "Showing 50 of 120" and Show more', async () => {
    await openDirectory()
    expect(rows()).toHaveLength(50)
    const families = rowNames().map((label) => label.split(',')[0]!.split(' ').at(-1)!)
    const first50 = DIRECTORY_PEOPLE.slice(0, 50).map((p) => p.familyName)
    expect(families).toEqual(first50)
    expect(first50).toEqual([...first50].sort((a, b) => a.localeCompare(b)))
    expect(screen.getByText('Showing 50 of 120')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show more' })).toBeInTheDocument()
  })

  it('appends the next page with the cursor when Show more is pressed, to the end', async () => {
    const { user, api } = await openDirectory()
    await user.click(screen.getByRole('button', { name: 'Show more' }))
    await waitFor(() => expect(rows()).toHaveLength(100))
    expect(api.listParams().at(-1)).toMatchObject({ cursor: '50', limit: '50' })
    // The first page is still there, then the next 50, in order.
    expect(rowNames()[0]).toContain(fullNameOf(DIRECTORY_PEOPLE[0]!))
    expect(rowNames()[99]).toContain(fullNameOf(DIRECTORY_PEOPLE[99]!))
    expect(screen.getByText('Showing 100 of 120')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Show more' }))
    await waitFor(() => expect(rows()).toHaveLength(DIRECTORY_SIZE))
    expect(screen.getByText('Showing all 120')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Show more' })).not.toBeInTheDocument()
  })

  it('tags the signed-in person\'s own row "You", and names it "(you)"', async () => {
    const { user } = await openDirectory()
    // Priya sits past the first page: press Show more until her row is there.
    while (!screen.queryByRole('link', { name: /^Priya Raman/ })) {
      await user.click(screen.getByRole('button', { name: 'Show more' }))
      await screen.findByText(/^Showing /)
    }
    const own = screen.getByRole('link', { name: /^Priya Raman, .*\(you\)$/ })
    expect(within(own).getByText('You')).toBeInTheDocument()
    expect(screen.queryAllByText('You')).toHaveLength(1)
  })
})

describe('the header count', () => {
  it('reads "120 people" with nothing applied', async () => {
    await openDirectory()
    await waitFor(() => expect(countText()).toBe('Directory120 people'))
  })

  it('reads "44 of 120 people" while filtering', async () => {
    const { user } = await openDirectory('marcus')
    await user.click(await screen.findByRole('button', { name: /^My team/ }))
    await waitFor(() => expect(countText()).toBe('Directory44 of 120 people'))
  })

  it('reads "0 of 120 people" when a search matches no one', async () => {
    const { user } = await openDirectory()
    await user.type(screen.getByRole('searchbox'), 'Jordn')
    await waitFor(() => expect(countText()).toBe('Directory0 of 120 people'))
  })
})

describe('the filters', () => {
  it("shows each menu's counts from the facets, zeros included", async () => {
    const { user } = await openDirectory()
    await waitFor(() => expect(countText()).toContain('120 people'))
    await user.click(screen.getByRole('combobox', { name: 'Location' }))
    for (const l of LOCATION_OPTIONS) {
      const n = DIRECTORY_PEOPLE.filter((p) => p.location.id === l.id).length
      expect(await screen.findByRole('option', { name: `${l.name}, ${n}` })).toBeInTheDocument()
    }
    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('combobox', { name: 'Department' }))
    for (const d of DEPARTMENT_OPTIONS) {
      const n = DIRECTORY_PEOPLE.filter((p) => p.department.id === d.id).length
      expect(await screen.findByRole('option', { name: `${d.name}, ${n}` })).toBeInTheDocument()
    }
  })

  it('writes a chosen filter to the URL as its short name, and sends the API name', async () => {
    const r = await openDirectory()
    await r.user.click(screen.getByRole('combobox', { name: 'Location' }))
    await r.user.click(await screen.findByRole('option', { name: /^Denver HQ/ }))
    await waitFor(() => expect(location(r)).toBe('?location=00000000-0000-4000-9000-000000000002'))
    await waitFor(() =>
      expect(r.api.listParams().at(-1)).toMatchObject({
        locationId: '00000000-0000-4000-9000-000000000002',
      }),
    )
  })

  it('starts again at page one when a filter changes, instead of adding to the old pages', async () => {
    const r = await openDirectory()
    await r.user.click(screen.getByRole('button', { name: 'Show more' }))
    await waitFor(() => expect(rows()).toHaveLength(100))

    await r.user.click(screen.getByRole('combobox', { name: 'Location' }))
    await r.user.click(await screen.findByRole('option', { name: /^Denver HQ/ }))
    const denver = r.api.matching({ locationId: '00000000-0000-4000-9000-000000000002' })
    await waitFor(() => expect(rows()).toHaveLength(denver.length))
    const afterChange = r.api
      .listParams()
      .filter((p) => p.locationId === '00000000-0000-4000-9000-000000000002')
    expect(afterChange[0]).not.toHaveProperty('cursor')
    expect(rowNames().every((label) => label.includes('Denver HQ'))).toBe(true)
  })

  it('never sends or writes "null" for a filter that is off', async () => {
    const r = await openDirectory()
    await r.user.click(screen.getByRole('combobox', { name: 'Location' }))
    await r.user.click(await screen.findByRole('option', { name: /^Denver HQ/ }))
    await waitFor(() => expect(location(r)).toBe('?location=00000000-0000-4000-9000-000000000002'))
    await r.user.click(screen.getByRole('combobox', { name: 'Location' }))
    await r.user.click(await screen.findByRole('option', { name: 'All' }))
    await waitFor(() => expect(location(r)).toBe(''))
    await waitFor(() => expect(r.api.listParams().at(-1)).not.toHaveProperty('locationId'))
    for (const u of [...r.api.listRequests, ...r.api.facetRequests]) {
      expect(u.search).not.toContain('null')
    }
    // The first request carries no filters at all, only the page size.
    expect(r.api.listParams()[0]).toEqual({ limit: '50' })
    expect(r.api.facetRequests[0]!.search).toBe('')
  })

  it('shows "My team" only to someone with reports', async () => {
    await openDirectory('priya')
    await waitFor(() => expect(countText()).toContain('120 people'))
    expect(screen.queryByRole('button', { name: /My team/ })).not.toBeInTheDocument()
  })

  it('shows "My team" with its count, pressed on, for a manager', async () => {
    const r = await openDirectory('marcus')
    const toggle = await screen.findByRole('button', { name: 'My team 44' })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    await r.user.click(toggle)
    expect(await screen.findByRole('button', { name: 'My team 44' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(location(r)).toBe('?team=mine')
    await waitFor(() => expect(r.api.listParams().at(-1)).toMatchObject({ team: 'mine' }))
  })

  it('shows "Clear filters" only while a filter is on, and it resets them but keeps the search', async () => {
    const r = await openDirectory('marcus')
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
    await r.user.type(screen.getByRole('searchbox'), 'a')
    await waitFor(() => expect(location(r)).toBe('?q=a'))
    // A search alone is not a filter.
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
    await r.user.click(await screen.findByRole('button', { name: /^My team/ }))
    await r.user.click(await screen.findByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(location(r)).toBe('?q=a'))
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
  })
})

describe('search', () => {
  it('writes q after a pause, replacing the history entry, and narrows the list', async () => {
    const r = await openDirectory()
    await r.user.type(screen.getByRole('searchbox'), 'Zhang')
    await waitFor(() => expect(location(r)).toBe('?q=Zhang'))
    await waitFor(() => expect(rows()).toHaveLength(3))
    // Five keystrokes, one list request for the search: none for a half-typed word.
    const searches = r.api.listParams().filter((p) => p.q !== undefined)
    expect(searches.map((p) => p.q)).toEqual(['Zhang'])
    expect(r.router.state.historyAction).toBe('REPLACE')
    expect(countText()).toBe('Directory3 of 120 people')
  })
})

describe('following a row before the search pause ends', () => {
  it('keeps the typed search in the box and the URL when the visitor comes back', async () => {
    const r = await openDirectory()
    await r.user.type(screen.getByRole('searchbox'), 'jo')
    // The 250 ms pause has not passed, so "jo" is not in the URL yet.
    expect(location(r)).toBe('')
    await r.user.click(
      within(screen.getByRole('list', { name: 'People' })).getAllByRole('link')[0]!,
    )
    await screen.findByRole('link', { name: 'Back to Directory' })
    await r.user.click(screen.getByRole('link', { name: 'Back to Directory' }))
    await screen.findByRole('list', { name: 'People' })
    expect(screen.getByRole('searchbox')).toHaveValue('jo')
    expect(location(r)).toBe('?q=jo')
  })
})

describe('loading', () => {
  it('shows eight skeleton rows and announces it, only on the first load', async () => {
    installFakeApi('priya')
    const api = installFakeDirectory('priya')
    api.delayList(150)
    renderApp({ at: '/directory' })
    await waitFor(() =>
      expect(document.querySelectorAll('[data-slot="skeleton-row"]')).toHaveLength(8),
    )
    expect(await screen.findByText('Loading the directory')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'People' })).not.toBeInTheDocument()
    await screen.findByRole('list', { name: 'People' })
    expect(document.querySelectorAll('[data-slot="skeleton-row"]')).toHaveLength(0)
  })

  it('keeps the previous results on screen while a search loads', async () => {
    const r = await openDirectory()
    const first = rowNames()[0]
    r.api.delayList(300)
    await r.user.type(screen.getByRole('searchbox'), 'Zhang')
    await waitFor(() => expect(location(r)).toBe('?q=Zhang'))
    // The search is in flight: the old rows are still there, with no skeleton and no announcement.
    expect(rowNames()[0]).toBe(first)
    expect(document.querySelectorAll('[data-slot="skeleton-row"]')).toHaveLength(0)
    expect(screen.queryByText('Loading the directory')).not.toBeInTheDocument()
    await waitFor(() => expect(rows()).toHaveLength(3))
  })
})

describe('when nothing matches', () => {
  it('says no one matches the search, with the curly quotes, and "Clear search" brings the list back', async () => {
    const r = await openDirectory()
    await r.user.type(screen.getByRole('searchbox'), 'Jordn')
    expect(await screen.findByText('No one matches “Jordn”.')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'People' })).not.toBeInTheDocument()
    // Two "Clear search" buttons would be one too many: the field's × and the empty state's.
    const empty = screen.getByText('No one matches “Jordn”.').closest('output')!
    await r.user.click(within(empty).getByRole('button', { name: 'Clear search' }))
    await waitFor(() => expect(rows()).toHaveLength(50))
    expect(screen.getByRole('searchbox')).toHaveValue('')
    expect(location(r)).toBe('')
  })

  it('says no one matches the filters, and "Clear filters" brings the list back', async () => {
    const r = await openDirectory()
    await r.user.click(screen.getByRole('combobox', { name: 'Department' }))
    await r.user.click(await screen.findByRole('option', { name: 'Legal, 0' }))
    const message = await screen.findByText('No one matches these filters.')
    await r.user.click(
      within(message.closest('output')!).getByRole('button', { name: 'Clear filters' }),
    )
    await waitFor(() => expect(rows()).toHaveLength(50))
    expect(location(r)).toBe('')
  })
})

describe('when one of the two first requests fails', () => {
  it('keeps the rows and shows the inline alert when the list arrives and the facets fail', async () => {
    installFakeApi('priya')
    const api = installFakeDirectory('priya')
    api.failFacets(500)
    api.delayFacets(80) // the list is on screen before the facets give up
    renderApp({ at: '/directory' })
    await screen.findByRole('list', { name: 'People' })
    expect(await screen.findByRole('alert')).toHaveTextContent("We couldn't load the filters.")
    expect(rows()).toHaveLength(50)
    expect(screen.getByRole('heading', { level: 1, name: 'Directory' })).toBeInTheDocument()
  })

  it('still shows the error page when the counts arrive and the list fails, since the list is the page', async () => {
    installFakeApi('priya')
    const api = installFakeDirectory('priya')
    api.failList(500)
    api.delayList(80) // the counts are on screen before the list gives up
    renderApp({ at: '/directory' })
    expect(
      await screen.findByRole('heading', { name: 'Something went wrong on our side.' }),
    ).toBeInTheDocument()
  })
})

describe('when an update cannot load', () => {
  const pickDenver = async (user: Awaited<ReturnType<typeof openDirectory>>['user']) => {
    await user.click(screen.getByRole('combobox', { name: 'Location' }))
    await user.click(await screen.findByRole('option', { name: /^Denver HQ/ }))
  }

  it("keeps the earlier rows and says so inline when a filter's list fails, and Retry recovers", async () => {
    const { user, api } = await openDirectory()
    await waitFor(() => expect(countText()).toBe('Directory120 people'))
    api.failListWhen({ locationId: '00000000-0000-4000-9000-000000000002' })
    await pickDenver(user)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("We couldn't update the list.")
    // Still the directory, with the rows it had: not the error page, not "no one matches".
    expect(screen.getByRole('heading', { level: 1, name: 'Directory' })).toBeInTheDocument()
    expect(rows()).toHaveLength(50)
    expect(screen.queryByText('No one matches these filters.')).not.toBeInTheDocument()

    api.failListWhen(null)
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(rows()).toHaveLength(40))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps the earlier counts when only the facets fail, and Retry recovers', async () => {
    const { user, api } = await openDirectory()
    await waitFor(() => expect(countText()).toBe('Directory120 people'))
    api.failFacets(500)
    await pickDenver(user)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("We couldn't update the list.")
    await waitFor(() => expect(rows()).toHaveLength(40))
    expect(countText()).toBe('Directory120 people')
    expect(screen.getByRole('heading', { level: 1, name: 'Directory' })).toBeInTheDocument()

    api.failFacets(null)
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(countText()).toBe('Directory40 of 120 people'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('the footer when an update has failed', () => {
  it('makes no claim about the old rows, and is right for the new search after Retry', async () => {
    const { user, api } = await openDirectory()
    await user.click(screen.getByRole('button', { name: 'Show more' }))
    await waitFor(() => expect(rows()).toHaveLength(100))
    expect(screen.getByText('Showing 100 of 120')).toBeInTheDocument()

    api.failListWhen({ q: 'a' })
    await user.type(screen.getByRole('searchbox'), 'a')
    const alert = await screen.findByRole('alert')
    // The 100 old rows are still shown, but the failed query knows nothing of more pages.
    expect(rows()).toHaveLength(100)
    expect(screen.queryByText(/^Showing /)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Show more' })).not.toBeInTheDocument()

    api.failListWhen(null)
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(rows()).toHaveLength(50))
    expect(await screen.findByText('Showing 50 of 120')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show more' })).toBeInTheDocument()
  })
})

describe('the footer when the counts are stale', () => {
  it('claims no total from counts that belong to the old filters', async () => {
    const { user, api } = await openDirectory()
    await waitFor(() => expect(screen.getByText('Showing 50 of 120')).toBeInTheDocument())
    api.failFacets(500)
    // A search matching everyone: the list loads, and only the counts fail.
    await user.type(screen.getByRole('searchbox'), 'a')
    await screen.findByRole('alert')
    await waitFor(() => expect(screen.queryByText('Showing 50 of 120')).not.toBeInTheDocument())
    expect(screen.getByText('Showing 50')).toBeInTheDocument()
  })
})

describe('when a later page cannot load', () => {
  it('keeps the pages already loaded, says so in an alert, and Retry loads the next page', async () => {
    const { user, api } = await openDirectory()
    api.failLaterPages(500)
    await user.click(screen.getByRole('button', { name: 'Show more' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("We couldn't load more people.")
    // Still the directory, with the first page where it was: no error page.
    expect(rows()).toHaveLength(50)
    expect(screen.getByRole('heading', { level: 1, name: 'Directory' })).toBeInTheDocument()

    api.failLaterPages(null)
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(rows()).toHaveLength(100))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('a filter the API would refuse', () => {
  it.each(['?location=abc', '?department=not-a-uuid', '?location=abc&department=not-a-uuid'])(
    'opens the list unfiltered for %s, and sends no invalid ID',
    async (query) => {
      installFakeApi('priya')
      const api = installFakeDirectory('priya')
      renderApp({ at: `/directory${query}` })
      await screen.findByRole('list', { name: 'People' })
      await waitFor(() => expect(countText()).toBe('Directory120 people'))
      expect(rows()).toHaveLength(50)
      for (const u of [...api.listRequests, ...api.facetRequests]) {
        expect(u.searchParams.has('locationId')).toBe(false)
        expect(u.searchParams.has('departmentId')).toBe(false)
      }
    },
  )

  it('still filters by a valid UUID in the URL', async () => {
    installFakeApi('priya')
    const api = installFakeDirectory('priya')
    renderApp({ at: '/directory?location=00000000-0000-4000-9000-000000000002' })
    await screen.findByRole('list', { name: 'People' })
    expect(api.listParams()[0]).toMatchObject({
      locationId: '00000000-0000-4000-9000-000000000002',
    })
  })
})

describe('a filter that matches no option', () => {
  // Each sandbox has its own IDs, so a link from another sandbox is a well-formed UUID that this
  // one has never heard of.
  const UNKNOWN_LOCATION = '00000000-0000-4000-9000-0000000000ff'
  const UNKNOWN_DEPARTMENT = '00000000-0000-4000-a000-0000000000ff'

  it.each([
    `?location=${UNKNOWN_LOCATION}`,
    `?department=${UNKNOWN_DEPARTMENT}`,
    `?location=${UNKNOWN_LOCATION}&department=${UNKNOWN_DEPARTMENT}`,
  ])('is no filter for %s: everyone is listed, and no request carries it', async (query) => {
    installFakeApi('priya')
    const api = installFakeDirectory('priya')
    renderApp({ at: `/directory${query}` })
    await screen.findByRole('list', { name: 'People' })
    await waitFor(() => expect(countText()).toBe('Directory120 people'))
    expect(rows()).toHaveLength(50)
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
    for (const u of [...api.listRequests, ...api.facetRequests]) {
      expect(u.searchParams.has('locationId')).toBe(false)
      expect(u.searchParams.has('departmentId')).toBe(false)
    }
  })

  it('still filters by a known option in the same link as an unknown one', async () => {
    installFakeApi('priya')
    const api = installFakeDirectory('priya')
    renderApp({
      at: `/directory?location=00000000-0000-4000-9000-000000000002&department=${UNKNOWN_DEPARTMENT}`,
    })
    await screen.findByRole('list', { name: 'People' })
    await waitFor(() => expect(countText()).toBe('Directory40 of 120 people'))
    expect(api.listParams().at(-1)).toMatchObject({
      locationId: '00000000-0000-4000-9000-000000000002',
    })
    expect(api.listParams().at(-1)).not.toHaveProperty('departmentId')
  })
})

describe('when the filters cannot load on the first visit', () => {
  it('shows the list, hides the count and the menus, and offers Retry for the filters', async () => {
    installFakeApi('priya')
    const api = installFakeDirectory('priya')
    api.failFacets(500)
    const { user } = renderApp({ at: '/directory' })
    await screen.findByRole('list', { name: 'People' })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("We couldn't load the filters.")
    expect(screen.queryByText("We couldn't update the list.")).not.toBeInTheDocument()
    expect(rows()).toHaveLength(50)
    expect(countText()).toBe('Directory')
    expect(document.querySelector('[data-slot="skeleton"]')).toBeNull()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()

    api.failFacets(null)
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(countText()).toBe('Directory120 people'))
    expect(screen.getAllByRole('combobox')).toHaveLength(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('when the filters cannot load on a link that carries a location', () => {
  it('lists without the location, and applies it once Retry succeeds', async () => {
    installFakeApi('priya')
    const api = installFakeDirectory('priya')
    api.failFacets(500)
    const denver = '00000000-0000-4000-9000-000000000002'
    const { user } = renderApp({ at: `/directory?location=${denver}` })
    await screen.findByRole('list', { name: 'People' })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("We couldn't load the filters.")
    expect(rows()).toHaveLength(50)
    expect(api.listParams().every((p) => !('locationId' in p))).toBe(true)

    api.failFacets(null)
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(rows()).toHaveLength(40))
    expect(api.listParams().at(-1)).toMatchObject({ locationId: denver })
  })
})

describe('a search the API would refuse', () => {
  it('opens the list for ?q=%00, with no search, instead of the error page', async () => {
    installFakeApi('priya')
    const api = installFakeDirectory('priya')
    renderApp({ at: '/directory?q=%00' })
    await screen.findByRole('list', { name: 'People' })
    expect(api.listParams()[0]).toEqual({ limit: '50' })
  })

  it('sends at most 100 characters of a longer search in the URL', async () => {
    installFakeApi('priya')
    const api = installFakeDirectory('priya')
    renderApp({ at: `/directory?q=${'a'.repeat(150)}` })
    await screen.findByText(/^No one matches /)
    expect(api.listParams()[0]!.q).toBe('a'.repeat(100))
  })

  it('limits the search box to the 100 characters the API takes', async () => {
    await openDirectory()
    expect(screen.getByRole('searchbox')).toHaveAttribute('maxlength', '100')
  })
})

describe('when the list cannot load', () => {
  it('shows "Something went wrong" inside the shell, with the request reference', async () => {
    installFakeApi('priya')
    installFakeDirectory('priya').failList(500)
    renderApp({ at: '/directory' })
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Something went wrong on our side.' }),
    ).toBeInTheDocument()
    expect(screen.getByText('b'.repeat(32))).toBeInTheDocument()
    // The shell is still there.
    expect(screen.getByRole('link', { name: 'Directory' })).toBeInTheDocument()
  })

  it('tries again from Retry', async () => {
    installFakeApi('priya')
    const api = installFakeDirectory('priya')
    api.failList(500)
    const { user } = renderApp({ at: '/directory' })
    await screen.findByRole('heading', { name: 'Something went wrong on our side.' })
    api.failList(null)
    await user.click(screen.getByRole('button', { name: /Try again|Retry/ }))
    expect(await screen.findByRole('list', { name: 'People' })).toBeInTheDocument()
  })
})
