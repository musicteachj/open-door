import { CircleAlert, Phone, RotateCcw, Users } from 'lucide-react'
import { useEffect, useId, type ReactNode } from 'react'
import { Link } from 'react-router'
import { handbookPath } from '@/components/handbook/labels'
import { Button } from '@/components/ui/button'
import { announce } from '@/lib/announce'
import { cn } from '@/lib/utils'
import { linkifyEmergency, parseCrisisText } from './crisis-text'
import { Segments } from './crisis-segments'
import { APP_LINK } from './link-class'
import { HrContacts, type HrContact } from './hr-contacts'
import { conversationCopy } from './labels'

type EscalationKind = 'crisis' | 'sensitive' | 'unavailable'

type EscalationPanelProps = {
  kind: EscalationKind
  /** The stream's fixed text for this event, shown as written. It is never generated or reworded. */
  message: string
  /** The HR people from the directory. The shared inbox is added after them. */
  contacts: HrContact[]
  /** Shows "Try again" on the `unavailable` panel. */
  onTryAgain?: () => void
  /**
   * Announces the panel to a screen reader when it mounts. Pass `true` only for a panel that
   * arrives live in the stream. A panel restored from the history (a reload, or an earlier turn)
   * must stay silent: several on a page would speak over one another, and a crisis panel is
   * assertive. Defaults to false.
   */
  announceOnMount?: boolean
  className?: string
}

const BANDS: Record<EscalationKind, { header: string; icon: ReactNode; className: string }> = {
  sensitive: {
    header: conversationCopy.sensitiveHeader,
    icon: <Users aria-hidden="true" className="size-4.5 shrink-0" />,
    className: 'border-b border-border bg-surface-sunken text-ink',
  },
  // The only dark band in the product, for the one message that must not be skimmed past.
  crisis: {
    header: conversationCopy.crisisHeader,
    icon: <Phone aria-hidden="true" className="size-4.5 shrink-0" />,
    className: 'bg-ink text-on-primary',
  },
  // The only red: this one is an error.
  unavailable: {
    header: conversationCopy.unavailableHeader,
    icon: <CircleAlert aria-hidden="true" className="size-4.5 shrink-0 text-danger" />,
    className: 'border-b border-border bg-surface-sunken text-ink',
  },
}

/** The crisis text as paragraphs and a list, with the few fixed links. Its words are unchanged. */
function CrisisMessage({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-3 text-[16px]/[26px] text-ink">
      {parseCrisisText(text).map((block, index) =>
        block.kind === 'paragraph' ? (
          <p key={index} className="m-0 text-pretty whitespace-pre-line">
            <Segments segments={block.segments} />
          </p>
        ) : (
          <ul key={index} className="m-0 flex list-disc flex-col gap-2 pl-5.5">
            {block.items.map((item, itemIndex) => (
              <li key={itemIndex} className="text-pretty">
                <Segments segments={item} />
              </li>
            ))}
          </ul>
        ),
      )}
    </div>
  )
}

/**
 * The card for a turn a person handles, not the assistant: a crisis, a sensitive topic, or "can't
 * answer right now" (from the design's Conversation frames). It is a region labeled by its header,
 * with a header band, the event's fixed text, and the HR contacts. It is never styled like an
 * answer: no "AI" label, no sources, and no "Was this right?". Only the crisis text is turned into
 * a list with links. The sensitive panel ends with the link to the handbook on confidential cases.
 *
 * "Show your work" under a sensitive panel is not part of this card (the design draws it beneath):
 * the caller puts `AnswerFooter` with a `WorkTrace` after it. A region added to the page is a
 * landmark, not a live region, so the panel announces its arrival itself, once, by its header: a
 * crisis assertively, the others politely (`announce` keeps the live regions in the page for
 * good, so they are watched before their text changes). It does so only for `announceOnMount`,
 * which Stage 6 sets for a panel that arrives live. Focus stays where it was, in the composer.
 */
function EscalationPanel({
  kind,
  message,
  contacts,
  onTryAgain,
  announceOnMount = false,
  className,
}: EscalationPanelProps) {
  const headerId = useId()
  const band = BANDS[kind]
  const header = band.header
  useEffect(() => {
    if (announceOnMount) announce(header, kind === 'crisis' ? 'assertive' : 'polite')
    // Once, when the panel arrives. A later change of the flag or the header is not an arrival.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return (
    <section
      data-slot="escalation-panel"
      data-kind={kind}
      aria-labelledby={headerId}
      className={cn(
        'max-w-[680px] overflow-hidden rounded-xl border border-border-strong bg-surface-raised',
        className,
      )}
    >
      <div
        data-slot="escalation-band"
        className={cn('flex items-center gap-2.5 px-6 py-3', band.className)}
      >
        {band.icon}
        <h2 id={headerId} className="m-0 text-body/[22px] font-semibold">
          {band.header}
        </h2>
      </div>
      <div className="flex flex-col gap-4 px-6 pt-4.5 pb-3">
        {kind === 'crisis' ? (
          <CrisisMessage text={message} />
        ) : (
          <p className="m-0 text-[16px]/[26px] text-pretty whitespace-pre-line text-ink">
            {kind === 'unavailable' ? <Segments segments={linkifyEmergency(message)} /> : message}
          </p>
        )}
        {kind === 'unavailable' && onTryAgain && (
          <div>
            <Button variant="secondary" size="sm" onClick={onTryAgain}>
              <RotateCcw aria-hidden="true" className="size-3.5" />
              {conversationCopy.tryAgain}
            </Button>
          </div>
        )}
        <HrContacts contacts={contacts} />
        {kind === 'sensitive' && (
          <Link
            to={handbookPath('7.2')}
            className={cn(APP_LINK, 'inline-flex items-center gap-1.5 self-start text-ui')}
          >
            {conversationCopy.sensitiveLink}
          </Link>
        )}
      </div>
    </section>
  )
}

export { EscalationPanel }
export type { EscalationKind, EscalationPanelProps }
