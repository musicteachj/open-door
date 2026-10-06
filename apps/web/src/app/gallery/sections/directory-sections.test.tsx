import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { DirectorySections } from './directory-sections'

const IDS = [
  'directory-table-default',
  'directory-table-loading',
  'directory-row-default',
  'directory-row-you',
  'skeleton-row-default',
  'detail-list-values',
  'detail-list-locked',
]

describe('DirectorySections', () => {
  it('has a heading with a stable id for every state', () => {
    const { container } = renderWithRouter(<DirectorySections />)
    expect(IDS.filter((id) => container.querySelector(`h3#${id}`) === null)).toEqual([])
  })

  it('tags one row in the table as yours, and locks every private row without a value', () => {
    const { container } = renderWithRouter(<DirectorySections />)
    expect(screen.getAllByRole('link', { name: /\(you\)$/ })).toHaveLength(2)
    const locked = container.querySelector('section[aria-labelledby]:has(svg.lucide-lock)')
    expect(locked).not.toBeNull()
    expect(screen.getAllByText('Visible to Leo and HR')).toHaveLength(4)
  })
})
