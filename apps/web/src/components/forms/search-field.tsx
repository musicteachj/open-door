import { Search, X } from 'lucide-react'
import { useRef } from 'react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

type SearchFieldProps = {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  /** The field's accessible name. The placeholder alone is not a name. */
  label?: string
  className?: string
}

/**
 * Filters a list as you type, from SearchField.jsx: no search button. The landmark is `<search>`.
 * "Clear search" appears only once there is text, and clearing (by the button or Escape) hands
 * back an empty string and puts focus back in the field, since the button disappears under it.
 * Controlled: the page owns the text (it lives in the URL, after a pause).
 */
function SearchField({
  value,
  onChange,
  placeholder = 'Search by name, title, or email',
  label = 'Search the directory by name, title, or email',
  className,
}: SearchFieldProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  function clear() {
    onChange('')
    inputRef.current?.focus()
  }

  return (
    <search data-slot="search-field" className={cn('relative w-90 max-w-full', className)}>
      <Search
        aria-hidden="true"
        className="pointer-events-none absolute top-3 left-3 size-4 text-ink-muted"
      />
      <Input
        ref={inputRef}
        type="search"
        aria-label={label}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && value) {
            event.preventDefault()
            clear()
          }
        }}
        className="pr-10 pl-9 [&::-webkit-search-cancel-button]:hidden"
      />
      {value ? (
        <button
          type="button"
          aria-label="Clear search"
          onClick={clear}
          className="absolute top-1 right-1 flex size-8 cursor-pointer items-center justify-center rounded-sm text-ink-muted hover:bg-neutral-hover hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-focus-ring focus-visible:outline-solid"
        >
          <X aria-hidden="true" className="size-4" />
        </button>
      ) : null}
    </search>
  )
}

export { SearchField }
export type { SearchFieldProps }
