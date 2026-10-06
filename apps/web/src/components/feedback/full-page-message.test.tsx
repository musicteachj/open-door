import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Button } from '@/components/ui/button'
import { FullPageMessage } from './full-page-message'

const BODY = 'Try again in a moment. If it keeps happening, this reference helps us find it:'

describe('FullPageMessage', () => {
  it('shows the title as the h1, and moves focus to it on mount', () => {
    render(<FullPageMessage title="We couldn't find that page." />)
    const heading = screen.getByRole('heading', { level: 1, name: "We couldn't find that page." })
    expect(heading).toHaveAttribute('tabindex', '-1')
    expect(heading).toHaveFocus()
  })

  it('shows no focus ring on the programmatically focused heading', () => {
    render(<FullPageMessage title="Gone." />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveClass('outline-none')
  })

  it('leaves focus alone when told not to take it', () => {
    render(<FullPageMessage title="Gone." focusOnMount={false} />)
    expect(screen.getByRole('heading', { level: 1 })).not.toHaveFocus()
  })

  it('has one sentence and one action', () => {
    render(
      <FullPageMessage title="This sandbox has reset." body="Sandboxes last 24 hours.">
        <Button>Choose who to be</Button>
      </FullPageMessage>,
    )
    expect(screen.getByText('Sandboxes last 24 hours.')).toBeInTheDocument()
    expect(screen.getAllByRole('button')).toHaveLength(1)
  })

  it('shows the reference in Geist Mono, selecting with one click', () => {
    render(
      <FullPageMessage title="Oops." body={BODY} reference="7f3a9c2e7f3a9c2e7f3a9c2e7f3a9c2e" />,
    )
    expect(screen.getByText('Reference')).toBeInTheDocument()
    const id = screen.getByText('7f3a9c2e7f3a9c2e7f3a9c2e7f3a9c2e')
    expect(id).toHaveClass('font-mono', 'select-all')
  })

  it('has no reference without one', () => {
    render(<FullPageMessage title="Oops." />)
    expect(screen.queryByText('Reference')).not.toBeInTheDocument()
  })

  it('keeps a 440 px measure, so "find it:" does not sit alone', () => {
    render(<FullPageMessage title="Oops." body={BODY} />)
    const measure = screen.getByText(BODY).parentElement
    expect(measure).toHaveClass('max-w-110')
    expect(screen.getByText(BODY)).toHaveClass('text-pretty')
  })

  it('inside the shell has no logo', () => {
    render(<FullPageMessage title="Gone." />)
    expect(screen.queryByText('Open Door')).not.toBeInTheDocument()
  })

  it('outside the shell shows the logo', () => {
    render(<FullPageMessage title="Gone." outsideShell />)
    expect(screen.getByText('Open Door')).toBeInTheDocument()
  })
})
