import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Input } from './input'
import { Textarea } from './textarea'

// jsdom computes no styles, so these check the classes that carry the design's states.
const FIELD_CLASSES = [
  'border',
  'border-input-border',
  'hover:border-input-border-hover',
  'focus:border-primary',
  'focus:shadow-focus-halo',
  'outline-none',
  'placeholder:text-ink-placeholder',
  'bg-surface-raised',
  'text-ink',
  'text-ui',
  'rounded-md',
  'aria-invalid:border-danger',
  'disabled:bg-disabled-bg',
  'disabled:text-disabled-fg',
]

describe('Input', () => {
  it('is a 40 px field with the design’s border, hover, and focus classes', () => {
    render(<Input aria-label="Name" />)
    const input = screen.getByRole('textbox', { name: 'Name' })
    expect(input).toHaveClass('h-control', ...FIELD_CLASSES)
  })

  it('types, and passes props through', async () => {
    render(<Input aria-label="Name" type="search" placeholder="Search" />)
    const input = screen.getByRole('searchbox')
    await userEvent.setup().type(input, 'Marcus')
    expect(input).toHaveValue('Marcus')
    expect(input).toHaveAttribute('placeholder', 'Search')
  })

  it('takes extra classes without losing the field’s own', () => {
    render(<Input aria-label="Name" className="w-60" />)
    expect(screen.getByRole('textbox')).toHaveClass('w-60', 'border-input-border')
  })

  it('shows its error state through aria-invalid', () => {
    render(<Input aria-label="Name" aria-invalid />)
    expect(screen.getByRole('textbox')).toBeInvalid()
  })
})

describe('Textarea', () => {
  it('shares the field classes and grows taller than a line', () => {
    render(<Textarea aria-label="Reason" />)
    const area = screen.getByRole('textbox', { name: 'Reason' })
    expect(area).toHaveClass('min-h-20', ...FIELD_CLASSES)
    expect(area).not.toHaveClass('h-control')
  })

  it('types', async () => {
    render(<Textarea aria-label="Reason" />)
    await userEvent.setup().type(screen.getByRole('textbox'), 'Family trip')
    expect(screen.getByRole('textbox')).toHaveValue('Family trip')
  })
})
