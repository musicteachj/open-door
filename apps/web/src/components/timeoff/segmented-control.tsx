import { Check } from 'lucide-react'
import { RadioGroup } from 'radix-ui'
import { useId } from 'react'
import { cn } from '@/lib/utils'
import { fieldLabelClass } from './field-parts'

type SegmentedOption = { value: string; label: string }

type SegmentedControlProps = {
  label: string
  options: SegmentedOption[]
  value: string
  onValueChange: (value: string) => void
  disabled?: boolean
  /**
   * `stacked` (the default) is the label above two equal columns. `inline` is the label beside
   * any number of options in one row, which scrolls sideways inside itself when it can't fit
   * (the case queue's "Show" filter), so the page never does.
   */
  layout?: 'stacked' | 'inline'
  className?: string
}

/**
 * A two-option choice (Type: PTO or Sick time), from SegmentedControl.jsx on Radix RadioGroup:
 * one tab stop, and the arrow keys move and select. The selected option is tinted and carries a
 * check, so it is not color alone.
 */
function SegmentedControl({
  label,
  options,
  value,
  onValueChange,
  disabled = false,
  layout = 'stacked',
  className,
}: SegmentedControlProps) {
  const labelId = useId()
  const inline = layout === 'inline'
  return (
    <div
      data-slot="segmented-control"
      className={cn(
        inline ? 'flex min-w-0 flex-row items-center gap-3' : 'flex flex-col gap-2',
        className,
      )}
    >
      <span
        id={labelId}
        className={cn(fieldLabelClass, inline && 'flex-none font-regular text-ink-muted')}
      >
        {label}
      </span>
      <RadioGroup.Root
        aria-labelledby={labelId}
        value={value}
        onValueChange={onValueChange}
        disabled={disabled}
        className={cn(
          'gap-1 rounded-md border border-border-strong bg-surface-sunken p-[3px]',
          inline ? 'flex min-w-0 overflow-x-auto' : 'grid grid-cols-2',
        )}
      >
        {options.map((option) => (
          <RadioGroup.Item
            key={option.value}
            value={option.value}
            className={cn(
              inline && 'flex-none px-4',
              'group flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-sm border-0 bg-transparent text-ui font-medium text-ink-nav',
              'transition-[background-color,color] outline-none',
              'focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus-ring focus-visible:outline-solid',
              'data-[state=unchecked]:enabled:hover:bg-neutral-hover data-[state=unchecked]:enabled:hover:text-ink',
              'data-[state=unchecked]:enabled:active:bg-border-subtle data-[state=unchecked]:enabled:active:text-ink',
              'data-[state=checked]:bg-primary-tint data-[state=checked]:font-semibold data-[state=checked]:text-ink',
              'disabled:cursor-not-allowed disabled:text-disabled-fg',
              'data-[state=checked]:disabled:bg-disabled-bg',
            )}
          >
            <RadioGroup.Indicator asChild>
              <Check
                aria-hidden="true"
                strokeWidth={2.25}
                className="size-3.5 text-primary group-disabled:text-disabled-fg"
              />
            </RadioGroup.Indicator>
            {option.label}
          </RadioGroup.Item>
        ))}
      </RadioGroup.Root>
    </div>
  )
}

export { SegmentedControl }
export type { SegmentedControlProps, SegmentedOption }
