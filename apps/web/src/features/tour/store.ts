import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { registerReset } from '@/lib/identity'
import { TOUR } from './script'

// Counts the times the tour's position was set anew (a step change, a begin, an end, a reset).
// A send that resolves later reports against the visit it was pressed in, so a late answer never
// touches a step the visitor has since moved to, even the same step entered again.
let visits = 0

export type Outcome = 'result' | 'missing'

type TourState = {
  /** A tour was begun and not ended: leaving keeps it, so the menu can offer Resume. */
  started: boolean
  /** The coach mark shows. False after Leave (the step is kept) and before a tour begins. */
  active: boolean
  /** Index into `TOUR`. */
  step: number
  /** Indexes of the current step's chips already sent. */
  sent: readonly number[]
  /**
   * The ID of the turn the server made for the step's last chip, once it is known. The step's
   * result is this turn's own, never one from earlier in the conversation. Kept with `sent`, so a
   * reload keeps it. Null until the server has taken the chip's question.
   */
  turnId: string | null
  /**
   * The step's last chip was sent but the send ended with no turn to follow (the server may hold
   * the question, and it is never asked twice): the step finishes without a result.
   */
  lost: boolean
  /**
   * The step's last chip's request was issued (set right before it goes out). A reload finds a
   * chip marked sent with no turn: if the request was issued, the server may hold the question
   * (lost); if not, the send never left the browser and the chip is pressable again.
   */
  issued: boolean
  /**
   * How the step's result turned out, latched once so leaving the page or starting a new
   * conversation never changes it: `result` (the chip's turn finished, or its card or panel was
   * seen) or `missing` (the turn finished without the expected card or panel). `missing` upgrades
   * to `result` if the card or panel shows up later (a re-ask). Null until decided.
   */
  outcome: Outcome | null
  /** Which visit to a position this is; not kept. See `visits`. */
  visit: number
  /**
   * The step was just entered: the runner must still make the visitor the step's persona and take
   * them to its page before the coach mark shows.
   */
  entering: boolean
  /**
   * The runner already asked for this step's persona once since the step was entered. A switch
   * remounts the runner, so this lives here and not in a ref: it is what stops a switch that fails,
   * or lands on someone else, from being asked for again and again. Not kept across a reload.
   */
  switchTried: boolean
  /** "Start the tour?" is open. Not kept across a reload. */
  startDialogOpen: boolean
  begin: () => void
  goTo: (step: number) => void
  /** A chip was pressed. */
  markSent: (chip: number) => void
  /**
   * A chip's send was turned away before the server took the question, so the chip may be pressed
   * again. Ignored when the tour has moved on since `visit` (the value of `visit` at the press).
   */
  unmarkSent: (visit: number, chip: number) => void
  /** The server took the step's last chip and made this turn. Ignored for another visit. */
  setTurnId: (visit: number, turnId: string) => void
  /** The step's last chip was sent and no turn can be followed. Ignored for another visit. */
  sendLost: (visit: number) => void
  /** The step's last chip's request is about to go out. Ignored for another visit. */
  markIssued: (visit: number) => void
  /** Latch the step's outcome. Set once; only `missing` can be upgraded to `result`. */
  settle: (visit: number, outcome: Outcome) => void
  /** Leave: hide the coach mark, keep the step. */
  leave: () => void
  /** Resume the step the visitor left on. */
  resume: () => void
  /** End the tour for good ("Keep exploring", "Choose who to be"). */
  end: () => void
  /** The runner is about to ask for the step's persona. */
  switchAttempted: () => void
  /** The runner has made the visitor the step's persona and taken them to its page. */
  arrived: () => void
  setStartDialogOpen: (open: boolean) => void
}

const IDLE = {
  started: false,
  active: false,
  step: 0,
  sent: [] as readonly number[],
  turnId: null as string | null,
  lost: false,
  issued: false,
  outcome: null as Outcome | null,
  entering: false,
  switchTried: false,
}

/**
 * The guided tour's state: whether it is on, the step, and which chips were sent. Kept in session
 * storage, so a reload resumes the step. Nothing about the tour is stored on the server.
 *
 * It is cleared by an identity reset (sign out, a new sandbox, the session ending), like the
 * shell's toast, with one exception: a persona switch's own reset (reason `switch`) keeps it, since
 * the tour switches persona itself and Resume brings a visitor who switched away back to their
 * step.
 */
