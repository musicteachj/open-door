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
 * later phases (11 onward). manifest.test.ts checks that every PNG in these has a row. */
export const SCREEN_FOLDERS = [
  '01-landing',
  '02-app-shell',
  '03-assistant-home',
  '04-directory',
  '05-global-states',
  '06-handbook',
  '07-conversation',
  '08-time-off',
  '09-approvals',
  '10-confirm-cards',
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
  | 'time-off'
  | 'approvals'
  | 'confirm-card'

/** The states of screen 08, by the design file's name (desktop-<state>.png). */
export type TimeOffState =
  | 'default'
  | 'default-full'
  | 'ceiling'
  | 'empty'
  | 'loading'
  | 'error'
  | 'form-one-day'
  | 'form-half-day'
  | 'form-weekend'
  | 'form-holiday'
  | 'form-sick-hours'
  | 'form-short-notice'
  | 'form-not-enough'
  | 'form-overlap'
  | 'form-submitting'
  | 'submitted'
  | 'submitted-sick'
  | 'cancel-confirm'
  | 'canceled'
  | 'date-picker-open'
  | 'date-picker-sick'
  | 'date-picker-range'

/** The states of screen 09. */
export type ApprovalsState =
  | 'default'
  | 'default-full'
  | 'approve-confirm'
  | 'deny-confirm'
  | 'deciding'
  | 'approved'
  | 'denied'
  | 'conflict'
  | 'empty'
  | 'loading'
  | 'error'
  | 'nav-manager'
  | 'home-manager'

/** The states of screen 10. */
export type ConfirmCardState =
  | 'pending'
  | 'pending-streaming'
  | 'confirming'
  | 'executed'
  | 'failed'
  | 'dismissed'
  | 'replaced'
  | 'expired'
  | 'holiday'
  | 'sick'
  | 'approve'
  | 'deny'
  | 'cancel'
  | 'executed-variants'
  | 'conversation'
  | 'conversation-executed'
  | 'sensitive'
  | 'sensitive-work'

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
  /** For `time-off`, `approvals`, and `confirm-card`: the state of the real page to reach, named
   * by the design file (desktop-<state>.png). capture.spec.ts holds the steps for each. */
  state?: TimeOffState | ApprovalsState | ConfirmCardState
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
// Phases 3 and 5 built the Handbook, Time off, and Approvals items and the at-a-glance figures, so
// what the sidebar still lacks is the one link Phase 7 adds.
const HOW_ITS_BUILT = 'Phase 7: the "How it\'s built" link in the sidebar, which is hidden until then'
const DIRECTORY_NAV = HOW_ITS_BUILT
const HANDBOOK_NAV = HOW_ITS_BUILT
const HOME_NAV = HOW_ITS_BUILT

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

/**
 * A row for screens 08 to 10: the real page against the real API with the scripted model, brought
 * to the state of the design file's name by the steps in capture.spec.ts. The seed's dates move
 * with today, and its people have different history from the frames' (Priya has no request ahead,
 * Marcus has one waiting, not two), so a row says where the figures or the dates can't match.
 */
/** Screen 10 states asked with "book next friday" or "I'm sick tomorrow", whose day the scripted
 * model works out from today. */
const DATE_DEPENDENT: readonly ConfirmCardState[] = [
  'pending',
  'pending-streaming',
  'confirming',
  'executed',
  'failed',
  'dismissed',
  'replaced',
  'expired',
  'holiday',
  'sick',
  'executed-variants',
  'conversation',
  'conversation-executed',
  'sensitive',
  'sensitive-work',
]
const DATE_CAVEAT =
  "Date-dependent: the scripted model's day can be a company holiday or a day off the schedule, and a capture taken on such a date shows a refusal instead of a card."

const pageRow = (
  folder: '08-time-off' | '09-approvals' | '10-confirm-cards',
  state: TimeOffState | ApprovalsState | ConfirmCardState,
  title: string,
  extra: Pick<ScreenRow, 'note' | 'persona' | 'target' | 'differsUntil'> = {},
): ScreenRow => {
  const screen = {
    '08-time-off': { label: '08 Time off', route: '/time-off', setup: 'time-off', who: 'Priya' },
    '09-approvals': { label: '09 Approvals', route: '/approvals', setup: 'approvals', who: 'Marcus' },
    '10-confirm-cards': {
      label: '10 Confirm cards',
      route: '/ask',
      setup: 'confirm-card',
      who: 'Priya',
    },
  } as const
  const { label, route, setup, who } = screen[folder]
  return {
    title: `${label}: ${title}`,
    designImage: `${SCREENS}/${folder}/desktop-${state}.png`,
    route,
    persona: who,
    setup,
    state,
    target: 'viewport',
    ...extra,
    ...(DATE_DEPENDENT.includes(state as ConfirmCardState)
      ? { note: [extra.note, DATE_CAVEAT].filter(Boolean).join(' ') }
      : {}),
  }
}

const SEED_DATES =
  'The seed has no request ahead for Priya, so the dates and figures differ from the frame'

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
    differsUntil: HOME_NAV,
    note: 'The clock says 21 h 30 min are left, as the design does',
  },
  {
    title: '02 App shell: persona menu',
    designImage: `${SCREENS}/02-app-shell/desktop-persona-menu.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'persona-menu',
    differsUntil: HOME_NAV,
  },
  {
    title: '02 App shell: switching',
    designImage: `${SCREENS}/02-app-shell/desktop-switching.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'switching',
    note: 'The switch request is held, so the switcher stays busy',
    differsUntil: HOME_NAV,
  },
  {
    title: '02 App shell: switched, with the toast',
    designImage: `${SCREENS}/02-app-shell/desktop-switched-toast.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'switched',
    note: "Marcus's home. The pointer rests on the toast so it stays open. The seed has 1 approval waiting for Marcus (Zara's), not the frame's 2",
    differsUntil: HOW_ITS_BUILT,
  },
  {
    title: '02 App shell: expiry banner',
    designImage: `${SCREENS}/02-app-shell/desktop-expiry-banner.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'expiry-banner',
    note: 'The clock says 2 h 50 min are left',
    differsUntil: HOME_NAV,
  },
  {
    title: '02 App shell: employee navigation',
    designImage: `${SCREENS}/02-app-shell/desktop-nav-employee.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'home',
    target: 'sidebar',
    note: "The sidebar, as Priya sees it (Mateo's is the same)",
    differsUntil: HOW_ITS_BUILT,
  },
  {
    title: '02 App shell: manager navigation',
    designImage: `${SCREENS}/02-app-shell/desktop-nav-manager.png`,
    route: '/ask',
    persona: 'Marcus',
    setup: 'home',
    target: 'sidebar',
    differsUntil: HOW_ITS_BUILT,
  },
  {
    title: '02 App shell: HR navigation',
    designImage: `${SCREENS}/02-app-shell/desktop-nav-hr.png`,
    route: '/ask',
    persona: 'Dana',
    setup: 'home',
    target: 'sidebar',
    differsUntil: `Phase 6: the Cases and Console items. ${HOW_ITS_BUILT}`,
  },

  {
    title: '03 Assistant home: default',
    designImage: `${SCREENS}/03-assistant-home/desktop-default.png`,
    route: '/ask',
    persona: 'Priya',
    setup: 'home',
    differsUntil: HOME_NAV,
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
    note: "The rail only. The frame's figures (days of PTO, a pending count) differ from the seed's hours, and requests pending now carries the marker when some wait",
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
    differsUntil: HOW_ITS_BUILT,
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
    differsUntil: DIRECTORY_NAV,
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
    differsUntil: HOW_ITS_BUILT,
  },
  {
    title: '05 Global states: something went wrong',
    designImage: `${SCREENS}/05-global-states/desktop-error.png`,
    route: '/directory',
    persona: 'Priya',
    setup: 'server-error',
    note: "The directory's list request is answered with a 500 and a request ID, so the error shows inside the shell",
    differsUntil:
      `${HOW_ITS_BUILT}. The build's reference is the full 32 characters, where the design draws 8`,
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
  // Screen 08, the Time off page. Priya, unless a row says otherwise.
  pageRow('08-time-off', 'default', 'default', {
    note: "Priya has four past approved requests and nothing ahead, so Upcoming is empty and the figures are the seed's, which change with the date (the frame shows 132 hours)",
  }),
  pageRow('08-time-off', 'default-full', 'default, full height', {
    target: 'page',
    note: 'The whole page. There is no denial row or note in the seed, so Past is shorter than the frame',
  }),
  pageRow('08-time-off', 'ceiling', 'at the PTO limit', {
    note: 'The seed has nobody at the 180-hour limit, so this is the default page. The notice and "Next: paused" are proved by the gallery state and the unit tests',
  }),
  pageRow('08-time-off', 'empty', 'no requests', {
    persona: 'Dana',
    note: "Dana has no requests in the seed, so My requests is empty. Her figures and schedule differ from Priya's frame",
  }),
  pageRow('08-time-off', 'loading', 'loading', {
    note: 'The balances request is held, so the skeletons stay',
  }),
  pageRow('08-time-off', 'error', 'error', {
    note: 'The balances request is answered with a 500 and a request ID, so the error shows inside the shell. The build shows the full 32-character reference',
  }),
  pageRow('08-time-off', 'form-one-day', 'form, one day', { note: SEED_DATES }),
  pageRow('08-time-off', 'form-half-day', 'form, half day', { note: SEED_DATES }),
  pageRow('08-time-off', 'form-weekend', 'form, across a weekend', {
    note: `A Friday to the Monday after. ${SEED_DATES}`,
  }),
  pageRow('08-time-off', 'form-holiday', 'form, across a holiday', {
    note: `The first company holiday ahead, with the day before and after. ${SEED_DATES}`,
  }),
  pageRow('08-time-off', 'form-sick-hours', 'form, sick time by the hour', {
    note: 'Sick time on the last scheduled day before today, 3 hours. Priya has 40 hours of sick leave in the seed, not 32',
  }),
  pageRow('08-time-off', 'form-short-notice', 'form, short notice', {
    note: `Four scheduled days starting tomorrow. ${SEED_DATES}`,
  }),
  pageRow('08-time-off', 'form-not-enough', 'form, not enough PTO', {
    note: `Sixteen scheduled days from two weeks out. ${SEED_DATES}`,
  }),
  pageRow('08-time-off', 'form-overlap', 'form, already booked', {
    note: 'A day is booked first through the form, then the form opens on it again. The frame overlaps the December 23 request',
  }),
  pageRow('08-time-off', 'form-submitting', 'form, submitting', {
    note: 'The send is held, so the button stays in its busy state',
  }),
  pageRow('08-time-off', 'submitted', 'submitted', {
    note: 'The pointer rests on the toast so it stays open. The PTO card counts the request as waiting',
  }),
  pageRow('08-time-off', 'submitted-sick', 'submitted, sick time', {
    note: 'The pointer rests on the toast so it stays open',
  }),
  pageRow('08-time-off', 'cancel-confirm', 'cancel confirm', {
    note: 'A request is made first, then its Cancel pressed. The frame cancels the December 23 request',
  }),
  pageRow('08-time-off', 'canceled', 'canceled', {
    note: 'A request is made and canceled, so it sits in Past as Canceled. The frame cancels the December 23 request',
  }),
  pageRow('08-time-off', 'date-picker-open', 'date picker', {
    note: 'Focus is on today, where the frame has it on October 30',
  }),
  pageRow('08-time-off', 'date-picker-sick', 'date picker, sick time', {
    note: 'Focus is on today, where the frame has it on a day 5 days back',
  }),
  pageRow('08-time-off', 'date-picker-range', 'date picker, a range over a holiday', {
    note: "The first company holiday ahead, focused so its name shows. The frame's is Thanksgiving",
  }),

  // Screen 09, the Approvals page. Marcus, with Priya's request made first so two wait, as in the
  // frames (the seed has only Zara's).
  pageRow('09-approvals', 'default', 'default', {
    note: "Priya's request is made on her Time off page first, so two wait, as in the frame. Zara's is the seed's, 21 days out; the frame's dates and figures differ",
  }),
  pageRow('09-approvals', 'default-full', 'default, full height', {
    target: 'page',
    note: "The whole page. Recent decisions holds the seed's history, not the frame's August 28 denial",
  }),
  pageRow('09-approvals', 'approve-confirm', 'approve dialog', {
    note: "Zara's Approve pressed, focus on Go back",
  }),
  pageRow('09-approvals', 'deny-confirm', 'deny dialog with a note', {
    note: "Zara's Deny pressed and a note typed; the count is the typed note's own, not the frame's 77",
  }),
  pageRow('09-approvals', 'deciding', 'deciding', {
    note: 'The decision is held, so the dialog stays on "Approving…"',
  }),
  pageRow('09-approvals', 'approved', 'approved', {
    note: "Zara approved. The pointer rests on the toast; focus is on Priya's Approve",
  }),
  pageRow('09-approvals', 'denied', 'denied with a note', {
    note: 'Zara denied with a note. The pointer rests on the toast',
  }),
  pageRow('09-approvals', 'conflict', 'conflict, canceled', {
    note: "STUB: Priya's request is canceled for real, and Marcus's queue read keeps listing it until he presses Approve, so the real API refuses and the card is held. The frame's card is Zara's",
  }),
  pageRow('09-approvals', 'empty', 'nothing waiting', {
    note: "Zara's request is approved first, then the page opened again, so the queue is empty",
  }),
  pageRow('09-approvals', 'loading', 'loading', {
    note: 'The time-off requests are held, so the skeletons stay',
  }),
  pageRow('09-approvals', 'error', 'error', {
    note: 'The requests are answered with a 500 and a request ID. The build shows the full 32-character reference',
  }),
  pageRow('09-approvals', 'nav-manager', 'navigation, manager', {
    target: 'sidebar',
    note: 'The sidebar as Marcus sees it on Approvals, with 2 waiting. The frame also draws hover, focus, none waiting, and Priya\'s navigation, which the gallery\'s nav states show',
  }),
  pageRow('09-approvals', 'home-manager', "Marcus's home", {
    persona: 'Marcus',
    note: "With Priya's request waiting, the rail reads 2 approvals waiting with the marker. His PTO figure is the seed's",
  }),

  // Screen 10, the confirm cards in the conversation. Priya, unless a row says otherwise.
  pageRow('10-confirm-cards', 'pending', 'pending', {
    note: 'Asked "book next friday". The scripted model\'s date and the seed\'s balance differ from the frame',
  }),
  pageRow('10-confirm-cards', 'pending-streaming', 'pending, answer still arriving', {
    note: "STUB: the real turn runs, and only its closing event is held back, so the real card shows while the answer is still being written. The line has no typing caret",
  }),
  pageRow('10-confirm-cards', 'confirming', 'confirming', {
    note: 'The confirm request is held, so the card stays on "Confirming…"',
  }),
  pageRow('10-confirm-cards', 'executed', 'executed', {
    note: 'Confirmed. The rail reads one request pending, without the cinnamon marker the frame draws beside it (reported, not built)',
  }),
  pageRow('10-confirm-cards', 'failed', 'failed', {
    note: 'The same day is booked through the Time off route after the card was made, so Confirm is refused for real (an overlap). The reason names the seed\'s date',
  }),
  pageRow('10-confirm-cards', 'dismissed', 'dismissed'),
  pageRow('10-confirm-cards', 'replaced', 'replaced', {
    note: 'A second "book next friday" makes the newer card. The frame\'s follow-up is a half day, which the scripted model can\'t ask for',
  }),
  pageRow('10-confirm-cards', 'expired', 'expired', {
    note: 'The card is aged past its 15 minutes with the test-only script, then Confirm is pressed',
  }),
  pageRow('10-confirm-cards', 'holiday', 'holiday skipped', {
    note: 'The scripted model can only book "next Friday", which is not a holiday, so this is the pending card. The skipped-holiday block is shown by the gallery state',
  }),
  pageRow('10-confirm-cards', 'sick', 'sick time', {
    note: 'Asked "I\'m sick tomorrow". Priya has 40 hours of sick leave in the seed, not 32',
  }),
  pageRow('10-confirm-cards', 'approve', 'approve, as Marcus', {
    persona: 'Marcus',
    note: 'Asked "approve it", which takes the first request waiting: Zara\'s from the seed, not Priya\'s as in the frame',
  }),
  pageRow('10-confirm-cards', 'deny', 'deny, as Marcus', {
    persona: 'Marcus',
    note: 'Asked "deny it", which takes Zara\'s request, with a note typed in the card. The frame\'s card is Zara\'s too',
  }),
  pageRow('10-confirm-cards', 'cancel', 'cancel', {
    note: 'A request is made on the Time off page first, then "cancel my request" asked. The frame cancels an approved request, so its balance and status differ',
  }),
  pageRow('10-confirm-cards', 'executed-variants', 'executed variants', {
    note: 'The end of Priya\'s thread, with three executed cards: a booking, sick time, and a cancel (scroll up for the first two). The frame also shows the holiday, approve, and deny variants, which are the gallery\'s states',
  }),
  pageRow('10-confirm-cards', 'conversation', 'conversation, show your work', {
    note: 'Asked "book next friday", with "Show your work" open. It lists the card tool only, because the scripted model does not read the balance first, where the frame also lists "Checked your time off"',
  }),
  pageRow('10-confirm-cards', 'conversation-executed', 'conversation, executed', {
    note: 'After Confirm, with "Show your work" open. The rail reads one request pending, without the frame\'s marker',
  }),
  pageRow('10-confirm-cards', 'sensitive', 'sensitive turn with a card', {
    note: 'STUB: the conversation GET puts a real sick-time card under a sensitive turn, because the scripted model cannot answer both in one message',
  }),
  pageRow('10-confirm-cards', 'sensitive-work', 'sensitive turn, show your work', {
    note: 'STUB: as the row above, with "Show your work" open',
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
