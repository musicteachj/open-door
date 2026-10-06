import { GALLERY_STATE_IDS } from '../gallery-ids'

// What `make captures` photographs, and which design specimen each build state is set beside.
//
// The design side is one picture per area: the whole specimen page,
// docs/design/system/components/<area>/<area>.card.html, which already shows every state of that
// area's components (hover and focus are drawn with data-state attributes). Each build state is a
// section of the gallery, photographed after its interaction, so one specimen picture appears in
// every row of its area.

export const AREAS = [
  'assistant',
  'core',
  'directory',
  'feedback',
  'forms',
  'landing',
  'navigation',
  'status',
] as const

export type Area = (typeof AREAS)[number]
export type GalleryStateId = (typeof GALLERY_STATE_IDS)[number]

/** Where an area's specimen page is, from the repository root. */
export const specimenPath = (area: Area) =>
  `docs/design/system/components/${area}/${area}.card.html`

/** What to do inside the section, with Playwright's locator for it, before the photograph. */
export type Interaction = {
  action: 'hover' | 'focus' | 'click'
  /** A CSS selector inside the section. The first match is used. */
  target: string
}

export type ComponentRow = {
  /** The gallery state, by the id of its heading. */
  id: GalleryStateId
  area: Area
  /** Shown under the row's title in the report. */
  note?: string
  interaction?: Interaction
  /** Tells two rows of one state apart, in the picture's file name. */
  variant?: string
  /** The interaction opens a floating panel outside the section. The spec waits for an element
   * with this role to be visible before photographing, and photographs the viewport, not the
   * section alone. */
  overlay?: 'listbox' | 'menu' | 'tooltip'
}

/** Paths the report links to, relative to captures/index.html. The spec takes every path from
 * these two functions. */
export const designFile = (area: Area) => `design/${area}.png`
export const buildFile = (row: Pick<ComponentRow, 'id' | 'variant'>) =>
  `build/${row.id}${row.variant ? `-${row.variant}` : ''}.png`

const row = (area: Area, id: GalleryStateId, extra: Partial<ComponentRow> = {}): ComponentRow => ({
  id,
  area,
  ...extra,
})

export const COMPONENT_ROWS: ComponentRow[] = [
  // Not photographed: the shadcn primitives (input, select, menu, avatar, skeleton), the page
  // header, and the empty state. The design system has no specimen for them.
  row('core', 'button-primary-default'),
  row('core', 'button-primary-disabled'),
  row('core', 'button-primary-loading'),
  row('core', 'button-destructive-loading'),
  row('core', 'logo-default'),
  row('core', 'logo-customer'),

  row('status', 'sandbox-indicator-default'),
  row('status', 'glance-link-default'),
  row('status', 'glance-link-marker'),
  row('status', 'glance-list-default'),

  row('navigation', 'nav-item-default', {
    variant: 'hover',
    note: 'Hovered',
    interaction: { action: 'hover', target: 'a' },
  }),
  row('navigation', 'nav-item-default', {
    variant: 'focus',
    note: 'Keyboard focus',
    interaction: { action: 'focus', target: 'a' },
  }),
  row('navigation', 'nav-item-current'),
  row('navigation', 'nav-item-count'),
  row('navigation', 'nav-item-count-current'),
  row('navigation', 'persona-switcher-closed'),
  row('navigation', 'persona-switcher-truncated', {
    note: 'Hovered, so the tooltip shows',
    interaction: { action: 'hover', target: 'button' },
    overlay: 'tooltip',
  }),
  row('navigation', 'persona-switcher-switching'),
  row('navigation', 'persona-menu-open', {
    note: 'Menu opened by pressing the switcher',
    interaction: { action: 'click', target: 'button' },
    overlay: 'menu',
  }),

  row('feedback', 'banner-default'),
  row('feedback', 'banner-no-dismiss'),
  row('feedback', 'full-page-message-session-expired'),
  row('feedback', 'full-page-message-not-found'),
  row('feedback', 'full-page-message-error'),

  row('assistant', 'composer-empty', {
    note: 'Focused',
    interaction: { action: 'focus', target: 'textarea' },
  }),
  row('assistant', 'composer-typed', {
    note: 'Focused',
    interaction: { action: 'focus', target: 'textarea' },
  }),
  row('assistant', 'composer-error'),
  row('assistant', 'composer-busy'),
  row('assistant', 'try-asking-default', {
    note: 'First row hovered',
    interaction: { action: 'hover', target: 'button' },
  }),
  row('assistant', 'inline-error-retry'),
  row('assistant', 'inline-error-message'),

  row('landing', 'persona-card-default'),
  row('landing', 'persona-card-starting'),
  row('landing', 'persona-card-disabled'),

  row('forms', 'search-field-empty'),
  row('forms', 'search-field-typed'),
  row('forms', 'filter-select-default', {
    note: 'Hovered',
    interaction: { action: 'hover', target: 'button' },
  }),
  row('forms', 'filter-select-active'),
  row('forms', 'filter-select-open', {
    note: 'Opened by pressing the trigger',
    interaction: { action: 'click', target: '#filter-select-open-trigger' },
    overlay: 'listbox',
  }),
  row('forms', 'filter-toggle-off'),
  row('forms', 'filter-toggle-on'),

  row('directory', 'directory-table-default'),
  row('directory', 'directory-table-loading'),
  row('directory', 'directory-row-default'),
  row('directory', 'directory-row-you'),
  row('directory', 'skeleton-row-default'),
  row('directory', 'detail-list-values'),
  row('directory', 'detail-list-locked'),
]

/** One row per screenshot in docs/design/screens/. Stages 5 and 6 add them, and the capture spec
 * gains a screen route to photograph for each. */
export type ScreenRow = {
  title: string
  /** The design screenshot, from the repository root. */
  designImage: string
  /** The route to open in the build, and what to do there before the photograph. */
  route: string
}

export const SCREEN_ROWS: ScreenRow[] = []
