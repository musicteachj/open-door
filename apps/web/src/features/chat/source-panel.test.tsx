import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { citation, toolCall } from '@/test/assistant-fixtures'
import { installFakeApi } from '@/test/fake-api'
import { installFakeDirectory } from '@/test/fake-directory'
import {
  conversationOut,
  installAssistantApi,
  installPassages,
  turnOut,
} from '@/test/fake-assistant'
import { stubMediaQuery } from '@/test/media-query'
import { server } from '@/test/msw'
import { renderApp } from '@/test/render-app'
import { useChatStore } from './store'
import { returnFocusToOpener } from './source-opener'
import * as sourceKeys from './source-key'

// The source panel: a marker or chip opens its passage, `?source=` in the URL is the one place that
// says so, and the shell shows it in the rail's place (wide) or as a modal sheet (narrow).

const ANSWER = 'You get 40 hours of sick leave. Tell your manager early.'
const CA = citation({
  marker: 1,
  sectionId: 'CA-4.3',
  passageId: 'p2',
  offsetUtf16: ANSWER.indexOf('.') + 1,
  groupName: 'California addendum',
})
const COMPANY = citation({
  marker: 2,
  sectionId: '4.3',
  passageId: 'p1',
  offsetUtf16: ANSWER.length,
  groupName: 'Time off',
})
const CA_MARKER = 'Source 1: Handbook CA-4.3, California addendum'
const CO_MARKER = 'Source 2: Handbook §4.3, Time off'

function signedIn(at = '/ask') {
  installFakeApi('priya')
  installAssistantApi({
    conversation: conversationOut({
      turns: [
        turnOut({
          id: 't-1',
          answerText: ANSWER,
          citations: [CA, COMPANY],
          toolCalls: [toolCall()],
        }),
      ],
    }),
  })
  const passages = installPassages()
  return { ...renderApp({ at }), passages }
}

const markers = (name: string) => screen.findAllByRole('button', { name })
const source = (router: { state: { location: { search: string } } }) =>
  new URLSearchParams(router.state.location.search).get('source')
const panel = () => screen.findByRole('complementary', { name: 'Handbook passage' })

