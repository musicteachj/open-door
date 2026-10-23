import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ApprovalCard } from '@/components/approvals/approval-card'
import { CoverageLine } from '@/components/approvals/coverage-line'
import { DecisionDialog } from '@/components/approvals/decision-dialog'
import { decisionFacts } from '@/components/approvals/labels'
import { NoteField } from '@/components/approvals/note-field'
import { Button } from '@/components/ui/button'
import { Group, Section } from '../gallery-parts'
import { PRIYA_WAITING, TIME_ZONE, TODAY, VIKRAM, ZARA, ZARA_WAITING } from '../fixtures/timeoff'

// The approvals parts, each state under a heading with a stable id: Marcus Bell deciding Zara
// Bautista's and Priya Raman's waiting requests, on Tuesday, October 20, 2026. The dialogs start
// closed behind a button. Hover and focus are not drawn: the browser tests hover and focus the
// real elements.

const TYPED_NOTE = 'Inventory runs November 9 and 10 this year. Could you move this a week later?'
const NOTE_AT_LIMIT = 'a'.repeat(300)
const VIKRAM_COVERAGE = ZARA_WAITING.coverage ?? []

function Cards({ children }: { children: ReactNode }) {
  return <ul className="m-0 w-[928px] max-w-full list-none p-0">{children}</ul>
}

function Field({ initial = '', disabled = false }: { initial?: string; disabled?: boolean }) {
  const [value, setValue] = useState(initial)
  return (
    <div className="w-[432px] max-w-full">
      <NoteField firstName="Zara" value={value} onChange={setValue} disabled={disabled} />
    </div>
  )
}

/** A dialog behind a button, with the page's own state: the note, and a decision that takes a moment. */
function DialogDemo({
  kind,
  label,
  startDeciding = false,
  initialNote = '',
}: {
  kind: 'approve' | 'deny'
  label: string
  startDeciding?: boolean
  initialNote?: string
}) {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState(initialNote)
  const opener = useRef<HTMLButtonElement>(null)
  // The deciding frame closes itself, since nothing inside it can while the decision is running.
  useEffect(() => {
    if (!open || !startDeciding) return
    const timer = setTimeout(() => setOpen(false), 4000)
    return () => clearTimeout(timer)
  }, [open, startDeciding])
  return (
    <>
      <Button ref={opener} variant="secondary" onClick={() => setOpen(true)}>
        {label}
      </Button>
      <DecisionDialog
        open={open}
        onOpenChange={setOpen}
        kind={kind}
        person={ZARA}
        facts={decisionFacts(ZARA_WAITING)}
        note={note}
        onNoteChange={setNote}
        deciding={startDeciding}
        onConfirm={() => setOpen(false)}
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          opener.current?.focus()
        }}
      />
    </>
  )
}

export function ApprovalsSections() {
  return (
    <>
      <Group title="Approvals: approval card">
        <Section id="approval-card-default" title="Approval card, with team coverage">
          <Cards>
            <ApprovalCard
              request={ZARA_WAITING}
              today={TODAY}
              timeZone={TIME_ZONE}
              onApprove={() => {}}
              onDeny={() => {}}
            />
          </Cards>
        </Section>
        <Section id="approval-card-no-coverage" title="Approval card, no one else off">
          <Cards>
            <ApprovalCard
              request={PRIYA_WAITING}
              today={TODAY}
              timeZone={TIME_ZONE}
              onApprove={() => {}}
              onDeny={() => {}}
            />
          </Cards>
        </Section>
        <Section
          id="approval-card-conflict"
          title="Approval card, conflict: the request was canceled"
        >
          <Cards>
            <ApprovalCard
              request={ZARA_WAITING}
              today={TODAY}
              timeZone={TIME_ZONE}
              conflict="canceled"
            />
          </Cards>
        </Section>
        <Section
          id="approval-card-conflict-decided"
          title="Approval card, conflict: already approved"
        >
          <Cards>
            <ApprovalCard
              request={ZARA_WAITING}
              today={TODAY}
              timeZone={TIME_ZONE}
              conflict="approved"
            />
          </Cards>
        </Section>
        <Section id="approval-card-loading" title="Approval card, loading">
          <Cards>
            <ApprovalCard loading />
          </Cards>
        </Section>
      </Group>
      <Group title="Approvals: team coverage">
        <Section id="coverage-line-one-person" title="Coverage line, one colleague off">
          <CoverageLine coverage={VIKRAM_COVERAGE} multiDay />
        </Section>
        <Section id="coverage-line-none" title="Coverage line, no one else off">
          <CoverageLine coverage={[]} multiDay={false} />
        </Section>
        <Section id="coverage-line-range" title="Coverage line, no one else off, a range">
          <CoverageLine coverage={[]} multiDay />
        </Section>
        <Section id="coverage-line-part-of-day" title="Coverage line, a part of a day">
          <CoverageLine
            multiDay={false}
            coverage={[
              {
                person: { id: VIKRAM.id, name: VIKRAM.name },
                days: [{ date: '2026-11-10', type: 'pto', partialMinutes: 240 }],
              },
            ]}
          />
        </Section>
      </Group>
      <Group title="Approvals: note field">
        <Section id="note-field-empty" title="Note field, empty">
          <Field />
        </Section>
        <Section id="note-field-typed" title="Note field, typed (77 of 300)">
          <Field initial={TYPED_NOTE} />
        </Section>
        <Section id="note-field-at-limit" title="Note field, at the limit">
          <Field initial={NOTE_AT_LIMIT} />
        </Section>
        <Section id="note-field-disabled" title="Note field, disabled">
          <Field initial={TYPED_NOTE} disabled />
        </Section>
      </Group>
      <Group title="Approvals: decision dialogs">
        <Section id="decision-dialog-approve" title="Decision dialog, approve: press the button">
          <DialogDemo kind="approve" label="Open the approve dialog" />
        </Section>
        <Section
          id="decision-dialog-deny"
          title="Decision dialog, deny with a note: press the button"
        >
          <DialogDemo kind="deny" label="Open the deny dialog" initialNote={TYPED_NOTE} />
        </Section>
        <Section
          id="decision-dialog-deciding"
          title="Decision dialog, deciding (closes itself after 4 seconds): press the button"
        >
          <DialogDemo kind="approve" label="Open the deciding dialog" startDeciding />
        </Section>
      </Group>
    </>
  )
}
