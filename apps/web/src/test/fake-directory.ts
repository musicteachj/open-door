import { http, HttpResponse } from 'msw'
import type {
  DirectoryCard,
  DirectoryFacets,
  DirectoryPage,
  PersonaKey,
  PrivateDetails,
} from '@/api/generated'
import { meFor } from './fixtures'
import { server } from './msw'
import { isUuid } from '@/lib/uuid'

// A fake directory behind MSW: 120 people sorted by family name, given name, then ID, three
// locations, four departments, and the API's search, filters, cursor, and facet counts. It records
// every request so a test can say what was (and was not) sent.
const url = (path: string) => `${window.location.origin}${path}`

const LOCATIONS = [
  {
    id: '00000000-0000-4000-9000-000000000001',
    code: 'aus',
    name: 'Austin warehouse',
    city: 'Austin',
    state: 'TX',
    timezone: 'America/Chicago',
  },
  {
    id: '00000000-0000-4000-9000-000000000002',
    code: 'den',
    name: 'Denver HQ',
    city: 'Denver',
    state: 'CO',
    timezone: 'America/Denver',
  },
  {
    id: '00000000-0000-4000-9000-000000000003',
    code: 'oak',
    name: 'Oakland store',
    city: 'Oakland',
    state: 'CA',
    timezone: 'America/Los_Angeles',
  },
]
const DEPARTMENTS = [
  { id: '00000000-0000-4000-a000-000000000001', name: 'Distribution' },
  { id: '00000000-0000-4000-a000-000000000002', name: 'Finance' },
  { id: '00000000-0000-4000-a000-000000000003', name: 'Information Technology' },
  { id: '00000000-0000-4000-a000-000000000004', name: 'Store Operations' },
  // Nobody works here, so choosing it is the way to a list with no one in it.
  { id: '00000000-0000-4000-a000-000000000005', name: 'Legal' },
]
DEPARTMENTS.sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id))
const FAMILY = [
  'Adams',
  'Baker',
  'Bell',
  'Carter',
  'Diaz',
  'Evans',
  'Foster',
  'Garcia',
  'Hayes',
  'Ibarra',
  'Jensen',
  'Kapoor',
  'Lopez',
  'Moreno',
  'Nakamura',
  'Ortiz',
  'Patel',
  'Quinn',
  'Raman',
  'Singh',
  'Turner',
  'Underwood',
  'Vega',
  'Walker',
  'Xu',
  'Young',
  'Zhang',
  'Archer',
  'Brooks',
  'Cole',
  'Dunn',
  'Ellis',
  'Fisher',
  'Grant',
  'Hunt',
  'Irwin',
  'Jordan',
  'Kim',
  'Lane',
  'Mason',
]
const GIVEN = ['Avery', 'Jordan', 'Riley']

const PEOPLE: DirectoryCard[] = FAMILY.flatMap((familyName, f) =>
  GIVEN.map((givenName, g): DirectoryCard => {
    const n = f * GIVEN.length + g
    return {
      id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
      givenName,
      familyName,
      title: `Associate ${n}`,
      department: DEPARTMENTS.filter((d) => d.id !== '00000000-0000-4000-a000-000000000005')[
        n % 4
      ]!,
      location: LOCATIONS[n % LOCATIONS.length]!,
      manager: null,
      workEmail: `${givenName}.${familyName}@juniperrow.example`.toLowerCase(),
    }
  }),
)

// The signed-in personas are in the list too, so "You" has a row to tag.
const priya = meFor('priya')
const marcus = meFor('marcus')
function plant(id: string, givenName: string, familyName: string, at: number) {
  PEOPLE[at] = { ...PEOPLE[at]!, id, givenName, familyName }
}
plant(priya.id, 'Priya', 'Raman', 54)
plant(marcus.id, 'Marcus', 'Bell', 6)
PEOPLE.sort(
  (a, b) =>
    a.familyName.localeCompare(b.familyName) ||
    a.givenName.localeCompare(b.givenName) ||
    a.id.localeCompare(b.id),
)

/** Marcus's 44 reports: the first 44 people, in directory order, who aren't Marcus. */
const MARCUS_TEAM = new Set(
  PEOPLE.filter((p) => p.id !== marcus.id)
    .slice(0, 44)
    .map((p) => p.id),
)

// Marcus manages everyone else, so a profile has a manager to link to, and his own has none.
const MARCUS_REF = { id: marcus.id, givenName: 'Marcus', familyName: 'Bell' }
for (const person of PEOPLE) person.manager = person.id === marcus.id ? null : MARCUS_REF

