import { Info } from 'lucide-react'
import { AI_DISCLOSURE } from '@/lib/disclosure'

const NOTICE =
  "Juniper Row and everyone in it are fictional. This is a demo, not legal advice. Don't enter real personal information."

/** The footer of the pages outside the app: the landing and the recorded walkthrough. */
function PublicFooter() {
  return (
    <footer className="mx-auto mt-16 w-full max-w-292">
      <div className="flex flex-col gap-1 border-t border-border py-6 text-small text-ink-muted">
        <p className="m-0 flex items-center gap-2">
          <Info aria-hidden="true" className="size-4 shrink-0" />
          {AI_DISCLOSURE}
        </p>
        <p className="m-0 pl-6">{NOTICE}</p>
      </div>
    </footer>
  )
}

export { PublicFooter }
