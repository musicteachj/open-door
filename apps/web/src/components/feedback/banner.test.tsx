import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Banner } from './banner'

const MESSAGE = "This sandbox resets in 2 h 50 min. Everything you've done here will be cleared."

describe('Banner', () => {
  it('is a polite status holding the message', () => {
    render(<Banner message={MESSAGE} />)
    expect(screen.getByRole('status')).toHaveTextContent(MESSAGE)
  })

  it('is plain content, not a live region, with live={false}', () => {
    render(<Banner message={MESSAGE} live={false} />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByText(MESSAGE)).toBeInTheDocument()
  })

  it('pairs the warning icon, in the warning color, with ink text', () => {
    render(<Banner message={MESSAGE} />)
    const status = screen.getByRole('status')
    const icon = status.querySelector('[data-slot="banner-icon"]')
    expect(icon).toHaveClass('text-warning')
    expect(icon).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getByText(MESSAGE)).toHaveClass('text-ink')
  })

  it('has a close button that says its scope, and calls onDismiss', async () => {
    const onDismiss = vi.fn<() => void>()
    render(<Banner message={MESSAGE} onDismiss={onDismiss} />)
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss for this session' }))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('takes another name for the close button', () => {
    render(<Banner message={MESSAGE} onDismiss={() => {}} dismissLabel="Close" />)
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument()
  })

  it('has no Dismiss button without onDismiss', () => {
    render(<Banner message={MESSAGE} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
