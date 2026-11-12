import { InlineError } from '@/components/feedback/inline-error'
import { PersonaCard } from '@/components/landing/persona-card'
import { TurnstileSlot } from '@/components/landing/turnstile-slot'
import { Group, Section } from '../gallery-parts'

// The persona card in its three states. Hover and focus are not shown: the tests hover and focus
// the real element.

const PRIYA = {
  name: 'Priya Raman',
  role: 'Visual Merchandiser',
  location: 'Oakland store',
  prompt: 'Ask about California sick leave and book a day off.',
}

const MATEO = {
  name: 'Mateo Alvarez',
  role: 'Warehouse Associate',
  location: 'Austin warehouse',
  prompt: 'Ask the same questions and get Texas answers.',
}

export function LandingSections() {
  return (
    <>
      <PersonaCardStates />
      <StartRefusalStates />
    </>
  )
}

function StartRefusalStates() {
  return (
    <Group title="Sandbox start">
      <Section id="start-refusal-retry" title="Start refused, a retry can help (the check failed)">
        <div className="w-full max-w-xl">
          <InlineError
            message="We couldn't confirm you're a person. Please try again."
            onRetry={() => {}}
          />
        </div>
      </Section>
      <Section id="start-refusal-limit" title="Start refused, a limit (no Retry)">
        <div className="w-full max-w-xl">
          <InlineError message="You've started several sandboxes in a short time. Please try again in 12 minutes, or keep using the one you have." />
        </div>
      </Section>
      <Section
        id="turnstile-slot-place"
        title="Cloudflare's check, in its place under the card that was pressed"
      >
        <div className="w-72">
          <PersonaCard {...PRIYA} onSelect={() => {}} />
          <TurnstileSlot>
            {/* A stand-in for Cloudflare's checkbox (300 by 65 px). It shows only when Cloudflare asks. */}
            <div className="flex h-16.25 w-75 max-w-full items-center justify-center rounded-md border border-dashed border-border text-small text-ink-muted">
              Cloudflare's check appears here
            </div>
          </TurnstileSlot>
        </div>
      </Section>
    </Group>
  )
}

function PersonaCardStates() {
  return (
    <Group title="Persona card">
      <Section id="persona-card-default" title="Persona card, default">
        <div className="w-72">
          <PersonaCard {...PRIYA} onSelect={() => {}} />
        </div>
      </Section>
      <Section id="persona-card-starting" title="Persona card, starting (still enabled)">
        <div className="w-72">
          <PersonaCard {...PRIYA} status="starting" onSelect={() => {}} />
        </div>
      </Section>
      <Section id="persona-card-disabled" title="Persona card, disabled while another one starts">
        <div className="w-72">
          <PersonaCard {...MATEO} disabled onSelect={() => {}} />
        </div>
      </Section>
    </Group>
  )
}
