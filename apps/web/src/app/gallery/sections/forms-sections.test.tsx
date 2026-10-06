import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FormsSections } from './forms-sections'

const IDS = [
  'search-field-empty',
  'search-field-typed',
  'filter-select-default',
  'filter-select-active',
  'filter-select-open',
  'filter-toggle-off',
  'filter-toggle-on',
]

describe('FormsSections', () => {
  it('has a heading with a stable id for every state', () => {
    const { container } = render(<FormsSections />)
    expect(IDS.filter((id) => container.querySelector(`h3#${id}`) === null)).toEqual([])
  })

  it('shows one empty and one typed search, one active filter of the open and active pair, and both toggles', () => {
    render(<FormsSections />)
    const searches = screen.getAllByRole('searchbox') as HTMLInputElement[]
    expect(searches.map((s) => s.value)).toEqual(['', 'Jordn'])
    expect(screen.getAllByRole('button', { name: 'Clear search' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { pressed: true })).toHaveLength(1)
    expect(screen.getAllByRole('button', { pressed: false })).toHaveLength(1)
    expect(screen.getAllByRole('combobox')).toHaveLength(3)
  })
})
