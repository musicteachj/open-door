import { useMe } from '@/app/useMe'
import { SandboxIndicator } from '@/components/status/sandbox-indicator'
import { formatTimeLeft } from '@/lib/time'
import { cn } from '@/lib/utils'
import { useNow } from './use-now'

/**
 * The sandbox pill for a page header's right slot, as the directory frames draw it. Below 760 px
 * the shell's top bar carries the indicator, so this one hides there to avoid showing two. The
 * conversation page sets `everyWidth`: it hides the shell's pills (the top bar's and the rail's)
 * and draws this one at every width, beside its "Start a new conversation" button.
 */
export function PageSandboxIndicator({ everyWidth = false }: { everyWidth?: boolean }) {
  const { data: me } = useMe()
  const now = useNow()
  if (!me) return null
  const timeLeft = formatTimeLeft(Date.parse(me.tenantExpiresAt) - now)
  return (
    <SandboxIndicator className={cn(!everyWidth && 'max-[760px]:hidden')}>
      Sandbox resets in {timeLeft}
    </SandboxIndicator>
  )
}
