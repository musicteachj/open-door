import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { arrow } from '@/test/arrow-key'
import { ChoiceGroup } from './choice-group'

const OPTIONS = [
  { value: 'full', label: 'Full day' },
  { value: 'half', label: 'Half day' },
]

function Controlled({ disabled = false, onChange }: { disabled?: boolean; onChange?: () => void }) {
  const [value, setValue] = useState('full')
  return (
    <>
      <ChoiceGroup
        label="How much"
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

describe('ChoiceGroup', () => {
  it('is a radiogroup named by its label', () => {
    render(<Controlled />)
    expect(screen.getByRole('radiogroup', { name: 'How much' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Full day' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Half day' })).not.toBeChecked()
  })

  it('has one tab stop, and the arrow keys move and select', async () => {
    const user = userEvent.setup()
    render(<Controlled />)
    await user.tab()
    expect(screen.getByRole('radio', { name: 'Full day' })).toHaveFocus()
    await arrow(user, 'ArrowDown')
    expect(screen.getByRole('radio', { name: 'Half day' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Half day' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'After' })).toHaveFocus()
  })

  it('selects on a click', async () => {
    const user = userEvent.setup()
    render(<Controlled />)
    await user.click(screen.getByRole('radio', { name: 'Half day' }))
    expect(screen.getByRole('radio', { name: 'Half day' })).toBeChecked()
  })

  it('draws a 16 px radio in each card, with a dot only in the selected one', () => {
    render(<Controlled />)
    const full = screen.getByRole('radio', { name: 'Full day' })
    const half = screen.getByRole('radio', { name: 'Half day' })
    expect(full.querySelector('[data-slot="choice-radio"]')).toHaveClass('size-4', 'rounded-full')
    expect(full.querySelector('[data-slot="choice-dot"]')).not.toBeNull()
    expect(half.querySelector('[data-slot="choice-dot"]')).toBeNull()
  })

  it('marks the selected card with a primary border and the primary tint', () => {
    render(<Controlled />)
    expect(screen.getByRole('radio', { name: 'Full day' })).toHaveClass(
      'enabled:data-[state=checked]:border-primary',
      'enabled:data-[state=checked]:bg-primary-tint',
    )
  })

  it('drops the primary border and tint when the selected card is disabled', () => {
    render(<Controlled disabled />)
    const selected = screen.getByRole('radio', { name: 'Full day' })
    expect(selected).toHaveClass(
      'enabled:data-[state=checked]:border-primary',
      'enabled:data-[state=checked]:bg-primary-tint',
      'disabled:border-disabled-bg',
      'disabled:text-disabled-fg',
    )
    expect(selected.className).not.toMatch(/(^|\s)data-\[state=checked\]:/)
    expect(selected.querySelector('[data-slot="choice-radio"]')).toHaveClass(
      'group-disabled:border-disabled-bg',
    )
    expect(selected.querySelector('[data-slot="choice-dot"]')).toHaveClass(
      'group-disabled:bg-disabled-fg',
    )
  })

  it('lights an unselected card on hover', () => {
    render(<Controlled />)
    expect(screen.getByRole('radio', { name: 'Half day' })).toHaveClass(
      'data-[state=unchecked]:enabled:hover:bg-surface-hover',
    )
  })

  it('locks every card when disabled', async () => {
    const onChange = vi.fn<() => void>()
    const user = userEvent.setup()
    render(<Controlled disabled onChange={onChange} />)
    expect(screen.getByRole('radio', { name: 'Full day' })).toBeDisabled()
    await user.click(screen.getByRole('radio', { name: 'Half day' }))
    expect(onChange).not.toHaveBeenCalled()
  })
})
