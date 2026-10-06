import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { CoreSections } from './core-sections'

// The browser tests address each state by its heading's id, so the ids are part of the contract.
const IDS = [
  'logo-default',
  'logo-customer',
  'page-header-title',
  'page-header-count',
  'page-header-back',
  'empty-state-action',
  'empty-state-message',
  'sandbox-indicator-default',
  'glance-link-default',
  'glance-link-marker',
  'glance-list-default',
]

describe('CoreSections', () => {
  it('has a heading with a stable id for every state', () => {
    const { container } = renderWithRouter(<CoreSections />)
    const missing = IDS.filter((id) => container.querySelector(`h3#${id}`) === null)
    expect(missing).toEqual([])
  })
})
