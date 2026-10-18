import { QueryClient } from '@tanstack/react-query'
import { HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CitationOut } from '@/api/generated'
import { resetIdentity } from '@/lib/identity'
import * as streamModule from '@/lib/stream-turn'
import { citation } from '@/test/assistant-fixtures'
import { stubAbsoluteUrls } from '@/test/absolute-urls'
import {
  CONVERSATION_ID,
  TEXTS,
  TURN_ID,
  eventStream,
  onTurn,
  openStream,
  problemResponse,
} from '@/test/fake-assistant'
import { useChatStore, type SendDeps } from './store'

const state = () => useChatStore.getState()
const NEW_CONVERSATION = 'c0ffee00-0000-4000-8000-0000000000bb'

function makeDeps(overrides: Partial<SendDeps> = {}) {
  const deps = {
    conversationId: CONVERSATION_ID as string | null,
    createConversation: vi.fn<() => Promise<string>>(() => Promise.resolve(NEW_CONVERSATION)),
    invalidateConversation: vi.fn<() => void>(),
    forgetConversation: vi.fn<() => void>(),
    onUnauthorized: vi.fn<() => void>(),
    texts: TEXTS,
    ...overrides,
  }
  return deps
}

const started: [event: string, data: unknown] = ['turn.started', { turnId: TURN_ID }]
const completedData = {
  turnId: TURN_ID,
  servedBy: 'anthropic',
  usage: { inputTokens: 1, outputTokens: 1 },
}
const completed: [event: string, data: unknown] = ['turn.completed', completedData]

beforeEach(() => {
  stubAbsoluteUrls()
  resetIdentity(new QueryClient())
})
afterEach(() => {
  resetIdentity(new QueryClient())
})

describe('the draft', () => {
  it('starts empty', () => {
    expect(state()).toMatchObject({
      draft: '',
      status: 'idle',
      turn: null,
      sendError: null,
      warning: null,
      offerNewConversation: false,
    })
  })

  it('keeps what the person types, and drops a send error that was about older text', () => {
    useChatStore.setState({ sendError: 'Something went wrong sending that.' })
    state().setDraft('How many sick days do I get?')
    expect(state().draft).toBe('How many sick days do I get?')
    expect(state().sendError).toBeNull()
  })
})

