import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  type MouseEvent,
  type RefObject,
} from 'react'
import type { CitationOut, ConversationOut, HrContactOut, TurnOut } from '@/api/generated'
import { AnswerViewerContext } from '@/components/assistant/answer-viewer'
import { Composer } from '@/components/assistant/composer'
import { EscalationPanel } from '@/components/assistant/escalation-panel'
import { ConversationHeader, RetentionLine } from '@/components/assistant/conversation-header'
import { conversationCopy } from '@/components/assistant/labels'
import { PageSandboxIndicator } from '@/features/shell/page-sandbox-indicator'
import { useShellLayout } from '@/features/shell/shell-layout-store'
import { useAnswerViewer, useWriteToHrLink } from '@/features/cases/use-write-to-hr'
import { BudgetStop } from './budget-stop'
import { forgetOpener, rememberOpener, returnFocusToOpener } from './source-opener'
import { useSourceUrl } from './source-url'
import { useAssistantTexts } from './use-conversation'
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
 * taller, by about 140 px on a phone), and what the last turn adds after it has ended. A reader
 * who scrolled up is left where they are.
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
  // No key, pointer, click, or scroll since the last scroll to the end that a question started
  // (see the observer below). Never on page open: Back or a reload puts the page where the reader
  // left it, and following its growth would fight that.
  const untouched = useRef(false)
  const atBottom = () => {
    const edge = window.innerHeight - (dock.current?.offsetHeight ?? 0)
    return (end.current?.getBoundingClientRect().bottom ?? 0) - edge <= FOLLOW_WITHIN_PX
  }
  // A block body: Chromium's scrollIntoView returns a Promise, which an effect must never return.
  const toEnd = (arm = true) => {
    const target = end.current
    if (target === null) return
    // The thread's own margin (useStickyScrollMargins) isn't set yet when the page opens.
    target.style.scrollMarginBottom = `${dock.current?.offsetHeight ?? 0}px`
    target.scrollIntoView({ block: 'end' })
    following.current = true
    if (arm) untouched.current = true
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
    toEnd(false)
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
  // Parts of the last turn that grow after it has ended, such as the HR panel's case line once its
  // data loads: a reader who was following is taken to the end again (under a tall HR panel,
  // "Show your work" would otherwise rest behind the composer). Only until the reader presses a
  // key or the pointer, clicks (a screen reader's click comes with neither), or scrolls with a
  // wheel or a finger, so opening "Show your work" or rereading never moves the page.
  useEffect(() => {
    const thread = end.current?.parentElement
    if (!thread) return
    const listeners = new AbortController()
    const on = { capture: true, passive: true, signal: listeners.signal }
    const stop = () => {
      untouched.current = false
    }
    for (const type of ['pointerdown', 'keydown', 'click', 'wheel', 'touchmove'] as const) {
      window.addEventListener(type, stop, on)
    }
    // Where the focused control sat in the window when last seen. The reader's scrolling (and
    // the browser's scroll anchoring) updates it, so a later change that moved the control on
    // screen can be told apart.
    const last: { seen: { el: Element; top: number } | null; height: number } = {
      seen: null,
      height: thread.offsetHeight,
    }
    const note = () => {
      const focused = document.activeElement
      last.seen =
        focused && thread.contains(focused)
          ? { el: focused, top: focused.getBoundingClientRect().top }
          : null
    }
    thread.addEventListener('focusin', note, on)
    window.addEventListener('scroll', note, on)
    const observer = new ResizeObserver(() => {
      const grew = thread.offsetHeight > last.height
      last.height = thread.offsetHeight
      // Only growth: a thread made wider or narrower (the docked panel, the window) isn't news.
      if (grew && untouched.current && following.current) {
        toEnd()
        return
      }
      // The last answer, while its text is still being revealed, grows after that text arrived, as the reveal
      // plays it out: a reader following it is kept at the end, as the stream's own growth does,
      // whatever they pressed since asking (ADR 0025).
      if (
        grew &&
        following.current &&
        [...thread.querySelectorAll('[data-slot="answer-live"]')]
          .at(-1)
          ?.hasAttribute('data-revealing')
      ) {
        toEnd(false)
        return
      }
      // A control with focus that the change pushed behind the composer, such as "Send feedback"
      // when the form's error appears above it, is brought clear (its scroll margin keeps it
      // above the composer). Only if the change moved it on screen: one the reader scrolled there,
      // or that scroll anchoring held in place, stays. (Nor can content above it push it up
      // behind the header: scroll anchoring holds what's in view in place.)
      const focused = document.activeElement
      if (!(focused instanceof HTMLElement) || !thread.contains(focused)) return
      const box = focused.getBoundingClientRect()
      const moved = last.seen?.el === focused && Math.abs(box.top - last.seen.top) > 1
      const composerTop = dock.current?.getBoundingClientRect().top ?? window.innerHeight
      if (moved && box.bottom > composerTop && box.top < window.innerHeight) {
        focused.scrollIntoView({ block: 'nearest' })
      }
      note()
    })
    observer.observe(thread)
    return () => {
      observer.disconnect()
      listeners.abort()
    }
  }, [])
  return { end, dock }
}

/**
 * Keeps whatever takes focus in the thread clear of the sticky header and composer (WCAG 2.4.11):
 * each thing in the thread gets a scroll margin of their heights, so the browser scrolls a focused
 * link or button above the composer instead of leaving it underneath. The margin is the thread's
 * own, not the page's scroll padding: with padding on the page, focusing the composer or the
 * header's button, which sit inside the padded edges, would scroll the page. The heights are CSS
 * variables set through the CSS object model, which the Content Security Policy allows.
 */
