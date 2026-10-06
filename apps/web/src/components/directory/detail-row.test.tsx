import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Link } from 'react-router'
import { describe, expect, it } from 'vitest'
import { DetailRow } from './detail-row'

function inList(row: React.ReactNode) {
  return render(<dl>{row}</dl>)
}

describe('DetailRow', () => {
  it('pairs a label with a value, as a term and its description', () => {
    inList(<DetailRow label="Title" value="Visual Merchandiser" />)
    expect(screen.getByText('Title').tagName).toBe('DT')
    expect(screen.getByText('Visual Merchandiser').tagName).toBe('DD')
  })

  it('takes a link as its value, underlined', () => {
    render(
      <MemoryRouter>
        <dl>
          <DetailRow label="Manager">
            <Link to="/directory/marcus">Marcus Bell</Link>
          </DetailRow>
        </dl>
      </MemoryRouter>,
    )
    const link = screen.getByRole('link', { name: 'Marcus Bell' })
    expect(link).toHaveAttribute('href', '/directory/marcus')
    expect(link.closest('dd')).toHaveClass('[&_a]:underline')
  })

  it('shows a locked row as a lock and the reason, with no value', () => {
    const { container } = inList(
      <DetailRow label="Home address" locked reason="Visible to Leo and HR" />,
    )
    const dd = screen.getByText('Home address').nextElementSibling as HTMLElement
    expect(within(dd).getByText('Visible to Leo and HR')).toBeInTheDocument()
    expect(container.querySelector('svg.lucide-lock')).not.toBeNull()
    expect(dd).toHaveTextContent('Visible to Leo and HR. Value hidden.')
  })

  it('never renders a value or children on a locked row, even if one is passed', () => {
    const smuggled = { value: '12 Elm Street', children: 'Also 12 Elm Street' } as object
    const { container } = inList(
      <DetailRow label="Home address" locked reason="Visible to Leo and HR" {...smuggled} />,
    )
    expect(container).not.toHaveTextContent('12 Elm Street')
  })

  it('looks calm: muted, with no danger or warning color', () => {
    const { container } = inList(<DetailRow label="Phone" locked reason="Visible to Leo and HR" />)
    const locked = screen.getByText('Visible to Leo and HR')
    expect(locked).toHaveClass('text-ink-muted')
    expect(container.innerHTML).not.toMatch(/danger|warning|red-|amber/)
  })

  it('stacks its label over its value below 760 px', () => {
    inList(<DetailRow label="Title" value="x" />)
    expect(screen.getByText('Title').parentElement).toHaveClass('max-[760px]:grid-cols-1')
  })
})
