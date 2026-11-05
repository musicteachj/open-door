import { QueryClient } from '@tanstack/react-query'
import { beforeEach, describe, expect, it } from 'vitest'
import { resetIdentity } from '@/lib/identity'
import { useTourStore } from './store'

const stored = () => JSON.parse(sessionStorage.getItem('od.tour') ?? 'null')?.state

beforeEach(() => {
  useTourStore.getState().end()
})

describe('the tour store', () => {
  it('begins on step 1 with nothing sent, active', () => {
    useTourStore.getState().begin()
    expect(useTourStore.getState()).toMatchObject({
      started: true,
      active: true,
      step: 0,
      sent: [],
      entering: true,
    })
  })

  it('goes to a step with its chips unsent, and marks the step as being entered', () => {
    const tour = useTourStore.getState()
    tour.begin()
    tour.markSent(0)
    tour.goTo(2)
    expect(useTourStore.getState()).toMatchObject({ step: 2, sent: [], entering: true })
    tour.goTo(99)
    expect(useTourStore.getState().step).toBe(9)
    tour.goTo(-3)
    expect(useTourStore.getState().step).toBe(0)
  })

  it('remembers each chip sent once', () => {
    const tour = useTourStore.getState()
    tour.begin()
    tour.markSent(1)
    tour.markSent(1)
    tour.markSent(0)
    expect(useTourStore.getState().sent).toEqual([1, 0])
  })

  it('keeps the step when the visitor leaves, and resumes it', () => {
    const tour = useTourStore.getState()
    tour.begin()
    tour.goTo(4)
    tour.markSent(0)
    tour.leave()
    expect(useTourStore.getState()).toMatchObject({
      started: true,
      active: false,
      step: 4,
      sent: [0],
    })
    tour.resume()
    expect(useTourStore.getState()).toMatchObject({ active: true, step: 4, entering: true })
  })

  it('ends for good, so the menu offers a new tour', () => {
    const tour = useTourStore.getState()
    tour.begin()
    tour.goTo(6)
    tour.end()
    expect(useTourStore.getState()).toMatchObject({ started: false, active: false, step: 0 })
  })

  it('is kept in session storage, without the dialog', () => {
    const tour = useTourStore.getState()
    tour.begin()
    tour.goTo(3)
    tour.setStartDialogOpen(true)
    expect(stored()).toEqual({
      started: true,
      active: true,
      step: 3,
      sent: [],
      turnId: null,
      lost: false,
      issued: false,
      outcome: null,
      entering: true,
    })
  })

  it('keeps the last chip’s turn ID with sent, and drops both when the step changes', () => {
    const tour = useTourStore.getState()
    tour.begin()
    const { visit } = useTourStore.getState()
    tour.markSent(0)
    tour.markSent(1)
    expect(useTourStore.getState().turnId).toBeNull()
    tour.setTurnId(visit, 'turn-a')
    expect(stored()).toMatchObject({ sent: [0, 1], turnId: 'turn-a', lost: false })
    tour.goTo(1)
    expect(useTourStore.getState()).toMatchObject({ sent: [], turnId: null, lost: false })
  })

  it('ignores a report from a visit the tour has left, even for the same step', () => {
    const tour = useTourStore.getState()
    tour.begin()
    tour.goTo(2)
    const { visit } = useTourStore.getState()
    tour.markSent(0)
    tour.goTo(3)
    tour.markSent(0)
    // The first press's send reports back now: it must not touch the new step's chip.
    tour.unmarkSent(visit, 0)
    tour.setTurnId(visit, 'late')
    tour.sendLost(visit)
    expect(useTourStore.getState()).toMatchObject({ sent: [0], turnId: null, lost: false })
    // Entering the same step again is another visit too.
    tour.goTo(2)
    tour.goTo(3)
    tour.markSent(0)
    tour.unmarkSent(visit, 0)
    expect(useTourStore.getState().sent).toEqual([0])
  })

  it('forgets that the last chip was issued when its send is given back', () => {
    // A send the API refused after it went out: a press again that a reload interrupts before its
    // own request must not read as lost.
    const tour = useTourStore.getState()
    tour.begin()
    tour.goTo(2)
    const { visit } = useTourStore.getState()
    tour.markSent(0)
    tour.markIssued(visit)
    tour.unmarkSent(visit, 0)
    expect(useTourStore.getState()).toMatchObject({ sent: [], issued: false })
  })

  it('gives a chip back for the visit it was pressed in, and loses a send only while it has no turn', () => {
    const tour = useTourStore.getState()
    tour.begin()
    const { visit } = useTourStore.getState()
    tour.markSent(0)
    tour.unmarkSent(visit, 0)
    expect(useTourStore.getState().sent).toEqual([])
    tour.markSent(1)
    tour.setTurnId(visit, 'turn-a')
    tour.sendLost(visit)
    expect(useTourStore.getState().lost).toBe(false)
  })

  it('comes back from session storage after a reload', async () => {
    sessionStorage.setItem(
      'od.tour',
      JSON.stringify({
        state: {
          started: true,
          active: true,
          step: 4,
          sent: [0],
          turnId: 't-1',
          lost: false,
          outcome: 'missing',
          entering: false,
        },
        version: 3,
      }),
    )
    await useTourStore.persist.rehydrate()
    expect(useTourStore.getState()).toMatchObject({
      active: true,
      step: 4,
      sent: [0],
      turnId: 't-1',
      outcome: 'missing',
    })
  })

  it('marks the last chip’s send lost when a reload found it still in flight', async () => {
    const save = (step: number, sent: number[], turnId: string | null) =>
      sessionStorage.setItem(
        'od.tour',
        JSON.stringify({
          state: {
            started: true,
            active: true,
            step,
            sent,
            turnId,
            lost: false,
            outcome: null,
            entering: false,
          },
          version: 3,
        }),
      )
    // Step 3 has two chips: the first alone is not the last chip's send.
    save(3, [0], null)
    await useTourStore.persist.rehydrate()
    expect(useTourStore.getState().lost).toBe(false)
    save(3, [0, 1], null)
    await useTourStore.persist.rehydrate()
    expect(useTourStore.getState().lost).toBe(true)
    save(3, [0, 1], 't-1')
    await useTourStore.persist.rehydrate()
    expect(useTourStore.getState().lost).toBe(false)
  })

  it('gives the last chip back when a reload found its request was never issued', async () => {
    const save = (issued: boolean) =>
      sessionStorage.setItem(
        'od.tour',
        JSON.stringify({
          state: {
            started: true,
            active: true,
            step: 3,
            sent: [0, 1],
            turnId: null,
            lost: false,
            issued,
            outcome: null,
            entering: false,
          },
          version: 3,
        }),
      )
    save(false)
    await useTourStore.persist.rehydrate()
    expect(useTourStore.getState()).toMatchObject({ sent: [0], lost: false, issued: false })
    save(true)
    await useTourStore.persist.rehydrate()
    expect(useTourStore.getState()).toMatchObject({ sent: [0, 1], lost: true })
  })

  it('records that the last chip’s request was issued, for its own visit only', () => {
    useTourStore.getState().begin()
    const { visit } = useTourStore.getState()
    useTourStore.getState().markIssued(visit + 1)
    expect(useTourStore.getState().issued).toBe(false)
    useTourStore.getState().markIssued(visit)
    expect(useTourStore.getState().issued).toBe(true)
    useTourStore.getState().goTo(1)
    expect(useTourStore.getState().issued).toBe(false)
  })

  it('ignores extra stored keys, so a stored "goTo" cannot replace an action', async () => {
    sessionStorage.setItem(
      'od.tour',
      JSON.stringify({
        state: {
          started: true,
          active: true,
          step: 2,
          sent: [],
          turnId: null,
          lost: false,
          outcome: null,
          entering: false,
          goTo: 0,
          leave: null,
        },
        version: 3,
      }),
    )
    await useTourStore.persist.rehydrate()
    const tour = useTourStore.getState()
    expect(tour).toMatchObject({ active: true, step: 2 })
    tour.goTo(3)
    expect(useTourStore.getState().step).toBe(3)
    useTourStore.getState().leave()
    expect(useTourStore.getState().active).toBe(false)
  })

  it.each([
    ['a step from a build with more steps', { started: true, active: true, step: 12, sent: [] }],
    ['a fractional step', { started: true, active: true, step: 1.5, sent: [] }],
    ['a wrong shape', { started: 'yes', active: true, step: 2, sent: 'x' }],
    ['a turn ID that is not text', { started: true, active: true, step: 2, sent: [], turnId: 5 }],
    [
      'a baseline from the old shape',
      { started: true, active: true, step: 2, sent: [], baseline: null, turnId: undefined },
    ],
    [
      'an outcome that is not one',
      { started: true, active: true, step: 2, sent: [], outcome: 'won' },
    ],
    ['a garbage value', 'garbage'],
  ])('loads %s as idle', async (_name, state) => {
    sessionStorage.setItem(
      'od.tour',
      JSON.stringify({
        state:
          typeof state === 'object'
            ? { entering: false, turnId: null, lost: false, outcome: null, ...state }
            : state,
        version: 3,
      }),
    )
    await useTourStore.persist.rehydrate()
    expect(useTourStore.getState()).toMatchObject({
      started: false,
      active: false,
      step: 0,
      sent: [],
    })
  })

  it('loads a state saved before outcomes (version 2) as idle', async () => {
    sessionStorage.setItem(
      'od.tour',
      JSON.stringify({
        state: {
          started: true,
          active: true,
          step: 2,
          sent: [0],
          turnId: null,
          lost: false,
          outcome: null,
          entering: false,
        },
        version: 2,
      }),
    )
    await useTourStore.persist.rehydrate()
    expect(useTourStore.getState()).toMatchObject({ started: false, active: false, step: 0 })
  })

  it('latches the outcome once, upgrades missing to a result, and clears it on a new step', () => {
    const tour = useTourStore.getState()
    tour.begin()
    const { visit } = useTourStore.getState()
    tour.settle(visit, 'result')
    tour.settle(visit, 'missing')
    expect(useTourStore.getState().outcome).toBe('result')
    tour.goTo(1)
    const next = useTourStore.getState().visit
    expect(useTourStore.getState().outcome).toBeNull()
    tour.settle(visit, 'result')
    expect(useTourStore.getState().outcome).toBeNull()
    tour.settle(next, 'missing')
    expect(useTourStore.getState().outcome).toBe('missing')
    tour.settle(next, 'result')
    expect(useTourStore.getState().outcome).toBe('result')
  })

  it('loads a state saved by the old build (version 1) as idle', async () => {
    sessionStorage.setItem(
      'od.tour',
      JSON.stringify({
        state: {
          started: true,
          active: true,
          step: 2,
          sent: [0],
          baseline: { turnIds: [], results: 1 },
          entering: false,
        },
        version: 1,
      }),
    )
    await useTourStore.persist.rehydrate()
    expect(useTourStore.getState()).toMatchObject({ started: false, active: false, step: 0 })
  })

  it('is cleared by an identity reset', () => {
    useTourStore.getState().begin()
    useTourStore.getState().goTo(5)
    useTourStore.getState().setStartDialogOpen(true)
    resetIdentity(new QueryClient())
    expect(useTourStore.getState()).toMatchObject({
      started: false,
      active: false,
      step: 0,
      startDialogOpen: false,
    })
  })

  it('is spared by the switch’s own reset, and cleared by the next reset', () => {
    useTourStore.getState().begin()
    useTourStore.getState().goTo(5)
    resetIdentity(new QueryClient(), 'switch')
    expect(useTourStore.getState()).toMatchObject({ started: true, step: 5 })
    resetIdentity(new QueryClient())
    expect(useTourStore.getState().started).toBe(false)
  })

  it('is cleared by another kind of reset, such as the session ending during a switch', () => {
    useTourStore.getState().begin()
    useTourStore.getState().goTo(5)
    resetIdentity(new QueryClient())
    expect(useTourStore.getState().started).toBe(false)
  })
})
