import { act, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { getGetHandbookSectionQueryKey } from '@/api/generated'
import { installFakeApi } from '@/test/fake-api'
import { http, HttpResponse } from 'msw'
import { installFakeHandbook, handbookSection } from '@/test/fake-handbook'
import { server } from '@/test/msw'
import { renderApp } from '@/test/render-app'

// The section page at /handbook/:sectionId, from docs/design/screens/06-handbook, against a fake API.
const NOTICE =
  'Juniper Row is a fictional company. This handbook is demo content, not legal advice.'

type Persona = 'priya' | 'mateo'

async function openSection(id: string, persona: Persona = 'priya', search = '') {
  installFakeApi(persona)
  const api = installFakeHandbook(persona)
  const app = renderApp({ at: `/handbook/${id}${search}` })
  return { ...app, api }
}

const title = (name: string) => screen.findByRole('heading', { level: 1, name })

describe('a company section (4.3 as Priya)', () => {
  it('shows the eyebrow, title, badge, marker, date, and the demo notice', async () => {
    await openSection('4.3')
    await title('Sick leave')
    expect(screen.getByText('§4.3 · Time off')).toBeVisible()
    expect(screen.getByText('Applies to:')).toBeVisible()
    expect(screen.getByText('Everyone')).toBeVisible()
    // The marker is in the header, and again on the State rules row that applies.
    expect(screen.getAllByText('Applies to you')[0]).toBeVisible()
    expect(screen.getByText('Last updated Sep 12, 2026')).toBeVisible()
    expect(screen.getByText(NOTICE)).toBeVisible()
    expect(screen.queryByText(/This section is for/)).not.toBeInTheDocument()
  })

  it('links back to the handbook, and keeps the Handbook item selected in the nav', async () => {
    await openSection('4.3')
    await title('Sick leave')
    expect(screen.getByRole('link', { name: /Back to Handbook/ })).toHaveAttribute(
      'href',
      '/handbook',
    )
    expect(screen.getByRole('link', { name: 'Handbook' })).toHaveAttribute('aria-current', 'page')
  })

  it('lists the addenda under "State rules", marking the one that applies to her', async () => {
    await openSection('4.3')
    await title('Sick leave')
    const block = screen.getByRole('region', { name: 'State rules' })
    const rows = within(block).getAllByRole('link')
    expect(rows.map((r) => r.getAttribute('href'))).toEqual([
      '/handbook/CA-4.3',
      '/handbook/CO-4.3',
    ])
    expect(within(rows[0]!).getByText('Applies to you')).toBeVisible()
    expect(within(rows[1]!).queryByText('Applies to you')).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Supplements' })).not.toBeInTheDocument()
  })

  it('shows the body, with no Sources and no cited passage', async () => {
    await openSection('4.3')
    await title('Sick leave')
    expect(screen.getByRole('heading', { level: 2, name: 'How much you receive' })).toBeVisible()
    expect(screen.getByText('The second paragraph of 4.3.')).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Sources' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Cited passage' })).not.toBeInTheDocument()
  })

  it('shows previous and next in handbook order', async () => {
    await openSection('4.3')
    await title('Sick leave')
    const nav = screen.getByRole('navigation', { name: 'Previous and next' })
    const [prev, next] = within(nav).getAllByRole('link')
    expect(prev).toHaveAttribute('href', '/handbook/4.2')
    expect(prev).toHaveTextContent('Previous')
    expect(prev).toHaveTextContent('4.2 Holidays')
    expect(next).toHaveAttribute('href', '/handbook/4.4')
    expect(next).toHaveTextContent('Next')
    expect(next).toHaveTextContent('4.4 Bereavement leave')
  })

  it('names the chapter in the navigator and marks the current section', async () => {
    await openSection('4.3')
    await title('Sick leave')
    const nav = await screen.findByRole('navigation', { name: 'Chapter 4 · Time off' })
    expect(within(nav).getAllByRole('link')).toHaveLength(5)
    expect(within(nav).getByRole('link', { name: /Sick leave/ })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('has no previous link on the first section and no next on the last', async () => {
    await openSection('1.1')
    await title('About this handbook')
    const nav = screen.getByRole('navigation', { name: 'Previous and next' })
    expect(within(nav).getAllByRole('link')).toHaveLength(1)
    expect(within(nav).getByRole('link')).toHaveTextContent('Next')
  })
})

describe('an addendum section (CA-4.3 as Priya)', () => {
  it('shows the addendum eyebrow, "Supplements", Sources, and the addendum navigator', async () => {
    await openSection('CA-4.3')
    await title('Sick leave')
    expect(screen.getByText('CA-4.3 · California addendum')).toBeVisible()
    expect(screen.getByText('Applies to you')).toBeVisible()
    const block = screen.getByRole('region', { name: 'Supplements' })
    expect(within(block).getByRole('link')).toHaveAttribute('href', '/handbook/4.3')
    expect(screen.queryByRole('region', { name: 'State rules' })).not.toBeInTheDocument()
    const sources = screen.getByRole('region', { name: 'Sources' })
    expect(within(sources).getByText(/California Labor Code §246/)).toBeVisible()
    const nav = await screen.findByRole('navigation', { name: 'California addendum' })
    expect(within(nav).getByRole('link', { name: /CA-4.3/ })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.queryByText(/This section is for/)).not.toBeInTheDocument()
  })

  it('crosses from one addendum into the next with its next link', async () => {
    await openSection('CA-5.1')
    await title('Family and medical leave')
    const nav = screen.getByRole('navigation', { name: 'Previous and next' })
    const next = within(nav).getAllByRole('link').at(-1)!
    expect(next).toHaveAttribute('href', '/handbook/CO-3.2')
  })
})

describe('a section that does not apply to the person (CA-4.3 as Mateo)', () => {
  it('shows the neutral note naming his location and state, linking to the company section', async () => {
    await openSection('CA-4.3', 'mateo')
    await title('Sick leave')
    expect(screen.getByText("Doesn't apply to you")).toBeVisible()
    const note = screen.getByRole('note')
    expect(note).toHaveTextContent(
      'This section is for California employees. You work at the Austin warehouse in Texas.',
    )
    const link = within(note).getByRole('link', {
      name: 'See what applies to you: §4.3 Sick leave',
    })
    expect(link).toHaveAttribute('href', '/handbook/4.3')
  })

  it('says the employment type is why, for a salaried person on an hourly section in her state', async () => {
    await openSection('CA-3.2', 'priya')
    await title('Overtime')
    expect(screen.getByRole('note')).toHaveTextContent(
      "This section is for hourly staff in California. You're salaried, at the Oakland store in California.",
    )
    expect(
      screen.getByRole('link', { name: 'See what applies to you: §3.2 Overtime' }),
    ).toHaveAttribute('href', '/handbook/3.2')
  })

  it('shows no note on a company section, which applies to everyone', async () => {
    await openSection('4.3', 'mateo')
    await title('Sick leave')
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })
})

const paragraph = (id: string, text: string) =>
  ({
    type: 'passage',
    id,
    kind: 'paragraph',
    inlines: [{ text, bold: false, italic: false, linkSectionId: null }],
  }) as const

describe('a cited passage (?passage=p2)', () => {
  it('highlights the passage, labeled "Cited passage", and moves focus to it', async () => {
    await openSection('CA-4.3', 'priya', '?passage=p2')
    await title('Sick leave')
    const cited = await screen.findByRole('region', { name: 'Cited passage' })
    expect(within(cited).getByText('The second paragraph of CA-4.3.')).toBeVisible()
    await waitFor(() => expect(cited).toHaveFocus())
  })

  it('scrolls the passage into view', async () => {
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
    await openSection('CA-4.3', 'priya', '?passage=p2')
    await screen.findByRole('region', { name: 'Cited passage' })
    expect(scroll).toHaveBeenCalled()
    scroll.mockRestore()
  })

  it('"Clear highlight" removes the passage from the URL without adding a history entry', async () => {
    const { router, user } = await openSection('CA-4.3', 'priya', '?passage=p2')
    await screen.findByRole('region', { name: 'Cited passage' })
    const before = window.history.length
    await user.click(screen.getByRole('button', { name: 'Clear highlight' }))
    expect(router.state.location.search).toBe('')
    expect(window.history.length).toBe(before)
    expect(screen.queryByRole('region', { name: 'Cited passage' })).not.toBeInTheDocument()
    expect(screen.getByText('The second paragraph of CA-4.3.')).toBeVisible()
  })

  it("doesn't take focus back when the section is fetched again with the same text", async () => {
    const { queryClient, api } = await openSection('CA-4.3', 'priya', '?passage=p2')
    const cited = await screen.findByRole('region', { name: 'Cited passage' })
    await waitFor(() => expect(cited).toHaveFocus())
    const link = screen.getByRole('link', { name: /Back to Handbook/ })
    link.focus()
    await act(() =>
      queryClient.invalidateQueries({ queryKey: getGetHandbookSectionQueryKey('CA-4.3') }),
    )
    await waitFor(() => expect(api.sectionRequests()).toEqual(['CA-4.3', 'CA-4.3']))
    expect(link).toHaveFocus()
  })

  it("doesn't take focus back when the fetch returns changed text either", async () => {
    const { queryClient } = await openSection('CA-4.3', 'priya', '?passage=p2')
    const cited = await screen.findByRole('region', { name: 'Cited passage' })
    await waitFor(() => expect(cited).toHaveFocus())
    // The handbook was edited: the same section now comes back with new blocks.
    const edited = handbookSection('priya', 'CA-4.3')!
    server.use(
      http.get(`${window.location.origin}/api/v1/handbook/sections/CA-4.3`, () =>
        HttpResponse.json({
          ...edited,
          blocks: [...edited.blocks.slice(0, 4), paragraph('p3', 'Edited.')],
        }),
      ),
    )
    const link = screen.getByRole('link', { name: /Back to Handbook/ })
    link.focus()
    await act(() =>
      queryClient.invalidateQueries({ queryKey: getGetHandbookSectionQueryKey('CA-4.3') }),
    )
    await waitFor(() => expect(screen.queryByText('Edited.')).not.toBeNull())
    expect(link).toHaveFocus()
  })

  it('focuses the passage again when it is cleared and then cited again', async () => {
    const { router, user } = await openSection('CA-4.3', 'priya', '?passage=p2')
    await screen.findByRole('region', { name: 'Cited passage' })
    await user.click(screen.getByRole('button', { name: 'Clear highlight' }))
    expect(screen.queryByRole('region', { name: 'Cited passage' })).not.toBeInTheDocument()
    screen.getByRole('link', { name: /Back to Handbook/ }).focus()
    await act(() => router.navigate('/handbook/CA-4.3?passage=p2'))
    const cited = await screen.findByRole('region', { name: 'Cited passage' })
    await waitFor(() => expect(cited).toHaveFocus())
  })

  it('moves focus again when the passage in the URL changes', async () => {
    const { router } = await openSection('CA-4.3', 'priya', '?passage=p2')
    await screen.findByRole('region', { name: 'Cited passage' })
    await act(() => router.navigate('/handbook/CA-4.3?passage=p3'))
    const cited = await screen.findByRole('region', { name: 'Cited passage' })
    expect(within(cited).getByText('The third paragraph of CA-4.3.')).toBeVisible()
    await waitFor(() => expect(cited).toHaveFocus())
  })
})

describe('loading', () => {
  it('keeps the back link, announces "Loading section", and shows the sheet and nav', async () => {
    installFakeApi('priya')
    const api = installFakeHandbook('priya')
    const release = api.holdSection('4.3')
    renderApp({ at: '/handbook/4.3' })
    expect(await screen.findByRole('link', { name: /Back to Handbook/ })).toBeVisible()
    await waitFor(() => expect(screen.getByText('Loading section')).toBeInTheDocument())
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Handbook' })).toBeVisible()
    release()
    await title('Sick leave')
  })
})

describe('a section that fails to load', () => {
  it('shows the "Something went wrong" page, not the missing-section page', async () => {
    installFakeApi('priya')
    installFakeHandbook('priya')
    server.use(
      http.get(`${window.location.origin}/api/v1/handbook/sections/4.3`, () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
          { status: 500 },
        ),
      ),
    )
    renderApp({ at: '/handbook/4.3' })
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Something went wrong on our side.' }),
    ).toBeVisible()
    expect(
      screen.queryByText("This section isn't in your handbook version."),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeVisible()
  })
})

describe('a section that is not in the version', () => {
  it('shows the missing-section page inside the shell, with a way back', async () => {
    await openSection('8.2')
    const heading = await title("This section isn't in your handbook version.")
    expect(heading).toHaveFocus()
    expect(
      await screen.findByText("There's no §8.2 in version 2026.10 of the Juniper Row handbook."),
    ).toBeVisible()
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Back to the handbook' })).toHaveAttribute(
      'href',
      '/handbook',
    )
  })

  it('words an addendum ID without a section sign', async () => {
    await openSection('ZZ-1.1')
    await title("This section isn't in your handbook version.")
    expect(
      await screen.findByText("There's no ZZ-1.1 in version 2026.10 of the Juniper Row handbook."),
    ).toBeVisible()
  })
})
