import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderToStaticMarkup } from 'react-dom/server'
import { createMemoryRouter, RouterProvider, type InitialEntry } from 'react-router'
import { describe, expect, it } from 'vitest'
import { getGetMeQueryKey, getMe } from '@/api/generated'
import { Answer } from '@/components/assistant/answer'
import { installFakeApi } from '@/test/fake-api'
import { renderApp } from '@/test/render-app'
import { PERSONAS } from '@/features/personas/personas'
import { metadataLine, POSTER_SRC, VIDEO_SRC, WALKTHROUGH } from './recording'
import { Transcript } from './transcript'
import { WalkthroughPage } from './walkthrough-page'

/** One step with one answer, to see how the transcript renders an answer's Markdown. */
function WalkthroughTranscriptProbe({ text }: { text: string }) {
  return (
    <Transcript
      steps={[
        {
          id: 'probe',
          title: 'Probe',
          persona: 'marcus',
          words: 'Words.',
          exchanges: [
            { speaker: 'person', text: 'Anything waiting on me?' },
            { speaker: 'ai', text },
          ],
        },
      ]}
    />
  )
}

const HEADING = 'The recorded walkthrough'

function renderPage(entry: InitialEntry = '/walkthrough') {
  const router = createMemoryRouter(
    [
      { path: '/walkthrough', element: <WalkthroughPage /> },
      { path: '*', element: <p>somewhere else</p> },
    ],
    { initialEntries: [entry] },
  )
  render(<RouterProvider router={router} />)
  return { router, user: userEvent.setup() }
}

const steps = () => screen.getAllByRole('article')

/** An answer's words as the app's own renderer shows them (its Markdown: lists, bold). */
const asRendered = (markdown: string) => {
  const box = document.createElement('div')
  box.innerHTML = renderToStaticMarkup(
    <Answer text={markdown} citations={[]} renderMarker={() => null} />,
  )
  return box.textContent
}

