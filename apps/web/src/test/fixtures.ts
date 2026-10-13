import type { Me, PersonaKey } from '@/api/generated'

// One signed-in card per persona the tests use. Only the names differ in ways the tests read.
const PERSONAS: Record<PersonaKey, { givenName: string; familyName: string; title: string }> = {
  priya: { givenName: 'Priya', familyName: 'Raman', title: 'Visual Merchandiser' },
  marcus: { givenName: 'Marcus', familyName: 'Bell', title: 'Store Manager' },
  mateo: { givenName: 'Mateo', familyName: 'Alvarez', title: 'Sales Associate' },
  dana: { givenName: 'Dana', familyName: 'Whitfield', title: 'HR Director' },
}

// Real IDs are UUIDs, and the profile page refuses anything else before it calls the API.
const PERSONA_IDS: Record<PersonaKey, string> = {
  priya: '00000000-0000-4000-8000-00000000f001',
  marcus: '00000000-0000-4000-8000-00000000f002',
  mateo: '00000000-0000-4000-8000-00000000f003',
  dana: '00000000-0000-4000-8000-00000000f004',
}

// A sandbox lasts 24 hours, so a fresh one has about 21 hours left here: no banner, "21 h". It is
// fixed when the test file loads, so two calls to meFor() give the same person to compare.
const DEFAULT_EXPIRY = new Date(Date.now() + 21.5 * 3_600_000).toISOString()

/** `tenantExpiresAt` is when the sandbox resets. It defaults to 21.5 hours after the test file loaded. */
export function meFor(persona: PersonaKey, tenantExpiresAt: string = DEFAULT_EXPIRY): Me {
  return {
    id: PERSONA_IDS[persona],
    ...PERSONAS[persona],
    department: { id: 'dept-1', name: 'Store Operations' },
    // Mateo works in Texas, as the seed has him; the others are at the Oakland store in California.
    location:
      persona === 'mateo'
        ? {
            id: 'loc-3',
            code: 'aus',
            name: 'Austin warehouse',
            state: 'TX',
            timezone: 'America/Chicago',
          }
        : {
            id: 'loc-1',
            code: 'oak',
            name: 'Oakland store',
            state: 'CA',
            timezone: 'America/Los_Angeles',
          },
    manager: null,
    workEmail: `${persona}@example.test`,
    employmentType: persona === 'mateo' ? 'hourly' : 'salaried',
    isManager: persona === 'marcus',
    isHrAdmin: persona === 'dana',
    personaKey: persona,
    tenantExpiresAt,
  }
}

export function fullName(persona: PersonaKey): string {
  const { givenName, familyName } = PERSONAS[persona]
  return `${givenName} ${familyName}`
}
