import type { Me, PersonaKey } from '@/api/generated'

// One signed-in card per persona the tests use. Only the names differ in ways the tests read.
const PERSONAS: Record<PersonaKey, { givenName: string; familyName: string; title: string }> = {
  priya: { givenName: 'Priya', familyName: 'Raman', title: 'Visual Merchandiser' },
  marcus: { givenName: 'Marcus', familyName: 'Bell', title: 'Store Manager' },
  mateo: { givenName: 'Mateo', familyName: 'Alvarez', title: 'Sales Associate' },
  dana: { givenName: 'Dana', familyName: 'Whitfield', title: 'HR Director' },
}

export function meFor(persona: PersonaKey): Me {
  return {
    id: `00000000-0000-4000-8000-${persona.padEnd(12, '0')}`,
    ...PERSONAS[persona],
    department: { id: 'dept-1', name: 'Store Operations' },
    location: { id: 'loc-1', name: 'Oak Street', state: 'CA', timezone: 'America/Los_Angeles' },
    manager: null,
    workEmail: `${persona}@example.test`,
    employmentType: 'salaried',
    isManager: persona === 'marcus',
    isHrAdmin: persona === 'dana',
    personaKey: persona,
    tenantExpiresAt: '2026-10-06T12:00:00Z',
  }
}

export function fullName(persona: PersonaKey): string {
  const { givenName, familyName } = PERSONAS[persona]
  return `${givenName} ${familyName}`
}
