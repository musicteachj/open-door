import { useRef, useState, type ReactNode } from 'react'
import type { QueueItemOut, Status, TimelineEntryOut } from '@/api/generated'
import { CaseDetailHeader } from '@/components/cases/case-detail-header'
import { CaseList } from '@/components/cases/case-list'
import { CaseOwnNotice } from '@/components/cases/case-own-notice'
import { CasePersonCard } from '@/components/cases/case-person-card'
import { CaseQueueTable } from '@/components/cases/case-queue-table'
import { CaseStatusActions } from '@/components/cases/case-status-actions'
import { CaseStatusDialog } from '@/components/cases/case-status-dialog'
import { CaseSummaryBlock } from '@/components/cases/case-summary-block'
import { CaseTimeline } from '@/components/cases/case-timeline'
import { CaseWordsReveal, type WordsState } from '@/components/cases/case-words-reveal'
import { firstNameOf, type CaseBadge, type QueueFilterValue } from '@/components/cases/labels'
import type { SummaryState } from '@/components/cases/summary-state'
import { StatusBadge } from '@/components/timeoff/status-badge'
import { Button } from '@/components/ui/button'
import { Group, Section } from '../gallery-parts'
import {
  AALIYAH_CASE,
  AALIYAH_CLOSED,
  AALIYAH_ROW,
  CASE_ZONE,
  DANA_OWN_CASE,
  LUCIA_ROW,
  MEGAN_CASE,
  MY_CASES,
  PRIYA_CASE,
  PRIYA_FAILED,
  PRIYA_PENDING,
  QUEUE_FACTS,
  QUEUE_OPEN,
  timelineEntry,
  TODAY,
  TOMORROW,
  type DemoCase,
} from '../fixtures/cases'

// My cases, HR's queue, and a case's detail (screens 11 and 12): every state the frames draw. Each
// frame is live where it can be, so the keyboard and focus can be tried here: the queue's filter
// filters, the words open and close and add one timeline row on each opening, the status buttons
// open their dialogs, and confirming changes the status. A frozen state (the words loading or
// failed) holds still. No frame fetches anything: these components are given their data.

const noop = () => {}
const SAMPLE_READ = Date.parse('2026-10-26T16:53:00Z')
const SAMPLE_CHANGE = '2026-10-26T17:30:00Z'

type DetailDemoProps = {
  c: DemoCase
  summary?: SummaryState
  /** The words are shown when the frame starts. */
  startShown?: boolean
  /** The words have been read on an earlier view, so the actions start unlocked. */
  wordsRead?: boolean
  /** Holds the words in this state: its buttons do nothing. */
  frozenWords?: WordsState
}

