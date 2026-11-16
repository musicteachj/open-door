import { BookOpen, Check, Users } from 'lucide-react'
import { Answer } from '@/components/assistant/answer'
import { AnswerViewerContext } from '@/components/assistant/answer-viewer'
import { conversationCopy } from '@/components/assistant/labels'
import { PERSONAS } from '@/features/personas/personas'
import { cn } from '@/lib/utils'
import type { WalkthroughExchange, WalkthroughSource, WalkthroughStep } from './types'

// Screen 16's transcript: the video's text alternative (WCAG 1.2.1), in the page as text, in step
// order. Each step is an article labeled by its title, with an id so it can be linked; each
// exchange is a description list row, the speaker beside the words. Answers carry the AI label;
// the HR panel's fixed text never does. Sources are plain text: the page has no session, so the
// handbook isn't reachable from here.

const AI_NAME = 'Open Door, the AI assistant'
const noMarker = () => null
const HR_PANEL = 'HR panel'
const HR_PANEL_NOTE = 'Fixed text written by a person, not the AI'

function Speaker({ exchange, firstName }: { exchange: WalkthroughExchange; firstName: string }) {
  if (exchange.speaker === 'ai') {
    return (
      <dt className="m-0 flex h-6 items-center gap-2">
        <span className="sr-only">{AI_NAME}</span>
        <span
          aria-hidden="true"
          className="inline-flex h-5 items-center rounded-xs border border-border-strong px-1.5 text-[11px]/4 font-semibold tracking-[0.03em] text-ink"
        >
          {conversationCopy.aiLabel}
        </span>
        <span aria-hidden="true" className="text-small text-ink-muted">
          {conversationCopy.assistantName}
        </span>
      </dt>
    )
  }
  if (exchange.speaker === 'hr-panel') {
    return (
      <dt className="m-0 flex flex-col gap-0.5">
        <span className="flex items-center gap-2 text-ui/6 font-semibold">
          <Users aria-hidden="true" className="size-4 shrink-0" />
          {HR_PANEL}
        </span>
        <span className="text-caption text-pretty text-ink-muted">{HR_PANEL_NOTE}</span>
      </dt>
    )
  }
  return <dt className="m-0 text-ui/6 font-semibold">{firstName}</dt>
}

function Sources({ sources }: { sources: readonly WalkthroughSource[] }) {
  return (
    <p className="m-0 flex flex-wrap items-center gap-x-2 gap-y-1 text-small">
      <span className="text-ink-muted">{sources.length > 1 ? 'Sources' : 'Source'}</span>
      {sources.map((source) => (
        <span key={source.id} className="inline-flex items-center gap-2">
          <BookOpen aria-hidden="true" className="size-3.5 shrink-0 text-ink-muted" />
          {`${source.id} · ${source.title}`}
        </span>
      ))}
    </p>
  )
}

function Exchange({
  exchange,
  firstName,
  first,
}: {
  exchange: WalkthroughExchange
  firstName: string
  first: boolean
}) {
  return (
    <div
      className={cn(
        'flex flex-col gap-1 p-4 sm:grid sm:grid-cols-[152px_minmax(0,1fr)] sm:gap-6 sm:px-6 sm:py-5',
        !first && 'border-t border-border-subtle',
        exchange.speaker === 'hr-panel' && 'bg-surface-sunken',
      )}
    >
      <Speaker exchange={exchange} firstName={firstName} />
      {exchange.speaker === 'ai' ? (
        <dd className="m-0 flex flex-col gap-3">
          {/* The app's own renderer, so lists and bold read as they did on screen. There are no
              markers, and the recording drops links: the page has no session to open them. */}
          <Answer text={exchange.text} citations={[]} renderMarker={noMarker} />
          {exchange.sources && exchange.sources.length > 0 && (
            <Sources sources={exchange.sources} />
          )}
        </dd>
      ) : (
        <dd className="m-0 text-body text-pretty">{exchange.text}</dd>
      )}
    </div>
  )
}

function TranscriptStep({
  step,
  number,
  count,
}: {
  step: WalkthroughStep
  number: number
  count: number
}) {
  const titleId = `step-${number}-title`
  const persona = PERSONAS.find((p) => p.key === step.persona)
  return (
    <article
      id={`step-${number}`}
      aria-labelledby={titleId}
      className="scroll-mt-6 border-t border-border pt-10 pb-12"
    >
      <p className="m-0 text-small text-ink-muted tabular-nums">{`Step ${number} of ${count}`}</p>
      <h3 id={titleId} className="m-0 mt-1 text-h2">
        {step.title}
      </h3>
      {persona && (
        <p data-slot="persona-line" className="m-0 mt-3 flex items-center gap-2.5 text-ui">
          <span
            data-slot="avatar"
            aria-hidden="true"
            className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary-tint text-[11px]/4 font-semibold"
          >
            {persona.initials}
          </span>
          <span>
            <span className="font-semibold">{persona.name}</span>
            <span className="text-ink-muted">{` · ${persona.title} · ${persona.location}`}</span>
          </span>
        </p>
      )}
      <p className="m-0 mt-5 text-[16px]/[26px] text-pretty">{step.words}</p>
      {step.exchanges.length > 0 && (
        <dl className="m-0 mt-6 overflow-hidden rounded-lg border border-border bg-surface-raised">
          {step.exchanges.map((exchange, at) => (
            <Exchange
              // The list never changes order: it is the recording's.
              // oxlint-disable-next-line react/no-array-index-key
              key={at}
              exchange={exchange}
              firstName={persona?.firstName ?? ''}
              first={at === 0}
            />
          ))}
        </dl>
      )}
      {step.note && (
        <p
          data-slot="step-note"
          className="m-0 mt-4 flex items-start gap-2 text-ui text-pretty text-ink-muted"
        >
          <Check aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          {step.note}
        </p>
      )}
    </article>
  )
}

function Transcript({
  steps,
  className,
}: {
  steps: readonly WalkthroughStep[]
  className?: string
}) {
  return (
    <section aria-labelledby="transcript-title" className={cn('max-w-190', className)}>
      <h2 id="transcript-title" className="m-0 mb-2 text-h2">
        Transcript
      </h2>
      {/* The page is public, so no answer links anywhere, whatever the recording kept. */}
      <AnswerViewerContext value="public">
        {steps.map((step, index) => (
          <TranscriptStep key={step.id} step={step} number={index + 1} count={steps.length} />
        ))}
      </AnswerViewerContext>
    </section>
  )
}

export { Transcript }
