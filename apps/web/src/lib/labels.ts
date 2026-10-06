// The accessible names, in one tested place. A component calls these instead of building its own
// string, so the wording a screen reader hears is decided here and proved by labels.test.ts. They
// come from the design's components (docs/design/system/components/) and the screens' notes.

/** "Approvals, 1 waiting". A count of zero, or none, is just the label. */
export function navItemLabel(label: string, count?: number): string {
  return count ? `${label}, ${count} waiting` : label
}

/**
 * The persona switcher's name. It always carries the full title, even when the title is cut off.
 * With no one current, it names the prompt the switcher shows instead.
 */
export function personaSwitcherLabel(name?: string, title?: string): string {
  if (name === undefined) return 'Switch persona. Choose a persona'
  return title === undefined
    ? `Switch persona. Current: ${name}`
    : `Switch persona. Current: ${name}, ${title}`
}

/** An at-a-glance link: the figure, what it counts, and where it goes. */
export function glanceLinkLabel(value: string, label: string, destination: string): string {
  return `${value} ${label}. Open ${destination}`
}

/** A landing-page persona card, which is one button. */
export function personaCardLabel(card: {
  name: string
  role: string
  location: string
  prompt: string
}): string {
  return `Start a sandbox as ${card.name}, ${card.role}, ${card.location}. ${card.prompt}`
}

/** A directory row, which is one link. */
export function directoryRowLabel(row: {
  name: string
  title: string
  department: string
  location: string
  isYou?: boolean
}): string {
  const base = `${row.name}, ${row.title}, ${row.department}, ${row.location}`
  return row.isYou ? `${base} (you)` : base
}
