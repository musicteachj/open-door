import {
  BookOpen,
  Calendar,
  ClipboardCheck,
  Code,
  FolderLock,
  LayoutDashboard,
  MessageCircle,
  Users,
  type LucideIcon,
} from 'lucide-react'

// One list of every sidebar item, from docs/design/screens/02-app-shell/notes.md, with who sees it
// and whether its page exists yet. Later phases flip `available`; nothing else changes. Icons are
// the design kit's (docs/design/system/ui_kits/assistant/AppShell.jsx).

export type NavRole = 'everyone' | 'manager' | 'hr'

export type NavItemConfig = {
  label: string
  to: string
  icon: LucideIcon
  roles: NavRole
  /** The item appears only once its page exists. */
  available: boolean
}

export const NAV_ITEMS: readonly NavItemConfig[] = [
  { label: 'Ask', to: '/ask', icon: MessageCircle, roles: 'everyone', available: true },
  { label: 'Time off', to: '/time-off', icon: Calendar, roles: 'everyone', available: false },
  { label: 'Directory', to: '/directory', icon: Users, roles: 'everyone', available: true },
  { label: 'Handbook', to: '/handbook', icon: BookOpen, roles: 'everyone', available: true },
  {
    label: 'Approvals',
    to: '/approvals',
    icon: ClipboardCheck,
    roles: 'manager',
    available: false,
  },
  { label: 'Cases', to: '/cases', icon: FolderLock, roles: 'hr', available: false },
  { label: 'Console', to: '/console', icon: LayoutDashboard, roles: 'hr', available: false },
  // Sits at the bottom of the sidebar. Hidden until Phase 7 builds its page.
  {
    label: "How it's built",
    to: '/how-its-built',
    icon: Code,
    roles: 'everyone',
    available: false,
  },
]

const SEES: Record<NavRole, (me: { isManager: boolean; isHrAdmin: boolean }) => boolean> = {
  everyone: () => true,
  manager: (me) => me.isManager,
  hr: (me) => me.isHrAdmin,
}

/** The items this person sees: available ones whose role rule they meet, in the notes' order. */
export function navFor(
  me: { isManager: boolean; isHrAdmin: boolean },
  items: readonly NavItemConfig[] = NAV_ITEMS,
): NavItemConfig[] {
  return items.filter((item) => item.available && SEES[item.roles](me))
}
