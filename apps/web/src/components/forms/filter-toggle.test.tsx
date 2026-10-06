import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { FilterToggle } from './filter-toggle'

describe('FilterToggle', () => {
  it('is a button named "My team" with its count, off by default', () => {
    render(<FilterToggle count={44} pressed={false} onChange={() => {}} />)
    const toggle = screen.getByRole('button', { name: 'My team 44' })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    expect(toggle).toHaveTextContent('44')
  })

  it('reports the opposite of what it shows', async () => {
    const onChange = vi.fn<(pressed: boolean) => void>()
    const user = userEvent.setup()
    const { rerender } = render(<FilterToggle count={44} pressed={false} onChange={onChange} />)
    await user.click(screen.getByRole('button'))
    expect(onChange).toHaveBeenLastCalledWith(true)
    rerender(<FilterToggle count={44} pressed onChange={onChange} />)
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button'))
    expect(onChange).toHaveBeenLastCalledWith(false)
  })

  it('shows a check when on, never color alone, and is tinted', () => {
    const { container, rerender } = render(
      <FilterToggle count={3} pressed={false} onChange={() => {}} />,
    )
    expect(container.querySelector('svg.lucide-users')).not.toBeNull()
    rerender(<FilterToggle count={3} pressed onChange={() => {}} />)
    expect(container.querySelector('svg.lucide-check')).not.toBeNull()
    expect(screen.getByRole('button')).toHaveClass('aria-pressed:bg-primary-tint')
  })

  it('omits the count when there is none, and takes another label', () => {
    render(<FilterToggle label="Remote" pressed={false} onChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'Remote' })).toBeInTheDocument()
  })
})
