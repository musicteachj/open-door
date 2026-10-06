import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LandingSections } from './landing-sections'

const IDS = ['persona-card-default', 'persona-card-starting', 'persona-card-disabled']

describe('LandingSections', () => {
  it('has a heading with a stable id for every state', () => {
    const { container } = render(<LandingSections />)
    const missing = IDS.filter((id) => container.querySelector(`h3#${id}`) === null)
    expect(missing).toEqual([])
  })

  it('shows the starting card enabled and busy, and the disabled card disabled', () => {
    render(<LandingSections />)
    const busy = screen.getAllByRole('button').filter((b) => b.getAttribute('aria-busy') === 'true')
    expect(busy).toHaveLength(1)
    expect(busy[0]).toBeEnabled()
    expect(screen.getAllByRole('button').filter((b) => b.hasAttribute('disabled'))).toHaveLength(1)
  })
})
