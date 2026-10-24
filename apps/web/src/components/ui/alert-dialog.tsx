import { AlertDialog as AlertDialogPrimitive } from 'radix-ui'
import { createContext, useContext, type ComponentProps } from 'react'
import { cn } from '@/lib/utils'
import { Button, type ButtonProps } from './button'

const BusyContext = createContext(false)

/**
 * A centered confirm step (cancel a request, approve, deny), from the design's `.od-dialog`: Radix
 * AlertDialog, so it is `role="alertdialog"`, modal, keeps focus inside, hides the page, and
 * returns focus to its `AlertDialogTrigger` (a caller that opens it some other way sets focus
 * itself in `onCloseAutoFocus`). The scrim covers the whole window, sidebar included. A press on
 * the scrim does not close it.
 *
 * Focus starts on the cancel button, the safe choice. A caller that wants it elsewhere (the deny
 * dialog's note field) passes `onOpenAutoFocus`. Set `busy` while the confirm is running: Escape
 * then does nothing and the cancel button is disabled. The confirm button never closes the dialog on its own, since the caller
 * closes it when the work has finished.
 */
const AlertDialog = AlertDialogPrimitive.Root
const AlertDialogTrigger = AlertDialogPrimitive.Trigger

type AlertDialogContentProps = ComponentProps<typeof AlertDialogPrimitive.Content> & {
  /** True while the confirm is running; Escape is ignored. */
  busy?: boolean
}

function AlertDialogContent({
  className,
  busy = false,
  onEscapeKeyDown,
  ...props
}: AlertDialogContentProps) {
  return (
    <AlertDialogPrimitive.Portal>
      {/* A flex overlay gives the dialog a definite width to fill, so on a phone it keeps the
          overlay's padding as its margins instead of running past the right edge. */}
      <AlertDialogPrimitive.Overlay
        data-slot="alert-dialog-overlay"
        className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-scrim p-6 max-sm:p-4"
      >
        <BusyContext value={busy}>
          <AlertDialogPrimitive.Content
            data-slot="alert-dialog"
            onEscapeKeyDown={(event) => {
              if (busy) event.preventDefault()
              onEscapeKeyDown?.(event)
            }}
            className={cn(
              'flex w-full max-w-120 flex-col gap-2 rounded-xl bg-surface-raised p-6 text-ink shadow-md outline-none',
              className,
            )}
            {...props}
          />
        </BusyContext>
      </AlertDialogPrimitive.Overlay>
    </AlertDialogPrimitive.Portal>
  )
}

function AlertDialogTitle({
  className,
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Title>) {
  return (
    <AlertDialogPrimitive.Title
      data-slot="alert-dialog-title"
      className={cn('m-0 text-h2 text-pretty text-ink', className)}
      {...props}
    />
  )
}

function AlertDialogDescription({
  className,
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Description>) {
  return (
    <AlertDialogPrimitive.Description
      data-slot="alert-dialog-description"
      className={cn('m-0 text-body text-pretty text-ink-muted tabular-nums', className)}
      {...props}
    />
  )
}

/** The buttons, right-aligned; on a phone they stack at full width with the confirm on top. */
function AlertDialogActions({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="alert-dialog-actions"
      className={cn('mt-4 flex flex-wrap justify-end gap-3 max-sm:flex-col-reverse', className)}
      {...props}
    />
  )
}

/** The way out: closes the dialog. Listed first, so it comes first in the tab order. */
function AlertDialogCancel({ className, disabled, ...props }: ComponentProps<typeof Button>) {
  const busy = useContext(BusyContext)
  return (
    <AlertDialogPrimitive.Cancel asChild>
      <Button
        variant="secondary"
        disabled={disabled || busy}
        className={cn('max-sm:w-full', className)}
        {...props}
      />
    </AlertDialogPrimitive.Cancel>
  )
}

/** The confirming action: a standard primary button, never destructive. It does not close. */
function AlertDialogConfirm({ className, ...props }: ButtonProps) {
  return <Button className={cn('max-sm:w-full', className)} {...props} />
}

export {
  AlertDialog,
  AlertDialogActions,
  AlertDialogCancel,
  AlertDialogConfirm,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
  AlertDialogTrigger,
}
export type { AlertDialogContentProps }