function useStickyScrollMargins(
  thread: RefObject<HTMLElement | null>,
  header: RefObject<HTMLElement | null>,
  dock: RefObject<HTMLElement | null>,
) {
  useLayoutEffect(() => {
    const el = thread.current
    if (el === null) return
    const update = () => {
      el.style.setProperty('--sticky-top', `${header.current?.offsetHeight ?? 0}px`)
      el.style.setProperty('--sticky-bottom', `${dock.current?.offsetHeight ?? 0}px`)
    }
    update()
    const observer = new ResizeObserver(update)
    for (const part of [header.current, dock.current]) if (part) observer.observe(part)
    // Chromium scrolls a text box to its caret, not to the box with its margin, so the case form's
    // "Your words" could take focus under the composer. Anything that takes focus from the
    // keyboard is brought clear here, and so is a text box however it gets focus (Chromium counts
    // any focused text box as `:focus-visible`); a click on a button or link leaves the page be.
    const clear = (event: FocusEvent) => {
      const target = event.target
      if (target instanceof HTMLElement && target.matches(':focus-visible')) {
        target.scrollIntoView({ block: 'nearest' })
      }
    }
    el.addEventListener('focusin', clear)
    return () => {
      observer.disconnect()
      el.removeEventListener('focusin', clear)
    }
  }, [thread, header, dock])
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
  const offerWithoutNoticeWords = useChatStore((s) => s.offerWithoutNoticeWords)
  const { end, dock } = useFollowThread(live, phase)
  const header = useRef<HTMLDivElement>(null)
  const thread = useRef<HTMLDivElement>(null)
  useStickyScrollMargins(thread, header, dock)

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
  // A turn that settled while this page was up but whose saved copy it never drew (the person
  // left first) must not announce its panel when the page comes back: the arrival is long past.
  useEffect(() => () => useChatStore.setState({ panelsToAnnounce: [] }), [])
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
  const writeToHr = useWriteToHrLink()
  const viewer = useAnswerViewer()
  const context: TurnContext = useMemo(
    () => ({
      hrContacts,
      renderMarker,
      onOpenSource,
      onAskAgain: (question) => void send(question, 'again'),
      budgetStop,
      writeToHr,
    }),
    [hrContacts, renderMarker, onOpenSource, send, budgetStop, writeToHr],
  )

  // The long-conversation notice offers a new conversation. It follows the conversation's own
  // length flags, and a send the API refused because this one can't go on (`offerNewConversation`:
  // too long, or from an older assistant, whose 409 text is the send error). An outdated
  // conversation says nothing on load, since "getting long" would be the wrong words.
  // One that can't be opened says so in the owner's words (from the API, which holds the only copy),
  // with the same button. A last turn the budget stopped because of the conversation's size
  // (`budget-conversation`) keeps the button after a reload, with its own words standing for the
  // notice's, as the live stop does.
  const texts = useAssistantTexts()
  const unreadable = conversation?.unreadable ?? false
  // Not under a budget banner: a sandbox spent since then refuses a new conversation too.
  const stoppedForSize =
    banner === null && live === null && turns.at(-1)?.error?.code === 'budget-conversation'
  const longConversation =
    unreadable ||
    (conversation?.longHistory ?? false) ||
    (conversation?.historyTooLong ?? false) ||
    offerNewConversation ||
    stoppedForSize

  return (
    <OpenSourceContext value={openKey}>
      <AnswerViewerContext value={viewer}>
        <div
          data-slot="conversation-view"
          className="flex min-w-0 flex-1 flex-col px-10 max-[760px]:px-4"
        >
          {banner !== null && <BudgetStop banner={banner} writeToHr={writeToHr} />}
          <div
            ref={header}
            className="sticky top-0 z-10 w-full max-w-content bg-surface-raised pt-5 pb-6 max-[760px]:pt-4 max-[760px]:pb-4"
          >
            <ConversationHeader onNewConversation={composer.startNewConversation}>
              <PageSandboxIndicator everyWidth />
            </ConversationHeader>
          </div>
          {/* Notes the pressed marker or chip. A click handler on a container, not a control. */}
          {/* oxlint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions */}
          <div
            ref={thread}
            data-slot="conversation-thread"
            onClickCapture={notePressed}
            className="flex w-full max-w-content min-w-0 flex-1 flex-col gap-6 pb-6 [&_*]:scroll-mt-(--sticky-top) [&_*]:scroll-mb-(--sticky-bottom)"
          >
            {turns.map((turn) => (
              <StoredTurn key={turn.id} turn={turn} context={context} />
            ))}
            {/* Its words can't be shown, but the crisis or HR panel it showed stays (invariant 6). */}
            {unreadable && conversation?.escalation && (
              <EscalationPanel
                kind={conversation.escalation.kind}
                message={conversation.escalation.message}
                contacts={conversation.escalation.hrContact}
                writeToHr={writeToHr}
                turnless
              />
            )}
            {settling.map(({ turn, phase: settledPhase }) => (
              <LiveTurnView
                key={`settling-${turn.turnId}`}
                live={turn}
                phase={settledPhase}
                context={context}
                settling
              />
            ))}
            {live !== null && (
              <LiveTurnView key="live" live={live} phase={phase} context={context} />
            )}
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
              noticeText={
                unreadable
                  ? (texts.data?.unreadableConversation ?? '')
                  : offerWithoutNoticeWords || stoppedForSize
                    ? ''
                    : undefined
              }
              onNewConversation={composer.startNewConversation}
            />
            <RetentionLine className="sm:hidden" />
          </div>
        </div>
      </AnswerViewerContext>
    </OpenSourceContext>
  )
}
