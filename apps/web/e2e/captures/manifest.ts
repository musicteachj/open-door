import { GALLERY_STATE_IDS } from '../gallery-ids'

// What `make captures` photographs, and which design specimen each build state is set beside.
//
// The design side is one picture per area: the whole specimen page,
// docs/design/system/components/<area>/<area>.card.html, which already shows every state of that
// area's components (hover and focus are drawn with data-state attributes). Each build state is a
// section of the gallery, photographed after its interaction, so one specimen picture appears in
// every row of its area.

export const AREAS = [
  'approvals',
  'assistant',
  'confirm',
  'core',
  'directory',
  'feedback',
  'forms',
  'handbook',
  'landing',
  'navigation',
  'status',
  'timeoff',
] as const

export type Area = (typeof AREAS)[number]
export type GalleryStateId = (typeof GALLERY_STATE_IDS)[number]

/** Where an area's specimen page is, from the repository root. */
export const specimenPath = (area: Area) =>
  area === 'confirm'
    ? // The confirm card's specimen sits in the assistant folder, beside the other assistant parts.
      'docs/design/system/components/assistant/confirm.card.html'
    : `docs/design/system/components/${area}/${area}.card.html`

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
  overlay?: 'listbox' | 'menu' | 'tooltip' | 'alertdialog' | 'dialog'
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

  // Not photographed: the chapter navigator (.od-sec-nav has a style but no sketch) and the
  // handbook blocks (the section screenshots show them, but no sketch does).
  row('handbook', 'applicability-badge-chip'),
  row('handbook', 'applicability-badge-text'),
  row('handbook', 'applies-marker-applies'),
  row('handbook', 'applies-marker-not'),
  row('handbook', 'last-updated-default'),
  row('handbook', 'section-row-default', {
    variant: 'hover',
    note: 'Hovered',
    interaction: { action: 'hover', target: 'a' },
  }),
  row('handbook', 'section-row-default', {
    variant: 'focus',
    note: 'Keyboard focus',
    interaction: { action: 'focus', target: 'a' },
  }),
  row('handbook', 'section-row-current'),
  row('handbook', 'section-row-marker'),
  row('handbook', 'section-row-addendum'),
  row('handbook', 'section-group-chapter'),
  row('handbook', 'section-group-addendum'),
  row('handbook', 'search-result-applies', {
    variant: 'hover',
    note: 'Hovered',
    interaction: { action: 'hover', target: 'a' },
  }),
  row('handbook', 'search-result-applies', {
    variant: 'focus',
    note: 'Keyboard focus',
    interaction: { action: 'focus', target: 'a' },
  }),
  row('handbook', 'search-result-not'),
  row('handbook', 'cited-passage-default'),
  row('handbook', 'cited-passage-compact'),
  row('handbook', 'link-block-state-rules', {
    variant: 'hover',
    note: 'First row hovered',
    interaction: { action: 'hover', target: 'a' },
  }),
  row('handbook', 'link-block-state-rules', {
    variant: 'focus',
    note: 'First row focused by keyboard',
    interaction: { action: 'focus', target: 'a' },
  }),
  row('handbook', 'link-block-supplements'),
  row('handbook', 'sources-block-default'),
  row('handbook', 'passage-panel-open', {
    note: 'Opened by pressing the button',
    interaction: { action: 'click', target: 'button' },
  }),
  row('handbook', 'passage-panel-long', {
    note: 'Opened by pressing the button; the body scrolls inside the panel',
    interaction: { action: 'click', target: 'button' },
  }),
  row('handbook', 'passage-panel-loading'),
  row('handbook', 'passage-panel-error'),

  // Phase 5, stage 5: the time-off form's parts, the approvals parts, and the confirm card. Hover
  // and focus rows pick the real element, since the gallery draws neither.
  row('timeoff', 'status-badge-waiting'),
  row('timeoff', 'status-badge-approved'),
  row('timeoff', 'status-badge-denied'),
  row('timeoff', 'status-badge-recorded'),
  row('timeoff', 'status-badge-canceled'),
  row('timeoff', 'segmented-control-default', {
    variant: 'hover',
    note: 'Unselected option hovered',
    interaction: { action: 'hover', target: '[role="radio"][data-state="unchecked"]' },
  }),
  row('timeoff', 'segmented-control-default', {
    variant: 'focus',
    note: 'Keyboard focus',
    interaction: { action: 'focus', target: '[role="radio"]' },
  }),
  row('timeoff', 'segmented-control-selected'),
  row('timeoff', 'segmented-control-disabled'),
  row('timeoff', 'choice-group-default', {
    variant: 'hover',
    note: 'Unselected option hovered',
    interaction: { action: 'hover', target: '[role="radio"][data-state="unchecked"]' },
  }),
  row('timeoff', 'choice-group-default', {
    variant: 'focus',
    note: 'Keyboard focus',
    interaction: { action: 'focus', target: '[role="radio"]' },
  }),
  row('timeoff', 'choice-group-selected'),
  row('timeoff', 'choice-group-disabled'),
  row('timeoff', 'hours-stepper-default'),
  row('timeoff', 'hours-stepper-at-1'),
  row('timeoff', 'hours-stepper-at-8'),
  row('timeoff', 'hours-stepper-error'),
  row('timeoff', 'hours-stepper-disabled'),
  row('timeoff', 'date-field-empty'),
  row('timeoff', 'date-field-one-day'),
  row('timeoff', 'date-field-range'),
  row('timeoff', 'date-field-open'),
  row('timeoff', 'date-field-error'),
  row('timeoff', 'date-field-disabled'),
  row('timeoff', 'date-picker-pto', {
    variant: 'hover',
    note: 'Hovered day',
    interaction: { action: 'hover', target: 'button[data-day="2026-10-22"]' },
  }),
  row('timeoff', 'date-picker-pto', {
    variant: 'focus',
    note: 'Day with keyboard focus',
    interaction: { action: 'focus', target: 'button[data-day="2026-10-22"]' },
  }),
  row('timeoff', 'date-picker-sick'),
  row('timeoff', 'date-picker-range'),
  row('timeoff', 'form-message-warning'),
  row('timeoff', 'form-message-refusal'),
  row('timeoff', 'alert-dialog-cancel-request', {
    note: 'Opened by pressing the button',
    interaction: { action: 'click', target: 'button' },
    overlay: 'alertdialog',
  }),
  row('timeoff', 'balance-card-pto'),
  row('timeoff', 'balance-card-ceiling'),
  row('timeoff', 'balance-card-sick'),
  row('timeoff', 'balance-card-empty'),
  row('timeoff', 'balance-card-loading'),
  row('timeoff', 'request-row-approved', {
    variant: 'hover',
    note: 'Row hovered',
    interaction: { action: 'hover', target: 'li' },
  }),
  row('timeoff', 'request-row-approved', {
    variant: 'focus',
    note: 'Cancel focused by keyboard',
    interaction: { action: 'focus', target: 'button' },
  }),
  row('timeoff', 'request-row-waiting'),
  row('timeoff', 'request-row-recorded'),
  row('timeoff', 'request-row-canceled'),
  row('timeoff', 'request-row-denied'),
  row('timeoff', 'request-row-team'),
  row('timeoff', 'request-row-team-denied'),
  row('timeoff', 'request-group-upcoming'),
  row('timeoff', 'request-group-empty'),
  row('timeoff', 'preview-block-one-day'),
  row('timeoff', 'preview-block-weekend'),
  row('timeoff', 'preview-block-holiday'),
  row('timeoff', 'preview-block-sick-hours'),
  row('timeoff', 'preview-block-already-booked'),
  row('timeoff', 'preview-block-runs'),
  row('timeoff', 'preview-block-cross-year-sick'),
  row('timeoff', 'preview-block-nothing-picked'),
  row('timeoff', 'preview-block-nothing-counted'),
  row('timeoff', 'request-form-pto-one-day'),
  row('timeoff', 'request-form-holiday-range'),
  row('timeoff', 'request-form-sick-hours'),
  row('timeoff', 'request-form-short-notice'),
  row('timeoff', 'request-form-not-enough'),
  row('timeoff', 'request-form-overlap'),
  row('timeoff', 'request-form-submitting'),
  row('timeoff', 'request-form-sheet', {
    note: 'Opened by pressing the button',
    interaction: { action: 'click', target: 'button' },
    overlay: 'dialog',
  }),

  row('approvals', 'approval-card-default', {
    variant: 'hover-approve',
    note: 'Approve hovered',
    interaction: { action: 'hover', target: 'button[aria-label^="Approve"]' },
  }),
  row('approvals', 'approval-card-default', {
    variant: 'hover-deny',
    note: 'Deny hovered',
    interaction: { action: 'hover', target: 'button[aria-label^="Deny"]' },
  }),
  row('approvals', 'approval-card-default', {
    variant: 'focus',
    note: 'Approve focused by keyboard',
    interaction: { action: 'focus', target: 'button[aria-label^="Approve"]' },
  }),
  row('approvals', 'approval-card-no-coverage'),
  row('approvals', 'approval-card-conflict'),
  row('approvals', 'approval-card-conflict-decided'),
  row('approvals', 'approval-card-loading'),
  row('approvals', 'coverage-line-one-person'),
  row('approvals', 'coverage-line-none'),
  row('approvals', 'coverage-line-range'),
  row('approvals', 'coverage-line-part-of-day'),
  row('approvals', 'note-field-empty'),
  row('approvals', 'note-field-typed'),
  row('approvals', 'note-field-at-limit'),
  row('approvals', 'note-field-disabled'),
  row('approvals', 'decision-dialog-approve', {
    note: 'Opened by pressing the button',
    interaction: { action: 'click', target: 'button' },
    overlay: 'alertdialog',
  }),
  row('approvals', 'decision-dialog-deny', {
    note: 'Opened by pressing the button',
    interaction: { action: 'click', target: 'button' },
    overlay: 'alertdialog',
  }),
  row('approvals', 'decision-dialog-deciding', {
    note: 'Opened by pressing the button; it closes itself after 4 seconds',
    interaction: { action: 'click', target: 'button' },
    overlay: 'alertdialog',
  }),

  row('confirm', 'confirm-card-book-pending', {
    variant: 'hover',
    note: 'Confirm hovered',
    interaction: { action: 'hover', target: 'button' },
  }),
  row('confirm', 'confirm-card-book-pending', {
    variant: 'focus',
    note: 'Confirm focused by keyboard',
    interaction: { action: 'focus', target: 'button' },
  }),
  row('confirm', 'confirm-card-holiday-pending'),
  row('confirm', 'confirm-card-sick-pending'),
  row('confirm', 'confirm-card-approve-pending'),
  row('confirm', 'confirm-card-deny-pending'),
  row('confirm', 'confirm-card-cancel-pending'),
  row('confirm', 'confirm-card-short-notice-pending'),
  row('confirm', 'confirm-card-cross-year-sick-pending'),
  row('confirm', 'confirm-card-streaming'),
  row('confirm', 'confirm-card-confirming'),
  row('confirm', 'confirm-card-book-executed'),
  row('confirm', 'confirm-card-holiday-executed'),
  row('confirm', 'confirm-card-sick-executed'),
  row('confirm', 'confirm-card-approve-executed'),
  row('confirm', 'confirm-card-deny-executed-with-note'),
  row('confirm', 'confirm-card-deny-executed'),
  row('confirm', 'confirm-card-cancel-executed'),
  row('confirm', 'confirm-card-failed'),
  row('confirm', 'confirm-card-dismissed'),
  row('confirm', 'confirm-card-replaced'),
  row('confirm', 'confirm-card-expired'),
]

