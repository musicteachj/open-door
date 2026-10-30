import type userEvent from '@testing-library/user-event'

/**
 * Radix selects the option a roving arrow key lands on only while the key is still down, and moves
 * focus a tick after the keydown. A browser's keyup comes later than that tick; user-event's comes
 * at once. So the key is held down, and let go after the focus has moved. A fixed one-tick wait
 * lets go too early on a loaded machine, so this waits until focus has moved (or half a second,
 * for a key that moves nothing, such as an arrow at the end of a list).
 */
export async function arrow(user: ReturnType<typeof userEvent.setup>, key: string) {
  const before = document.activeElement
  await user.keyboard(`{${key}>}`)
  const giveUpAt = Date.now() + 500
  while (document.activeElement === before && Date.now() < giveUpAt) {
    await new Promise((resolve) => setTimeout(resolve, 0))
  }
  await new Promise((resolve) => setTimeout(resolve, 0))
  await user.keyboard(`{/${key}}`)
}