describe('the walkthrough page', () => {
  it('opens for a visitor with no session, with no app navigation', async () => {
    installFakeApi()
    const { router } = renderApp({ at: '/walkthrough' })
    expect(await screen.findByRole('heading', { level: 1, name: HEADING })).toBeVisible()
    expect(router.state.location.pathname).toBe('/walkthrough')
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  it('stays open for a signed-in visitor (the landing would send them to /ask)', async () => {
    installFakeApi('priya')
    const { queryClient, router } = renderApp({ at: '/walkthrough' })
    expect(await screen.findByRole('heading', { level: 1, name: HEADING })).toBeVisible()
    // Wait for the session to be known: a redirect would come only once /me has answered.
    queryClient.prefetchQuery({ queryKey: getGetMeQueryKey(), queryFn: () => getMe() })
    await waitFor(() => expect(queryClient.getQueryData(getGetMeQueryKey())).toBeDefined())
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.getByRole('heading', { level: 1, name: HEADING })).toBeVisible()
    expect(router.state.location.pathname).toBe('/walkthrough')
    expect(screen.queryByRole('button', { name: /Switch persona$/ })).not.toBeInTheDocument()
  })

  it('shows the intro under the heading', () => {
    renderPage()
    expect(
      screen.getByText(
        'The guided tour, recorded with the live assistant: the same ten steps you can take yourself.',
      ),
    ).toBeVisible()
  })

  it('plays the video only when asked: native controls, a poster, no autoplay, preload none', () => {
    renderPage()
    const video = document.querySelector('video')!
    expect(video).toHaveAttribute('controls')
    expect(video).toHaveAttribute('preload', 'none')
    expect(video).toHaveAttribute('poster', POSTER_SRC)
    expect(video).not.toHaveAttribute('autoplay')
    expect(video.autoplay).toBe(false)
    expect(video).not.toHaveAttribute('loop')
    expect(video.querySelector('source')).toHaveAttribute('src', VIDEO_SRC)
    expect(video.querySelector('source')).toHaveAttribute('type', 'video/mp4')
    expect(video).toHaveAccessibleName(HEADING)
  })

  it('says when and with which model it was recorded, under the video', () => {
    renderPage()
    const figure = screen.getByRole('figure')
    expect(within(figure).getByText(metadataLine(WALKTHROUGH))).toBeVisible()
    expect(figure).toContainElement(document.querySelector('video'))
  })
})

describe('the transcript', () => {
  it('is real text under a "Transcript" heading, one article per step, in order', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 2, name: 'Transcript' })).toBeVisible()
    expect(steps()).toHaveLength(WALKTHROUGH.steps.length)
    steps().forEach((article, index) => {
      const step = WALKTHROUGH.steps[index]
      expect(article).toHaveAttribute('id', `step-${index + 1}`)
      expect(article).toHaveAccessibleName(step.title)
      expect(within(article).getByRole('heading', { level: 3 })).toHaveTextContent(step.title)
      expect(article).toHaveTextContent(
        `Step ${index + 1} of ${WALKTHROUGH.steps.length}${step.title}`,
      )
      expect(within(article).getByText(step.words)).toBeVisible()
    })
  })

  it('names the persona after the title, and none on the end card', () => {
    renderPage()
    const lineOf = (article: HTMLElement) => article.querySelector('[data-slot="persona-line"]')
    const expected = WALKTHROUGH.steps.map((step) => {
      const persona = PERSONAS.find((p) => p.key === step.persona)
      return persona ? `${persona.name} · ${persona.title} · ${persona.location}` : null
    })
    const shown = steps().map((article) => {
      const line = lineOf(article)
      return line === null ? null : line.textContent!.replace(/^[A-Z]{2}/, '')
    })
    expect(shown).toEqual(expected)
    const withLines = steps().filter((article) => lineOf(article) !== null)
    expect(
      withLines.map((article) => {
        const title = within(article).getByRole('heading', { level: 3 })
        return Boolean(
          title.compareDocumentPosition(lineOf(article)!) & Node.DOCUMENT_POSITION_FOLLOWING,
        )
      }),
    ).toEqual(withLines.map(() => true))
    expect(
      withLines.map((article) =>
        lineOf(article)!.querySelector('[data-slot="avatar"]')!.getAttribute('aria-hidden'),
      ),
    ).toEqual(withLines.map(() => 'true'))
  })

  it('shows each exchange as a description list: the speaker, then the words', () => {
    renderPage()
    const shown = steps().map((article) =>
      [...article.querySelectorAll('dl > div')].map((row) => ({
        speaker: row.querySelector('dt')!.textContent,
        words: row.querySelector('dd')!.textContent,
      })),
    )
    const expected = WALKTHROUGH.steps.map((step) => {
      const firstName = PERSONAS.find((p) => p.key === step.persona)?.firstName
      return step.exchanges.map((exchange) => ({
        speaker: {
          person: firstName,
          ai: 'Open Door, the AI assistantAIOpen Door',
          'hr-panel': 'HR panelFixed text written by a person, not the AI',
        }[exchange.speaker],
        words:
          exchange.speaker === 'ai'
            ? `${asRendered(exchange.text)}${exchange.sources?.length ? `${exchange.sources.length > 1 ? 'Sources' : 'Source'}${exchange.sources.map((x) => `${x.id} · ${x.title}`).join('')}` : ''}`
            : exchange.text,
      }))
    })
    expect(shown).toEqual(expected)
    // A step with no exchanges has no empty box.
    expect(steps().map((article) => article.querySelectorAll('dl').length)).toEqual(
      WALKTHROUGH.steps.map((step) => (step.exchanges.length > 0 ? 1 : 0)),
    )
  })

  it('labels every answer as the AI’s, and the HR panel’s text never', () => {
    renderPage()
    const terms = [...document.querySelectorAll('dt')]
    const exchanges = WALKTHROUGH.steps.flatMap((step) => step.exchanges)
    expect(exchanges.some((e) => e.speaker === 'hr-panel')).toBe(true)
    expect(
      terms.map((term) => ({
        aiName: term.textContent!.includes('Open Door, the AI assistant'),
        badge: within(term).queryByText('AI')?.getAttribute('aria-hidden') ?? null,
      })),
    ).toEqual(
      exchanges.map((exchange) =>
        exchange.speaker === 'ai'
          ? { aiName: true, badge: 'true' }
          : { aiName: false, badge: null },
      ),
    )
  })

  it('marks each answer as AI-generated and never a question or the HR panel’s text', () => {
    renderPage()
    const exchanges = WALKTHROUGH.steps.flatMap((step) => step.exchanges)
    const rows = [...document.querySelectorAll('dl > div')]
    expect(rows).toHaveLength(exchanges.length)
    expect(
      rows.map((row) => row.querySelector('dd')!.querySelectorAll('[data-ai-generated]').length),
    ).toEqual(exchanges.map((exchange) => (exchange.speaker === 'ai' ? 1 : 0)))
  })

  it('renders an answer’s Markdown as the app does: a list stays a list', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: (
            <WalkthroughTranscriptProbe text={'Two requests:\n\n- **Zara**, November 9\n- Priya'} />
          ),
        },
      ],
      { initialEntries: ['/'] },
    )
    render(<RouterProvider router={router} />)
    const answer = document.querySelectorAll('dd')[1]!
    expect(answer.querySelectorAll('li')).toHaveLength(2)
    expect(answer.querySelector('strong')).toHaveTextContent('Zara')
    expect(answer).not.toHaveTextContent('**')
  })

  it('links nothing in an answer, whatever form the link takes: the page is public', () => {
    const text =
      'See [sick leave](/handbook/4.3), [it](/handbook/4.3 "Sick leave"), and [Leo][d].\n\n' +
      '[d]: /directory/abc'
    const router = createMemoryRouter(
      [{ path: '/', element: <WalkthroughTranscriptProbe text={text} /> }],
      { initialEntries: ['/'] },
    )
    render(<RouterProvider router={router} />)
    const answer = document.querySelectorAll('dd')[1]!
    expect(answer.querySelector('a')).toBeNull()
    expect(answer).toHaveTextContent('See sick leave, it, and Leo.')
  })

  it('shows sources as plain text, never as links or buttons', () => {
    renderPage()
    const sources = WALKTHROUGH.steps
      .flatMap((step) => step.exchanges)
      .flatMap((e) => (e.speaker === 'ai' ? (e.sources ?? []) : []))
    expect(sources.length).toBeGreaterThan(0)
    expect(
      sources.map((source) =>
        screen.getAllByText(`${source.id} · ${source.title}`)[0].closest('a, button'),
      ),
    ).toEqual(sources.map(() => null))
    const transcript = screen.getByRole('region', { name: 'Transcript' })
    expect(within(transcript).queryAllByRole('link')).toHaveLength(0)
    expect(within(transcript).queryAllByRole('button')).toHaveLength(0)
  })

  it('puts each note under its exchanges, outside the answer', () => {
    renderPage()
    const notes = steps().map((article) => article.querySelector('[data-slot="step-note"]'))
    expect(notes.map((note) => note?.textContent ?? null)).toEqual(
      WALKTHROUGH.steps.map((step) => step.note ?? null),
    )
    expect(notes.map((note) => note?.closest('dl') ?? null)).toEqual(notes.map(() => null))
  })
})

