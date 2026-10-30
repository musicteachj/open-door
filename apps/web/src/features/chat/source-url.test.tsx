import { act, render, screen } from '@testing-library/react'
import { QueryClient } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router'
import { beforeEach, describe, expect, it } from 'vitest'
import { resetIdentity } from '@/lib/identity'
import { goneBackOverCount, useSourceUrl } from './source-url'

beforeEach(() => sessionStorage.clear())

function Probe() {
  const { key, open, close, clear } = useSourceUrl()
  const location = useLocation()
  return (
    <div>
      <output data-testid="url">{`${location.pathname}${location.search}`}</output>
      <output data-testid="key">{key ?? 'none'}</output>
      <button onClick={() => open('CA-4.3~p1')}>open p1</button>
      <button onClick={() => open('4.3~p1')}>open other</button>
      <button onClick={() => close()}>close</button>
      <button onClick={() => clear()}>clear</button>
      <button
        onClick={() => {
          clear()
          clear()
        }}
      >
        clear twice
      </button>
      <button
        onClick={() => {
          close()
          close()
        }}
      >
        close twice
      </button>
    </div>
  )
}

function setup(at: string) {
  const router = createMemoryRouter([{ path: '/ask', element: <Probe /> }], {
    initialEntries: ['/ask', at],
    initialIndex: 1,
  })
  render(<RouterProvider router={router} />)
  const url = () => screen.getByTestId('url').textContent
  const press = async (name: string) => {
    await act(async () => {
      screen.getByRole('button', { name }).click()
    })
  }
  return { router, url, press }
}

