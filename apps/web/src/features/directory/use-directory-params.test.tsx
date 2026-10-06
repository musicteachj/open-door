import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, useLocation, useNavigate, useNavigationType } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useDirectoryParams } from './use-directory-params'

function setup(at = '/directory') {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[at]}>{children}</MemoryRouter>
  )
  return renderHook(
    () => ({
      dir: useDirectoryParams(),
      location: useLocation(),
      type: useNavigationType(),
      navigate: useNavigate(),
    }),
    { wrapper },
  )
}

const search = (r: ReturnType<typeof setup>) =>
  new URLSearchParams(r.result.current.location.search)

beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('reading the URL', () => {
  it('reads q, location, department, and team=mine', () => {
    const r = setup(
      '/directory?q=ja&location=00000000-0000-4000-9000-000000000011&department=00000000-0000-4000-a000-000000000012&team=mine',
    )
    expect(r.result.current.dir).toMatchObject({
      q: 'ja',
      searchText: 'ja',
      location: '00000000-0000-4000-9000-000000000011',
      department: '00000000-0000-4000-a000-000000000012',
      myTeam: true,
    })
  })

  it('reads an empty URL as nothing set', () => {
    const r = setup()
    expect(r.result.current.dir).toMatchObject({
      q: '',
      location: null,
      department: null,
      myTeam: false,
      hasFilters: false,
    })
  })

  it('maps the URL names to the API names, leaving out what is unset', () => {
    const r = setup(
      '/directory?q=ja&location=00000000-0000-4000-9000-000000000011&department=00000000-0000-4000-a000-000000000012&team=mine',
    )
    expect(r.result.current.dir.apiParams).toEqual({
      q: 'ja',
      locationId: '00000000-0000-4000-9000-000000000011',
      departmentId: '00000000-0000-4000-a000-000000000012',
      team: 'mine',
    })
    expect(setup().result.current.dir.apiParams).toEqual({})
    expect(
      setup('/directory?department=00000000-0000-4000-a000-000000000012').result.current.dir
        .apiParams,
    ).toEqual({
      departmentId: '00000000-0000-4000-a000-000000000012',
    })
  })

  it('treats empty values, a blank search, and any team other than "mine" as unset', () => {
    const r = setup('/directory?q=%20%20&location=&department=&team=all')
    expect(r.result.current.dir.apiParams).toEqual({})
    expect(r.result.current.dir.myTeam).toBe(false)
    expect(r.result.current.dir.hasFilters).toBe(false)
  })

  it('treats a location or department that is not a UUID as no filter, as the API would refuse it', () => {
    const r = setup('/directory?location=abc&department=not-a-uuid&team=mine')
    expect(r.result.current.dir).toMatchObject({
      location: null,
      department: null,
      hasFilters: true,
    })
    expect(r.result.current.dir.apiParams).toEqual({ team: 'mine' })
    expect(setup('/directory?location=abc').result.current.dir.hasFilters).toBe(false)
  })

  it('strips a NUL from the search, which the API refuses', () => {
    expect(setup('/directory?q=%00').result.current.dir.apiParams).toEqual({})
    const r = setup('/directory?q=a%00b')
    expect(r.result.current.dir.q).toBe('ab')
    expect(r.result.current.dir.apiParams).toEqual({ q: 'ab' })
  })

  it('sends a search of at most 100 characters, the API limit', () => {
    const r = setup(`/directory?q=${'a'.repeat(120)}`)
    expect(r.result.current.dir.apiParams.q).toBe('a'.repeat(100))
  })
})

describe('writing filters', () => {
  it('writes each filter under its URL name, and pushes a history entry', () => {
    const r = setup()
    act(() => r.result.current.dir.setLocation('00000000-0000-4000-9000-000000000011'))
    expect(search(r).get('location')).toBe('00000000-0000-4000-9000-000000000011')
    expect(r.result.current.type).toBe('PUSH')
    act(() => r.result.current.dir.setDepartment('00000000-0000-4000-a000-000000000012'))
    act(() => r.result.current.dir.setMyTeam(true))
    expect(r.result.current.location.search).toBe(
      '?location=00000000-0000-4000-9000-000000000011&department=00000000-0000-4000-a000-000000000012&team=mine',
    )
  })

  it('removes a filter from the URL when it is unset, never writing "null" or an empty value', () => {
    const r = setup(
      '/directory?location=00000000-0000-4000-9000-000000000011&department=00000000-0000-4000-a000-000000000012&team=mine',
    )
    act(() => r.result.current.dir.setLocation(null))
    act(() => r.result.current.dir.setDepartment(null))
    act(() => r.result.current.dir.setMyTeam(false))
    expect(r.result.current.location.search).toBe('')
    expect(r.result.current.dir.apiParams).toEqual({})
  })

  it('"Clear filters" resets every filter and keeps the search', () => {
    const r = setup(
      '/directory?q=ja&location=00000000-0000-4000-9000-000000000011&department=00000000-0000-4000-a000-000000000012&team=mine',
    )
    act(() => r.result.current.dir.clearFilters())
    expect(r.result.current.location.search).toBe('?q=ja')
    expect(r.result.current.dir.hasFilters).toBe(false)
  })

  it('"Clear filters" keeps a search that is still waiting to be written', () => {
    const r = setup('/directory?location=00000000-0000-4000-9000-000000000011')
    act(() => r.result.current.dir.setSearchText('ja'))
    act(() => r.result.current.dir.clearFilters())
    act(() => void vi.advanceTimersByTime(250))
    expect(r.result.current.location.search).toBe('?q=ja')
  })
})

