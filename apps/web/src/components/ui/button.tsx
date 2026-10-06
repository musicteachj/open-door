import { LoaderCircle } from 'lucide-react'
import type { ComponentProps, MouseEvent } from 'react'
import { cn } from '@/lib/utils'
import { buttonVariants, type ButtonVariants } from './button-variants'

type ButtonProps = ComponentProps<'button'> &
  ButtonVariants & {
    /** Shows a spinner before the label, keeps the label, and ignores clicks. */
    loading?: boolean
  }

/**
 * The only clickable action control. Primary is the one confirming action on a view.
 *
 * The design has no loading state yet (it is built, not designed): a spinner before the label.
 * A loading button is deliberately not `disabled`. Disabling a focused button drops keyboard
 * focus, so it stays focusable, says it is busy, and swallows the click instead.
 */
function Button({
  className,
  variant,
  size,
  type = 'button',
  loading = false,
  onClick,
  children,
  ...props
}: ButtonProps) {
  function handleClick(event: MouseEvent<HTMLButtonElement>) {
    if (loading) {
      event.preventDefault()
      return
    }
    onClick?.(event)
  }

  return (
    <button
      data-slot="button"
      type={type}
      aria-busy={loading || undefined}
      className={cn(buttonVariants({ variant, size }), className)}
      onClick={handleClick}
      {...props}
    >
      {loading && (
        <LoaderCircle
          data-slot="button-spinner"
          aria-hidden="true"
          className="size-4 animate-spin"
        />
      )}
      {children}
    </button>
  )
}

export { Button }
export type { ButtonProps }
