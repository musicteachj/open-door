import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, type MouseEvent } from 'react'
import type { CitationOut, ConversationOut, HrContactOut, TurnOut } from '@/api/generated'
import { Composer } from '@/components/assistant/composer'
import { ConversationHeader, RetentionLine } from '@/components/assistant/conversation-header'
import { conversationCopy } from '@/components/assistant/labels'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { useShellLayout } from '@/features/shell/shell-layout-store'
import { BudgetStop } from './budget-stop'
import { forgetOpener, rememberOpener, returnFocusToOpener } from './source-opener'
import { useSourceUrl } from './source-url'
import { useChatStore, type ChatStatus, type LiveTurn, type SettlingTurn } from './store'
import { OpenSourceContext } from './open-source'
import { LiveTurnView, SourceMarker, StoredTurn, type TurnContext } from './turn-view'
import { focusComposerIfLost, useAssistantComposer } from './use-assistant-composer'

// The conversation at /ask: the header row, the thread at the 760 px measure, and the docked
// composer, composed the way the gallery's `Conversation` frame is (screen 07). The sheet scrolls
// (the page, not an inner box), so the header and the composer stick to the window's edges.

/** One empty list for a conversation with no HR contacts, so the context does not change for it. */
const NO_CONTACTS: HrContactOut[] = []

/**
 * How close the end of the thread has to be to the composer's top edge for the reader to count as
 * "at the bottom", so a growing answer keeps scrolling into view.
 */
const FOLLOW_WITHIN_PX = 160

/**
 * Keeps the newest part of the thread in view: the last turn when the page opens, the new question
 * when one is sent, the growing answer while the reader is following it, and the chips, feedback
 * and work trace the saved copy adds when the live turn settles into it (that swap makes the page
 * taller, by about 140 px on a phone). A reader who scrolled up is left where they are.
 *
 * "The bottom" is measured against the visible part of the window: what is above the sticky
 * composer, since the thread's end can sit under it while the page is still at the top. Scrolling
 * to the end leaves a margin of the composer's height, so the end lands above it.
 */
