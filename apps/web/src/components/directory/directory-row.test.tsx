import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { DirectoryRow } from './directory-row'

const leo = {
  name: 'Leo Nakamura',
  title: 'Sales Associate',
  department: 'Store Operations',
  location: 'Oakland store',
  to: '/directory/leo-id',
}

describe('DirectoryRow', () => {
  it('is one link to the profile, not a list item', () => {
    renderWithRouter(<DirectoryRow {...leo} />)
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAttribute('href', '/directory/leo-id')
    expect(links[0]).not.toHaveAttribute('role')
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('is named by the name, title, department, and location', () => {
    renderWithRouter(<DirectoryRow {...leo} />)
    expect(screen.getByRole('link')).toHaveAccessibleName(
      'Leo Nakamura, Sales Associate, Store Operations, Oakland store',
    )
  })

  it('shows each cell, with the initials hidden from screen readers', () => {
    renderWithRouter(<DirectoryRow {...leo} />)
    const link = screen.getByRole('link')
    for (const text of [leo.name, leo.title, leo.department, leo.location]) {
      expect(within(link).getByText(text)).toBeInTheDocument()
    }
    expect(within(link).getByText('LN').closest('[aria-hidden="true"]')).not.toBeNull()
    expect(within(link).queryByText('You')).not.toBeInTheDocument()
  })

  it('tags your own row "You", and the name says "You"', () => {
    renderWithRouter(<DirectoryRow {...leo} isYou />)
    const link = screen.getByRole('link')
    expect(within(link).getByText('You')).toBeInTheDocument()
    expect(link).toHaveAccessibleName(
      'Leo Nakamura, You, Sales Associate, Store Operations, Oakland store',
    )
  })

  it('takes its initials from the caller when given', () => {
    renderWithRouter(<DirectoryRow {...leo} initials="XY" />)
    expect(screen.getByText('XY')).toBeInTheDocument()
  })

  it('is a grid of five columns that stacks below 760 px, with the chevron kept top right', () => {
    renderWithRouter(<DirectoryRow {...leo} />)
    const link = screen.getByRole('link')
    expect(link).toHaveClass('max-[760px]:grid-cols-[minmax(0,1fr)_16px]', 'max-[760px]:h-auto')
    expect(link).toHaveClass('hover:bg-primary-tint', 'focus-visible:outline-focus-ring')
  })
})
