import { useEffect, useLayoutEffect, useState } from 'react'
import type { BudgetOut, ConversationOut, Me, TurnOut } from '@/api/generated'
import { Composer } from '@/components/assistant/composer'
import { TryAskingList } from '@/components/assistant/try-asking-list'
import { useMe } from '@/app/useMe'
import { useWriteToHrLink } from '@/features/cases/use-write-to-hr'
import { BudgetStop } from '@/features/chat/budget-stop'
import { ConversationView } from '@/features/chat/conversation-view'
import { forgetOpener } from '@/features/chat/source-opener'
import { useSourceUrl } from '@/features/chat/source-url'
import { useChatStore, type LiveTurn, type SettlingTurn } from '@/features/chat/store'
import { focusComposerIfLost, useAssistantComposer } from '@/features/chat/use-assistant-composer'
import {
  useAssistantTexts,
  useBudgetBeforeConversation,
  useConversationTurns,
} from '@/features/chat/use-conversation'
import { personaFor } from '@/features/personas/personas'
import { useNow } from '@/features/shell/use-now'
import { greetingLine } from '@/lib/time'

// The assistant at /ask. Until the person has asked something it is the home from
// docs/design/screens/03-assistant-home: the greeting, the composer, and the "Try asking" list. The
// first question turns it into the conversation (screen 07), and a reload shows the conversation
// from the server. The shell supplies the sidebar, the rail, and the page's one <main>.

export function HomePage() {
  const { data: me } = useMe()
  const texts = useAssistantTexts()
  const { conversation, turns, live, settling } = useConversationTurns()
  // With no conversation to carry it, the budget (and so the banner) comes from its own route.
  const budget = useBudgetBeforeConversation(
    conversation.data === undefined ? undefined : conversation.data !== null,
  )

  // A failed read goes to the route's error element (with Retry), as the handbook's does. Only a
  // first load that failed: a later read that fails leaves what is on the page there.
  if (texts.data === undefined && texts.isError) throw texts.error
  if (conversation.data === undefined && conversation.isError) throw conversation.error

  // The composer waits for who is asking, the API's refusal texts, and the current conversation,
  // so it never runs without its words and never shows the home for a conversation that exists.
  // A budget read that fails leaves the page usable: the send itself is refused if there is no room.
  const waitingForBudget = conversation.data === null && budget.isPending && !budget.isError
  if (!me || texts.data === undefined || conversation.data === undefined || waitingForBudget) {
    return <output className="sr-only">Loading…</output>
  }
  return (
    <Assistant
      me={me}
      conversation={conversation.data}
      budget={budget.data}
      turns={turns}
      live={live}
      settling={settling}
    />
  )
}

function Assistant({
  me,
  conversation,
  budget,
  turns,
  live,
  settling,
}: {
  me: Me
  conversation: ConversationOut | null
  budget: BudgetOut | undefined
  turns: TurnOut[]
  live: LiveTurn | null
  settling: readonly SettlingTurn[]
}) {
  const showConversation = turns.length > 0 || live !== null || settling.length > 0
  // The page changing shape (the first question, or "Start a new conversation") unmounts the
  // control that had focus, so the view that takes over focuses its composer. Noticed while
  // rendering, so the new view knows from its first render.
  const [shape, setShape] = useState({ showConversation, changed: false })
  if (shape.showConversation !== showConversation) setShape({ showConversation, changed: true })
  const changed = shape.changed
  return showConversation ? (
    <ConversationView
      conversation={conversation}
      turns={turns}
      live={live}
      settling={settling}
      focusComposerOnMount={changed}
    />
  ) : (
    <Home me={me} conversation={conversation} budget={budget} focusComposerOnMount={changed} />
  )
}

function Home({
  me,
  conversation,
  budget,
  focusComposerOnMount,
}: {
  me: Me
  conversation: ConversationOut | null
  budget: BudgetOut | undefined
  focusComposerOnMount: boolean
}) {
  const now = useNow()
  const writeToHr = useWriteToHrLink()
  const composer = useAssistantComposer(conversation, budget)
  const { banner } = composer
  const setDraft = useChatStore((s) => s.setDraft)
  useLayoutEffect(() => {
    if (focusComposerOnMount) focusComposerIfLost()
  }, [focusComposerOnMount])
  // The home has no answers to cite. A passage left open from the conversation that was just
  // replaced (or from a stale link) closes: by going back when the panel pushed its own history
  // entry, otherwise by replacing the address.
  const { clear: clearSource } = useSourceUrl()
  useEffect(() => {
    forgetOpener()
    clearSource()
    // On arrival at the home only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The kit's .kit-content: 120/72/48/80 px padding, 72/48/40 under 1100 px, 40/20/32 under
  // 760 px. The greeting is 32/40 on a narrow screen, a size the type scale has no step for.
  return (
    <div className="flex min-w-0 flex-col pt-30 pr-18 pb-12 pl-20 max-[1100px]:px-12 max-[1100px]:pt-18 max-[1100px]:pb-10 max-[760px]:px-5 max-[760px]:pt-10 max-[760px]:pb-8">
      {banner !== null && <BudgetStop banner={banner} writeToHr={writeToHr} />}
      <h1 className="m-0 mb-9 text-display text-ink max-[760px]:text-[32px] max-[760px]:leading-10">
        {greetingLine(new Date(now), me.location.timezone, me.givenName)}
      </h1>
      <Composer {...composer.props} />
      <TryAskingList
        items={personaFor(me.personaKey).tryAsking}
        onPick={setDraft}
        className="mt-12"
      />
    </div>
  )
}