beforeEach(() => {
  useChatStore.setState(useChatStore.getInitialState())
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the docked panel (a wide window)', () => {
  it('opens from a marker: the URL names the passage, the rail gives way, and focus is on the title', async () => {
    const { user, router, passages } = signedIn()
    const [marker] = await markers(CA_MARKER)
    expect(screen.getByRole('complementary', { name: 'Sandbox status' })).toBeInTheDocument()
    await user.click(marker!)

    const open = await panel()
    expect(source(router)).toBe('CA-4.3~p2')
    expect(passages.requests).toEqual([{ sectionId: 'CA-4.3', passageId: 'p2' }])
    const title = await within(open).findByRole('heading', { level: 2, name: 'Sick leave' })
    await waitFor(() => expect(title).toHaveFocus())
    expect(within(open).getByText('The p2 text of CA-4.3.')).toBeInTheDocument()
    // It takes the rail's place, 420 px wide, and is not modal.
    expect(screen.queryByRole('complementary', { name: 'Sandbox status' })).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('main').parentElement).toHaveClass(
      'grid-cols-[minmax(0,1fr)_var(--spacing-panel)]',
    )
    // Everything else is still reachable.
    expect(screen.getByRole('button', { name: 'Start a new conversation' })).toBeInTheDocument()
    // Every marker and chip of that passage's source says it is open.
    for (const button of screen.getAllByRole('button', { name: CA_MARKER })) {
      expect(button).toHaveAttribute('aria-expanded', 'true')
    }
    expect(screen.getAllByRole('button', { name: CO_MARKER })[0]).toHaveAttribute(
      'aria-expanded',
      'false',
    )
  })

  it('does not read the conversation again when the panel opens', async () => {
    const { user } = signedIn()
    const [marker] = await markers(CA_MARKER)
    let reads = 0
    const count = ({ request }: { request: Request }) => {
      if (new URL(request.url).pathname.endsWith('/assistant/conversations/current')) reads++
    }
    server.events.on('request:start', count)
    try {
      await user.click(marker!)
      await panel()
      expect(reads).toBe(0)
    } finally {
      server.events.removeListener('request:start', count)
    }
  })

  it('does not scroll the window to the top when a marker opens the panel', async () => {
    const { user } = signedIn()
    const [marker] = await markers(CA_MARKER)
    const scrollTo = vi.spyOn(window, 'scrollTo')
    await user.click(marker!)
    await panel()
    expect(scrollTo).not.toHaveBeenCalled()
    scrollTo.mockRestore()
  })

  it('closes when the same marker is pressed again, and puts focus back on it', async () => {
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await panel()
    await user.click(marker!)
    await waitFor(() =>
      expect(
        screen.queryByRole('complementary', { name: 'Handbook passage' }),
      ).not.toBeInTheDocument(),
    )
    expect(source(router)).toBeNull()
    expect(marker).toHaveFocus()
    expect(screen.getByRole('complementary', { name: 'Sandbox status' })).toBeInTheDocument()
  })

  it('closes with the panel’s own Close button, and focus returns to the marker', async () => {
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    const open = await panel()
    await user.click(within(open).getByRole('button', { name: 'Close passage' }))
    await waitFor(() => expect(source(router)).toBeNull())
    expect(marker).toHaveFocus()
  })

  it('closes with Escape from the marker, and from the composer, anywhere in the conversation', async () => {
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await panel()
    // Focus is on the panel's title after it opens. Put it back on the marker: Escape closes.
    marker!.focus()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(source(router)).toBeNull())
    expect(marker).toHaveFocus()

    await user.click(marker!)
    await panel()
    const box = screen.getByRole('textbox', { name: 'Ask Open Door' })
    box.focus()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(source(router)).toBeNull())
    // Focus returns to the opener, not to where Escape was pressed.
    expect(marker).toHaveFocus()
  })

  it('closes with Escape from inside the panel', async () => {
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await panel()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(source(router)).toBeNull())
    expect(marker).toHaveFocus()
  })

  it('goes back to the previous page once, not twice, when Escape closes a panel the page opened', async () => {
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await panel()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(source(router)).toBeNull())
    expect(router.state.location.pathname).toBe('/ask')
    expect(router.state.historyAction).toBe('POP')
  })

  it('replaces the passage when a different marker is pressed, moves focus to the title again, and returns to the newest opener', async () => {
    const { user, router, passages } = signedIn()
    const [first] = await markers(CA_MARKER)
    const [second] = await markers(CO_MARKER)
    await user.click(first!)
    await panel()
    await user.click(second!)

    await waitFor(() => expect(source(router)).toBe('4.3~p1'))
    expect(await screen.findByText('The p1 text of 4.3.')).toBeInTheDocument()
    expect(passages.requests.map((r) => `${r.sectionId}/${r.passageId}`)).toEqual([
      'CA-4.3/p2',
      '4.3/p1',
    ])
    const title = await screen.findByRole('heading', { level: 2, name: 'Sick leave' })
    await waitFor(() => expect(title).toHaveFocus())
    expect(first).toHaveAttribute('aria-expanded', 'false')
    expect(second).toHaveAttribute('aria-expanded', 'true')

    // One Back closes the panel however many passages were looked at.
    await act(async () => {
      await router.navigate(-1)
    })
    expect(source(router)).toBeNull()
    expect(router.state.location.pathname).toBe('/ask')
    // Close returns focus to the newest opener.
    await waitFor(() => expect(second).toHaveFocus())
  })

  it('closes when "Start a new conversation" replaces the conversation, by going back over the panel\'s step', async () => {
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await panel()
    await user.click(screen.getByRole('button', { name: 'Start a new conversation' }))
    await screen.findByRole('heading', { level: 1 })
    await waitFor(() => expect(source(router)).toBeNull())
    expect(
      screen.queryByRole('complementary', { name: 'Handbook passage' }),
    ).not.toBeInTheDocument()
    // The step the panel added is gone back over, so Back never stops on a step that changes
    // nothing.
    expect(router.state.historyAction).toBe('POP')
    // The marker it came from is gone, and focus is in the new composer, not a stale element.
    expect(await screen.findByRole('textbox', { name: 'Ask Open Door' })).toHaveFocus()
  })

  it('keeps the panel when a new conversation could not be started', async () => {
    const { user, router } = signedIn()
    server.use(
      http.post(`${window.location.origin}/api/v1/assistant/conversations`, () =>
        HttpResponse.json(null, { status: 500 }),
      ),
    )
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await panel()
    await user.click(screen.getByRole('button', { name: 'Start a new conversation' }))
    expect(await screen.findByText('Something went wrong sending that.')).toBeInTheDocument()
    expect(source(router)).toBe('CA-4.3~p2')
  })

  it('still closes by going back once after the passage was swapped', async () => {
    const { user, router } = signedIn()
    const [first] = await markers(CA_MARKER)
    const [second] = await markers(CO_MARKER)
    await user.click(first!)
    await panel()
    await user.click(second!)
    await waitFor(() => expect(source(router)).toBe('4.3~p1'))
    await user.keyboard('{Escape}')
    await waitFor(() => expect(source(router)).toBeNull())
    // Back over the one entry the panel added, not a replace that leaves a dead step behind.
    expect(router.state.historyAction).toBe('POP')
    expect(second).toHaveFocus()
  })

  it('leaves the panel open for Escape pressed outside the conversation, in the sidebar', async () => {
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await panel()
    const nav = screen.getByRole('link', { name: 'Directory' })
    nav.focus()
    await user.keyboard('{Escape}')
    expect(source(router)).toBe('CA-4.3~p2')
    expect(screen.getByRole('complementary', { name: 'Handbook passage' })).toBeInTheDocument()
  })

  it('closes with Back, and returns focus to the marker', async () => {
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await panel()
    await act(async () => {
      await router.navigate(-1)
    })
    await waitFor(() =>
      expect(
        screen.queryByRole('complementary', { name: 'Handbook passage' }),
      ).not.toBeInTheDocument(),
    )
    expect(marker).toHaveFocus()
  })

  it('opens from a source chip with the first passage cited from its section, and focus returns to the chip', async () => {
    const { user, router } = signedIn()
    const chip = (await screen.findByRole('list', { name: 'Sources' })).querySelector(
      '[data-slot="source-chip"][data-passage-id="4.3~p1"]',
    ) as HTMLElement
    await user.click(chip)
    await panel()
    expect(source(router)).toBe('4.3~p1')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(source(router)).toBeNull())
    expect(chip).toHaveFocus()
  })

  it('keeps two sections’ same-numbered passages apart (both are p1)', async () => {
    const { user, router, passages } = signedIn()
    installFakeApi('priya')
    server.use(
      http.get(`${window.location.origin}/api/v1/assistant/conversations/current`, () =>
        HttpResponse.json(
          conversationOut({
            turns: [
              turnOut({
                id: 't-1',
                answerText: ANSWER,
                citations: [{ ...CA, passageId: 'p1' }, COMPANY],
              }),
            ],
          }),
        ),
      ),
    )
    const markersOf = await markers(CA_MARKER)
    await user.click(markersOf[0]!)
    await panel()
    expect(source(router)).toBe('CA-4.3~p1')
    // The company section's marker is not open just because it too cites p1.
    expect(screen.getAllByRole('button', { name: CO_MARKER })[0]).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    expect(passages.requests.at(-1)).toEqual({ sectionId: 'CA-4.3', passageId: 'p1' })
  })

  it('opens from a URL with a passage in it, and closing replaces the address', async () => {
    const { user, router } = signedIn('/ask?source=CA-4.3~p2')
    const open = await panel()
    expect(await within(open).findByText('The p2 text of CA-4.3.')).toBeInTheDocument()
    await user.click(within(open).getByRole('button', { name: 'Close passage' }))
    await waitFor(() => expect(source(router)).toBeNull())
    expect(router.state.historyAction).toBe('REPLACE')
  })

  it('shows the section and group in the eyebrow while the passage loads, then the passage', async () => {
    installFakeApi('priya')
    installAssistantApi({
      conversation: conversationOut({
        turns: [turnOut({ id: 't-1', answerText: ANSWER, citations: [CA, COMPANY] })],
      }),
    })
    let release!: () => void
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    installPassages()
    server.use(
      http.get(`${window.location.origin}/api/v1/handbook/sections/:s/passages/:p`, async () => {
        await held
        return HttpResponse.json({ never: true }, { status: 500 })
      }),
    )
    renderApp({ at: '/ask?source=CA-4.3~p2' })
    const open = await panel()
    expect(
      await within(open).findByText('Handbook CA-4.3 · California addendum'),
    ).toBeInTheDocument()
    expect(open).toHaveAttribute('aria-busy', 'true')
    release()
  })

  it('shows the panel’s error, with Retry, when the passage cannot be read', async () => {
    installFakeApi('priya')
    installAssistantApi({
      conversation: conversationOut({
        turns: [turnOut({ id: 't-1', answerText: ANSWER, citations: [CA] })],
      }),
    })
    const passages = installPassages({ failing: true })
    const { user } = renderApp({ at: '/ask?source=CA-4.3~p2' })
    const open = await panel()
    expect(await within(open).findByText(/Couldn't load this passage/)).toBeInTheDocument()
    passages.recover()
    await user.click(within(open).getByRole('button', { name: 'Retry' }))
    expect(await within(open).findByText('The p2 text of CA-4.3.')).toBeInTheDocument()
  })

  it('ignores a source value that names no passage', async () => {
    signedIn('/ask?source=nonsense')
    await markers(CA_MARKER)
    expect(
      screen.queryByRole('complementary', { name: 'Handbook passage' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Sandbox status' })).toBeInTheDocument()
  })

  it('shows no panel, and fetches no passage, where there is no conversation to cite: not while loading, nor on the home', async () => {
    installFakeApi('priya')
    installAssistantApi()
    const passages = installPassages()
    const { router } = renderApp({ at: '/ask?source=CA-4.3~p2' })
    // The wait for the conversation, then the home, which closes a stale link by replacing it.
    expect(
      screen.queryByRole('complementary', { name: 'Handbook passage' }),
    ).not.toBeInTheDocument()
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await waitFor(() => expect(source(router)).toBeNull())
    expect(
      screen.queryByRole('complementary', { name: 'Handbook passage' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(passages.requests).toEqual([])
  })

  it('shows no sheet on the home for a stale link in a narrow window either', async () => {
    stubMediaQuery(true)
    installFakeApi('priya')
    installAssistantApi()
    const passages = installPassages()
    const { router } = renderApp({ at: '/ask?source=CA-4.3~p2' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await screen.findByRole('textbox', { name: 'Ask Open Door' })
    await waitFor(() => expect(source(router)).toBeNull())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(passages.requests).toEqual([])
  })

  it('shows no panel on another page, whatever the URL says', async () => {
    installFakeApi('priya')
    installAssistantApi()
    installPassages()
    // It opens the directory, whose requests need answers too.
    installFakeDirectory('priya')
    const { queryClient } = renderApp({ at: '/directory?source=CA-4.3~p2' })
    await screen.findByRole('heading', { name: 'Directory' })
    await screen.findByRole('list', { name: 'People' })
    await waitFor(() => expect(queryClient.isFetching()).toBe(0))
    expect(
      screen.queryByRole('complementary', { name: 'Handbook passage' }),
    ).not.toBeInTheDocument()
  })

  it('comes last in the Tab order, after the composer and Ask', async () => {
    const { user } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    const open = await panel()
    const close = within(open).getByRole('button', { name: 'Close passage' })
    const ask = screen.getByRole('button', { name: 'Ask' })
    expect(ask.compareDocumentPosition(close) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    const box = screen.getByRole('textbox', { name: 'Ask Open Door' })
    box.focus()
    await user.tab()
    expect(ask).toHaveFocus()
    await user.tab()
    // The panel's own controls come next (its Close button).
    expect(document.activeElement).toBe(close)
  })
})

describe('the sheet (a narrow window)', () => {
  function narrow() {
    return stubMediaQuery(true)
  }

  it('opens as a modal sheet with focus inside, and hides the page behind it', async () => {
    narrow()
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)

    const dialog = await screen.findByRole('dialog')
    expect(source(router)).toBe('CA-4.3~p2')
    const title = await within(dialog).findByRole('heading', { level: 2, name: 'Sick leave' })
    await waitFor(() => expect(title).toHaveFocus())
    expect(dialog).toContainElement(document.activeElement as HTMLElement)
    // The page behind is out of reach for a screen reader, and the rail is still in the page.
    expect(
      screen.queryByRole('button', { name: 'Start a new conversation' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Ask Open Door' })).not.toBeInTheDocument()
    // One panel, the sheet: not also a docked one in the rail's place, and no second landmark in it.
    expect(
      screen.queryAllByRole('complementary', { name: 'Handbook passage', hidden: true }),
    ).toHaveLength(0)
    expect(screen.getByRole('main').parentElement).not.toHaveClass(
      'grid-cols-[minmax(0,1fr)_var(--spacing-panel)]',
    )
    // One name, the visible title, and one heading.
    expect(dialog).toHaveAccessibleName('Sick leave')
    expect(dialog).not.toHaveAttribute('aria-label')
    expect(within(dialog).getAllByRole('heading')).toHaveLength(1)
    // The same header (eyebrow, title, close) and footer ("Open in handbook").
    expect(within(dialog).getByText('Handbook CA-4.3 · California addendum')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Close passage' })).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: /Open in handbook/ })).toHaveAttribute(
      'href',
      '/handbook/CA-4.3?passage=p2',
    )
  })

  it('is named by the eyebrow while the passage loads', async () => {
    narrow()
    installFakeApi('priya')
    installAssistantApi({
      conversation: conversationOut({
        turns: [turnOut({ id: 't-1', answerText: ANSWER, citations: [CA, COMPANY] })],
      }),
    })
    let release!: () => void
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    installPassages()
    server.use(
      http.get(`${window.location.origin}/api/v1/handbook/sections/:s/passages/:p`, async () => {
        await held
        return HttpResponse.json({ never: true }, { status: 500 })
      }),
    )
    renderApp({ at: '/ask?source=CA-4.3~p2' })
    const dialog = await screen.findByRole('dialog')
    await waitFor(() =>
      expect(dialog).toHaveAccessibleName('Handbook CA-4.3 · California addendum'),
    )
    release()
  })

  it('keeps Tab inside the sheet', async () => {
    narrow()
    const { user } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    const dialog = await screen.findByRole('dialog')
    for (let i = 0; i < 8; i++) {
      await user.tab()
      expect(dialog).toContainElement(document.activeElement as HTMLElement)
    }
  })

  it('closes with Close, and focus returns to the marker', async () => {
    narrow()
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Close passage' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(source(router)).toBeNull()
    expect(marker).toHaveFocus()
  })

  it('closes with Escape, once', async () => {
    narrow()
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await screen.findByRole('dialog')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(source(router)).toBeNull()
    expect(router.state.historyAction).toBe('POP')
    expect(router.state.location.pathname).toBe('/ask')
    expect(marker).toHaveFocus()
  })

  it('closes with a swipe down on the handle', async () => {
    narrow()
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await screen.findByRole('dialog')
    const handle = document.querySelector('[data-slot="bottom-sheet-handle"]')!
    fireEvent.pointerDown(handle, { clientY: 100, pointerId: 1, button: 0 })
    fireEvent.pointerMove(handle, { clientY: 260, pointerId: 1 })
    fireEvent.pointerUp(handle, { clientY: 260, pointerId: 1 })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(source(router)).toBeNull()
    expect(marker).toHaveFocus()
  })

  it('closes with Back', async () => {
    narrow()
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await screen.findByRole('dialog')
    await act(async () => {
      await router.navigate(-1)
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(marker).toHaveFocus()
  })

  it('becomes the docked panel when the window widens, and the sheet again when it narrows', async () => {
    const media = narrow()
    const { user } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await screen.findByRole('dialog')
    act(() => media.set(false))
    expect(
      await screen.findByRole('complementary', { name: 'Handbook passage' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    act(() => media.set(true))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('asks the media query for the sheet’s breakpoint, below 1280 px', async () => {
    const media = narrow()
    signedIn()
    await markers(CA_MARKER)
    expect(media.queries()).toContain('(max-width: 1279px)')
  })
})

describe('the panel’s group-name lookup', () => {
  it('finds the group of a passage cited in a turn that waits for its saved copy', async () => {
    installFakeApi('priya')
    installAssistantApi()
    let release!: () => void
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    installPassages()
    server.use(
      http.get(`${window.location.origin}/api/v1/handbook/sections/:s/passages/:p`, async () => {
        await held
        return HttpResponse.json({ never: true }, { status: 500 })
      }),
    )
    const waiting = {
      turnId: 't-1',
      question: 'Sick days?',
      steps: [],
      text: ANSWER,
      citations: [CA, COMPANY],
      escalation: null,
      proposals: [],
      error: null,
      completed: true,
      incomplete: false,
      accepted: true,
      toolInputs: {},
    }
    useChatStore.setState({ settling: [{ turn: waiting, phase: 'stopped' }] })
    renderApp({ at: '/ask?source=CA-4.3~p2' })
    const open = await panel()
    expect(
      await within(open).findByText('Handbook CA-4.3 · California addendum'),
    ).toBeInTheDocument()
    release()
  })

  it('numbers the citations again only when they change, not on every render of the panel', async () => {
    const withKeys = vi.spyOn(sourceKeys, 'withSourceKeys')
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    const open = await panel()
    await within(open).findByText('The p2 text of CA-4.3.')
    // The page redraws (the address gains an unrelated parameter) and the conversation has not
    // changed: no new numbering of the citations, so the remembered result is used.
    // (The thread's own turns ask for the same arrays again, which their remembered result answers.)
    const seen = new Set(withKeys.mock.calls.map((call) => call[0]))
    withKeys.mockClear()
    await act(async () => {
      await router.navigate(
        `${router.state.location.pathname}${router.state.location.search}&x=1`,
        {
          replace: true,
        },
      )
    })
    expect(source(router)).toBe('CA-4.3~p2')
    expect(withKeys.mock.calls.filter((call) => !seen.has(call[0]))).toEqual([])
    withKeys.mockRestore()
  })
})

describe('what the panel leaves behind', () => {
  it('forgets the opener when the conversation page goes away, so a later marker is not focused', async () => {
    const { user, router } = signedIn()
    const [marker] = await markers(CA_MARKER)
    await user.click(marker!)
    await panel()
    await act(async () => {
      await router.navigate('/handbook')
    })
    await waitFor(() => expect(router.state.location.pathname).toBe('/handbook'))
    // Another marker for the same passage appears (another page, another persona): not focused.
    const other = document.createElement('button')
    other.dataset.slot = 'citation-marker'
    other.dataset.passageId = 'CA-4.3~p2'
    document.body.append(other)
    returnFocusToOpener()
    expect(other).not.toHaveFocus()
    other.remove()
  })
})
