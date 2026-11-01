import { screen, within } from '@testing-library/react'
import { renderToString } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { DirectoryTable } from './directory-table'

const items = [
  {
    id: 'a',
    name: 'Dana Whitfield',
    title: 'HR Lead',
    department: 'People',
    location: 'Denver HQ',
    to: '/directory/a',
  },
  {
    id: 'b',
    name: 'Priya Raman',
    title: 'Visual Merchandiser',
    department: 'Store Operations',
    location: 'Oakland store',
    to: '/directory/b',
  },
]

describe('DirectoryTable', () => {
  it('shows the column labels Name, Title, Department, and Location', () => {
    renderWithRouter(<DirectoryTable items={items} />)
    for (const label of ['Name', 'Title', 'Department', 'Location']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('hides the column labels from screen readers, since each row’s link name carries them', () => {
    renderWithRouter(<DirectoryTable items={items} />)
    expect(screen.getByText('Name').parentElement).toHaveAttribute('aria-hidden', 'true')
    expect(screen.queryByRole('columnheader')).not.toBeInTheDocument()
  })

  it('lists the people as one link each, in a labeled list', () => {
    renderWithRouter(<DirectoryTable items={items} />)
    const list = screen.getByRole('list', { name: 'People' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
    expect(within(list).getAllByRole('link')).toHaveLength(2)
    expect(
      within(list).getByRole('link', {
        name: 'Priya Raman, Visual Merchandiser, Store Operations, Oakland store',
      }),
    ).toHaveAttribute('href', '/directory/b')
  })

  it('marks only your own row', () => {
    renderWithRouter(<DirectoryTable items={items} youId="b" />)
    expect(screen.getAllByText('You')).toHaveLength(1)
    expect(screen.getByRole('link', { name: /Priya Raman, You/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Dana Whitfield/ })).not.toHaveAccessibleName(/, You, /)
  })

  it('while loading shows eight skeleton rows, keeps the labels, and says so politely', () => {
    const { container } = renderWithRouter(<DirectoryTable items={items} loading />)
    expect(container.querySelectorAll('[data-slot="skeleton-row"]')).toHaveLength(8)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Loading the directory')
    expect(container.querySelector('[aria-busy]')).toHaveAttribute('aria-busy', 'true')
  })

  it('keeps its status outside the busy region, mounted before and after loading', () => {
    const { container, rerender } = renderWithRouter(<DirectoryTable items={items} loading />)
    const status = screen.getByRole('status')
    expect(status.closest('[aria-busy]')).toBeNull()
    expect(status).toHaveTextContent('Loading the directory')
    rerender(
      <MemoryRouter>
        <DirectoryTable items={items} />
      </MemoryRouter>,
    )
    expect(container.contains(status)).toBe(true)
    expect(status).toBeEmptyDOMElement()
  })

  it('renders its status empty at first and fills it after mount, so the text arrives as a change', () => {
    const first = renderToString(
      <MemoryRouter>
        <DirectoryTable items={items} loading />
      </MemoryRouter>,
    )
    expect(first).toMatch(/<output[^>]*><\/output>/)
    expect(first).not.toContain('Loading the directory')
    renderWithRouter(<DirectoryTable items={items} loading />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading the directory')
  })

  it('gives the list an explicit role, which list-none would otherwise drop in Safari', () => {
    renderWithRouter(<DirectoryTable items={items} />)
    expect(screen.getByRole('list', { name: 'People' })).toHaveAttribute('role', 'list')
  })

  it('is not busy, and says nothing, once loaded', () => {
    const { container } = renderWithRouter(<DirectoryTable items={items} />)
    expect(container.querySelector('[aria-busy]')).toHaveAttribute('aria-busy', 'false')
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
    expect(container.querySelectorAll('[data-slot="skeleton-row"]')).toHaveLength(0)
  })

  it('renders no list at all with no one to show (the page shows the empty state)', () => {
    renderWithRouter(<DirectoryTable items={[]} />)
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('hides the column labels below 760 px', () => {
    renderWithRouter(<DirectoryTable items={items} />)
    expect(screen.getByText('Name').parentElement).toHaveClass('max-[760px]:hidden')
  })
})
