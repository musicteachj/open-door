import { Composer } from '@/components/assistant/composer'
import { TryAskingList } from '@/components/assistant/try-asking-list'
import { useMe } from '@/app/useMe'
import { useChatStore } from '@/features/chat/store'
import { useChatTransport } from '@/features/chat/transport'
import { personaFor } from '@/features/personas/personas'
import { useNow } from '@/features/shell/use-now'
import { greetingLine } from '@/lib/time'

// The assistant home at /ask, from docs/design/screens/03-assistant-home. The shell supplies the
// sidebar, the rail (so the at-a-glance list is the shell's, and empty until Phases 3 and 5), and
// the page's one <main>. This is the page's content: the greeting, the composer, the reply, and
// the "Try asking" list.

const SEND_FAILED = 'Something went wrong sending that.'

export function HomePage() {
  const { data: me } = useMe()
  if (!me) return null
  return <Home me={me} />
}

function Home({ me }: { me: NonNullable<ReturnType<typeof useMe>['data']> }) {
  const now = useNow()
  const transport = useChatTransport()
  const draft = useChatStore((s) => s.draft)
  const status = useChatStore((s) => s.status)
  const reply = useChatStore((s) => s.reply)
  const setDraft = useChatStore((s) => s.setDraft)
  const send = useChatStore((s) => s.send)

  // The kit's .kit-content: 120/72/48/80 px padding, 72/48/40 under 1100 px, 40/20/32 under
  // 760 px. The greeting is 32/40 on a narrow screen, a size the type scale has no step for.
  return (
    <div className="flex min-w-0 flex-col pt-30 pr-18 pb-12 pl-20 max-[1100px]:px-12 max-[1100px]:pt-18 max-[1100px]:pb-10 max-[760px]:px-5 max-[760px]:pt-10 max-[760px]:pb-8">
      <h1 className="m-0 mb-9 text-display text-ink max-[760px]:text-[32px] max-[760px]:leading-10">
        {greetingLine(new Date(now), me.location.timezone, me.givenName)}
      </h1>
      <Composer
        value={draft}
        onChange={setDraft}
        onSubmit={(question) => void send(transport, question)}
        busy={status === 'sending'}
        error={status === 'failed' ? SEND_FAILED : undefined}
      />
      {/* Always mounted and polite, so the reply is announced when it arrives. A region that
          mounted already filled would not be. */}
      <output data-slot="reply-slot" className="block empty:hidden">
        {status === 'replied' && reply !== null && <ReplyBlock text={reply} />}
      </output>
      <TryAskingList
        items={personaFor(me.personaKey).tryAsking}
        onPick={setDraft}
        className="mt-12"
      />
    </div>
  )
}

// Deleted in Phase 4: the streaming reply, with its citations, replaces this plain block.
function ReplyBlock({ text }: { text: string }) {
  return (
    <section
      aria-label="Open Door's reply"
      className="mt-6 w-full max-w-content rounded-lg border border-border-subtle bg-surface-sunken px-6 py-4 text-body text-ink"
    >
      <p className="m-0">{text}</p>
    </section>
  )
}
