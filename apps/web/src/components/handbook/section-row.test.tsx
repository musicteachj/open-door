import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { californiaSickLeave, sectionSummary } from '@/test/handbook-fixtures'
import { renderWithRouter } from '@/test/render-with-router'
import { SectionRow } from './section-row'

describe('SectionRow', () => {
  it('is one link to the section', () => {
    renderWithRouter(<SectionRow section={sectionSummary()} />)
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAttribute('href', '/handbook/4.3')
  })

  it('is named by its number, title, audience, and date', () => {
    renderWithRouter(<SectionRow section={sectionSummary()} />)
    expect(screen.getByRole('link')).toHaveAccessibleName(
      '4.3 Sick leave. Applies to Everyone. Last updated Sep 12, 2026',
    )
  })

  it('shows the marker on a restricted section that covers me, and names it', () => {
    renderWithRouter(<SectionRow section={californiaSickLeave()} />)
    const link = screen.getByRole('link')
    expect(within(link).getByText('Applies to you')).toBeInTheDocument()
    expect(link).toHaveAccessibleName(
      'CA-4.3 Sick leave. Applies to California employees. Applies to you. Last updated Sep 12, 2026',
    )
    expect(link).toHaveAttribute('href', '/handbook/CA-4.3')
  })

  it('leaves an everyone row unmarked, even if it applies to me', () => {
    renderWithRouter(<SectionRow section={sectionSummary({ appliesToMe: true })} />)
    expect(screen.queryByText('Applies to you')).not.toBeInTheDocument()
  })

  it('leaves a restricted row unmarked when it does not cover me, and never shows "no"', () => {
    renderWithRouter(<SectionRow section={californiaSickLeave({ appliesToMe: false })} />)
    expect(screen.queryByText('Applies to you')).not.toBeInTheDocument()
    expect(screen.queryByText("Doesn't apply to you")).not.toBeInTheDocument()
  })

  it('decides from the audience lists, not the label text', () => {
    renderWithRouter(<SectionRow section={sectionSummary({ audienceLabel: 'Hourly staff' })} />)
    expect(screen.queryByText('Applies to you')).not.toBeInTheDocument()
  })

  it('shows the bare date, the audience text, and a hidden chevron', () => {
    const { container } = renderWithRouter(<SectionRow section={californiaSickLeave()} />)
    expect(screen.getByText('Sep 12, 2026')).toBeInTheDocument()
    expect(screen.getByText('California employees')).toBeInTheDocument()
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })

  it('keeps the section number visible when the row stacks on narrow screens', () => {
    renderWithRouter(<SectionRow section={californiaSickLeave()} />)
    const number = screen.getByText('CA-4.3')
    expect(number.className).not.toMatch(/hidden/)
    expect(screen.getByRole('link').className).toMatch(
      /@max-\[56rem\]:grid-cols-\[3.5rem_minmax\(0,1fr\)_16px\]/,
    )
  })

  it('marks the current row with aria-current="page"', () => {
    renderWithRouter(<SectionRow section={sectionSummary()} current />)
    expect(screen.getByRole('link')).toHaveAttribute('aria-current', 'page')
  })

  it('has no aria-current otherwise', () => {
    renderWithRouter(<SectionRow section={sectionSummary()} />)
    expect(screen.getByRole('link')).not.toHaveAttribute('aria-current')
  })
})
