import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './dropdown-menu'

const FOCUS_RING = [
  'outline-none',
  'focus-visible:outline-2',
  'focus-visible:outline-solid',
  'focus-visible:-outline-offset-2',
  'focus-visible:outline-focus-ring',
]

function Example({
  onSignOut = () => {},
  onPick = () => {},
}: {
  onSignOut?: () => void
  onPick?: (value: string) => void
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger>View as</DropdownMenuTrigger>
      <DropdownMenuContent aria-label="View as">
        <DropdownMenuLabel>View as</DropdownMenuLabel>
        <DropdownMenuRadioGroup value="marcus" onValueChange={onPick}>
          <DropdownMenuRadioItem value="marcus">Marcus Bell</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="priya">Priya Nair</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onSignOut}>Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

describe('DropdownMenu', () => {
  it('opens from the keyboard into a menu whose actions are menuitems', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.tab()
    await user.keyboard('{Enter}')
    expect(await screen.findByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Sign out' })).toBeInTheDocument()
    expect(screen.getByRole('separator')).toBeInTheDocument()
  })

  it('makes radio items menuitemradio, with the current one checked', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.click(screen.getByRole('button', { name: 'View as' }))
    const current = await screen.findByRole('menuitemradio', { name: 'Marcus Bell' })
    expect(current).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('menuitemradio', { name: 'Priya Nair' })).toHaveAttribute(
      'aria-checked',
      'false',
    )
    expect(current).toHaveClass('data-[state=checked]:bg-primary-tint')
  })

  it('moves with the arrow keys and picks with Enter, then closes', async () => {
    const onSignOut = vi.fn<() => void>()
    const user = userEvent.setup()
    render(<Example onSignOut={onSignOut} />)
    await user.tab()
    await user.keyboard('{Enter}')
    await screen.findByRole('menu')
    await user.keyboard('{ArrowDown}{ArrowDown}{ArrowDown}')
    expect(screen.getByRole('menuitem', { name: 'Sign out' })).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(onSignOut).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('reports a radio pick', async () => {
    const onPick = vi.fn<(value: string) => void>()
    const user = userEvent.setup()
    render(<Example onPick={onPick} />)
    await user.click(screen.getByRole('button', { name: 'View as' }))
    await user.click(await screen.findByRole('menuitemradio', { name: 'Priya Nair' }))
    expect(onPick).toHaveBeenCalledWith('priya')
  })

  it('closes on Escape and returns focus to the trigger', async () => {
    const user = userEvent.setup()
    render(<Example />)
    const trigger = screen.getByRole('button', { name: 'View as' })
    await user.click(trigger)
    await screen.findByRole('menu')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('styles the menu and its items from the design', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.click(screen.getByRole('button', { name: 'View as' }))
    expect(await screen.findByRole('menu')).toHaveClass(
      'bg-popover',
      'border',
      'border-border',
      'rounded-md',
      'shadow-md',
    )
    expect(screen.getByRole('menuitem', { name: 'Sign out' })).toHaveClass(
      'min-h-9',
      'rounded-xs',
      'text-ui',
      'data-[highlighted]:bg-neutral-hover',
    )
  })

  it('shows keyboard focus on every row with the design’s inset ring', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.click(screen.getByRole('button', { name: 'View as' }))
    await screen.findByRole('menu')
    expect(screen.getByRole('menuitem', { name: 'Sign out' })).toHaveClass(...FOCUS_RING)
    expect(screen.getByRole('menuitemradio', { name: 'Marcus Bell' })).toHaveClass(...FOCUS_RING)
  })

  it('spaces rows 2 px apart', async () => {
    const user = userEvent.setup()
    render(<Example />)
    await user.click(screen.getByRole('button', { name: 'View as' }))
    expect(await screen.findByRole('menu')).toHaveClass('flex', 'flex-col', 'gap-0.5')
  })
})
