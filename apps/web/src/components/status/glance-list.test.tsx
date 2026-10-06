import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithRouter } from '@/test/render-with-router'
import { GlanceList } from './glance-list'

const items = [
  {
    id: 'pto',
    value: '11.5',
    label: 'days PTO available',
    destination: 'Time off',
    to: '/time-off',
  },
  {
    id: 'pending',
    value: '1',
    label: 'request pending',
    destination: 'Approvals',
    to: '/approvals',
    marker: true,
  },
]

describe('GlanceList', () => {
  it('is a labeled region with one link per item', () => {
    renderWithRouter(<GlanceList items={items} />)
    expect(screen.getByRole('region', { name: 'At a glance' })).toBeInTheDocument()
    expect(screen.getAllByRole('link').map((a) => a.getAttribute('href'))).toEqual([
      '/time-off',
      '/approvals',
    ])
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('takes its own heading', () => {
    renderWithRouter(<GlanceList heading="This week" items={items} />)
    expect(screen.getByRole('region', { name: 'This week' })).toBeInTheDocument()
  })

  it('renders nothing when it has no items', () => {
    const { container } = renderWithRouter(<GlanceList items={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
