import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ConsoleTurnsPageOut } from '@/api/generated'
import { useMoreTurns } from './use-more-turns'

describe('useMoreTurns', () => {
  it('hands back the same array on every render while no later page is held', () => {
    const first: ConsoleTurnsPageOut = { items: [], nextCursor: 'next' }
    const { result, rerender } = renderHook(() => useMoreTurns(first))
    const items = result.current.items
    rerender()
    expect(result.current.items).toBe(items)
  })
})
