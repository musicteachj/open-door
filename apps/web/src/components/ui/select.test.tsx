import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './select'

const FOCUS_RING = [
  'outline-none',
  'focus-visible:outline-2',
  'focus-visible:outline-solid',
  'focus-visible:-outline-offset-2',
  'focus-visible:outline-focus-ring',
]

function Example({ onValueChange = () => {} }: { onValueChange?: (value: string) => void }) {
  return (
    <Select onValueChange={onValueChange}>
      <SelectTrigger aria-label="Location">
        <SelectValue placeholder="All locations" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="sf">San Francisco</SelectItem>
        <SelectItem value="denver">Denver</SelectItem>
        <SelectItem value="austin">Austin</SelectItem>
      </SelectContent>
    </Select>
  )
}

describe('Select', () => {
  it('shows its placeholder, and its trigger wears the field’s classes', () => {
    render(<Example />)
    const trigger = screen.getByRole('combobox', { name: 'Location' })
    expect(trigger).toHaveTextContent('All locations')
    expect(trigger).toHaveClass(
      'h-control',
      'rounded-md',
      'border-input-border',
      'hover:border-input-border-hover',
      'focus:border-primary',
      'focus:shadow-focus-halo',
      'outline-none',
      'aria-invalid:border-danger',
      'text-ui',
    )
  })

  it('opens with the keyboard and chooses with the arrow keys and Enter', async () => {
    const onValueChange = vi.fn<(value: string) => void>()
    const user = userEvent.setup()
    render(<Example onValueChange={onValueChange} />)
    await user.tab()
    await user.keyboard('{Enter}')
    expect(await screen.findByRole('listbox')).toBeInTheDocument()
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual([
      'San Francisco',
      'Denver',
      'Austin',
    ])
    await user.keyboard('{ArrowDown}{Enter}')
    expect(onValueChange).toHaveBeenCalledWith('denver')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(screen.getByRole('combobox')).toHaveTextContent('Denver')
    // Focus goes back to the trigger.
    expect(screen.getByRole('combobox')).toHaveFocus()
  })

  it('closes on Escape without choosing', async () => {
    const onValueChange = vi.fn<(value: string) => void>()
    const user = userEvent.setup()
    render(<Example onValueChange={onValueChange} />)
    await user.tab()
    await user.keyboard('{Enter}')
    await screen.findByRole('listbox')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(onValueChange).not.toHaveBeenCalled()
  })

  it('marks the chosen option and gives items the menu styling', async () => {
    const user = userEvent.setup()
    render(
      <Select defaultValue="denver">
        <SelectTrigger aria-label="Location">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="sf">San Francisco</SelectItem>
          <SelectItem value="denver">Denver</SelectItem>
        </SelectContent>
      </Select>,
    )
    await user.click(screen.getByRole('combobox'))
    const chosen = await screen.findByRole('option', { name: 'Denver' })
    expect(chosen).toHaveAttribute('aria-selected', 'true')
    expect(chosen).toHaveClass(
      'h-9',
      'rounded-xs',
      'text-ui',
      'data-[highlighted]:bg-neutral-hover',
    )
    expect(screen.getByRole('listbox').closest('[data-slot="select-content"]')).toHaveClass(
      'bg-popover',
      'border-border',
      'shadow-md',
    )
  })

  it('does not open when disabled', async () => {
    render(
      <Select disabled>
        <SelectTrigger aria-label="Location">
          <SelectValue placeholder="All" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="sf">San Francisco</SelectItem>
        </SelectContent>
      </Select>,
    )
    const trigger = screen.getByRole('combobox')
    expect(trigger).toBeDisabled()
    await userEvent.setup().click(trigger)
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('shows keyboard focus on an option with the design’s inset ring, at regular weight', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.click(screen.getByRole('combobox'))
    const option = await screen.findByRole('option', { name: 'Denver' })
    expect(option).toHaveClass(...FOCUS_RING, 'font-regular')
  })

  it('spaces options 2 px apart', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.click(screen.getByRole('combobox'))
    await screen.findByRole('listbox')
    expect(document.querySelector('[data-slot="select-viewport"]')).toHaveClass(
      'flex',
      'flex-col',
      'gap-0.5',
    )
  })
})