/** The private details the fake holds for anyone, built from the person's name. */
export function privateDetailsOf(person: DirectoryCard): PrivateDetails {
  const handle = `${person.givenName}.${person.familyName}`.toLowerCase()
  return {
    personalEmail: `${handle}@example.com`,
    phone: '(510) 555-0175',
    homeAddress: '4221 Bluebell Way, Oakland, CA 94610',
    dateOfBirth: '2000-06-22',
  }
}

type Filters = { q: string; locationId: string; departmentId: string; team: boolean }

function matches(person: DirectoryCard, f: Filters, team: Set<string>): boolean {
  const q = f.q.trim().toLowerCase()
  const text = `${person.givenName} ${person.familyName} ${person.title} ${person.workEmail}`
  return (
    (!q || text.toLowerCase().includes(q)) &&
    (!f.locationId || person.location.id === f.locationId) &&
    (!f.departmentId || person.department.id === f.departmentId) &&
    (!f.team || team.has(person.id))
  )
}

/** What the API refuses with a 422: a search over 100 characters (trimmed) or with a NUL, a filter ID that isn't a UUID, a page size outside 1-100. */
function refusal(params: URLSearchParams): string | null {
  const q = params.get('q')
  if (q !== null && (q.includes('\0') || q.trim().length > 100)) return 'The search is not valid.'
  for (const name of ['locationId', 'departmentId']) {
    const id = params.get(name)
    if (id !== null && !isUuid(id)) return `${name} is not a valid UUID.`
  }
  const limit = params.get('limit')
  if (
    limit !== null &&
    !(Number.isInteger(Number(limit)) && Number(limit) >= 1 && Number(limit) <= 100)
  )
    return 'The page size is not valid.'
  return null
}

function unprocessable(detail: string) {
  return HttpResponse.json(
    {
      type: 'about:blank',
      title: 'Unprocessable',
      status: 422,
      instance: '/api/v1/people',
      detail,
    },
    { status: 422, headers: { 'X-Request-ID': 'c'.repeat(32) } },
  )
}

function filtersOf(params: URLSearchParams): Filters {
  return {
    q: params.get('q') ?? '',
    locationId: params.get('locationId') ?? '',
    departmentId: params.get('departmentId') ?? '',
    team: params.get('team') === 'mine',
  }
}

export const DIRECTORY_SIZE = PEOPLE.length
export const DIRECTORY_PEOPLE = PEOPLE
export const LOCATION_OPTIONS = LOCATIONS
export const DEPARTMENT_OPTIONS = DEPARTMENTS
export const fullNameOf = (p: DirectoryCard) => `${p.givenName} ${p.familyName}`

