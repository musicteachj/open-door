import { useRef } from 'react'
import type { BudgetBannerOut } from '@/api/generated'
import { BudgetBanner } from '@/components/assistant/budget-banner'
import { InlineError } from '@/components/feedback/inline-error'
import { TurnstileSlot } from '@/components/landing/turnstile-slot'
import { ShellBanner } from '@/features/shell/shell-banner'
import type { PageLink } from '@/lib/page-link'
import { sandboxStartError } from '@/lib/sandbox-copy'
import { useStartNewSandbox } from './use-start-new-sandbox'

/**
 * The budget banner across the top of the shell's sheet, with "Start a new sandbox" for the
 * sandbox kind and the error if starting one fails. The home and the conversation both show it.
 */
export function BudgetStop({
  banner,
  writeToHr = null,
}: {
  banner: BudgetBannerOut
  writeToHr?: PageLink | null
}) {
  const sandbox = useStartNewSandbox()
  const slot = useRef<HTMLDivElement>(null)
  const startNewSandbox = () => sandbox.startNewSandbox(slot.current)
  const failure = sandbox.failed ? sandboxStartError(sandbox.error) : null
  return (
    <ShellBanner>
      <BudgetBanner
        kind={banner.kind}
        message={banner.message}
        onStartNewSandbox={startNewSandbox}
        writeToHr={writeToHr}
      />
      <TurnstileSlot ref={slot} />
      {failure && (
        <InlineError
          message={failure.message}
          onRetry={failure.canRetry ? startNewSandbox : undefined}
        />
      )}
    </ShellBanner>
  )
}
