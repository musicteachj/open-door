import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { accessibleNameOf } from '@/test/accessible-name'
import { apiCitations, citation } from '@/test/assistant-fixtures'
import { stubMediaQuery } from '@/test/media-query'
import { AssistantMessage } from './assistant-message'
import { CitationMarker } from './citation-marker'
import * as linkSpans from './link-spans'
import { SourceChips } from './source-chip'
import * as sources from './sources'
import { numberBySection } from './sources'

type MessageProps = React.ComponentProps<typeof AssistantMessage>

// Loose on purpose: the tests set `errorMessage` on any status. The component's own type, which
// ties the message to `error`, is checked in the one test that builds an error without one.
type Props = Partial<Omit<MessageProps, 'status' | 'errorMessage'>> & {
  status?: MessageProps['status']
  errorMessage?: string
}

function renderMessage(props: Props = {}) {
  const messageProps = {
    status: 'complete',
    text: 'You get 5 days.',
    renderMarker: (c) => <button type="button">{`marker ${c.marker}`}</button>,
    ...props,
  } as MessageProps
  return render(
    <MemoryRouter>
      <AssistantMessage {...messageProps} />
    </MemoryRouter>,
  )
}

const STATUSES = ['streaming', 'complete', 'stopped', 'incomplete', 'error'] as const

const message = (container: HTMLElement) =>
  container.querySelector<HTMLElement>('[data-slot="assistant-message"]')!

describe('AssistantMessage: every state', () => {
  it.each(STATUSES)('starts with the AI label and "Open Door" when %s', (status) => {
    const { container } = renderMessage({ status, errorMessage: 'It broke.' })
    const label = within(message(container)).getByText('AI')
    expect(label).toBeInTheDocument()
    expect(within(message(container)).getByText('Open Door')).toBeInTheDocument()
    // The label comes before the answer, so it is the first thing read.
    expect(message(container).firstElementChild).toContainElement(label)
  })

  it.each(STATUSES)('shows the answer text when %s', (status) => {
    renderMessage({ status, errorMessage: 'It broke.' })
    expect(screen.getByText('You get 5 days.')).toBeInTheDocument()
  })

  it('is capped at 680 px with no bubble', () => {
    const { container } = renderMessage()
    expect(message(container)).toHaveClass('max-w-[680px]')
    expect(message(container).className).not.toMatch(/\bbg-|\bborder\b/)
  })
})

