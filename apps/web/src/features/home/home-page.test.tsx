import { act, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatStore } from '@/features/chat/store'
import { createFakeTransport, FAKE_REPLY } from '@/features/chat/fake-transport'
import type { ChatTransport } from '@/features/chat/transport'
import { PERSONAS } from '@/features/personas/personas'
import { installFakeApi } from '@/test/fake-api'
import { renderApp } from '@/test/render-app'

const FAST = createFakeTransport({ delayMs: 0 })
const FAILING = createFakeTransport({ delayMs: 0, fail: true })
const composer = () => screen.findByRole('textbox', { name: 'Ask Open Door' })

beforeEach(() => {
  useChatStore.setState({ draft: '', status: 'idle', reply: null, lastQuestion: null })
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
      renderApp({ at: '/ask', transport: FAST })
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
    renderApp({ at: '/ask', transport: FAST })
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Good morning, Marcus.' }),
    ).toBeInTheDocument()
  })
})

describe('Try asking', () => {
  it("lists the signed-in person's own questions", async () => {
    installFakeApi('marcus')
    renderApp({ at: '/ask', transport: FAST })
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
    const send = vi.fn<ChatTransport['send']>(() => Promise.resolve({ text: 'x' }))
    const { user } = renderApp({ at: '/ask', transport: { send } })
    await user.click(await screen.findByRole('button', { name: 'Book next Friday off' }))
    expect(await composer()).toHaveValue('Book next Friday off')
    // Give a stray send every chance to happen.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(send).not.toHaveBeenCalled()
    expect(useChatStore.getState().status).toBe('idle')
    expect(screen.queryByRole('region', { name: "Open Door's reply" })).not.toBeInTheDocument()
  })
})

describe('asking', () => {
  it('sends through the transport and shows the reply in a block named for screen readers', async () => {
    installFakeApi('priya')
    const send = vi.fn<ChatTransport['send']>(FAST.send)
    const { user } = renderApp({ at: '/ask', transport: { send } })
    await user.type(await composer(), 'How many sick days do I get?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    const reply = await screen.findByRole('region', { name: "Open Door's reply" })
    expect(reply).toHaveTextContent(FAKE_REPLY)
    expect(send).toHaveBeenCalledOnce()
    expect(send.mock.calls[0][0]).toBe('How many sick days do I get?')
    await waitFor(async () => expect(await composer()).toHaveValue(''))
  })

  it('sends a picked question when Ask is pressed', async () => {
    installFakeApi('priya')
    const send = vi.fn<ChatTransport['send']>(FAST.send)
    const { user } = renderApp({ at: '/ask', transport: { send } })
    await user.click(await screen.findByRole('button', { name: 'Book next Friday off' }))
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByRole('region', { name: "Open Door's reply" })
    expect(send.mock.calls[0][0]).toBe('Book next Friday off')
  })

  it('keeps the question and announces the error with Retry when the send fails', async () => {
    installFakeApi('priya')
    const { user } = renderApp({ at: '/ask', transport: FAILING })
    await user.type(await composer(), 'How many sick days do I get?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Something went wrong sending that.')
    expect(within(alert).getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(await composer()).toHaveValue('How many sick days do I get?')
    expect(screen.queryByRole('region', { name: "Open Door's reply" })).not.toBeInTheDocument()
  })

  it('Retry sends the same question again', async () => {
    installFakeApi('priya')
    let calls = 0
    const send = vi.fn<ChatTransport['send']>(() => {
      calls++
      return calls === 1 ? Promise.reject(new Error('down')) : Promise.resolve({ text: 'Back.' })
    })
    const { user } = renderApp({ at: '/ask', transport: { send } })
    await user.type(await composer(), 'Who do I talk to about a concern?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    await user.click(
      await within(await screen.findByRole('alert')).findByRole('button', { name: 'Retry' }),
    )
    expect(await screen.findByRole('region', { name: "Open Door's reply" })).toHaveTextContent(
      'Back.',
    )
    expect(send).toHaveBeenCalledTimes(2)
    expect(send.mock.calls[1][0]).toBe('Who do I talk to about a concern?')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('the reply slot', () => {
  const slot = () => document.querySelector<HTMLElement>('[data-slot="reply-slot"]')

  it('is a polite output region that exists before the send and receives the reply', async () => {
    installFakeApi('priya')
    const { user } = renderApp({ at: '/ask', transport: FAST })
    await user.type(await composer(), 'Hello')
    const before = slot()
    // An <output> is a polite status region.
    expect(before?.tagName).toBe('OUTPUT')
    expect(before).toBeEmptyDOMElement()
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    const reply = await screen.findByRole('region', { name: "Open Door's reply" })
    expect(slot()).toBe(before)
    expect(slot()).toContainElement(reply)
  })

  it("says the spec's fixed text, word for word", async () => {
    installFakeApi('priya')
    const { user } = renderApp({ at: '/ask', transport: FAST })
    await user.type(await composer(), 'Hello')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByRole('region', { name: "Open Door's reply" })).toHaveTextContent(
      "The assistant isn't connected yet. When it is, it will answer here and cite the Juniper Row handbook for every policy it mentions.",
    )
  })
})

describe('Retry', () => {
  async function failFirst() {
    installFakeApi('priya')
    let calls = 0
    const send = vi.fn<ChatTransport['send']>(() => {
      calls++
      return calls === 1 ? Promise.reject(new Error('down')) : Promise.resolve({ text: 'Back.' })
    })
    const { user } = renderApp({ at: '/ask', transport: { send } })
    await user.type(await composer(), 'First question')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    const alert = await screen.findByRole('alert')
    return { user, send, alert }
  }

  it('sends the edited text when the box was edited after the failure', async () => {
    const { user, send, alert } = await failFirst()
    await user.type(await composer(), ' edited')
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    await screen.findByRole('region', { name: "Open Door's reply" })
    expect(send.mock.calls[1][0]).toBe('First question edited')
  })

  it('focuses the box and keeps the error when the box was cleared', async () => {
    const { user, send, alert } = await failFirst()
    await user.clear(await composer())
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    expect(await composer()).toHaveFocus()
    expect(send).toHaveBeenCalledOnce()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })
})

describe('the page', () => {
  it('shows the disclosure and no at-a-glance figures in Phase 2', async () => {
    installFakeApi('priya')
    renderApp({ at: '/ask', transport: FAST })
    await composer()
    expect(
      screen.getByText(
        'Open Door is an AI assistant. It can make mistakes, and it always shows its sources.',
      ),
    ).toBeVisible()
    expect(screen.queryByText('At a glance')).not.toBeInTheDocument()
  })

  it("tabs through the controls in 03's order, from the first real control", async () => {
    // The notes list the logo first, but the design's logo is not a control (the kit draws a
    // plain div), so the order starts at the first nav item.
    installFakeApi('priya')
    const { user } = renderApp({ at: '/ask', transport: FAST })
    await composer()
    const seen: string[] = []
    for (let i = 0; i < 9; i++) {
      await user.tab()
      const el = document.activeElement as HTMLElement
      seen.push(`${el.tagName.toLowerCase()}:${el.getAttribute('aria-label') ?? el.textContent}`)
    }
    expect(seen).toEqual([
      'a:Ask',
      'a:Directory',
      'button:Switch persona. Current: Priya Raman, Visual Merchandiser',
      'textarea:Ask Open Door',
      'button:Ask',
      'button:How many sick days do I get?',
      'button:Book next Friday off',
      'button:What holidays do we have this year?',
      'button:Who do I talk to about a concern?',
    ])
  })
})
