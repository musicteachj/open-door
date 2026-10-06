import { useId } from 'react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'

// Radix reserves the empty string for "no value", so "All" travels under a word no ID can be.
const ALL = 'all'

type FilterOption = { id: string; name: string; count: number }

type FilterSelectProps = {
  /** The filter's name, "Location" or "Department". It names the control. */
  label: string
  /** The chosen option's ID, or null for "All". */
  value: string | null
  /** From the facets: every option, zeros included. Extra fields (a location's state) are ignored. */
  options: FilterOption[]
  onChange: (id: string | null) => void
  allLabel?: string
  /** The trigger's DOM id, so a test or a label can address it. */
  id?: string
  className?: string
}

/**
 * Narrows a list by one field, from FilterSelect.jsx. A single-choice menu: "All" first (null),
 * then each option with its count, listed even at zero (the sketch doesn't disable them). The
 * chosen state is the value text and the tint together, never color alone. A combobox isn't
 * named from its content, so the visible label names it through `aria-labelledby`.
 */
function FilterSelect({
  label,
  value,
  options,
  onChange,
  allLabel = 'All',
  id,
  className,
}: FilterSelectProps) {
  const labelId = useId()
  const current = options.find((option) => option.id === value)
  // A value that matches no option is shown, and counted, as "All".
  const active = current !== undefined
  return (
    <Select
      // A value with no option gets no selection (''), so choosing "All" is a change Radix reports.
      value={current ? current.id : value === null ? ALL : ''}
      onValueChange={(next) => onChange(next === ALL ? null : next)}
    >
      <SelectTrigger
        id={id}
        data-slot="filter-select"
        aria-labelledby={labelId}
        data-active={active || undefined}
        className={cn(
          'gap-1.5 border-border-strong pr-2.5 pl-3.5 hover:border-border-strong-hover',
          'text-ui focus:shadow-none data-[active=true]:border-primary-tint data-[active=true]:bg-primary-tint',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring focus-visible:outline-solid',
          className,
        )}
      >
        <span id={labelId} className="text-ink-muted">
          {label}
        </span>
        <span className="font-semibold">
          <SelectValue placeholder={allLabel}>{current ? current.name : allLabel}</SelectValue>
        </span>
      </SelectTrigger>
      <SelectContent align="start" className="min-w-65">
        <SelectItem value={ALL}>{allLabel}</SelectItem>
        {options.map((option) => (
          <FilterOptionItem key={option.id} option={option} />
        ))}
      </SelectContent>
    </Select>
  )
}

// The option's name is the name, a comma, and the count ("Denver HQ, 40"), from a hidden label,
// because Radix names an item from its text alone and the count sits outside that text.
function FilterOptionItem({ option }: { option: FilterOption }) {
  const nameId = useId()
  return (
    <SelectItem
      value={option.id}
      aria-labelledby={nameId}
      trailing={
        <>
          <span aria-hidden="true" className="ml-auto text-ink-muted tabular-nums">
            {option.count}
          </span>
          <span id={nameId} hidden>
            {option.name}, {option.count}
          </span>
        </>
      }
    >
      {option.name}
    </SelectItem>
  )
}

export { FilterSelect }
export type { FilterOption, FilterSelectProps }
