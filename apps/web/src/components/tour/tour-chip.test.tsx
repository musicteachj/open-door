import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TourChip } from './tour-chip'

describe('TourChip', () => {
  it('is named by its own text, and sends it when pressed', async () => {
    const onSend = vi.fn<(text: string) => void>()
    render(<TourChip text="How many sick days do I get?" onSend={onSend} />)
    await userEvent.click(screen.getByRole('button', { name: 'How many sick days do I get?' }))
    expect(onSend).toHaveBeenCalledTimes(1)
  })

  it('sends with the keyboard', async () => {
    const onSend = vi.fn<(text: string) => void>()
    render(<TourChip text="Book next Friday off." onSend={onSend} />)
    await userEvent.tab()
    await userEvent.keyboard('{Enter}')
    expect(onSend).toHaveBeenCalledTimes(1)
  })

  it('has a row at least 44 px tall with 14 px text, and an inset focus ring', () => {
    render(<TourChip text="Book next Friday off." />)
    const chip = screen.getByRole('button')
    expect(chip).toHaveClass('min-h-11', 'text-ui')
    expect(chip.className).toContain('-outline-offset-2')
  })

  describe('once sent', () => {
    function renderSent(onSend = vi.fn<(text: string) => void>()) {
      render(<TourChip text="How many sick days do I get?" sent onSend={onSend} />)
      return onSend
    }

    it('shows a check and "Sent", and its name starts with its text', () => {
      renderSent()
      const chip = screen.getByRole('button', { name: 'How many sick days do I get?, sent' })
      expect(chip).toHaveTextContent('How many sick days do I get?')
      expect(chip).toHaveTextContent('Sent')
      expect(chip.querySelector('svg')).not.toBeNull()
    })

    it('keeps the hidden ", sent" in the same inline wrapper as the text, so no space comes between', () => {
      renderSent()
      const suffix = screen.getByRole('button').querySelector('.sr-only')!
      expect(suffix.parentElement).toHaveTextContent(/^How many sick days do I get\?, sent$/)
    })

    it('is aria-disabled but still focusable', async () => {
      renderSent()
      const chip = screen.getByRole('button')
      expect(chip).toHaveAttribute('aria-disabled', 'true')
      expect(chip).not.toBeDisabled()
      await userEvent.tab()
      expect(chip).toHaveFocus()
    })

    it('does nothing when pressed', async () => {
      const onSend = renderSent()
      await userEvent.click(screen.getByRole('button'))
      await userEvent.keyboard('{Enter}')
      expect(onSend).not.toHaveBeenCalled()
    })

    it('reads in muted ink', () => {
      renderSent()
      expect(screen.getByRole('button')).toHaveClass('text-ink-muted')
    })
  })

  it('is not aria-disabled before it is sent', () => {
    render(<TourChip text="Book next Friday off." />)
    expect(screen.getByRole('button')).not.toHaveAttribute('aria-disabled', 'true')
  })
})
