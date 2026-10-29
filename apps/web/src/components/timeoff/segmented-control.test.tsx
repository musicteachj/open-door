import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { arrow } from '@/test/arrow-key'
import { SegmentedControl } from './segmented-control'

const OPTIONS = [
  { value: 'pto', label: 'PTO' },
  { value: 'sick', label: 'Sick time' },
]

function Controlled({ disabled = false, onChange }: { disabled?: boolean; onChange?: () => void }) {
  const [value, setValue] = useState('pto')
  return (
    <>
      <SegmentedControl
        label="Type"
        options={OPTIONS}
        value={value}
        onValueChange={(next) => {
          setValue(next)
          onChange?.()
        }}
        disabled={disabled}
      />
      <button>After</button>
    </>
  )
}

describe('SegmentedControl', () => {
  it('is a radiogroup named by its label, with a radio for each option', () => {
    render(<Controlled />)
    expect(screen.getByRole('radiogroup', { name: 'Type' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'PTO' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Sick time' })).not.toBeChecked()
  })

  it('has one tab stop: Tab lands on the selected option and the next Tab leaves', async () => {
    const user = userEvent.setup()
    render(<Controlled />)
    await user.tab()
    expect(screen.getByRole('radio', { name: 'PTO' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'After' })).toHaveFocus()
  })

  it('moves and selects with the arrow keys, wrapping around', async () => {
    const onChange = vi.fn<() => void>()
    const user = userEvent.setup()
    render(<Controlled onChange={onChange} />)
    await user.tab()
    await arrow(user, 'ArrowRight')
    expect(screen.getByRole('radio', { name: 'Sick time' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Sick time' })).toHaveFocus()
    expect(onChange).toHaveBeenCalledTimes(1)
    await arrow(user, 'ArrowRight')
    expect(screen.getByRole('radio', { name: 'PTO' })).toBeChecked()
    await arrow(user, 'ArrowLeft')
    expect(screen.getByRole('radio', { name: 'Sick time' })).toBeChecked()
  })

  it('selects on a click', async () => {
    const user = userEvent.setup()
    render(<Controlled />)
    await user.click(screen.getByRole('radio', { name: 'Sick time' }))
    expect(screen.getByRole('radio', { name: 'Sick time' })).toBeChecked()
  })

  it('marks the selected option with a check, so it is not color alone', () => {
    render(<Controlled />)
    expect(screen.getByRole('radio', { name: 'PTO' }).querySelector('svg')).toHaveAttribute(
      'aria-hidden',
      'true',
    )
    expect(screen.getByRole('radio', { name: 'Sick time' }).querySelector('svg')).toBeNull()
  })

  it('tints the selected option and sits on a sunken track', () => {
    render(<Controlled />)
    expect(screen.getByRole('radiogroup')).toHaveClass(
      'bg-surface-sunken',
      'border-border-strong',
      'rounded-md',
    )
    expect(screen.getByRole('radio', { name: 'PTO' })).toHaveClass(
      'data-[state=checked]:bg-primary-tint',
    )
  })

  it('locks every option when disabled', async () => {
    const onChange = vi.fn<() => void>()
    const user = userEvent.setup()
    render(<Controlled disabled onChange={onChange} />)
    expect(screen.getByRole('radio', { name: 'PTO' })).toBeDisabled()
    expect(screen.getByRole('radio', { name: 'Sick time' })).toBeDisabled()
    await user.click(screen.getByRole('radio', { name: 'Sick time' }))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('can sit inline: the label beside the options, one row, scrolling inside itself', () => {
    render(
      <SegmentedControl
        label="Show"
        options={[
          { value: 'a', label: 'Open' },
          { value: 'b', label: 'New' },
          { value: 'c', label: 'All' },
        ]}
        value="a"
        onValueChange={() => {}}
        layout="inline"
      />,
    )
    const group = screen.getByRole('radiogroup', { name: 'Show' })
    expect(group).toHaveClass('flex', 'overflow-x-auto')
    expect(group).not.toHaveClass('grid-cols-2')
    expect(screen.getByText('Show').parentElement).toHaveClass('flex-row')
  })
})
