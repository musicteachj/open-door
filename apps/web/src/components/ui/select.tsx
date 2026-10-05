import { Check, ChevronDown } from 'lucide-react'
import { Select as SelectPrimitive } from 'radix-ui'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'
import { rowFocusRing } from './focus-ring'
import { fieldClasses } from './field-classes'

const Select = SelectPrimitive.Root
const SelectGroup = SelectPrimitive.Group
const SelectValue = SelectPrimitive.Value

// The trigger is a field (input.tsx), so it gets the field's border, hover, and halo.
function SelectTrigger({
  className,
  children,
  ...props
}: ComponentProps<typeof SelectPrimitive.Trigger>) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      className={cn(
        fieldClasses,
        'inline-flex h-control w-auto items-center justify-between gap-2 pr-2.5 pl-3 text-left whitespace-nowrap',
        'cursor-pointer data-[placeholder]:text-ink-placeholder',
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDown aria-hidden="true" className="size-4 shrink-0 text-ink-muted" />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  )
}

// The panel and its rows follow the design's filter menu (forms.css): 1 px border, 10 px radius,
// medium shadow, 36 px rows with a 6 px radius, the chosen row on the primary tint.
function SelectContent({
  className,
  children,
  position = 'popper',
  ...props
}: ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        data-slot="select-content"
        position={position}
        sideOffset={4}
        className={cn(
          'relative z-50 max-h-(--radix-select-content-available-height) min-w-(--radix-select-trigger-width) overflow-x-hidden overflow-y-auto',
          'rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md',
          className,
        )}
        {...props}
      >
        <SelectPrimitive.Viewport data-slot="select-viewport" className="flex flex-col gap-0.5">
          {children}
        </SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  )
}

function SelectLabel({ className, ...props }: ComponentProps<typeof SelectPrimitive.Label>) {
  return (
    <SelectPrimitive.Label
      data-slot="select-label"
      className={cn('px-2.5 pt-2 pb-1 text-caption text-ink-muted', className)}
      {...props}
    />
  )
}

function SelectItem({
  className,
  children,
  ...props
}: ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item
      data-slot="select-item"
      className={cn(
        'relative flex h-9 w-full cursor-pointer items-center gap-2 rounded-xs pr-2.5 pl-8 text-ui font-regular text-ink select-none',
        rowFocusRing,
        'data-[highlighted]:bg-neutral-hover data-[state=checked]:bg-primary-tint',
        'data-[disabled]:pointer-events-none data-[disabled]:text-disabled-fg',
        className,
      )}
      {...props}
    >
      <span className="absolute left-2 flex size-4 items-center justify-center text-primary">
        <SelectPrimitive.ItemIndicator>
          <Check aria-hidden="true" className="size-4" strokeWidth={2} />
        </SelectPrimitive.ItemIndicator>
      </span>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  )
}

function SelectSeparator({
  className,
  ...props
}: ComponentProps<typeof SelectPrimitive.Separator>) {
  return (
    <SelectPrimitive.Separator
      data-slot="select-separator"
      className={cn('-mx-1 mb-0.5 h-px bg-border-subtle', className)}
      {...props}
    />
  )
}

export {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
}
