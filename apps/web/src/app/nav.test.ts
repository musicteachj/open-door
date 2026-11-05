import { describe, expect, it } from 'vitest'
import { NAV_ITEMS, navFor, type NavItemConfig } from './nav'

const priya = { isManager: false, isHrAdmin: false }
const mateo = { isManager: false, isHrAdmin: false }
const marcus = { isManager: true, isHrAdmin: false }
const dana = { isManager: false, isHrAdmin: true }

const labels = (items: readonly NavItemConfig[]) => items.map((i) => i.label)
const allAvailable = NAV_ITEMS.map((item) => ({ ...item, available: true }))

describe('NAV_ITEMS', () => {
  it('lists every item in the notes order, with its roles', () => {
    expect(NAV_ITEMS.map((i) => [i.label, i.roles])).toEqual([
      ['Ask', 'everyone'],
      ['Time off', 'everyone'],
      ['My cases', 'notHr'],
      ['Directory', 'everyone'],
      ['Handbook', 'everyone'],
      ['Approvals', 'manager'],
      ['Cases', 'hr'],
      ['Console', 'hr'],
    ])
  })

  it('gives every item a path and an icon', () => {
    expect(NAV_ITEMS.map((i) => i.to)).toEqual([
      '/ask',
      '/time-off',
      '/my-cases',
      '/directory',
      '/handbook',
      '/approvals',
      '/cases',
      '/console',
    ])
    for (const item of NAV_ITEMS) expect(item.icon).toBeTruthy()
  })

  it('has every item available, and no How it is built (dropped in Phase 7)', () => {
    expect(NAV_ITEMS.filter((i) => i.available).map((i) => i.label)).toEqual([
      'Ask',
      'Time off',
      'My cases',
      'Directory',
      'Handbook',
      'Approvals',
      'Cases',
      'Console',
    ])
    expect(NAV_ITEMS.map((i) => i.label)).not.toContain("How it's built")
  })
})

describe('navFor with every item available (the 02 notes)', () => {
  const person = ['Ask', 'Time off', 'My cases', 'Directory', 'Handbook']
  it.each([
    ['Priya', priya, [...person]],
    ['Mateo', mateo, [...person]],
    ['Marcus', marcus, [...person, 'Approvals']],
    ['Dana', dana, ['Ask', 'Time off', 'Directory', 'Handbook', 'Cases', 'Console']],
  ])('%s', (_name, me, expected) => {
    expect(labels(navFor(me, allAvailable))).toEqual(expected)
  })
})

describe('navFor', () => {
  const person = ['Ask', 'Time off', 'My cases', 'Directory', 'Handbook']

  it.each([
    ['Priya', priya],
    ['Mateo', mateo],
  ])('%s sees My cases after Time off, and no Approvals or Cases', (_name, me) => {
    expect(labels(navFor(me))).toEqual(person)
  })

  it('shows Approvals to a manager, after Handbook', () => {
    expect(labels(navFor(marcus))).toEqual([...person, 'Approvals'])
  })

  it('gives HR no My cases, and Cases then Console after Handbook', () => {
    expect(labels(navFor(dana))).toEqual([
      'Ask',
      'Time off',
      'Directory',
      'Handbook',
      'Cases',
      'Console',
    ])
  })

  it('hides Approvals again for the employee a manager switches to', () => {
    expect(labels(navFor(marcus))).toContain('Approvals')
    expect(labels(navFor(priya))).not.toContain('Approvals')
  })

  it('applies roles to a manager who is also HR', () => {
    expect(labels(navFor({ isManager: true, isHrAdmin: true }, allAvailable))).toEqual([
      'Ask',
      'Time off',
      'Directory',
      'Handbook',
      'Approvals',
      'Cases',
      'Console',
    ])
  })
})
