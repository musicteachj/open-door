import { create } from 'zustand'

/**
 * What the page inside the shell tells the shell about itself. The conversation has its own
 * sandbox pill in its header, so while it shows the shell hides its own (the top bar's and the
 * rail's) and the rail's "At a glance" moves up and hides on a phone. The page sets it on mount
 * and clears it on unmount, so a reset (which unmounts the page) leaves nothing behind.
 *
 * `stickyPanel` is for a page that docks something beside its content and keeps it in the window as
 * the page scrolls (the Time off page's request form). `position: sticky` stops working inside a
 * scroll container, and `overflow: hidden` makes the sheet one, so the shell clips with
 * `overflow: clip` while it is set.
 */
type ShellLayoutState = {
  conversation: boolean
  setConversation: (conversation: boolean) => void
  stickyPanel: boolean
  setStickyPanel: (stickyPanel: boolean) => void
}

export const useShellLayout = create<ShellLayoutState>((set) => ({
  conversation: false,
  setConversation: (conversation) => set({ conversation }),
  stickyPanel: false,
  setStickyPanel: (stickyPanel) => set({ stickyPanel }),
}))
