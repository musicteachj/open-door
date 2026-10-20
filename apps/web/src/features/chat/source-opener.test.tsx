import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { createQueryClient } from '@/lib/query-client'
import { resetIdentity } from '@/lib/identity'
import { forgetOpener, rememberOpener, returnFocusToOpener } from './source-opener'

afterEach(() => forgetOpener())

const marker = (id: string, label: string) => (
  <button data-slot="citation-marker" data-passage-id={id}>
    {label}
  </button>
)

describe('the opener', () => {
  it('puts focus back on the element that was remembered, once', () => {
    render(
      <>
        {marker('CA-4.3~p1', 'first')}
        {marker('CA-4.3~p1', 'second')}
      </>,
    )
    rememberOpener(screen.getByText('second'), 'CA-4.3~p1')
    returnFocusToOpener()
    expect(screen.getByText('second')).toHaveFocus()
    screen.getByText('first').focus()
    returnFocusToOpener()
    expect(screen.getByText('first')).toHaveFocus()
  })

  it('remembers only the newest opener', () => {
    render(
      <>
        {marker('CA-4.3~p1', 'one')}
        {marker('4.3~p1', 'two')}
      </>,
    )
    rememberOpener(screen.getByText('one'), 'CA-4.3~p1')
    rememberOpener(screen.getByText('two'), '4.3~p1')
    returnFocusToOpener()
    expect(screen.getByText('two')).toHaveFocus()
  })

  it('finds the passage’s marker again when the element was redrawn', () => {
    const { rerender } = render(<div key="a">{marker('CA-4.3~p1', 'old')}</div>)
    rememberOpener(screen.getByText('old'), 'CA-4.3~p1')
    rerender(<div key="b">{marker('CA-4.3~p1', 'new')}</div>)
    returnFocusToOpener()
    expect(screen.getByText('new')).toHaveFocus()
  })

  it('does nothing when there is no opener, or nothing to find', () => {
    render(marker('CA-4.3~p1', 'x'))
    returnFocusToOpener()
    expect(document.body).toHaveFocus()
    rememberOpener(null, '4.3~p9')
    returnFocusToOpener()
    expect(document.body).toHaveFocus()
  })

  it('forgets the opener when who is signed in changes, so another persona’s marker is never focused', () => {
    render(marker('CA-4.3~p1', 'mine'))
    rememberOpener(screen.getByText('mine'), 'CA-4.3~p1')
    resetIdentity(createQueryClient({ onUnauthorized: () => {} }))
    returnFocusToOpener()
    expect(document.body).toHaveFocus()
  })
})
