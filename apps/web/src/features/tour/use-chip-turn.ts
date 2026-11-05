import { useGetCurrentConversation } from '@/api/generated'
import { isRunning, useChatStore } from '@/features/chat/store'

/**
 * Whether the turn with this ID has finished, however it ended. While the page holds the turn it
 * is the chat store's live one (not sending or streaming any more) or a finished one waiting
 * behind a newer question; after a reload it is the saved conversation's turn, no longer running.
 * Never a timer. With no ID (the server has not taken the chip's question yet) nothing has
 * finished.
 */
export function useTurnFinished(turnId: string | null): boolean {
  const live = useChatStore((s) => {
    if (turnId === null) return false
    const running = isRunning(s)
    return (
      (!running && s.turn !== null && s.turn.turnId === turnId) ||
      s.settling.some((e) => e.turn.turnId === turnId)
    )
  })
  const saved = useGetCurrentConversation({ query: { enabled: turnId !== null } })
  const storedDone =
    turnId !== null &&
    (saved.data?.turns.some((turn) => turn.id === turnId && turn.status !== 'running') ?? false)
  return live || storedDone
}
