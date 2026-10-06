import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Avatar, AvatarFallback, AvatarImage } from './avatar'

describe('Avatar', () => {
  it('falls back to initials when the image has not loaded', () => {
    // jsdom never loads images, so the fallback is what shows.
    render(
      <Avatar>
        <AvatarImage src="/nobody.png" alt="Marcus Bell" />
        <AvatarFallback>MB</AvatarFallback>
      </Avatar>,
    )
    expect(screen.getByText('MB')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('is a 36 px circle on the primary tint with semibold initials', () => {
    render(
      <Avatar data-testid="avatar">
        <AvatarFallback>MB</AvatarFallback>
      </Avatar>,
    )
    expect(screen.getByTestId('avatar')).toHaveClass('size-9', 'rounded-full')
    expect(screen.getByText('MB')).toHaveClass(
      'bg-primary-tint',
      'text-ink',
      'text-small',
      'font-semibold',
      'rounded-full',
    )
  })

  it('has a 28 px size for menus', () => {
    render(
      <Avatar size="sm" data-testid="avatar">
        <AvatarFallback>MB</AvatarFallback>
      </Avatar>,
    )
    expect(screen.getByTestId('avatar')).toHaveClass('size-7')
    expect(screen.getByTestId('avatar')).not.toHaveClass('size-9')
  })

  it('passes aria-hidden through, for a avatar beside the person’s name', () => {
    render(
      <Avatar aria-hidden="true" data-testid="avatar">
        <AvatarFallback>MB</AvatarFallback>
      </Avatar>,
    )
    expect(screen.getByTestId('avatar')).toHaveAttribute('aria-hidden', 'true')
  })
})
