import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { stubMediaQuery } from '@/test/media-query'
import { useMediaQuery } from './use-media-query'

function Probe({ query }: { query: string }) {
  return <p>{useMediaQuery(query) ? 'matches' : 'no match'}</p>
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useMediaQuery', () => {
  it('reports the browser answer, and follows it when it changes', () => {
    const media = stubMediaQuery(true)
    render(<Probe query="(max-width: 1100px)" />)
    expect(screen.getByText('matches')).toBeInTheDocument()
    act(() => media.set(false))
    expect(screen.getByText('no match')).toBeInTheDocument()
    expect(media.queries()).toContain('(max-width: 1100px)')
  })

  it('stops listening when the component goes away', () => {
    const media = stubMediaQuery(false)
    const { unmount } = render(<Probe query="(max-width: 1100px)" />)
    expect(media.listeners()).toBe(1)
    unmount()
    expect(media.listeners()).toBe(0)
  })

  it('keeps one listener across re-renders, and moves it when the query changes', () => {
    const media = stubMediaQuery(false)
    const { rerender } = render(<Probe query="(max-width: 1279px)" />)
    media.set(false)
    rerender(<Probe query="(max-width: 1279px)" />)
    rerender(<Probe query="(max-width: 1279px)" />)
    expect(media.subscribed()).toBe(1)
    rerender(<Probe query="(max-width: 700px)" />)
    expect(media.subscribed()).toBe(2)
    expect(media.listeners()).toBe(1)
  })

  it('asks the browser for one MediaQueryList per query, not one per render', () => {
    const media = stubMediaQuery(true)
    const { rerender } = render(<Probe query="(max-width: 1279px)" />)
    rerender(<Probe query="(max-width: 1279px)" />)
    rerender(<Probe query="(max-width: 1279px)" />)
    act(() => media.set(false))
    expect(media.queries()).toEqual(['(max-width: 1279px)'])
    rerender(<Probe query="(max-width: 700px)" />)
    expect(media.queries()).toEqual(['(max-width: 1279px)', '(max-width: 700px)'])
  })

  it('says no match where there is no matchMedia (jsdom, the server)', () => {
    vi.stubGlobal('matchMedia', undefined)
    render(<Probe query="(max-width: 1100px)" />)
    expect(screen.getByText('no match')).toBeInTheDocument()
  })
})
