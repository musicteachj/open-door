import { useContext, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ShellBannerSlot } from './shell-slots'

/** Renders `children` in the shell's banner slot. Renders nothing where there is no shell. */
export function ShellBanner({ children }: { children: ReactNode }) {
  const slot = useContext(ShellBannerSlot)
  return slot === null ? null : createPortal(children, slot)
}
