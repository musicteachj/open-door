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

/** The screen folders the report compares, in docs/design/screens/. The other folders belong to
 * later stages (04 and 06 onward). manifest.test.ts checks that every PNG in these has a row. */
export const SCREEN_FOLDERS = [
  '01-landing',
  '02-app-shell',
  '03-assistant-home',
  '05-global-states',
] as const

/** How to reach each state in the build. The capture spec holds the steps for each one; they use
 * the same page.route and page.clock tools as the browser tests. */
export type ScreenSetup =
  | 'landing'
  | 'landing-hover-focus'
  | 'landing-starting'
  | 'landing-error'
  | 'home'
  | 'persona-menu'
  | 'switching'
  | 'switched'
  | 'expiry-banner'
  | 'composer-states'
  | 'nav-states'
  | 'session-expired'
  | 'not-found'
  | 'server-error'

/** What the build photograph shows: the whole viewport, or one region of it. */
export type ScreenTarget = 'viewport' | 'page' | 'sidebar' | 'main' | 'rail'

/** One row per screenshot in docs/design/screens/. */
export type ScreenRow = {
  title: string
  /** The design screenshot, from the repository root. */
  designImage: string
  /** The route to open in the build, after signing in as `persona` when there is one. */
  route: string
  /** Signed in as this person first. Left out, the visitor is not signed in. */
  persona?: 'Priya' | 'Mateo' | 'Marcus' | 'Dana'
  setup: ScreenSetup
  target?: ScreenTarget
  /** Photographed at this size. 1440 by 900 when left out, the width the designs are drawn at. */
  viewport?: { width: number; height: number }
  /** Set when the design shows something Phase 2 can't, with the phase that adds it. The report
   * prints "Differs by design until " and this. The build photograph is the closest real state. */
  differsUntil?: string
  /** Shown under the row's title, for what the photograph does. */
  note?: string
}

const SCREENS = 'docs/design/screens'
const PHASE_5_HOME =
  'Phase 3 and Phase 5: the Time off and Handbook items and the at-a-glance figures'

