import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { SectionRef } from '@/api/generated'
import { renderWithRouter } from '@/test/render-with-router'
import { LinkBlock } from './link-block'

const california: SectionRef = {
  id: 'CA-4.3',
  title: 'Sick leave',
  groupName: 'California addendum',
  audienceLabel: 'California employees',
  appliesToMe: true,
}
const colorado: SectionRef = {
  id: 'CO-4.3',
  title: 'Sick leave',
  groupName: 'Colorado addendum',
  audienceLabel: 'Colorado employees',
  appliesToMe: false,
}
const company: SectionRef = {
  id: '4.3',
  title: 'Sick leave',
  groupName: 'Time off',
  audienceLabel: 'Everyone',
  appliesToMe: true,
}

describe('LinkBlock', () => {
  it('lists the state rules as "{group} · {id}", each row a link with a chevron', () => {
    const { container } = renderWithRouter(
      <LinkBlock
        variant="stateRules"
        note="California and Colorado add to this section."
        sections={[california, colorado]}
      />,
    )
    expect(screen.getByRole('heading', { name: 'State rules' })).toBeInTheDocument()
    expect(screen.getByText('California and Colorado add to this section.')).toBeInTheDocument()
    const links = screen.getAllByRole('link')
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '/handbook/CA-4.3',
      '/handbook/CO-4.3',
    ])
    expect(links[0]).toHaveTextContent('California addendum · CA-4.3')
    expect(links[1]).toHaveTextContent('Colorado addendum · CO-4.3')
    expect(container.querySelectorAll('a svg.lucide-chevron-right')).toHaveLength(2)
  })

  it('writes the name in ink and the id muted', () => {
    renderWithRouter(<LinkBlock variant="stateRules" sections={[california]} />)
    expect(screen.getByText('California addendum')).not.toHaveClass('text-ink-muted')
    expect(screen.getByText('· CA-4.3')).toHaveClass('text-ink-muted')
  })

  it('marks only the rows that apply to the person', () => {
    renderWithRouter(<LinkBlock variant="stateRules" sections={[california, colorado]} />)
    const [first, second] = screen.getAllByRole('link')
    expect(within(first).getByText('Applies to you')).toBeInTheDocument()
    expect(within(second).queryByText(/apply to you|Applies to you/)).not.toBeInTheDocument()
  })

  it('shows the Supplements row for an addendum, with no marker', () => {
    renderWithRouter(<LinkBlock variant="supplements" sections={[company]} />)
    expect(screen.getByRole('heading', { name: 'Supplements' })).toBeInTheDocument()
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/handbook/4.3')
    expect(link).toHaveTextContent('§4.3 Sick leave · Company handbook')
    expect(screen.queryByText('Applies to you')).not.toBeInTheDocument()
  })

  it('is a region named by its heading', () => {
    renderWithRouter(<LinkBlock variant="stateRules" sections={[california]} />)
    const region = screen.getByRole('region', { name: 'State rules' })
    expect(region.getAttribute('aria-label')).toBeNull()
    expect(region.getAttribute('aria-labelledby')).toBeTruthy()
  })

  it('renders nothing when there are no sections', () => {
    const { container } = renderWithRouter(<LinkBlock variant="stateRules" sections={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
