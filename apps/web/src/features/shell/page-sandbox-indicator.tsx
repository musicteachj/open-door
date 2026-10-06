import { useMe } from '@/app/useMe'
import { SandboxIndicator } from '@/components/status/sandbox-indicator'
import { formatTimeLeft } from '@/lib/time'
import { useNow } from './use-now'

/**
 * The sandbox pill for a page header's right slot, as the directory frames draw it. Below 760 px
 * the shell's top bar carries the indicator, so this one hides there to avoid showing two.
 */
export function PageSandboxIndicator() {
  const { data: me } = useMe()
  const now = useNow()
  if (!me) return null
  const timeLeft = formatTimeLeft(Date.parse(me.tenantExpiresAt) - now)
  return (
    <SandboxIndicator className="max-[760px]:hidden">Sandbox resets in {timeLeft}</SandboxIndicator>
  )
}
