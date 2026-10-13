import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, useLocation, useNavigate, useNavigationType } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MAX_SEARCH_LENGTH, useClearPassage, useHandbookParams } from './url-state'

function setup(at = '/handbook') {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[at]}>{children}</MemoryRouter>
  )
  return renderHook(
    () => ({
      params: useHandbookParams(),
      clearPassage: useClearPassage(),
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
  it('reads q and show=mine', () => {
    const r = setup('/handbook?q=sick&show=mine')
    expect(r.result.current.params).toMatchObject({ q: 'sick', searchText: 'sick', show: 'mine' })
  })

  it('reads an empty URL as no search and every section', () => {
    expect(setup().result.current.params).toMatchObject({ q: '', searchText: '', show: 'all' })
  })

  it('takes any other show value as all', () => {
    expect(setup('/handbook?show=everyone').result.current.params.show).toBe('all')
  })

  it('trims q and drops a NUL, which the API refuses', () => {
    expect(setup('/handbook?q=%20sick%00%20').result.current.params.q).toBe('sick')
  })

  it('shows the text capped at 100 characters, as the query is', () => {
    const r = setup(`/handbook?q=${'a'.repeat(120)}`)
    expect(r.result.current.params.searchText).toBe('a'.repeat(100))
  })

  it('keeps the search to the 100 characters the API takes', () => {
    const r = setup(`/handbook?q=${'a'.repeat(120)}`)
    expect(MAX_SEARCH_LENGTH).toBe(100)
    expect(r.result.current.params.queryText).toBe('a'.repeat(100))
  })
})

describe('searching', () => {
  it('shows typed text at once and writes it to the URL after 250 ms, replacing the entry', () => {
    const r = setup()
    act(() => r.result.current.params.setSearchText('sick'))
    expect(r.result.current.params.searchText).toBe('sick')
    expect(search(r).get('q')).toBeNull()
    act(() => void vi.advanceTimersByTime(249))
    expect(search(r).get('q')).toBeNull()
    act(() => void vi.advanceTimersByTime(1))
    expect(search(r).get('q')).toBe('sick')
    expect(r.result.current.type).toBe('REPLACE')
  })

  it('writes only the last text after a burst of typing', () => {
    const r = setup()
    act(() => r.result.current.params.setSearchText('s'))
    act(() => void vi.advanceTimersByTime(200))
    act(() => r.result.current.params.setSearchText('si'))
    act(() => void vi.advanceTimersByTime(200))
    expect(search(r).get('q')).toBeNull()
    act(() => void vi.advanceTimersByTime(50))
    expect(search(r).get('q')).toBe('si')
  })

  it('removes q from the URL when the text is emptied', () => {
    const r = setup('/handbook?q=sick')
    act(() => r.result.current.params.setSearchText(''))
    act(() => void vi.advanceTimersByTime(250))
    expect(search(r).has('q')).toBe(false)
  })

  it('clears the search at once, replacing the entry, and keeps show', () => {
    const r = setup('/handbook?q=sick&show=mine')
    act(() => r.result.current.params.clearSearch())
    expect(r.result.current.params.searchText).toBe('')
    expect(search(r).has('q')).toBe(false)
    expect(search(r).get('show')).toBe('mine')
    expect(r.result.current.type).toBe('REPLACE')
  })

  it('follows the URL when it changes some other way', () => {
    const r = setup('/handbook?q=sick')
    act(() => void r.result.current.navigate('/handbook?q=overtime'))
    expect(r.result.current.params.searchText).toBe('overtime')
  })

  it('drops a write still waiting when the URL changes some other way', () => {
    const r = setup()
    act(() => r.result.current.params.setSearchText('sick'))
    act(() => void r.result.current.navigate('/handbook?show=mine'))
    act(() => void vi.advanceTimersByTime(300))
    expect(search(r).has('q')).toBe(false)
    expect(r.result.current.params.searchText).toBe('')
  })
})

describe('flushing a pending search', () => {
  it('writes the waiting text at once, replacing the entry, and nothing again later', () => {
    const r = setup()
    act(() => r.result.current.params.setSearchText('sick'))
    act(() => r.result.current.params.flushSearch())
    expect(search(r).get('q')).toBe('sick')
    expect(r.result.current.type).toBe('REPLACE')
    act(() => r.result.current.navigate('/handbook?q=other', { replace: true }))
    act(() => void vi.advanceTimersByTime(300))
    expect(search(r).get('q')).toBe('other')
  })

  it('does nothing when no write is waiting', () => {
    const r = setup('/handbook?q=sick')
    act(() => r.result.current.params.flushSearch())
    expect(r.result.current.type).toBe('POP')
  })
})

describe('the Show menu', () => {
  it('writes show=mine as a new history entry, and removes it for all', () => {
    const r = setup('/handbook?q=sick')
    act(() => r.result.current.params.setShow('mine'))
    expect(search(r).get('show')).toBe('mine')
    expect(search(r).get('q')).toBe('sick')
    expect(r.result.current.type).toBe('PUSH')
    act(() => r.result.current.params.setShow('all'))
    expect(search(r).has('show')).toBe(false)
  })

  it('keeps a pending search when the filter changes', () => {
    const r = setup()
    act(() => r.result.current.params.setSearchText('sick'))
    act(() => r.result.current.params.setShow('mine'))
    act(() => void vi.advanceTimersByTime(250))
    expect(search(r).get('q')).toBe('sick')
    expect(search(r).get('show')).toBe('mine')
  })

  it('writes a pending search before the filter, so Back undoes only the filter', () => {
    const r = setup()
    act(() => r.result.current.params.setSearchText('sick'))
    act(() => r.result.current.params.setShow('mine'))
    expect(search(r).get('q')).toBe('sick')
    expect(search(r).get('show')).toBe('mine')
    act(() => void r.result.current.navigate(-1))
    expect(search(r).get('q')).toBe('sick')
    expect(search(r).has('show')).toBe(false)
  })
})

describe('clearing the highlight', () => {
  it('removes passage, replaces the entry, and keeps the rest', () => {
    const r = setup('/handbook/CA-4.3?passage=p2&x=1')
    act(() => r.result.current.clearPassage())
    expect(search(r).has('passage')).toBe(false)
    expect(search(r).get('x')).toBe('1')
    expect(r.result.current.location.pathname).toBe('/handbook/CA-4.3')
    expect(r.result.current.type).toBe('REPLACE')
  })
})
