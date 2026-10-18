import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { apiCitations, citation } from '@/test/assistant-fixtures'
import { AssistantMessage } from './assistant-message'
import { CitationMarker } from './citation-marker'
import * as linkSpans from './link-spans'
import { SourceChips } from './source-chip'

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

  it('has the status region in the page while it streams, empty before the first step', () => {
    const { container } = renderMessage({ status: 'streaming', text: '', steps: [] })
    const line = container.querySelector('[data-slot="status-line"]')!
    expect(line).toBeInTheDocument()
    expect(line).toHaveAttribute('role', 'status')
    expect(line).toBeEmptyDOMElement()
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
    expect(live).toBeEmptyDOMElement()
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

  it('shows no caret before text arrives, or once done', () => {
    const { container, rerender } = renderMessage({ status: 'streaming', text: '' })
    expect(container.querySelector('[data-slot="caret"]')).toBeNull()
    rerender(
      <MemoryRouter>
        <AssistantMessage status="complete" text="Done." renderMarker={() => null} />
      </MemoryRouter>,
    )
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
  it('numbers markers by section, so marker 1 and chip 1 are the same section', () => {
    // The API numbers each passage (two passages of one section are 1 and 2). The design numbers
    // each section, and the message, its chips, and "Show your work" all show that.
    const citations = apiCitations()
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
    expect(markers.map((m) => m.getAttribute('aria-label'))).toEqual([
      chips[0]!.getAttribute('aria-label'),
      chips[0]!.getAttribute('aria-label'),
      chips[0]!.getAttribute('aria-label'),
      chips[1]!.getAttribute('aria-label'),
    ])
  })

  it('still opens the passage each marker cites', async () => {
    const onOpen = vi.fn<(passageId: string) => void>()
    const citations = apiCitations()
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
