import { Info } from 'lucide-react'
import { AI_DISCLOSURE } from '@/lib/disclosure'

const NOTICE =
  "Juniper Row and everyone in it are fictional. This is a demo, not legal advice. Don't enter real personal information."

// Approved 2026-11-19 (Phase 9a). The retention periods are what the deploy's backups and logs keep
// (docs/DATA-INVENTORY.md), and the four are the processors the app calls.
const RETENTION_NOTE =
  'Each sandbox is removed after 24 hours. Server backups keep copies for up to 7 days, and server logs, which include IP addresses, are kept for 14 days. Anthropic (AI answers), Voyage (handbook search), Cloudflare (the bot check), and AWS (hosting) process this data.'

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
        <p className="m-0 pl-6">{RETENTION_NOTE}</p>
      </div>
    </footer>
  )
}

export { PublicFooter }
