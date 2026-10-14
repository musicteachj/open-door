import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SourcesBlock } from './sources-block'

const sources = [
  'California Labor Code §246, read from dir.ca.gov on Oct 6, 2026.',
  'California Code of Regulations, title 2, §11042.',
]

describe('SourcesBlock', () => {
  it('has a Sources heading and one line per source', () => {
    render(<SourcesBlock sources={sources} />)
    expect(screen.getByRole('heading', { name: 'Sources' })).toBeInTheDocument()
    for (const s of sources) expect(screen.getByText(s)).toBeInTheDocument()
  })

  it('has no "Source:" prefix', () => {
    const { container } = render(<SourcesBlock sources={sources} />)
    expect(container.textContent).not.toMatch(/Source:/)
  })

  it('is a region named by its heading, and two blocks do not share an id', () => {
    const { container } = render(
      <>
        <SourcesBlock sources={sources} />
        <SourcesBlock sources={sources} />
      </>,
    )
    const ids = [...container.querySelectorAll('h2')].map((h) => h.id)
    expect(new Set(ids).size).toBe(2)
    expect(screen.getAllByRole('region', { name: 'Sources' })).toHaveLength(2)
  })

  it('shows a web address as its site and an ISO date as a friendly date', () => {
    render(
      <SourcesBlock
        sources={[
          'California Labor Code §246, read from https://www.dir.ca.gov/dlse/Paid_Sick_Leave.htm on 2026-10-07.',
          'DLSE posting (amended effective 1/1/2026) at https://www.dir.ca.gov/DLSE/Poster_(11_2014).pdf on 2026-10-07.',
          'Colorado HFWA, read from cdle.colorado.gov on 2026-10-07.',
        ]}
      />,
    )
    expect(
      screen.getByText('California Labor Code §246, read from dir.ca.gov on Oct 7, 2026.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('DLSE posting (amended effective 1/1/2026) at dir.ca.gov on Oct 7, 2026.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Colorado HFWA, read from cdle.colorado.gov on Oct 7, 2026.'),
    ).toBeInTheDocument()
  })

  it('renders nothing when there are no sources', () => {
    const { container } = render(<SourcesBlock sources={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
