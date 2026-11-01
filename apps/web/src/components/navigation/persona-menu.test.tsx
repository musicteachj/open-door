import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PersonaMenu, type PersonaOption } from './persona-menu'

const PERSONAS: PersonaOption[] = [
  { key: 'priya', name: 'Priya Raman', title: 'Visual Merchandiser' },
  { key: 'mateo', name: 'Mateo Cruz', title: 'Store Associate' },
  { key: 'marcus', name: 'Marcus Bell', title: 'Department Lead, Apparel' },
  { key: 'dana', name: 'Dana Ortiz', title: 'HR Business Partner' },
]

function setup(props: Partial<React.ComponentProps<typeof PersonaMenu>> = {}) {
  const onSwitch = vi.fn<(key: string) => void>()
  const onSignOut = vi.fn<() => void>()
  // Radix makes the page behind an open menu pointer-events: none, so a click outside skips the check.
  const user = userEvent.setup({ pointerEventsCheck: 0 })
  render(
    <PersonaMenu
      personas={PERSONAS}
      currentKey="priya"
      onSwitch={onSwitch}
      onSignOut={onSignOut}
      {...props}
    />,
  )
  const trigger = screen.getByRole('button')
  return { user, trigger, onSwitch, onSignOut }
}

async function open(user: ReturnType<typeof userEvent.setup>, trigger: HTMLElement) {
  await user.click(trigger)
  return screen.findByRole('menu')
}

