import { create } from 'zustand'
import { registerReset } from '@/lib/identity'

type ShellToastState = {
  message: string | null
  /** Who the message is about. The shell shows it only to that person. */
  personId: string | null
  /** The icon and color: a confirmation (the default) or a plain notice. */
  tone: 'success' | 'info'
  /** Changes with each message, so a second toast replaces the first rather than reusing it. */
  id: number
  show: (message: string, personId: string, tone?: 'success' | 'info') => void
  clear: () => void
}

/**
 * The shell's one toast. It lives outside React's tree because a persona switch remounts the
 * whole shell (everything identity-scoped sits under the reset key). A switch runs `signInAs`,
 * which resets, and only then calls `show`, so the new shell still finds its message. Any later
 * reset (another tab changes the person, the sandbox expires) clears it, and the shell also
 * checks the message is for the person it is showing, so a stale one is never shown to anyone else.
 */
export const useShellToast = create<ShellToastState>((set) => ({
  message: null,
  personId: null,
  tone: 'success',
  id: 0,
  show: (message, personId, tone = 'success') =>
    set((state) => ({ message, personId, tone, id: state.id + 1 })),
  clear: () => set({ message: null, personId: null }),
}))

registerReset(() => useShellToast.getState().clear())