describe('Back to the demo', () => {
  const back = () => screen.getByRole('link', { name: 'Back to the demo' })

  it('returns to the page the visitor came from', () => {
    renderPage({ pathname: '/walkthrough', state: { from: '/ask?c=abc' } })
    expect(back()).toHaveAttribute('href', '/ask?c=abc')
  })

  it('goes to the landing for a direct open', () => {
    renderPage()
    expect(back()).toHaveAttribute('href', '/')
  })

  it('goes to the landing when the state names another site', () => {
    renderPage({ pathname: '/walkthrough', state: { from: '//evil.example/' } })
    expect(back()).toHaveAttribute('href', '/')
  })

  it('follows the link', async () => {
    const { router, user } = renderPage({ pathname: '/walkthrough', state: { from: '/time-off' } })
    await user.click(back())
    expect(router.state.location.pathname).toBe('/time-off')
  })

  it('has the logo as a link to the landing, whatever the state', () => {
    renderPage({ pathname: '/walkthrough', state: { from: '/ask' } })
    expect(screen.getByRole('link', { name: 'Open Door home' })).toHaveAttribute('href', '/')
  })
})

describe('the footer', () => {
  it('says the assistant is an AI and the company is fictional', () => {
    renderPage()
    const footer = screen.getByRole('contentinfo')
    expect(footer).toHaveTextContent(
      'Open Door is an AI assistant. It can make mistakes, and it always shows its sources.',
    )
    expect(footer).toHaveTextContent('Juniper Row and everyone in it are fictional.')
  })
})
