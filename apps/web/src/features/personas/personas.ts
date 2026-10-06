import type { PersonaKey } from '@/api/generated'

// The four demo personas, in the landing page's order. The landing page needs this before any
// session exists, and the persona menu and the assistant home read it too. The keys are the API's
// (seed_data.py). Task 39's browser test starts a sandbox as each persona and checks that /me's
// name, title, and location agree with this constant, so the seed and it can't drift apart.
// Wording comes from docs/design/screens/01-landing/notes.md and 02-app-shell/notes.md (Copy).

export type Persona = {
  key: PersonaKey
  name: string
  firstName: string
  title: string
  /** The location's name, as the seed spells it. */
  location: string
  initials: string
  /** The landing card's one line on what to try. */
  cardPrompt: string
  /** The four "Try asking" questions on the assistant home. */
  tryAsking: readonly [string, string, string, string]
}

export const PERSONAS: readonly Persona[] = [
  {
    key: 'priya',
    name: 'Priya Raman',
    firstName: 'Priya',
    title: 'Visual Merchandiser',
    location: 'Oakland store',
    initials: 'PR',
    cardPrompt: 'Ask about California sick leave and book a day off.',
    tryAsking: [
      'How many sick days do I get?',
      'Book next Friday off',
      'What holidays do we have this year?',
      'Who do I talk to about a concern?',
    ],
  },
  {
    key: 'mateo',
    name: 'Mateo Alvarez',
    firstName: 'Mateo',
    title: 'Warehouse Associate',
    location: 'Austin warehouse',
    initials: 'MA',
    cardPrompt: 'Ask the same questions and get Texas answers.',
    tryAsking: [
      'How many sick days do I get?',
      'Do I get paid for holidays?',
      'Book next Friday off',
      'Who do I talk to about a concern?',
    ],
  },
  {
    key: 'marcus',
    name: 'Marcus Bell',
    firstName: 'Marcus',
    title: 'Store Manager',
    location: 'Oakland store',
    initials: 'MB',
    cardPrompt: 'Approve a request and check on your team.',
    tryAsking: [
      "What's waiting for my approval?",
      'Who on my team is off this week?',
      'How many sick days do I get?',
      'Who do I talk to about a concern?',
    ],
  },
  {
    key: 'dana',
    name: 'Dana Whitfield',
    firstName: 'Dana',
    title: 'HR Business Partner',
    location: 'Denver HQ',
    initials: 'DW',
    cardPrompt: 'See the confidential case queue.',
    tryAsking: [
      'Show me the open cases',
      'Summarize the newest case',
      'What does the handbook say about reporting harassment?',
      'How has the assistant been doing this week?',
    ],
  },
]

export const PERSONA_KEYS: readonly PersonaKey[] = PERSONAS.map((p) => p.key)

export function personaFor(key: PersonaKey): Persona {
  const persona = PERSONAS.find((p) => p.key === key)
  if (!persona) throw new Error(`Unknown persona: ${key}`)
  return persona
}
