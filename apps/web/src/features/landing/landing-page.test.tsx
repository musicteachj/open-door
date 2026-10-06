import { act, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { getGetMeQueryKey } from '@/api/generated'
import { PERSONAS } from '@/features/personas/personas'
import { AI_DISCLOSURE } from '@/lib/disclosure'
import { installFakeApi } from '@/test/fake-api'
import { meFor } from '@/test/fixtures'
import { server } from '@/test/msw'
import { renderApp } from '@/test/render-app'

const SANDBOXES = () => `${window.location.origin}/api/v1/sandboxes`
const card = (firstName: string) =>
  screen.findByRole('button', { name: new RegExp(`^Start a sandbox as ${firstName} `) })
const cards = () => screen.getAllByRole('button', { name: /^Start a sandbox as / })

function gate() {
  let resolve = () => {}
  const promise = new Promise<void>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function failStarts(status = 500) {
  server.use(
    http.post(
      SANDBOXES(),
      () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'Boom', status, instance: '/x' },
          { status },
        ),
      { once: true },
    ),
  )
}

describe('the landing page', () => {
  it('shows the pitch, the picker, the sandbox note, and the footer', async () => {
    installFakeApi()
    renderApp({ at: '/' })
    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: 'Your open-door policy, now always open.',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText(/^An AI help desk for HR questions\./)).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Choose who to be' })).toBeInTheDocument()
    expect(
      screen.getByText(
        'Each visit gets its own private copy of Juniper Row, a fictional company. It resets after 24 hours.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText(AI_DISCLOSURE)).toBeInTheDocument()
    expect(
      screen.getByText(
        "Juniper Row and everyone in it are fictional. This is a demo, not legal advice. Don't enter real personal information.",
      ),
    ).toBeInTheDocument()
  })

  it('hides "How it\'s built" and the tour until Phase 7 builds them', async () => {
    installFakeApi()
    renderApp({ at: '/' })
    await screen.findByRole('heading', { level: 2, name: 'Choose who to be' })
    expect(screen.queryByText("How it's built")).not.toBeInTheDocument()
    expect(screen.queryByText('Take the 2-minute tour')).not.toBeInTheDocument()
  })

  it('lists one card per persona, in order, as list items', async () => {
    installFakeApi()
    renderApp({ at: '/' })
    await card('Priya')
    const list = screen.getByRole('list')
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(PERSONAS.length)
    PERSONAS.forEach((persona, index) => {
      const button = within(items[index]!).getByRole('button')
      expect(button).toHaveAccessibleName(
        `Start a sandbox as ${persona.name}, ${persona.title}, ${persona.location}. ${persona.cardPrompt}`,
      )
    })
  })

  it('shows the card starting, disables the others, and announces it politely', async () => {
    const api = installFakeApi()
    const held = gate()
    server.use(
      http.post(SANDBOXES(), async () => {
        await held.promise
        api.signIn('priya')
        return HttpResponse.json(
          { tenant: { id: 't', expiresAt: '2026-10-06T12:00:00Z' }, me: meFor('priya') },
          { status: 201 },
        )
      }),
    )
    const { user } = renderApp({ at: '/' })
    await user.click(await card('Priya'))

    const priya = await card('Priya')
    await waitFor(() => expect(priya).toHaveAttribute('aria-busy', 'true'))
    expect(priya).toBeEnabled()
    for (const other of cards().filter((button) => button !== priya)) expect(other).toBeDisabled()
    const announcements = screen.getAllByRole('status').map((status) => status.textContent)
    expect(announcements).toContain('Setting up Juniper Row…')
    held.resolve()
    await screen.findByRole('heading', {
      level: 1,
      name: /^Good (morning|afternoon|evening), Priya\.$/,
    })
  })

  it('resets the identity, stores the new me, and lands on /ask', async () => {
    const api = installFakeApi()
    const { user, router, queryClient } = renderApp({ at: '/' })
    queryClient.setQueryData(['someone-elses-data'], 'stale')
    await user.click(await card('Marcus'))
    await screen.findByRole('heading', {
      level: 1,
      name: /^Good (morning|afternoon|evening), Marcus\.$/,
    })
    expect(router.state.location.pathname).toBe('/ask')
    expect(api.signedInAs()).toBe('marcus')
    expect(queryClient.getQueryData(['someone-elses-data'])).toBeUndefined()
    expect(queryClient.getQueryData(getGetMeQueryKey())).toEqual(meFor('marcus'))
  })

  it('re-enables the cards on failure and shows an error whose Retry starts the same persona', async () => {
    installFakeApi()
    failStarts()
    const { user } = renderApp({ at: '/' })
    await user.click(await card('Mateo'))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("We couldn't start a sandbox.")
    for (const button of cards()) expect(button).toBeEnabled()
    for (const button of cards()) expect(button).not.toHaveAttribute('aria-busy')

    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    await screen.findByRole('heading', {
      level: 1,
      name: /^Good (morning|afternoon|evening), Mateo\.$/,
    })
  })

  it('takes the error away when a card is chosen again', async () => {
    installFakeApi()
    failStarts()
    const { user } = renderApp({ at: '/' })
    await user.click(await card('Priya'))
    await screen.findByRole('alert')
    await user.click(await card('Dana'))
    await screen.findByRole('heading', {
      level: 1,
      name: /^Good (morning|afternoon|evening), Dana\.$/,
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('sends a signed-in visitor to /ask', async () => {
    installFakeApi('priya')
    const { router } = renderApp({ at: '/' })
    await screen.findByRole('heading', {
      level: 1,
      name: /^Good (morning|afternoon|evening), Priya\.$/,
    })
    expect(router.state.location.pathname).toBe('/ask')
  })

  it('still shows the picker when the first /me fails with a 500', async () => {
    const api = installFakeApi()
    api.failMe(500)
    renderApp({ at: '/' })
    expect(await card('Priya')).toBeEnabled()
    await act(async () => {})
  })
})
