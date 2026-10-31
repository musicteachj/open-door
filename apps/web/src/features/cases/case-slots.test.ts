import { beforeEach, describe, expect, it } from 'vitest'
import type { CaseSentOut } from '@/api/generated'
import { useCaseSlots } from './case-slots'

const SENT = {
  sentLine: { lead: 'Sent.', pointer: '' },
  crisisText: null,
} as unknown as CaseSentOut

beforeEach(() => useCaseSlots.getState().reset())

describe('markShown', () => {
  it('flips only the flag and keeps the rest of the slot', () => {
    useCaseSlots.getState().set('t', { phase: 'sent', sent: SENT })
    useCaseSlots.getState().markShown('t', 'sent')
    expect(useCaseSlots.getState().slots.t).toEqual({ phase: 'sent', sent: SENT, shown: true })
  })

  it('does not overwrite a slot that moved to another phase meanwhile', () => {
    useCaseSlots.getState().set('t', { phase: 'open' })
    // The slot changed between the render that saw `open` and its effect.
    useCaseSlots.getState().set('t', { phase: 'limit', readAt: 5 })
    useCaseSlots.getState().markShown('t', 'open')
    expect(useCaseSlots.getState().slots.t).toEqual({ phase: 'limit', readAt: 5 })
  })

  it('does nothing for a cleared slot', () => {
    useCaseSlots.getState().markShown('t', 'open')
    expect(useCaseSlots.getState().slots.t).toBeUndefined()
  })
})