describe('the state machine', () => {
  it('goes idle, sending, streaming, idle, and builds the live turn from the events', async () => {
    const stream = openStream()
    const posted = onTurn(() => stream.response())
    const deps = makeDeps()
    state().setDraft('How many sick days do I get?')

    const sending = state().send('How many sick days do I get?', deps)
    expect(state().status).toBe('sending')
    expect(state().turn).toMatchObject({ question: 'How many sick days do I get?', turnId: null })
    await vi.waitFor(() => expect(posted).toHaveLength(1))

    stream.push(...started)
    await vi.waitFor(() => expect(state().status).toBe('streaming'))
    expect(state().turn?.turnId).toBe(TURN_ID)
    // The server took the question, so the box empties.
    expect(state().draft).toBe('')

    stream.push('status', { text: 'Searching the handbook…' })
    await vi.waitFor(() =>
      expect(state().turn?.steps).toEqual([
        { id: 'status-0', text: 'Searching the handbook…', done: false },
      ]),
    )

    stream.push('tool.started', {
      id: 't1',
      name: 'search_handbook',
      summary: "query='sick leave'",
    })
    await vi.waitFor(() => expect(state().turn?.steps[0]?.id).toBe('tool-t1'))
    // The tool takes over the status line that said the same thing: one step, running.
    expect(state().turn?.steps).toEqual([
      { id: 'tool-t1', text: 'Searching the handbook…', done: false },
    ])

    stream.push('tool.finished', { id: 't1', ok: true, summary: '3 results', durationMs: 90 })
    await vi.waitFor(() => expect(state().turn?.steps[0]?.done).toBe(true))
    expect(state().turn?.steps[0]?.text).toBe('Searched the handbook: sick leave')

    stream.push('text.delta', { text: 'You get ' })
    stream.push('text.delta', { text: '5 days.' })
    await vi.waitFor(() => expect(state().turn?.text).toBe('You get 5 days.'))
    expect(state().status).toBe('streaming')

    stream.push(...completed)
    stream.close()
    await sending
    expect(state().status).toBe('idle')
    // The finished turn stays until the server's copy arrives.
    expect(state().turn).toMatchObject({
      completed: true,
      text: 'You get 5 days.',
      turnId: TURN_ID,
    })
    expect(state().turn?.steps.every((step) => step.done)).toBe(true)
  })

  it('finishes every step when the turn ends, so no spinner is left turning', async () => {
    onTurn(() =>
      eventStream(
        started,
        ['status', { text: 'Working…' }],
        ['tool.started', { id: 't1', name: 'get_my_profile', summary: '' }],
        completed,
      ),
    )
    await state().send('Who am I?', makeDeps())
    expect(state().turn?.steps.map((step) => step.done)).toEqual([true, true])
  })

  describe('steps', () => {
    const search = (id: string): [string, unknown] => [
      'tool.started',
      { id, name: 'search_handbook', summary: "query='sick leave'" },
    ]
    const searched = (id: string): [string, unknown] => [
      'tool.finished',
      { id, ok: true, summary: '3 results', durationMs: 90 },
    ]

    it('shows a running tool in the present tense, then the past tense when it finishes', async () => {
      const stream = openStream()
      onTurn(() => stream.response())
      void state().send('Sick days?', makeDeps())
      stream.push(...started)
      stream.push(...search('t1'))
      await vi.waitFor(() => expect(state().turn?.steps).toHaveLength(1))
      expect(state().turn?.steps[0]).toEqual({
        id: 'tool-t1',
        text: 'Searching the handbook…',
        done: false,
      })
      stream.push(...searched('t1'))
      await vi.waitFor(() => expect(state().turn?.steps[0]?.done).toBe(true))
      expect(state().turn?.steps[0]?.text).toBe('Searched the handbook: sick leave')
      stream.close()
    })

    it('says "again" for a later search in the same turn', async () => {
      onTurn(() => eventStream(started, search('t1'), searched('t1'), search('t2')))
      await state().send('Sick days?', makeDeps())
      expect(state().turn?.steps.map((step) => step.text)).toEqual([
        'Searched the handbook: sick leave',
        'Searching the handbook again…',
      ])
    })

    it('words the profile and directory tools', async () => {
      onTurn(() =>
        eventStream(
          started,
          ['tool.started', { id: 'p', name: 'get_my_profile', summary: '' }],
          [
            'tool.started',
            { id: 'd', name: 'find_people', summary: "scope=directory, query='Ana'" },
          ],
        ),
      )
      await state().send('Who?', makeDeps())
      expect(state().turn?.steps.map((step) => step.text)).toEqual([
        'Looking up your profile…',
        'Searching the directory…',
      ])
    })

    it('adds its own line when the status line says something else', async () => {
      const stream = openStream()
      onTurn(() => stream.response())
      void state().send('Sick days?', makeDeps())
      stream.push(...started)
      stream.push('status', { text: 'Let me check.' })
      stream.push(...search('t1'))
      await vi.waitFor(() => expect(state().turn?.steps).toHaveLength(2))
      expect(state().turn?.steps).toEqual([
        { id: 'status-0', text: 'Let me check.', done: true },
        { id: 'tool-t1', text: 'Searching the handbook…', done: false },
      ])
      stream.close()
    })

    it('does not take over a status line that text has already finished', async () => {
      const stream = openStream()
      onTurn(() => stream.response())
      void state().send('Sick days?', makeDeps())
      stream.push(...started)
      stream.push('status', { text: 'Searching the handbook…' })
      stream.push('text.delta', { text: 'Let me look. ' })
      stream.push(...search('t1'))
      await vi.waitFor(() => expect(state().turn?.steps).toHaveLength(2))
      expect(state().turn?.steps.map((step) => [step.id, step.done])).toEqual([
        ['status-0', true],
        ['tool-t1', false],
      ])
      stream.close()
    })

    it('does not take over a status line that has already finished', async () => {
      onTurn(() =>
        eventStream(
          started,
          ['status', { text: 'Searching the handbook…' }],
          ['status', { text: 'Reading the results…' }],
          search('t1'),
        ),
      )
      await state().send('Sick days?', makeDeps())
      expect(state().turn?.steps.map((step) => step.id)).toEqual([
        'status-0',
        'status-1',
        'tool-t1',
      ])
    })
  })

  it('marks a failed tool call as failed', async () => {
    onTurn(() =>
      eventStream(
        started,
        [
          'tool.started',
          { id: 't1', name: 'find_people', summary: "scope=directory, query='Ana'" },
        ],
        ['tool.finished', { id: 't1', ok: false, summary: 'timed out', durationMs: 30000 }],
        completed,
      ),
    )
    await state().send('Who is Ana?', makeDeps())
    expect(state().turn?.steps).toEqual([
      { id: 'tool-t1', text: 'Looked up the directory: Ana (failed)', done: true },
    ])
  })

  it('takes back the text and citations on text.retracted, and the note arrives as a status line', async () => {
    onTurn(() =>
      eventStream(
        started,
        ['text.delta', { text: 'Let me look that up first. ' }],
        ['citation', citation({ marker: 1, offsetUtf16: 5 })],
        ['text.retracted', {}],
        ['status', { text: 'Let me look that up first.' }],
        ['text.delta', { text: 'You get 5 days.' }],
        completed,
      ),
    )
    await state().send('Sick days?', makeDeps())
    expect(state().turn?.text).toBe('You get 5 days.')
    expect(state().turn?.citations).toEqual([])
    // Once: the retraction itself adds no line, the server's status event does.
    expect(state().turn?.steps.map((step) => step.text)).toEqual(['Let me look that up first.'])
  })

  it('numbers citations by section as they arrive, once, so the components never do', async () => {
    const raw: CitationOut[] = [
      citation({ marker: 1, passageId: 'CA-4.3~p1', offsetUtf16: 10 }),
      citation({ marker: 2, passageId: 'CA-4.3~p2', offsetUtf16: 30 }),
      citation({ marker: 3, sectionId: '4.3', passageId: '4.3~p3', offsetUtf16: 50 }),
    ]
    onTurn(() =>
      eventStream(started, ...raw.map((c) => ['citation', c] as [string, unknown]), completed),
    )
    await state().send('Sick days?', makeDeps())
    expect(state().turn?.citations.map((c) => [c.passageId, c.marker])).toEqual([
      ['CA-4.3~p1', 1],
      ['CA-4.3~p2', 1],
      ['4.3~p3', 2],
    ])
  })

  it('keeps an escalation, flagged as live, so only it is announced', async () => {
    onTurn(() =>
      eventStream(
        started,
        [
          'escalation',
          { kind: 'sensitive', message: 'A person handles this.', hrContact: [], offerCase: false },
        ],
        completed,
      ),
    )
    await state().send('I want to report harassment', makeDeps())
    expect(state().turn?.escalation).toMatchObject({ kind: 'sensitive', live: true })
  })

  it('marks an answer the output limit cut off', async () => {
    onTurn(() => eventStream(started, ['turn.completed', { ...completedData, incomplete: true }]))
    await state().send('Sick days?', makeDeps())
    expect(state().turn?.incomplete).toBe(true)
  })
})

