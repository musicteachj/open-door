import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useChatStore } from '@/features/chat/store'
import { installFakeApi } from '@/test/fake-api'
import { installFakeHandbook, searchResult } from '@/test/fake-handbook'
import { renderApp } from '@/test/render-app'

// The handbook home at /handbook, from docs/design/screens/06-handbook, against a fake API.
const NOTICE =
  'Juniper Row is a fictional company. This handbook is demo content, not legal advice.'

type Persona = 'priya' | 'mateo'
type Api = ReturnType<typeof installFakeHandbook>

function overtimeSearch(q: string, sections: Api['sections']) {
  const byId = (id: string) => sections.find((s) => s.id === id)!
  if (q === 'overtime') {
    return [
      searchResult(byId('3.2'), 'Hourly staff are paid ', 'overtime', ' at 1.5 times', 'p3'),
      searchResult(byId('CA-3.2'), 'In California, ', 'overtime', ' is owed daily'),
      searchResult(byId('CO-3.2'), 'In Colorado, ', 'overtime', ' is also owed'),
    ]
  }
  return []
}

async function openHandbook(persona: Persona = 'priya', at = '/handbook') {
  installFakeApi(persona)
  const api = installFakeHandbook(persona, { search: overtimeSearch })
  const app = renderApp({ at })
  await screen.findByRole('heading', { level: 1, name: 'Employee handbook' })
  return { ...app, api }
}

const listReady = () => screen.findByRole('heading', { level: 2, name: 'Welcome' })
const slot = (name: string, within: ParentNode = document) =>
  Array.from(within.querySelectorAll<HTMLElement>(`[data-slot="${name}"]`))
const rows = () => slot('section-row')
const rowNames = () => rows().map((row) => row.getAttribute('aria-label')!)
const urlSearch = (r: { router: { state: { location: { search: string } } } }) =>
  r.router.state.location.search

beforeEach(() => {
  useChatStore.setState({ draft: '' })
})

describe('the header', () => {
  it('shows the title, the version line, and the demo notice', async () => {
    await openHandbook()
    expect(
      await screen.findByText('Juniper Row · Version 2026.10 · Updated Sep 12, 2026'),
    ).toBeVisible()
    expect(screen.getByText(NOTICE)).toBeVisible()
  })
})

