import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor } from '@testing-library/react'
import { createMemoryRouter, MemoryRouter, Outlet, redirect, RouterProvider } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { installFakeApi } from '@/test/fake-api'
import { installAssistantApi } from '@/test/fake-assistant'
import { meFor } from '@/test/fixtures'
import { stubAbsoluteUrls } from '@/test/absolute-urls'
import { TourRunner } from './tour-runner'
import { TOUR } from './script'
import { useTourStore } from './store'

// The runner's ask for a step's persona, with the shell's `switchTo` stood in for.

function mount(switchTo: (key: string, options?: { tour?: boolean; to?: string }) => boolean) {
  stubAbsoluteUrls()
  installFakeApi('priya')
  installAssistantApi()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/ask']}>
        <TourRunner
          me={meFor('priya') as never}
          actions={{ switchTo }}
          onChoosePersona={() => {}}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useTourStore.setState(useTourStore.getInitialState())
})

describe('asking for the step’s persona', () => {
  it('asks again after the shell refused, and the step goes on once it is free', async () => {
    const switchTo = vi
      .fn<(key: string, options?: { tour?: boolean; to?: string }) => boolean>()
      .mockReturnValueOnce(false)
      .mockReturnValue(true)
    useTourStore.setState({ started: true, active: true, step: 1, entering: true })
    mount(switchTo)
    await waitFor(() => expect(switchTo).toHaveBeenCalledTimes(2))
    expect(useTourStore.getState().switchTried).toBe(true)
    // Asked for once it started, never again.
    await new Promise((resolve) => setTimeout(resolve, 600))
    expect(switchTo).toHaveBeenCalledTimes(2)
  })

  it('tells the switch to land on the step’s own page', async () => {
    const switchTo = vi
      .fn<(key: string, options?: { tour?: boolean; to?: string }) => boolean>()
      .mockReturnValue(true)
    const dana = TOUR.findIndex((s) => s.persona === 'dana')
    useTourStore.setState({ started: true, active: true, step: dana, entering: true })
    mount(switchTo)
    await waitFor(() => expect(switchTo).toHaveBeenCalledTimes(1))
    expect(switchTo).toHaveBeenCalledWith('dana', { tour: true, to: TOUR[dana]!.path })
  })
})

describe('taking the visitor to the step’s page', () => {
  it('goes once, and shows the step anyway when the page redirects away', async () => {
    stubAbsoluteUrls()
    installFakeApi('priya')
    installAssistantApi()
    const switchTo = vi.fn<() => boolean>(() => true)
    let redirects = 0
    useTourStore.setState({ started: true, active: true, step: 0, entering: true })
    // A loader that redirects, so the router never shows the step's own path.
    const router = createMemoryRouter(
      [
        {
          element: (
            <>
              <Outlet />
              <TourRunner
                me={meFor('priya') as never}
                actions={{ switchTo }}
                onChoosePersona={() => {}}
              />
            </>
          ),
          children: [
            {
              path: TOUR[0]!.path,
              loader: () => {
                redirects++
                return redirect('/elsewhere')
              },
            },
            { path: '*', element: null },
          ],
        },
      ],
      { initialEntries: ['/handbook'] },
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(useTourStore.getState().entering).toBe(false))
    expect(router.state.location.pathname).toBe('/elsewhere')
    // Taken to the step's page once, not again for every path the redirect lands on.
    expect(redirects).toBe(1)
  })
})
