import { createContext } from 'react'

/**
 * A place in the shell's sheet, above the content and the rail, for a page's full-width banner (the
 * budget banner spans the rail too, as the design draws it). The shell provides the element, and a
 * page puts its banner there with `ShellBanner`. Null until the shell has mounted it.
 */
export const ShellBannerSlot = createContext<HTMLElement | null>(null)