export const SCREEN_ROWS: ScreenRow[] = [
  {
    title: '01 Landing: default',
    designImage: `${SCREENS}/01-landing/desktop-default.png`,
    route: '/',
    setup: 'landing',
    differsUntil: 'Phase 7: "How it\'s built" and the tour button, which are hidden until then',
  },
  {
    title: '01 Landing: hover and focus',
    designImage: `${SCREENS}/01-landing/desktop-hover-focus.png`,
    route: '/',
    setup: 'landing-hover-focus',
    note: "Priya's card hovered, Mateo's focused by keyboard",
  },
  {
    title: '01 Landing: starting',
    designImage: `${SCREENS}/01-landing/desktop-starting.png`,
    route: '/',
    setup: 'landing-starting',
    note: 'The sandbox request is held, so the card stays in its starting state',
    differsUntil: 'Phase 7: the tour button, which is hidden until then',
  },
  {
    title: '01 Landing: error',
    designImage: `${SCREENS}/01-landing/desktop-error.png`,
    route: '/',
    setup: 'landing-error',
    note: 'The sandbox request is answered with a 500',
    differsUntil: 'Phase 7: the tour button, which is hidden until then',
  },

  {
    title: "02 App shell: default (Priya's home)",
    designImage: `${SCREENS}/02-app-shell/desktop-default.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'home',
    differsUntil: PHASE_5_HOME,
    note: 'The clock says 21 h 30 min are left, as the design does',
  },
  {
    title: '02 App shell: persona menu',
    designImage: `${SCREENS}/02-app-shell/desktop-persona-menu.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'persona-menu',
    differsUntil: PHASE_5_HOME,
  },
  {
    title: '02 App shell: switching',
    designImage: `${SCREENS}/02-app-shell/desktop-switching.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'switching',
    note: 'The switch request is held, so the switcher stays busy',
    differsUntil: PHASE_5_HOME,
  },
  {
    title: '02 App shell: switched, with the toast',
    designImage: `${SCREENS}/02-app-shell/desktop-switched-toast.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'switched',
    note: "Marcus's home. The pointer rests on the toast so it stays open",
    differsUntil: 'Phase 5: the Approvals item and its count, and the at-a-glance figures',
  },
  {
    title: '02 App shell: expiry banner',
    designImage: `${SCREENS}/02-app-shell/desktop-expiry-banner.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'expiry-banner',
    note: 'The clock says 2 h 50 min are left',
    differsUntil: PHASE_5_HOME,
  },
  {
    title: '02 App shell: employee navigation',
    designImage: `${SCREENS}/02-app-shell/desktop-nav-employee.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'home',
    target: 'sidebar',
    note: "The sidebar, as Priya sees it (Mateo's is the same)",
    differsUntil: 'Phase 3 and Phase 5: Handbook and Time off, and the "How it\'s built" link in Phase 7',
  },
  {
    title: '02 App shell: manager navigation',
    designImage: `${SCREENS}/02-app-shell/desktop-nav-manager.png`,
    route: '/ask',
    persona: 'Marcus',
    setup: 'home',
    target: 'sidebar',
    differsUntil: 'Phase 5: the Approvals item with its count, Time off, and Handbook (Phase 3)',
  },
  {
    title: '02 App shell: HR navigation',
    designImage: `${SCREENS}/02-app-shell/desktop-nav-hr.png`,
    route: '/ask',
    persona: 'Dana',
    setup: 'home',
    target: 'sidebar',
    differsUntil: 'Phase 6: the Cases and Console items, and Time off and Handbook before that',
  },

  {
    title: '03 Assistant home: default',
    designImage: `${SCREENS}/03-assistant-home/desktop-default.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'home',
    differsUntil: PHASE_5_HOME,
  },
  {
    title: '03 Assistant home: composer and "Try asking" states',
    designImage: `${SCREENS}/03-assistant-home/desktop-composer-states.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'composer-states',
    target: 'main',
    note: 'A question typed, the second row hovered, the third focused (so the box has lost focus)',
    differsUntil:
      'Phase 4: the failed-send error, which needs a real assistant that can fail. The unit tests and the gallery cover it',
  },
  {
    title: '03 Assistant home: at-a-glance states',
    designImage: `${SCREENS}/03-assistant-home/desktop-glance-states.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'home',
    target: 'rail',
    differsUntil: 'Phase 3 and Phase 5: the at-a-glance links. Until then the rail shows only the sandbox indicator',
  },
  {
    title: '03 Assistant home: navigation states',
    designImage: `${SCREENS}/03-assistant-home/desktop-nav-states.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'nav-states',
    target: 'sidebar',
    note: 'Ask current, Directory hovered. The switcher shows its whole title, as it fits',
    differsUntil:
      'Phase 3: the Handbook item, to focus. The truncated title and its tooltip are in the gallery',
  },
  {
    title: '03 Assistant home: narrow (390 px)',
    designImage: `${SCREENS}/03-assistant-home/narrow-first-pass.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'home',
    target: 'page',
    viewport: { width: 390, height: 844 },
    note: 'The design is a first pass. The build fixes its two problems: the sandbox indicator is in the top bar, and the navigation fades when it scrolls',
    differsUntil: 'Phase 3 and Phase 5: the Time off and Handbook items and the at-a-glance figures',
  },

  {
    title: '05 Global states: session expired',
    designImage: `${SCREENS}/05-global-states/desktop-session-expired.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'session-expired',
    note: 'The next /me is answered with a 401',
  },
  {
    title: '05 Global states: not found',
    designImage: `${SCREENS}/05-global-states/desktop-not-found.png`,
    route: '/no/such/page',
    persona: 'Priya',
    setup: 'not-found',
    differsUntil: 'Phase 3 and Phase 5: the Time off and Handbook items',
  },
  {
    title: '05 Global states: something went wrong',
    designImage: `${SCREENS}/05-global-states/desktop-error.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'server-error',
    note: 'The first /me is answered with a 500, so the page shows outside the shell',
    differsUntil:
      "Phase 2's stage 6: the in-shell error, which needs a page that loads data (the directory's profile). Its reference is the full 32 characters, where the design draws 8",
  },
]

/** The slug that names a screen row's pictures: "01-landing-desktop-default". */
export const screenSlug = (row: Pick<ScreenRow, 'designImage'>) =>
  row.designImage.replace(`${SCREENS}/`, '').replace('/', '-').replace(/\.png$/, '')

export const designScreenFile = (row: Pick<ScreenRow, 'designImage'>) =>
  `design/screens/${screenSlug(row)}.png`
export const buildScreenFile = (row: Pick<ScreenRow, 'designImage'>) =>
  `build/screens/${screenSlug(row)}.png`

/** The group heading a screen row prints under, such as "screens: 01-landing". */
export const screenGroup = (row: Pick<ScreenRow, 'designImage'>) =>
  `screens: ${screenSlug(row).match(/^\d\d-[a-z-]+?(?=-(desktop|narrow))/)?.[0] ?? 'other'}`
