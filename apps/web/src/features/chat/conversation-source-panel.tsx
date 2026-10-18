import { useEffect, useMemo } from 'react'
import { useGetCurrentConversation } from '@/api/generated'
import { PassagePanel } from '@/components/handbook/passage-panel'
import { BottomSheet, SheetTitle } from '@/components/ui/bottom-sheet'
import { usePassage } from '@/features/handbook/use-passage'
import { useChatStore } from './store'
import { parseSourceKey, withSourceKeys } from './source-key'
import { useSourceUrl } from './source-url'

// The passage a marker or chip opened (`?source=`), shown beside the conversation on a wide window
// and as a modal sheet on a narrow one. The shell renders it, because on a wide window it takes the
// rail's place. Which citation opened it, for focus, is the page's (source-opener.ts).

/**
 * Below 1280 px the panel is a sheet, not a column. At 1101 px a 420 px panel beside the 248 px
 * sidebar would leave about 339 px for the thread. The shell's rail keeps its own 1100 px rule.
 */
export const NARROW_WINDOW_QUERY = '(max-width: 1279px)'

/** The group name ("California addendum") of a cited passage, for the eyebrow while it loads. */
function useGroupName(key: string): string | undefined {
  const conversation = useGetCurrentConversation().data
  const liveCitations = useChatStore((s) => s.turn?.citations)
  const settling = useChatStore((s) => s.settling)
  // Worked out again only when the conversation is read again or the live answer's citations
  // change, not on every render: `withSourceKeys` remembers its result by the array it was given.
  const citations = useMemo(
    () => [
      ...(conversation?.turns.flatMap((turn) => turn.citations) ?? []),
      // Turns the page still holds itself: the live one, and finished ones waiting for their copy.
      ...settling.flatMap((entry) => entry.turn.citations),
      ...(liveCitations ?? []),
    ],
    [conversation, settling, liveCitations],
  )
  const keyed = useMemo(() => withSourceKeys(citations), [citations])
  return keyed.find((citation) => citation.passageId === key)?.groupName
}

function Passage({
  sourceKey,
  onClose,
  inSheet = false,
}: {
  sourceKey: string
  onClose: () => void
  /** In the sheet, the dialog is the landmark and the visible title names it. */
  inSheet?: boolean
}) {
  const parsed = parseSourceKey(sourceKey)!
  const passage = usePassage(parsed.sectionId, parsed.passageId)
  const groupName = useGroupName(sourceKey)
  return (
    <PassagePanel
      state={passage.data ? 'open' : passage.isError ? 'error' : 'loading'}
      sectionId={parsed.sectionId}
      passageId={parsed.passageId}
      view={passage.data}
      groupName={groupName}
      onClose={onClose}
      onRetry={() => void passage.refetch()}
      landmark={!inSheet}
      titleAs={inSheet ? SheetTitle : undefined}
    />
  )
}

/**
 * Escape closes the docked panel from anywhere in the conversation view (a marker, a chip, the
 * composer), not only from the panel. The panel itself handles Escape from inside it and from the
 * page body, so this takes only what is in the view and leaves the rest alone. It skips a key
 * another part of the page already used (an open menu) and an IME composition.
 */
function useEscapeInConversation(onClose: () => void) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented || event.isComposing) return
      const view = document.querySelector('[data-slot="conversation-view"]')
      if (event.target instanceof Node && view?.contains(event.target)) onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])
}

/** The panel in the rail's place: `w-panel` (420 px) wide, as tall as the window, and not modal. */
function DockedPanel({ sourceKey, onClose }: { sourceKey: string; onClose: () => void }) {
  useEscapeInConversation(onClose)
  return (
    <div
      data-slot="source-panel"
      className="min-h-0 w-panel max-w-full border-l border-border-subtle"
    >
      <div className="sticky top-3 h-[calc(100dvh-24px)]">
        <Passage sourceKey={sourceKey} onClose={onClose} />
      </div>
    </div>
  )
}

/**
 * Renders the open source panel, or nothing when `?source=` names no passage. `docked` is the
 * wide window's panel (the shell gives it the rail's column); otherwise a modal bottom sheet.
 */
export function ConversationSourcePanel({ docked }: { docked: boolean }) {
  const { key, close } = useSourceUrl()
  if (key === null) return null
  if (docked) return <DockedPanel sourceKey={key} onClose={close} />
  return (
    <BottomSheet onClose={close}>
      <Passage sourceKey={key} onClose={close} inSheet />
    </BottomSheet>
  )
}
