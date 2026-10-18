import { create } from 'zustand'

/**
 * What the page inside the shell tells the shell about itself. The conversation has its own
 * sandbox pill in its header, so while it shows the shell hides its own (the top bar's and the
 * rail's) and the rail's "At a glance" moves up and hides on a phone. The page sets it on mount
 * and clears it on unmount, so a reset (which unmounts the page) leaves nothing behind.
 */
type ShellLayoutState = {
  conversation: boolean
  setConversation: (conversation: boolean) => void
}

export const useShellLayout = create<ShellLayoutState>((set) => ({
  conversation: false,
  setConversation: (conversation) => set({ conversation }),
}))
