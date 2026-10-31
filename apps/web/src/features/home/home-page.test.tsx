import { act, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatStore } from '@/features/chat/store'
import { PERSONAS } from '@/features/personas/personas'
import { installFakeApi } from '@/test/fake-api'
import {
  CONVERSATION_ID,
  TEXTS,
  TURN_ID,
  eventStream,
  installAssistantApi,
  onTurn,
  openStream,
} from '@/test/fake-assistant'
import { server } from '@/test/msw'
import { renderApp } from '@/test/render-app'

const composer = () => screen.findByRole('textbox', { name: 'Ask Open Door' })

beforeEach(() => {
  useChatStore.setState(useChatStore.getInitialState())
})
afterEach(() => {
  vi.useRealTimers()
})

describe('the greeting', () => {
  // 2026-10-07 01:00 UTC is 18:00 in Los Angeles (the fixture's location) and 10:00 in Tokyo.
  const INSTANT = new Date('2026-10-07T01:00:00Z')

  it("uses the location's timezone, not the browser's", async () => {
    const browserZone = process.env.TZ
    process.env.TZ = 'Asia/Tokyo'
    try {
      vi.useFakeTimers({ toFake: ['Date'], now: INSTANT })
      installFakeApi('priya')
      renderApp({ at: '/ask' })
      expect(
        await screen.findByRole('heading', { level: 1, name: 'Good evening, Priya.' }),
      ).toBeInTheDocument()
    } finally {
      if (browserZone === undefined) delete process.env.TZ
      else process.env.TZ = browserZone
    }
  })

  it('names the signed-in person', async () => {
    vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-10-06T17:00:00Z') })
    installFakeApi('marcus')
    renderApp({ at: '/ask' })
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Good morning, Marcus.' }),
    ).toBeInTheDocument()
  })
})

describe('Try asking', () => {
  it("lists the signed-in person's own questions", async () => {
    installFakeApi('marcus')
    renderApp({ at: '/ask' })
    const list = await screen.findByRole('region', { name: 'Try asking' })
    const marcus = PERSONAS.find((p) => p.key === 'marcus')!
    expect(
      within(list)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual([...marcus.tryAsking])
  })

  it('fills the box without sending', async () => {
    installFakeApi('priya')
    const posted = onTurn(() => eventStream())
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'Book next Friday off' }))
    expect(await composer()).toHaveValue('Book next Friday off')
    // Give a stray send every chance to happen.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(posted).toHaveLength(0)
    expect(useChatStore.getState().status).toBe('idle')
    // Still the home: no conversation was started.
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
  })
})

describe('asking', () => {
  const started = ['turn.started', { turnId: TURN_ID }] as const
  const completed = [
    'turn.completed',
    { turnId: TURN_ID, servedBy: 'anthropic', usage: { inputTokens: 1, outputTokens: 1 } },
  ] as const

  function answer(text: string) {
    return onTurn(() => eventStream([...started], ['text.delta', { text }], [...completed]))
  }

  it('sends the question to the API, trimmed, and shows the streamed reply in the conversation', async () => {
    installFakeApi('priya')
    installAssistantApi()
    const posted = answer('You get 5 days.')
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), '  How many sick days do I get?  ')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText('You get 5 days.')).toBeInTheDocument()
    expect(posted).toHaveLength(1)
    // The first question creates the conversation, and what is sent is trimmed.
    expect(posted[0]).toMatchObject({
      conversationId: CONVERSATION_ID,
      question: 'How many sick days do I get?',
    })
    await waitFor(async () => expect(await composer()).toHaveValue(''))
  })

  it('sends a picked question when Ask is pressed', async () => {
    installFakeApi('priya')
    installAssistantApi()
    const posted = answer('Done.')
    const { user } = renderApp({ at: '/ask' })
    await user.click(await screen.findByRole('button', { name: 'Book next Friday off' }))
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByText('Done.')
    expect(posted[0]?.question).toBe('Book next Friday off')
  })

  it('keeps the question and announces the error when the send fails, and Ask sends it again', async () => {
    installFakeApi('priya')
    installAssistantApi()
    let calls = 0
    const posted = onTurn(() =>
      ++calls === 1
        ? new Response(null, { status: 500 })
        : eventStream([...started], ['text.delta', { text: 'Back.' }], [...completed]),
    )
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'How many sick days do I get?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Something went wrong sending that.')
    expect(await composer()).toHaveValue('How many sick days do I get?')
    // Still the home: nothing was answered.
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText('Back.')).toBeInTheDocument()
    expect(posted.map((p) => p.question)).toEqual([
      'How many sick days do I get?',
      'How many sick days do I get?',
    ])
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it("shows the API's personal-data text and sends nothing for a number it refuses", async () => {
    installFakeApi('priya')
    installAssistantApi()
    const posted = answer('x')
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'My SSN is 123-45-6789')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(TEXTS.personalData)
    expect(posted).toHaveLength(0)
    expect(await composer()).toHaveValue('My SSN is 123-45-6789')
  })

  it('stops an answer that is streaming, and shows it as stopped', async () => {
    installFakeApi('priya')
    installAssistantApi()
    const stream = openStream()
    onTurn(() => stream.response())
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'How many sick days do I get?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    stream.push(...started)
    stream.push('text.delta', { text: 'You get ' })
    expect(await screen.findByText(/You get/)).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Stop' }))
    expect(useChatStore.getState().status).toBe('stopped')
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument()
    expect(screen.getByText('Stopped')).toBeInTheDocument()
  })
})

