import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BottomSheet, SheetTitle } from '@/components/ui/bottom-sheet'
import { stubMediaQuery } from '@/test/media-query'
import { TourEndCard } from './tour-end-card'

afterEach(() => vi.unstubAllGlobals())

function setup(props: Partial<React.ComponentProps<typeof TourEndCard>> = {}) {
  const onKeepExploring = vi.fn<() => void>()
  const onChoose = vi.fn<() => void>()
  render(
    <TourEndCard persona="Dana" onKeepExploring={onKeepExploring} onChoose={onChoose} {...props} />,
  )
  return { onKeepExploring, onChoose }
}

describe('TourEndCard', () => {
  it('is a non-modal dialog named by its heading, with the step count announced', () => {
    setup()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'false')
    expect(dialog).toHaveAccessibleName(/^Step 10 of 10:\s?That’s the tour$/)
    expect(screen.getByText('Step 10 of 10')).toHaveAttribute('aria-hidden', 'true')
  })

  it('moves focus to the heading on mount', () => {
    setup()
    const heading = screen.getByRole('heading', { level: 2 })
    expect(heading).toHaveFocus()
    expect(heading).toHaveAttribute('tabindex', '-1')
  })

  it('does not take focus when asked not to', () => {
    setup({ focusOnMount: false })
    expect(document.body).toHaveFocus()
  })

  it('says what the tour showed and how long the sandbox stays', () => {
    setup()
    expect(screen.getByText(/^You’ve seen answers that change by state/)).toBeInTheDocument()
    expect(
      screen.getByText('This sandbox stays for 24 hours, so keep exploring.'),
    ).toBeInTheDocument()
  })

  it('names the persona on the primary button, and calls each handler', async () => {
    const { onKeepExploring, onChoose } = setup({ persona: 'Dana' })
    await userEvent.click(screen.getByRole('button', { name: 'Keep exploring as Dana' }))
    await userEvent.click(screen.getByRole('button', { name: 'Choose who to be' }))
    expect(onKeepExploring).toHaveBeenCalledTimes(1)
    expect(onChoose).toHaveBeenCalledTimes(1)
  })

  it('is 520 px wide with no scrim or dimming', () => {
    setup()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveClass('w-130', 'rounded-xl')
    expect(dialog.className).not.toMatch(/scrim|backdrop/)
  })

  it('docks as a sheet at 640 px and below', () => {
    stubMediaQuery(true)
    setup()
    expect(screen.getByRole('dialog')).toHaveClass('rounded-t-xl', 'inset-x-0', 'bottom-0')
  })

  describe('Escape', () => {
    it('ends the tour through onLeave', async () => {
      const onLeave = vi.fn<() => void>()
      const { onKeepExploring } = setup({ onLeave })
      await userEvent.keyboard('{Escape}')
      expect(onLeave).toHaveBeenCalledTimes(1)
      expect(onKeepExploring).not.toHaveBeenCalled()
    })

    it('keeps exploring when no onLeave is given', async () => {
      const { onKeepExploring } = setup()
      await userEvent.keyboard('{Escape}')
      expect(onKeepExploring).toHaveBeenCalledTimes(1)
    })

    it('leaves it to an open menu or sheet', async () => {
      const onLeave = vi.fn<() => void>()
      setup({ onLeave })
      const onClose = vi.fn<() => void>()
      render(<div role="menu" aria-label="View as" />)
      await userEvent.keyboard('{Escape}')
      expect(onLeave).not.toHaveBeenCalled()
      render(
        <BottomSheet full onClose={onClose}>
          <SheetTitle>Trace</SheetTitle>
        </BottomSheet>,
      )
      await userEvent.keyboard('{Escape}')
      expect(onLeave).not.toHaveBeenCalled()
    })

    it('does not listen to the page when drawn in flow', async () => {
      const onLeave = vi.fn<() => void>()
      setup({ onLeave, inFlow: true })
      await userEvent.keyboard('{Escape}')
      expect(onLeave).not.toHaveBeenCalled()
    })
  })

  it('has no transition or animation', () => {
    setup()
    expect(screen.getByRole('dialog').outerHTML).not.toMatch(/transition-\[|animate-|duration-/)
  })
})