export const useTourStore = create<TourState>()(
  persist(
    (set) => ({
      ...IDLE,
      startDialogOpen: false,
      visit: 0,
      // Entering, so step 1 goes through the same persona-and-page check as every other step.
      begin: () => set({ ...IDLE, started: true, active: true, entering: true, visit: ++visits }),
      goTo: (step) =>
        set({
          step: Math.max(0, Math.min(step, TOUR.length - 1)),
          sent: [],
          turnId: null,
          lost: false,
          issued: false,
          outcome: null,
          entering: true,
          switchTried: false,
          visit: ++visits,
        }),
      markSent: (chip) =>
        set((s) => ({ sent: s.sent.includes(chip) ? s.sent : [...s.sent, chip] })),
      // Giving the last chip back also forgets that its request went out, so a press again starts
      // clean.
      unmarkSent: (visit, chip) =>
        set((s) =>
          s.visit === visit
            ? {
                sent: s.sent.filter((c) => c !== chip),
                issued: chip === (TOUR[s.step]!.chips?.length ?? 0) - 1 ? false : s.issued,
              }
            : {},
        ),
      setTurnId: (visit, turnId) => set((s) => (s.visit === visit ? { turnId } : {})),
      sendLost: (visit) =>
        set((s) => (s.visit === visit && s.turnId === null ? { lost: true } : {})),
      markIssued: (visit) => set((s) => (s.visit === visit ? { issued: true } : {})),
      settle: (visit, outcome) =>
        set((s) =>
          s.visit === visit &&
          (s.outcome === null || (s.outcome === 'missing' && outcome === 'result'))
            ? { outcome }
            : {},
        ),
      leave: () => set({ active: false, entering: false }),
      resume: () => set({ active: true, entering: true, switchTried: false }),
      end: () => set({ ...IDLE, visit: ++visits }),
      arrived: () => set({ entering: false }),
      switchAttempted: () => set({ switchTried: true }),
      setStartDialogOpen: (startDialogOpen) => set({ startDialogOpen }),
    }),
    {
      name: 'od.tour',
      // A build with more steps, or an edited value, must not crash the shell: it loads as idle.
      version: 3,
      merge: (persisted, current) => {
        const kept = validStored(persisted)
        return kept === null ? { ...current, ...IDLE } : { ...current, ...kept }
      },
      storage: createJSONStorage(() => sessionStorage),
      partialize: ({ started, active, step, sent, turnId, lost, issued, outcome, entering }) => ({
        started,
        active,
        step,
        sent,
        turnId,
        lost,
        issued,
        outcome,
        entering,
      }),
    },
  ),
)

/** The kept state, if it is the shape this build writes and its step exists; otherwise null. */
function validStored(raw: unknown): Partial<TourState> | null {
  if (typeof raw !== 'object' || raw === null) return null
  const r = raw as Record<string, unknown>
  const isIndexList = (v: unknown) =>
    Array.isArray(v) && v.every((n) => Number.isInteger(n) && n >= 0)
  if (
    typeof r.started !== 'boolean' ||
    typeof r.active !== 'boolean' ||
    typeof r.entering !== 'boolean' ||
    !Number.isInteger(r.step) ||
    (r.step as number) < 0 ||
    (r.step as number) >= TOUR.length ||
    !isIndexList(r.sent) ||
    (r.turnId !== null && typeof r.turnId !== 'string') ||
    typeof r.lost !== 'boolean' ||
    (r.issued !== undefined && typeof r.issued !== 'boolean') ||
    (r.outcome !== null && r.outcome !== 'result' && r.outcome !== 'missing')
  ) {
    return null
  }
  // A reload while the last chip's send was in flight: nothing can report on that send any more
  // (the page that made it is gone). If its request was issued the server may hold the question,
  // so it is never asked again and the step finishes without a result instead of waiting for ever.
  // If it was not issued (still waiting for the conversation), nothing left the browser, so the
  // chip is un-marked and can be pressed again. A value from before `issued` counts as issued.
  const lastChip = (TOUR[r.step as number]!.chips?.length ?? 0) - 1
  const pending = lastChip >= 0 && (r.sent as number[]).includes(lastChip) && r.turnId === null
  const issued = r.issued !== false
  const inFlightLost = pending && issued
  const sent =
    pending && !issued ? (r.sent as number[]).filter((c) => c !== lastChip) : (r.sent as number[])
  // Only the fields this build writes: an extra stored key must not replace a store action.
  return {
    started: r.started,
    active: r.active,
    step: r.step as number,
    sent,
    turnId: r.turnId as string | null,
    lost: r.lost || inFlightLost,
    issued,
    outcome: r.outcome as Outcome | null,
    entering: r.entering,
  }
}

registerReset((reason) => {
  // A persona switch's own reset spares the tour (the switch passes the reason itself). Any other
  // reset, such as a sign out or the session ending while a switch is pending, clears it.
  if (reason === 'switch') return
  useTourStore.setState({ ...IDLE, startDialogOpen: false, visit: ++visits })
})
