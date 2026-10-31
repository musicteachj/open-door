import type { BudgetBannerOut } from '@/api/generated'
import { BudgetBanner } from '@/components/assistant/budget-banner'
import { InlineError } from '@/components/feedback/inline-error'
import { ShellBanner } from '@/features/shell/shell-banner'
import type { PageLink } from '@/lib/page-link'
import { SANDBOX_START_FAILED } from '@/lib/sandbox-copy'
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
  return (
    <ShellBanner>
      <BudgetBanner
        kind={banner.kind}
        message={banner.message}
        onStartNewSandbox={sandbox.startNewSandbox}
        writeToHr={writeToHr}
      />
      {sandbox.failed && (
        <InlineError message={SANDBOX_START_FAILED} onRetry={sandbox.startNewSandbox} />
      )}
    </ShellBanner>
  )
}