describe('turn.completed', () => {
  it('asks for the conversation again, once, and leaves the live turn showing', async () => {
    onTurn(() => eventStream(started, ['text.delta', { text: 'Hi.' }], completed))
    const deps = makeDeps()
    await state().send('Hello', deps)
    expect(deps.invalidateConversation).toHaveBeenCalledTimes(1)
    expect(state().turn?.text).toBe('Hi.')
  })

  it('ends the live turn only for the turn the refetch holds', async () => {
    onTurn(() => eventStream(started, completed))
    await state().send('Hello', makeDeps())
    state().settle('some-other-turn')
    expect(state().turn).not.toBeNull()
    state().settle(TURN_ID)
    expect(state().turn).toBeNull()
    expect(state().status).toBe('idle')
  })

  it('does not end a turn that has not completed', async () => {
    const stream = openStream()
    onTurn(() => stream.response())
    void state().send('Hello', makeDeps())
    stream.push(...started)
    await vi.waitFor(() => expect(state().turn?.turnId).toBe(TURN_ID))
    state().settle(TURN_ID)
    expect(state().turn).not.toBeNull()
  })
})

describe('Stop', () => {
  it('aborts the stream, shows the turn as stopped with its partial text, and refetches', async () => {
    const stream = openStream()
    onTurn(() => stream.response())
    const deps = makeDeps()
    const sending = state().send('Sick days?', deps)
    stream.push(...started)
    stream.push('status', { text: 'Searching the handbook…' })
    stream.push('text.delta', { text: 'You get ' })
    await vi.waitFor(() => expect(state().turn?.text).toBe('You get '))

    state().stop(deps)
    expect(state().status).toBe('stopped')
    expect(state().turn).toMatchObject({ text: 'You get ', completed: false })
    expect(state().turn?.steps.every((step) => step.done)).toBe(true)
    expect(deps.invalidateConversation).toHaveBeenCalledTimes(1)
    await sending

    // Anything still on its way is dropped.
    stream.push('text.delta', { text: 'LATE' })
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(state().turn?.text).toBe('You get ')
    expect(state().status).toBe('stopped')
  })

  it('does nothing when no answer is coming', () => {
    const deps = makeDeps()
    state().stop(deps)
    expect(state().status).toBe('idle')
    expect(deps.invalidateConversation).not.toHaveBeenCalled()
  })

  it('lets the next question go out', async () => {
    const stream = openStream()
    const posted = onTurn((question) =>
      question === 'again' ? eventStream(started, completed) : stream.response(),
    )
    const deps = makeDeps()
    void state().send('first', deps)
    await vi.waitFor(() => expect(posted).toHaveLength(1))
    stream.push(...started)
    await vi.waitFor(() => expect(state().status).toBe('streaming'))
    state().stop(deps)
    await state().send('again', deps)
    expect(posted.map((p) => p.question)).toEqual(['first', 'again'])
    expect(state().status).toBe('idle')
    expect(state().turn?.question).toBe('again')
  })
})

describe('one question at a time', () => {
  it('keeps the draft and shows "still answering" when the server says a turn is running', async () => {
    onTurn(() => problemResponse(409, 'turn-running', 'ignored: the texts route has the words'))
    state().setDraft('Second question')
    await state().send('Second question', makeDeps())
    expect(state().sendError).toBe(TEXTS.stillAnswering)
    expect(state().draft).toBe('Second question')
    expect(state().status).toBe('idle')
    expect(state().turn).toBeNull()
  })

  it('sends nothing, and says "still answering", when Enter is pressed while an answer streams', async () => {
    const stream = openStream()
    const posted = onTurn(() => stream.response())
    const deps = makeDeps()
    void state().send('First', deps)
    stream.push(...started)
    await vi.waitFor(() => expect(state().status).toBe('streaming'))

    state().setDraft('Second')
    await state().send('Second', deps)
    expect(posted).toHaveLength(1)
    expect(state().sendError).toBe(TEXTS.stillAnswering)
    expect(state().draft).toBe('Second')
    expect(state().turn?.question).toBe('First')
    expect(state().status).toBe('streaming')
    stream.close()
  })

  it('sends nothing while the first send is still on its way', async () => {
    const posted = onTurn(() => new Promise<never>(() => {}) as never)
    const deps = makeDeps()
    void state().send('First', deps)
    await vi.waitFor(() => expect(posted).toHaveLength(1))
    expect(state().status).toBe('sending')
    await state().send('Second', deps)
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(posted).toHaveLength(1)
    expect(state().sendError).toBe(TEXTS.stillAnswering)
  })
})