describe('useSourceUrl', () => {
  it('reads the source from the URL, and ignores a value that names no passage', () => {
    setup('/ask?source=CA-4.3~p1')
    expect(screen.getByTestId('key')).toHaveTextContent('CA-4.3~p1')
  })

  it('treats an unusable value as closed', () => {
    setup('/ask?source=nonsense')
    expect(screen.getByTestId('key')).toHaveTextContent('none')
  })

  it('opens with a new history entry, so Back closes it, and keeps the rest of the URL', async () => {
    const { router, url, press } = setup('/ask?x=1')
    await press('open p1')
    expect(url()).toBe('/ask?x=1&source=CA-4.3%7Ep1')
    await act(async () => {
      await router.navigate(-1)
    })
    expect(url()).toBe('/ask?x=1')
  })

  it('swaps by replacing the entry, so one Back still closes the panel', async () => {
    const { router, url, press } = setup('/ask')
    await press('open p1')
    await press('open other')
    expect(screen.getByTestId('key')).toHaveTextContent('4.3~p1')
    await act(async () => {
      await router.navigate(-1)
    })
    expect(url()).toBe('/ask')
  })

  it('closes a panel it opened by going back, leaving no forward entry or dead step', async () => {
    const { router, press } = setup('/ask')
    await press('open p1')
    const before = router.state.historyAction
    expect(before).toBe('PUSH')
    await press('close')
    expect(screen.getByTestId('key')).toHaveTextContent('none')
    expect(router.state.historyAction).toBe('POP')
  })

  it('closes a panel the URL arrived with by replacing, since there is no entry of its own to go back to', async () => {
    const { router, url, press } = setup('/ask?source=CA-4.3~p1&x=1')
    await press('close')
    expect(url()).toBe('/ask?x=1')
    expect(router.state.historyAction).toBe('REPLACE')
  })

  it('goes back only once when closed twice before the page catches up', async () => {
    const { router, url, press } = setup('/ask?first=1')
    await press('open p1')
    await press('close twice')
    // One entry back is "/ask?first=1". Two would be "/ask".
    expect(url()).toBe('/ask?first=1')
    expect(router.state.location.pathname).toBe('/ask')
  })

  it('marks only the entry that opens the panel, and a swap keeps what that entry said', async () => {
    const { router, press } = setup('/ask')
    await press('open p1')
    expect(router.state.location.state).toMatchObject({ keepScroll: true, openedSource: true })
    await press('open other')
    expect(router.state.location.state).toMatchObject({ keepScroll: true, openedSource: true })
  })

  it('leaves no marker on a plain entry: a swap on a deep link, or a replace that closes one', async () => {
    const { router, press } = setup('/ask?source=CA-4.3~p1')
    await press('open other')
    // A replace on the same page never moves the scroll, so it needs no marker, and this entry is
    // the page itself, not a panel's.
    expect(router.state.location.state).toBeNull()
    await press('close')
    expect(router.state.location.state).toBeNull()
  })

  it('remembers at most the last 50 entries gone back over, and forgets them on a persona switch', async () => {
    const router = createMemoryRouter([{ path: '/ask', element: <Probe /> }], {
      initialEntries: ['/ask'],
    })
    render(<RouterProvider router={router} />)
    for (let i = 0; i < 55; i++) {
      await act(async () => {
        await router.navigate('/ask?source=CA-4.3~p1', {
          state: { openedSource: true, keepScroll: true },
        })
      })
      await act(async () => {
        screen.getByRole('button', { name: 'clear' }).click()
      })
    }
    expect(goneBackOverCount()).toBe(50)
    resetIdentity(new QueryClient())
    expect(goneBackOverCount()).toBe(0)
  })

  it('leaves no marker when the source is cleared', async () => {
    const { router, press } = setup('/ask?source=CA-4.3~p1')
    await press('clear')
    expect(router.state.location.state).toBeNull()
    expect(router.state.location.search).toBe('')
  })

  describe('clearing a panel the panel opened (Start a new conversation)', () => {
    it('goes back over the entry the panel added, so no step is left that changes nothing', async () => {
      const { router, url, press } = setup('/ask')
      await press('open p1')
      await press('clear')
      expect(url()).toBe('/ask')
      expect(screen.getByTestId('key')).toHaveTextContent('none')
      expect(router.state.historyAction).toBe('POP')
      expect(router.state.location.state).toBeNull()
    })

    it('goes back only once when cleared twice, as a development double effect does', async () => {
      const { router, url, press } = setup('/ask?first=1')
      await press('open p1')
      await press('clear twice')
      expect(url()).toBe('/ask?first=1')
      expect(router.state.location.pathname).toBe('/ask')
    })

    it('leaves no Forward step that reopens the panel: going forward lands on a closed page', async () => {
      const { router, url, press } = setup('/ask')
      await press('open p1')
      await press('clear')
      await act(async () => {
        await router.navigate(1)
      })
      expect(screen.getByTestId('key')).toHaveTextContent('none')
      expect(url()).toBe('/ask')
      // Its address was replaced, not left as "?source=" for a later render to trip over.
      expect(router.state.historyAction).toBe('REPLACE')
    })

    it('still reopens a panel the same way once the person opens one again', async () => {
      const { url, press } = setup('/ask')
      await press('open p1')
      await press('clear')
      await press('open p1')
      expect(url()).toBe('/ask?source=CA-4.3%7Ep1')
      expect(screen.getByTestId('key')).toHaveTextContent('CA-4.3~p1')
    })

    it('remembers the stale entry across a reload, in the session', async () => {
      const { press } = setup('/ask')
      await press('open p1')
      await press('clear')
      expect(sessionStorage.getItem('od.staleSourceEntries')).toMatch(/\w/)
    })
  })
})

describe('two components using the hook at once', () => {
  function Two() {
    const first = useSourceUrl()
    const second = useSourceUrl()
    return (
      <div>
        <button onClick={() => first.open('CA-4.3~p1')}>open</button>
        <button
          onClick={() => {
            first.clear()
            second.clear()
          }}
        >
          clear both
        </button>
      </div>
    )
  }

  it('goes back once when both ask to clear', async () => {
    const router = createMemoryRouter([{ path: '/ask', element: <Two /> }], {
      initialEntries: ['/ask?before=1', '/ask?first=1'],
      initialIndex: 1,
    })
    render(<RouterProvider router={router} />)
    await act(async () => screen.getByRole('button', { name: 'open' }).click())
    await act(async () => screen.getByRole('button', { name: 'clear both' }).click())
    expect(router.state.location.search).toBe('?first=1')
  })
})
