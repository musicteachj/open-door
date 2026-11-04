// The rows are CSS grids, so the table is built from ARIA roles on divs: a real <tr> with
// display: grid loses its table semantics in some browsers.
/* oxlint-disable jsx-a11y/prefer-tag-over-role */
import { Lock } from 'lucide-react'
import type { ConsoleTurnOut } from '@/api/generated'
import { redactedFacts } from './labels'

const FLAGGED = 'Flagged by the safety check. Details are hidden to protect the person.'
// An abandoned turn was never judged, so it must not read as flagged.
const ABANDONED =
  'This turn didn’t finish, so its safety check result wasn’t kept. Details are hidden to protect the person.'

/**
 * A turn the console keeps no details of (.od-turns__flagged): plain text in a single cell, on the
 * confidential tint with screen 11's lock. Not a button, not focusable, no trace. It carries only
 * the date, the token counts, the cost, and the timings the row type holds.
 */
function RedactedRow({ turn }: { turn: ConsoleTurnOut }) {
  return (
    <div role="row" data-slot="redacted-row" data-abandoned={turn.abandoned || undefined}>
      <div
        role="cell"
        className="flex flex-col gap-1 border-b border-border-subtle bg-confidential-tint px-3 py-4"
      >
        <p className="m-0 flex items-center gap-2.5 text-body">
          <Lock aria-hidden="true" className="size-4 shrink-0 text-primary" />
          {turn.abandoned ? ABANDONED : FLAGGED}
        </p>
        <p className="m-0 ml-6.5 text-small text-ink-muted">{redactedFacts(turn)}</p>
      </div>
    </div>
  )
}

export { RedactedRow }
