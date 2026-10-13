import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { californiaSickLeave, sectionSummary } from '@/test/handbook-fixtures'
import { renderWithRouter } from '@/test/render-with-router'
import { SectionGroup } from './section-group'
import { SectionRow } from './section-row'

describe('SectionGroup', () => {
  it('is a region named by its heading, which shows the number and title', () => {
    renderWithRouter(
      <SectionGroup id="ch-4" num="4" title="Time off">
        <SectionRow section={sectionSummary()} />
      </SectionGroup>,
    )
    const group = screen.getByRole('region', { name: 'Time off' })
    expect(within(group).getByRole('heading', { level: 2, name: 'Time off' })).toBeInTheDocument()
    expect(within(group).getByText('4')).toBeInTheDocument()
  })

  it('lists its rows', () => {
    renderWithRouter(
      <SectionGroup id="ch-4" num="4" title="Time off">
        <SectionRow section={sectionSummary()} />
        <SectionRow section={californiaSickLeave()} />
      </SectionGroup>,
    )
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getAllByRole('link')).toHaveLength(2)
  })

  it('shows a note beside the title for an addendum', () => {
    renderWithRouter(
      <SectionGroup
        id="add-ca"
        num="CA"
        title="California addendum"
        note="For California employees"
      >
        <SectionRow section={californiaSickLeave()} />
      </SectionGroup>,
    )
    expect(screen.getByText('For California employees')).toBeInTheDocument()
  })
})
