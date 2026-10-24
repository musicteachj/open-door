import type userEvent from '@testing-library/user-event'

/**
 * Radix selects the option a roving arrow key lands on only while the key is still down, and moves
 * focus a tick after the keydown. A browser's keyup comes later than that tick; user-event's comes
 * at once. So the key is held down, and let go after the focus has moved.
 */
export async function arrow(user: ReturnType<typeof userEvent.setup>, key: string) {
  await user.keyboard(`{${key}>}`)
  await new Promise((resolve) => setTimeout(resolve, 0))
  await user.keyboard(`{/${key}}`)
}
