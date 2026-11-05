import { render, screen, waitFor } from '@testing-library/react'
import { turnKey } from '@/lib/turn-key'
import { afterEach, describe, expect, it } from 'vitest'
import { TOUR } from './script'
import { findTourElements, useTourElements } from './use-tour-elements'

afterEach(() => {
  document.body.innerHTML = ''
})

const html = (markup: string) => {
  document.body.innerHTML = markup
}

describe('findTourElements', () => {
  it('points at the last of the step’s targets that is on the page', () => {
    html('<form data-tour="composer" id="c"></form>')
    expect(findTourElements(TOUR[2]!).target?.id).toBe('c')
    html(
      '<form data-tour="composer" id="c"></form><section data-slot="confirm-card"><button data-tour="confirm" id="ok"></button></section>',
    )
    const found = findTourElements(TOUR[2]!)
    expect(found.target?.id).toBe('ok')
    expect(found.composer?.id).toBe('c')
    expect(found.result?.getAttribute('data-slot')).toBe('confirm-card')
  })

  it('uses the latest match when several are on the page', () => {
    html('<form data-tour="composer" id="a"></form><form data-tour="composer" id="b"></form>')
    expect(findTourElements(TOUR[1]!).target?.id).toBe('b')
  })

  it('finds the conversation’s sticky header, the parent of its header row', () => {
    html('<div id="sticky"><div data-slot="conversation-header"></div></div>')
    expect(findTourElements(TOUR[0]!).header?.id).toBe('sticky')
    html('<main></main>')
    expect(findTourElements(TOUR[0]!).header).toBeNull()
  })

  it('points at the first flagged row, the newest, not the oldest', () => {
    html(
      '<div data-tour="flagged-row" id="newest"></div><div data-tour="flagged-row" id="oldest"></div>',
    )
    expect(findTourElements(TOUR[8]!).target?.id).toBe('newest')
  })

  it('points at the first source chip under the latest answer', () => {
    html(`
      <form data-tour="composer"></form>
      <div data-slot="source-chips"><button data-tour="source-chip" id="old"></button></div>
      <div data-slot="source-chips">
        <button data-tour="source-chip" id="first"></button>
        <button data-tour="source-chip" id="second"></button>
      </div>`)
    expect(findTourElements(TOUR[0]!).target?.id).toBe('first')
  })

  it('finds the HR panel as the result of a step that expects one, and none otherwise', () => {
    html('<section data-slot="escalation-panel" id="p"></section>')
    expect(findTourElements(TOUR[6]!).result?.id).toBe('p')
    // A step that expects nothing keeps the card off the latest answer instead.
    expect(findTourElements(TOUR[0]!).result).toBeNull()
    html(
      '<div data-slot="assistant-message" id="old"></div><div data-slot="assistant-message" id="new"></div>',
    )
    expect(findTourElements(TOUR[0]!).result?.id).toBe('new')
  })
})

describe('the step’s own result', () => {
  const cards = (turn: string) =>
    `<div data-slot="proposal-cards" data-turn-key="${turnKey(turn)}"><section data-slot="confirm-card" id="card-${turn}"></section></div>`

  it('finds a confirm card only inside the given turn’s own cards', () => {
    html(cards('old') + cards('mine'))
    expect(findTourElements(TOUR[2]!, 'mine').own?.id).toBe('card-mine')
    expect(findTourElements(TOUR[2]!, 'mine').result?.id).toBe('card-mine')
  })

  it('has no own result when only an earlier turn’s card is on the page, or the turn is unknown', () => {
    html(cards('old'))
    expect(findTourElements(TOUR[2]!, 'mine').own).toBeNull()
    expect(findTourElements(TOUR[2]!, null).own).toBeNull()
    // The card still keeps the coach mark off it: placement is not the result.
    expect(findTourElements(TOUR[2]!, 'mine').result?.id).toBe('card-old')
  })

  const asked = (turn: string) =>
    `<div data-slot="user-message" data-turn-key="${turnKey(turn)}"></div>`

  it('counts a card of a later turn (a question asked again), and the ring points at it', () => {
    html(asked('old') + cards('old') + asked('mine') + asked('later') + cards('later'))
    const found = findTourElements(TOUR[2]!, 'mine')
    expect(found.own?.id).toBe('card-later')
    expect(found.result?.id).toBe('card-later')
  })

  it('never counts a card of a turn before the chip’s own, even with the turn marked', () => {
    html(asked('old') + cards('old') + asked('mine'))
    expect(findTourElements(TOUR[2]!, 'mine').own).toBeNull()
  })

  it('counts an HR panel of a later turn, not an earlier one', () => {
    const panel = (turn: string) =>
      `<section data-slot="escalation-panel" data-turn-key="${turnKey(turn)}" id="p-${turn}"></section>`
    html(asked('old') + panel('old') + asked('mine') + asked('later') + panel('later'))
    expect(findTourElements(TOUR[6]!, 'mine').own?.id).toBe('p-later')
    html(asked('old') + panel('old') + asked('mine'))
    expect(findTourElements(TOUR[6]!, 'mine').own).toBeNull()
  })

  it('has no own result for an empty cards row of the turn', () => {
    html('<div data-slot="proposal-cards" data-turn-key="${turnKey(\'mine\')}"></div>')
    expect(findTourElements(TOUR[2]!, 'mine').own).toBeNull()
  })

  it('finds an HR panel carrying the turn’s ID, and not another turn’s', () => {
    html(
      `<section data-slot="escalation-panel" data-turn-key="${turnKey('old')}" id="o"></section><section data-slot="escalation-panel" data-turn-key="${turnKey('mine')}" id="m"></section>`,
    )
    expect(findTourElements(TOUR[6]!, 'mine').own?.id).toBe('m')
    html(
      `<section data-slot="escalation-panel" data-turn-key="${turnKey('old')}" id="o"></section>`,
    )
    expect(findTourElements(TOUR[6]!, 'mine').own).toBeNull()
  })
})

describe('useTourElements', () => {
  it('picks up an element that arrives after the first read', async () => {
    function Probe() {
      const { target } = useTourElements(TOUR[2]!, null, true)
      return <output>{target?.id ?? 'none'}</output>
    }
    html('<form data-tour="composer" id="c"></form>')
    render(<Probe />)
    expect(screen.getByRole('status')).toHaveTextContent('c')
    const button = document.createElement('button')
    button.dataset.tour = 'confirm'
    button.id = 'ok'
    document.body.append(button)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('ok'))
  })

  it('watches the page’s main area, not the rest of the document', async () => {
    function Probe() {
      const { target } = useTourElements(TOUR[2]!, null, true)
      return <output>{target?.id ?? 'none'}</output>
    }
    html('<main id="m"></main>')
    render(<Probe />)
    const outside = document.createElement('button')
    outside.dataset.tour = 'confirm'
    outside.id = 'outside'
    document.body.prepend(outside)
    await new Promise((resolve) => setTimeout(resolve, 80))
    expect(screen.getByRole('status')).toHaveTextContent('none')
    const inside = document.createElement('button')
    inside.dataset.tour = 'confirm'
    inside.id = 'inside'
    document.getElementById('m')!.append(inside)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('inside'))
  })

  it('picks up an existing element that takes the data-tour attribute', async () => {
    function Probe() {
      const { target } = useTourElements(TOUR[2]!, null, true)
      return <output>{target?.id ?? 'none'}</output>
    }
    html('<main><button id="late"></button></main>')
    render(<Probe />)
    expect(screen.getByRole('status')).toHaveTextContent('none')
    document.getElementById('late')!.setAttribute('data-tour', 'confirm')
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('late'))
  })
})
