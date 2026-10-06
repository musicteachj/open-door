import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { SearchField } from './search-field'

function Controlled({
  initial = '',
  onChange = () => {},
}: {
  initial?: string
  onChange?: (value: string) => void
}) {
  const [value, setValue] = useState(initial)
  return (
    <SearchField
      value={value}
      onChange={(next) => {
        setValue(next)
        onChange(next)
      }}
    />
  )
}

describe('SearchField', () => {
  it('has the design’s placeholder and an accessible name', () => {
    render(<Controlled />)
    const input = screen.getByRole('searchbox', {
      name: 'Search the directory by name, title, or email',
    })
    expect(input).toHaveAttribute('placeholder', 'Search by name, title, or email')
  })

  it('takes a maxLength for the input, so the field can never hold more', () => {
    render(<SearchField value="" onChange={() => {}} maxLength={100} />)
    expect(screen.getByRole('searchbox')).toHaveAttribute('maxlength', '100')
  })

  it('is wrapped in a search landmark', () => {
    const { container } = render(<Controlled />)
    const landmark = container.querySelector('search')
    expect(landmark).not.toBeNull()
    expect(landmark).toContainElement(screen.getByRole('searchbox'))
  })

  it('shows "Clear search" only when there is text', () => {
    const { rerender } = render(<SearchField value="" onChange={() => {}} />)
    expect(screen.queryByRole('button', { name: 'Clear search' })).not.toBeInTheDocument()
    rerender(<SearchField value="Jord" onChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'Clear search' })).toBeInTheDocument()
  })

  it('reports what is typed', async () => {
    const onChange = vi.fn<(value: string) => void>()
    const user = userEvent.setup()
    render(<Controlled onChange={onChange} />)
    await user.type(screen.getByRole('searchbox'), 'ab')
    expect(onChange).toHaveBeenLastCalledWith('ab')
  })

  it('clears with onChange(""), and puts focus back in the field', async () => {
    const onChange = vi.fn<(value: string) => void>()
    const user = userEvent.setup()
    render(<Controlled initial="Jordn" onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: 'Clear search' }))
    expect(onChange).toHaveBeenCalledWith('')
    expect(screen.getByRole('searchbox')).toHaveValue('')
    expect(screen.getByRole('searchbox')).toHaveFocus()
    expect(screen.queryByRole('button', { name: 'Clear search' })).not.toBeInTheDocument()
  })

  it('clears with Escape while there is text, and does nothing when empty', async () => {
    const onChange = vi.fn<(value: string) => void>()
    const user = userEvent.setup()
    const { rerender } = render(<SearchField value="Jordn" onChange={onChange} />)
    await user.click(screen.getByRole('searchbox'))
    await user.keyboard('{Escape}')
    expect(onChange).toHaveBeenCalledWith('')
    onChange.mockClear()
    rerender(<SearchField value="" onChange={onChange} />)
    await user.keyboard('{Escape}')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('draws the clear button’s focus ring flush, as the design does', () => {
    render(<SearchField value="x" onChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'Clear search' })).toHaveClass(
      'focus-visible:outline-offset-0',
    )
  })

  it('wears the field’s classes and leaves room for the icon and the clear button', () => {
    render(<SearchField value="x" onChange={() => {}} />)
    expect(screen.getByRole('searchbox')).toHaveClass(
      'h-control',
      'border-input-border',
      'focus:shadow-focus-halo',
      'pl-9',
      'pr-10',
    )
  })
})
