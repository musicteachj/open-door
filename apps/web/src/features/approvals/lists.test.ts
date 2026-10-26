import { describe, expect, it } from 'vitest'
import type { RequestOut } from '@/api/generated'
import {
  PRIYA_WAITING,
  TEAM_APPROVED,
  TEAM_SICK,
  TODAY,
  ZARA_WAITING,
} from '@/app/gallery/fixtures/timeoff'
import { comingUp, waitingRequests } from './lists'

const patch = (request: RequestOut, changes: Partial<RequestOut>): RequestOut => ({
  ...request,
  ...changes,
})

describe('waitingRequests', () => {
  it('lists pending PTO oldest sent first, whatever order the API sent', () => {
    expect(waitingRequests([PRIYA_WAITING, ZARA_WAITING]).map((request) => request.id)).toEqual([
      ZARA_WAITING.id,
      PRIYA_WAITING.id,
    ])
  })

  it('never lists sick time, or anything that is no longer pending', () => {
    const sick = patch(ZARA_WAITING, { id: 'sick', type: 'sick' })
    const approved = patch(ZARA_WAITING, { id: 'done', status: 'approved' })
    expect(waitingRequests([sick, approved, PRIYA_WAITING]).map((request) => request.id)).toEqual([
      PRIYA_WAITING.id,
    ])
  })
})

describe('comingUp', () => {
  it('lists approved PTO and recorded sick time in the next 30 days, soonest first', () => {
    expect(comingUp([TEAM_APPROVED, TEAM_SICK], TODAY).map((request) => request.id)).toEqual([
      TEAM_SICK.id,
      TEAM_APPROVED.id,
    ])
  })

  it('includes a request under way, and the 30th day, and leaves out the 31st', () => {
    const underWay = patch(TEAM_APPROVED, {
      id: 'a',
      startDate: '2026-10-19',
      endDate: '2026-10-21',
    })
    const lastDay = patch(TEAM_APPROVED, {
      id: 'b',
      startDate: '2026-11-19',
      endDate: '2026-11-19',
    })
    const tooFar = patch(TEAM_APPROVED, { id: 'c', startDate: '2026-11-20', endDate: '2026-11-20' })
    expect(comingUp([tooFar, lastDay, underWay], TODAY).map((request) => request.id)).toEqual([
      'a',
      'b',
    ])
  })

  it('leaves out what has ended, what is not approved or recorded, and PTO that is only waiting', () => {
    const ended = patch(TEAM_APPROVED, {
      id: 'ended',
      startDate: '2026-10-19',
      endDate: '2026-10-19',
    })
    const denied = patch(TEAM_APPROVED, { id: 'denied', status: 'denied' })
    const canceled = patch(TEAM_APPROVED, { id: 'canceled', status: 'canceled' })
    const waiting = patch(TEAM_APPROVED, { id: 'waiting', status: 'pending' })
    expect(comingUp([ended, denied, canceled, waiting], TODAY)).toEqual([])
  })
})