describe('PersonaMenu', () => {
  it('has the current persona in its switcher', () => {
    setup({ currentKey: 'marcus' })
    expect(screen.getByRole('button', { name: /Switch persona/ })).toHaveAccessibleName(
      'Marcus Bell, Department Lead, Apparel. Current persona. Switch persona',
    )
  })

  it('is closed until the switcher is pressed', () => {
    setup()
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('opens with "View as", the four personas, the note, a separator, and Sign out', async () => {
    const { user, trigger } = setup()
    const menu = await open(user, trigger)
    expect(menu).toHaveAccessibleName('View as')
    expect(within(menu).getByText('View as')).toBeInTheDocument()
    const radios = within(menu).getAllByRole('menuitemradio')
    expect(radios.map((r) => r.textContent)).toEqual([
      expect.stringContaining('Priya Raman'),
      expect.stringContaining('Mateo Cruz'),
      expect.stringContaining('Marcus Bell'),
      expect.stringContaining('Dana Ortiz'),
    ])
    expect(radios[0]).toHaveTextContent('Visual Merchandiser')
    expect(within(menu).getByText('Switching starts a new conversation.')).toBeInTheDocument()
    expect(within(menu).getByRole('separator')).toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'Sign out' })).toBeInTheDocument()
  })

  it('describes the menu with the note, so menu-mode screen readers hear it', async () => {
    const { user, trigger } = setup()
    const menu = await open(user, trigger)
    expect(menu).toHaveAccessibleDescription('Switching starts a new conversation.')
  })

  it('checks only the current persona', async () => {
    const { user, trigger } = setup({ currentKey: 'marcus' })
    const menu = await open(user, trigger)
    const checked = within(menu)
      .getAllByRole('menuitemradio')
      .filter((r) => r.getAttribute('aria-checked') === 'true')
    expect(checked).toHaveLength(1)
    expect(checked[0]).toHaveTextContent('Marcus Bell')
  })

  it('lays each persona out in a row: avatar, then name above role, hidden initials', async () => {
    const { user, trigger } = setup()
    const menu = await open(user, trigger)
    const row = within(menu).getAllByRole('menuitemradio')[1]!
    const avatar = row.querySelector('[data-slot="avatar"]')!
    expect(avatar).toHaveAttribute('aria-hidden', 'true')
    expect(avatar).toHaveTextContent('MC')
    // The avatar and the text block share one flex row; the row never stacks them.
    const flexRow = avatar.parentElement!
    expect(flexRow).toHaveClass('flex', 'items-center')
    expect(flexRow).not.toHaveClass('flex-col')
    expect(flexRow).toContainElement(within(row).getByText('Mateo Cruz'))
  })

  it('starts focus on the checked persona', async () => {
    const { user, trigger } = setup({ currentKey: 'marcus' })
    await open(user, trigger)
    expect(screen.getByRole('menuitemradio', { name: /Marcus Bell/ })).toHaveFocus()
  })

  it('starts focus on the checked persona when opened from the keyboard', async () => {
    const { user, trigger } = setup({ currentKey: 'dana' })
    trigger.focus()
    await user.keyboard('{Enter}')
    await screen.findByRole('menu')
    expect(screen.getByRole('menuitemradio', { name: /Dana Ortiz/ })).toHaveFocus()
  })

  it('falls back to the first persona, with focus in the menu, for an unknown currentKey', async () => {
    const { user, trigger } = setup({ currentKey: 'nobody' })
    await open(user, trigger)
    // Radix focuses the menu itself on a pointer open; the first arrow key then reaches a row.
    expect(screen.getByRole('menu')).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitemradio', { name: /Priya Raman/ })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitemradio', { name: /Mateo Cruz/ })).toHaveFocus()
  })

  it('names no one, and checks no one, for an unknown currentKey', async () => {
    const { user, trigger, onSwitch } = setup({ currentKey: 'nobody' })
    expect(trigger).toHaveAccessibleName('Choose a persona. Switch persona')
    expect(trigger).toHaveTextContent('Choose a persona')
    for (const persona of PERSONAS) expect(trigger).not.toHaveTextContent(persona.name)
    await open(user, trigger)
    const checked = screen
      .getAllByRole('menuitemradio')
      .filter((r) => r.getAttribute('aria-checked') === 'true')
    expect(checked).toEqual([])
    await user.click(screen.getByRole('menuitemradio', { name: /Priya Raman/ }))
    expect(onSwitch).toHaveBeenCalledWith('priya')
  })

  it('moves with the arrow keys, wrapping at the ends', async () => {
    const { user, trigger } = setup({ currentKey: 'mateo' })
    await open(user, trigger)
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitemradio', { name: /Marcus Bell/ })).toHaveFocus()
    await user.keyboard('{ArrowUp}{ArrowUp}')
    expect(screen.getByRole('menuitemradio', { name: /Priya Raman/ })).toHaveFocus()
    await user.keyboard('{ArrowUp}')
    expect(screen.getByRole('menuitem', { name: 'Sign out' })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitemradio', { name: /Priya Raman/ })).toHaveFocus()
  })

  it('closes on Escape and returns focus to the switcher', async () => {
    const { user, trigger } = setup()
    await open(user, trigger)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('closes on a click outside, and returns focus to the switcher', async () => {
    const { user, trigger } = setup()
    await open(user, trigger)
    await user.click(document.body)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('closes without switching when the current persona is chosen', async () => {
    const { user, trigger, onSwitch, onSignOut } = setup()
    await open(user, trigger)
    await user.click(screen.getByRole('menuitemradio', { name: /Priya Raman/ }))
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(onSwitch).not.toHaveBeenCalled()
    expect(onSignOut).not.toHaveBeenCalled()
  })

  it('calls onSwitch with the key when another persona is chosen', async () => {
    const { user, trigger, onSwitch } = setup()
    await open(user, trigger)
    await user.click(screen.getByRole('menuitemradio', { name: /Marcus Bell/ }))
    expect(onSwitch).toHaveBeenCalledTimes(1)
    expect(onSwitch).toHaveBeenCalledWith('marcus')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('chooses with the keyboard too', async () => {
    const { user, trigger, onSwitch } = setup()
    await open(user, trigger)
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}')
    expect(onSwitch).toHaveBeenCalledWith('marcus')
  })

  it('calls onSignOut for Sign out, and not onSwitch', async () => {
    const { user, trigger, onSwitch, onSignOut } = setup()
    await open(user, trigger)
    await user.click(screen.getByRole('menuitem', { name: 'Sign out' }))
    expect(onSignOut).toHaveBeenCalledTimes(1)
    expect(onSwitch).not.toHaveBeenCalled()
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  describe('while a switch is pending (busyLabel)', () => {
    it('shows the busy label, and the switcher does not open the menu', async () => {
      const { user, trigger } = setup({ busyLabel: 'Switching to Marcus…' })
      expect(trigger).toHaveAccessibleName('Switching to Marcus…')
      expect(trigger).toHaveAttribute('aria-disabled', 'true')
      await user.click(trigger)
      expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    })

    it('treats an empty busyLabel as busy', async () => {
      const { user, trigger } = setup({ busyLabel: '' })
      expect(trigger).toHaveAttribute('aria-disabled', 'true')
      await user.click(trigger)
      expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    })

    it('does not open from the keyboard either', async () => {
      const { user, trigger } = setup({ busyLabel: 'Switching to Marcus…' })
      trigger.focus()
      await user.keyboard('{Enter}')
      await user.keyboard('{ArrowDown}')
      expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    })

    it('closes a menu that is open when the switch starts', async () => {
      const onSwitch = vi.fn<(key: string) => void>()
      const onSignOut = vi.fn<() => void>()
      const user = userEvent.setup()
      const { rerender } = render(
        <PersonaMenu
          personas={PERSONAS}
          currentKey="priya"
          onSwitch={onSwitch}
          onSignOut={onSignOut}
        />,
      )
      await user.click(screen.getByRole('button', { name: /Switch persona/ }))
      await screen.findByRole('menu')
      rerender(
        <PersonaMenu
          personas={PERSONAS}
          currentKey="priya"
          onSwitch={onSwitch}
          onSignOut={onSignOut}
          busyLabel="Switching to Marcus…"
        />,
      )
      expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    })
  })
})