export function installFakeDirectory(persona: PersonaKey = 'priya') {
  const team = persona === 'marcus' ? MARCUS_TEAM : new Set<string>()
  const listRequests: URL[] = []
  const facetRequests: URL[] = []
  let listFailure: number | null = null
  let laterFailure: number | null = null
  let facetsFailure: number | null = null
  let listFailureFor: { when: Record<string, string>; status: number } | null = null
  let listDelayMs = 0
  let facetsDelayMs = 0
  let viewer = persona
  const profileRequests: string[] = []
  const privateRequests: string[] = []
  let privateFailure: number | null = null
  let privateDelayMs = 0
  const problem = (status: number, title: string, path: string) =>
    HttpResponse.json(
      { type: 'about:blank', title, status, instance: path },
      { status, headers: { 'X-Request-ID': 'd'.repeat(32) } },
    )

  server.use(
    http.get(url('/api/v1/people/facets'), async ({ request }) => {
      const u = new URL(request.url)
      facetRequests.push(u)
      const refused = refusal(u.searchParams)
      if (refused) return unprocessable(refused)
      if (facetsDelayMs > 0) await new Promise((resolve) => setTimeout(resolve, facetsDelayMs))
      if (facetsFailure !== null) return problem(facetsFailure, 'Failure', '/api/v1/people/facets')
      const f = filtersOf(u.searchParams)
      const count = (over: Partial<Filters>) =>
        PEOPLE.filter((p) => matches(p, { ...f, ...over }, team)).length
      const facets: DirectoryFacets = {
        total: PEOPLE.length,
        matching: count({}),
        locations: LOCATIONS.map((l) => ({ ...l, count: count({ locationId: l.id }) })),
        departments: DEPARTMENTS.map((d) => ({ ...d, count: count({ departmentId: d.id }) })),
        myTeam: team.size === 0 ? null : count({ team: true }),
      }
      return HttpResponse.json(facets)
    }),
    http.get(url('/api/v1/people'), async ({ request }) => {
      const u = new URL(request.url)
      listRequests.push(u)
      const refused = refusal(u.searchParams)
      if (refused) return unprocessable(refused)
      if (listDelayMs > 0) await new Promise((resolve) => setTimeout(resolve, listDelayMs))
      const only = listFailureFor
      const failure =
        listFailure ??
        (u.searchParams.has('cursor') ? laterFailure : null) ??
        (only && Object.entries(only.when).every(([k, v]) => u.searchParams.get(k) === v)
          ? only.status
          : null)
      if (failure !== null) {
        return HttpResponse.json(
          {
            type: 'about:blank',
            title: 'Failure',
            status: failure,
            instance: '/api/v1/people',
          },
          { status: failure, headers: { 'X-Request-ID': 'b'.repeat(32) } },
        )
      }
      const limit = Number(u.searchParams.get('limit') ?? 50)
      const start = Number(u.searchParams.get('cursor') ?? 0)
      const all = PEOPLE.filter((p) => matches(p, filtersOf(u.searchParams), team))
      const page: DirectoryPage = {
        items: all.slice(start, start + limit),
        nextCursor: start + limit < all.length ? String(start + limit) : null,
      }
      return HttpResponse.json(page)
    }),
    http.get(url('/api/v1/people/:personId'), ({ params }) => {
      const id = String(params.personId)
      profileRequests.push(id)
      const person = PEOPLE.find((p) => p.id === id)
      return person ? HttpResponse.json(person) : problem(404, 'Not found', `/api/v1/people/${id}`)
    }),
    // Like the server: only the person and HR may read, and anyone else is refused.
    http.get(url('/api/v1/people/:personId/private'), async ({ params }) => {
      const id = String(params.personId)
      privateRequests.push(id)
      if (privateDelayMs > 0) await new Promise((resolve) => setTimeout(resolve, privateDelayMs))
      const path = `/api/v1/people/${id}/private`
      if (privateFailure !== null) return problem(privateFailure, 'Failure', path)
      if (viewer !== 'dana' && meFor(viewer).id !== id) return problem(403, 'Forbidden', path)
      const person = PEOPLE.find((p) => p.id === id)
      return person ? HttpResponse.json(privateDetailsOf(person)) : problem(404, 'Not found', path)
    }),
  )

  return {
    /** The IDs of every GET /people/{id}, in order. */
    profileRequests,
    /** The IDs of every GET /people/{id}/private, in order: for anyone else this must stay empty. */
    privateRequests,
    /** Who the fake answers /private for, after a persona switch. */
    viewAs: (next: PersonaKey) => {
      viewer = next
    },
    /** Hold each /private answer for this long. */
    delayPrivate: (ms: number) => {
      privateDelayMs = ms
    },
    /** Make /private answer this status, or work again with null. */
    failPrivate: (status: number | null) => {
      privateFailure = status
    },
    listRequests,
    facetRequests,
    /** Every list request's search parameters, as plain objects. */
    listParams: () => listRequests.map((u) => Object.fromEntries(u.searchParams)),
    /** Make the list answer this status, or work again with null. */
    failList: (status: number | null) => {
      listFailure = status
    },
    /** Make only the requests that carry a cursor (page two on) answer this status, or work again with null. */
    failLaterPages: (status: number | null) => {
      laterFailure = status
    },
    /** Make the facets answer this status, or work again with null. */
    failFacets: (status: number | null) => {
      facetsFailure = status
    },
    /** Make only the list requests carrying all of these parameters answer this status. Null undoes it. */
    failListWhen: (when: Record<string, string> | null, status = 500) => {
      listFailureFor = when && { when, status }
    },
    /** Hold each facets answer for this long. */
    delayFacets: (ms: number) => {
      facetsDelayMs = ms
    },
    /** Hold each list answer for this long. */
    delayList: (ms: number) => {
      listDelayMs = ms
    },
    /** Everyone who matches, in directory order. */
    matching: (params: Partial<Record<'q' | 'locationId' | 'departmentId' | 'team', string>>) =>
      PEOPLE.filter((p) => matches(p, filtersOf(new URLSearchParams(params)), team)),
  }
}