describe('search', () => {
  it('shows the typed text at once but writes the URL only after a 250 ms pause', () => {
    const r = setup()
    act(() => r.result.current.dir.setSearchText('j'))
    expect(r.result.current.dir.searchText).toBe('j')
    act(() => void vi.advanceTimersByTime(200))
    act(() => r.result.current.dir.setSearchText('ja'))
    act(() => void vi.advanceTimersByTime(200))
    // 400 ms in, but only 200 since the last key: nothing written yet.
    expect(search(r).has('q')).toBe(false)
    act(() => void vi.advanceTimersByTime(50))
    expect(search(r).get('q')).toBe('ja')
  })

  it('writes once for a burst of keys', () => {
    const r = setup()
    const writes: string[] = []
    for (const text of ['j', 'ja', 'jan', 'jane']) {
      act(() => r.result.current.dir.setSearchText(text))
      act(() => void vi.advanceTimersByTime(100))
      writes.push(r.result.current.location.search)
    }
    expect(writes).toEqual(['', '', '', ''])
    act(() => void vi.advanceTimersByTime(250))
    expect(r.result.current.location.search).toBe('?q=jane')
  })

  it('replaces the history entry rather than adding one', () => {
    const r = setup()
    act(() => r.result.current.dir.setSearchText('ja'))
    act(() => void vi.advanceTimersByTime(250))
    expect(r.result.current.type).toBe('REPLACE')
    // One entry only: going back stays where it is.
    act(() => void r.result.current.navigate(-1))
    expect(r.result.current.location.pathname).toBe('/directory')
  })

  it('keeps the filters when it writes, and removes q when the text is blank', () => {
    const r = setup('/directory?location=00000000-0000-4000-9000-000000000011&q=ja')
    act(() => r.result.current.dir.setSearchText('   '))
    act(() => void vi.advanceTimersByTime(250))
    expect(r.result.current.location.search).toBe('?location=00000000-0000-4000-9000-000000000011')
  })

  it('"Clear search" resets q and the text at once, and keeps the filters', () => {
    const r = setup('/directory?q=ja&location=00000000-0000-4000-9000-000000000011')
    act(() => r.result.current.dir.clearSearch())
    expect(r.result.current.location.search).toBe('?location=00000000-0000-4000-9000-000000000011')
    expect(r.result.current.dir.searchText).toBe('')
    expect(r.result.current.type).toBe('REPLACE')
  })

  it('"Clear search" cancels a write still waiting, so the old text does not come back', () => {
    const r = setup()
    act(() => r.result.current.dir.setSearchText('ja'))
    act(() => r.result.current.dir.clearSearch())
    act(() => void vi.advanceTimersByTime(500))
    expect(search(r).has('q')).toBe(false)
  })

  it('drops a write still waiting when Back changes the search, and shows the earlier search', () => {
    const r = setup('/directory?q=zed')
    act(() => void r.result.current.navigate('/directory'))
    act(() => r.result.current.dir.setSearchText('ja'))
    act(() => void vi.advanceTimersByTime(100))
    act(() => void r.result.current.navigate(-1))
    act(() => void vi.advanceTimersByTime(300))
    expect(r.result.current.location.search).toBe('?q=zed')
    expect(r.result.current.dir.searchText).toBe('zed')
  })

  it('drops a write still waiting when a link to /directory clears the search', () => {
    const r = setup('/directory?q=ja')
    act(() => r.result.current.dir.setSearchText('jan'))
    act(() => void vi.advanceTimersByTime(100))
    act(() => void r.result.current.navigate('/directory'))
    act(() => void vi.advanceTimersByTime(300))
    expect(r.result.current.location.search).toBe('')
    expect(r.result.current.dir.searchText).toBe('')
  })

  it('drops a write still waiting on Back to an entry with the same search, and replaces nothing', () => {
    const lid = '00000000-0000-4000-9000-000000000011'
    const r = setup('/directory?q=zed')
    act(() => void r.result.current.navigate(`/directory?q=zed&location=${lid}`))
    act(() => r.result.current.dir.setSearchText('ja'))
    act(() => void vi.advanceTimersByTime(100))
    act(() => void r.result.current.navigate(-1))
    act(() => void vi.advanceTimersByTime(300))
    expect(r.result.current.type).toBe('POP') // nothing replaced the entry we went back to
    expect(r.result.current.location.search).toBe('?q=zed')
    expect(r.result.current.dir.searchText).toBe('zed')
    // The entry we left is still there, as it was.
    act(() => void r.result.current.navigate(1))
    expect(r.result.current.location.search).toBe(`?q=zed&location=${lid}`)
    act(() => void r.result.current.navigate(-1))
    expect(r.result.current.location.search).toBe('?q=zed')
  })

  it('still writes the typed text when the only URL change was its own earlier write', () => {
    const r = setup()
    act(() => r.result.current.dir.setSearchText('ja'))
    act(() => void vi.advanceTimersByTime(250))
    act(() => r.result.current.dir.setSearchText('jan'))
    act(() => void vi.advanceTimersByTime(250))
    expect(r.result.current.location.search).toBe('?q=jan')
  })

  it('follows the URL when it changes some other way, such as Back', () => {
    const r = setup('/directory?q=ja')
    act(() => void r.result.current.navigate('/directory?q=zed'))
    expect(r.result.current.dir.q).toBe('zed')
    expect(r.result.current.dir.searchText).toBe('zed')
  })
})
