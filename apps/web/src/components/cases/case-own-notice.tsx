import { Lock } from 'lucide-react'
import { cn } from '@/lib/utils'
import { detailCopy } from './labels'

/**
 * On HR's own case: the metadata is all there is. The case's words, summary, and timeline are not
 * for the person who opened it to act on, and HR has no My cases page to read it from.
 */
function CaseOwnNotice({ className }: { className?: string }) {
  return (
    <div
      data-slot="case-own-notice"
      className={cn(
        'flex max-w-[720px] items-center gap-3 rounded-lg border border-confidential-border bg-confidential-tint px-6 py-4 text-body',
        className,
      )}
    >
      <Lock aria-hidden="true" className="size-4 flex-none text-primary" />
      <p className="m-0">{detailCopy.ownCase}</p>
    </div>
  )
}

export { CaseOwnNotice }
