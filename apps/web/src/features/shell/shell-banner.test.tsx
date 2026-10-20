import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ShellBanner } from './shell-banner'
import { ShellBannerSlot } from './shell-slots'

describe('ShellBanner', () => {
  it('puts its children in the slot the shell gave', () => {
    const slot = document.createElement('div')
    document.body.append(slot)
    render(
      <ShellBannerSlot value={slot}>
        <ShellBanner>
          <p>Budget banner</p>
        </ShellBanner>
      </ShellBannerSlot>,
    )
    expect(slot).toContainElement(screen.getByText('Budget banner'))
    slot.remove()
  })

  it('draws nothing where there is no slot yet', () => {
    render(
      <ShellBanner>
        <p>Budget banner</p>
      </ShellBanner>,
    )
    expect(screen.queryByText('Budget banner')).not.toBeInTheDocument()
  })
})
