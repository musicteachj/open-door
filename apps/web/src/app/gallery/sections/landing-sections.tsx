import { PersonaCard } from '@/components/landing/persona-card'
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
