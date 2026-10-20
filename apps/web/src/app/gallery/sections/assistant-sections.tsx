import { useState } from 'react'
import { Composer } from '@/components/assistant/composer'
import { conversationCopy } from '@/components/assistant/labels'
import { TryAskingList } from '@/components/assistant/try-asking-list'
import { Group, Section } from '../gallery-parts'

// The assistant components, each state under a heading with a stable id. Hover and focus are not
// shown: the tests hover and focus the real elements. Each composer gets the content width, which
// the trial's capture showed it lacking when the gallery's flex rows shrank it to its text.

const QUESTIONS = [
  'How many sick days do I get?',
  'Book next Friday off',
  'What holidays do we have this year?',
  'Who do I talk to about a concern?',
]

function Draft({
  initial = '',
  ...props
}: { initial?: string } & Partial<React.ComponentProps<typeof Composer>>) {
  const [value, setValue] = useState(initial)
  return <Composer value={value} onChange={setValue} onSubmit={() => {}} {...props} />
}

function TryAsking() {
  const [value, setValue] = useState('')
  return (
    <div className="flex w-full flex-col gap-6">
      <Composer value={value} onChange={setValue} onSubmit={() => {}} />
      <TryAskingList items={QUESTIONS} onPick={setValue} />
    </div>
  )
}

export function AssistantSections() {
  return (
    <>
      <Group title="Composer">
        <Section id="composer-empty" title="Composer, empty">
          <Draft />
        </Section>
        <Section id="composer-typed" title="Composer, with a question typed">
          <Draft initial="How many sick days do I get?" />
        </Section>
        <Section id="composer-error" title="Composer, after a failed send">
          <Draft initial="How many sick days do I get?" sendError={conversationCopy.sendFailed} />
        </Section>
        <Section id="composer-busy" title="Composer, sending">
          <Draft initial="How many sick days do I get?" busy />
        </Section>
      </Group>
      <Group title="Try asking">
        <Section id="try-asking-default" title="Try asking list, filling a composer">
          <TryAsking />
        </Section>
      </Group>
    </>
  )
}
