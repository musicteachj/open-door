// The inset keyboard-focus ring on menu and list rows, from the design's menu and filter rows
// (.od-menu__item:focus-visible, .od-filter__option:focus-visible): 2 px, solid, offset -2 px,
// the focus-ring color. The row's hover fill (neutral-hover) is only 1.15:1 against the white
// panel, and a checked row's tint hides it, so the ring is what shows where focus is.
export const rowFocusRing =
  'outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:-outline-offset-2 focus-visible:outline-focus-ring'
