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
      ['Directory', 'everyone'],
      ['Handbook', 'everyone'],
      ['Approvals', 'manager'],
      ['Cases', 'hr'],
      ['Console', 'hr'],
      ["How it's built", 'everyone'],
    ])
  })

  it('gives every item a path and an icon', () => {
    expect(NAV_ITEMS.map((i) => i.to)).toEqual([
      '/ask',
      '/time-off',
      '/directory',
      '/handbook',
      '/approvals',
      '/cases',
      '/console',
      '/how-its-built',
    ])
    for (const item of NAV_ITEMS) expect(item.icon).toBeTruthy()
  })

  it('has only Ask, Time off, Directory, Handbook, and Approvals available in Phase 5', () => {
    expect(NAV_ITEMS.filter((i) => i.available).map((i) => i.label)).toEqual([
      'Ask',
      'Time off',
      'Directory',
      'Handbook',
      'Approvals',
    ])
  })

  it("configures How it's built, hidden until Phase 7", () => {
    const built = NAV_ITEMS.find((i) => i.label === "How it's built")
    expect(built).toBeDefined()
    expect(built?.available).toBe(false)
  })
})

describe('navFor with every item available (the 02 notes)', () => {
  const everyone = ['Ask', 'Time off', 'Directory', 'Handbook']
  const built = "How it's built"
  it.each([
    ['Priya', priya, [...everyone, built]],
    ['Mateo', mateo, [...everyone, built]],
    ['Marcus', marcus, [...everyone, 'Approvals', built]],
    ['Dana', dana, [...everyone, 'Cases', 'Console', built]],
  ])('%s', (_name, me, expected) => {
    expect(labels(navFor(me, allAvailable))).toEqual(expected)
  })
})

describe('navFor in Phase 5', () => {
  const everyone = ['Ask', 'Time off', 'Directory', 'Handbook']

  it.each([
    ['Priya', priya],
    ['Mateo', mateo],
    ['Dana', dana],
  ])('%s sees Ask, Time off, Directory, and Handbook, and no Approvals', (_name, me) => {
    expect(labels(navFor(me))).toEqual(everyone)
  })

  it('shows Approvals to a manager, after Handbook', () => {
    expect(labels(navFor(marcus))).toEqual([...everyone, 'Approvals'])
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
      "How it's built",
    ])
  })
})
