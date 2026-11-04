import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { TourMenuItems } from './tour-menu-items'

async function setup(props: Partial<React.ComponentProps<typeof TourMenuItems>> = {}) {
  const handlers = {
    onTake: vi.fn<() => void>(),
    onResume: vi.fn<() => void>(),
    onRestart: vi.fn<() => void>(),
  }
  const user = userEvent.setup()
  render(
    <DropdownMenu>
      <DropdownMenuTrigger>Open</DropdownMenuTrigger>
      <DropdownMenuContent>
        <TourMenuItems {...handlers} {...props} />
      </DropdownMenuContent>
    </DropdownMenu>,
  )
  await user.click(screen.getByRole('button', { name: 'Open' }))
  return { user, ...handlers }
}

describe('TourMenuItems', () => {
  it('offers only "Take the tour" when idle', async () => {
    const { user, onTake } = await setup()
    expect(screen.getAllByRole('menuitem')).toHaveLength(1)
    await user.click(screen.getByRole('menuitem', { name: 'Take the tour' }))
    expect(onTake).toHaveBeenCalledTimes(1)
  })

  describe('in progress', () => {
    it('offers Resume with the step under it, and Start over', async () => {
      await setup({ step: 5 })
      const items = screen.getAllByRole('menuitem')
      expect(items).toHaveLength(2)
      expect(items[0]).toHaveTextContent('Resume the tour')
      expect(items[0]).toHaveTextContent('Step 5 of 10')
      expect(items[1]).toHaveTextContent('Start the tour over')
      expect(screen.queryByRole('menuitem', { name: 'Take the tour' })).toBeNull()
    })

    it('names Resume from its visible text plus a hidden comma, not an aria-label', async () => {
      await setup({ step: 5 })
      const resume = screen.getAllByRole('menuitem')[0]!
      expect(resume).not.toHaveAttribute('aria-label')
      expect(resume).toHaveAccessibleName(/^Resume the tour,\s?Step 5 of 10$/)
      // The comma ends the first line's own span, so no layout gap can come before it.
      expect(resume.querySelector('.sr-only')!.parentElement).toHaveTextContent(
        /^Resume the tour,$/,
      )
    })

    it('uses the total it is given', async () => {
      await setup({ step: 2, total: 8 })
      expect(screen.getAllByRole('menuitem')[0]).toHaveTextContent('Step 2 of 8')
    })

    it('calls onResume and onRestart', async () => {
      const { user, onResume, onRestart } = await setup({ step: 5 })
      await user.click(screen.getByRole('menuitem', { name: /^Resume the tour/ }))
      expect(onResume).toHaveBeenCalledTimes(1)
      await user.click(screen.getByRole('button', { name: 'Open' }))
      await user.click(screen.getByRole('menuitem', { name: 'Start the tour over' }))
      expect(onRestart).toHaveBeenCalledTimes(1)
    })
  })
})