function useFollowThread(live: LiveTurn | null, phase: ChatStatus) {
  const end = useRef<HTMLDivElement>(null)
  const dock = useRef<HTMLDivElement>(null)
  // Whether the reader is following the end. Decided by the reader's own scrolling (the listener
  // below) and by our scrolling to the end, never by measuring after the page has grown: one long
  // chunk of text can lay out more than 160 px below the end without the reader having moved.
  const following = useRef(true)
  const atBottom = () => {
    const edge = window.innerHeight - (dock.current?.offsetHeight ?? 0)
    return (end.current?.getBoundingClientRect().bottom ?? 0) - edge <= FOLLOW_WITHIN_PX
  }
  // A block body: Chromium's scrollIntoView returns a Promise, which an effect must never return.
  const toEnd = () => {
    const target = end.current
    if (target === null) return
    target.style.scrollMarginBottom = `${dock.current?.offsetHeight ?? 0}px`
    target.scrollIntoView({ block: 'end' })
    following.current = true
  }
  useEffect(() => {
    const onScroll = () => {
      following.current = atBottom()
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  // The page opening.
  useLayoutEffect(() => {
    toEnd()
  }, [])
  // A question being sent (Ask, Ask again, Retry, and Try again all start here).
  useLayoutEffect(() => {
    if (phase === 'sending') toEnd()
  }, [phase])
  // The answer growing: only if the reader is following.
  const growth = (live?.text.length ?? 0) + (live?.steps.length ?? 0)
  useEffect(() => {
    if (growth > 0 && following.current) toEnd()
  }, [growth])
  // The live turn settling into its saved copy: keep following if the reader was.
  const isLive = live !== null
  const wasLive = useRef(isLive)
  useLayoutEffect(() => {
    if (wasLive.current && !isLive && following.current) toEnd()
    wasLive.current = isLive
  }, [isLive])
  return { end, dock }
}

type ConversationViewProps = {
  conversation: ConversationOut | null
  /** The stored turns, without the live one's copy. */
  turns: TurnOut[]
  live: LiveTurn | null
  /** Finished turns still waiting for their saved copy, shown in order before the live one. */
  settling: readonly SettlingTurn[]
  /** The page changed shape just now (the first question), so focus the composer if it was lost. */
  focusComposerOnMount: boolean
}

export function ConversationView({
  conversation,
  turns,
  live,
  settling,
  focusComposerOnMount,
}: ConversationViewProps) {
  const composer = useAssistantComposer(conversation)
  const { banner, send } = composer
  const phase = useChatStore((s) => s.status)
  const offerNewConversation = useChatStore((s) => s.offerNewConversation)
  const { end, dock } = useFollowThread(live, phase)

  // The shell hides its own sandbox pills while this page shows its own in the header.
  const setLayout = useShellLayout((s) => s.setConversation)
  useLayoutEffect(() => {
    setLayout(true)
    return () => setLayout(false)
  }, [setLayout])
  useLayoutEffect(() => {
    if (focusComposerOnMount) focusComposerIfLost()
  }, [focusComposerOnMount])

  // The source panel. A marker or chip opens its passage, and the same one again closes it.
  const { key: openKey, open } = useSourceUrl()
  // The marker or chip being pressed, noted on the way down (before its own handler runs) so focus
  // can come back to that very element, even where the browser doesn't focus a pressed button.
  const pressed = useRef<Element | null>(null)
  const notePressed = (event: MouseEvent) => {
    pressed.current =
      event.target instanceof Element
        ? event.target.closest('[data-slot="citation-marker"], [data-slot="source-chip"]')
        : null
  }
  // `open` changes with the address, and the turns must not be drawn again for it, so the handler
  // the turns hold is one function that calls the latest `open`.
  const latestOpen = useRef(open)
  useLayoutEffect(() => {
    latestOpen.current = open
  })
  const onOpenSource = useCallback((citation: CitationOut) => {
    rememberOpener(pressed.current, citation.passageId)
    latestOpen.current(citation.passageId)
  }, [])
  // When the panel closes (its button, Escape, the marker again, or Back), focus goes back to the
  // newest opener.
  // The opener is only worth keeping while this page is up.
  useEffect(() => forgetOpener, [])
  const wasOpen = useRef(openKey !== null)
  useEffect(() => {
    if (wasOpen.current && openKey === null) returnFocusToOpener()
    wasOpen.current = openKey !== null
  }, [openKey])

  // Markers and chips read the open passage from `OpenSourceContext`, so opening the panel redraws
  // them and not the turns around them: nothing here depends on `openKey`.
  const renderMarker = useCallback(
    (citation: CitationOut) => <SourceMarker citation={citation} onOpen={onOpenSource} />,
    [onOpenSource],
  )
  const hrContacts = conversation?.hrContacts ?? NO_CONTACTS
  const budgetStop = banner !== null
  const context: TurnContext = useMemo(
    () => ({
      hrContacts,
      renderMarker,
      onOpenSource,
      onAskAgain: (question) => void send(question, 'again'),
      budgetStop,
    }),
    [hrContacts, renderMarker, onOpenSource, send, budgetStop],
  )

  // The long-conversation notice offers a new conversation. It follows the conversation's own
  // length flags, and a send the API refused because this one can't go on (`offerNewConversation`:
  // too long, or from an older assistant, whose 409 text is the send error). An outdated
  // conversation says nothing on load, since "getting long" would be the wrong words.
  const longConversation =
    (conversation?.longHistory ?? false) ||
    (conversation?.historyTooLong ?? false) ||
    offerNewConversation

  return (
    <OpenSourceContext value={openKey}>
      <div
        data-slot="conversation-view"
        className="flex min-w-0 flex-1 flex-col px-10 max-[760px]:px-4"
      >
        {banner !== null && <BudgetStop banner={banner} />}
        <div className="sticky top-0 z-10 w-full max-w-content bg-surface-raised pt-5 pb-6 max-[760px]:pt-4 max-[760px]:pb-4">
          <ConversationHeader onNewConversation={composer.startNewConversation}>
            <PageSandboxIndicator everyWidth />
          </ConversationHeader>
        </div>
        {/* Notes the pressed marker or chip. A click handler on a container, not a control. */}
        {/* oxlint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions */}
        <div
          data-slot="conversation-thread"
          onClickCapture={notePressed}
          className="flex w-full max-w-content min-w-0 flex-1 flex-col gap-6 pb-6"
        >
          {turns.map((turn) => (
            <StoredTurn key={turn.id} turn={turn} context={context} />
          ))}
          {settling.map(({ turn, phase: settledPhase }) => (
            <LiveTurnView
              key={`settling-${turn.turnId}`}
              live={turn}
              phase={settledPhase}
              context={context}
              settling
            />
          ))}
          {live !== null && <LiveTurnView key="live" live={live} phase={phase} context={context} />}
          <div ref={end} data-slot="thread-end" aria-hidden="true" />
        </div>
        <div
          ref={dock}
          data-slot="composer-dock"
          className="sticky bottom-0 z-10 flex w-full max-w-content flex-col gap-3 bg-surface-raised pt-2 pb-5 max-[760px]:pb-4"
        >
          <Composer
            {...composer.props}
            variant="docked"
            placeholder={conversationCopy.followUpPlaceholder}
            longConversation={longConversation}
            onNewConversation={composer.startNewConversation}
          />
          <RetentionLine className="sm:hidden" />
        </div>
      </div>
    </OpenSourceContext>
  )
}
