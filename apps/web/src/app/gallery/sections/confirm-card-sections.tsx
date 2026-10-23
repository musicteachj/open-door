import { useState, type ReactNode } from 'react'
import type { Card } from '@/api/generated'
import { ConfirmCard, type ConfirmCardProps } from '@/components/assistant/confirm-card'
import { Group, Section } from '../gallery-parts'
import {
  CARD_APPROVE,
  CARD_BOOK,
  CARD_CANCEL,
  CARD_CROSS_YEAR_SICK,
  CARD_DENY,
  CARD_HOLIDAY,
  CARD_SHORT_NOTICE,
  CARD_SICK,
  EXPIRES_AT,
  THIS_YEAR,
  TIME_ZONE,
} from '../fixtures/timeoff'

// The confirm card in every variant and state, each under a heading with a stable id: Priya Raman's
// bookings and cancellation, and Marcus Bell's decisions, as they appear in the 680 px assistant
// column. The cards call nothing: every button is a no-op, and the deny card's note is its own.

const TYPED_NOTE = 'Inventory runs November 9 and 10 this year. Could you move this a week later?'

function Frame({ children }: { children: ReactNode }) {
  return <div className="w-[680px] max-w-full">{children}</div>
}

function Demo({
  card,
  initialNote = '',
  ...rest
}: { card: Card; initialNote?: string } & Partial<Omit<ConfirmCardProps, 'card'>>) {
  const [note, setNote] = useState(initialNote)
  return (
    <Frame>
      <ConfirmCard
        card={card}
        status="pending"
        expiresAt={EXPIRES_AT}
        timeZone={TIME_ZONE}
        thisYear={THIS_YEAR}
        note={note}
        onNoteChange={setNote}
        {...rest}
      />
    </Frame>
  )
}

export function ConfirmCardSections() {
  return (
    <>
      <Group title="Confirm card: pending, every variant">
        <Section id="confirm-card-book-pending" title="Confirm card, book PTO">
          <Demo card={CARD_BOOK} />
        </Section>
        <Section id="confirm-card-holiday-pending" title="Confirm card, book PTO over a holiday">
          <Demo card={CARD_HOLIDAY} />
        </Section>
        <Section id="confirm-card-sick-pending" title="Confirm card, record sick time">
          <Demo card={CARD_SICK} />
        </Section>
        <Section id="confirm-card-approve-pending" title="Confirm card, approve a request">
          <Demo card={CARD_APPROVE} />
        </Section>
        <Section id="confirm-card-deny-pending" title="Confirm card, deny a request, with a note">
          <Demo card={CARD_DENY} initialNote={TYPED_NOTE} />
        </Section>
        <Section id="confirm-card-cancel-pending" title="Confirm card, cancel time off">
          <Demo card={CARD_CANCEL} />
        </Section>
        <Section id="confirm-card-short-notice-pending" title="Confirm card, short-notice warning">
          <Demo card={CARD_SHORT_NOTICE} />
        </Section>
        <Section
          id="confirm-card-cross-year-sick-pending"
          title="Confirm card, sick time across New Year (a left line for each year)"
        >
          <Demo card={CARD_CROSS_YEAR_SICK} />
        </Section>
      </Group>
      <Group title="Confirm card: in progress">
        <Section id="confirm-card-streaming" title="Confirm card, the answer is still streaming">
          <Demo card={CARD_BOOK} turnRunning />
        </Section>
        <Section id="confirm-card-confirming" title="Confirm card, confirming">
          <Demo card={CARD_DENY} initialNote={TYPED_NOTE} confirming />
        </Section>
      </Group>
      <Group title="Confirm card: executed">
        <Section id="confirm-card-book-executed" title="Confirm card, executed: book PTO">
          <Demo card={CARD_BOOK} status="executed" />
        </Section>
        <Section
          id="confirm-card-holiday-executed"
          title="Confirm card, executed: PTO over a holiday"
        >
          <Demo card={CARD_HOLIDAY} status="executed" />
        </Section>
        <Section id="confirm-card-sick-executed" title="Confirm card, executed: sick time">
          <Demo card={CARD_SICK} status="executed" />
        </Section>
        <Section id="confirm-card-approve-executed" title="Confirm card, executed: approve">
          <Demo card={CARD_APPROVE} status="executed" />
        </Section>
        <Section
          id="confirm-card-deny-executed-with-note"
          title="Confirm card, executed: deny with a note"
        >
          <Demo card={CARD_DENY} status="executed" deniedNote={TYPED_NOTE} />
        </Section>
        <Section id="confirm-card-deny-executed" title="Confirm card, executed: deny with no note">
          <Demo card={CARD_DENY} status="executed" />
        </Section>
        <Section id="confirm-card-cancel-executed" title="Confirm card, executed: cancel time off">
          <Demo card={CARD_CANCEL} status="executed" />
        </Section>
      </Group>
      <Group title="Confirm card: ended without a change">
        <Section id="confirm-card-failed" title="Confirm card, failed">
          <Demo
            card={CARD_BOOK}
            status="failed"
            failure={{
              code: 'overlaps',
              text: 'You already have time off on those days.',
              dates: ['2026-10-30'],
            }}
          />
        </Section>
        <Section id="confirm-card-dismissed" title="Confirm card, dismissed">
          <Demo card={CARD_BOOK} status="canceled" canceledReason="dismissed" />
        </Section>
        <Section id="confirm-card-replaced" title="Confirm card, replaced by a newer card">
          <Demo card={CARD_BOOK} status="canceled" canceledReason="replaced" />
        </Section>
        <Section id="confirm-card-expired" title="Confirm card, expired">
          <Demo card={CARD_BOOK} status="expired" />
        </Section>
      </Group>
    </>
  )
}
