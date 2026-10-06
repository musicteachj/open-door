import { act, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { getGetPersonPrivateQueryKey, type PersonaKey } from '@/api/generated'
import { installFakeApi } from '@/test/fake-api'
import { DIRECTORY_PEOPLE, installFakeDirectory, privateDetailsOf } from '@/test/fake-directory'
import { meFor } from '@/test/fixtures'
import { switchViaMenu } from '@/test/persona-menu'
import { renderApp } from '@/test/render-app'

// The profile at /directory/:personId, from docs/design/screens/04-directory, against a fake API.
// The viewer is whoever /me says; the fake /private answers like the server, and records every ask.
const LEO = DIRECTORY_PEOPLE.find((p) => p.familyName === 'Nakamura')!
const MARCUS = meFor('marcus')
const OTHER_PERSON = DIRECTORY_PEOPLE.find((p) => p.id !== LEO.id && p.id !== MARCUS.id)!

async function openProfile(viewer: PersonaKey, personId: string, at = `/directory/${personId}`) {
  const fakeApi = installFakeApi(viewer)
  const api = installFakeDirectory(viewer)
  const app = renderApp({ at })
  return { ...app, api, fakeApi }
}

const workDetails = () => screen.getByRole('region', { name: 'Work details' })
const privateDetails = () => screen.getByRole('region', { name: 'Private details' })
const profileHeading = (name: string) => screen.findByRole('heading', { level: 1, name })
const leoName = `${LEO.givenName} ${LEO.familyName}`

describe('the header', () => {
  it('shows the name, title, and department and location, with no "You" tag on someone else', async () => {
    await openProfile('priya', LEO.id)
    await profileHeading(leoName)
    // The header and the Work details both say it.
    expect(screen.getAllByText(LEO.title)).toHaveLength(2)
    expect(screen.getByText(`${LEO.department.name} · ${LEO.location.name}`)).toBeInTheDocument()
    expect(screen.queryByText('You')).not.toBeInTheDocument()
  })

  it('tags your own profile "You"', async () => {
    const priya = meFor('priya')
    await openProfile('priya', priya.id)
    const heading = await profileHeading('Priya Raman')
    expect(within(heading.parentElement!).getByText('You')).toBeInTheDocument()
  })
})

describe('work details', () => {
  it('shows the title, department, location, the manager as a profile link, and a mail link', async () => {
    await openProfile('priya', LEO.id)
    await profileHeading(leoName)
    const work = within(workDetails())
    expect(work.getByText(LEO.title)).toBeInTheDocument()
    expect(work.getByText(LEO.department.name)).toBeInTheDocument()
    expect(work.getByText(LEO.location.name)).toBeInTheDocument()
    expect(work.getByRole('link', { name: 'Marcus Bell' })).toHaveAttribute(
      'href',
      `/directory/${MARCUS.id}`,
    )
    expect(work.getByRole('link', { name: LEO.workEmail })).toHaveAttribute(
      'href',
      `mailto:${LEO.workEmail}`,
    )
  })

  it('says "None listed" for someone with no manager, and links no one', async () => {
    await openProfile('priya', MARCUS.id)
    await profileHeading('Marcus Bell')
    const work = within(workDetails())
    expect(work.getByText('None listed')).toBeInTheDocument()
    expect(work.queryByRole('link', { name: /Bell|Raman/ })).not.toBeInTheDocument()
  })

  it('opens the manager profile from the link', async () => {
    const { user, router } = await openProfile('priya', LEO.id)
    await profileHeading(leoName)
    await user.click(within(workDetails()).getByRole('link', { name: 'Marcus Bell' }))
    await profileHeading('Marcus Bell')
    expect(router.state.location.pathname).toBe(`/directory/${MARCUS.id}`)
  })
})

describe('private details for the person and for HR', () => {
  it('fetches them for yourself, shows the values, "Only you and HR can see these.", and the audit note', async () => {
    const priya = meFor('priya')
    const { api } = await openProfile('priya', priya.id)
    await profileHeading('Priya Raman')
    const details = within(privateDetails())
    const priyaCard = DIRECTORY_PEOPLE.find((p) => p.id === priya.id)!
    const values = privateDetailsOf(priyaCard)
    expect(await details.findByText(values.personalEmail)).toBeInTheDocument()
    expect(details.getByText(values.phone)).toBeInTheDocument()
    expect(details.getByText(values.homeAddress)).toBeInTheDocument()
    expect(details.getByText('June 22, 2000')).toBeInTheDocument()
    expect(details.getByText(/Only you and HR can see these\./)).toBeInTheDocument()
    expect(details.getByText('Viewing private details is recorded in the audit log.')).toBeVisible()
    expect(details.queryByText(/Visible to/)).not.toBeInTheDocument()
    expect(api.privateRequests).toEqual([priya.id])
  })

  it('fetches them for HR viewing someone else, naming that person: "Only Avery and HR can see these."', async () => {
    const { api } = await openProfile('dana', LEO.id)
    await profileHeading(leoName)
    const details = within(privateDetails())
    expect(await details.findByText(privateDetailsOf(LEO).personalEmail)).toBeInTheDocument()
    expect(details.getByText(`Only ${LEO.givenName} and HR can see these.`)).toBeInTheDocument()
    expect(details.getByText('Viewing private details is recorded in the audit log.')).toBeVisible()
    expect(api.privateRequests).toEqual([LEO.id])
  })

  it('shows no audit note and no values while they load', async () => {
    await openProfile('dana', LEO.id)
    await profileHeading(leoName)
    const details = within(privateDetails())
    expect(details.queryByText(/audit log/)).not.toBeInTheDocument()
    expect(details.queryByText(privateDetailsOf(LEO).phone)).not.toBeInTheDocument()
    await details.findByText(privateDetailsOf(LEO).phone)
  })

  it('shows an inline error with Retry when the private request fails, and Retry loads the values', async () => {
    const { user, api } = await openProfile('dana', LEO.id)
    api.failPrivate(500)
    await profileHeading(leoName)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("We couldn't load the private details.")
    // The work details are still there, and no value or audit note is claimed.
    expect(within(workDetails()).getByText(LEO.title)).toBeInTheDocument()
    expect(within(privateDetails()).queryByText(/audit log/)).not.toBeInTheDocument()

    api.failPrivate(null)
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    expect(
      await within(privateDetails()).findByText(privateDetailsOf(LEO).personalEmail),
    ).toBeInTheDocument()
  })

  it('shows the same inline error for a 403 on your own profile', async () => {
    const priya = meFor('priya')
    const { api } = await openProfile('priya', priya.id)
    api.failPrivate(403)
    await profileHeading('Priya Raman')
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})

describe('private details for everyone else', () => {
  it('shows four locked rows, "Visible to Avery and HR", and never asks for the values', async () => {
    const { api, queryClient } = await openProfile('priya', LEO.id)
    await profileHeading(leoName)
    const details = within(privateDetails())
    for (const label of ['Personal email', 'Phone', 'Home address', 'Date of birth']) {
      const term = details.getByText(label)
      expect(term.nextElementSibling).toHaveTextContent(`Visible to ${LEO.givenName} and HR`)
    }
    expect(details.getAllByText(`Visible to ${LEO.givenName} and HR`)).toHaveLength(4)
    expect(details.queryByText(/Only .* can see these/)).not.toBeInTheDocument()
    expect(details.queryByText(/audit log/)).not.toBeInTheDocument()
    expect(details.queryByText(privateDetailsOf(LEO).phone)).not.toBeInTheDocument()

    // Not after a re-render or a refetch either, nor once everything has settled.
    await queryClient.refetchQueries()
    await waitFor(() => expect(api.profileRequests.length).toBeGreaterThan(1))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(api.privateRequests).toEqual([])
  })

  it('shows no value in a locked row even if the cache somehow held one', async () => {
    const { queryClient } = await openProfile('priya', LEO.id)
    queryClient.setQueryData(getGetPersonPrivateQueryKey(LEO.id), privateDetailsOf(LEO))
    await profileHeading(leoName)
    const details = within(privateDetails())
    expect(details.getAllByText(`Visible to ${LEO.givenName} and HR`)).toHaveLength(4)
    for (const value of Object.values(privateDetailsOf(LEO))) {
      expect(screen.queryByText(value, { exact: false })).not.toBeInTheDocument()
    }
    expect(screen.queryByText('June 22, 2000')).not.toBeInTheDocument()
  })

  it('makes no private request for a manager who is not HR, even for their own report', async () => {
    const { api } = await openProfile('marcus', LEO.id)
    await profileHeading(leoName)
    expect(within(privateDetails()).getAllByText(/^Visible to /)).toHaveLength(4)
    expect(api.privateRequests).toEqual([])
  })

  it('makes no private request after switching to someone else, and clears the values HR saw', async () => {
    const { user, api, router } = await openProfile('dana', LEO.id)
    await profileHeading(leoName)
    await within(privateDetails()).findByText(privateDetailsOf(LEO).phone)
    expect(api.privateRequests).toEqual([LEO.id])

    api.viewAs('priya')
    await switchViaMenu(user, 'Priya')
    // A switch lands on Ask: open the same profile again as Priya, from a cleared cache.
    await screen.findByText(/Good (morning|afternoon|evening), Priya/)
    await act(() => router.navigate(`/directory/${LEO.id}`))
    await profileHeading(leoName)
    expect(within(privateDetails()).getAllByText(/^Visible to /)).toHaveLength(4)
    expect(screen.queryByText(privateDetailsOf(LEO).phone)).not.toBeInTheDocument()
    expect(screen.queryByText(/audit log/)).not.toBeInTheDocument()
    expect(api.privateRequests).toEqual([LEO.id])
  })

  it('makes no private request over the whole page lifetime when Priya switches to Marcus', async () => {
    const { user, api, router } = await openProfile('priya', LEO.id)
    await profileHeading(leoName)
    api.viewAs('marcus')
    await switchViaMenu(user, 'Marcus')
    // A switch lands on Ask: open the same profile again as Marcus.
    await screen.findByText(/Good (morning|afternoon|evening), Marcus/)
    await act(() => router.navigate(`/directory/${LEO.id}`))
    await profileHeading(leoName)
    expect(within(privateDetails()).getAllByText(/^Visible to /)).toHaveLength(4)
    expect(api.privateRequests).toEqual([])
  })

  it('decides from /me, not the URL: ids that look like the viewer or HR change nothing', async () => {
    const priya = meFor('priya')
    const { api } = await openProfile('priya', LEO.id, `/directory/${LEO.id}?id=${priya.id}&hr=1`)
    await profileHeading(leoName)
    expect(within(privateDetails()).getAllByText(/^Visible to /)).toHaveLength(4)
    expect(api.privateRequests).toEqual([])
  })

  it('makes no private request for an unrelated person either', async () => {
    const { api } = await openProfile('priya', OTHER_PERSON.id)
    await profileHeading(`${OTHER_PERSON.givenName} ${OTHER_PERSON.familyName}`)
    expect(api.privateRequests).toEqual([])
  })
})

describe('loading', () => {
  it('announces the profile loading politely, then clears it', async () => {
    await openProfile('dana', LEO.id)
    const status = await screen.findByText('Loading the profile')
    expect(status.tagName).toBe('OUTPUT')
    await profileHeading(leoName)
    await waitFor(() => expect(screen.queryByText('Loading the profile')).not.toBeInTheDocument())
  })

  it('announces the private details loading, then clears it', async () => {
    const { api } = await openProfile('dana', LEO.id)
    api.delayPrivate(200)
    await profileHeading(leoName)
    expect(await screen.findByText('Loading the private details')).toBeInTheDocument()
    await within(privateDetails()).findByText(privateDetailsOf(LEO).phone)
    expect(screen.queryByText('Loading the private details')).not.toBeInTheDocument()
  })
})

describe('errors', () => {
  it('shows not found inside the shell for an API 404', async () => {
    const { api } = await openProfile('priya', '00000000-0000-4000-8000-0000deadbeef')
    expect(
      await screen.findByRole('heading', { level: 1, name: "We couldn't find that page." }),
    ).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Sidebar' })).toBeInTheDocument()
    expect(api.profileRequests).toEqual(['00000000-0000-4000-8000-0000deadbeef'])
    expect(api.privateRequests).toEqual([])
  })

  it.each([
    ['text', 'not-a-uuid'],
    ['a path', 'x%2F..%2Fme'],
    ['a UUID with a suffix', `${LEO.id}%2Fprivate`],
    ['a UUID with a query', `${LEO.id}%3Fx%3D1`],
    ['an almost UUID', '00000000-0000-4000-8000-00000000000'],
  ])('shows not found without any request when the ID is %s', async (_name, id) => {
    const { api } = await openProfile('dana', id)
    expect(
      await screen.findByRole('heading', { level: 1, name: "We couldn't find that page." }),
    ).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Sidebar' })).toBeInTheDocument()
    expect(api.profileRequests).toEqual([])
    expect(api.privateRequests).toEqual([])
  })

  it('goes to the route boundary, inside the shell, for any other error', async () => {
    installFakeApi('priya')
    installFakeDirectory('priya')
    const { server } = await import('@/test/msw')
    const { http, HttpResponse } = await import('msw')
    server.use(
      http.get(`${window.location.origin}/api/v1/people/${LEO.id}`, () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'Boom', status: 500, instance: '/x' },
          { status: 500, headers: { 'X-Request-ID': 'e'.repeat(32) } },
        ),
      ),
    )
    renderApp({ at: `/directory/${LEO.id}` })
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Something went wrong on our side.' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Sidebar' })).toBeInTheDocument()
  })
})

