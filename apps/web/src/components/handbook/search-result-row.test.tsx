import userEvent from '@testing-library/user-event'
import { screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { SearchResultOut } from '@/api/generated'
import { californiaSickLeave, sectionSummary } from '@/test/handbook-fixtures'
import { renderWithRouter } from '@/test/render-with-router'
import { SearchResultRow } from './search-result-row'

function result(overrides: Partial<SearchResultOut> = {}): SearchResultOut {
  return {
    section: californiaSickLeave({ id: 'CA-3.2', title: 'Overtime' }),
    passageId: 'p2',
    excerpt: [
      { text: 'Hourly staff are paid ', match: false },
      { text: 'overtime', match: true },
      { text: ' at 1.5 times their rate', match: false },
    ],
    ...overrides,
  }
}

describe('SearchResultRow', () => {
  it('runs onNavigate when the link is followed, before the page changes', async () => {
    const onNavigate = vi.fn<() => void>()
    renderWithRouter(<SearchResultRow result={result()} onNavigate={onNavigate} />)
    await userEvent.click(screen.getByRole('link'))
    expect(onNavigate).toHaveBeenCalledTimes(1)
  })

  it('is one link that deep-links to the passage', () => {
    renderWithRouter(<SearchResultRow result={result()} />)
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAttribute('href', '/handbook/CA-3.2?passage=p2')
  })

  it('is named "number title, source", and described by the excerpt and the meta line', () => {
    renderWithRouter(
      <SearchResultRow
        result={result({ section: sectionSummary({ id: '3.2', title: 'Overtime' }) })}
      />,
    )
    const link = screen.getByRole('link')
    expect(link).toHaveAccessibleName('3.2 Overtime, Company handbook')
    // jsdom doesn't lay out flex items, so the meta line's pieces run together here; a browser
    // puts a space between them.
    expect(link).toHaveAccessibleDescription(
      /^Hourly staff are paid overtime at 1\.5 times their rate Applies to:.*Everyone.*Applies to you.*Last updated Sep 12, 2026$/,
    )
  })

  it('encodes the passage ID in the link', () => {
    renderWithRouter(<SearchResultRow result={result({ passageId: 'p 2&x=1' })} />)
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      '/handbook/CA-3.2?passage=p%202%26x%3D1',
    )
  })

  it('shows the number, title, and source', () => {
    renderWithRouter(<SearchResultRow result={result()} />)
    const link = screen.getByRole('link')
    expect(within(link).getByText('CA-3.2')).toBeInTheDocument()
    expect(within(link).getByText('Overtime')).toBeInTheDocument()
    expect(within(link).getByText(/California addendum/)).toBeInTheDocument()
  })

  it('names a company section\'s source "Company handbook"', () => {
    renderWithRouter(<SearchResultRow result={result({ section: sectionSummary() })} />)
    expect(screen.getByText(/Company handbook/)).toBeInTheDocument()
  })

  it('wraps each match in <mark> and leaves the rest plain', () => {
    const { container } = renderWithRouter(<SearchResultRow result={result()} />)
    const marks = container.querySelectorAll('mark')
    expect(marks).toHaveLength(1)
    expect(marks[0]).toHaveTextContent('overtime')
    expect(marks[0].parentElement).toHaveTextContent(
      'Hourly staff are paid overtime at 1.5 times their rate',
    )
  })

  it('renders segment text as text, never as markup', () => {
    const { container } = renderWithRouter(
      <SearchResultRow
        result={result({
          excerpt: [
            { text: '<img src=x onerror=alert(1)> ', match: false },
            { text: '<b>pay</b>', match: true },
          ],
        })}
      />,
    )
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(container.querySelector('mark')).toHaveTextContent('<b>pay</b>')
  })

  it('shows the badge, the marker (yes), and the date', () => {
    renderWithRouter(<SearchResultRow result={result()} />)
    expect(screen.getByText('California employees')).toBeInTheDocument()
    expect(screen.getByText('Applies to you')).toBeInTheDocument()
    expect(screen.getByText('Last updated Sep 12, 2026')).toBeInTheDocument()
  })

  it('shows "Doesn\'t apply to you" when it does not cover me, and for everyone rows too', () => {
    const { unmount } = renderWithRouter(
      <SearchResultRow result={result({ section: californiaSickLeave({ appliesToMe: false }) })} />,
    )
    expect(screen.getByText("Doesn't apply to you")).toBeInTheDocument()
    unmount()
    renderWithRouter(<SearchResultRow result={result({ section: sectionSummary() })} />)
    expect(screen.getByText('Applies to you')).toBeInTheDocument()
  })

  it('has no arrow-key handling', async () => {
    const { user } = renderWithRouter(
      <ul>
        <SearchResultRow result={result()} />
        <SearchResultRow result={result({ passageId: 'p3' })} />
      </ul>,
    )
    await user.tab()
    const first = screen.getAllByRole('link')[0]
    expect(first).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(first).toHaveFocus()
  })
})
