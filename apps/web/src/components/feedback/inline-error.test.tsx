import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { InlineError } from './inline-error'

describe('InlineError', () => {
  it('is an alert with the message', () => {
    render(<InlineError message="Something went wrong sending that." />)
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong sending that.')
  })

  it('pairs an icon with the text, so color is never the only signal', () => {
    render(<InlineError message="Something went wrong sending that." />)
    const icon = screen.getByRole('alert').querySelector('[data-slot="inline-error-icon"]')
    expect(icon).toHaveAttribute('aria-hidden', 'true')
  })

  it('offers Retry only with a handler, and calls it', async () => {
    const onRetry = vi.fn<() => void>()
    const { rerender } = render(<InlineError message="Failed." />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    rerender(<InlineError message="Failed." onRetry={onRetry} />)
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
