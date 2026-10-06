import { LogOut } from 'lucide-react'
import { useId, useRef, useState } from 'react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { initialsOf } from '@/lib/initials'
import { PersonaSwitcher } from './persona-switcher'

type PersonaOption = {
  key: string
  name: string
  /** The role shown under the name, such as "Visual Merchandiser". */
  title: string
}

type PersonaMenuProps = {
  personas: PersonaOption[]
  currentKey: string
  /** Called with the chosen persona's key. Never called for the current persona. */
  onSwitch: (key: string) => void
  onSignOut: () => void
  /** While a switch or sign-out runs, such as "Switching to Marcus…": the switcher shows it and the menu won't open. */
  busyLabel?: string
}

/**
 * The persona switcher and the menu it opens upward: who to view as, and Sign out. It calls no API;
 * the shell does that in `onSwitch` and `onSignOut`. A radio group, so screen readers hear
 * `menuitemradio` and which one is checked. Focus starts on the checked persona. From
 * PersonaMenu.jsx.
 */
function PersonaMenu({ personas, currentKey, onSwitch, onSignOut, busyLabel }: PersonaMenuProps) {
  const [open, setOpen] = useState(false)
  const checkedRef = useRef<HTMLDivElement>(null)
  // No match means no one is current: the switcher says so, and no row is checked.
  const current = personas.find((p) => p.key === currentKey)
  const labelId = useId()
  const noteId = useId()
  const busy = busyLabel !== undefined

  // Radix's content types leave out onOpenAutoFocus, though it honors it. A spread object gets it
  // past the type. Without it, focus would land on the menu's first row, not the checked one.
  const focusChecked = {
    onOpenAutoFocus: (event: Event) => {
      // With no checked item (an unknown currentKey), leave Radix's own focus on the first row.
      if (!checkedRef.current) return
      event.preventDefault()
      checkedRef.current.focus()
    },
  }

  return (
    <DropdownMenu open={open && !busy} onOpenChange={(next) => setOpen(next && !busy)}>
      <DropdownMenuTrigger asChild>
        <PersonaSwitcher name={current?.name} title={current?.title} busyLabel={busyLabel} />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        side="top"
        align="start"
        aria-labelledby={labelId}
        aria-describedby={noteId}
        loop
        {...focusChecked}
      >
        <DropdownMenuLabel id={labelId}>View as</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={currentKey}
          onValueChange={(key) => {
            if (key !== currentKey) onSwitch(key)
          }}
        >
          {personas.map((persona) => (
            <DropdownMenuRadioItem
              key={persona.key}
              value={persona.key}
              ref={persona.key === currentKey ? checkedRef : undefined}
              className="py-2 pr-2.5 pl-2"
            >
              <span className="flex items-center gap-2.5">
                <Avatar size="sm" aria-hidden="true">
                  <AvatarFallback>{initialsOf(persona.name)}</AvatarFallback>
                </Avatar>
                <span className="flex min-w-0 flex-col">
                  <span className="block text-ui leading-4.5 font-semibold">{persona.name}</span>
                  <span className="block text-caption text-ink-muted">{persona.title}</span>
                </span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <p id={noteId} className="px-2.5 pt-1.5 pb-2 text-caption text-ink-muted">
          Switching starts a new conversation.
        </p>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onSignOut}>
          <LogOut aria-hidden="true" className="size-4 text-ink-muted" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export { PersonaMenu }
export type { PersonaMenuProps, PersonaOption }
