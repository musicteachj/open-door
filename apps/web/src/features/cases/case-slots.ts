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
export type CaseSlot = (
  | { phase: 'open' }
  | { phase: 'sent'; sent: CaseSentOut }
  /** `readAt`: when the case list was last read as the refusal came (`dataUpdatedAt`). */
  | { phase: 'limit'; readAt: number }
) & {
  /**
   * What the slot shows has already acted once on arrival (taken focus, announced the crisis
   * text). The slot outlives the page, so a later mount, after the person went elsewhere and came
   * back, shows the same thing quietly.
   */
  shown?: boolean
}

type CaseSlotsState = {
  slots: Record<string, CaseSlot>
  set: (turnId: string, slot: CaseSlot) => void
  /** Flips only `shown`, and only if the slot is still in `phase`: a newer slot is left alone. */
  markShown: (turnId: string, phase: CaseSlot['phase']) => void
  clear: (turnId: string) => void
  reset: () => void
}

export const useCaseSlots = create<CaseSlotsState>((set) => ({
  slots: {},
  set: (turnId, slot) => set((state) => ({ slots: { ...state.slots, [turnId]: slot } })),
  markShown: (turnId, phase) =>
    set((state) => {
      const slot = state.slots[turnId]
      if (slot === undefined || slot.phase !== phase) return state
      return { slots: { ...state.slots, [turnId]: { ...slot, shown: true } } }
    }),
  clear: (turnId) =>
    set((state) => {
      const { [turnId]: _gone, ...rest } = state.slots
      return { slots: rest }
    }),
  reset: () => set({ slots: {} }),
}))

// A persona switch or a sign-out forgets every offer: the next person starts with none.
registerReset(() => useCaseSlots.getState().reset())
