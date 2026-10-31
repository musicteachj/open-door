import { describe, expect, it } from 'vitest'
import {
  directoryRowLabel,
  glanceLinkLabel,
  navItemLabel,
  personaCardLabel,
  personaSwitcherLabel,
} from './labels'

describe('navItemLabel', () => {
  it('names the count after the label', () => {
    expect(navItemLabel('Approvals', 1)).toBe('Approvals, 1 waiting')
    expect(navItemLabel('Approvals', 12)).toBe('Approvals, 12 waiting')
    expect(navItemLabel('Cases', 3, 'new')).toBe('Cases, 3 new')
  })

  it('is just the label with no count, or a count of zero', () => {
    expect(navItemLabel('Approvals')).toBe('Approvals')
    expect(navItemLabel('Approvals', 0)).toBe('Approvals')
    expect(navItemLabel('Cases', 0, 'new')).toBe('Cases')
  })
})

describe('personaSwitcherLabel', () => {
  it('carries the full title, never a shortened one', () => {
    expect(personaSwitcherLabel('Dana Whitfield', 'HR Business Partner')).toBe(
      'Switch persona. Current: Dana Whitfield, HR Business Partner',
    )
  })
})

describe('personaSwitcherLabel with no title', () => {
  it('names the person alone', () => {
    expect(personaSwitcherLabel('Priya Raman')).toBe('Switch persona. Current: Priya Raman')
  })
})

describe('personaSwitcherLabel with no one chosen', () => {
  it('names the prompt the switcher shows', () => {
    expect(personaSwitcherLabel(undefined, undefined)).toBe('Switch persona. Choose a persona')
  })
})

describe('glanceLinkLabel', () => {
  it('reads the figure, the label, and where the link goes', () => {
    expect(glanceLinkLabel('11.5', 'days PTO available', 'Time off')).toBe(
      '11.5 days PTO available. Open Time off',
    )
  })
})

describe('personaCardLabel', () => {
  it('names the persona, the role, and the place, then gives the prompt', () => {
    expect(
      personaCardLabel({
        name: 'Priya Raman',
        role: 'Visual Merchandiser',
        location: 'Oakland store',
        prompt: 'Ask about California sick leave and book a day off.',
      }),
    ).toBe(
      'Start a sandbox as Priya Raman, Visual Merchandiser, Oakland store. Ask about California sick leave and book a day off.',
    )
  })
})

describe('directoryRowLabel', () => {
  const row = {
    name: 'Leo Nakamura',
    title: 'Sales Associate',
    department: 'Store Operations',
    location: 'Oakland store',
  }

  it('lists name, title, department, and location', () => {
    expect(directoryRowLabel(row)).toBe(
      'Leo Nakamura, Sales Associate, Store Operations, Oakland store',
    )
  })

  it('adds "(you)" on your own row', () => {
    expect(directoryRowLabel({ ...row, isYou: true })).toBe(
      'Leo Nakamura, Sales Associate, Store Operations, Oakland store (you)',
    )
  })
})
