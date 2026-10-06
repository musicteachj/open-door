import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { PersonaKey } from '@/api/generated'
import { initialsOf } from '@/lib/initials'
import { PERSONAS, PERSONA_KEYS, personaFor } from './personas'

// Copied from docs/design/screens/01-landing/notes.md and 02-app-shell/notes.md (Copy), so a change
// to the constant that the design doesn't know about fails here.
const EXPECTED = {
  priya: {
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
  mateo: {
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
  marcus: {
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
  dana: {
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
} as const

describe('PERSONAS', () => {
  it('lists the four personas in the landing order', () => {
    expect(PERSONAS.map((p) => p.key)).toEqual(['priya', 'mateo', 'marcus', 'dana'])
  })

  it.each(Object.entries(EXPECTED))('pins %s exactly as the notes say', (key, expected) => {
    expect(personaFor(key as keyof typeof EXPECTED)).toEqual({ key, ...expected })
  })

  it.each(PERSONAS.map((p) => [p.key, p] as const))(
    '%s: initials agree with initialsOf',
    (_k, p) => {
      expect(p.initials).toBe(initialsOf(p.name))
    },
  )

  it.each(PERSONAS.map((p) => [p.key, p] as const))('%s: has four questions', (_k, p) => {
    expect(p.tryAsking).toHaveLength(4)
  })

  // Pinned from apps/api/app/modules/sandbox/seed_data.py (persona_key="dana", "marcus", "priya",
  // "mateo"), which the generated PersonaKey mirrors. Task 39's browser test checks that /me
  // agrees with this constant for each persona.
  it('uses the API persona keys', () => {
    expect([...PERSONA_KEYS].sort()).toEqual(['dana', 'marcus', 'mateo', 'priya'])
    expect(Object.values(PersonaKey).sort()).toEqual([...PERSONA_KEYS].sort())
  })

  it('keeps the API keys pinned to seed_data.py', () => {
    const seed = readFileSync(`${process.cwd()}/../api/app/modules/sandbox/seed_data.py`, 'utf8')
    const keys = [...seed.matchAll(/persona_key="([a-z]+)"/g)].map((m) => m[1]).sort()
    expect(keys).toEqual(['dana', 'marcus', 'mateo', 'priya'])
  })
})
