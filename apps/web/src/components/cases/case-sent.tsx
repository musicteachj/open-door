import { Lock } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import type { HrContactOut, SentLineOut } from '@/api/generated'
import { APP_LINK } from '@/components/assistant/link-class'
import { HrContacts } from '@/components/assistant/hr-contacts'
import { cn } from '@/lib/utils'
import type { PageLink } from '@/lib/page-link'
import { CaseSurface } from './surface'

type CaseSentBase = {
  /** `panel` is a band at the foot of the HR panel; `page` is a card on My cases. */
  variant: 'panel' | 'page'
  /**
   * The link after the line, or `null` for none. There is no default: HR has no My cases page, so
   * the page names the link it can reach ("View in My cases", "View your cases" for a person,
   * `MY_CASES_LINK` and `YOUR_CASES_LINK` in labels; a link to Cases for HR). On My cases itself
   * it is `null`, since a link would point at the page it is on.
   */
  link: PageLink | null
  className?: string
}

type CaseSentProps = CaseSentBase &
  (
    | {
        /** The quiet result after a case is sent. */
        state: 'sent'
        /** The API's sent line (`sentLine` on the send's answer and on a reloaded turn's `caseOpened`). */
        sentLine: SentLineOut
        /** The sent line takes focus when it appears. Off only for a frame that is shown, not sent. */
        focusOnMount?: boolean
      }
    | {
        /** The five-waiting line. */
        state: 'limit'
        /** The API's line (`waitingLimit` from `GET /cases/texts`). */
        limitLine: string
        /** The HR contacts, shown under the line on the page, where no panel is above it. */
        contacts?: HrContactOut[]
        /**
         * The line takes focus when it appears. The page sets it when the line replaces the form
         * (after a 409 case-waiting-limit), whose focused field has just gone.
         */
        focusOnMount?: boolean
      }
  )

/**
 * The quiet result after a case is sent, and the five-waiting limit (CaseSent.jsx). One line with
 * a lock, no apricot, no check, no celebration. A reload renders the same line. The sent line is a
 * status with `tabindex="-1"` and takes focus, so "View in My cases" is the next tab stop.
 *
 * For a crisis verdict the caller renders the crisis panel right after this, unchanged and never
 * shortened: `<EscalationPanel kind="crisis" message={sent.crisisText} ... />`.
 */
function CaseSent(props: CaseSentProps) {
  const { variant, link, className } = props
  const ref = useRef<HTMLOutputElement>(null)
  const sent = props.state === 'sent'
  // Decided when the line appears, so the tab stop does not vanish under focus when it is spent.
  const [takesFocus] = useState(() =>
    props.state === 'sent' ? (props.focusOnMount ?? true) : !!props.focusOnMount,
  )
  useEffect(() => {
    if (takesFocus) ref.current?.focus()
    // Once, when the line appears.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const text =
    props.state === 'limit'
      ? props.limitLine
      : variant === 'panel'
        ? `${props.sentLine.lead} ${props.sentLine.pointer}`
        : props.sentLine.lead
  return (
    <CaseSurface variant={variant} data-slot="case-sent" className={className}>
      <output
        ref={ref}
        tabIndex={takesFocus || sent ? -1 : undefined}
        className="flex items-start gap-3 text-ink outline-none"
      >
        <Lock aria-hidden="true" className="mt-0.5 size-5 flex-none text-primary" />
        <div
          className={cn(
            'flex min-w-0',
            // The limit line carries its link after it; the sent line puts the link under it.
            sent ? 'flex-col gap-2' : 'flex-wrap items-baseline gap-x-3 gap-y-1',
          )}
        >
          <p className="m-0 text-body text-pretty">{text}</p>
          {link && (
            <Link to={link.to} className={cn(APP_LINK, 'self-start text-ui')}>
              {link.label}
            </Link>
          )}
        </div>
      </output>
      {props.state === 'limit' && variant === 'page' && props.contacts && (
        <HrContacts contacts={props.contacts} className="mt-4" />
      )}
    </CaseSurface>
  )
}

export { CaseSent }
export type { CaseSentProps }
