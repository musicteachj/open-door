import { screen } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'

/** The persona switcher at the bottom of the sidebar, whoever is current or busy. */
export const personaSwitcher = () =>
  screen.getByRole('button', { name: /Switch persona$|^Switching|^Signing out/ })

/** Opens the persona menu and chooses a person, such as "Marcus". */
export async function switchViaMenu(user: UserEvent, firstName: string) {
  await user.click(screen.getByRole('button', { name: /Switch persona$/ }))
  await user.click(await screen.findByRole('menuitemradio', { name: new RegExp(`^${firstName} `) }))
}

/** Opens the persona menu and chooses Sign out. */
export async function signOutViaMenu(user: UserEvent) {
  await user.click(screen.getByRole('button', { name: /Switch persona$/ }))
  await user.click(await screen.findByRole('menuitem', { name: 'Sign out' }))
}
