import { create } from 'zustand'
import type { CaseSentOut } from '@/api/generated'
import { registerReset } from '@/lib/identity'

/**
 * Where a turn's case offer is: the form open, the case sent (with what the server answered, so
 * a crisis screening's text can show right after), or the waiting limit reached. Keyed by turn ID,
 * because the live turn and its saved copy are different components for the same turn, and the
 * form must survive that swap. Only the shape of the offer is kept here: the words a person types
 * stay in the form's own state, and nothing here is server data (no case text, never the cache).
 */
export type CaseSlot = { phase: 'open' } | { phase: 'sent'; sent: CaseSentOut } | { phase: 'limit' }

type CaseSlotsState = {
  slots: Record<string, CaseSlot>
  set: (turnId: string, slot: CaseSlot) => void
  clear: (turnId: string) => void
  reset: () => void
}

export const useCaseSlots = create<CaseSlotsState>((set) => ({
  slots: {},
  set: (turnId, slot) => set((state) => ({ slots: { ...state.slots, [turnId]: slot } })),
  clear: (turnId) =>
    set((state) => {
      const { [turnId]: _gone, ...rest } = state.slots
      return { slots: rest }
    }),
  reset: () => set({ slots: {} }),
}))

// A persona switch or a sign-out forgets every offer: the next person starts with none.
registerReset(() => useCaseSlots.getState().reset())
