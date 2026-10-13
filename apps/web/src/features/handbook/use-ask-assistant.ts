import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import { useChatStore } from '@/features/chat/store'

/**
 * "Ask the assistant": opens Ask with this text in the composer, not sent. The text goes into the
 * chat store's draft, which the composer shows, and then the page changes to /ask. The handbook's
 * no-results state is the first caller; any page that wants to hand a question over can use it.
 */
export function useAskAssistant() {
  const navigate = useNavigate()
  const setDraft = useChatStore((s) => s.setDraft)
  return useCallback(
    (text: string) => {
      setDraft(text)
      void navigate('/ask')
    },
    [navigate, setDraft],
  )
}
