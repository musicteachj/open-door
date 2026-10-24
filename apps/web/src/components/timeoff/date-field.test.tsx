import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DateField } from './date-field'

describe('DateField', () => {
  it('shows the placeholder when empty, and is named by it', () => {
    render(<DateField onToggle={() => {}} />)
    const button = screen.getByRole('button', { name: 'Dates Pick a day or a range' })
    expect(button).toHaveTextContent('Pick a day or a range')
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })

  it('shows the short form and is named by the label and the full form', () => {
    render(<DateField start="2026-11-25" end="2026-11-27" onToggle={() => {}} controls="picker" />)
    const button = screen.getByRole('button', {
      name: 'Dates Wednesday, November 25 to Friday, November 27',
    })
    expect(button).toHaveTextContent('Wed, Nov 25 to Fri, Nov 27')
    expect(button).toHaveAttribute('aria-controls', 'picker')
  })

  it('shows one day as one date', () => {
    render(<DateField start="2026-10-30" onToggle={() => {}} />)
    const button = screen.getByRole('button', { name: 'Dates Friday, October 30' })
    expect(button).toHaveTextContent('Fri, Oct 30')
  })

  it('hides the visible short form from assistive technology, so the name is not read twice', () => {
    render(<DateField start="2026-10-30" onToggle={() => {}} />)
    expect(screen.getByText('Fri, Oct 30')).toHaveAttribute('aria-hidden', 'true')
  })

  it('reports it is open, with a chevron up in place of down', () => {
    const { rerender, container } = render(<DateField onToggle={() => {}} />)
    const closedIcons = [...container.querySelectorAll('svg')].map((svg) =>
      svg.getAttribute('class'),
    )
    rerender(<DateField open onToggle={() => {}} />)
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true')
    const openIcons = [...container.querySelectorAll('svg')].map((svg) => svg.getAttribute('class'))
    expect(openIcons[1]).not.toBe(closedIcons[1])
    expect(container.querySelectorAll('svg')).toHaveLength(2)
  })

  it('calls onToggle when pressed', async () => {
    const onToggle = vi.fn<() => void>()
    render(<DateField onToggle={onToggle} />)
    await userEvent.setup().click(screen.getByRole('button'))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('shows an error as an alert, outlines the button in danger, and describes it by the error', () => {
    render(<DateField error="Pick a day." onToggle={() => {}} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Pick a day.')
    const button = screen.getByRole('button')
    expect(button).toHaveClass('data-[invalid]:border-danger')
    expect(button).toHaveAttribute('data-invalid')
    expect(button).toHaveAccessibleDescription('Pick a day.')
  })

  it('is disabled when asked', () => {
    render(<DateField disabled onToggle={() => {}} />)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('mutes the placeholder', () => {
    render(<DateField onToggle={() => {}} />)
    const visible = screen
      .getAllByText('Pick a day or a range')
      .find((node) => node.hasAttribute('aria-hidden'))
    expect(visible).toHaveClass('text-ink-placeholder')
  })
})
