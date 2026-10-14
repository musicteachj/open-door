import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { HandbookSections } from './handbook-sections'

describe('HandbookSections', () => {
  it('has a heading with a stable id for every state, each unique', () => {
    const { container } = renderWithRouter(<HandbookSections />)
    const ids = [...container.querySelectorAll('section > h3[id]')].map((h) => h.id)
    expect(ids).toHaveLength(29)
    expect(ids.every((id) => id !== '')).toBe(true)
    expect(new Set(ids).size).toBe(29)
  })

  it('does not open a panel, and so does not move focus, on load', () => {
    const { container } = renderWithRouter(<HandbookSections />)
    expect(container.querySelector('aside[aria-label="Handbook passage"] h2')).toBeNull()
    expect(document.activeElement).toBe(document.body)
  })
})
