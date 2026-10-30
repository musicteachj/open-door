import type { BudgetOut, ConversationOut } from '@/api/generated'
import type { ComposerProps } from '@/components/assistant/composer'
import { useChatStore } from './store'
import { useConversationActions } from './use-conversation'

/**
 * What the assistant home and the conversation share on the composer: the draft, sending, Stop,
 * the failed-send line (`sendError`, the only one), the personal-data warning, and the budget
 * stop. `banner` is the conversation's budget banner, or null. A person with no conversation yet
 * has none to carry it, so the page passes what the budget route said (`budget`).
 */
export function useAssistantComposer(conversation: ConversationOut | null, budget?: BudgetOut) {
  const { send, stop, startNewConversation } = useConversationActions()
  const draft = useChatStore((s) => s.draft)
  const status = useChatStore((s) => s.status)
  const sendError = useChatStore((s) => s.sendError)
  const waitingToSend = useChatStore((s) => s.waitingToSend)
  const warning = useChatStore((s) => s.warning)
  const setDraft = useChatStore((s) => s.setDraft)
  const banner = (conversation?.budget ?? budget)?.banner ?? null
  const props: ComposerProps = {
    value: draft,
    onChange: setDraft,
    onSubmit: (question) => void send(question),
    // Busy while a question waits for "Start a new conversation" too, so a second Enter is seen.
    busy: status === 'sending' || waitingToSend,
    streaming: status === 'streaming',
    onStop: stop,
    onSubmitWhileStreaming: () => void send(draft),
    sendError: sendError ?? undefined,
    warning: warning ?? undefined,
    disabledReason: banner?.kind,
  }
  return { props, banner, send, startNewConversation: () => void startNewConversation() }
}

const composerInput = () =>
  document.querySelector<HTMLTextAreaElement>('[data-slot="composer"] textarea')

/** Puts focus in the composer if it was lost when the page changed shape (home to conversation). */
export function focusComposerIfLost() {
  const active = document.activeElement
  if (active !== null && active !== document.body) return
  composerInput()?.focus()
}

/** Puts focus in the composer, wherever it was. A card's "Ask again" does this after it fills the box. */
export function focusComposer() {
  composerInput()?.focus()
}