describe('what is sent', () => {
  it('sends the trimmed question', async () => {
    const posted = onTurn(() => eventStream(started, completed))
    await state().send('   How many sick days?　\n ', makeDeps())
    expect(posted[0]?.question).toBe('How many sick days?')
    expect(state().turn?.question).toBe('How many sick days?')
  })

  it('does not send a blank question', async () => {
    const posted = onTurn(() => eventStream(started, completed))
    const deps = makeDeps()
    await state().send('   \n  ', deps)
    expect(posted).toHaveLength(0)
    expect(state().status).toBe('idle')
    expect(state().turn).toBeNull()
    expect(deps.createConversation).not.toHaveBeenCalled()
  })

  it('does not send a question that looks like a Social Security or card number', async () => {
    const posted = onTurn(() => eventStream(started, completed))
    const deps = makeDeps()
    state().setDraft('My SSN is 123-45-6789')
    await state().send('My SSN is 123-45-6789', deps)
    expect(posted).toHaveLength(0)
    expect(state().warning).toBe(TEXTS.personalData)
    expect(state().draft).toBe('My SSN is 123-45-6789')
    expect(state().status).toBe('idle')

    // Taking the number out clears the warning, and a number still in it does not.
    state().setDraft('My SSN is 123-45-6789!')
    expect(state().warning).toBe(TEXTS.personalData)
    state().setDraft('My SSN is private')
    expect(state().warning).toBeNull()
  })

  it('shows the warning if the server refuses a number the check let through', async () => {
    onTurn(() => problemResponse(422, 'personal-data', 'ignored'))
    await state().send('a question', makeDeps())
    expect(state().warning).toBe(TEXTS.personalData)
  })

  it('goes to the conversation it is given, with the CSRF token', async () => {
    document.cookie = '__Host-od_csrf=tok-1; Secure; Path=/'
    const posted = onTurn(() => eventStream(started, completed))
    await state().send('Hello', makeDeps())
    expect(posted[0]).toMatchObject({ conversationId: CONVERSATION_ID, csrf: 'tok-1' })
    document.cookie = '__Host-od_csrf=; Secure; Path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  })

  it('creates the conversation first when there is none, and asks in it', async () => {
    const posted = onTurn(() => eventStream(started, completed))
    const deps = makeDeps({ conversationId: null })
    await state().send('Hello', deps)
    expect(deps.createConversation).toHaveBeenCalledTimes(1)
    expect(posted[0]?.conversationId).toBe(NEW_CONVERSATION)
    expect(state().conversationId).toBe(NEW_CONVERSATION)
  })

  it('keeps the draft if creating the conversation fails', async () => {
    const posted = onTurn(() => eventStream(started, completed))
    const deps = makeDeps({
      conversationId: null,
      createConversation: vi.fn<() => Promise<string>>(() => Promise.reject(new Error('down'))),
    })
    state().setDraft('Hello')
    await state().send('Hello', deps)
    expect(posted).toHaveLength(0)
    expect(state().draft).toBe('Hello')
    expect(state().sendError).toBe('Something went wrong sending that.')
  })

  it('keeps text typed after the question was sent', async () => {
    const stream = openStream()
    onTurn(() => stream.response())
    state().setDraft('First')
    void state().send('First', makeDeps())
    state().setDraft('First, and then more')
    stream.push(...started)
    await vi.waitFor(() => expect(state().turn?.turnId).toBe(TURN_ID))
    expect(state().draft).toBe('First, and then more')
    stream.close()
  })
})

describe('a send that fails', () => {
  it.each([
    [
      'a server error with a message',
      () => problemResponse(500, 'about:blank', 'The server broke.'),
      'The server broke.',
    ],
    [
      'a response that is not a problem',
      () => new HttpResponse('<html>Bad gateway</html>', { status: 502 }),
      'Something went wrong sending that.',
    ],
    ['a network failure', () => HttpResponse.error(), 'Something went wrong sending that.'],
  ])('keeps the draft after %s', async (_name, response, message) => {
    onTurn(response)
    state().setDraft('Keep me')
    await state().send('Keep me', makeDeps())
    expect(state().draft).toBe('Keep me')
    expect(state().sendError).toBe(message)
    expect(state().status).toBe('idle')
    expect(state().turn).toBeNull()
  })

  it('asks the session guard to check who is signed in after a 401', async () => {
    onTurn(() => problemResponse(401, 'about:blank', 'Not signed in'))
    const deps = makeDeps()
    await state().send('Hello', deps)
    expect(deps.onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it.each(['conversation-outdated', 'history-too-long'])(
    "keeps the draft, shows the API's text, and offers a new conversation after %s",
    async (type) => {
      onTurn(() => problemResponse(409, type, "This conversation can't continue. Start a new one."))
      state().setDraft('Hello')
      await state().send('Hello', makeDeps())
      expect(state().sendError).toBe("This conversation can't continue. Start a new one.")
      expect(state().offerNewConversation).toBe(true)
      expect(state().draft).toBe('Hello')
    },
  )

  it.each(['budget-sandbox', 'budget-daily'])(
    'keeps the draft, asks again, and says the problem’s words under the box (the banner, if it shows, wins there) after a 429 %s',
    async (type) => {
      onTurn(() => problemResponse(429, type, 'The limit was reached.'))
      const deps = makeDeps()
      state().setDraft('Hello')
      await state().send('Hello', deps)
      expect(deps.invalidateConversation).toHaveBeenCalledTimes(1)
      expect(state().draft).toBe('Hello')
      expect(state().sendError).toBe('The limit was reached.')
      expect(state().status).toBe('idle')
    },
  )

  it('does not ask again for a 429 that is not a budget stop', async () => {
    onTurn(() => problemResponse(429, 'rate-limited', 'Slow down.'))
    const deps = makeDeps()
    await state().send('Hello', deps)
    expect(deps.invalidateConversation).not.toHaveBeenCalled()
  })

  it('clears the offer for a new conversation on the next send', async () => {
    useChatStore.setState({ offerNewConversation: true })
    onTurn(() => eventStream(started, completed))
    await state().send('Hello', makeDeps())
    expect(state().offerNewConversation).toBe(false)
  })
})

describe('an error in the middle of an answer', () => {
  it("puts the turn in error with the event's message, and keeps the partial answer", async () => {
    onTurn(() =>
      eventStream(
        started,
        ['text.delta', { text: 'You get ' }],
        [
          'error',
          { code: 'internal', message: 'Something went wrong on our side.', requestId: 'r1' },
        ],
      ),
    )
    const deps = makeDeps()
    await state().send('Sick days?', deps)
    expect(state().status).toBe('error')
    expect(state().turn).toMatchObject({
      text: 'You get ',
      error: { code: 'internal', message: 'Something went wrong on our side.' },
    })
    // The failed turn is stored, so the conversation is read again to hold it.
    expect(deps.invalidateConversation).toHaveBeenCalledTimes(1)
  })

  it('still takes an escalation that follows the error', async () => {
    onTurn(() =>
      eventStream(
        started,
        ['error', { code: 'internal', message: 'Something went wrong.', requestId: null }],
        [
          'escalation',
          { kind: 'unavailable', message: "Can't answer.", hrContact: [], offerCase: false },
        ],
      ),
    )
    await state().send('Sick days?', makeDeps())
    expect(state().status).toBe('error')
    expect(state().turn?.escalation?.kind).toBe('unavailable')
  })

  it.each(['budget-sandbox', 'budget-daily', 'spend-limit'])(
    'asks for the conversation again after the %s error, so the banner comes from it',
    async (code) => {
      onTurn(() => eventStream(started, ['error', { code, message: 'Words.', requestId: null }]))
      const deps = makeDeps()
      await state().send('Sick days?', deps)
      expect(deps.invalidateConversation).toHaveBeenCalledTimes(1)
      expect(state().status).toBe('error')
      // An error event is the turn's own, shown in its message: nothing is set under the box.
      expect(state().sendError).toBeNull()
    },
  )

  it('lets Retry send the same question again', async () => {
    let calls = 0
    const posted = onTurn(() =>
      ++calls === 1
        ? eventStream(started, ['error', { code: 'internal', message: 'Oops.', requestId: null }])
        : eventStream(started, completed),
    )
    const deps = makeDeps()
    await state().send('Sick days?', deps)
    await state().send(state().turn!.question, deps)
    expect(posted.map((p) => p.question)).toEqual(['Sick days?', 'Sick days?'])
    expect(state().status).toBe('idle')
    expect(state().turn?.error).toBeNull()
  })
})

describe('what a send clears from the box', () => {
  it('empties the box when the server takes a question typed in the composer', async () => {
    onTurn(() => eventStream(started, completed))
    state().setDraft('Sick days?')
    await state().send('Sick days?', makeDeps())
    expect(state().draft).toBe('')
  })

  it.each([['Retry or Ask again'], ['Try again']])(
    'leaves a draft typed since alone when %s re-sends a question, even one that matches',
    async () => {
      onTurn(() => eventStream(started, completed))
      state().setDraft('Sick days?')
      await state().send('Sick days?', makeDeps(), 'again')
      expect(state().draft).toBe('Sick days?')
    },
  )
})

describe('a connection that drops', () => {
  it('shows the partial answer as stopped when it drops after the turn began', async () => {
    const stream = openStream()
    onTurn(() => stream.response())
    const deps = makeDeps()
    const sending = state().send('Sick days?', deps)
    stream.push(...started)
    stream.push('text.delta', { text: 'You get ' })
    await vi.waitFor(() => expect(state().turn?.text).toBe('You get '))
    // The stream ends with no closing event.
    stream.close()
    await sending
    expect(state().status).toBe('stopped')
    expect(state().turn?.text).toBe('You get ')
    expect(deps.invalidateConversation).toHaveBeenCalledTimes(1)
  })

  it('is a failed send, with the question still in the box, when the server never answered', async () => {
    onTurn(() => Response.error())
    const deps = makeDeps()
    state().setDraft('Sick days?')
    await state().send('Sick days?', deps)
    expect(state().status).toBe('idle')
    expect(state().turn).toBeNull()
    expect(state().sendError).toBe('Something went wrong sending that.')
    expect(state().draft).toBe('Sick days?')
    // No turn can exist, so there is nothing to read.
    expect(deps.invalidateConversation).not.toHaveBeenCalled()
  })

  describe('after the server answered (200) but before it announced the turn', () => {
    // The server has the question and saves the turn stopped: a resend would ask it twice.
    it('clears the question from the box, reads the conversation, and says the send failed, when the stream ends', async () => {
      onTurn(() => eventStream())
      const deps = makeDeps()
      state().setDraft('Sick days?')
      await state().send('Sick days?', deps)
      expect(state().status).toBe('idle')
      expect(state().turn).toBeNull()
      expect(state().sendError).toBe('Something went wrong sending that.')
      expect(state().draft).toBe('')
      expect(deps.invalidateConversation).toHaveBeenCalledTimes(1)
    })

    it('does the same when the connection fails', async () => {
      onTurn(
        () =>
          new HttpResponse(
            new ReadableStream({
              start(controller) {
                controller.error(new Error('connection reset'))
              },
            }),
            { headers: { 'Content-Type': 'text/event-stream' } },
          ),
      )
      const deps = makeDeps()
      state().setDraft('Sick days?')
      await state().send('Sick days?', deps)
      expect(state().turn).toBeNull()
      expect(state().sendError).toBe('Something went wrong sending that.')
      expect(state().draft).toBe('')
      expect(deps.invalidateConversation).toHaveBeenCalledTimes(1)
    })

    it('keeps what was typed since', async () => {
      const stream = openStream()
      onTurn(() => stream.response())
      const deps = makeDeps()
      state().setDraft('Sick days?')
      const sending = state().send('Sick days?', deps)
      await vi.waitFor(() => expect(state().turn?.accepted).toBe(true))
      state().setDraft('Something else')
      stream.close()
      await sending
      expect(state().draft).toBe('Something else')
    })
  })
})

describe('a turn that ends with its escalation and no closing event', () => {
  const escalation = (kind: string): [string, unknown] => [
    'escalation',
    { kind, message: 'Fixed text.', hrContact: [], offerCase: false },
  ]

  it.each(['crisis', 'unavailable'])(
    'finishes a %s turn like a completed one: not stopped, and the conversation is read again',
    async (kind) => {
      onTurn(() => eventStream(started, escalation(kind)))
      const deps = makeDeps()
      await state().send('A hard question', deps)
      expect(state().status).toBe('idle')
      expect(state().turn).toMatchObject({
        turnId: TURN_ID,
        completed: true,
        escalation: { kind, live: true },
      })
      expect(deps.invalidateConversation).toHaveBeenCalledTimes(1)
      state().settle(TURN_ID)
      expect(state().turn).toBeNull()
    },
  )

  it('still means stopped when the escalation is the sensitive one, which a completed turn follows', async () => {
    onTurn(() => eventStream(started, escalation('sensitive')))
    await state().send('A question', makeDeps())
    expect(state().status).toBe('stopped')
  })

  it('still means stopped when an error came with it', async () => {
    onTurn(() =>
      eventStream(
        started,
        ['error', { code: 'internal', message: 'Oops.', requestId: null }],
        escalation('unavailable'),
      ),
    )
    await state().send('A question', makeDeps())
    expect(state().status).toBe('error')
    expect(state().turn?.completed).toBe(false)
  })

  it('still means stopped when there is no escalation at all', async () => {
    onTurn(() => eventStream(started, ['text.delta', { text: 'Half' }]))
    await state().send('A question', makeDeps())
    expect(state().status).toBe('stopped')
    expect(state().turn?.completed).toBe(false)
  })
})

describe('the "still answering" message', () => {
  async function stillAnswering() {
    const stream = openStream()
    onTurn(() => stream.response())
    const deps = makeDeps()
    const first = state().send('First', deps)
    stream.push(...started)
    await vi.waitFor(() => expect(state().status).toBe('streaming'))
    await state().send('Second', deps)
    expect(state().sendError).toBe(TEXTS.stillAnswering)
    return { stream, first, deps }
  }

  it('goes away when the answer completes', async () => {
    const { stream, first } = await stillAnswering()
    stream.push(...completed)
    stream.close()
    await first
    expect(state().sendError).toBeNull()
  })

  it('goes away when the answer ends in an error', async () => {
    const { stream, first } = await stillAnswering()
    stream.push('error', { code: 'internal', message: 'Oops.', requestId: null })
    await vi.waitFor(() => expect(state().status).toBe('error'))
    expect(state().sendError).toBeNull()
    stream.close()
    await first
  })

  it('goes away when the answer is stopped', async () => {
    const { stream, first, deps } = await stillAnswering()
    state().stop(deps)
    expect(state().sendError).toBeNull()
    stream.close()
    await first
  })

  it('goes away when the connection drops', async () => {
    const { stream, first } = await stillAnswering()
    stream.close()
    await first
    expect(state().status).toBe('stopped')
    expect(state().sendError).toBeNull()
  })

  it('goes away when a crisis answer ends', async () => {
    const { stream, first } = await stillAnswering()
    stream.push('escalation', { kind: 'crisis', message: 'x', hrContact: [], offerCase: false })
    stream.close()
    await first
    expect(state().status).toBe('idle')
    expect(state().sendError).toBeNull()
  })
})

describe('settling a finished turn', () => {
  it.each([
    ['stopped', () => eventStream(started, ['text.delta', { text: 'Half' }])],
    [
      'error',
      () =>
        eventStream(started, ['error', { code: 'internal', message: 'Oops.', requestId: null }]),
    ],
    ['completed', () => eventStream(started, completed)],
  ])("hands a %s turn to the server's copy", async (_name, response) => {
    onTurn(response)
    await state().send('Hello', makeDeps())
    expect(state().turn).not.toBeNull()
    state().settle(TURN_ID)
    expect(state().turn).toBeNull()
    expect(state().status).toBe('idle')
  })

  it('leaves a turn that is still coming', async () => {
    const stream = openStream()
    onTurn(() => stream.response())
    void state().send('Hello', makeDeps())
    stream.push(...started)
    await vi.waitFor(() => expect(state().status).toBe('streaming'))
    state().settle(TURN_ID)
    expect(state().turn).not.toBeNull()
    stream.close()
  })
})

describe('Stop after the server answered but before the turn was announced', () => {
  // The response is 200, so the server has the turn and will save it stopped: it is not a send that
  // went nowhere, and the question must not be put back in the box to be asked twice.
  it('waits for turn.started, then shows the turn as stopped, and leaves the box empty', async () => {
    const stream = openStream()
    const posted = onTurn(() => stream.response())
    const deps = makeDeps()
    state().setDraft('Sick days?')
    const sending = state().send('Sick days?', deps)
    await vi.waitFor(() => expect(state().turn?.accepted).toBe(true))
    expect(posted).toHaveLength(1)

    state().stop(deps)
    // Nothing is decided yet: no turn is known to stop, and the box is not touched.
    expect(state().draft).toBe('Sick days?')
    stream.push(...started)
    await vi.waitFor(() => expect(state().status).toBe('stopped'))
    expect(state().turn).toMatchObject({ turnId: TURN_ID, question: 'Sick days?' })
    expect(state().draft).toBe('')
    expect(deps.invalidateConversation).toHaveBeenCalledTimes(1)
    await sending
  })

  it('is not a stopped turn when nothing ever comes: the server has the question, so it is read', async () => {
    const stream = openStream()
    onTurn(() => stream.response())
    const deps = makeDeps()
    state().setDraft('Sick days?')
    const sending = state().send('Sick days?', deps)
    await vi.waitFor(() => expect(state().turn?.accepted).toBe(true))
    state().stop(deps)
    stream.close()
    await sending
    expect(state().turn).toBeNull()
    expect(state().draft).toBe('')
    expect(deps.invalidateConversation).toHaveBeenCalledTimes(1)
    expect(state().status).toBe('idle')
  })

  it('does not mark a send accepted before the response came', async () => {
    onTurn(() => new Promise<never>(() => {}) as never)
    void state().send('Sick days?', makeDeps())
    await vi.waitFor(() => expect(state().status).toBe('sending'))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(state().turn?.accepted).toBe(false)
  })
})

describe('a new question while the last answer waits for its saved copy', () => {
  async function stoppedAnswer(deps = makeDeps()) {
    const stream = openStream()
    let calls = 0
    const posted = onTurn((question) => {
      calls++
      if (calls === 1) return stream.response()
      return question === 'busy'
        ? problemResponse(409, 'turn-running', 'running')
        : eventStream(['turn.started', { turnId: 't-2' }], ['text.delta', { text: 'Next.' }])
    })
    const sending = state().send('Sick days?', deps)
    stream.push(...started)
    stream.push('text.delta', { text: 'You get ' })
    await vi.waitFor(() => expect(state().turn?.text).toBe('You get '))
    state().stop(deps)
    await sending
    return { deps, posted }
  }

  it('keeps the stopped answer showing, in order before the new turn', async () => {
    const { deps } = await stoppedAnswer()
    await state().send('And carry-over?', deps)
    expect(state().settling.map((s) => [s.turn.turnId, s.phase])).toEqual([[TURN_ID, 'stopped']])
    expect(state().settling[0]?.turn.text).toBe('You get ')
    expect(state().turn?.question).toBe('And carry-over?')
  })

  it('drops it from the list when its saved copy arrives, and the new turn stays', async () => {
    const { deps } = await stoppedAnswer()
    await state().send('And carry-over?', deps)
    state().settle(TURN_ID)
    expect(state().settling).toEqual([])
    expect(state().turn?.question).toBe('And carry-over?')
  })

  it('leaves the stopped answer and the draft alone when the follow-up is refused (409 turn-running)', async () => {
    const { deps } = await stoppedAnswer()
    state().setDraft('busy')
    await state().send('busy', deps)
    expect(state().settling.map((s) => s.turn.turnId)).toEqual([TURN_ID])
    expect(state().draft).toBe('busy')
    expect(state().sendError).toBe(TEXTS.stillAnswering)
    expect(state().turn).toBeNull()
  })

  it('keeps an errored answer the same way, and a completed one', async () => {
    onTurn(() =>
      eventStream(started, ['error', { code: 'internal', message: 'Oops.', requestId: null }]),
    )
    const deps = makeDeps()
    await state().send('One', deps)
    expect(state().status).toBe('error')
    await state().send('Two', deps)
    expect(state().settling.map((s) => s.phase)).toEqual(['error'])
  })

  it('has no list entry for a turn that never began, which is cleared as before', async () => {
    onTurn(() => problemResponse(500, 'internal', 'No.'))
    const deps = makeDeps()
    await state().send('One', deps)
    expect(state().turn).toBeNull()
    expect(state().settling).toEqual([])
  })

  it('forgets them all on a new conversation and on an identity change', async () => {
    const { deps } = await stoppedAnswer()
    await state().send('And carry-over?', deps)
    state().beginConversation(NEW_CONVERSATION)
    expect(state().settling).toEqual([])
    useChatStore.setState({ settling: [{ turn: state().turn ?? ({} as never), phase: 'idle' }] })
    resetIdentity(new QueryClient())
    expect(state().settling).toEqual([])
  })
})

describe('Stop before the answer began', () => {
  it('shows no turn, and puts the question back in an empty box', async () => {
    const posted = onTurn(() => new Promise<never>(() => {}) as never)
    const deps = makeDeps()
    // (Asked again from a stopped or failed turn, so the box was empty.)
    void state().send('Sick days?', deps)
    await vi.waitFor(() => expect(posted).toHaveLength(1))
    expect(state().status).toBe('sending')
    state().stop(deps)
    expect(state().status).toBe('idle')
    expect(state().turn).toBeNull()
    expect(state().draft).toBe('Sick days?')
  })

  it('leaves what was typed since', async () => {
    const posted = onTurn(() => new Promise<never>(() => {}) as never)
    const deps = makeDeps()
    void state().send('Sick days?', deps)
    await vi.waitFor(() => expect(posted).toHaveLength(1))
    state().setDraft('Something else')
    state().stop(deps)
    expect(state().draft).toBe('Something else')
  })

  it('still remembers the conversation it created, so the next question does not create another', async () => {
    let created!: (id: string) => void
    const deps = makeDeps({
      conversationId: null,
      createConversation: vi.fn<() => Promise<string>>(
        () => new Promise((resolve) => (created = resolve)),
      ),
    })
    const sending = state().send('Hello', deps)
    state().stop(deps)
    expect(state().status).toBe('idle')
    created(NEW_CONVERSATION)
    await sending
    expect(state().conversationId).toBe(NEW_CONVERSATION)
    expect(state().turn).toBeNull()
    expect(state().status).toBe('idle')
  })

  it('does not remember a conversation created for someone else after a reset', async () => {
    let created!: (id: string) => void
    const deps = makeDeps({
      conversationId: null,
      createConversation: vi.fn<() => Promise<string>>(
        () => new Promise((resolve) => (created = resolve)),
      ),
    })
    const sending = state().send('Hello', deps)
    state().stop(deps)
    resetIdentity(new QueryClient())
    created(NEW_CONVERSATION)
    await sending
    expect(state().conversationId).toBeNull()
  })
})

describe('a remembered conversation that is gone', () => {
  it('forgets it, has the cached conversation dropped and read again, and keeps the draft', async () => {
    useChatStore.setState({ conversationId: 'gone-1' })
    onTurn(() => problemResponse(404, 'about:blank', 'Not found'))
    const deps = makeDeps({ conversationId: 'gone-1' })
    state().setDraft('Hello')
    await state().send('Hello', deps)
    expect(state().conversationId).toBeNull()
    expect(deps.forgetConversation).toHaveBeenCalledTimes(1)
    expect(state().sendError).toBe('Something went wrong sending that.')
    expect(state().draft).toBe('Hello')
    expect(state().turn).toBeNull()
  })
})

describe('a new conversation', () => {
  it('drops the live turn and the errors, and remembers the conversation', async () => {
    onTurn(() => eventStream(started, completed))
    await state().send('Hello', makeDeps())
    useChatStore.setState({ sendError: 'x', offerNewConversation: true })
    state().beginConversation(NEW_CONVERSATION)
    expect(state()).toMatchObject({
      status: 'idle',
      turn: null,
      sendError: null,
      offerNewConversation: false,
      conversationId: NEW_CONVERSATION,
    })
  })
})

describe('an identity change', () => {
  it('aborts the stream in flight, and drops the events that arrive after it', async () => {
    // A stream that ignores the abort and keeps delivering, as a misbehaving one could.
    let signal: AbortSignal | undefined
    let deliver!: (event: streamModule.TurnStreamEvent) => void
    let finish!: () => void
    vi.spyOn(streamModule, 'streamTurn').mockImplementation(
      (_id, _question, options) =>
        new Promise<void>((resolve) => {
          signal = options.signal
          deliver = options.onEvent
          finish = resolve
        }),
    )
    const deps = makeDeps()
    const sending = state().send('Sick days?', deps)
    await vi.waitFor(() => expect(signal).toBeDefined())
    deliver({ type: 'turn.started', data: { turnId: TURN_ID } })
    deliver({ type: 'text.delta', data: { text: "Priya's answer " } })
    expect(state().turn?.text).toBe("Priya's answer ")

    resetIdentity(new QueryClient())

    expect(signal?.aborted).toBe(true)
    expect(state()).toMatchObject({ status: 'idle', turn: null, draft: '' })
    deliver({ type: 'text.delta', data: { text: 'for the next person' } })
    deliver({ type: 'turn.completed', data: completedData })
    finish()
    await sending
    expect(state()).toMatchObject({ status: 'idle', turn: null })
    expect(deps.invalidateConversation).not.toHaveBeenCalled()
  })

  it("keeps a late event from the old person out of the next person's turn", async () => {
    let deliver!: (event: streamModule.TurnStreamEvent) => void
    let finish!: () => void
    vi.spyOn(streamModule, 'streamTurn').mockImplementationOnce(
      (_id, _question, options) =>
        new Promise<void>((resolve) => {
          deliver = options.onEvent
          finish = resolve
        }),
    )
    const first = state().send("Priya's question", makeDeps())
    await vi.waitFor(() => expect(deliver).toBeDefined())
    deliver({ type: 'turn.started', data: { turnId: 'old-turn' } })

    resetIdentity(new QueryClient())

    // The next person asks, on a stream that is really open.
    const stream = openStream()
    onTurn(() => stream.response())
    const second = state().send("Mateo's question", makeDeps())
    stream.push(...started)
    await vi.waitFor(() => expect(state().turn?.turnId).toBe(TURN_ID))

    deliver({ type: 'text.delta', data: { text: "Priya's answer" } })
    deliver({ type: 'turn.started', data: { turnId: 'old-turn' } })
    expect(state().turn).toMatchObject({ turnId: TURN_ID, text: '', question: "Mateo's question" })

    finish()
    await first
    stream.close()
    await second
  })

  it('drops a send that fails after the reset', async () => {
    let fail!: (error: Error) => void
    vi.spyOn(streamModule, 'streamTurn').mockImplementation(
      () => new Promise<void>((_resolve, reject) => (fail = reject)),
    )
    const sending = state().send('Hello', makeDeps())
    await vi.waitFor(() => expect(fail).toBeDefined())
    resetIdentity(new QueryClient())
    fail(new Error('down'))
    await sending
    expect(state().sendError).toBeNull()
  })

  it('drops a conversation that was created after the reset', async () => {
    let created!: (id: string) => void
    const posted = onTurn(() => eventStream(started, completed))
    const deps = makeDeps({
      conversationId: null,
      createConversation: () => new Promise((resolve) => (created = resolve)),
    })
    const sending = state().send('Hello', deps)
    resetIdentity(new QueryClient())
    created(NEW_CONVERSATION)
    await sending
    expect(posted).toHaveLength(0)
    expect(state().conversationId).toBeNull()
  })

  it('empties the draft and everything else', () => {
    useChatStore.setState({ draft: 'secret', sendError: 'x', warning: 'y', conversationId: 'z' })
    resetIdentity(new QueryClient())
    expect(state()).toMatchObject({
      draft: '',
      sendError: null,
      warning: null,
      conversationId: null,
    })
  })
})