describe('AssistantMessage: streaming', () => {
  const answerLive = (container: HTMLElement) =>
    container.querySelector<HTMLElement>('[data-slot="answer-live"]')!

  it('holds the answer text back as busy while it streams, and not once it is done', () => {
    const { container, rerender } = renderMessage({ status: 'streaming', text: 'You get' })
    expect(answerLive(container)).toHaveAttribute('aria-busy', 'true')
    rerender(
      <MemoryRouter>
        <AssistantMessage status="complete" text="You get 5 days." renderMarker={() => null} />
      </MemoryRouter>,
    )
    expect(answerLive(container)).toHaveAttribute('aria-busy', 'false')
  })

  it('keeps the status line out of every busy element, so its steps are spoken', () => {
    const { container } = renderMessage({
      status: 'streaming',
      text: 'You get',
      steps: [{ id: 's1', text: 'Searching the handbook…', done: false }],
    })
    const line = container.querySelector('[data-slot="status-line"]')!
    expect(line).toBeInTheDocument()
    expect(line.closest('[aria-busy="true"]')).toBeNull()
    // The answer text is the busy part, and it is a sibling of the status line, not a parent.
    expect(answerLive(container)).toHaveAttribute('aria-busy', 'true')
    expect(answerLive(container)).not.toContainElement(line as HTMLElement)
  })

  it('says "Reading your question…" in the status region until the first step arrives', async () => {
    const { container, rerender } = renderMessage({ status: 'streaming', text: '', steps: [] })
    const line = container.querySelector('[data-slot="status-line"]')!
    expect(line).toHaveAttribute('role', 'status')
    // Empty when it mounts, so the live region is watching when the step is added.
    expect(line).toBeEmptyDOMElement()
    expect(await within(line as HTMLElement).findByRole('listitem')).toHaveTextContent(
      'Reading your question…',
    )
    expect(line.querySelector('[data-slot="status-spinner"]')).not.toBeNull()
    rerender(
      <MemoryRouter>
        <AssistantMessage
          status="streaming"
          text=""
          steps={[{ id: 'tool-1', text: 'Searching the handbook…', done: false }]}
          renderMarker={() => null}
        />
      </MemoryRouter>,
    )
    const items = within(line as HTMLElement).getAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual(['Searching the handbook…'])
  })

  it('says "Working on the answer…" when every step is done and no text has come', async () => {
    const done = [{ id: 'tool-1', text: 'Searched the handbook: sick leave', done: true }]
    const { container, rerender } = renderMessage({ status: 'streaming', text: '', steps: done })
    const line = container.querySelector<HTMLElement>('[data-slot="status-line"]')!
    const working = await within(line).findByText('Working on the answer…')
    expect(working.closest('li')!.querySelector('[data-slot="status-spinner"]')).not.toBeNull()
    rerender(
      <MemoryRouter>
        <AssistantMessage
          status="streaming"
          text="You get"
          steps={done}
          renderMarker={() => null}
        />
      </MemoryRouter>,
    )
    expect(within(line).queryByText('Working on the answer…')).toBeNull()
    expect(within(line).getAllByRole('listitem')).toHaveLength(1)
  })

  it('adds no step of its own while a step is still running', async () => {
    const running = [{ id: 'tool-1', text: 'Searching the handbook…', done: false }]
    const { container } = renderMessage({ status: 'streaming', text: '', steps: running })
    const line = container.querySelector<HTMLElement>('[data-slot="status-line"]')!
    await act(async () => {})
    expect(
      within(line)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual(['Searching the handbook…'])
  })

  it('adds "Reading your question…" a moment after streaming starts again in the same message', async () => {
    const view = (status: 'streaming' | 'complete', text: string) => (
      <MemoryRouter>
        <AssistantMessage status={status} text={text} steps={[]} renderMarker={() => null} />
      </MemoryRouter>
    )
    const { container, rerender } = render(view('streaming', ''))
    await screen.findByText('Reading your question…')
    rerender(view('complete', 'Done.'))
    // The live turn's message is reused for the next question.
    rerender(view('streaming', ''))
    const line = container.querySelector<HTMLElement>('[data-slot="status-line"]')!
    expect(line).toBeEmptyDOMElement()
    expect(await within(line).findByText('Reading your question…')).toBeInTheDocument()
  })

  it('shows no "Reading your question…" once the message is no longer streaming', () => {
    renderMessage({ status: 'stopped', text: '', steps: [] })
    expect(screen.queryByText('Reading your question…')).toBeNull()
  })

  it('says "Still working on it…" after 8 seconds with no answer text, and not before', () => {
    vi.useFakeTimers()
    try {
      renderMessage({ status: 'streaming', text: '', steps: [] })
      act(() => vi.advanceTimersByTime(7900))
      expect(screen.queryByText('Still working on it…')).toBeNull()
      act(() => vi.advanceTimersByTime(200))
      expect(screen.getByText('Still working on it…')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('counts a new 8 seconds after text is taken back', () => {
    vi.useFakeTimers()
    try {
      const view = (text: string) => (
        <MemoryRouter>
          <AssistantMessage status="streaming" text={text} steps={[]} renderMarker={() => null} />
        </MemoryRouter>
      )
      const { rerender } = render(view(''))
      act(() => vi.advanceTimersByTime(8000))
      expect(screen.getByText('Still working on it…')).toBeInTheDocument()
      rerender(view('A working note'))
      expect(screen.queryByText('Still working on it…')).toBeNull()
      rerender(view(''))
      expect(screen.queryByText('Still working on it…')).toBeNull()
      act(() => vi.advanceTimersByTime(8000))
      expect(screen.getByText('Still working on it…')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('never says "Still working on it…" once answer text has arrived', () => {
    vi.useFakeTimers()
    try {
      renderMessage({ status: 'streaming', text: 'You get', steps: [] })
      act(() => vi.advanceTimersByTime(20_000))
      expect(screen.queryByText('Still working on it…')).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not fade in: a turn is drawn again as it settles and is saved, and must not blink', () => {
    const { container } = renderMessage()
    expect(message(container).className).not.toMatch(/animate-/)
  })

  it('says "Working on the answer…" for a running turn seen after a reload, not "Reading your question…"', async () => {
    renderMessage({ status: 'streaming', text: '', steps: [], justAsked: false })
    expect(await screen.findByText('Working on the answer…')).toBeInTheDocument()
    expect(screen.queryByText('Reading your question…')).toBeNull()
  })

  it('keeps that same region when the first step arrives', () => {
    const { container, rerender } = renderMessage({ status: 'streaming', text: '', steps: [] })
    const line = container.querySelector('[data-slot="status-line"]')!
    rerender(
      <MemoryRouter>
        <AssistantMessage
          status="streaming"
          text=""
          renderMarker={() => null}
          steps={[{ id: 's1', text: 'Searching the handbook…', done: false }]}
        />
      </MemoryRouter>,
    )
    expect(container.querySelector('[data-slot="status-line"]')).toBe(line)
    expect(line).toHaveTextContent('Searching the handbook…')
  })

  it('has no status region once it is no longer streaming', () => {
    const { container } = renderMessage({ status: 'complete' })
    expect(container.querySelector('[data-slot="status-line"]')).toBeNull()
  })

  it('does not mark the whole message busy', () => {
    const { container } = renderMessage({ status: 'streaming' })
    expect(message(container)).not.toHaveAttribute('aria-busy', 'true')
  })

  it('keeps one polite live region for the answer, before text, while it streams, and after', () => {
    const { container, rerender } = renderMessage({ status: 'streaming', text: '' })
    const live = container.querySelector('[data-slot="answer-live"]')!
    expect(live).toHaveAttribute('aria-live', 'polite')
    // Only the hidden caret: nothing for a screen reader to say yet.
    expect(live).toHaveTextContent('')
    expect(live.querySelector('[data-slot="caret"]')).toHaveAttribute('aria-hidden', 'true')
    const props = { renderMarker: () => null }
    rerender(
      <MemoryRouter>
        <AssistantMessage status="streaming" text="You get" {...props} />
      </MemoryRouter>,
    )
    expect(container.querySelector('[data-slot="answer-live"]')).toBe(live)
    expect(live).toHaveAttribute('aria-live', 'polite')
    rerender(
      <MemoryRouter>
        <AssistantMessage status="complete" text="You get 5 days." {...props} />
      </MemoryRouter>,
    )
    // The same element, still polite, now holding the finished answer: that is what is announced.
    expect(container.querySelector('[data-slot="answer-live"]')).toBe(live)
    expect(live).toHaveAttribute('aria-live', 'polite')
    expect(live).toHaveTextContent('You get 5 days.')
  })

  it('takes no room while the live region is empty', () => {
    const { container } = renderMessage({ status: 'streaming', text: '' })
    expect(container.querySelector('[data-slot="answer-live"]')).toHaveClass('empty:-mt-3.5')
  })

  it('shows the status steps before any text arrives', () => {
    renderMessage({
      status: 'streaming',
      text: '',
      steps: [{ id: 'a', text: 'Searching the handbook…', done: false }],
    })
    expect(screen.getByRole('status')).toHaveTextContent('Searching the handbook…')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps finished steps above the current one', () => {
    renderMessage({
      status: 'streaming',
      text: '',
      steps: [
        { id: 'a', text: 'Searched the handbook: sick leave', done: true },
        { id: 'b', text: 'Searching the handbook again…', done: false },
      ],
    })
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Searched the handbook: sick leave',
      'Searching the handbook again…',
    ])
  })

  it('shows a caret at the end of the streaming text', () => {
    const { container } = renderMessage({ status: 'streaming' })
    expect(container.querySelector('[data-slot="caret"]')).not.toBeNull()
  })

  it('shows the caret alone while nothing has arrived, so the message does not read as stuck', () => {
    const { container } = renderMessage({ status: 'streaming', text: '', steps: [] })
    expect(container.querySelector('[data-slot="caret"]')).not.toBeNull()
    expect(answerLive(container)).toHaveAttribute('aria-busy', 'true')
  })

  it('shows no caret while a step is showing before any text, or once done', () => {
    const { container, rerender } = renderMessage({
      status: 'streaming',
      text: '',
      steps: [{ id: 's1', text: 'Searching the handbook…', done: false }],
    })
    expect(container.querySelector('[data-slot="caret"]')).toBeNull()
    rerender(
      <MemoryRouter>
        <AssistantMessage status="complete" text="Done." renderMarker={() => null} />
      </MemoryRouter>,
    )
    expect(container.querySelector('[data-slot="caret"]')).toBeNull()
  })

  it('shows no caret for a stopped or failed message with no text', () => {
    const stopped = renderMessage({ status: 'stopped', text: '' })
    expect(stopped.container.querySelector('[data-slot="caret"]')).toBeNull()
    expect(answerLive(stopped.container)).toBeEmptyDOMElement()
    stopped.unmount()
    const { container } = renderMessage({
      status: 'error',
      errorMessage: 'Something broke.',
      text: '',
    })
    expect(container.querySelector('[data-slot="caret"]')).toBeNull()
  })

  it('shows markers as the citations arrive, but no sources or feedback yet', () => {
    renderMessage({
      status: 'streaming',
      citations: [citation({ marker: 1, offsetUtf16: 15 })],
      sources: <p>the sources</p>,
      feedback: <p>the feedback</p>,
    })
    expect(screen.getByRole('button', { name: 'marker 1' })).toBeInTheDocument()
    expect(screen.queryByText('the sources')).not.toBeInTheDocument()
    expect(screen.queryByText('the feedback')).not.toBeInTheDocument()
  })

  it('has no Ask again, Retry, or Stopped', () => {
    renderMessage({ status: 'streaming', onAskAgain: () => {}, onRetry: () => {} })
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByText('Stopped')).not.toBeInTheDocument()
  })
})

describe('AssistantMessage: complete', () => {
  it('shows its slots in order: sources, contacts, then feedback', () => {
    const { container } = renderMessage({
      sources: <p>the sources</p>,
      contacts: <p>the contacts</p>,
      feedback: <p>the feedback</p>,
    })
    const text = message(container).textContent!
    expect(text.indexOf('You get 5 days.')).toBeLessThan(text.indexOf('the sources'))
    expect(text.indexOf('the sources')).toBeLessThan(text.indexOf('the contacts'))
    expect(text.indexOf('the contacts')).toBeLessThan(text.indexOf('the feedback'))
  })

  it('works with no slots at all', () => {
    renderMessage()
    expect(screen.getByText('You get 5 days.')).toBeInTheDocument()
  })

  it('reads a not-found answer, with the HR contacts below it', () => {
    const { container } = renderMessage({
      text: "I couldn't find that in the handbook.\n\nThe HR team can tell you.",
      contacts: <section aria-label="HR contacts">HR contacts</section>,
    })
    expect(screen.getByRole('region', { name: 'HR contacts' })).toBeInTheDocument()
    expect(message(container).querySelectorAll('p')).toHaveLength(2)
  })

  it('reads a refusal as an ordinary answer, with its AI label and slots', () => {
    renderMessage({
      text: "I can't share another employee's home address.",
      sources: <p>the sources</p>,
      feedback: <p>the feedback</p>,
    })
    expect(screen.getByText('AI')).toBeInTheDocument()
    expect(screen.getByText("I can't share another employee's home address.")).toBeInTheDocument()
    expect(screen.getByText('the sources')).toBeInTheDocument()
    expect(screen.getByText('the feedback')).toBeInTheDocument()
  })

  it('has no Stopped, Retry, or incomplete note', () => {
    renderMessage()
    expect(screen.queryByText('Stopped')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(
      screen.queryByText('This answer was cut off before it finished.'),
    ).not.toBeInTheDocument()
  })
})

describe('AssistantMessage: stopped', () => {
  it('shows the partial text, "Stopped", and Ask again', async () => {
    const onAskAgain = vi.fn<() => void>()
    renderMessage({ status: 'stopped', text: 'Because you work in California, the', onAskAgain })
    expect(screen.getByText('Because you work in California, the')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Stopped')
    await userEvent.click(screen.getByRole('button', { name: 'Ask again' }))
    expect(onAskAgain).toHaveBeenCalledTimes(1)
  })

  it('has no Ask again without a handler, and no sources or feedback', () => {
    renderMessage({ status: 'stopped', sources: <p>the sources</p>, feedback: <p>the feedback</p> })
    expect(screen.queryByRole('button', { name: 'Ask again' })).not.toBeInTheDocument()
    expect(screen.queryByText('the sources')).not.toBeInTheDocument()
    expect(screen.queryByText('the feedback')).not.toBeInTheDocument()
  })

  it('is not busy and has no caret', () => {
    const { container } = renderMessage({ status: 'stopped' })
    expect(container.querySelector('[data-slot="answer-live"]')).toHaveAttribute(
      'aria-busy',
      'false',
    )
    expect(container.querySelector('[data-slot="caret"]')).toBeNull()
  })
})

describe('AssistantMessage: incomplete', () => {
  it('shows the answer and a muted note that it was cut off', () => {
    renderMessage({ status: 'incomplete' })
    expect(screen.getByText('You get 5 days.')).toBeInTheDocument()
    expect(screen.getByText('This answer was cut off before it finished.')).toHaveClass(
      'text-ink-muted',
    )
  })

  it('still shows its sources and feedback, as the turn did finish', () => {
    renderMessage({
      status: 'incomplete',
      sources: <p>the sources</p>,
      feedback: <p>the feedback</p>,
    })
    expect(screen.getByText('the sources')).toBeInTheDocument()
    expect(screen.getByText('the feedback')).toBeInTheDocument()
  })
})

describe('AssistantMessage: error', () => {
  it("shows the API's message verbatim in an alert, with Retry", async () => {
    const onRetry = vi.fn<() => void>()
    renderMessage({
      status: 'error',
      text: 'Because you work in California,',
      errorMessage: 'The assistant is unavailable right now. Try again in a moment.',
      onRetry,
    })
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(
      'The assistant is unavailable right now. Try again in a moment.',
    )
    expect(alert.textContent).not.toContain('Something went wrong partway')
    expect(screen.getByText('Because you work in California,')).toBeInTheDocument()
    await userEvent.click(within(alert).getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('keeps Retry right after the message, not at the far end of the row', () => {
    renderMessage({ status: 'error', text: '', errorMessage: 'It broke.', onRetry: () => {} })
    expect(screen.getByText('It broke.').closest('p')).not.toHaveClass('flex-1')
  })

  it('shows the error with no partial text', () => {
    renderMessage({ status: 'error', text: '', errorMessage: 'It broke.' })
    expect(screen.getByRole('alert')).toHaveTextContent('It broke.')
    expect(screen.getByText('AI')).toBeInTheDocument()
  })

  it('shows the walkthrough link under the error text when it offers one', () => {
    renderMessage({
      status: 'error',
      text: '',
      errorMessage: 'It broke.',
      offerWalkthrough: true,
    })
    const alert = screen.getByRole('alert')
    const link = screen.getByRole('link', { name: 'Watch the recorded walkthrough' })
    expect(alert).toHaveTextContent('It broke.')
    // The link follows the error message in the page.
    expect(alert.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(link.parentElement).toHaveClass('mt-2', 'block')
  })

  it('shows no walkthrough link for an internal error', () => {
    renderMessage({ status: 'error', text: '', errorMessage: 'It broke.' })
    expect(screen.queryByRole('link', { name: 'Watch the recorded walkthrough' })).toBeNull()
  })

  it('has no Retry without a handler, and no sources or feedback', () => {
    renderMessage({
      status: 'error',
      errorMessage: 'It broke.',
      sources: <p>the sources</p>,
      feedback: <p>the feedback</p>,
    })
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
    expect(screen.queryByText('the sources')).not.toBeInTheDocument()
    expect(screen.queryByText('the feedback')).not.toBeInTheDocument()
  })

  it('cannot be built without the API message, which only the API words', () => {
    // The union type makes `errorMessage` required for `error`. The directive is itself the
    // test: `tsc` fails on an unused one if the type ever lets the message go missing.
    const build = () => (
      // @ts-expect-error errorMessage is required when status is "error"
      <AssistantMessage status="error" text="" renderMarker={() => null} />
    )
    expect(build).toBeTypeOf('function')
  })
})

describe('AssistantMessage: work it does for a render', () => {
  it('does not scan the answer again when it re-renders with the same text and citations', () => {
    const spy = vi.spyOn(linkSpans, 'linkAddressSpans')
    const citations = [citation({ offsetUtf16: 5 })]
    const props = { text: 'Five days.', citations, renderMarker: () => null } as const
    const { rerender } = render(
      <MemoryRouter>
        <AssistantMessage status="streaming" {...props} />
      </MemoryRouter>,
    )
    rerender(
      <MemoryRouter>
        <AssistantMessage status="streaming" {...props} steps={[]} />
      </MemoryRouter>,
    )
    expect(spy).toHaveBeenCalledTimes(1)
    spy.mockRestore()
  })

  it('does not look for link addresses at all in a message with no citations', () => {
    const spy = vi.spyOn(linkSpans, 'linkAddressSpans')
    const props = { text: 'See [x](/handbook/4.3).', renderMarker: () => null } as const
    const { rerender } = render(
      <MemoryRouter>
        <AssistantMessage status="streaming" {...props} />
      </MemoryRouter>,
    )
    rerender(
      <MemoryRouter>
        <AssistantMessage status="streaming" {...props} steps={[]} />
      </MemoryRouter>,
    )
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })
})

describe('AssistantMessage: numbering by source', () => {
  it('takes citations as numbered, and does not number them again', () => {
    const spy = vi.spyOn(sources, 'numberBySection')
    render(
      <MemoryRouter>
        <AssistantMessage
          status="complete"
          text={'x'.repeat(80)}
          citations={apiCitations()}
          renderMarker={(c) => <CitationMarker citation={c} expanded={false} onOpen={() => {}} />}
        />
      </MemoryRouter>,
    )
    expect(spy).not.toHaveBeenCalled()
  })

  it('numbers markers by section, so marker 1 and chip 1 are the same section', () => {
    // The API numbers each passage (two passages of one section are 1 and 2). The design numbers
    // each section, and the message, its chips, and "Show your work" all show that.
    const citations = numberBySection(apiCitations())
    const { container } = render(
      <MemoryRouter>
        <AssistantMessage
          status="complete"
          text={'x'.repeat(80)}
          citations={citations}
          renderMarker={(c) => <CitationMarker citation={c} expanded={false} onOpen={() => {}} />}
          sources={<SourceChips citations={citations} onOpen={() => {}} />}
        />
      </MemoryRouter>,
    )
    const answer = container.querySelector<HTMLElement>('[data-slot="answer"]')!
    const markers = within(answer).getAllByRole('button')
    expect(markers.map((m) => m.textContent)).toEqual(['1', '1', '1', '2'])
    const chips = within(screen.getByRole('list', { name: 'Sources' })).getAllByRole('button')
    expect(chips).toHaveLength(2)
    // A marker is named "Source 1: Handbook ...", its chip starts with the chip's own text and ends
    // with the same number.
    expect(markers.map((m) => accessibleNameOf(m).slice(0, 9))).toEqual([
      'Source 1:',
      'Source 1:',
      'Source 1:',
      'Source 2:',
    ])
    expect(chips.map((c) => accessibleNameOf(c).slice(-10))).toEqual([', source 1', ', source 2'])
  })

  it('still opens the passage each marker cites', async () => {
    const onOpen = vi.fn<(passageId: string) => void>()
    const citations = numberBySection(apiCitations())
    const { container } = render(
      <MemoryRouter>
        <AssistantMessage
          status="complete"
          text={'x'.repeat(80)}
          citations={citations}
          renderMarker={(c) => (
            <CitationMarker
              citation={c}
              expanded={false}
              onOpen={(cited) => onOpen(cited.passageId)}
            />
          )}
        />
      </MemoryRouter>,
    )
    const answer = container.querySelector<HTMLElement>('[data-slot="answer"]')!
    const markers = within(answer).getAllByRole('button')
    await userEvent.click(markers[2]!)
    expect(onOpen).toHaveBeenLastCalledWith('CA-4.3~p2')
  })
})

describe('AssistantMessage: the paced reveal (ADR 0025)', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('holds back markers past the revealed text, and the footer, until the reveal ends', () => {
    stubMediaQuery(true)
    // Frames never run, so the reveal stays where it starts.
    vi.stubGlobal('requestAnimationFrame', () => 1)
    vi.stubGlobal('cancelAnimationFrame', () => {})
    const long = `${'You get five days. '.repeat(40)}End.`
    const props = {
      citations: [citation({ marker: 1, offsetUtf16: long.length })],
      renderMarker: (c: { marker: number }) => (
        <button type="button">{`marker ${c.marker}`}</button>
      ),
      feedback: <p>the feedback</p>,
    }
    const { container, rerender } = render(
      <MemoryRouter>
        <AssistantMessage status="streaming" text="" {...props} />
      </MemoryRouter>,
    )
    rerender(
      <MemoryRouter>
        <AssistantMessage status="complete" text={long} {...props} />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('button', { name: 'marker 1' })).toBeNull()
    expect(screen.queryByText('the feedback')).toBeNull()
    expect(container.querySelector('[data-slot="answer-live"]')).toHaveAttribute(
      'aria-busy',
      'true',
    )
  })
})

describe('AssistantMessage: a stop during the reveal', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the whole text at once beside "Stopped", with no caret and nothing busy', () => {
    stubMediaQuery(true)
    vi.stubGlobal('requestAnimationFrame', () => 1)
    vi.stubGlobal('cancelAnimationFrame', () => {})
    const long = `${'You get five days. '.repeat(40)}End.`
    const view = (status: 'streaming' | 'stopped', text: string) => (
      <MemoryRouter>
        <AssistantMessage status={status} text={text} renderMarker={() => null} />
      </MemoryRouter>
    )
    const { container, rerender } = render(view('streaming', ''))
    rerender(view('streaming', long))
    expect(container.querySelector('[data-slot="answer-live"]')).toHaveTextContent('')
    rerender(view('stopped', long))
    expect(screen.getByText('Stopped', { exact: true })).toBeInTheDocument()
    expect(container.querySelector('[data-slot="answer-live"]')).toHaveTextContent(/End\.$/)
    expect(container.querySelector('[data-slot="caret"]')).toBeNull()
    expect(container.querySelector('[data-slot="answer-live"]')).toHaveAttribute(
      'aria-busy',
      'false',
    )
  })
})