/** The screen folders the report compares, in docs/design/screens/. The other folders belong to
 * later phases (08 onward). manifest.test.ts checks that every PNG in these has a row. */
export const SCREEN_FOLDERS = [
  '01-landing',
  '02-app-shell',
  '03-assistant-home',
  '04-directory',
  '05-global-states',
  '06-handbook',
  '07-conversation',
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
  | 'directory'
  | 'directory-loading'
  | 'directory-my-team'
  | 'directory-empty'
  | 'directory-show-more'
  | 'profile-locked'
  | 'profile-hr'
  | 'profile-self'
  | 'session-expired'
  | 'not-found'
  | 'server-error'
  | 'handbook'
  | 'handbook-search'
  | 'handbook-no-results'
  | 'handbook-loading'
  | 'section'
  | 'section-loading'
  | 'cited-passage'
  | 'not-applicable'
  | 'missing-section'
  | 'panel-gallery'
  | 'conversation'

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
  /** For `conversation`: the state of the real /ask page to reach, named by the design file
   * (desktop-<scenario>.png). capture.spec.ts holds the steps for each. */
  scenario?: ConversationFile
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
const DIRECTORY_NAV =
  'Phase 3 and Phase 5: the Time off and Handbook items in the sidebar, and "How it\'s built" in Phase 7'
const HANDBOOK_NAV =
  'Phase 5: the Time off item in the sidebar and the at-a-glance figures, and "How it\'s built" in Phase 7'
const PHASE_5_HOME =
  'Phase 3 and Phase 5: the Time off and Handbook items and the at-a-glance figures'

/**
 * The conversation states of screen 07, by the design file's name (desktop-<file>.png). Each is
 * the gallery's state of the same name, `conversation-<file>`, which is where the names come from.
 */
export type ConversationFile<Id extends string = GalleryStateId> =
  Id extends `conversation-${infer File}` ? File : never

/**
 * A screen 07 row: the real /ask page, brought to the state by asking the scripted model a
 * question (or, for the states it can't reach, by stubbing a response), photographed at 1440 by
 * 900 beside the design screenshot of the same name. The steps are in capture.spec.ts.
 */
export const conversationRow = (
  file: ConversationFile,
  title: string,
  extra: Pick<ScreenRow, 'note' | 'persona' | 'differsUntil'> = {},
): ScreenRow => ({
  title: `07 Conversation: ${title}`,
  designImage: `${SCREENS}/07-conversation/desktop-${file}.png`,
  route: '/ask',
  persona: 'Priya',
  setup: 'conversation',
  scenario: file,
  target: 'viewport',
  ...extra,
})

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
    note: 'A question typed, the second row hovered, the third focused (so the box has lost focus). The failed-send error is the conversation page\'s send-error row below',
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
    title: "04 Directory: default (Priya's list)",
    designImage: `${SCREENS}/04-directory/desktop-default.png`,
    route: '/directory',
    persona: 'Priya',
    setup: 'directory',
    differsUntil: DIRECTORY_NAV,
    note: 'Only the first eight people are the seed company in the design; the rest are illustrative',
  },
  {
    title: '04 Directory: loading',
    designImage: `${SCREENS}/04-directory/desktop-loading.png`,
    route: '/directory',
    persona: 'Priya',
    setup: 'directory-loading',
    note: 'The list request is held, so the eight skeleton rows stay. The count already reads "145 people", because the counts load apart from the list; the design draws a bar there',
    differsUntil: DIRECTORY_NAV,
  },
  {
    title: '04 Directory: My team',
    designImage: `${SCREENS}/04-directory/desktop-my-team.png`,
    route: '/directory',
    persona: 'Marcus',
    setup: 'directory-my-team',
    differsUntil: `Phase 5: the Approvals item with its count. ${DIRECTORY_NAV}`,
  },
  {
    title: '04 Directory: no results',
    designImage: `${SCREENS}/04-directory/desktop-empty-search.png`,
    route: '/directory',
    persona: 'Priya',
    setup: 'directory-empty',
    note: 'Searched for "Jordn"',
    differsUntil: DIRECTORY_NAV,
  },
  {
    title: '04 Directory: Show more',
    designImage: `${SCREENS}/04-directory/desktop-show-more.png`,
    route: '/directory',
    persona: 'Priya',
    setup: 'directory-show-more',
    note: 'Scrolled to the end of the first 50. The design shows illustrative rows past the first eight',
    differsUntil: DIRECTORY_NAV,
  },
  {
    title: "04 Directory: profile, locked (Priya on Leo's)",
    designImage: `${SCREENS}/04-directory/desktop-profile-locked.png`,
    route: '/directory',
    persona: 'Priya',
    setup: 'profile-locked',
    differsUntil: DIRECTORY_NAV,
  },
  {
    title: "04 Directory: profile, HR view (Dana on Leo's)",
    designImage: `${SCREENS}/04-directory/desktop-profile-hr.png`,
    route: '/directory',
    persona: 'Dana',
    setup: 'profile-hr',
    differsUntil: `Phase 6: the Cases and Console items. ${DIRECTORY_NAV}`,
  },
  {
    title: '04 Directory: profile, own (Priya)',
    designImage: `${SCREENS}/04-directory/desktop-profile-self.png`,
    route: '/directory',
    persona: 'Priya',
    setup: 'profile-self',
    differsUntil: DIRECTORY_NAV,
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
    route: '/directory',
    persona: 'Priya',
    setup: 'server-error',
    note: "The directory's list request is answered with a 500 and a request ID, so the error shows inside the shell",
    differsUntil:
      'Phase 3 and Phase 5: the Time off and Handbook items, and "How it\'s built" in Phase 7. The build\'s reference is the full 32 characters, where the design draws 8',
  },

  {
    title: "06 Handbook: default (Priya's list)",
    designImage: `${SCREENS}/06-handbook/desktop-default.png`,
    route: '/handbook',
    persona: 'Priya',
    setup: 'handbook',
    differsUntil: HANDBOOK_NAV,
    note: 'The real handbook, so the list is longer and the words differ from the design, whose section text is placeholder',
  },
  {
    title: '06 Handbook: search',
    designImage: `${SCREENS}/06-handbook/desktop-search.png`,
    route: '/handbook',
    persona: 'Mateo',
    setup: 'handbook-search',
    note: 'Searched for "overtime"',
    differsUntil: HANDBOOK_NAV,
  },
  {
    title: '06 Handbook: no results',
    designImage: `${SCREENS}/06-handbook/desktop-no-results.png`,
    route: '/handbook',
    persona: 'Priya',
    setup: 'handbook-no-results',
    note: 'Searched for "dental plan"',
    differsUntil: HANDBOOK_NAV,
  },
  {
    title: '06 Handbook: loading',
    designImage: `${SCREENS}/06-handbook/desktop-loading.png`,
    route: '/handbook',
    persona: 'Priya',
    setup: 'handbook-loading',
    note: 'The handbook request is held, so the skeleton rows stay',
    differsUntil: HANDBOOK_NAV,
  },
  {
    title: '06 Handbook: section (Priya on 4.3)',
    designImage: `${SCREENS}/06-handbook/desktop-section.png`,
    route: '/handbook/4.3',
    persona: 'Priya',
    setup: 'section',
    differsUntil: HANDBOOK_NAV,
  },
  {
    title: '06 Handbook: section loading',
    designImage: `${SCREENS}/06-handbook/desktop-section-loading.png`,
    route: '/handbook/4.3',
    persona: 'Priya',
    setup: 'section-loading',
    note: 'The section request is held, so the skeleton stays',
    differsUntil: HANDBOOK_NAV,
  },
  {
    title: '06 Handbook: cited passage',
    designImage: `${SCREENS}/06-handbook/desktop-cited-passage.png`,
    route: '/handbook/CA-4.3?passage=p2',
    persona: 'Priya',
    setup: 'cited-passage',
    differsUntil: HANDBOOK_NAV,
  },
  {
    title: "06 Handbook: doesn't apply (Mateo on CA-4.3)",
    designImage: `${SCREENS}/06-handbook/desktop-not-applicable.png`,
    route: '/handbook/CA-4.3',
    persona: 'Mateo',
    setup: 'not-applicable',
    differsUntil: HANDBOOK_NAV,
  },
  {
    title: '06 Handbook: missing section',
    designImage: `${SCREENS}/06-handbook/desktop-missing-section.png`,
    route: '/handbook/8.2',
    persona: 'Priya',
    setup: 'missing-section',
    differsUntil: HANDBOOK_NAV,
  },
  {
    title: '06 Handbook: passage panel states',
    designImage: `${SCREENS}/06-handbook/desktop-panel-states.png`,
    route: '/gallery',
    setup: 'panel-gallery',
    note: 'The gallery\'s open panel. The loading, error, and long-passage states are the gallery\'s other passage-panel rows above. The panel docked on the real page is the next row',
  },
  {
    title: '06 Handbook: passage panel docked',
    designImage: `${SCREENS}/06-handbook/desktop-panel-docked.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'conversation',
    scenario: 'source-panel',
    target: 'viewport',
    note: "The real conversation page: the panel docked in the right rail, opened from a citation, as Priya. The scripted model answers with the handbook's own words, so the passage differs from the design's placeholder",
  },

  // Screen 07, the conversation view: the real /ask page against the real API with the scripted
  // model, one row per screenshot. The scripted model answers with the handbook's own words, so
  // the text differs from the design's placeholder everywhere. Priya, unless a row says otherwise.
  conversationRow('cited-answer', 'Cited answer', {
    note: 'Asked "How many sick days do I get?". The scripted model quotes the first passage it finds',
  }),
  conversationRow('source-panel', 'Source panel', {
    note: 'The first marker pressed: the passage docked at 420 px in the rail\'s place, with focus on its title',
  }),
  conversationRow('streaming-searching', 'Streaming, searching', {
    note: 'STUB: the turn\'s POST response is a stream the capture holds open after one "Searching the handbook…" step, because the scripted model finishes in milliseconds. Everything else is the real page',
  }),
  conversationRow('streaming-text', 'Streaming, text arriving', {
    note: 'STUB: the turn\'s stream is held open after the search steps, some text, and its first marker',
  }),
  conversationRow('streaming-progress-note', 'Streaming, progress note', {
    note: 'STUB: a draft note streams, is taken back (`text.retracted`), and the step "Searching the handbook again…" shows in its place. The design\'s "Read §4.3 Sick leave" step matches no tool event',
  }),
  conversationRow('stopped', 'Stopped', {
    note: 'STUB: a held stream with some text, then the real Stop button pressed. The scripted model leaves no partial text of its own',
  }),
  conversationRow('show-your-work', 'Show your work', {
    note: 'The profile line reads "Read your profile", with no private details (owner decision). The scripted model searches only, so only the search shows',
  }),
  conversationRow('show-your-work-routed', 'Show your work, routed', {
    note: 'Build decision: the sensitive turn shows the assistant\'s answer, then the panel, then "Show your work" with "Routed to HR guidance" and the "also go to" note. The screenshot is not redrawn',
  }),
  conversationRow('feedback-yes', 'Feedback, Yes'),
  conversationRow('feedback-no', 'Feedback, No'),
  conversationRow('feedback-thanks', 'Feedback, thank-you', {
    note: 'Build decision: the thank-you after a reason is "Thanks for the feedback.", the same as after Yes',
  }),
  conversationRow('other-state', "Another state's policy", {
    persona: 'Mateo',
    note: 'Mateo (Austin), asked "sick leave". The scripted model cites the California addendum when a search returns it (Priya) and otherwise the first result, so Mateo is cited §4.3, the company rule. It never says "this does not apply to you", which the design\'s answer does',
  }),
  conversationRow('not-found', 'Not found', {
    note: 'Asked "Where is the parking garage?", the scripted not-found scenario',
  }),
  conversationRow('refusal', 'Refusal', {
    note: 'Asked "Leo\'s home address", the scripted decline scenario. It searches nothing, so it shows no sources',
  }),
  conversationRow('sensitive', 'Sensitive', {
    note: 'Build decision: the assistant\'s answer comes first, with its sources and "Was this right?", then the panel. The screenshot is not redrawn',
  }),
  conversationRow('crisis', 'Crisis'),
  conversationRow('error-midstream', 'Error mid-stream', {
    note: 'Build decision: the error shows the API\'s own text (the "internal" error), where the screenshot shows its own sentence. Only "Retry" is the design\'s',
  }),
  conversationRow('cant-answer', "Can't answer right now", {
    note: 'The scripted guard failure scenario',
  }),
  conversationRow('send-error', 'Send error', {
    note: 'STUB: a held stream with some text, then Enter pressed with a draft typed. The error is the page\'s own "still answering" text',
  }),
  conversationRow('budget-sandbox', 'Budget banner, sandbox', {
    note: 'STUB: the conversation GET, with the budget fields changed (the scripted model can\'t spend a sandbox\'s budget)',
  }),
  conversationRow('budget-daily', 'Budget banner, daily', {
    note: 'STUB: the conversation GET, with the budget fields changed',
  }),
  conversationRow('length-hint', 'Length hint', {
    note: 'A draft of 1,962 characters typed into the composer',
  }),
  conversationRow('personal-data', 'Personal-data warning', {
    note: 'A number shaped like a Social Security number typed, and Enter pressed. The check runs in the browser',
  }),
  conversationRow('long-conversation', 'Long conversation', {
    note: 'STUB: the conversation GET, with `longHistory` on. "Show your work" stays on every finished answer, though the mockup leaves it off',
  }),
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