/** A case's detail, composed the way the page will compose it (Stage 6), with state of its own. */
function DetailDemo({
  c,
  summary = 'written',
  startShown = false,
  wordsRead = false,
  frozenWords,
}: DetailDemoProps) {
  const first = firstNameOf(c.name)
  const [status, setStatus] = useState<Status>(c.status)
  const [changedAt, setChangedAt] = useState(c.statusChangedAt)
  const [words, setWords] = useState<WordsState>(startShown ? 'shown' : 'hidden')
  const [read, setRead] = useState(wordsRead || startShown)
  // A frame that starts with the words shown has already recorded that opening.
  const [entries, setEntries] = useState<TimelineEntryOut[]>(
    startShown
      ? [...c.entries, timelineEntry('text_read', new Date(SAMPLE_READ).toISOString())]
      : c.entries,
  )
  const [summaryState, setSummaryState] = useState(summary)
  const [dialog, setDialog] = useState<'review' | 'close' | null>(null)
  const reads = useRef(startShown ? 1 : 0)
  const startRef = useRef<HTMLButtonElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const returnTo = useRef<'start' | 'close' | 'heading'>('start')

  if (c.isOwn) {
    return (
      <Wide width={1080}>
        <div className="flex flex-col gap-6">
          <CaseDetailHeader {...headerProps(c, status, changedAt)} isOwn crisis={false} />
          <CaseOwnNotice />
        </div>
      </Wide>
    )
  }

  function show() {
    reads.current += 1
    setWords('shown')
    setRead(true)
    setEntries((all) => [
      ...all,
      timelineEntry(
        'text_read',
        new Date(SAMPLE_READ + (reads.current - 1) * 60_000).toISOString(),
      ),
    ])
  }

  function confirm() {
    const to: Status = dialog === 'review' ? 'in_review' : 'closed'
    setEntries((all) => [
      ...all,
      timelineEntry('status_changed', SAMPLE_CHANGE, { fromStatus: status, toStatus: to }),
    ])
    setStatus(to)
    setChangedAt(SAMPLE_CHANGE)
    if (to === 'closed') setWords('hidden')
    returnTo.current = to === 'closed' ? 'heading' : 'close'
    setDialog(null)
  }

  const shownWords = frozenWords ?? words
  return (
    <Wide width={1080}>
      <div className="flex flex-col gap-6">
        <CaseDetailHeader
          {...headerProps(c, status, changedAt)}
          isOwn={false}
          crisis={c.screening === 'crisis'}
          headingRef={headingRef}
        />
        <div className="grid grid-cols-[minmax(0,1fr)_360px] items-start gap-x-10 gap-y-6 max-[900px]:grid-cols-1">
          <div className="flex min-w-0 flex-col gap-6">
            <CasePersonCard
              name={c.name}
              title={c.title}
              department={c.department}
              location={c.location}
              email={c.email}
            />
            <CaseSummaryBlock
              state={summaryState}
              text={c.summaryText}
              writtenAt={c.summaryWrittenAt}
              model={c.model}
              timeZone={CASE_ZONE}
              onRetry={() => setSummaryState('pending')}
            />
            <CaseWordsReveal
              firstName={first}
              state={shownWords}
              words={c.words}
              onShow={frozenWords ? noop : show}
              onHide={frozenWords ? noop : () => setWords('hidden')}
            />
            <CaseStatusActions
              status={status}
              firstName={first}
              locked={!read}
              startButtonRef={startRef}
              closeButtonRef={closeRef}
              onStartReview={() => {
                returnTo.current = 'start'
                setDialog('review')
              }}
              onClose={() => {
                returnTo.current = 'close'
                setDialog('close')
              }}
            />
          </div>
          <CaseTimeline
            entries={entries}
            screening={c.screening}
            personName={c.name}
            timeZone={CASE_ZONE}
          />
        </div>
        <CaseStatusDialog
          open={dialog !== null}
          kind={dialog ?? 'review'}
          firstName={first}
          onOpenChange={(open) => !open && setDialog(null)}
          onConfirm={confirm}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            const target = { start: startRef, close: closeRef, heading: headingRef }[
              returnTo.current
            ]
            target.current?.focus()
          }}
        />
      </div>
    </Wide>
  )
}

function headerProps(c: DemoCase, status: Status, statusChangedAt: string) {
  return {
    category: c.category,
    status,
    sentAt: c.sentAt,
    statusChangedAt,
    replyBy: c.replyBy,
    timeZone: CASE_ZONE,
    today: TODAY,
  }
}

/** A queue whose rows filter as the server would: Open is new and in review. */
function QueueDemo({
  rows,
  initial = 'open',
  today = TODAY,
}: {
  rows: QueueItemOut[]
  initial?: QueueFilterValue
  today?: string
}) {
  const [filter, setFilter] = useState<QueueFilterValue>(initial)
  const shown = rows.filter((row) =>
    filter === 'all' ? true : filter === 'open' ? row.status !== 'closed' : row.status === filter,
  )
  return (
    <Wide width={1080}>
      <CaseQueueTable
        rows={shown}
        filter={filter}
        onFilterChange={setFilter}
        today={today}
        timeZone={CASE_ZONE}
      />
    </Wide>
  )
}

/** A dialog shown open from a button in its own state, so it can be scanned and tried. */
function DialogHost({ kind, label }: { kind: 'review' | 'close'; label: string }) {
  const [open, setOpen] = useState(false)
  const opener = useRef<HTMLButtonElement>(null)
  return (
    <>
      <Button ref={opener} variant="secondary" onClick={() => setOpen(true)}>
        {label}
      </Button>
      <CaseStatusDialog
        open={open}
        kind={kind}
        firstName="Priya"
        onOpenChange={setOpen}
        onConfirm={() => setOpen(false)}
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          opener.current?.focus()
        }}
      />
    </>
  )
}

