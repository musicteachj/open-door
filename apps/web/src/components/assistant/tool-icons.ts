import {
  CalendarCheck,
  ClipboardCheck,
  FolderLock,
  Search,
  User,
  Users,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import type { ToolIconKind } from './labels'

/** The icon for each kind of tool, shared by the assistant's "Show your work" and the console's trace. */
export const TOOL_ICONS: Record<ToolIconKind, LucideIcon> = {
  search: Search,
  profile: User,
  people: Users,
  calendar: CalendarCheck,
  card: ClipboardCheck,
  cases: FolderLock,
  tool: Wrench,
}
