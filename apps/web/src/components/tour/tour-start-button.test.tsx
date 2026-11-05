import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TourStartButton } from './tour-start-button'

describe('TourStartButton', () => {
  it('says "Take the 2-minute tour" and starts on a press', async () => {
    const onStart = vi.fn<() => void>()
    render(<TourStartButton onStart={onStart} />)
    const button = screen.getByRole('button', { name: 'Take the 2-minute tour' })
    expect(button).not.toHaveAttribute('aria-busy')
    await userEvent.click(button)
    expect(onStart).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
  })

  describe('starting', () => {
    function setup(onStart = vi.fn<() => void>()) {
      render(<TourStartButton starting persona="Priya Raman" onStart={onStart} />)
      return onStart
    }

    it('is busy, with a spinner and "Starting the tour…"', () => {
      setup()
      const button = screen.getByRole('button', { name: 'Starting the tour…' })
      expect(button).toHaveAttribute('aria-busy', 'true')
      expect(button.querySelector('[data-slot="button-spinner"]')).not.toBeNull()
    })

    it('swallows presses, so a double press starts once', async () => {
      const onStart = setup()
      await userEvent.click(screen.getByRole('button'))
      expect(onStart).not.toHaveBeenCalled()
    })

    it('announces the start politely', () => {
      setup()
      expect(screen.getByRole('status')).toHaveTextContent('Starting the tour as Priya Raman.')
    })
  })
})