describe('"← Directory"', () => {
  async function openFromList(search: string) {
    const fakeApi = installFakeApi('priya')
    const api = installFakeDirectory('priya')
    const app = renderApp({ at: `/directory${search}` })
    const list = await screen.findByRole('list', { name: 'People' })
    return { ...app, api, fakeApi, list }
  }

  it('returns to the list with the same search and filters, after clicking a row', async () => {
    const search = `?q=nakamura&department=${LEO.department.id}&location=${LEO.location.id}`
    const { user, router, api } = await openFromList(search)
    // The search, the filters and their results are what the visitor left.
    const people = api.matching({
      q: 'nakamura',
      departmentId: LEO.department.id,
      locationId: LEO.location.id,
    })
    const target = people[0]!
    const row = await screen.findByRole('link', {
      name: new RegExp(`^${target.givenName} Nakamura`),
    })
    await user.click(row)
    await profileHeading(`${target.givenName} Nakamura`)
    expect(router.state.location.pathname).toBe(`/directory/${target.id}`)

    await user.click(screen.getByRole('link', { name: 'Back to Directory' }))
    await screen.findByRole('list', { name: 'People' })
    expect(router.state.location.pathname).toBe('/directory')
    expect(router.state.location.search).toBe(search)
    expect(screen.getByRole('searchbox')).toHaveValue('nakamura')
  })

  it('goes back through history, so the scroll comes back too, rather than pushing a new entry', async () => {
    const { user, router } = await openFromList('?q=nakamura')
    await user.click(
      await screen.findByRole('link', { name: new RegExp(`^${LEO.givenName} Nakamura`) }),
    )
    await profileHeading(leoName)
    await user.click(screen.getByRole('link', { name: 'Back to Directory' }))
    await screen.findByRole('list', { name: 'People' })
    expect(router.state.historyAction).toBe('POP')
  })

  it('returns to the list through a manager link too, past every profile in between', async () => {
    const search = `?q=nakamura&department=${LEO.department.id}&location=${LEO.location.id}`
    const { user, router } = await openFromList(search)
    await user.click(
      await screen.findByRole('link', { name: new RegExp(`^${LEO.givenName} Nakamura`) }),
    )
    await profileHeading(leoName)
    await user.click(within(workDetails()).getByRole('link', { name: 'Marcus Bell' }))
    await profileHeading('Marcus Bell')
    await user.click(screen.getByRole('link', { name: 'Back to Directory' }))
    await screen.findByRole('list', { name: 'People' })
    expect(router.state.location.pathname).toBe('/directory')
    expect(router.state.location.search).toBe(search)
  })

  it('opens the plain directory when the profile was opened directly', async () => {
    const { user, router } = await openProfile('priya', LEO.id)
    await profileHeading(leoName)
    await user.click(screen.getByRole('link', { name: 'Back to Directory' }))
    await screen.findByRole('list', { name: 'People' })
    expect(router.state.location.pathname).toBe('/directory')
    expect(router.state.location.search).toBe('')
  })

  it('keeps a modified click (a new tab) as a plain link to the directory', async () => {
    const { user } = await openFromList('?q=nakamura')
    await user.click(
      await screen.findByRole('link', { name: new RegExp(`^${LEO.givenName} Nakamura`) }),
    )
    await profileHeading(leoName)
    expect(screen.getByRole('link', { name: 'Back to Directory' })).toHaveAttribute(
      'href',
      '/directory?q=nakamura',
    )
  })
})
