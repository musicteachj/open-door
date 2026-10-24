import { RadioGroup } from 'radix-ui'
import { useId } from 'react'
import { cn } from '@/lib/utils'
import { fieldLabelClass } from './field-parts'

type ChoiceOption = { value: string; label: string }

type ChoiceGroupProps = {
  label: string
  options: ChoiceOption[]
  value: string
  onValueChange: (value: string) => void
  disabled?: boolean
  className?: string
}

/**
 * Options as cards with a radio (How much: Full day or Half day, Full day or Some hours), from
 * ChoiceGroup.jsx on Radix RadioGroup: one tab stop, and the arrow keys move and select. The cards
 * sit side by side when they fit and stack when they do not.
 */
function ChoiceGroup({
  label,
  options,
  value,
  onValueChange,
  disabled = false,
  className,
}: ChoiceGroupProps) {
  const labelId = useId()
  return (
    <div data-slot="choice-group" className={cn('flex flex-col gap-2', className)}>
      <span id={labelId} className={fieldLabelClass}>
        {label}
      </span>
      <RadioGroup.Root
        aria-labelledby={labelId}
        value={value}
        onValueChange={onValueChange}
        disabled={disabled}
        // 180 px fits "Half day (4 hours)" on one line: two cards in the 372 px form, stacked on a phone.
        className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-2"
      >
        {options.map((option) => (
          <RadioGroup.Item
            key={option.value}
            value={option.value}
            className={cn(
              'group flex min-h-11 cursor-pointer items-center gap-2.5 rounded-md border border-border-strong bg-surface-raised px-3 py-2.5 text-left text-ui font-regular text-ink',
              'transition-[background-color,border-color] outline-none',
              'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid',
              'data-[state=unchecked]:enabled:hover:border-input-border-hover data-[state=unchecked]:enabled:hover:bg-surface-hover',
              'data-[state=unchecked]:enabled:active:bg-neutral-hover',
              // The 2 px selected edge is the border plus an inset 1 px ring of the same color.
              'enabled:data-[state=checked]:border-primary enabled:data-[state=checked]:bg-primary-tint enabled:data-[state=checked]:shadow-[inset_0_0_0_1px_var(--color-primary)]',
              'disabled:cursor-not-allowed disabled:border-disabled-bg disabled:bg-surface-raised disabled:text-disabled-fg disabled:shadow-none',
            )}
          >
            <span
              data-slot="choice-radio"
              aria-hidden="true"
              className={cn(
                'flex size-4 flex-none items-center justify-center rounded-full border-[1.5px] border-input-border bg-surface-raised',
                'group-disabled:border-disabled-bg group-data-[state=checked]:group-enabled:border-primary',
              )}
            >
              <RadioGroup.Indicator asChild>
                <span
                  data-slot="choice-dot"
                  className="size-2 rounded-full bg-primary group-disabled:bg-disabled-fg"
                />
              </RadioGroup.Indicator>
            </span>
            {option.label}
          </RadioGroup.Item>
        ))}
      </RadioGroup.Root>
    </div>
  )
}

export { ChoiceGroup }
export type { ChoiceGroupProps, ChoiceOption }