describe('the page', () => {
  it('shows the disclosure and the rail, with only the figures that exist so far', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask' })
    await composer()
    expect(
      screen.getByText(
        'Open Door is an AI assistant. It can make mistakes, and it always shows its sources.',
      ),
    ).toBeVisible()
    // Only the Handbook's figure until Phase 5 brings time off.
    expect(
      await screen.findByRole('link', { name: 'Sep 12 Handbook updated. Open Handbook' }),
    ).toBeInTheDocument()
    expect(screen.queryByText(/days PTO available/)).not.toBeInTheDocument()
  })

  it.each(['assistant/conversations/current', 'assistant/texts'])(
    'waits for the %s read before it shows the composer',
    async (path) => {
      installFakeApi('priya')
      let release!: () => void
      const held = new Promise<void>((resolve) => {
        release = resolve
      })
      installAssistantApi()
      server.use(
        http.get(`${window.location.origin}/api/v1/${path}`, async () => {
          await held
          return HttpResponse.json(path.endsWith('texts') ? TEXTS : null)
        }),
      )
      renderApp({ at: '/ask' })
      await screen.findByRole('link', { name: /Handbook updated/ })
      expect(screen.queryByRole('textbox', { name: 'Ask Open Door' })).not.toBeInTheDocument()
      release()
      expect(await composer()).toBeInTheDocument()
    },
  )

  it('sends a failed read to the route’s error page, with Retry', async () => {
    installFakeApi('priya')
    installAssistantApi()
    let calls = 0
    server.use(
      http.get(`${window.location.origin}/api/v1/assistant/texts`, () =>
        ++calls <= 2 ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(TEXTS),
      ),
    )
    const { user } = renderApp({ at: '/ask' })
    expect(await screen.findByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Ask Open Door' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await composer()).toBeInTheDocument()
  })

  it("tabs through the controls in 03's order, from the first real control", async () => {
    // The notes list the logo first, but the design's logo is not a control (the kit draws a
    // plain div), so the order starts at the first nav item.
    installFakeApi('priya')
    const { user } = renderApp({ at: '/ask' })
    await composer()
    // The rail comes after the page, so its figure is the last stop.
    await screen.findByRole('link', { name: 'Sep 12 Handbook updated. Open Handbook' })
    await screen.findByRole('link', { name: '92 hours PTO available. Open Time off' })
    const seen: string[] = []
    for (let i = 0; i < 15; i++) {
      await user.tab()
      const el = document.activeElement as HTMLElement
      seen.push(`${el.tagName.toLowerCase()}:${el.getAttribute('aria-label') ?? el.textContent}`)
    }
    expect(seen).toEqual([
      'a:Ask',
      'a:Time off',
      'a:My cases',
      'a:Directory',
      'a:Handbook',
      'button:Switch persona. Current: Priya Raman, Visual Merchandiser',
      'textarea:Ask Open Door',
      'button:Ask',
      'button:How many sick days do I get?',
      'button:Book next Friday off',
      'button:What holidays do we have this year?',
      'button:Who do I talk to about a concern?',
      'a:92 hours PTO available. Open Time off',
      'a:0 requests pending. Open Time off',
      'a:Sep 12 Handbook updated. Open Handbook',
    ])
  })
})