describe('the list', () => {
  it('groups the company sections by chapter, then "State addenda" and the three addenda', async () => {
    await openHandbook()
    await listReady()
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual([
      'Welcome',
      'Working here',
      'Hours and pay',
      'Time off',
      'Leaves of absence',
      'Health, safety, and support',
      'Privacy and confidential cases',
      'State addenda',
      'California addendum',
      'Colorado addendum',
      'Texas addendum',
    ])
    expect(
      screen.getByText(
        'Each addendum section supplements the company section with the same number.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('For California employees')).toBeInTheDocument()
    expect(screen.getByText('For Colorado employees')).toBeInTheDocument()
    expect(screen.getByText('For Texas employees')).toBeInTheDocument()
    expect(rows()).toHaveLength(34)
  })

  it('puts each section under its own group', async () => {
    await openHandbook()
    await listReady()
    const time = screen.getByRole('region', { name: 'Time off' })
    expect(slot('section-row', time)).toHaveLength(5)
    const ca = screen.getByRole('region', { name: 'California addendum' })
    expect(slot('section-row', ca).map((r) => r.textContent)).toEqual([
      expect.stringContaining('CA-3.2'),
      expect.stringContaining('CA-3.3'),
      expect.stringContaining('CA-3.4'),
      expect.stringContaining('CA-4.3'),
      expect.stringContaining('CA-5.1'),
    ])
  })

  it('shows the column labels', async () => {
    await openHandbook()
    await listReady()
    for (const label of ['Section', 'Applies to', 'Last updated']) {
      expect(screen.getByText(label, { selector: '[aria-hidden="true"] span' })).toBeInTheDocument()
    }
  })

  it('marks only the restricted sections that cover Priya, never an Everyone row', async () => {
    await openHandbook('priya')
    await listReady()
    const marked = rowNames()
      .filter((name) => name.includes('Applies to you'))
      .map((name) => name.split(' ')[0])
    // Priya is salaried in California: the California sections that aren't for hourly staff.
    expect(marked).toEqual(['CA-3.4', 'CA-4.3', 'CA-5.1'])
    expect(rowNames().find((name) => name.startsWith('4.3 '))).not.toContain('Applies to you')
  })
})

describe('the Show menu', () => {
  it('counts every section and the ones that apply, and the counts match the list', async () => {
    const { user, api } = await openHandbook()
    await listReady()
    const applies = api.sections.filter((s) => s.appliesToMe)
    await user.click(screen.getByRole('combobox', { name: /Show/ }))
    expect(await screen.findByRole('option', { name: 'All sections, 34' })).toBeInTheDocument()
    expect(
      screen.getByRole('option', { name: `Applies to me, ${applies.length}` }),
    ).toBeInTheDocument()
    expect(rows()).toHaveLength(34)
  })

  it('keeps exactly the sections that apply, writes show=mine, and drops empty groups', async () => {
    const r = await openHandbook('priya')
    await listReady()
    const expected = r.api.sections.filter((s) => s.appliesToMe).map((s) => s.id)
    await r.user.click(screen.getByRole('combobox', { name: /Show/ }))
    await r.user.click(await screen.findByRole('option', { name: /^Applies to me/ }))
    await waitFor(() => expect(rows()).toHaveLength(expected.length))
    expect(rowNames().map((n) => n.split(' ')[0])).toEqual(expected)
    expect(urlSearch(r)).toBe('?show=mine')
    expect(screen.queryByRole('heading', { level: 2, name: 'Colorado addendum' })).toBeNull()
    expect(screen.queryByRole('heading', { level: 2, name: 'Texas addendum' })).toBeNull()
    expect(screen.getByRole('heading', { level: 2, name: 'California addendum' })).toBeVisible()
  })

  it('opens already filtered from the URL', async () => {
    const r = await openHandbook('mateo', '/handbook?show=mine')
    await listReady()
    const expected = r.api.sections.filter((s) => s.appliesToMe).length
    expect(rows()).toHaveLength(expected)
    expect(screen.getByRole('combobox', { name: /Show/ })).toHaveTextContent('Applies to me')
  })
})

describe('searching', () => {
  it('shows the results the API orders, with the count, the source, and the match', async () => {
    const { user, api } = await openHandbook('mateo')
    await user.type(screen.getByRole('searchbox', { name: 'Search the handbook' }), 'overtime')
    expect(await screen.findByText('3 sections match “overtime”')).toBeInTheDocument()
    const links = slot('search-result-row')
    expect(links.map((l) => l.getAttribute('aria-label'))).toEqual([
      '3.2 Overtime, Company handbook',
      'CA-3.2 Overtime, California addendum',
      'CO-3.2 Overtime, Colorado addendum',
    ])
    expect(links[0]).toHaveAttribute('href', '/handbook/3.2?passage=p3')
    expect(within(links[0]!).getByText('overtime').tagName).toBe('MARK')
    expect(api.searches()).toEqual(['overtime'])
    // The list is gone, and the notice stays.
    expect(rows()).toHaveLength(0)
    expect(screen.getByText(NOTICE)).toBeVisible()
  })

  it('writes q to the URL, and a link with q opens the results', async () => {
    const r = await openHandbook('mateo', '/handbook?q=overtime')
    expect(await screen.findByText('3 sections match “overtime”')).toBeInTheDocument()
    expect(screen.getByRole('searchbox', { name: 'Search the handbook' })).toHaveValue('overtime')
    expect(urlSearch(r)).toBe('?q=overtime')
  })

  it('says "1 section matches" for one result', async () => {
    installFakeApi('priya')
    installFakeHandbook('priya', {
      search: (_q, sections) => [searchResult(sections[0]!, 'About ', 'this', ' handbook')],
    })
    renderApp({ at: '/handbook?q=this' })
    expect(await screen.findByText('1 section matches “this”')).toBeInTheDocument()
  })

  it('goes back to the list when the search is cleared', async () => {
    const { user } = await openHandbook('mateo', '/handbook?q=overtime')
    await user.click(await screen.findByRole('button', { name: 'Clear search' }))
    await listReady()
    expect(rows()).toHaveLength(34)
  })

  it('keeps the search to 100 characters', async () => {
    await openHandbook()
    expect(screen.getByRole('searchbox', { name: 'Search the handbook' })).toHaveAttribute(
      'maxlength',
      '100',
    )
  })
})

describe('no results', () => {
  async function noResults() {
    const app = await openHandbook('mateo', '/handbook?q=dental%20plan')
    await screen.findByText('No sections match “dental plan.”')
    return app
  }

  it('says so, and offers Clear search and Ask the assistant', async () => {
    await noResults()
    // The field's own × and the action beside the message.
    expect(screen.getAllByRole('button', { name: 'Clear search' })).toHaveLength(2)
    expect(screen.getByRole('button', { name: /Ask the assistant/ })).toBeEnabled()
    expect(screen.getByText(NOTICE)).toBeVisible()
  })

  it('empties the field and the URL with Clear search', async () => {
    const r = await noResults()
    const clear = screen.getAllByRole('button', { name: 'Clear search' })
    await r.user.click(clear.at(-1)!)
    await listReady()
    expect(urlSearch(r)).toBe('')
    expect(screen.getByRole('searchbox', { name: 'Search the handbook' })).toHaveValue('')
  })

  it('opens Ask with the search text in the composer, not sent', async () => {
    const r = await noResults()
    await r.user.click(screen.getByRole('button', { name: /Ask the assistant/ }))
    expect(r.router.state.location.pathname).toBe('/ask')
    expect(useChatStore.getState()).toMatchObject({ draft: 'dental plan', status: 'idle' })
    // The composer on Ask shows the text, ready to edit; nothing was sent.
    expect(await screen.findByRole('textbox', { name: 'Ask Open Door' })).toHaveValue('dental plan')
    expect(screen.queryByRole('region', { name: "Open Door's reply" })).not.toBeInTheDocument()
  })
})

describe('loading', () => {
  it('shows skeleton rows with the header, search, filter, and column labels kept', async () => {
    installFakeApi('priya')
    const api = installFakeHandbook('priya')
    const release = api.holdOverview()
    renderApp({ at: '/handbook' })
    await screen.findByRole('heading', { level: 1, name: 'Employee handbook' })
    expect(screen.getByRole('searchbox', { name: 'Search the handbook' })).toBeVisible()
    expect(screen.getByRole('combobox', { name: /Show/ })).toBeVisible()
    expect(
      screen.getByText('Last updated', { selector: '[aria-hidden="true"] span' }),
    ).toBeVisible()
    expect(screen.getByText(NOTICE)).toBeVisible()
    expect(document.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(10)
    expect(rows()).toHaveLength(0)
    expect(await screen.findByText('Loading the handbook')).toBeInTheDocument()
    release()
    await listReady()
    expect(document.querySelectorAll('[data-slot="skeleton"]')).toHaveLength(0)
  })
})

describe('a failure', () => {
  it('shows the route error page inside the shell when the list cannot load', async () => {
    installFakeApi('priya')
    installFakeHandbook('priya').failOverview(500)
    renderApp({ at: '/handbook' })
    expect(await screen.findByText('Something went wrong on our side.')).toBeVisible()
  })
})

describe('a new search while the old results are on screen', () => {
  function twoSearches(q: string, sections: Api['sections']) {
    if (q === 'aaa') return [searchResult(sections[0]!, 'one ', 'aaa', ' here')]
    if (q === 'aaa2') return [searchResult(sections[1]!, 'one ', 'aaa2', ' x')]
    if (q === 'bbb') return [searchResult(sections[2]!, 'two ', 'bbb', ' here')]
    return []
  }

  it('shows no count for the new query until its results arrive', async () => {
    installFakeApi('priya')
    const api = installFakeHandbook('priya', { search: twoSearches })
    const release = api.holdSearch('bbb')
    const { user } = Object.assign(renderApp({ at: '/handbook?q=aaa' }), {})
    expect(await screen.findByText('1 section matches “aaa”')).toBeInTheDocument()
    const box = screen.getByRole('searchbox', { name: 'Search the handbook' })
    await user.clear(box)
    await user.type(box, 'bbb')
    await waitFor(() => expect(api.searches()).toContain('bbb'))
    // The old row may stay, dimmed and busy, but nothing claims it matches "bbb".
    expect(screen.queryByText(/sections? match/)).toBeNull()
    expect(screen.queryByText(/No sections/)).toBeNull()
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    release()
    expect(await screen.findByText('1 section matches “bbb”')).toBeInTheDocument()
    expect(slot('search-result-row')).toHaveLength(1)
    expect(slot('search-result-row')[0]).toHaveAttribute('href', '/handbook/2.1?passage=p1')
  })

  it('does not flash "No sections match" while the first results of a new query load', async () => {
    installFakeApi('priya')
    const api = installFakeHandbook('priya', { search: twoSearches })
    const release = api.holdSearch('aaa')
    const { user } = renderApp({ at: '/handbook?q=nothing' })
    expect(await screen.findByText('No sections match “nothing.”')).toBeInTheDocument()
    const box = screen.getByRole('searchbox', { name: 'Search the handbook' })
    await user.clear(box)
    await user.type(box, 'aaa')
    await waitFor(() => expect(api.searches()).toContain('aaa'))
    expect(screen.queryByText(/No sections/)).toBeNull()
    release()
    expect(await screen.findByText('1 section matches “aaa”')).toBeInTheDocument()
  })
})

describe('Clear search from the no-results state', () => {
  it('puts focus in the search field', async () => {
    const { user } = await openHandbook('mateo', '/handbook?q=dental%20plan')
    await screen.findByText('No sections match “dental plan.”')
    const buttons = screen.getAllByRole('button', { name: 'Clear search' })
    await user.click(buttons.at(-1)!)
    await listReady()
    expect(screen.getByRole('searchbox', { name: 'Search the handbook' })).toHaveFocus()
  })
})

describe('"Applies to me"', () => {
  it('keeps the whole list in the All count when the page opens filtered', async () => {
    const { user, api } = await openHandbook('priya', '/handbook?show=mine')
    await listReady()
    await user.click(screen.getByRole('combobox', { name: /Show/ }))
    expect(
      await screen.findByRole('option', { name: `All sections, ${api.sections.length}` }),
    ).toBeInTheDocument()
    const applies = api.sections.filter((s) => s.appliesToMe).length
    expect(screen.getByRole('option', { name: `Applies to me, ${applies}` })).toBeInTheDocument()
  })

  it('keeps only the results that apply to the person, and counts those', async () => {
    await openHandbook('mateo', '/handbook?show=mine&q=overtime')
    expect(await screen.findByText('1 section matches “overtime”')).toBeInTheDocument()
    expect(slot('search-result-row').map((l) => l.getAttribute('aria-label'))).toEqual([
      '3.2 Overtime, Company handbook',
    ])
  })

  it('says none that apply match, not that none match, and offers to show all', async () => {
    const r = await openHandbook('priya', '/handbook?show=mine&q=overtime')
    expect(
      await screen.findByText('No sections that apply to you match “overtime.”'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/^No sections match/)).toBeNull()
    expect(screen.getByRole('button', { name: /Ask the assistant/ })).toBeEnabled()
    await r.user.click(screen.getByRole('button', { name: 'Show all sections' }))
    expect(await screen.findByText('3 sections match “overtime”')).toBeInTheDocument()
    expect(urlSearch(r)).toBe('?q=overtime')
  })

  it('still says "No sections match" when the search itself finds nothing', async () => {
    await openHandbook('priya', '/handbook?show=mine&q=dental%20plan')
    expect(await screen.findByText('No sections match “dental plan.”')).toBeInTheDocument()
  })
})

describe('typing and following a result', () => {
  it('writes the typed text before a result link is followed, so Back returns to it', async () => {
    const r = await openHandbook('mateo', '/handbook?q=overtime')
    await screen.findByText('3 sections match “overtime”')
    await r.user.type(screen.getByRole('searchbox', { name: 'Search the handbook' }), 'x')
    await r.user.click(slot('search-result-row')[0]!)
    expect(r.router.state.location.pathname).toBe('/handbook/3.2')
    await r.router.navigate(-1)
    expect(urlSearch(r)).toBe('?q=overtimex')
  })

  it('shows a search from a link at the 100 characters the API takes', async () => {
    await openHandbook('priya', `/handbook?q=${'a'.repeat(120)}`)
    expect(screen.getByRole('searchbox', { name: 'Search the handbook' })).toHaveValue(
      'a'.repeat(100),
    )
  })
})

describe('a search that fails', () => {
  const answers = (q: string, sections: Api['sections']) =>
    q === 'aaa'
      ? [searchResult(sections[0]!, 'one ', 'aaa', ' here')]
      : q === 'good'
        ? [searchResult(sections[1]!, 'a ', 'good', ' one')]
        : []

  async function typeNew(user: ReturnType<typeof renderApp>['user'], text: string) {
    const box = screen.getByRole('searchbox', { name: 'Search the handbook' })
    await user.clear(box)
    await user.type(box, text)
  }

  it('shows the error with Retry, not a skeleton, after a search that found nothing', async () => {
    installFakeApi('priya')
    const api = installFakeHandbook('priya', { search: answers })
    api.failSearch('bad')
    const { user } = renderApp({ at: '/handbook?q=nothing' })
    await screen.findByText('No sections match “nothing.”')
    await typeNew(user, 'bad')
    expect(await screen.findByText("We couldn't search the handbook.")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.queryByText('Searching the handbook')).toBeNull()
    expect(document.querySelector('[data-slot="skeleton"]')).toBeNull()
  })

  it('shows the error and drops the old rows when earlier results were on screen', async () => {
    installFakeApi('priya')
    const api = installFakeHandbook('priya', { search: answers })
    api.failSearch('bad')
    const { user } = renderApp({ at: '/handbook?q=aaa' })
    await screen.findByText('1 section matches “aaa”')
    await typeNew(user, 'bad')
    expect(await screen.findByText("We couldn't search the handbook.")).toBeInTheDocument()
    expect(slot('search-result-row')).toHaveLength(0)
    expect(screen.queryByText('Searching the handbook')).toBeNull()
    expect(document.querySelector('[aria-busy="true"]')).toBeNull()
  })

  it('recovers to the right results with Retry', async () => {
    installFakeApi('priya')
    const api = installFakeHandbook('priya', { search: answers })
    api.failSearch('good')
    const { user } = renderApp({ at: '/handbook?q=aaa' })
    await screen.findByText('1 section matches “aaa”')
    await typeNew(user, 'good')
    await screen.findByText("We couldn't search the handbook.")
    api.failSearch('good', false)
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('1 section matches “good”')).toBeInTheDocument()
    expect(screen.queryByText("We couldn't search the handbook.")).toBeNull()
    expect(slot('search-result-row')[0]).toHaveAttribute('href', '/handbook/1.2?passage=p1')
  })
})
