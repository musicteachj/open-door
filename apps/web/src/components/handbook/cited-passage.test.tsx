import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CitedPassage } from './cited-passage'

describe('CitedPassage', () => {
  it('is a region labeled "Cited passage", with the quote icon', () => {
    const { container } = render(<CitedPassage>Earn one hour per 30 worked.</CitedPassage>)
    const region = screen.getByRole('region', { name: 'Cited passage' })
    expect(region).toHaveTextContent('Earn one hour per 30 worked.')
    const icon = container.querySelector('svg.lucide-quote')
    expect(icon).not.toBeNull()
    expect(icon).toHaveAttribute('aria-hidden', 'true')
    expect(icon).toHaveAttribute('aria-hidden', 'true')
  })

  it('has no Clear highlight button unless onClear is given', () => {
    render(<CitedPassage>Text</CitedPassage>)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('calls onClear from the Clear highlight button', async () => {
    const onClear = vi.fn<() => void>()
    render(<CitedPassage onClear={onClear}>Text</CitedPassage>)
    await userEvent.click(screen.getByRole('button', { name: 'Clear highlight' }))
    expect(onClear).toHaveBeenCalledTimes(1)
  })

  it('is focusable by script, not in the Tab order', () => {
    render(<CitedPassage>Text</CitedPassage>)
    expect(screen.getByRole('region')).toHaveAttribute('tabindex', '-1')
  })

  it('uses the compact size for the panel', () => {
    render(<CitedPassage compact>Text</CitedPassage>)
    expect(screen.getByRole('region')).toHaveAttribute('data-compact', 'true')
  })

  it('keeps the cinnamon bar as decoration on the marker token', () => {
    render(<CitedPassage>Text</CitedPassage>)
    expect(screen.getByRole('region').className).toContain('before:bg-marker')
  })
})
