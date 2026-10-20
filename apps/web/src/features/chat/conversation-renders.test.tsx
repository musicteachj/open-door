import { act, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getGetCurrentConversationQueryKey, type TurnOut } from '@/api/generated'
import { citation, toolCall } from '@/test/assistant-fixtures'
import { installPassages } from '@/test/fake-assistant'
import { installFakeApi } from '@/test/fake-api'
import {
  conversationOut,
  eventStream,
  installAssistantApi,
  onTurn,
  openStream,
  turnOut,
} from '@/test/fake-assistant'
import { renderApp } from '@/test/render-app'
import { useChatStore } from './store'

// What the conversation draws again, and when. A settled conversation must be still, and a
// streaming answer must redraw its own message only, not every earlier turn: each redraw of a long
// thread is work (and, with a repeated key, one more React warning per turn).

const renders = vi.hoisted(() => ({ workTrace: 0 }))
vi.mock('@/components/assistant/work-trace', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/components/assistant/work-trace')>()
  return {
    ...original,
    WorkTrace: (props: Parameters<typeof original.WorkTrace>[0]) => {
      renders.workTrace++
      return original.WorkTrace(props)
    },
  }
})

const ANSWER = 'You get 40 hours of sick leave.'
function stored(id: string, question: string): TurnOut {
  return turnOut({
    id,
    question,
    answerText: ANSWER,
    citations: [citation({ passageId: 'p2', offsetUtf16: ANSWER.length })],
    toolCalls: [toolCall()],
    sections: [
      {
        sectionId: 'CA-4.3',
        passageIds: ['p2'],
        title: 'Sick leave',
        groupName: 'California addendum',
      },
    ],
  })
}
const twoTurns = () =>
  conversationOut({ turns: [stored('t-1', 'First?'), stored('t-2', 'Second?')] })
const composer = () => screen.findByRole('textbox', { name: 'Ask Open Door' })
const pause = (ms: number) =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms))
  })

beforeEach(() => {
  useChatStore.setState(useChatStore.getInitialState())
  renders.workTrace = 0
})

describe('a settled conversation', () => {
  it('does not read again or draw again on its own', async () => {
    installFakeApi('priya')
    const api = installAssistantApi({ conversation: twoTurns() })
    renderApp({ at: '/ask' })
    await screen.findAllByText('Was this right?')
    await pause(200)
    const reads = api.requests.current
    const drawn = renders.workTrace
    await pause(1200)
    expect(api.requests.current).toBe(reads)
    expect(renders.workTrace).toBe(drawn)
  })

  it('stays still after an answer settles into its saved copy', async () => {
    installFakeApi('priya')
    const api = installAssistantApi({ conversation: twoTurns() })
    onTurn(() => {
      api.setCurrent(
        conversationOut({
          turns: [stored('t-1', 'First?'), stored('t-2', 'Second?'), stored('t-3', 'Third?')],
        }),
      )
      return eventStream(
        ['turn.started', { turnId: 't-3' }],
        ['text.delta', { text: ANSWER }],
        [
          'turn.completed',
          { turnId: 't-3', servedBy: 'anthropic', usage: { inputTokens: 1, outputTokens: 1 } },
        ],
      )
    })
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'Third?{Enter}')
    await waitFor(() => expect(useChatStore.getState().turn).toBeNull())
    await screen.findByText('Third?', { selector: '[data-slot="user-message"]' })
    await pause(300)
    const reads = api.requests.current
    const drawn = renders.workTrace
    await pause(1500)
    expect(api.requests.current).toBe(reads)
    expect(renders.workTrace).toBe(drawn)
  })
})

describe('a streaming answer', () => {
  it('draws its own message, and leaves the earlier turns alone', async () => {
    installFakeApi('priya')
    installAssistantApi({ conversation: twoTurns() })
    const stream = openStream()
    onTurn(() => stream.response())
    const { user } = renderApp({ at: '/ask' })
    await user.type(await composer(), 'Third?{Enter}')
    stream.push('turn.started', { turnId: 't-3' })
    stream.push('text.delta', { text: 'Thinking' })
    await screen.findByText(/Thinking/)
    await pause(50)
    const drawn = renders.workTrace
    for (let i = 0; i < 15; i++) stream.push('text.delta', { text: ` word${i}` })
    await screen.findByText(/word14/)
    expect(renders.workTrace).toBe(drawn)
    stream.close()
  })
})

describe('what redraws the earlier turns', () => {
  it('leaves them alone when a source panel opens and closes', async () => {
    installFakeApi('priya')
    installAssistantApi({ conversation: twoTurns() })
    installPassages()
    const { user } = renderApp({ at: '/ask' })
    await screen.findAllByText('Was this right?')
    await pause(100)
    const drawn = renders.workTrace
    const [marker] = await screen.findAllByRole('button', { name: /^Source 1:/ })
    await user.click(marker!)
    await screen.findByRole('complementary', { name: 'Handbook passage' }).catch(() => null)
    expect(marker).toHaveAttribute('aria-expanded', 'true')
    await user.click(marker!)
    await waitFor(() => expect(marker).toHaveAttribute('aria-expanded', 'false'))
    expect(renders.workTrace).toBe(drawn)
  })

  it('leaves them alone when the conversation is read again with other things changed', async () => {
    installFakeApi('priya')
    const api = installAssistantApi({ conversation: twoTurns() })
    const { queryClient } = renderApp({ at: '/ask' })
    await screen.findAllByText('Was this right?')
    await pause(100)
    const drawn = renders.workTrace
    // The turns and the HR people are as they were; only a flag on the conversation changes.
    api.setCurrent({ ...twoTurns(), longHistory: true })
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: getGetCurrentConversationQueryKey() })
    })
    await screen.findByText(/This conversation is getting long/)
    expect(renders.workTrace).toBe(drawn)
  })
})
