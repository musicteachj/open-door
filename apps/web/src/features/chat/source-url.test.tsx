import { act, render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router'
import { describe, expect, it } from 'vitest'
import { useSourceUrl } from './source-url'

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

  it('leaves no marker when the source is cleared', async () => {
    const { router, press } = setup('/ask?source=CA-4.3~p1')
    await press('clear')
    expect(router.state.location.state).toBeNull()
    expect(router.state.location.search).toBe('')
  })
})
