import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { GlanceLink } from './glance-link'

const props = {
  value: '11.5',
  label: 'days PTO available',
  destination: 'Time off',
  to: '/time-off',
}

describe('GlanceLink', () => {
  it('is one link, named for the figure, the label, and the destination', () => {
    renderWithRouter(<GlanceLink {...props} />)
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAccessibleName('11.5 days PTO available. Open Time off')
    expect(links[0]).toHaveAttribute('href', '/time-off')
  })

  it('shows the figure, the label, and the destination inside that link', () => {
    renderWithRouter(<GlanceLink {...props} />)
    const link = screen.getByRole('link')
    expect(within(link).getByText('11.5')).toBeInTheDocument()
    expect(within(link).getByText('days PTO available')).toBeInTheDocument()
    expect(within(link).getByText('Time off')).toBeInTheDocument()
  })

  it('shows no marker by default', () => {
    renderWithRouter(<GlanceLink {...props} />)
    expect(screen.getByRole('link').querySelector('[data-slot="glance-marker"]')).toBeNull()
  })

  it('puts the marker beside the figure only, hidden from the name and the text', () => {
    renderWithRouter(<GlanceLink {...props} marker />)
    const link = screen.getByRole('link')
    const marker = link.querySelector('[data-slot="glance-marker"]')!
    expect(marker).toHaveAttribute('aria-hidden', 'true')
    expect(marker).toBeEmptyDOMElement()
    // It shares a row with the figure, and the caption is outside that row.
    expect(marker.parentElement).toContainElement(screen.getByText('11.5'))
    expect(marker.parentElement).not.toContainElement(screen.getByText('days PTO available'))
    // And the link's name is the same with it.
    expect(link).toHaveAccessibleName('11.5 days PTO available. Open Time off')
  })

  it('keeps the whole row one link, with the marker on', () => {
    renderWithRouter(<GlanceLink {...props} marker />)
    expect(screen.getAllByRole('link')).toHaveLength(1)
  })
})