const BADGES: CaseBadge[] = [
  'case-sent',
  'case-reviewing',
  'case-finished',
  'case-new',
  'case-in-review',
  'case-closed',
]

/**
 * The design draws these at a 1080 px (queue and detail) or 760 px (My cases) content width, wider
 * than the gallery's column. A frame is centered on the column and spills out on both sides, down
 * to the window's edge minus the gallery's padding, so its layout is the one the design draws.
 */
function Wide({ width, children }: { width: 760 | 1080; children: ReactNode }) {
  return (
    <div
      style={{ width: `min(${width}px, 100vw - 4rem)` }}
      className="relative left-1/2 shrink-0 -translate-x-1/2"
    >
      {children}
    </div>
  )
}

export function CasesHrSections() {
  return (
    <>
      <Group title="Cases: My cases">
        <Section id="case-list-empty" title="My cases, nothing sent yet">
          <Wide width={760}>
            <CaseList cases={[]} timeZone={CASE_ZONE} onOpenCase={noop} />
          </Wide>
        </Section>
        <Section id="case-list-rows" title="My cases, one case in each status">
          <Wide width={760}>
            <CaseList cases={MY_CASES} timeZone={CASE_ZONE} onOpenCase={noop} />
          </Wide>
        </Section>
        <Section id="case-badges" title="Case status badges: three for the person, three for HR">
          {BADGES.map((badge) => (
            <StatusBadge key={badge} status={badge} />
          ))}
        </Section>
      </Group>
      <Group title="Cases: HR's queue (live filter)">
        <Section id="case-queue-open" title="Queue, Open filter, Monday Oct 26">
          <QueueDemo rows={[...QUEUE_OPEN, LUCIA_ROW]} />
        </Section>
        <Section id="case-queue-closed" title="Queue, Closed filter">
          <QueueDemo rows={[...QUEUE_OPEN, LUCIA_ROW]} initial="closed" />
        </Section>
        <Section id="case-queue-empty" title="Queue, New filter with nothing in it">
          <QueueDemo rows={[AALIYAH_ROW, LUCIA_ROW]} initial="new" />
        </Section>
        <Section
          id="case-queue-facts"
          title="Queue, Tuesday Oct 27: overdue, due today, the crisis fact, and HR's own case"
        >
          <QueueDemo rows={QUEUE_FACTS} today={TOMORROW} />
        </Section>
      </Group>
      <Group title="Cases: HR's case detail (live)">
        <Section id="case-detail-new" title="Detail, new: words hidden, actions locked">
          <DetailDemo c={PRIYA_CASE} />
        </Section>
        <Section id="case-detail-revealed" title="Detail, words shown, actions enabled">
          <DetailDemo c={PRIYA_CASE} startShown />
        </Section>
        <Section id="case-detail-in-review" title="Detail, in review, words read before">
          <DetailDemo c={AALIYAH_CASE} wordsRead />
        </Section>
        <Section id="case-summary-pending" title="Detail, summary being written">
          <DetailDemo c={PRIYA_PENDING} summary="pending" />
        </Section>
        <Section id="case-summary-failed" title="Detail, summary failed">
          <DetailDemo c={PRIYA_FAILED} summary="failed" />
        </Section>
        <Section id="case-summary-crisis" title="Detail, crisis case with no summary">
          <DetailDemo c={MEGAN_CASE} summary="crisis" />
        </Section>
        <Section id="case-words-loading" title="Detail, words loading">
          <DetailDemo c={PRIYA_CASE} frozenWords="loading" />
        </Section>
        <Section id="case-words-failed" title="Detail, words failed to open">
          <DetailDemo c={PRIYA_CASE} frozenWords="failed" />
        </Section>
        <Section id="case-detail-closed" title="Detail, closed">
          <DetailDemo c={AALIYAH_CLOSED} wordsRead />
        </Section>
        <Section id="case-dialog-review" title="Start review dialog (opens from the button)">
          <DialogHost kind="review" label="Open the start review dialog" />
        </Section>
        <Section id="case-dialog-close" title="Close case dialog (opens from the button)">
          <DialogHost kind="close" label="Open the close case dialog" />
        </Section>
        <Section id="case-detail-own" title="Detail, HR's own case">
          <DetailDemo c={DANA_OWN_CASE} />
        </Section>
      </Group>
    </>
  )
}
