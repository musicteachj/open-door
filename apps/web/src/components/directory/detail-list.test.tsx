import { render, screen } from '@testing-library/react'
import { Lock } from 'lucide-react'
import { describe, expect, it } from 'vitest'
import { DetailRow } from './detail-row'
import { DetailList } from './detail-list'

describe('DetailList', () => {
  it('is a region named by its title, holding a description list', () => {
    const { container } = render(
      <DetailList title="Work details">
        <DetailRow label="Title" value="Visual Merchandiser" />
      </DetailList>,
    )
    expect(screen.getByRole('heading', { level: 2, name: 'Work details' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Work details' })).toBeInTheDocument()
    expect(container.querySelector('dl')).toContainElement(screen.getByText('Title'))
  })

  it('shows an optional note beside the title', () => {
    render(
      <DetailList title="Private details" note="Only Leo and HR can see these.">
        <DetailRow label="Phone" locked reason="Visible to Leo and HR" />
      </DetailList>,
    )
    expect(screen.getByText('Only Leo and HR can see these.')).toBeInTheDocument()
  })

  it('has no note, no audit note, and no icon unless given', () => {
    const { container } = render(
      <DetailList title="Work details">
        <DetailRow label="Title" value="x" />
      </DetailList>,
    )
    expect(container.querySelector('p')).toBeNull()
    expect(container.querySelector('svg')).toBeNull()
  })

  it('shows the audit note when values are visible', () => {
    render(
      <DetailList
        title="Private details"
        auditNote="Viewing private details is recorded in the audit log."
      >
        <DetailRow label="Phone" value="(510) 555-0175" />
      </DetailList>,
    )
    expect(
      screen.getByText('Viewing private details is recorded in the audit log.'),
    ).toBeInTheDocument()
  })

  it('shows its icon, hidden from screen readers', () => {
    const { container } = render(
      <DetailList title="Private details" icon={Lock}>
        <DetailRow label="Phone" value="x" />
      </DetailList>,
    )
    expect(container.querySelector('h2 ~ svg, svg')?.getAttribute('aria-hidden')).toBe('true')
  })
})
