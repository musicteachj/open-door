import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { NavigationSections } from './navigation-sections'

// The browser tests address each state by its heading's id, so the ids are part of the contract.
const IDS = [
  'nav-item-default',
  'nav-item-current',
  'nav-item-count',
  'nav-item-count-current',
  'persona-switcher-closed',
  'persona-switcher-truncated',
  'persona-switcher-switching',
  'persona-menu-open',
]

describe('NavigationSections', () => {
  it('has a heading with a stable id for every state', () => {
    const { container } = renderWithRouter(<NavigationSections />)
    const missing = IDS.filter((id) => container.querySelector(`h3#${id}`) === null)
    expect(missing).toEqual([])
  })
})
